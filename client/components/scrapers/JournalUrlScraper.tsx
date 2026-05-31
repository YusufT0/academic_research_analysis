'use client';

/**
 * JournalUrlScraper
 *
 * URL girerek tekil journal scraping yapılmasını sağlayan component.
 * - Frontend regex validasyonu (anlık)
 * - Backend validasyon + DB kontrol
 * - DB'de mevcutsa journal bilgisi + onay dialodu
 * - Onay sonrası mevcut JournalQueue + WebSocket takip altyapısını kullanır
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import Link from 'next/link';
import {
  Link2,
  Search,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Play,
  Square,
  Pause,
  BookOpen,
  ChevronRight,
  ChevronDown,
  Info,
  RefreshCw,
  Zap,
  FileText,
  Clock,
  BarChart3,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  validateJournalUrl,
  checkJournalExists,
  startSingleJournalScraper,
  getJournal,
  getJournals,
  getJournalIssues,
  getJournalCitationMetrics,
  type JournalExistsResponse,
  type JournalUrlValidateResponse,
} from '@/lib/api';
import type { ScraperStatus, IssueProgress, Journal, Issue, JournalCitationMetrics } from '@/lib/types';
import { JournalCard } from '@/app/journals/JournalCard';

// ==================== URL Valdiation (Frontend) ====================

const URL_PATTERNS: Record<string, { label: string; regex: RegExp; variant: 'default' | 'info' | 'success' | 'warning' }> = {
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
  wiley: {
    label: 'Wiley Online Library',
    variant: 'default',
    regex: /https?:\/\/(?:[\w\-]+\.)?onlinelibrary\.wiley\.com\/(journal|toc)\/[a-zA-Z0-9\-]+/i,
  },
  springer: {
    label: 'Springer Link',
    variant: 'info',
    regex: /https?:\/\/link\.springer\.com\/(journal\/\d+|brands\/springer\/journals(\/computer-science)?)/i,
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
  if (sourceWebsite === 'wiley') return `https://onlinelibrary.wiley.com${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'springer') return `https://link.springer.com${url.startsWith('/') ? '' : '/'}${url}`;
  return url;
}

// ==================== Existing Journal Banner ====================

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
    wiley: 'Wiley Online Library',
    springer: 'Springer Link',
  };
  const sourceVariants: Record<string, 'info' | 'success' | 'warning' | 'default'> = {
    ieeexplore: 'info',
    sciencedirect: 'success',
    acm: 'warning',
    wiley: 'default',
    springer: 'info',
  };

  const lastUpdated = info.updated_at
    ? new Date(info.updated_at).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })
    : 'Bilinmiyor';

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 overflow-hidden animate-in slide-in-from-top-2 duration-300">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-amber-100 border-b border-amber-200">
        <div className="p-1.5 bg-amber-200 rounded-lg">
          <Info className="h-4 w-4 text-amber-700" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-amber-800">Bu dergi veritabanında mevcut</p>
          <p className="text-xs text-amber-600">Yeniden scrape etmek ister misiniz?</p>
        </div>
        <Badge variant={sourceVariants[info.source_website] ?? 'default'} className="text-xs">
          {sourceLabels[info.source_website] ?? info.source_website}
        </Badge>
      </div>

      {/* Journal Info */}
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

      {/* Actions */}
      <div className="flex items-center gap-3 px-4 py-3 bg-amber-50 border-t border-amber-200">
        <Button
          variant="primary"
          size="sm"
          onClick={onContinue}
          className="flex-1 bg-amber-600 hover:bg-amber-700"
        >
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
          Yeniden Scrape Et
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel} className="flex-1">
          Vazgeç
        </Button>
      </div>
    </div>
  );
}

// ==================== Inline Journal Queue (reuses ScraperStatus shape) ====================

// ── Helpers shared with JournalQueue ────────────────────────────────────────

type CompletedJournalDetails = {
  loading: boolean;
  journal: Journal | null;
  issues: Issue[];
  citationMetrics: JournalCitationMetrics | null;
  error?: string;
};

