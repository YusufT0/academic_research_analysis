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
  listClusters,
  suggestJournals,
} from '@/lib/api';
import type { TopicTrendsData, TopicCluster, NlpStatus } from '@/lib/types';

// ─── Constants ───────────────────────────────────────────────────────────────

const PUBLISHERS = [
  { label: 'IEEE Xplore',        value: 'IEEE'     },
  { label: 'ACM Digital Library', value: 'ACM'     },
  { label: 'Science Direct',     value: 'Elsevier' },
  { label: 'Wiley Online Library', value: 'Wiley'   },
  { label: 'Springer Link',      value: 'Springer' },
];

type Mode = 'all' | 'journal' | 'publisher';

// ─── Component ───────────────────────────────────────────────────────────────

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
      if (mode === 'all')           result = await getAllTopicTrends(mv, n);
      else if (mode === 'journal')  result = await getJournalTopicTrends(name ?? '', mv, n);
      else                          result = await getPublisherTopicTrends(name ?? '', mv, n);
      setData(!result ? { graph_data: [], clusters: [] } : result);
    } catch {
      setError('Veri yüklenirken hata oluştu.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function fetchAllClusters(name: string | undefined, mv: string) {
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
    mode === 'all' ? 'all' : mode === 'journal' ? 'journal' : 'publisher';

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
                  className="h-8 min-w-[210px] rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
              className={`cursor-pointer px-4 py-2 rounded-lg text-sm font-medium transition-colors ${topTab === 'url' ? 'bg-violet-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
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
            <div className="flex gap-2">
              {(['all', 'journal', 'publisher'] as Mode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => handleModeChange(m)}
                  className={`cursor-pointer px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    mode === m ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {m === 'all' ? 'Tümü' : m === 'journal' ? 'Dergi Bazlı' : 'Yayıncı Bazlı'}
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
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                          className="px-3 py-2 cursor-pointer hover:bg-emerald-50 hover:text-emerald-700 truncate border-b border-slate-100 last:border-0"
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
                    onClick={() => { setNameInput(pub.value); setSubmittedName(pub.value); fetchBoth(pub.value); }}
                    className={`cursor-pointer px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                      submittedName === pub.value ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
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
                groupId={mode !== 'all' ? submittedName : undefined}
                visible={topTab === 'trend' && !collapsed}
              />
            )}

            {/* Empty state */}
            {!loading && !error && data && data.graph_data.length === 0 && (
              <div className="text-center py-10 text-slate-500 text-sm">
                {mode !== 'all'
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
