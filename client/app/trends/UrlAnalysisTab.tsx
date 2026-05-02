'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import Link from 'next/link';
import {
  Link2,
  Search,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Play,
  Info,
  RefreshCw,
  Zap,
  FileText,
  Clock,
  ChevronRight,
  ChevronDown,
  Sparkles,
  Square,
  Database,
  Network,
  BarChart2,
} from 'lucide-react';
import { TopicTrendChart } from './TopicTrendChart';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  validateJournalUrl,
  checkJournalExists,
  startSingleJournalScraper,
  getSingleJournalScraperStatus,
  stopSingleJournalScraper,
  startJournalAnalysis,
  getAnalysisProgress,
  getActiveJournalAnalysisForJournal,
  getJournalTopicTrends,
  listClusters,
  getJournal,
  type JournalExistsResponse,
  type JournalUrlValidateResponse,
  type AnalysisStep,
  type AnalysisTaskProgress,
} from '@/lib/api';
import type { ScraperStatus, IssueProgress, TopicTrendsData, TopicCluster, Journal } from '@/lib/types';
import { JournalCard } from '@/app/journals/JournalCard';

// ─── URL patterns ────────────────────────────────────────────────────────────

const URL_PATTERNS: Record<string, { label: string; regex: RegExp; variant: 'info' | 'success' | 'warning' }> = {
  ieee: {
    label: 'IEEE Xplore',
    variant: 'info',
    regex: /https?:\/\/ieeexplore\.ieee\.org\/(xpl\/RecentIssue\.jsp\?punumber=\d+|servlet\/opac\?punumber=\d+|xpl\/aboutJournal\.jsp\?punumber=\d+)/i,
  },
  sciencedirect: {
    label: 'ScienceDirect',
    variant: 'success',
    regex: /https?:\/\/www\.sciencedirect\.com\/journal\/[a-zA-Z0-9\-]+/i,
  },
  acm: {
    label: 'ACM Digital Library',
    variant: 'warning',
    regex: /https?:\/\/dl\.acm\.org\/(journal|loi)\/[a-zA-Z0-9\-]+/i,
  },
};

function detectPlatformFrontend(url: string): string | null {
  for (const [key, cfg] of Object.entries(URL_PATTERNS)) {
    if (cfg.regex.test(url.trim())) return key;
  }
  return null;
}

function getFullUrl(url: string, sourceWebsite: string): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (sourceWebsite === 'ieeexplore') return `https://ieeexplore.ieee.org${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'sciencedirect') return `https://www.sciencedirect.com${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'acm') return `https://dl.acm.org${url.startsWith('/') ? '' : '/'}${url}`;
  return url;
}

const PLATFORM_BG: Record<string, string> = {
  ieee: 'bg-blue-50 border-blue-200',
  sciencedirect: 'bg-emerald-50 border-emerald-200',
  acm: 'bg-amber-50 border-amber-200',
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function ExistingJournalBanner({
  info,
  onContinue,
  onCancel,
}: {
  info: NonNullable<JournalExistsResponse['journal']>;
  onContinue: () => void;
  onCancel: () => void;
}) {
  const sourceLabels: Record<string, string> = {
    ieeexplore: 'IEEE Xplore',
    sciencedirect: 'ScienceDirect',
    acm: 'ACM Digital Library',
  };
  const sourceVariants: Record<string, 'info' | 'success' | 'warning'> = {
    ieeexplore: 'info',
    sciencedirect: 'success',
    acm: 'warning',
  };

  const lastUpdated = info.updated_at
    ? new Date(info.updated_at).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })
    : 'Bilinmiyor';

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 overflow-hidden animate-in slide-in-from-top-2 duration-300">
      <div className="flex items-center gap-3 px-4 py-3 bg-amber-100 border-b border-amber-200">
        <div className="p-1.5 bg-amber-200 rounded-lg">
          <Info className="h-4 w-4 text-amber-700" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-amber-800">Bu dergi veritabanında mevcut</p>
          <p className="text-xs text-amber-600">Yeniden scrape edip analiz etmek ister misiniz?</p>
        </div>
        <Badge variant={sourceVariants[info.source_website] ?? 'default'} className="text-xs">
          {sourceLabels[info.source_website] ?? info.source_website}
        </Badge>
      </div>

      <div className="px-4 py-3 grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div>
          <p className="text-xs text-amber-600 font-medium uppercase tracking-wide mb-0.5">Dergi Adı</p>
          <p className="text-sm text-slate-800 font-semibold line-clamp-2">{info.name}</p>
        </div>
        <div>
          <p className="text-xs text-amber-600 font-medium uppercase tracking-wide mb-0.5">Makaleler</p>
          <p className="text-sm text-slate-800 font-semibold">{info.article_count.toLocaleString('tr-TR')}</p>
        </div>
        <div>
          <p className="text-xs text-amber-600 font-medium uppercase tracking-wide mb-0.5">Son Güncelleme</p>
          <p className="text-sm text-slate-800 font-semibold">{lastUpdated}</p>
        </div>
        {info.issue_count > 0 && (
          <div>
            <p className="text-xs text-amber-600 font-medium uppercase tracking-wide mb-0.5">Sayı (Issue)</p>
            <p className="text-sm text-slate-800 font-semibold">{info.issue_count}</p>
          </div>
        )}
        {info.publisher && (
          <div>
            <p className="text-xs text-amber-600 font-medium uppercase tracking-wide mb-0.5">Yayıncı</p>
            <p className="text-sm text-slate-800 font-semibold">{info.publisher}</p>
          </div>
        )}
        {info.issn && (
          <div>
            <p className="text-xs text-amber-600 font-medium uppercase tracking-wide mb-0.5">ISSN</p>
            <p className="text-sm text-slate-800 font-medium font-mono">{info.issn}</p>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3 px-4 py-3 bg-amber-50 border-t border-amber-200">
        <Button
          variant="primary"
          size="sm"
          onClick={onContinue}
          className="flex-1 bg-amber-600 hover:bg-amber-700"
        >
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
          Yeniden Scrape Et ve Analiz Yap
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel} className="flex-1">
          Vazgeç
        </Button>
      </div>
    </div>
  );
}

function IssueArticleList({ articles }: { articles: string[] }) {
  if (!articles.length) return null;
  return (
    <ul className="py-1.5 space-y-0.5 px-4">
      {articles.map((title, i) => (
        <li key={i} className="flex items-start gap-1.5 text-xs text-slate-500">
          <span className="text-slate-300 flex-shrink-0 mt-0.5">›</span>
          <span className="line-clamp-2">{title}</span>
        </li>
      ))}
    </ul>
  );
}

