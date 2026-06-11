'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';
import { getClusterTrendSeries, getClusterArticles } from '@/lib/api';
import type { TopicTrendsData, TopicCluster } from '@/lib/types';
import Link from 'next/link';
import { TopicDistributionPie } from './TopicDistributionPie';

// ─── Constants ───────────────────────────────────────────────────────────────

export const COLOR_PALETTE = [
  '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#14b8a6',
  '#a855f7', '#eab308', '#64748b', '#0ea5e9', '#d946ef',
  '#22c55e', '#f43f5e', '#fb923c', '#a3e635', '#38bdf8',
];

const TOP_N_OPTIONS = [10, 15, 20];
const CLUSTER_PAGE_SIZE = 20;
const ARTICLE_PAGE_SIZE = 15;

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

// ─── Props ────────────────────────────────────────────────────────────────────

export interface TopicTrendChartProps {
  data: TopicTrendsData;
  allClusters: TopicCluster[];
  allLoading?: boolean;
  topN: number;
  /** When provided, top-N selector is shown and triggers this callback. */
  onTopNChange?: (n: number) => void;
  modelVersion: string | null;
  clusterType: 'all' | 'journal' | 'publisher';
  /** Journal name or publisher name used for on-demand series fetching. */
  groupId?: string;
  /** Whether the chart is currently visible — guards wheel-zoom from firing when hidden. */
  visible?: boolean;
  keywordDistribution?: Record<string, number>;
  hideFullClusterList?: boolean;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function TopicTrendChart({
  data,
  allClusters,
  allLoading = false,
  topN,
  onTopNChange,
  modelVersion,
  clusterType,
  groupId,
  visible = true,
  keywordDistribution,
  hideFullClusterList = false,
}: TopicTrendChartProps) {
  const clusters = data.clusters ?? [];
  // ── On-demand series cache ──
  const [seriesCache, setSeriesCache] = useState<Map<string, Record<string, number>>>(new Map());
  const [fetchingTopics, setFetchingTopics] = useState<Set<string>>(new Set());

  // ── Visibility ──
  const [visibleTopics, setVisibleTopics] = useState<Set<string>>(
    () => new Set((data.clusters ?? []).map((c) => c.topic_tag)),
  );

  // ── Full-list UI ──
  const [fullListOpen, setFullListOpen] = useState(false);
  const [clusterSearch, setClusterSearch] = useState('');
  const [clusterPage, setClusterPage] = useState(0);

  // ── Zoom ──
  const [zoomStart, setZoomStart] = useState(0);
  const [zoomEnd, setZoomEnd] = useState<number | null>(null);
  const isZoomingRef = useRef(false);
  const zoomStartRef = useRef(0);
  const zoomEndRef = useRef<number | null>(null);
  const mergedGraphDataLenRef = useRef(0);
  const chartWrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => { zoomStartRef.current = zoomStart; }, [zoomStart]);
  useEffect(() => { zoomEndRef.current = zoomEnd; }, [zoomEnd]);

  // ── Article panel ──
  type ClusterArticle = { id: string; title: string; doi?: string; url?: string; publication_date?: string };
  const [openArticleClusterId, setOpenArticleClusterId] = useState<number | null>(null);
  const [clusterArticles, setClusterArticles] = useState<ClusterArticle[]>([]);
  const [clusterArticlesLoading, setClusterArticlesLoading] = useState(false);
  const [clusterArticlesTotal, setClusterArticlesTotal] = useState(0);
  const [articleSearch, setArticleSearch] = useState('');
  const [articlePage, setArticlePage] = useState(0);

