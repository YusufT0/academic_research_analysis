'use client';

import { useEffect, useRef, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/Card';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { UrlAnalysisTab, type UrlAnalysisResult } from './UrlAnalysisTab';
import { TopicTrendChart } from './TopicTrendChart';
import {
  getNlpStatus,
  getNlpModelVersions,
  getAllTopicTrends,
  getJournalTopicTrends,
  getPublisherTopicTrends,
  getKeywordTopicTrends,
  nlpSearch,
  listClusters,
  suggestJournals,
} from '@/lib/api';
import type { TopicTrendsData, TopicCluster, NlpStatus, NlpSearchResponse } from '@/lib/types';

// ─── Constants ───────────────────────────────────────────────────────────────

const PUBLISHERS = [
  { label: 'IEEE Xplore',        value: 'IEEE'     },
  { label: 'ACM Digital Library', value: 'ACM'     },
  { label: 'Science Direct',     value: 'Elsevier' },
  { label: 'Wiley Online Library', value: 'Wiley'   },
  { label: 'Springer Link',      value: 'Springer' },
];

type Mode = 'all' | 'journal' | 'publisher' | 'keyword';

// ─── Component ───────────────────────────────────────────────────────────────

function KeywordSkeleton({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="py-10 text-center">
        <div className="h-10 w-10 rounded-full bg-slate-100 mx-auto mb-3 animate-pulse" />
        <p className="text-slate-600 font-medium">{message}</p>
        <p className="text-sm text-slate-400 mt-1">NLP modeli sorgunuzu işliyor</p>
      </div>
    </div>
  );
}

function KeywordError({ message }: { message: string }) {
  return (
    <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm">
      {message}
    </div>
  );
}

function KeywordClusterInfo({ data }: { data: NlpSearchResponse }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm p-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            AI Cluster Bilgisi
          </p>
          <p className="text-sm text-slate-700 mt-1 truncate">
            Cluster:{' '}
            <span className="font-semibold text-slate-900">
              {data.cluster_label ?? (data.cluster_id != null ? `#${data.cluster_id}` : 'Bilinmiyor')}
            </span>
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Model: {data.model_version}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="px-3 py-2 rounded-lg bg-indigo-50 text-center">
            <p className="text-lg font-bold text-indigo-700">
              {(data.similarity_score * 100).toFixed(1)}%
            </p>
            <p className="text-[11px] text-indigo-500 mt-0.5">Benzerlik</p>
          </div>
          <div className="px-3 py-2 rounded-lg bg-slate-50 text-center">
            <p className="text-lg font-bold text-slate-800">
              {data.total_in_cluster ?? data.articles.length}
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">Kümede Makale</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function KeywordMatchedArticles({ data }: { data: NlpSearchResponse }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-slate-50 transition-colors cursor-pointer"
      >
        <div className="text-left min-w-0">
          <p className="text-sm font-semibold text-slate-900">Eşleşen Makaleler</p>
          <p className="text-xs text-slate-500 truncate">
            NLP modelinin bulduğu en benzer makaleler
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs font-semibold px-2 py-1 rounded-full bg-indigo-100 text-indigo-700">
            {data.articles.length} sonuç
          </span>
          {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
        </div>
      </button>
      {open && (
        <div className="p-4 space-y-3">
          {data.articles.map((a) => (
            <a
              key={a.id}
              href={`/articles/${a.id}`}
              className="block p-3 rounded-lg border border-slate-100 hover:border-indigo-200 hover:bg-indigo-50/30 transition-colors"
            >
              <p className="text-sm font-medium text-slate-900 line-clamp-2">
                {a.title}
              </p>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                {a.cluster_id != null && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                    Cluster #{a.cluster_id}
                  </span>
                )}
                {a.similarity_score != null && (
                  <span className="text-[11px] text-slate-400">
                    Benzerlik: {(a.similarity_score * 100).toFixed(1)}%
                  </span>
                )}
              </div>
              {a.abstract && (
                <p className="text-xs text-slate-500 mt-2 line-clamp-2">{a.abstract}</p>
              )}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export function TopicTrendsSection({ collapsible = false }: { collapsible?: boolean }) {
  // ── Collapsible ──
  const [collapsed, setCollapsed] = useState(false);

  // ── Active tab ──
  const [topTab, setTopTab] = useState<'trend' | 'url'>('trend');

  // ── Core state ──
  const [mode, setMode] = useState<Mode>('all');
  const [nameInput, setNameInput] = useState('');
  const [journalSuggestions, setJournalSuggestions] = useState<string[]>([]);
  const [showJournalSuggestions, setShowJournalSuggestions] = useState(false);
  const journalInputRef = useRef<HTMLDivElement>(null);
  const [submittedName, setSubmittedName] = useState('');

  // ── NLP model ──
  const [nlpStatus, setNlpStatus] = useState<NlpStatus | null>(null);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelVersion, setModelVersion] = useState<string | null>(null);

  // ── Chart data ──
  const [data, setData] = useState<TopicTrendsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topN, setTopN] = useState(10);
  const [allClusters, setAllClusters] = useState<TopicCluster[]>([]);
  const [allLoading, setAllLoading] = useState(false);

  // ── Keyword mode: NLP result (cluster + matched articles) ──
  const [nlpResult, setNlpResult] = useState<NlpSearchResponse | null>(null);
  const [nlpLoading, setNlpLoading] = useState(false);
  const [nlpError, setNlpError] = useState<string | null>(null);
  const [nlpTraining, setNlpTraining] = useState(false);

  // ── NLP status on mount ──
  useEffect(() => {
    Promise.all([getNlpStatus(), getNlpModelVersions()])
      .then(([status, versions]) => {
        setNlpStatus(status);
        setModelOptions(versions.model_versions ?? []);
        const latest = status.latest_model_version;
        if (latest) { setModelVersion(latest); return; }
        if (versions.model_versions?.length) setModelVersion(versions.model_versions[0]);
      })
      .catch(() => { setNlpStatus(null); setModelOptions([]); });
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
      } else if (mode === 'keyword') {
        const kw = (name ?? '').trim();
        setNlpLoading(true);
        setNlpError(null);
        setNlpResult(null);

        let needsTraining = false;
        try {
          const status = await getNlpStatus();
          needsTraining = !status.has_trained_model && !status.pkl_model_available && !status.cache_loaded;
        } catch {
          // ignore status fetch errors
        }
        setNlpTraining(needsTraining);

        const tasks: Promise<unknown>[] = [getKeywordTopicTrends(kw, mv, n)];
        const shouldRunNlp = kw.length >= 2;
        if (shouldRunNlp) tasks.push(nlpSearch(kw, 20, true));

        const settled = await Promise.allSettled(tasks);
        const trendsRes = settled[0] as PromiseSettledResult<TopicTrendsData>;
        const nlpRes = (settled[1] as PromiseSettledResult<NlpSearchResponse>) ?? null;

        if (trendsRes.status === 'fulfilled') {
          const raw = trendsRes.value;
          const dist = raw.keyword_distribution ?? {};
          const synth: TopicCluster[] = Object.entries(dist)
            .map(([topic_tag, article_count], idx) => ({
              cluster_id: -1000 - idx,
              topic_tag,
              article_count,
            }))
            .sort((a, b) => b.article_count - a.article_count);
          result = { ...raw, clusters: synth };
        } else {
          result = { graph_data: [], clusters: [] };
        }

        if (!shouldRunNlp) {
          setNlpError('NLP araması için en az 2 karakter girin (trend grafiği 1 karakterle çalışır).');
        } else if (nlpRes?.status === 'fulfilled') {
          setNlpResult(nlpRes.value);
        } else {
          const msg = (nlpRes as PromiseRejectedResult | null)?.reason?.message;
          setNlpError(msg ? `NLP sonuç alınamadı: ${msg}` : 'NLP sonuç alınamadı.');
        }

        setNlpLoading(false);
        setNlpTraining(false);
      } else {
        result = await getPublisherTopicTrends(name ?? '', mv, n);
      }
      setData(!result ? { graph_data: [], clusters: [] } : result);
    } catch {
      setError('Veri yüklenirken hata oluştu.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function fetchAllClusters(name: string | undefined, mv: string) {
    if (mode === 'keyword') {
      setAllClusters([]);
      setAllLoading(false);
      return;
    }
    setAllLoading(true);
    try {
      const ct = mode === 'all' ? 'all' : mode === 'journal' ? 'journal' : 'publisher';
      const gid = mode !== 'all' ? (name ?? '') : undefined;
      const res = await listClusters(mv, ct, gid);
      setAllClusters(res.clusters);
    } catch {
      setAllClusters([]);
    } finally {
      setAllLoading(false);
    }
  }

  function fetchBoth(name?: string, n?: number, mvOverride?: string) {
    const mv = mvOverride ?? modelVersion;
    if (!mv) return;
    fetchTopN(name, n ?? topN, mv);
    fetchAllClusters(name, mv);
  }

  function handleModelVersionChange(nextVersion: string) {
    setModelVersion(nextVersion || null);
    setData(null);
    setAllClusters([]);
    setError(null);
    if (nextVersion) {
      if (mode === 'all') fetchBoth(undefined, topN, nextVersion);
      else if (submittedName.trim()) fetchBoth(submittedName, topN, nextVersion);
    }
  }

  // ── Auto-fetch on mode=all ──
  useEffect(() => {
    if (mode === 'all' && modelVersion) fetchBoth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, modelVersion]);

  // ── Journal autocomplete debounce ──
  useEffect(() => {
    if (mode !== 'journal' || !nameInput.trim()) { setJournalSuggestions([]); return; }
    const t = setTimeout(() => {
      suggestJournals(nameInput.trim()).then((s) => {
        setJournalSuggestions(s);
        setShowJournalSuggestions(s.length > 0);
      });
    }, 300);
    return () => clearTimeout(t);
  }, [nameInput, mode]);

  // ── Handlers ──

  function handleSearch() {
    const trimmed = nameInput.trim();
    if (!trimmed) return;
    setSubmittedName(trimmed);
    setShowJournalSuggestions(false);
    fetchBoth(trimmed);
  }

  function handleModeChange(newMode: Mode) {
    setMode(newMode);
    setData(null);
    setAllClusters([]);
    setError(null);
    setNameInput('');
    setSubmittedName('');
    setJournalSuggestions([]);
    setShowJournalSuggestions(false);
    setNlpResult(null);
    setNlpError(null);
    setNlpLoading(false);
    setNlpTraining(false);
  }

  function handleTopNChange(n: number) {
    setTopN(n);
    if (!modelVersion) return;
    fetchTopN(submittedName || undefined, n, modelVersion);
  }

  function handleUrlAnalysisComplete(result: UrlAnalysisResult) {
    // Populate trend tab data (for manual navigation), no tab switch
    setMode('journal');
    setNameInput(result.journalName);
    setSubmittedName(result.journalName);
    setData(result.trendsData);
    setAllClusters(result.allClusters);
  }

  const noModel = nlpStatus !== null && !nlpStatus.has_trained_model;
  const clusterType: 'all' | 'journal' | 'publisher' =
    mode === 'publisher' ? 'publisher' : mode === 'journal' ? 'journal' : 'all';

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <CardTitle>Konu Trend Analizi</CardTitle>
            <CardDescription>NLP kümeleme modeline göre konu trendleri</CardDescription>
            {modelOptions.length > 0 && (
              <div className="mt-2 flex items-center gap-2">
                <label htmlFor="trend-model-select" className="text-xs font-medium text-slate-500">Model</label>
                <select
                  id="trend-model-select"
                  value={modelVersion ?? ''}
                  onChange={(e) => handleModelVersionChange(e.target.value)}
                  className="h-8 min-w-[210px] rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {modelOptions.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
            )}
          </div>
          {collapsible && (
            <button
              onClick={() => setCollapsed((v) => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-500 hover:bg-slate-100 transition-colors cursor-pointer flex-shrink-0"
            >
              <span>{collapsed ? 'Göster' : 'Gizle'}</span>
              {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
            </button>
          )}
        </div>
      </CardHeader>

      <div
        className={
          collapsible
            ? `transition-[max-height,opacity,margin-top] duration-300 ease-in-out motion-reduce:transition-none ${
                collapsed
                  ? 'overflow-hidden pointer-events-none max-h-0 opacity-0 mt-0'
                  : 'overflow-visible max-h-[10000px] opacity-100'
              }`
            : 'contents'
        }
      >
      <CardContent className={`space-y-6 ${collapsible ? 'transition-opacity duration-300 ease-out' : ''}`}>

        {/* Top-level tab buttons */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex gap-2">
            <button
              onClick={() => setTopTab('trend')}
              className={`cursor-pointer px-4 py-2 rounded-lg text-sm font-medium transition-colors ${topTab === 'trend' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            >
              Trend Analizi
            </button>
            <button
              onClick={() => setTopTab('url')}
              className={`cursor-pointer px-4 py-2 rounded-lg text-sm font-medium transition-colors ${topTab === 'url' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            >
              URL Analizi
            </button>
          </div>
        </div>

        {/* URL Analysis Tab — always mounted to preserve flowState across tab switches */}
        <div className={topTab !== 'url' ? 'hidden' : ''}>
          <UrlAnalysisTab
            modelVersion={modelVersion}
            topN={topN}
            onAnalysisComplete={handleUrlAnalysisComplete}
          />
        </div>

        {/* Trend Analysis Tab */}
        {topTab === 'trend' && (
          <>
            {/* Mode selector */}
            <div className="flex gap-2 flex-wrap">
              {(['all', 'journal', 'publisher', 'keyword'] as Mode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => handleModeChange(m)}
                  className={`cursor-pointer px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    mode === m
                      ? m === 'keyword'
                        ? 'bg-indigo-600 text-white'
                        : 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {m === 'all' ? 'Tümü' : m === 'journal' ? 'Dergi Bazlı' : m === 'publisher' ? 'Yayıncı Bazlı' : 'Kelime Bazlı'}
                </button>
              ))}
            </div>

            {/* Journal input */}
            {mode === 'journal' && (
              <div className="flex gap-2">
                <div ref={journalInputRef} className="relative flex-1">
                  <input
                    type="text"
                    value={nameInput}
                    onChange={(e) => {
                      setNameInput(e.target.value);
                      if (!e.target.value.trim()) { setJournalSuggestions([]); setShowJournalSuggestions(false); }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { setShowJournalSuggestions(false); handleSearch(); }
                      if (e.key === 'Escape') setShowJournalSuggestions(false);
                    }}
                    onFocus={() => journalSuggestions.length > 0 && setShowJournalSuggestions(true)}
                    onBlur={() => setTimeout(() => setShowJournalSuggestions(false), 150)}
                    placeholder="Dergi adı girin..."
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  {showJournalSuggestions && journalSuggestions.length > 0 && (
                    <ul className="absolute z-50 left-0 right-0 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-60 overflow-y-auto text-sm">
                      {journalSuggestions.map((name) => (
                        <li
                          key={name}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            setNameInput(name);
                            setShowJournalSuggestions(false);
                            setSubmittedName(name);
                            fetchBoth(name);
                          }}
                          className="px-3 py-2 cursor-pointer hover:bg-indigo-50 hover:text-indigo-700 truncate border-b border-slate-100 last:border-0"
                        >
                          {name}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <button
                  onClick={handleSearch}
                  disabled={!nameInput.trim() || loading || !modelVersion}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                    onClick={() => { setNameInput(pub.value); setSubmittedName(pub.value); fetchBoth(pub.value); }}
                    className={`cursor-pointer px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                      submittedName === pub.value ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {pub.label}
                  </button>
                ))}
              </div>
            )}

            {/* Keyword input */}
            {mode === 'keyword' && (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSearch();
                  }}
                  placeholder="Anahtar kelime girin..."
                  className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <button
                  type="button"
                  onClick={handleSearch}
                  disabled={!nameInput.trim() || loading || !modelVersion}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Ara
                </button>
              </div>
            )}

            {/* No model */}
            {noModel && (
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-600 text-sm">
                Henüz eğitilmiş bir NLP modeli bulunmuyor. Model eğitildikten sonra konu trendleri burada görünecektir.
              </div>
            )}

            {/* Loading skeleton */}
            {loading && <div className="animate-pulse h-64 bg-slate-100 rounded-lg" />}

            {/* Error */}
            {!loading && error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">{error}</div>
            )}

            {/* Chart */}
            {!loading && !error && data && data.graph_data.length > 0 && (
              <TopicTrendChart
                data={data}
                allClusters={allClusters}
                allLoading={allLoading}
                topN={topN}
                onTopNChange={handleTopNChange}
                modelVersion={modelVersion}
                clusterType={clusterType}
                groupId={mode !== 'all' && mode !== 'keyword' ? submittedName : undefined}
                visible={topTab === 'trend' && !collapsed}
                keywordDistribution={data.keyword_distribution}
                hideFullClusterList={mode === 'keyword'}
              />
            )}

            {/* Keyword mode: cluster info + matched articles */}
            {mode === 'keyword' && (
              <div className="space-y-4">
                {nlpLoading && (
                  <KeywordSkeleton
                    message={nlpTraining ? 'NLP modeli eğitiliyor...' : 'AI analiz yapılıyor...'}
                  />
                )}
                {!nlpLoading && nlpError && <KeywordError message={nlpError} />}
                {!nlpLoading && nlpResult && (
                  <>
                    <KeywordClusterInfo data={nlpResult} />
                    {nlpResult.articles.length > 0 && (
                      <KeywordMatchedArticles data={nlpResult} />
                    )}
                  </>
                )}
              </div>
            )}

            {/* Empty state */}
            {!loading && !error && data && data.graph_data.length === 0 && (
              <div className="text-center py-10 text-slate-500 text-sm">
                {mode === 'keyword'
                  ? 'Bu anahtar kelime için trend verisi bulunamadı. Farklı bir kelime deneyin veya modelin güncel olduğundan emin olun.'
                  : mode !== 'all'
                    ? 'Bu yayıncı/dergi için cluster verisi bulunamadı. Modeli yeniden eğiterek publisher/journal clustering ekleyebilirsiniz.'
                    : 'Bu sorgu için grafik verisi bulunamadı.'}
              </div>
            )}
          </>
        )}

      </CardContent>
      </div>
    </Card>
  );
}
