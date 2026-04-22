'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/Card';
import {
  getNlpStatus,
  getAllTopicTrends,
  getJournalTopicTrends,
  getPublisherTopicTrends,
  listClusters,
  getClusterTrendSeries,
  getClusterArticles,
} from '@/lib/api';
import type { TopicTrendsData, TopicCluster, NlpStatus } from '@/lib/types';
import Link from 'next/link';

// ─── Constants ───────────────────────────────────────────────────────────────

const COLOR_PALETTE = [
  '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#14b8a6',
  '#a855f7', '#eab308', '#64748b', '#0ea5e9', '#d946ef',
  '#22c55e', '#f43f5e', '#fb923c', '#a3e635', '#38bdf8',
];

const TOP_N_OPTIONS = [10, 15, 20];

const PUBLISHERS = [
  { label: 'IEEE Xplore', value: 'IEEE' },
  { label: 'ACM Digital Library', value: 'ACM' },
  { label: 'Science Direct', value: 'Elsevier' },
];

const CLUSTER_PAGE_SIZE = 20;

type Mode = 'all' | 'journal' | 'publisher';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function capitalize(s: string): string {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const sorted = [...payload]
    .filter((p) => p.value != null && p.value > 0)
    .sort((a, b) => b.value - a.value);
  if (!sorted.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-3 shadow-lg text-xs max-h-72 overflow-y-auto min-w-[180px]">
      <p className="font-semibold text-slate-700 mb-2">{label}</p>
      {sorted.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 py-0.5">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: entry.color }} />
          <span className="text-slate-600 flex-1">{capitalize(entry.name)}</span>
          <span className="font-semibold text-slate-800 ml-2">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export function TopicTrendsSection() {
  // ── Core state ──
  const [mode, setMode] = useState<Mode>('all');
  const [nameInput, setNameInput] = useState('');
  const [submittedName, setSubmittedName] = useState('');

  // ── NLP model ──
  const [nlpStatus, setNlpStatus] = useState<NlpStatus | null>(null);
  const [modelVersion, setModelVersion] = useState<string | null>(null);

  // ── Top-N chart data ──
  const [data, setData] = useState<TopicTrendsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topN, setTopN] = useState(10);

  // ── Full cluster metadata list (lightweight) ──
  const [allClusters, setAllClusters] = useState<TopicCluster[]>([]);
  const [allLoading, setAllLoading] = useState(false);

  // ── On-demand series cache: topic_tag → { date → count } ──
  const [seriesCache, setSeriesCache] = useState<Map<string, Record<string, number>>>(new Map());
  const [fetchingTopics, setFetchingTopics] = useState<Set<string>>(new Set());

  // ── Visibility (which topic_tags appear on chart) ──
  const [visibleTopics, setVisibleTopics] = useState<Set<string>>(new Set());

  // ── Full-list UI ──
  const [fullListOpen, setFullListOpen] = useState(false);
  const [clusterSearch, setClusterSearch] = useState('');
  const [clusterPage, setClusterPage] = useState(0);

  // ── Cluster article panel ──
  type ClusterArticle = { id: string; title: string; doi?: string; url?: string; publication_date?: string };
  const [openArticleClusterId, setOpenArticleClusterId] = useState<number | null>(null);
  const [clusterArticles, setClusterArticles] = useState<ClusterArticle[]>([]);
  const [clusterArticlesLoading, setClusterArticlesLoading] = useState(false);
  const [clusterArticlesTotal, setClusterArticlesTotal] = useState(0);
  const [articleSearch, setArticleSearch] = useState('');
  const [articlePage, setArticlePage] = useState(0);
  const ARTICLE_PAGE_SIZE = 15;

  // ── NLP status on mount ──
  useEffect(() => {
    getNlpStatus()
      .then((status) => {
        setNlpStatus(status);
        setModelVersion(status.latest_model_version);
      })
      .catch(() => setNlpStatus(null));
  }, []);

  // ── Fetch helpers ──

  async function fetchTopN(name: string | undefined, n: number, mv: string) {
    setLoading(true);
    setError(null);
    try {
      let result: TopicTrendsData;
      if (mode === 'all') {
        result = await getAllTopicTrends(mv, n);
      } else if (mode === 'journal') {
        result = await getJournalTopicTrends(name ?? '', mv, n);
      } else {
        result = await getPublisherTopicTrends(name ?? '', mv, n);
      }
      if (!result) {
        setData({ graph_data: [], clusters: [] });
        setVisibleTopics(new Set());
        return;
      }
      setData(result);
      setVisibleTopics(new Set(result.clusters.map((c) => c.topic_tag)));
    } catch {
      setError('Veri yuklenirken hata olustu.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function fetchAllClusters(name: string | undefined, mv: string) {
    setAllLoading(true);
    try {
      const clusterType = mode === 'all' ? 'all' : mode === 'journal' ? 'journal' : 'publisher';
      const groupId = mode !== 'all' ? (name ?? '') : undefined;
      const res = await listClusters(mv, clusterType, groupId);
      setAllClusters(res.clusters);
    } catch {
      setAllClusters([]);
    } finally {
      setAllLoading(false);
    }
  }

  function fetchBoth(name?: string, n?: number) {
    if (!modelVersion) return;
    const resolvedN = n ?? topN;
    setFullListOpen(false);
    setClusterSearch('');
    setClusterPage(0);
    setSeriesCache(new Map());
    setFetchingTopics(new Set());
    setOpenArticleClusterId(null);
    setClusterArticles([]);
    setArticleSearch('');
    setArticlePage(0);
    fetchTopN(name, resolvedN, modelVersion);
    fetchAllClusters(name, modelVersion);
  }

  async function fetchArticlePanel(clusterId: number, page: number, search: string) {
    if (!modelVersion) return;
    setClusterArticlesLoading(true);
    try {
      const res = await getClusterArticles(clusterId, modelVersion, {
        skip: page * ARTICLE_PAGE_SIZE,
        limit: ARTICLE_PAGE_SIZE,
        search: search.trim() || undefined,
      });
      setClusterArticles(res.articles);
      setClusterArticlesTotal(res.total_count);
    } catch {
      setClusterArticles([]);
      setClusterArticlesTotal(0);
    } finally {
      setClusterArticlesLoading(false);
    }
  }

  async function openArticlePanel(cluster: TopicCluster) {
    if (openArticleClusterId === cluster.cluster_id) {
      setOpenArticleClusterId(null);
      setArticleSearch('');
      setArticlePage(0);
      return;
    }
    setOpenArticleClusterId(cluster.cluster_id);
    setArticleSearch('');
    setArticlePage(0);
    fetchArticlePanel(cluster.cluster_id, 0, '');
  }

  // ── Auto-fetch on mode=all ──
  useEffect(() => {
    if (mode === 'all' && modelVersion) {
      fetchBoth();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, modelVersion]);

  // ── Article search debounce (fires 500ms after articleSearch stops changing) ──
  useEffect(() => {
    if (openArticleClusterId === null) return;
    const t = setTimeout(() => {
      fetchArticlePanel(openArticleClusterId, 0, articleSearch);
    }, 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [articleSearch, openArticleClusterId]);

  // ── Handlers ──

  function handleSearch() {
    const trimmed = nameInput.trim();
    if (!trimmed) return;
    setSubmittedName(trimmed);
    fetchBoth(trimmed);
  }

  function handleModeChange(newMode: Mode) {
    setMode(newMode);
    setData(null);
    setAllClusters([]);
    setSeriesCache(new Map());
    setFetchingTopics(new Set());
    setError(null);
    setNameInput('');
    setSubmittedName('');
    setVisibleTopics(new Set());
    setFullListOpen(false);
    setClusterSearch('');
    setClusterPage(0);
  }

  function handleTopNChange(n: number) {
    setTopN(n);
    if (!modelVersion) return;
    fetchTopN(submittedName || undefined, n, modelVersion);
  }

  // ── Derived ──

  // Top-N topic tags
  const topNSet = useMemo(
    () => new Set((data?.clusters ?? []).map((c) => c.topic_tag)),
    [data],
  );

  const toggleVisible = useCallback((cluster: TopicCluster) => {
    const tag = cluster.topic_tag;
    const willBeVisible = !visibleTopics.has(tag);

    if (willBeVisible && !topNSet.has(tag) && !seriesCache.has(tag) && modelVersion) {
      const clusterType = (mode === 'all' ? 'all' : mode === 'journal' ? 'journal' : 'publisher') as 'all' | 'journal' | 'publisher';
      const groupId = mode !== 'all' ? submittedName : undefined;
      setFetchingTopics((prev) => new Set(prev).add(tag));
      getClusterTrendSeries(cluster.cluster_id, modelVersion, clusterType, groupId)
        .then((res) => {
          const map: Record<string, number> = {};
          for (const { date, count } of res.series) map[date] = count;
          setSeriesCache((prev) => new Map(prev).set(tag, map));
        })
        .catch(() => {})
        .finally(() => {
          setFetchingTopics((prev) => {
            const next = new Set(prev);
            next.delete(tag);
            return next;
          });
        });
    }

    setVisibleTopics((prev) => {
      const next = new Set(prev);
      next.has(tag) ? next.delete(tag) : next.add(tag);
      return next;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleTopics, topNSet, seriesCache, modelVersion, mode, submittedName]);

  // Color map: top-N first, then extra activated topics
  const topicColorMap = useMemo(() => {
    const map = new Map<string, string>();
    (data?.clusters ?? []).forEach((c, idx) => {
      map.set(c.topic_tag, COLOR_PALETTE[idx % COLOR_PALETTE.length]);
    });
    let extra = data?.clusters.length ?? 0;
    allClusters.forEach((c) => {
      if (!map.has(c.topic_tag)) {
        map.set(c.topic_tag, COLOR_PALETTE[extra % COLOR_PALETTE.length]);
        extra++;
      }
    });
    return map;
  }, [data, allClusters]);

  // Merged graph_data: top-N data + on-demand series from cache
  const mergedGraphData = useMemo(() => {
    if (!data?.graph_data) return [];
    const dateMap = new Map<string, Record<string, string | number>>();
    for (const entry of data.graph_data) dateMap.set(entry.date as string, { ...entry });
    for (const [tag, seriesMap] of seriesCache.entries()) {
      if (!visibleTopics.has(tag)) continue;
      for (const [date, count] of Object.entries(seriesMap)) {
        if (!dateMap.has(date)) dateMap.set(date, { date });
        dateMap.get(date)![tag] = count;
      }
    }
    return Array.from(dateMap.values()).sort((a, b) =>
      String(a.date).localeCompare(String(b.date))
    );
  }, [data, seriesCache, visibleTopics]);

  // Lines to render on chart — use local `seen` set to guarantee no duplicate dataKeys
  // (prevents double entries during parallel fetch race conditions)
  const chartLines = useMemo(() => {
    const seen = new Set<string>();
    const lines: TopicCluster[] = [];
    for (const c of data?.clusters ?? []) {
      if (visibleTopics.has(c.topic_tag) && !seen.has(c.topic_tag)) {
        seen.add(c.topic_tag);
        lines.push(c);
      }
    }
    for (const c of allClusters) {
      if (visibleTopics.has(c.topic_tag) && !seen.has(c.topic_tag)) {
        seen.add(c.topic_tag);
        lines.push(c);
      }
    }
    return lines;
  }, [data, allClusters, visibleTopics]);

  const filteredAll = useMemo(() => {
    if (!clusterSearch.trim()) return allClusters;
    const q = clusterSearch.toLowerCase();
    return allClusters.filter((c) => c.topic_tag.toLowerCase().includes(q));
  }, [allClusters, clusterSearch]);

  const totalPages = Math.ceil(filteredAll.length / CLUSTER_PAGE_SIZE);
  const pagedAll = filteredAll.slice(
    clusterPage * CLUSTER_PAGE_SIZE,
    (clusterPage + 1) * CLUSTER_PAGE_SIZE,
  );

  const noModel = nlpStatus !== null && !nlpStatus.has_trained_model;

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <Card>
      <CardHeader>
        <CardTitle>Konu Trend Analizi</CardTitle>
        <CardDescription>
          NLP kumeleme modeline gore konu trendleri
          {nlpStatus?.latest_model_version && (
            <span className="ml-2 text-xs text-slate-400">
              (model: {nlpStatus.latest_model_version})
            </span>
          )}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Mode selector */}
        <div className="flex gap-2">
          {(['all', 'journal', 'publisher'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => handleModeChange(m)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === m
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {m === 'all' ? 'Tumu' : m === 'journal' ? 'Dergi Bazli' : 'Yayinci Bazli'}
            </button>
          ))}
        </div>

        {/* Journal input */}
        {mode === 'journal' && (
          <div className="flex gap-2">
            <input
              type="text"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Dergi adi girin..."
              className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <button
              onClick={handleSearch}
              disabled={!nameInput.trim() || loading || !modelVersion}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Ara
            </button>
          </div>
        )}

        {/* Publisher buttons */}
        {mode === 'publisher' && (
          <div className="flex gap-2 flex-wrap">
            {PUBLISHERS.map((pub) => (
              <button
                key={pub.value}
                disabled={loading || !modelVersion}
                onClick={() => {
                  setNameInput(pub.value);
                  setSubmittedName(pub.value);
                  fetchBoth(pub.value);
                }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                  submittedName === pub.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {pub.label}
              </button>
            ))}
          </div>
        )}

        {/* No model */}
        {noModel && (
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-600 text-sm">
            Henuz egitilmis bir NLP modeli bulunmuyor. Model egitildikten sonra konu trendleri burada gorunecektir.
          </div>
        )}

        {/* Loading skeleton */}
        {loading && <div className="animate-pulse h-64 bg-slate-100 rounded-lg" />}

        {/* Error */}
        {!loading && error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
            {error}
          </div>
        )}

        {/* Chart section */}
        {!loading && !error && data && data.graph_data.length > 0 && (
          <>
            {/* Top-N selector row */}
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-500">
                Grafik: en yuksek{' '}
                <span className="font-semibold text-slate-700">{topN}</span> konu
                {data.clusters.length < topN && data.clusters.length > 0 && (
                  <span className="ml-1 text-slate-400">
                    ({data.clusters.length} konu mevcut)
                  </span>
                )}
              </p>
              <div className="flex items-center gap-1">
                <span className="text-xs text-slate-500 mr-1">Grafik:</span>
                {TOP_N_OPTIONS.map((n) => (
                  <button
                    key={n}
                    onClick={() => handleTopNChange(n)}
                    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                      topN === n
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    Top {n}
                  </button>
                ))}
              </div>
            </div>

            {/* LineChart */}
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={mergedGraphData} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
                <XAxis
                  dataKey="date"
                  angle={-35}
                  textAnchor="end"
                  tick={{ fontSize: 11 }}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                {chartLines.map((cluster) => {
                  const color = topicColorMap.get(cluster.topic_tag) ?? '#94a3b8';
                  return (
                    <Line
                      key={cluster.cluster_id}
                      type="monotone"
                      dataKey={cluster.topic_tag}
                      name={cluster.topic_tag}
                      stroke={color}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                      activeDot={{ r: 7, strokeWidth: 2, stroke: '#fff', fill: color }}
                    />
                  );
                })}
              </LineChart>
            </ResponsiveContainer>

            {/* Top-N badge list — click to toggle */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                Grafikteki Konular (Top {topN}) — Tikla: Goster/Gizle
              </p>
              <div className="flex flex-wrap gap-2">
                {data.clusters.map((cluster, idx) => {
                  const color = COLOR_PALETTE[idx % COLOR_PALETTE.length];
                  const visible = visibleTopics.has(cluster.topic_tag);
                  return (
                    <button
                      key={cluster.cluster_id}
                      onClick={() => toggleVisible(cluster)}
                      title={`${cluster.article_count} makale — tikla: ${visible ? 'gizle' : 'goster'}`}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                        visible
                          ? 'border-transparent text-white shadow-sm'
                          : 'border-slate-300 text-slate-400 bg-white'
                      }`}
                      style={visible ? { backgroundColor: color, borderColor: color } : {}}
                    >
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: visible ? 'rgba(255,255,255,0.7)' : color }}
                      />
                      <span className={visible ? '' : 'line-through'}>{capitalize(cluster.topic_tag)}</span>
                      <span className={`ml-0.5 ${visible ? 'opacity-70' : 'opacity-50'}`}>
                        ({cluster.article_count})
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Full cluster list — paginated */}
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200">
                <span className="text-sm font-semibold text-slate-700">
                  Tum Konular
                  {allClusters.length > 0 && (
                    <span className="ml-2 text-xs font-normal text-slate-400">
                      ({allClusters.length} konu)
                    </span>
                  )}
                </span>
                <button
                  onClick={() => setFullListOpen((v) => !v)}
                  className="text-xs text-emerald-600 hover:text-emerald-700 font-medium"
                >
                  {fullListOpen ? 'Kapat ▲' : 'Ac ▼'}
                </button>
              </div>

              {fullListOpen && (
                <div className="p-4 space-y-3">
                  {/* Search */}
                  <input
                    type="text"
                    value={clusterSearch}
                    onChange={(e) => {
                      setClusterSearch(e.target.value);
                      setClusterPage(0);
                    }}
                    placeholder="Konu ara..."
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />

                  {/* Legend */}
                  <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 pb-1 border-b border-slate-100">
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500" />
                      Top {topN} — gorunuyor
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-400" />
                      Eklendi (Top {topN} disi)
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block w-2.5 h-2.5 rounded-full bg-slate-300" />
                      Gizli (tikla: goster)
                    </span>
                  </div>

                  {/* Loading */}
                  {allLoading && (
                    <div className="text-center py-6 text-sm text-slate-400 animate-pulse">
                      Konular yukleniyor...
                    </div>
                  )}

                  {/* Rows */}
                  {!allLoading && pagedAll.map((cluster) => {
                    const isTopN = topNSet.has(cluster.topic_tag);
                    const visible = visibleTopics.has(cluster.topic_tag);
                    const isFetching = fetchingTopics.has(cluster.topic_tag);
                    const color = topicColorMap.get(cluster.topic_tag) ?? '#cbd5e1';
                    const articlesOpen = openArticleClusterId === cluster.cluster_id;

                    return (
                      <div key={cluster.cluster_id}>
                        <div
                          onClick={() => !isFetching && toggleVisible(cluster)}
                          className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-all select-none cursor-pointer hover:bg-slate-50 active:bg-slate-100 ${
                            visible
                              ? 'border-slate-300 bg-white'
                              : 'border-slate-200 bg-white opacity-60'
                          }`}
                        >
                          <span
                            className={`w-3 h-3 rounded-full flex-shrink-0 transition-opacity ${visible ? '' : 'opacity-30'}`}
                            style={{ backgroundColor: color }}
                          />
                          <span
                            className={`flex-1 text-sm font-medium truncate ${
                              visible ? 'text-slate-800' : 'text-slate-400 line-through'
                            }`}
                          >
                            {capitalize(cluster.topic_tag)}
                          </span>
                          <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full flex-shrink-0">
                            {articlesOpen && !clusterArticlesLoading
                              ? clusterArticlesTotal
                              : cluster.article_count} makale
                          </span>
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${
                              visible
                                ? isTopN
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-blue-100 text-blue-700'
                                : 'bg-slate-100 text-slate-500'
                            }`}
                          >
                            {isFetching ? 'Yukleniyor...' : visible ? (isTopN ? 'Top ' + topN : 'Eklendi') : 'Gizli'}
                          </span>
                          {/* Article list toggle button */}
                          <button
                            onClick={(e) => { e.stopPropagation(); openArticlePanel(cluster); }}
                            title="Makaleleri goster/gizle"
                            className={`flex-shrink-0 px-2 py-0.5 text-xs rounded-lg border transition-colors ${
                              articlesOpen
                                ? 'bg-indigo-600 text-white border-indigo-600'
                                : 'bg-white text-indigo-600 border-indigo-200 hover:bg-indigo-50'
                            }`}
                          >
                            Makaleler {articlesOpen ? '▲' : '▼'}
                          </button>
                        </div>

                        {/* Article panel */}
                        {articlesOpen && (
                          <div className="ml-6 mt-1 mb-2 border border-indigo-100 rounded-lg bg-indigo-50/40 overflow-hidden">
                            {/* Search bar */}
                            <div className="px-4 pt-3 pb-2 bg-indigo-50 border-b border-indigo-100">
                              <input
                                type="text"
                                value={articleSearch}
                                onChange={(e) => {
                                  setArticleSearch(e.target.value);
                                  setArticlePage(0);
                                }}
                                placeholder="Makale başlığında ara..."
                                className="w-full px-3 py-1.5 text-xs border border-indigo-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                              />
                            </div>

                            {clusterArticlesLoading ? (
                              <p className="text-xs text-slate-400 animate-pulse px-4 py-3">Makaleler yukleniyor...</p>
                            ) : clusterArticles.length === 0 ? (
                              <p className="text-xs text-slate-400 px-4 py-3">Makale bulunamadi.</p>
                            ) : (
                              <>
                                <ul className="divide-y divide-indigo-100">
                                  <li className="px-4 py-2 text-xs text-slate-400 font-medium bg-indigo-50 sticky top-0">
                                    {clusterArticlesTotal} makale
                                    {articleSearch.trim() && ' (arama sonucu)'}
                                    {' — '}sayfa {articlePage + 1} / {Math.ceil(clusterArticlesTotal / ARTICLE_PAGE_SIZE) || 1}
                                  </li>
                                  {clusterArticles.map((art) => (
                                    <li key={art.id} className="flex items-center gap-2 px-4 py-2.5 hover:bg-indigo-50 group">
                                      <span className="flex-1 text-xs text-slate-700 line-clamp-2 group-hover:text-indigo-700 transition-colors">
                                        {art.title}
                                      </span>
                                      <Link
                                        href={`/articles?article_id=${art.id}`}
                                        onClick={(e) => e.stopPropagation()}
                                        className="flex-shrink-0 px-2.5 py-1 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors whitespace-nowrap"
                                      >
                                        Goruntule →
                                      </Link>
                                    </li>
                                  ))}
                                </ul>

                                {/* Article pagination */}
                                {Math.ceil(clusterArticlesTotal / ARTICLE_PAGE_SIZE) > 1 && (
                                  <div className="flex items-center justify-between px-4 py-2 border-t border-indigo-100 bg-indigo-50">
                                    <button
                                      onClick={() => {
                                        const np = articlePage - 1;
                                        setArticlePage(np);
                                        if (openArticleClusterId !== null) fetchArticlePanel(openArticleClusterId, np, articleSearch);
                                      }}
                                      disabled={articlePage === 0 || clusterArticlesLoading}
                                      className="px-3 py-1 text-xs font-medium rounded-lg bg-white border border-indigo-200 text-indigo-600 hover:bg-indigo-50 disabled:opacity-40 disabled:cursor-not-allowed"
                                    >
                                      ← Onceki
                                    </button>
                                    <span className="text-xs text-slate-500">
                                      {articlePage + 1} / {Math.ceil(clusterArticlesTotal / ARTICLE_PAGE_SIZE)}
                                    </span>
                                    <button
                                      onClick={() => {
                                        const np = articlePage + 1;
                                        setArticlePage(np);
                                        if (openArticleClusterId !== null) fetchArticlePanel(openArticleClusterId, np, articleSearch);
                                      }}
                                      disabled={articlePage >= Math.ceil(clusterArticlesTotal / ARTICLE_PAGE_SIZE) - 1 || clusterArticlesLoading}
                                      className="px-3 py-1 text-xs font-medium rounded-lg bg-white border border-indigo-200 text-indigo-600 hover:bg-indigo-50 disabled:opacity-40 disabled:cursor-not-allowed"
                                    >
                                      Sonraki →
                                    </button>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {!allLoading && pagedAll.length === 0 && (
                    <p className="text-sm text-slate-400 text-center py-4">Sonuc bulunamadi.</p>
                  )}

                  {/* Pagination */}
                  {!allLoading && totalPages > 1 && (
                    <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                      <button
                        onClick={() => setClusterPage((p) => Math.max(0, p - 1))}
                        disabled={clusterPage === 0}
                        className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Onceki
                      </button>
                      <span className="text-xs text-slate-500">
                        {clusterPage + 1} / {totalPages}
                        <span className="ml-1 text-slate-400">({filteredAll.length} konu)</span>
                      </span>
                      <button
                        onClick={() => setClusterPage((p) => Math.min(totalPages - 1, p + 1))}
                        disabled={clusterPage >= totalPages - 1}
                        className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Sonraki
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {/* Empty state */}
        {!loading && !error && data && data.graph_data.length === 0 && (
          <div className="text-center py-10 text-slate-500 text-sm">
            {mode !== 'all'
              ? 'Bu yayinci/dergi icin cluster verisi bulunamadi. Modeli yeniden egiterek publisher/journal clustering ekleyebilirsiniz.'
              : 'Bu sorgu icin grafik verisi bulunamadi.'}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