  // ── Reset all internal state when data changes ──
  useEffect(() => {
    setVisibleTopics(new Set((data.clusters ?? []).map((c) => c.topic_tag)));
    setSeriesCache(new Map());
    setFetchingTopics(new Set());
    setZoomStart(0);
    setZoomEnd(null);
    setFullListOpen(false);
    setClusterSearch('');
    setClusterPage(0);
    setOpenArticleClusterId(null);
    setClusterArticles([]);
    setArticleSearch('');
    setArticlePage(0);
    isZoomingRef.current = false;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // ── Derived ──

  const topNSet = useMemo(
    () => new Set(clusters.map((c) => c.topic_tag)),
    [clusters],
  );

  const toggleVisible = useCallback(
    (cluster: TopicCluster) => {
      const tag = cluster.topic_tag;
      const willBeVisible = !visibleTopics.has(tag);
      if (willBeVisible && !topNSet.has(tag) && !seriesCache.has(tag) && modelVersion) {
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
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visibleTopics, topNSet, seriesCache, modelVersion, clusterType, groupId],
  );

  const topicColorMap = useMemo(() => {
    const map = new Map<string, string>();
    clusters.forEach((c, idx) => map.set(c.topic_tag, COLOR_PALETTE[idx % COLOR_PALETTE.length]));
    let extra = clusters.length;
    allClusters.forEach((c) => {
      if (!map.has(c.topic_tag)) {
        map.set(c.topic_tag, COLOR_PALETTE[extra % COLOR_PALETTE.length]);
        extra++;
      }
    });
    return map;
  }, [clusters, allClusters]);

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
      String(a.date).localeCompare(String(b.date)),
    );
  }, [data, seriesCache, visibleTopics]);

  useEffect(() => { mergedGraphDataLenRef.current = mergedGraphData.length; }, [mergedGraphData.length]);