function CitationHistoryMiniChart({ data, loading }: { data: JournalCitationMetrics | null; loading: boolean }) {
  const chartData = useMemo(() => {
    if (!data?.historical_citation_data) return [];
    return Object.entries(data.historical_citation_data)
      .map(([year, count]) => ({ year, count }))
      .sort((a, b) => a.year.localeCompare(b.year));
  }, [data]);

  if (loading) {
    return <div className="h-28 rounded bg-slate-100 animate-pulse" />;
  }

  if (chartData.length === 0) {
    return <p className="text-xs text-slate-400 italic">Atıf geçmişi verisi bulunamadı.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={140}>
      <BarChart data={chartData} margin={{ top: 6, right: 8, left: -18, bottom: 2 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="year" tick={{ fontSize: 10 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
          formatter={(value) => [`${Number(value).toLocaleString()} atıf`, 'Atıf']}
        />
        <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
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

// ── Inline Journal Queue (tam replica) ──────────────────────────────────────

function InlineJournalQueue({ scraper }: { scraper: ScraperStatus }) {
  const [expandedJournals, setExpandedJournals] = useState<Set<string>>(new Set());
  const [expandedIssues, setExpandedIssues] = useState<Set<string>>(new Set());
  const [journalDetails, setJournalDetails] = useState<Record<string, CompletedJournalDetails>>({});

  const sourceMap: Record<string, string> = {
    ieee: 'ieeexplore',
    sciencedirect: 'sciencedirect',
    acm: 'acm',
    wiley: 'wiley',
    springer: 'springer',
  };

  const loadCompletedJournalDetails = useCallback(async (journalName: string) => {
    if (!journalName || journalDetails[journalName]?.loading || journalDetails[journalName]) return;

    setJournalDetails(prev => ({
      ...prev,
      [journalName]: { loading: true, journal: null, issues: [], citationMetrics: null },
    }));

    try {
      const sourceWebsite = sourceMap[scraper.scraper_type] || undefined;
      const list = await getJournals({
        search: journalName,
        source_website: sourceWebsite,
        page: 1,
        page_size: 20,
      });

      const match = list.items.find(j => j.name.trim().toLowerCase() === journalName.trim().toLowerCase()) ?? list.items[0] ?? null;
      if (!match) {
        setJournalDetails(prev => ({
          ...prev,
          [journalName]: {
            loading: false,
            journal: null,
            issues: [],
            citationMetrics: null,
            error: 'Dergi detayı veritabanında bulunamadı.',
          },
        }));
        return;
      }

      const [issuesData, citationMetrics] = await Promise.all([
        getJournalIssues(match.id, 1, 100),
        getJournalCitationMetrics(match.id).catch(() => null),
      ]);
      const issues = Array.isArray(issuesData)
        ? (issuesData as Issue[])
        : (((issuesData as { items?: Issue[] }).items) ?? []);

      setJournalDetails(prev => ({
        ...prev,
        [journalName]: {
          loading: false,
          journal: match,
          issues,
          citationMetrics,
        },
      }));
    } catch {
      setJournalDetails(prev => ({
        ...prev,
        [journalName]: {
          loading: false,
          journal: null,
          issues: [],
          citationMetrics: null,
          error: 'Dergi detayları yüklenemedi.',
        },
      }));
    }
  }, [journalDetails, scraper.scraper_type]);

  const toggleJournal = (name: string) => {
    setExpandedJournals(prev => {
      const s = new Set(prev);
      const willOpen = !s.has(name);
      if (willOpen) {
        s.add(name);
        void loadCompletedJournalDetails(name);
      } else {
        s.delete(name);
      }
      return s;
    });
  };

  const toggleIssue = (key: string) =>
    setExpandedIssues(prev => { const s = new Set(prev); s.has(key) ? s.delete(key) : s.add(key); return s; });

  const completed = scraper.completed_journals ?? [];
  const pending   = scraper.pending_journals ?? [];
  const isActive  = !!scraper.current_journal && ['running', 'paused', 'starting'].includes(scraper.status);
  const totalVisible = completed.length + (isActive ? 1 : 0) + pending.length;

  if (totalVisible === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden mt-4">
      {/* Header */}
      <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Dergi Kuyruğu</span>
        <span className="text-xs text-slate-400">
          {scraper.current_journal_index}/{scraper.total_journals}
        </span>
      </div>

      <div className="max-h-96 overflow-y-auto divide-y divide-slate-100">

        {/* Tamamlanan dergiler */}
        {completed.map((j, i) => {
          const isOpen = expandedJournals.has(j.name);
          const issues = j.issues ?? [];
          return (
            <div key={`done-${i}`} className="bg-white">
              <button
                onClick={() => toggleJournal(j.name)}
                className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-slate-50 transition-colors text-left"
              >
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
                <span className="flex-1 text-xs text-slate-600 truncate" title={j.name}>{j.name}</span>
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
                  {isOpen && (
                    <div className="bg-slate-50 border-t border-slate-100 px-3 py-3 space-y-3">
                      <div>
                        <h4 className="font-medium text-slate-700 mb-2 flex items-center gap-1.5 text-xs">
                          <BarChart3 className="h-3.5 w-3.5 text-indigo-600" />
                          Yıllık Atıf Grafiği
                        </h4>
                        <CitationHistoryMiniChart
                          data={journalDetails[j.name]?.citationMetrics ?? null}
                          loading={!!journalDetails[j.name]?.loading}
                        />
                      </div>

                      <div>
                        <h4 className="font-medium text-slate-700 mb-2 flex items-center gap-1.5 text-xs">
                          <BookOpen className="h-3.5 w-3.5 text-purple-600" />
                          Dergi Sayıları
                        </h4>
                        {journalDetails[j.name]?.error ? (
                          <p className="text-xs text-amber-600">{journalDetails[j.name]?.error}</p>
                        ) : !!journalDetails[j.name]?.loading ? (
                          <div className="space-y-1">
                            <div className="h-6 bg-slate-100 rounded animate-pulse" />
                            <div className="h-6 bg-slate-100 rounded animate-pulse" />
                          </div>
                        ) : (journalDetails[j.name]?.issues?.length ?? 0) > 0 ? (
                          <div className="space-y-1 max-h-36 overflow-y-auto">
                            {(journalDetails[j.name]?.issues ?? []).slice(0, 25).map((issue) => {
                              const title = issue.volume
                                ? `Cilt ${issue.volume}${issue.issue_number ? `, Sayı ${issue.issue_number}` : ''}`
                                : `Sayı ${issue.issue_number || issue.year || 'Bilinmiyor'}`;
                              return (
                                <div key={issue.id} className="text-xs text-slate-600 bg-white border border-slate-200 rounded px-2 py-1 flex items-center justify-between gap-2">
                                  <span className="truncate">{title}</span>
                                  <span className="text-[11px] text-slate-400 flex-shrink-0">{issue.article_count} makale</span>
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <p className="text-xs text-slate-400 italic">Bu dergiye ait sayı bulunamadı.</p>
                        )}
                      </div>
                    </div>
                  )}

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

        {/* Aktif dergi */}
        {isActive && scraper.current_journal && (
          <div className="bg-blue-50">
            <div className="flex items-center gap-2 px-4 py-2.5">
              <Loader2 className="h-3.5 w-3.5 text-blue-500 flex-shrink-0 animate-spin" />
              <span className="flex-1 text-xs font-semibold text-blue-800 truncate" title={scraper.current_journal}>
                {scraper.current_journal}
              </span>
              {scraper.total_issues > 0 && (
                <span className="text-xs text-blue-400 flex-shrink-0">
                  {scraper.current_issue_index}/{scraper.total_issues} sayı
                </span>
              )}
            </div>

            {/* Tamamlanan issue'lar (aktif dergide) */}
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

            {/* Aktif issue */}
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

            {/* Aktif issue'nun makale listesi */}
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
          </div>
        )}

        {/* Bekleyen dergiler */}
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

// ==================== Progress Stats Bar ====================

function ProgressBar({ percent, status }: { percent: number; status: string }) {
  const color =
    status === 'error' ? 'bg-red-500' :
    status === 'completed' ? 'bg-emerald-500' :
    'bg-gradient-to-r from-blue-500 to-indigo-400';

  return (
    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-700 ease-out ${color}`}
        style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
      />
    </div>
  );
}

// ==================== Main Component ====================

type FlowState =
  | 'idle'
  | 'validating'         // backend'e doğrulama isteği gönderildi
  | 'exists_prompt'      // DB'de var, kullanıcıdan onay bekleniyor
  | 'confirmed'          // kullanıcı onayladı / yeni dergi
  | 'scraping'           // scraper çalışıyor
  | 'done'
  | 'error';

const PLATFORM_COLORS: Record<string, string> = {
  ieee: 'from-blue-600 to-cyan-500',
  sciencedirect: 'from-emerald-600 to-teal-500',
  acm: 'from-amber-600 to-orange-500',
  wiley: 'from-slate-600 to-slate-500',
  springer: 'from-indigo-600 to-blue-600',
};

const PLATFORM_BG: Record<string, string> = {
  ieee: 'bg-blue-50 border-blue-200',
  sciencedirect: 'bg-emerald-50 border-emerald-200',
  acm: 'bg-amber-50 border-amber-200',
  wiley: 'bg-slate-50 border-slate-200',
  springer: 'bg-indigo-50 border-indigo-200',
};

export function JournalUrlScraper() {
  const [url, setUrl] = useState('');
  const [maxArticles, setMaxArticles] = useState(50);
  const [depth, setDepth] = useState(1);
  const [maxTabs, setMaxTabs] = useState(3);
  const [flowState, setFlowState] = useState<FlowState>('idle');
  const [frontendPlatform, setFrontendPlatform] = useState<string | null>(null);
  const [backendValidation, setBackendValidation] = useState<JournalUrlValidateResponse | null>(null);
  const [existsInfo, setExistsInfo] = useState<JournalExistsResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [resolvedJournal, setResolvedJournal] = useState<Journal | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Scraper status (WebSocket + polling)
  const [scraperStatus, setScraperStatus] = useState<ScraperStatus | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pingRef = useRef<NodeJS.Timeout | null>(null);

  // Frontend anlık platform tespiti
  useEffect(() => {
    setFrontendPlatform(detectPlatformFrontend(url));
  }, [url]);

  // WebSocket + polling scraper durumunu takip et
  const startTracking = useCallback((scraperType: string) => {
    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
    const wsBase = API_URL.replace('/api/v1', '').replace('http://', 'ws://').replace('https://', 'wss://');
    const wsUrl = `${wsBase}/ws/scrapers/events?scrapers=${scraperType}`;

    let destroyed = false;

    const connect = () => {
      if (destroyed) return;
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
          if (event.type === 'status_update' || event.type === 'progress') {
            if (event.data && event.scraper_type === scraperType) {
              setScraperStatus(prev => prev ? { ...prev, ...event.data } : event.data as ScraperStatus);
              const s = (event.data as Record<string, unknown>).status as string;
              if (['completed', 'stopped', 'error'].includes(s)) {
                setFlowState(s === 'error' ? 'error' : 'done');
              } else if (['running', 'starting', 'paused', 'stopping'].includes(s)) {
                // New scrape has started — reset to scraping even if UI was stuck on 'done'.
                setFlowState('scraping');
              }
            }
          }
        } catch { /* ignore */ }
      };
      ws.onclose = () => {
        if (pingRef.current) clearInterval(pingRef.current);
        if (!destroyed) setTimeout(connect, 5000);
      };
    };

    connect();

    // Polling yedek (WS bağlanamazsa)
    pollRef.current = setInterval(async () => {
      try {
        const { getSingleJournalScraperStatus } = await import('@/lib/api');
        const s = await getSingleJournalScraperStatus(scraperType) as ScraperStatus;
        setScraperStatus(s);
        if (['completed', 'stopped', 'error'].includes(s.status)) {
          setFlowState(s.status === 'error' ? 'error' : 'done');
        } else if (['running', 'starting', 'paused', 'stopping'].includes(s.status)) {
          setFlowState('scraping');
        }
      } catch { /* ignore */ }
    }, 3000);

    return () => {
      destroyed = true;
      if (pingRef.current) clearInterval(pingRef.current);
      if (wsRef.current) wsRef.current.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Temizlik
  useEffect(() => {
    return () => {
      if (pingRef.current) clearInterval(pingRef.current);
      if (wsRef.current) wsRef.current.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const resetFlow = useCallback(() => {
    setFlowState('idle');
    setBackendValidation(null);
    setExistsInfo(null);
    setErrorMsg(null);
    setScraperStatus(null);
    setResolvedJournal(null);
    setDetailError(null);
    setDetailLoading(false);
    if (pingRef.current) clearInterval(pingRef.current);
    if (wsRef.current) wsRef.current.close();
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  useEffect(() => {
    if (flowState !== 'done') return;
    let cancelled = false;

    const resolveJournalDetail = async () => {
      setDetailLoading(true);
      setDetailError(null);

      try {
        const existsResult = await checkJournalExists(url.trim());
        if (!existsResult.exists || !existsResult.journal?.id) {
          if (!cancelled) {
            setResolvedJournal(null);
            setDetailError('Dergi detayı bulunamadı. Journals sayfasından arama yapabilirsiniz.');
          }
          return;
        }

        const fullJournal = await getJournal(existsResult.journal.id);
        if (!cancelled) {
          setResolvedJournal(fullJournal);
        }
      } catch {
        if (!cancelled) {
          setResolvedJournal(null);
          setDetailError('Dergi detayları yüklenirken bir hata oluştu.');
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    };

    resolveJournalDetail();

    return () => {
      cancelled = true;
    };
  }, [flowState, url]);

  // Ana "Kontrol Et" akışı
  const handleCheck = useCallback(async () => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl) return;

    setFlowState('validating');
    setErrorMsg(null);
    setBackendValidation(null);
    setExistsInfo(null);

    try {
      // 1. Backend URL validasyonu
      const validation = await validateJournalUrl(trimmedUrl);
      setBackendValidation(validation);

      if (!validation.valid) {
        setErrorMsg(validation.message);
        setFlowState('error');
        return;
      }

      // 2. DB kontrol
      const existsResult = await checkJournalExists(trimmedUrl);
      setExistsInfo(existsResult);

      if (existsResult.exists) {
        setFlowState('exists_prompt');
      } else {
        setFlowState('confirmed');
      }
    } catch (err) {
      setErrorMsg('Bağlantı hatası. Backend çalışıyor mu?');
      setFlowState('error');
    }
  }, [url]);

  // Scraping başlat
  const handleStart = useCallback(async () => {
    const scraperType = backendValidation?.scraper_type;
    if (!scraperType) return;

    setFlowState('scraping');
    setScraperStatus(null);
    setResolvedJournal(null);
    setDetailError(null);

    try {
      const force = existsInfo?.exists ?? false;
      await startSingleJournalScraper(url.trim(), scraperType, maxArticles, depth, false, maxTabs, force);
      startTracking(scraperType);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scraper başlatılamadı';
      setErrorMsg(msg);
      setFlowState('error');
    }
  }, [url, backendValidation, maxArticles, depth, maxTabs, startTracking]);

  const platform = frontendPlatform ?? backendValidation?.scraper_type;
  const platformCfg = platform ? URL_PATTERNS[platform] : null;
  const isLoading = flowState === 'validating';
  const canCheck = url.trim().length > 0 && !['validating', 'scraping'].includes(flowState);

  const statusConfig: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
    idle: { label: 'Bekliyor', variant: 'default' },
    starting: { label: 'Başlatılıyor', variant: 'info' },
    running: { label: 'Çalışıyor', variant: 'success' },
    paused: { label: 'Duraklatıldı', variant: 'warning' },
    stopping: { label: 'Durduruluyor', variant: 'warning' },
    stopped: { label: 'Durduruldu', variant: 'default' },
    error: { label: 'Hata', variant: 'error' },
    completed: { label: 'Tamamlandı', variant: 'success' },
  };

  return (
    <div className="space-y-4">
      {/* URL Input Section */}
      <div className="space-y-3">
        {/* Large URL Input */}
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <Link2 className={`h-5 w-5 transition-colors duration-200 ${
              platform ? (
                platform === 'ieee' ? 'text-blue-500' :
                platform === 'sciencedirect' ? 'text-emerald-500' :
                platform === 'acm' ? 'text-amber-500' :
                platform === 'wiley' ? 'text-slate-500' :
                'text-indigo-500'
              ) : 'text-slate-400'
            }`} />
          </div>
          <input
            id="journal-url-input"
            type="url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (flowState !== 'idle' && flowState !== 'scraping') resetFlow();
            }}
            onKeyDown={(e) => { if (e.key === 'Enter' && canCheck) handleCheck(); }}
            placeholder="https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=..."
            className={`w-full pl-12 pr-36 py-3.5 text-sm border-2 rounded-xl focus:outline-none transition-all duration-200 font-mono bg-white ${
              platform
                ? platform === 'ieee'
                  ? 'border-blue-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-100'
                  : platform === 'sciencedirect'
                  ? 'border-emerald-300 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100'
                  : platform === 'acm'
                  ? 'border-amber-300 focus:border-amber-500 focus:ring-4 focus:ring-amber-100'
                  : platform === 'springer'
                  ? 'border-indigo-300 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100'
                  : 'border-slate-300 focus:border-slate-500 focus:ring-4 focus:ring-slate-100'
                : 'border-slate-200 focus:border-slate-400 focus:ring-4 focus:ring-slate-100'
            }`}
          />
          {/* Platform Badge (in input) */}
          {platformCfg && (
            <div className="absolute inset-y-0 right-16 flex items-center">
              <Badge variant={platformCfg.variant} className="text-xs px-2 py-0.5 animate-in fade-in duration-200">
                {platformCfg.label}
              </Badge>
            </div>
          )}
          {/* Clear button */}
          {url && (
            <button
              onClick={() => { setUrl(''); resetFlow(); }}
              className="absolute inset-y-0 right-3 flex items-center px-2 text-slate-400 hover:text-slate-600 transition-colors"
            >
              <span className="text-lg leading-none">×</span>
            </button>
          )}
        </div>

        {/* URL Format Hints */}
        {!platform && url.length === 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
            {Object.entries(URL_PATTERNS).map(([key, cfg]) => (
              <button
                key={key}
                onClick={() => setUrl(
                  key === 'ieee' ? 'https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=' :
                  key === 'sciencedirect' ? 'https://www.sciencedirect.com/journal/' :
                  key === 'acm' ? 'https://dl.acm.org/journal/' :
                  key === 'wiley' ? 'https://onlinelibrary.wiley.com/journal/' :
                  'https://link.springer.com/journal/'
                )}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs text-left transition-all
                  hover:shadow-sm active:scale-[0.98]
                  ${key === 'ieee' ? 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100' :
                    key === 'sciencedirect' ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100' :
                    key === 'acm' ? 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100' :
                    key === 'wiley' ? 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100' :
                    'border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100'}`}
              >
                <Zap className="h-3 w-3 flex-shrink-0" />
                <span>{cfg.label}</span>
                <ChevronRight className="h-3 w-3 ml-auto flex-shrink-0 opacity-50" />
              </button>
            ))}
          </div>
        )}

        {/* Parameters Row */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5">
            <label htmlFor="jus-max-articles" className="text-xs text-slate-600 whitespace-nowrap">
              Makale limiti:
            </label>
            <input
              id="jus-max-articles"
              type="number"
              min={1}
              max={5000}
              value={maxArticles}
              onChange={(e) => setMaxArticles(parseInt(e.target.value) || 50)}
              disabled={flowState === 'scraping'}
              className="w-14 px-1.5 py-1 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <label htmlFor="jus-depth" className="text-xs text-slate-600 whitespace-nowrap">
              Issue derinliği:
            </label>
            <input
              id="jus-depth"
              type="number"
              min={1}
              max={50}
              value={depth}
              onChange={(e) => setDepth(parseInt(e.target.value) || 1)}
              disabled={flowState === 'scraping'}
              className="w-12 px-1.5 py-1 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
              title="Kaç issue işlenecek (1 = sadece en yeni)"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <label htmlFor="jus-max-tabs" className="text-xs text-slate-600 whitespace-nowrap">
              Max Tab:
            </label>
            <input
              id="jus-max-tabs"
              type="number"
              min={1}
              max={10}
              value={maxTabs}
              onChange={(e) => setMaxTabs(parseInt(e.target.value) || 3)}
              disabled={flowState === 'scraping'}
              className="w-12 px-1.5 py-1 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
              title="Makale listesi çıkarıldıktan sonra aynı anda çalışacak tab sayısı"
            />
          </div>

          <div className="flex gap-2 ml-auto">
            {flowState === 'idle' || flowState === 'error' ? (
              <Button
                id="journal-url-check-btn"
                variant="primary"
                size="sm"
                onClick={handleCheck}
                isLoading={isLoading}
                disabled={!canCheck}
                className="min-w-[120px]"
              >
                <Search className="h-4 w-4 mr-1.5" />
                Kontrol Et
              </Button>
            ) : flowState === 'confirmed' ? (
              <Button
                id="journal-url-start-btn"
                variant="primary"
                size="sm"
                onClick={handleStart}
                className="min-w-[120px] bg-blue-600 hover:bg-blue-700"
              >
                <Play className="h-4 w-4 mr-1.5" />
                Scrape Başlat
              </Button>
            ) : flowState === 'exists_prompt' ? (
              <Button variant="ghost" size="sm" onClick={resetFlow}>
                Vazgeç
              </Button>
            ) : flowState === 'scraping' ? (
              <Button variant="ghost" size="sm" onClick={resetFlow} className="text-slate-500">
                <RefreshCw className="h-3.5 w-3.5 mr-1" />
                Sıfırla
              </Button>
            ) : flowState === 'done' ? (
              <Button variant="ghost" size="sm" onClick={() => { setUrl(''); resetFlow(); }}>
                Yeni Scrape
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      {/* ── State-Based Content ── */}

      {/* Validating spinner */}
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
          <div>
            <p className="text-sm font-medium text-red-700">Hata</p>
            <p className="text-xs text-red-600 mt-0.5">{errorMsg}</p>
          </div>
          <button onClick={resetFlow} className="ml-auto text-red-400 hover:text-red-600 text-lg leading-none">×</button>
        </div>
      )}

      {/* Existing journal prompt */}
      {flowState === 'exists_prompt' && existsInfo?.journal && (
        <ExistingJournalBanner
          info={existsInfo.journal}
          onContinue={handleStart}
          onCancel={resetFlow}
        />
      )}

      {/* Confirmed — ready to start */}
      {flowState === 'confirmed' && backendValidation?.scraper_type && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border animate-in slide-in-from-top-2 duration-300 ${PLATFORM_BG[backendValidation.scraper_type] ?? 'bg-slate-50 border-slate-200'}`}>
          <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-slate-700">Hazır</p>
            <p className="text-xs text-slate-500 mt-0.5">
              {backendValidation.message} — Parametreleri ayarlayıp "Scrape Başlat" butonuna tıklayın.
            </p>
          </div>
          <Badge variant={URL_PATTERNS[backendValidation.scraper_type]?.variant ?? 'default'} className="text-xs flex-shrink-0">
            {URL_PATTERNS[backendValidation.scraper_type]?.label}
          </Badge>
        </div>
      )}

      {/* Scraping — progress + queue */}
      {(flowState === 'scraping' || flowState === 'done') && scraperStatus && (
        <div className="space-y-3 animate-in slide-in-from-top-2 duration-300">
          {/* Status row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {flowState === 'scraping' && <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />}
              {flowState === 'done' && <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
              <span className="text-sm font-medium text-slate-700">
                {flowState === 'done' ? 'Tamamlandı' : 'Scraping devam ediyor...'}
              </span>
            </div>
            <Badge
              variant={statusConfig[scraperStatus.status]?.variant ?? 'default'}
              className="text-xs"
            >
              {statusConfig[scraperStatus.status]?.label ?? scraperStatus.status}
            </Badge>
          </div>

          {/* Progress bar */}
          <ProgressBar percent={scraperStatus.progress_percent} status={scraperStatus.status} />

          {/* Stats mini-grid */}
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: 'Dergi', value: `${scraperStatus.journals_scraped}/${scraperStatus.total_journals}` },
              { label: 'Sayı', value: scraperStatus.issues_scraped },
              { label: 'Makale', value: scraperStatus.articles_scraped },
              { label: 'Hata', value: scraperStatus.errors_count },
            ].map((stat) => (
              <div key={stat.label} className="bg-slate-50 rounded-lg p-2.5 text-center">
                <p className={`text-lg font-bold ${stat.label === 'Hata' && scraperStatus.errors_count > 0 ? 'text-red-600' : 'text-slate-800'}`}>
                  {stat.value}
                </p>
                <p className="text-xs text-slate-500">{stat.label}</p>
              </div>
            ))}
          </div>

          {/* Last error */}
          {scraperStatus.last_error && (
            <div className="flex items-start gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg">
              <AlertTriangle className="h-3.5 w-3.5 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-red-700">{scraperStatus.last_error}</p>
            </div>
          )}

          {/* Inline Journal Queue */}
          <InlineJournalQueue scraper={scraperStatus} />

          {flowState === 'done' && (
            <div className="space-y-3 pt-2">
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-indigo-800">Scrape Edilen Dergi Detayı</p>
                  <p className="text-xs text-indigo-600">OpenAlex, amaç-kapsam, sayılar ve makale listesi aşağıda görüntülenir.</p>
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

              {detailLoading && (
                <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Dergi detayları yükleniyor...
                </div>
              )}

              {!detailLoading && detailError && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                  {detailError}
                </div>
              )}

              {!detailLoading && resolvedJournal && (
                <JournalCard
                  journal={resolvedJournal}
                  getFullUrl={getFullUrl}
                  enableJournalsDeepLinks
                />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