function CompletedIssueRow({ issue, expanded, onToggle }: {
  issue: IssueProgress;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-slate-100 transition-colors text-left"
      >
        <CheckCircle2 className="h-3 w-3 text-emerald-400 flex-shrink-0" />
        <span className="flex-1 text-xs text-slate-600 truncate">{issue.title}</span>
        {issue.articles_count > 0 && (
          <span className="text-xs text-emerald-600 font-medium flex-shrink-0 flex items-center gap-0.5">
            <FileText className="h-2.5 w-2.5" />{issue.articles_count}
          </span>
        )}
        <ChevronDown className={`h-3 w-3 text-slate-400 flex-shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </button>
      <div className={`grid transition-all duration-200 ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
        <div className="overflow-hidden bg-slate-50">
          <IssueArticleList articles={issue.article_list ?? []} />
        </div>
      </div>
    </div>
  );
}

// Journal name placeholder pattern from backend (e.g. "Journal (punumber=5992)")
const JOURNAL_PLACEHOLDER_RE = /^Journal\s*\(punumber=\d+\)$/i;

function InlineJournalQueue({
  scraper,
  journalNameOverride,
}: {
  scraper: ScraperStatus;
  journalNameOverride?: string;
}) {
  const [expandedJournals, setExpandedJournals] = useState<Set<string>>(new Set());
  const [expandedIssues, setExpandedIssues] = useState<Set<string>>(new Set());

  const toggleJournal = (name: string) =>
    setExpandedJournals(prev => { const s = new Set(prev); s.has(name) ? s.delete(name) : s.add(name); return s; });
  const toggleIssue = (key: string) =>
    setExpandedIssues(prev => { const s = new Set(prev); s.has(key) ? s.delete(key) : s.add(key); return s; });

  const completed = scraper.completed_journals ?? [];
  const pending   = scraper.pending_journals ?? [];
  const isActive  = !!scraper.current_journal && ['running', 'paused', 'starting'].includes(scraper.status);
  const totalVisible = completed.length + (isActive ? 1 : 0) + pending.length;
  if (totalVisible === 0) return null;

  const resolveJournalName = (raw: string) =>
    (JOURNAL_PLACEHOLDER_RE.test(raw) && journalNameOverride) ? journalNameOverride : raw;

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden mt-4">
      <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Dergi Kuyruğu</span>
        {scraper.total_issues > 0 && (
          <span className="text-xs text-slate-400">
            {scraper.current_issue_index}/{scraper.total_issues} sayı
          </span>
        )}
      </div>
      <div className="max-h-96 overflow-y-auto divide-y divide-slate-100">
        {completed.map((j, i) => {
          const displayName = resolveJournalName(j.name);
          const isOpen = expandedJournals.has(j.name);
          const issues = j.issues ?? [];
          return (
            <div key={`done-${i}`} className="bg-white">
              <button
                onClick={() => toggleJournal(j.name)}
                className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-slate-50 transition-colors text-left"
              >
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
                <span className="flex-1 text-xs text-slate-600 truncate" title={displayName}>{displayName}</span>
                {issues.length > 0 && (
                  <span className="text-xs text-slate-400 flex-shrink-0 mr-1">{issues.length} sayı</span>
                )}
                {j.articles_count > 0 && (
                  <span className="text-xs text-emerald-600 font-medium flex-shrink-0 flex items-center gap-1">
                    <FileText className="h-3 w-3" />{j.articles_count}
                  </span>
                )}
                <ChevronDown className={`h-3.5 w-3.5 text-slate-400 flex-shrink-0 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} />
              </button>
              <div className={`grid transition-all duration-300 ease-in-out ${isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
                <div className="overflow-hidden">
                  {issues.length > 0 ? (
                    <div className="bg-slate-50 border-t border-slate-100 divide-y divide-slate-100">
                      {issues.map((issue, ii) => {
                        const issueKey = `${j.name}|${issue.title}`;
                        return (
                          <CompletedIssueRow
                            key={ii}
                            issue={issue}
                            expanded={expandedIssues.has(issueKey)}
                            onToggle={() => toggleIssue(issueKey)}
                          />
                        );
                      })}
                    </div>
                  ) : (
                    <p className="px-4 py-2 text-xs text-slate-400 bg-slate-50">Issue bilgisi kaydedilmedi</p>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {isActive && scraper.current_journal && (
          <div className="bg-blue-50">
            <div className="flex items-center gap-2 px-4 py-2.5">
              <Loader2 className="h-3.5 w-3.5 text-blue-500 flex-shrink-0 animate-spin" />
              <span className="flex-1 text-xs font-semibold text-blue-800 truncate" title={resolveJournalName(scraper.current_journal)}>
                {resolveJournalName(scraper.current_journal)}
              </span>
              {scraper.total_issues > 0 && (
                <span className="text-xs text-blue-400 flex-shrink-0">
                  {scraper.current_issue_index}/{scraper.total_issues} sayı
                </span>
              )}
            </div>
            {(scraper.completed_issues ?? []).length > 0 && (
              <div className="border-t border-blue-100 divide-y divide-blue-100">
                {(scraper.completed_issues ?? []).map((issue, ii) => {
                  const issueKey = `active|${issue.title}`;
                  return (
                    <CompletedIssueRow
                      key={ii}
                      issue={issue}
                      expanded={expandedIssues.has(issueKey)}
                      onToggle={() => toggleIssue(issueKey)}
                    />
                  );
                })}
              </div>
            )}
            {scraper.current_issue && (
              <div className="border-t border-blue-100 px-3 py-1.5 flex items-center gap-2 bg-blue-100">
                <Loader2 className="h-3 w-3 text-blue-500 flex-shrink-0 animate-spin" />
                <span className="flex-1 text-xs font-medium text-blue-700 truncate">{scraper.current_issue}</span>
                {scraper.total_articles > 0 && (
                  <span className="text-xs text-blue-500 flex-shrink-0">
                    {scraper.current_article_index}/{scraper.total_articles}
                  </span>
                )}
              </div>
            )}
            {(() => {
              const artList = scraper.article_list ?? [];
              const curIdx = scraper.current_article_index;
              if (artList.length === 0 && scraper.total_articles === 0) return null;
              const displayList = artList.length > 0
                ? artList
                : Array.from({ length: scraper.total_articles }, (_, i) => `Makale ${i + 1}`);
              return (
                <ul className="pb-2 space-y-0.5 max-h-40 overflow-y-auto">
                  {displayList.map((title, i) => {
                    const oneBasedIdx = i + 1;
                    const isDone    = oneBasedIdx < curIdx;
                    const isLoading = oneBasedIdx === curIdx;
                    const displayTitle = isLoading && scraper.current_article
                      ? scraper.current_article
                      : (title || `Makale ${oneBasedIdx}`);
                    return (
                      <li
                        key={i}
                        className={`flex items-start gap-2 px-4 py-0.5 text-xs transition-colors duration-300 ${
                          isLoading ? 'bg-blue-200' : isDone ? 'opacity-60' : 'opacity-40'
                        }`}
                      >
                        {isDone ? (
                          <CheckCircle2 className="h-3 w-3 text-emerald-400 flex-shrink-0 mt-0.5" />
                        ) : isLoading ? (
                          <Loader2 className="h-3 w-3 text-blue-500 flex-shrink-0 mt-0.5 animate-spin" />
                        ) : (
                          <Clock className="h-3 w-3 text-slate-300 flex-shrink-0 mt-0.5" />
                        )}
                        <span className={`line-clamp-2 ${isLoading ? 'text-blue-700 font-medium' : isDone ? 'text-slate-500' : 'text-slate-400'}`}>
                          {displayTitle}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              );
            })()}
            {(scraper.pending_issues ?? []).length > 0 && (
              <div className="border-t border-blue-100 bg-blue-50/70">
                <div className="px-3 py-1 text-[10px] font-semibold text-blue-500 uppercase tracking-wide">
                  Sıradaki Sayılar
                </div>
                <ul className="pb-1.5 space-y-0.5 max-h-24 overflow-y-auto">
                  {(scraper.pending_issues ?? []).map((issueTitle, idx) => (
                    <li key={`${issueTitle}-${idx}`} className="flex items-start gap-2 px-4 py-0.5 text-xs opacity-80">
                      <Clock className="h-3 w-3 text-blue-300 flex-shrink-0 mt-0.5" />
                      <span className="line-clamp-1 text-blue-600">{issueTitle}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {pending.map((name, i) => (
          <div key={`pending-${i}`} className="flex items-center gap-2 px-4 py-2 bg-white">
            <Clock className="h-3 w-3 text-slate-300 flex-shrink-0" />
            <span className="text-xs text-slate-400 truncate flex-1" title={name}>{name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProgressBar({ percent, status }: { percent: number; status: string }) {
  const color =
    status === 'error' ? 'bg-red-500' :
    status === 'completed' ? 'bg-emerald-500' :
    'bg-gradient-to-r from-blue-500 to-indigo-400';
  const clampedPct = Math.max(0, Math.min(100, percent));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">
          {status === 'completed' ? 'Tamamlandı' : status === 'error' ? 'Hata' : 'İlerleme'}
        </span>
        <span className="text-xs font-semibold text-slate-700">{Math.round(clampedPct)}%</span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${color}`}
          style={{ width: `${clampedPct}%` }}
        />
      </div>
    </div>
  );
}

function AnimatedStatValue({ value, className }: { value: number; className: string }) {
  const [displayValue, setDisplayValue] = useState(value);

  useEffect(() => {
    if (displayValue === value) return;

    let frameId: number;
    const from = displayValue;
    const to = value;
    const durationMs = 450;
    const start = performance.now();

    const tick = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(1, elapsed / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      const next = Math.round(from + ((to - from) * eased));
      setDisplayValue(next);
      if (t < 1) frameId = requestAnimationFrame(tick);
    };

    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [value, displayValue]);

  return <p className={className}>{displayValue}</p>;
}

// ─── Parallel analysis steps visualization ───────────────────────────────────

const STEP_DEFS = [
  { key: 'cluster_update', label: 'Küme Güncelleme', Icon: BarChart2 },
  { key: 'openalex',       label: 'OpenAlex',        Icon: Network },
  { key: 'elasticsearch',  label: 'Elasticsearch',   Icon: Database },
] as const;

function AnalysisSteps({ steps }: { steps: Record<string, AnalysisStep> }) {
  return (
    <div className="flex items-start justify-center gap-2 py-2">
      {STEP_DEFS.map(({ key, label, Icon }, i) => {
        const step = steps[key] ?? { status: 'pending', message: '' };
        const isDone    = step.status === 'done';
        const isRunning = step.status === 'running';
        const isError   = step.status === 'error';

        return (
          <div key={key} className="flex items-center gap-2">
            {i > 0 && (
              <div className={`w-6 h-0.5 flex-shrink-0 mt-[-16px] transition-colors duration-500 ${
                isDone ? 'bg-emerald-400' : isRunning ? 'bg-blue-400' : 'bg-slate-200'
              }`} />
            )}
            <div className="flex flex-col items-center gap-1.5 w-28">
              <div className={`w-11 h-11 rounded-full flex items-center justify-center transition-all duration-500 shadow-sm ${
                isDone    ? 'bg-emerald-500 shadow-emerald-200' :
                isRunning ? 'bg-blue-500 shadow-blue-200 ring-4 ring-blue-100' :
                isError   ? 'bg-red-500 shadow-red-200' :
                            'bg-slate-200'
              }`}>
                {isDone ? (
                  <CheckCircle2 className="h-5 w-5 text-white" />
                ) : isRunning ? (
                  <Loader2 className="h-5 w-5 text-white animate-spin" />
                ) : isError ? (
                  <AlertTriangle className="h-5 w-5 text-white" />
                ) : (
                  <Icon className="h-5 w-5 text-slate-400" />
                )}
              </div>
              <p className={`text-xs font-semibold text-center leading-tight ${
                isDone    ? 'text-emerald-700' :
                isRunning ? 'text-blue-700' :
                isError   ? 'text-red-600' :
                            'text-slate-400'
              }`}>
                {label}
              </p>
              {step.message && (
                <p className="text-[10px] text-slate-400 text-center leading-tight line-clamp-2">{step.message}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Flow state ───────────────────────────────────────────────────────────────

type FlowState =
  | 'idle'
  | 'validating'
  | 'exists_prompt'
  | 'confirmed'
  | 'scraping'
  | 'scrape_done'
  | 'analyzing'
  | 'done'
  | 'error';

const statusConfig: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
  idle:      { label: 'Bekliyor',      variant: 'default' },
  starting:  { label: 'Başlatılıyor',  variant: 'info' },
  running:   { label: 'Çalışıyor',     variant: 'success' },
  paused:    { label: 'Duraklatıldı',  variant: 'warning' },
  stopping:  { label: 'Durduruluyor',  variant: 'warning' },
  stopped:   { label: 'Durduruldu',    variant: 'default' },
  error:     { label: 'Hata',          variant: 'error' },
  completed: { label: 'Tamamlandı',    variant: 'success' },
};

// ─── Props ────────────────────────────────────────────────────────────────────

export interface UrlAnalysisResult {
  journalName: string;
  trendsData: TopicTrendsData;
  allClusters: TopicCluster[];
  assignedCount: number;
  affectedCount: number;
}

interface Props {
  modelVersion: string | null;
  topN: number;
  onAnalysisComplete: (result: UrlAnalysisResult) => void;
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function UrlAnalysisTab({ modelVersion, topN, onAnalysisComplete }: Props) {
  const [url, setUrl] = useState('');
  const [maxArticles, setMaxArticles] = useState(50);
  const [depth, setDepth] = useState(1);
  const [flowState, setFlowState] = useState<FlowState>('idle');
  const [frontendPlatform, setFrontendPlatform] = useState<string | null>(null);
  const [backendValidation, setBackendValidation] = useState<JournalUrlValidateResponse | null>(null);
  const [existsInfo, setExistsInfo] = useState<JournalExistsResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [scraperStatus, setScraperStatus] = useState<ScraperStatus | null>(null);

  // Analysis task state
  const [analysisSteps, setAnalysisSteps] = useState<Record<string, AnalysisStep>>({
    cluster_update: { status: 'pending', message: 'Bekliyor...' },
    openalex:       { status: 'pending', message: 'Bekliyor...' },
    elasticsearch:  { status: 'pending', message: 'Bekliyor...' },
  });
  const [isStopping, setIsStopping] = useState(false);
  const [resultData, setResultData] = useState<UrlAnalysisResult | null>(null);
  const [resolvedJournal, setResolvedJournal] = useState<Journal | null>(null);
  const [journalDetailLoading, setJournalDetailLoading] = useState(false);
  const [journalDetailError, setJournalDetailError] = useState<string | null>(null);

  const pollRef          = useRef<NodeJS.Timeout | null>(null);
  const wsRef            = useRef<WebSocket | null>(null);
  const pingRef          = useRef<NodeJS.Timeout | null>(null);
  const analysisPollRef  = useRef<NodeJS.Timeout | null>(null);
  // stopTracking() gibi "bilerek kapatma" durumlarında reconnect'i engellemek için
  const shouldReconnectRef = useRef(false);
  const scrapeDoneRef    = useRef(false);
  const stopRequestedRef = useRef(false);
  const displayedProgressRef = useRef(0);
  /** Kontrol Et sonrası URL; kullanıcı metni düzenlemedikçe sarı/yeşil paneller sıfırlanmaz */
  const lastValidatedUrlRef = useRef<string | null>(null);

  useEffect(() => { setFrontendPlatform(detectPlatformFrontend(url)); }, [url]);

  useEffect(() => {
    return () => {
      if (pingRef.current)         clearInterval(pingRef.current);
      if (wsRef.current)           wsRef.current.close();
      if (pollRef.current)         clearInterval(pollRef.current);
      if (analysisPollRef.current) clearInterval(analysisPollRef.current);
    };
  }, []);

  const stopTracking = useCallback(() => {
    shouldReconnectRef.current = false;
    if (pingRef.current)  { clearInterval(pingRef.current);  pingRef.current  = null; }
    if (wsRef.current)    {
      // Intentional close → onclose içindeki reconnect'i tetiklemesin
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    if (pollRef.current)  { clearInterval(pollRef.current);   pollRef.current  = null; }
  }, []);

  const resetFlow = useCallback(() => {
    stopTracking();
    if (analysisPollRef.current) { clearInterval(analysisPollRef.current); analysisPollRef.current = null; }
    scrapeDoneRef.current = false;
    stopRequestedRef.current = false;
    displayedProgressRef.current = 0;
    setFlowState('idle');
    setBackendValidation(null);
    setExistsInfo(null);
    setErrorMsg(null);
    setScraperStatus(null);
    setIsStopping(false);
    setResultData(null);
    setResolvedJournal(null);
    setJournalDetailLoading(false);
    setJournalDetailError(null);
    setAnalysisSteps({
      cluster_update: { status: 'pending', message: 'Bekliyor...' },
      openalex:       { status: 'pending', message: 'Bekliyor...' },
      elasticsearch:  { status: 'pending', message: 'Bekliyor...' },
    });
    lastValidatedUrlRef.current = null;
  }, [stopTracking]);

  // WebSocket + polling scraper tracking
  const startTracking = useCallback((scraperType: string) => {
    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
    const wsBase  = API_URL.replace('/api/v1', '').replace('http://', 'ws://').replace('https://', 'wss://');
    const wsUrl   = `${wsBase}/ws/scrapers/events?scrapers=${scraperType}`;
    let destroyed = false;
    shouldReconnectRef.current = true;

    const connect = () => {
      if (destroyed || !shouldReconnectRef.current) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => {
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, 15000);
      };
      ws.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data);
          if ((event.type === 'status_update' || event.type === 'progress') && event.scraper_type === scraperType) {
            if (event.data) {
              setScraperStatus(prev => prev ? { ...prev, ...event.data } : event.data as ScraperStatus);
              const s = (event.data as Record<string, unknown>).status as string;
              if (s === 'completed' && !scrapeDoneRef.current) {
                scrapeDoneRef.current = true;
                setFlowState('scrape_done');
              } else if (s === 'stopped') {
                stopTracking();
                scrapeDoneRef.current = false;
                setFlowState('idle');
                setIsStopping(false);
                if (stopRequestedRef.current) {
                  setErrorMsg(null);
                  stopRequestedRef.current = false;
                }
              } else if (s === 'error') {
                setFlowState('error');
                setErrorMsg('Scraping sırasında hata oluştu.');
              }
            }
          }
        } catch { /* ignore */ }
      };
      ws.onclose = () => {
        if (pingRef.current) clearInterval(pingRef.current);
        if (!destroyed && shouldReconnectRef.current) setTimeout(connect, 5000);
      };
    };
    connect();

    pollRef.current = setInterval(async () => {
      try {
        const s = await getSingleJournalScraperStatus(scraperType) as ScraperStatus;
        setScraperStatus(s);
        if (s.status === 'completed' && !scrapeDoneRef.current) {
          scrapeDoneRef.current = true;
          setFlowState('scrape_done');
        } else if (s.status === 'stopped') {
          stopTracking();
          scrapeDoneRef.current = false;
          setFlowState('idle');
          setIsStopping(false);
          if (stopRequestedRef.current) {
            setErrorMsg(null);
            stopRequestedRef.current = false;
          }
        } else if (s.status === 'error') {
          setFlowState('error');
          setErrorMsg('Scraping sırasında hata oluştu.');
        }
      } catch { /* ignore */ }
    }, 3000);

    return () => {
      destroyed = true;
      shouldReconnectRef.current = false;
      stopTracking();
    };
  }, [stopTracking]);

  // When scraping finishes → trigger NLP analysis
  useEffect(() => {
    if (flowState !== 'scrape_done') return;
    stopTracking();
    runAnalysis();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowState]);

  async function runAnalysis(existingTaskId?: string, restoredJournalName?: string) {
    if (!modelVersion) {
      setErrorMsg('NLP modeli bulunamadı. Önce bir model eğitin.');
      setFlowState('error');
      return;
    }
    setFlowState('analyzing');
    setAnalysisSteps({
      cluster_update: { status: 'pending', message: 'Bekliyor...' },
      openalex:       { status: 'pending', message: 'Bekliyor...' },
      elasticsearch:  { status: 'pending', message: 'Bekliyor...' },
    });

    try {
      // 1. Get journal ID and name
      const existsRes = await checkJournalExists(url.trim());
      if (!existsRes.exists || !existsRes.journal) {
        setErrorMsg('Scraping tamamlandı fakat journal veritabanında bulunamadı.');
        setFlowState('error');
        return;
      }
      const journalId   = existsRes.journal.id;
      const journalName = restoredJournalName ?? existsRes.journal.name;

      setJournalDetailLoading(true);
      setJournalDetailError(null);
      try {
        const fullJournal = await getJournal(journalId);
        setResolvedJournal(fullJournal);
      } catch {
        setResolvedJournal(null);
        setJournalDetailError('Dergi detayları yüklenemedi. Journals sayfasından görüntüleyebilirsiniz.');
      } finally {
        setJournalDetailLoading(false);
      }

      // 2. Start parallel analysis task
      const taskId = existingTaskId ?? (await startJournalAnalysis(journalId, modelVersion)).task_id;

      // 3. Poll until done
      const finalTask = await new Promise<AnalysisTaskProgress>((resolve, reject) => {
        analysisPollRef.current = setInterval(async () => {
          try {
            const progress = await getAnalysisProgress(taskId);
            setAnalysisSteps(progress.steps as Record<string, AnalysisStep>);
            if (progress.status === 'done' || progress.status === 'done_with_errors') {
              clearInterval(analysisPollRef.current!);
              analysisPollRef.current = null;
              resolve(progress);
            } else if (progress.status === 'error') {
              clearInterval(analysisPollRef.current!);
              analysisPollRef.current = null;
              reject(new Error(progress.error ?? 'Analiz başarısız'));
            }
          } catch (err) {
            clearInterval(analysisPollRef.current!);
            analysisPollRef.current = null;
            reject(err);
          }
        }, 500);
      });

      // 4. Load journal-specific chart (retry briefly to avoid eventual-consistency empty response)
      const fetchTrendsWithRetry = async (name: string, retries = 6, delayMs = 700) => {
        let last = await getJournalTopicTrends(name, modelVersion, topN);
        for (let i = 0; i < retries; i++) {
          if ((last.graph_data?.length ?? 0) > 0) return last;
          await new Promise((r) => setTimeout(r, delayMs));
          last = await getJournalTopicTrends(name, modelVersion, topN);
        }
        return last;
      };

      const [trendsRes, clustersRes] = await Promise.all([
        fetchTrendsWithRetry(journalName),
        listClusters(modelVersion, 'journal', journalName),
      ]);

      const result: UrlAnalysisResult = {
        journalName,
        trendsData: trendsRes,
        allClusters: clustersRes.clusters,
        assignedCount: finalTask.result?.assigned ?? 0,
        affectedCount: finalTask.result?.affected_clusters?.length ?? 0,
      };
      setResultData(result);
      setFlowState('done');
      onAnalysisComplete(result);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'NLP analizi sırasında hata oluştu.');
      setFlowState('error');
    }
  }

  const handleCheck = useCallback(async () => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) return;
    setFlowState('validating');
    setErrorMsg(null);
    setBackendValidation(null);
    setExistsInfo(null);
    lastValidatedUrlRef.current = null;
    try {
      const validation = await validateJournalUrl(trimmedUrl);
      setBackendValidation(validation);
      if (!validation.valid) {
        setErrorMsg(validation.message ?? 'Geçersiz URL.');
        setFlowState('error');
        return;
      }
      const existsResult = await checkJournalExists(trimmedUrl);
      setExistsInfo(existsResult);
      lastValidatedUrlRef.current = trimmedUrl;
      setFlowState(existsResult.exists ? 'exists_prompt' : 'confirmed');
    } catch {
      setErrorMsg('Bağlantı hatası. Backend çalışıyor mu?');
      setFlowState('error');
    }
  }, [url]);

  const handleStart = useCallback(async () => {
    const scraperType = backendValidation?.scraper_type;
    if (!scraperType) return;
    scrapeDoneRef.current = false;
    stopRequestedRef.current = false;
    setFlowState('scraping');
    setScraperStatus(null);
    setIsStopping(false);
    try {
      await startSingleJournalScraper(url.trim(), scraperType, maxArticles, depth, false);
      startTracking(scraperType);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Scraper başlatılamadı.');
      setFlowState('error');
    }
  }, [url, backendValidation, maxArticles, depth, startTracking]);

  const handleStop = useCallback(async () => {
    const scraperType = backendValidation?.scraper_type;
    if (!scraperType || isStopping) return;
    setIsStopping(true);
    stopRequestedRef.current = true;
    try {
      await stopSingleJournalScraper(scraperType);
    } catch {
      /* ignore — status polling will reflect stopped state */
    }
  }, [backendValidation, isStopping]);

  // Sayfa yenilenince aktif tekil scrape/analiz akışını backend'den geri yükle.
  useEffect(() => {
    let cancelled = false;

    const resume = async () => {
      try {
        const scraperTypes = ['ieee', 'sciencedirect', 'acm'] as const;
        const statuses = await Promise.all(
          scraperTypes.map(async (scraperType) => ({
            scraperType,
            status: await getSingleJournalScraperStatus(scraperType) as ScraperStatus,
          })),
        );
        if (cancelled) return;

        const activeRunning = statuses.find(({ status }) =>
          status.is_single_journal_mode
          && ['starting', 'running', 'paused'].includes(status.status)
          && !!status.single_journal_url,
        );
        const activeCompleted = statuses.find(({ status }) =>
          status.is_single_journal_mode
          && status.status === 'completed'
          && !!status.single_journal_url,
        );

        const active = activeRunning ?? activeCompleted;
        if (!active) return;

        const resumeUrl = (active.status.single_journal_url ?? '').trim();
        if (!resumeUrl) return;

        const { scraperType, status } = active;
        setUrl(resumeUrl);
        if (typeof status.single_journal_max_articles === 'number' && status.single_journal_max_articles > 0) {
          setMaxArticles(status.single_journal_max_articles);
        }
        if (typeof status.single_journal_depth === 'number' && status.single_journal_depth > 0) {
          setDepth(status.single_journal_depth);
        }
        setBackendValidation({ valid: true, scraper_type: scraperType, message: 'Aktif işlem backend durumundan geri yüklendi.' });
        lastValidatedUrlRef.current = resumeUrl;

        setScraperStatus(status);

        if (['starting', 'running', 'paused'].includes(status.status)) {
          setFlowState('scraping');
          startTracking(scraperType);
          return;
        }

        if (status.status === 'completed') {
          scrapeDoneRef.current = true;
          const existsRes = await checkJournalExists(resumeUrl);
          if (cancelled) return;

          if (existsRes.exists && existsRes.journal) {
            const activeAnalysis = await getActiveJournalAnalysisForJournal(existsRes.journal.id, modelVersion);
            if (cancelled) return;

            if (activeAnalysis.found && activeAnalysis.task_id) {
              setFlowState('analyzing');
              runAnalysis(activeAnalysis.task_id, existsRes.journal.name);
              return;
            }
          }

          setFlowState('scrape_done');
          return;
        }

        if (status.status === 'error') {
          setFlowState('error');
          setErrorMsg('Scraping sırasında hata oluştu.');
          return;
        }

        setFlowState('idle');
      } catch {
        if (cancelled) return;
        setFlowState('idle');
      }
    };

    resume();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelVersion, startTracking]);

  // Unified progress: scraping(issue + article) + analysis(openalex/elasticsearch/cluster)
  const scrapeProgressRatio = (() => {
    if (!scraperStatus) return 0;
    if (scraperStatus.status === 'completed') return 1;

    if (scraperStatus.total_issues <= 0) return 0;

    // Current issue index is 1-based while running.
    const completedIssues = Math.max(0, scraperStatus.current_issue_index - 1);
    const currentIssueArticleRatio = scraperStatus.total_articles > 0
      ? Math.max(0, Math.min(1, (scraperStatus.current_article_index - 1) / scraperStatus.total_articles))
      : 0;

    const issueEquivalentProgress = completedIssues + currentIssueArticleRatio;
    return Math.max(0, Math.min(1, issueEquivalentProgress / scraperStatus.total_issues));
  })();

  const analysisProgressRatio = (() => {
    const steps = Object.values(analysisSteps);
    if (!steps.length) return 0;
    const score = steps.reduce((acc, step) => {
      if (step.status === 'done') return acc + 1;
      if (step.status === 'running') return acc + 0.5;
      return acc;
    }, 0);
    return Math.max(0, Math.min(1, score / steps.length));
  })();

  const SCRAPE_WEIGHT = 0.7;
  const ANALYSIS_WEIGHT = 0.3;
  const overallProgressPct = (() => {
    if (flowState === 'done') return 100;

    // Analyzing aşamasına geçildiğinde scraping tamamlanmış kabul edilir;
    // bu sayede yüzde barı 35%'e düşmez.
    const effectiveScrapeRatio = ['analyzing', 'done'].includes(flowState)
      ? 1
      : scrapeProgressRatio;

    const ratio = (effectiveScrapeRatio * SCRAPE_WEIGHT) + (analysisProgressRatio * ANALYSIS_WEIGHT);
    const next = Math.round(Math.max(0, Math.min(1, ratio)) * 100);

    // Görsel stabilite: yüzde geri düşmez, sadece ileri gider.
    displayedProgressRef.current = Math.max(displayedProgressRef.current, next);
    return displayedProgressRef.current;
  })();

  const liveIssuesScraped = (() => {
    if (!scraperStatus) return 0;
    const completedIssues = scraperStatus.completed_issues?.length ?? 0;
    const fromIndex = scraperStatus.total_issues > 0
      ? Math.max(0, scraperStatus.current_issue_index - 1)
      : 0;
    return Math.max(scraperStatus.issues_scraped, completedIssues, fromIndex);
  })();

  const liveArticlesScraped = (() => {
    if (!scraperStatus) return 0;
    const completedFromIssues = (scraperStatus.completed_issues ?? []).reduce(
      (sum, issue) => sum + (issue.articles_count ?? 0),
      0,
    );
    const currentIssueProgress = scraperStatus.total_articles > 0
      ? Math.max(0, Math.min(scraperStatus.current_article_index - 1, scraperStatus.total_articles))
      : 0;
    return Math.max(scraperStatus.articles_scraped, completedFromIssues + currentIssueProgress);
  })();

  const platform    = frontendPlatform ?? backendValidation?.scraper_type;
  const platformCfg = platform ? URL_PATTERNS[platform] : null;
  const isLoading   = flowState === 'validating';
  const canCheck    = url.trim().length > 0 && !['validating', 'scraping', 'scrape_done', 'analyzing'].includes(flowState);
  const isBusy      = ['scraping', 'scrape_done', 'analyzing'].includes(flowState);

  return (
    <div className="space-y-4">
      {/* ── URL Input ── */}
      <div className="space-y-3">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <Link2 className={`h-5 w-5 transition-colors duration-200 ${
              platform === 'ieee'          ? 'text-blue-500'    :
              platform === 'sciencedirect' ? 'text-emerald-500' :
              platform === 'acm'           ? 'text-amber-500'   : 'text-slate-400'
            }`} />
          </div>
          <input
            type="url"
            value={url}
            onChange={(e) => {
              const next = e.target.value;
              setUrl(next);
              const trimmed = next.trim();
              // Aktif scrape / analiz sırasında URL düzenlemesini görmezden gel
              if (['scraping', 'scrape_done', 'analyzing', 'done', 'validating'].includes(flowState)) return;
              // Kontrol Et sonrası: yalnızca URL gerçekten değiştiğinde sıfırla (aksi halde satır içi yazım panelleri titrer)
              if (flowState === 'exists_prompt' || flowState === 'confirmed') {
                if (lastValidatedUrlRef.current !== null && trimmed !== lastValidatedUrlRef.current) {
                  resetFlow();
                }
                return;
              }
              if (['idle'].includes(flowState)) return;
              resetFlow();
            }}
            onKeyDown={(e) => { if (e.key === 'Enter' && canCheck) handleCheck(); }}
            disabled={isBusy}
            placeholder="https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=..."
            className={`w-full pl-12 pr-36 py-3.5 text-sm border-2 rounded-xl focus:outline-none transition-all duration-200 font-mono bg-white disabled:opacity-60 disabled:cursor-not-allowed ${
              platform === 'ieee'
                ? 'border-blue-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-100'
                : platform === 'sciencedirect'
                ? 'border-emerald-300 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100'
                : platform === 'acm'
                ? 'border-amber-300 focus:border-amber-500 focus:ring-4 focus:ring-amber-100'
                : 'border-slate-200 focus:border-slate-400 focus:ring-4 focus:ring-slate-100'
            }`}
          />
          {platformCfg && (
            <div className="absolute inset-y-0 right-16 flex items-center">
              <Badge variant={platformCfg.variant} className="text-xs px-2 py-0.5 animate-in fade-in duration-200">
                {platformCfg.label}
              </Badge>
            </div>
          )}
          {url && !isBusy && (
            <button
              onClick={() => { setUrl(''); resetFlow(); }}
              className="absolute inset-y-0 right-3 flex items-center px-2 text-slate-400 hover:text-slate-600 transition-colors"
            >
              <span className="text-lg leading-none">×</span>
            </button>
          )}
        </div>

        {/* Quick-start platform hints */}
        {!platform && url.length === 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {Object.entries(URL_PATTERNS).map(([key, cfg]) => (
              <button
                key={key}
                onClick={() => setUrl(
                  key === 'ieee'          ? 'https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=' :
                  key === 'sciencedirect' ? 'https://www.sciencedirect.com/journal/' :
                                           'https://dl.acm.org/journal/'
                )}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs text-left transition-all hover:shadow-sm active:scale-[0.98] ${
                  key === 'ieee'          ? 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100' :
                  key === 'sciencedirect' ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100' :
                                           'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'
                }`}
              >
                <Zap className="h-3 w-3 flex-shrink-0" />
                <span>{cfg.label}</span>
                <ChevronRight className="h-3 w-3 ml-auto flex-shrink-0 opacity-50" />
              </button>
            ))}
          </div>
        )}

        {/* Parameters + action buttons */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-600 whitespace-nowrap">Makale limiti:</label>
            <input
              type="number" min={1} max={5000} value={maxArticles}
              onChange={(e) => setMaxArticles(parseInt(e.target.value) || 50)}
              disabled={isBusy}
              className="w-20 px-2 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-600 whitespace-nowrap">Issue derinliği:</label>
            <input
              type="number" min={1} max={50} value={depth}
              onChange={(e) => setDepth(parseInt(e.target.value) || 1)}
              disabled={isBusy}
              title="Kaç issue işlenecek (1 = sadece en yeni)"
              className="w-16 px-2 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
            />
          </div>

          <div className="flex gap-2 ml-auto">
            {(flowState === 'idle' || flowState === 'error') && (
              <Button variant="primary" size="sm" onClick={handleCheck} isLoading={isLoading} disabled={!canCheck} className="min-w-[120px]">
                <Search className="h-4 w-4 mr-1.5" />
                Kontrol Et
              </Button>
            )}
            {flowState === 'confirmed' && (
              <Button variant="primary" size="sm" onClick={handleStart} className="min-w-[140px] bg-blue-600 hover:bg-blue-700">
                <Play className="h-4 w-4 mr-1.5" />
                Tara ve Analiz Et
              </Button>
            )}
            {flowState === 'exists_prompt' && (
              <Button variant="ghost" size="sm" onClick={resetFlow}>Vazgeç</Button>
            )}
            {flowState === 'scraping' && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleStop}
                disabled={isStopping}
                className="text-red-600 hover:bg-red-50 border border-red-200 min-w-[110px]"
              >
                {isStopping ? (
                  <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                ) : (
                  <Square className="h-3.5 w-3.5 mr-1" />
                )}
                {isStopping ? 'Durduruluyor...' : 'Durdur'}
              </Button>
            )}
            {isBusy && (
              <Button variant="ghost" size="sm" onClick={resetFlow} className="text-slate-500">
                <RefreshCw className="h-3.5 w-3.5 mr-1" />Sıfırla
              </Button>
            )}
            {flowState === 'done' && (
              <Button variant="ghost" size="sm" onClick={() => { setUrl(''); resetFlow(); }}>Yeni URL</Button>
            )}
          </div>
        </div>
      </div>

      {/* ── State-Based Content ── */}

      {/* Validating */}
      {flowState === 'validating' && (
        <div className="flex items-center gap-3 px-4 py-3 bg-slate-50 rounded-xl border border-slate-200 animate-pulse">
          <Loader2 className="h-4 w-4 text-slate-400 animate-spin flex-shrink-0" />
          <span className="text-sm text-slate-500">URL doğrulanıyor ve veritabanı kontrol ediliyor...</span>
        </div>
      )}

      {/* Error */}
      {flowState === 'error' && errorMsg && (
        <div className="flex items-start gap-3 px-4 py-3 bg-red-50 border border-red-200 rounded-xl animate-in slide-in-from-top-2 duration-300">
          <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-700">Hata</p>
            <p className="text-xs text-red-600 mt-0.5">{errorMsg}</p>
          </div>
          <button onClick={resetFlow} className="ml-auto text-red-400 hover:text-red-600 text-lg leading-none">×</button>
        </div>
      )}

      {/* Existing journal prompt */}
      {flowState === 'exists_prompt' && existsInfo?.journal && (
        <ExistingJournalBanner info={existsInfo.journal} onContinue={handleStart} onCancel={resetFlow} />
      )}

      {/* Confirmed — ready to start */}
      {flowState === 'confirmed' && backendValidation?.scraper_type && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border animate-in slide-in-from-top-2 duration-300 ${PLATFORM_BG[backendValidation.scraper_type] ?? 'bg-slate-50 border-slate-200'}`}>
          <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-slate-700">Hazır</p>
            <p className="text-xs text-slate-500 mt-0.5">
              {backendValidation.message} — Parametreleri ayarlayıp &quot;Tara ve Analiz Et&quot; butonuna tıklayın.
            </p>
          </div>
          <Badge variant={URL_PATTERNS[backendValidation.scraper_type]?.variant ?? 'default'} className="text-xs flex-shrink-0">
            {URL_PATTERNS[backendValidation.scraper_type]?.label}
          </Badge>
        </div>
      )}

      {/* Scraping progress */}
      {(flowState === 'scraping' || flowState === 'scrape_done') && scraperStatus && (
        <div className="space-y-3 animate-in slide-in-from-top-2 duration-300">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
              <span className="text-sm font-medium text-slate-700">Scraping devam ediyor...</span>
            </div>
            <Badge variant={statusConfig[scraperStatus.status]?.variant ?? 'default'} className="text-xs">
              {statusConfig[scraperStatus.status]?.label ?? scraperStatus.status}
            </Badge>
          </div>
          <ProgressBar percent={overallProgressPct} status={scraperStatus.status} />
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Sayı',   value: liveIssuesScraped },
              { label: 'Makale', value: liveArticlesScraped },
              { label: 'Hata',   value: scraperStatus.errors_count },
            ].map((stat) => (
              <div key={stat.label} className="bg-slate-50 rounded-lg p-2.5 text-center">
                <AnimatedStatValue
                  value={stat.value}
                  className={`text-lg font-bold ${stat.label === 'Hata' && scraperStatus.errors_count > 0 ? 'text-red-600' : 'text-slate-800'}`}
                />
                <p className="text-xs text-slate-500">{stat.label}</p>
              </div>
            ))}
          </div>
          {scraperStatus.last_error && (
            <div className="flex items-start gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg">
              <AlertTriangle className="h-3.5 w-3.5 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-red-700">{scraperStatus.last_error}</p>
            </div>
          )}
          <InlineJournalQueue
            scraper={scraperStatus}
            journalNameOverride={existsInfo?.journal?.name}
          />
        </div>
      )}

      {/* NLP Analyzing — parallel steps */}
      {flowState === 'analyzing' && (
        <div className="space-y-3 animate-in slide-in-from-top-2 duration-300">
          {scraperStatus && (
            <div className="flex items-center gap-3 px-4 py-2.5 bg-emerald-50 border border-emerald-200 rounded-xl">
              <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
              <span className="text-sm text-emerald-700 flex-1">
                Scraping tamamlandı — {scraperStatus.articles_scraped} makale
              </span>
              <Badge variant="success" className="text-xs">Tamamlandı</Badge>
            </div>
          )}
          <ProgressBar percent={overallProgressPct} status="running" />
          <div className="rounded-xl border border-purple-200 bg-purple-50 p-4 space-y-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-purple-500 flex-shrink-0" />
              <p className="text-sm font-semibold text-purple-800">NLP Analizi Yapılıyor</p>
              <p className="text-xs text-purple-500 ml-auto">Paralel işlem çalışıyor...</p>
            </div>
            <AnalysisSteps steps={analysisSteps} />
          </div>
        </div>
      )}

      {/* Done */}
      {flowState === 'done' && scraperStatus && (
        <div className="space-y-3 animate-in slide-in-from-top-2 duration-300">
          <div className="flex items-center gap-3 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-xl">
            <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-emerald-800">Tüm işlemler tamamlandı</p>
              <p className="text-xs text-emerald-600 mt-0.5">
                Konu trend grafiği aşağıda görüntüleniyor.
              </p>
            </div>
            <Badge variant="success" className="text-xs flex-shrink-0">Tamamlandı</Badge>
          </div>
          <ProgressBar percent={100} status="completed" />
          <div className="rounded-xl border border-purple-100 bg-purple-50/50 p-3">
            <AnalysisSteps steps={analysisSteps} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Sayı',   value: liveIssuesScraped },
              { label: 'Makale', value: liveArticlesScraped },
              { label: 'Hata',   value: scraperStatus.errors_count },
            ].map((stat) => (
              <div key={stat.label} className="bg-slate-50 rounded-lg p-2.5 text-center">
                <AnimatedStatValue
                  value={stat.value}
                  className={`text-lg font-bold ${stat.label === 'Hata' && scraperStatus.errors_count > 0 ? 'text-red-600' : 'text-slate-800'}`}
                />
                <p className="text-xs text-slate-500">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {flowState === 'done' && (
        <div className="space-y-3 animate-in slide-in-from-top-2 duration-300">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-indigo-800">Scrape Edilen Dergi Detayı</p>
              <p className="text-xs text-indigo-600">Grafiğin üstünde journals sayfasındaki detaylar gösterilir.</p>
            </div>
            {resolvedJournal && (
              <Link
                href={`/journals?journal_id=${resolvedJournal.id}`}
                className="inline-flex items-center justify-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Journals Detayına Git
              </Link>
            )}
          </div>

          {journalDetailLoading && (
            <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Dergi detayları yükleniyor...
            </div>
          )}

          {!journalDetailLoading && journalDetailError && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
              {journalDetailError}
            </div>
          )}

          {!journalDetailLoading && resolvedJournal && (
            <JournalCard
              journal={resolvedJournal}
              getFullUrl={getFullUrl}
              enableJournalsDeepLinks
            />
          )}
        </div>
      )}

      {/* Trend chart — reuses the shared TopicTrendChart component */}
      {flowState === 'done' && resultData && resultData.trendsData.graph_data.length > 0 && (
        <div className="animate-in slide-in-from-top-2 duration-300">
          <TopicTrendChart
            data={resultData.trendsData}
            allClusters={resultData.allClusters}
            topN={topN}
            modelVersion={modelVersion}
            clusterType="journal"
            groupId={resultData.journalName}
            visible={true}
          />
        </div>
      )}
    </div>
  );
}