  const chartLines = useMemo(() => {
    const seen = new Set<string>();
    const lines: TopicCluster[] = [];
    for (const c of clusters) {
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
  }, [clusters, allClusters, visibleTopics]);

  const visibleChartData = useMemo(() => {
    if (mergedGraphData.length === 0) return mergedGraphData;
    const end = zoomEnd ?? mergedGraphData.length;
    return mergedGraphData.slice(zoomStart, end);
  }, [mergedGraphData, zoomStart, zoomEnd]);

  const isZoomed = zoomStart > 0 || (zoomEnd !== null && zoomEnd < mergedGraphData.length);

  // ── Pie source from zoomed range ──
  const pieSource = useMemo(() => {
    // If zoom is applied and we have visible chart data, compute pie from zoomed range
    if (isZoomed && visibleChartData.length > 0) {
      const topicTotals: Record<string, number> = {};
      for (const entry of visibleChartData) {
        for (const [key, value] of Object.entries(entry)) {
          if (key !== 'date' && typeof value === 'number' && value > 0) {
            topicTotals[key] = (topicTotals[key] ?? 0) + value;
          }
        }
      }
      // If we got data from zoomed range, use it; otherwise fallback
      if (Object.keys(topicTotals).length > 0) {
        return topicTotals;
      }
    }
    // Default: use keyword distribution or full distribution
    return keywordDistribution ?? data.keyword_distribution;
  }, [isZoomed, visibleChartData, keywordDistribution, data.keyword_distribution]);

  function resetZoom() {
    isZoomingRef.current = true;
    setZoomStart(0);
    setZoomEnd(null);
  }

  // ── Wheel zoom (passive:false to block page scroll) ──
  useEffect(() => {
    const el = chartWrapperRef.current;
    if (!el) return;
    let rafId: number | null = null;
    let pendingDelta = 0;
    let pendingClientX: number | null = null;

    function applyZoomOnce() {
      rafId = null;
      const delta = pendingDelta;
      const clientX = pendingClientX;
      pendingDelta = 0;
      pendingClientX = null;
      if (delta === 0 || clientX == null) return;
      isZoomingRef.current = true;
      const len = mergedGraphDataLenRef.current;
      if (len === 0) return;
      const curStart = zoomStartRef.current;
      const curEnd = zoomEndRef.current ?? len;
      const range = curEnd - curStart;
      const step = Math.max(1, Math.floor(range * 0.12));
      const rect = (el as HTMLDivElement).getBoundingClientRect();
      const mouseRatio = rect.width > 0
        ? Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
        : 0.5;
      if (delta < 0) {
        const cutLeft = Math.round(step * mouseRatio);
        const cutRight = Math.round(step * (1 - mouseRatio));
        setZoomStart(Math.min(curStart + cutLeft, curEnd - 3));
        setZoomEnd(Math.max(curEnd - cutRight, curStart + cutLeft + 3));
      } else {
        const addLeft = Math.round(step * mouseRatio);
        const addRight = Math.round(step * (1 - mouseRatio));
        const newStart = Math.max(0, curStart - addLeft);
        const newEnd = Math.min(len, curEnd + addRight);
        setZoomStart(newStart);
        setZoomEnd(newEnd === len ? null : newEnd);
      }
    }

    function onWheel(e: WheelEvent) {
      if (!visible) return;
      if (!data || data.graph_data.length === 0) return;
      e.preventDefault();
      pendingDelta += e.deltaY;
      pendingClientX = e.clientX;
      if (rafId == null) rafId = window.requestAnimationFrame(applyZoomOnce);
    }

    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      if (rafId != null) window.cancelAnimationFrame(rafId);
      el.removeEventListener('wheel', onWheel);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, visible]);

  // ── Article panel helpers ──

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

  useEffect(() => {
    if (openArticleClusterId === null) return;
    const t = setTimeout(() => {
      fetchArticlePanel(openArticleClusterId, 0, articleSearch);
    }, 500);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [articleSearch, openArticleClusterId]);

  const filteredAll = useMemo(() => {
    if (!clusterSearch.trim()) return allClusters;
    const q = clusterSearch.toLowerCase();
    return allClusters.filter((c) => c.topic_tag.toLowerCase().includes(q));
  }, [allClusters, clusterSearch]);

  const totalClusterPages = Math.ceil(filteredAll.length / CLUSTER_PAGE_SIZE);
  const pagedAll = filteredAll.slice(
    clusterPage * CLUSTER_PAGE_SIZE,
    (clusterPage + 1) * CLUSTER_PAGE_SIZE,
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      {/* Top-N selector row */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-500">
          Grafik: en yüksek{' '}
          <span className="font-semibold text-slate-700">{topN}</span> konu
          {clusters.length < topN && clusters.length > 0 && (
            <span className="ml-1 text-slate-400">
              ({clusters.length} konu mevcut)
            </span>
          )}
          {isZoomed && (
            <span className="ml-2 text-xs text-indigo-600">
              • {visibleChartData.length} / {mergedGraphData.length} tarih gösteriliyor
            </span>
          )}
        </p>
        <div className="flex items-center gap-1 flex-wrap">
          {onTopNChange && (
            <>
              <span className="text-xs text-slate-500 mr-1">Grafik:</span>
              {TOP_N_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => onTopNChange(n)}
                  className={`cursor-pointer px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    topN === n
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Top {n}
                </button>
              ))}
            </>
          )}
        </div>
      </div>

      {/* LineChart */}
      <div
        ref={chartWrapperRef}
        style={{ touchAction: 'none', userSelect: 'none' }}
        title="Fare tekerleği ile zoom yapabilirsiniz"
        className="relative"
      >
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={visibleChartData} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
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
                  dot={(dotProps: { cx?: number; cy?: number; index: number; payload: Record<string, unknown> }) => {
                    const { cx, cy, index, payload } = dotProps;
                    if (cx == null || cy == null || payload[cluster.topic_tag] == null) return <g />;
                    const firstIdx = visibleChartData.findIndex((entry) => entry[cluster.topic_tag] != null);
                    if (index !== firstIdx) return <g />;
                    return <circle cx={cx} cy={cy} r={3} fill={color} stroke="#fff" strokeWidth={1.5} />;
                  }}
                  connectNulls
                  isAnimationActive={!isZoomingRef.current}
                  animationDuration={600}
                  animationEasing="ease-out"
                  activeDot={{ r: 7, strokeWidth: 2, stroke: '#fff', fill: color }}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
        {isZoomed && (
          <button
            onClick={resetZoom}
            className="cursor-pointer absolute top-2 right-2 px-2 py-1 text-xs font-medium rounded-lg bg-white border border-amber-300 text-amber-700 hover:bg-amber-50 shadow-sm transition-colors"
          >
            ↺ Zoom Sıfırla
          </button>
        )}
      </div>

      {pieSource && Object.keys(pieSource).length > 0 && (
        <div className="border border-slate-200 rounded-xl p-4 mt-4">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Konu dağılımı
          </p>
          <TopicDistributionPie data={pieSource} colorMap={topicColorMap} />
        </div>
      )}

      {/* Topic badge list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            Grafikteki Konular (Top {topN}) — Tıkla: Göster/Gizle
          </p>
          <button
            onClick={() => {
              const allVisible = clusters.every((c) => visibleTopics.has(c.topic_tag));
              if (allVisible) {
                setVisibleTopics(new Set());
              } else {
                setVisibleTopics(new Set(clusters.map((c) => c.topic_tag)));
              }
            }}
            className="cursor-pointer text-xs font-medium px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors flex-shrink-0"
          >
            {clusters.every((c) => visibleTopics.has(c.topic_tag)) ? 'Hepsini Gizle' : 'Hepsini Göster'}
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {clusters.map((cluster, idx) => {
            const color = topicColorMap.get(cluster.topic_tag) ?? COLOR_PALETTE[idx % COLOR_PALETTE.length];
            const isVisible = visibleTopics.has(cluster.topic_tag);
            return (
              <button
                key={cluster.cluster_id}
                onClick={() => toggleVisible(cluster)}
                title={`${cluster.article_count} makale — tıkla: ${isVisible ? 'gizle' : 'göster'}`}
                className={`cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                  isVisible
                    ? 'border-transparent text-white shadow-sm'
                    : 'border-slate-300 text-slate-400 bg-white'
                }`}
                style={isVisible ? { backgroundColor: color, borderColor: color } : {}}
              >
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: isVisible ? 'rgba(255,255,255,0.7)' : color }}
                />
                <span className={isVisible ? '' : 'line-through'}>{capitalize(cluster.topic_tag)}</span>
                <span className={`ml-0.5 ${isVisible ? 'opacity-70' : 'opacity-50'}`}>
                  ({cluster.article_count})
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {!hideFullClusterList && (
      <div className="border border-slate-200 rounded-xl overflow-hidden mt-4">
        <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200">
          <span className="text-sm font-semibold text-slate-700">
            Tüm Konular
            {allClusters.length > 0 && (
              <span className="ml-2 text-xs font-normal text-slate-400">
                ({allClusters.length} konu)
              </span>
            )}
          </span>
          <button
            onClick={() => setFullListOpen((v) => !v)}
            className="cursor-pointer text-xs text-indigo-600 hover:text-indigo-700 font-medium"
          >
            {fullListOpen ? 'Kapat ▲' : 'Aç ▼'}
          </button>
        </div>

        {fullListOpen && (
          <div className="p-4 space-y-3">
            <input
              type="text"
              value={clusterSearch}
              onChange={(e) => { setClusterSearch(e.target.value); setClusterPage(0); }}
              placeholder="Konu ara..."
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />

            <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 pb-1 border-b border-slate-100">
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-indigo-500" />
                Top {topN} — görünüyor
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-400" />
                Eklendi (Top {topN} dışı)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-slate-300" />
                Gizli (tıkla: göster)
              </span>
            </div>

            {allLoading && (
              <div className="text-center py-6 text-sm text-slate-400 animate-pulse">
                Konular yükleniyor...
              </div>
            )}

            {!allLoading && pagedAll.map((cluster) => {
              const isTopN = topNSet.has(cluster.topic_tag);
              const isVisible = visibleTopics.has(cluster.topic_tag);
              const isFetching = fetchingTopics.has(cluster.topic_tag);
              const color = topicColorMap.get(cluster.topic_tag) ?? '#cbd5e1';
              const articlesOpen = openArticleClusterId === cluster.cluster_id;

              return (
                <div key={cluster.cluster_id}>
                  <div
                    onClick={() => !isFetching && toggleVisible(cluster)}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-all select-none cursor-pointer hover:bg-slate-50 active:bg-slate-100 ${
                      isVisible ? 'border-slate-300 bg-white' : 'border-slate-200 bg-white opacity-60'
                    }`}
                  >
                    <span
                      className={`w-3 h-3 rounded-full flex-shrink-0 transition-opacity ${isVisible ? '' : 'opacity-30'}`}
                      style={{ backgroundColor: color }}
                    />
                    <span className={`flex-1 text-sm font-medium truncate ${isVisible ? 'text-slate-800' : 'text-slate-400 line-through'}`}>
                      {capitalize(cluster.topic_tag)}
                    </span>
                    <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full flex-shrink-0">
                      {articlesOpen && !clusterArticlesLoading ? clusterArticlesTotal : cluster.article_count} makale
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${
                      isVisible
                        ? isTopN ? 'bg-indigo-100 text-indigo-700' : 'bg-blue-100 text-blue-700'
                        : 'bg-slate-100 text-slate-500'
                    }`}>
                      {isFetching ? 'Yükleniyor...' : isVisible ? (isTopN ? 'Top ' + topN : 'Eklendi') : 'Gizli'}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); openArticlePanel(cluster); }}
                      className={`flex-shrink-0 px-2 py-0.5 text-xs rounded-lg border transition-colors ${
                        articlesOpen
                          ? 'bg-indigo-600 text-white border-indigo-600'
                          : 'bg-white text-indigo-600 border-indigo-200 hover:bg-indigo-50'
                      }`}
                    >
                      Makaleler {articlesOpen ? '▲' : '▼'}
                    </button>
                  </div>

                  {articlesOpen && (
                    <div className="ml-6 mt-1 mb-2 border border-indigo-100 rounded-lg bg-indigo-50/40 overflow-hidden">
                      <div className="px-4 pt-3 pb-2 bg-indigo-50 border-b border-indigo-100">
                        <input
                          type="text"
                          value={articleSearch}
                          onChange={(e) => { setArticleSearch(e.target.value); setArticlePage(0); }}
                          placeholder="Makale başlığında ara..."
                          className="w-full px-3 py-1.5 text-xs border border-indigo-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                        />
                      </div>

                      {clusterArticlesLoading ? (
                        <p className="text-xs text-slate-400 animate-pulse px-4 py-3">Makaleler yükleniyor...</p>
                      ) : clusterArticles.length === 0 ? (
                        <p className="text-xs text-slate-400 px-4 py-3">Makale bulunamadı.</p>
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
                                  Görüntüle →
                                </Link>
                              </li>
                            ))}
                          </ul>

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
                                ← Önceki
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
              <p className="text-sm text-slate-400 text-center py-4">Sonuç bulunamadı.</p>
            )}

            {!allLoading && totalClusterPages > 1 && (
              <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                <button
                  onClick={() => setClusterPage((p) => Math.max(0, p - 1))}
                  disabled={clusterPage === 0}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Önceki
                </button>
                <span className="text-xs text-slate-500">
                  {clusterPage + 1} / {totalClusterPages}
                  <span className="ml-1 text-slate-400">({filteredAll.length} konu)</span>
                </span>
                <button
                  onClick={() => setClusterPage((p) => Math.min(totalClusterPages - 1, p + 1))}
                  disabled={clusterPage >= totalClusterPages - 1}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Sonraki
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      )}
    </>
  );
}
