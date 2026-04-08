'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Play,
  Pause,
  Square,
  RefreshCw,
  AlertTriangle,
  Wifi,
  WifiOff,
  Radio,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Clock,
  Loader2,
  FileText,
  Columns2,
  AlignJustify,
  Link2,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  getScrapersStatus,
  startIeeeScraper,
  stopIeeeScraper,
  pauseIeeeScraper,
  resumeIeeeScraper,
  startScienceDirectScraper,
  stopScienceDirectScraper,
  pauseScienceDirectScraper,
  resumeScienceDirectScraper,
  startAcmScraper,
  stopAcmScraper,
  pauseAcmScraper,
  resumeAcmScraper,
  getScraperLogs
} from '@/lib/api';
import { useGlobalScraperEvents } from '@/components/providers/ScraperProvider';
import type { AllScrapersStatus, ScraperStatus } from '@/lib/types';
import type { ScraperEvent, ConnectionStatus } from '@/lib/useScraperEvents';
import { OpenAlexScanner } from '@/components/dashboard/OpenAlexScanner';
import { JournalUrlScraper } from '@/components/scrapers/JournalUrlScraper';

// ==================== Status Config ====================

const statusConfig: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' | 'info'; color: string }> = {
  idle: { label: 'Bekliyor', variant: 'default', color: 'text-slate-500' },
  starting: { label: 'Başlatılıyor', variant: 'info', color: 'text-blue-500' },
  running: { label: 'Çalışıyor', variant: 'success', color: 'text-emerald-500' },
  paused: { label: 'Duraklatıldı', variant: 'warning', color: 'text-amber-500' },
  stopping: { label: 'Durduruluyor', variant: 'warning', color: 'text-amber-500' },
  stopped: { label: 'Durduruldu', variant: 'default', color: 'text-slate-500' },
  error: { label: 'Hata', variant: 'error', color: 'text-red-500' },
  completed: { label: 'Tamamlandı', variant: 'success', color: 'text-emerald-500' },
};

// ==================== Connection Status Badge ====================

function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  if (status === 'connected') {
    return (
      <Badge variant="success" className="text-xs gap-1">
        <Wifi className="h-3 w-3" />
        Canlı
      </Badge>
    );
  }
  if (status === 'reconnecting') {
    return (
      <Badge variant="warning" className="text-xs gap-1 animate-pulse">
        <Radio className="h-3 w-3" />
        Bağlanıyor...
      </Badge>
    );
  }
  return (
    <Badge variant="default" className="text-xs gap-1">
      <WifiOff className="h-3 w-3" />
      Çevrimdışı
    </Badge>
  );
}

// ==================== Journal Queue ====================

import type { IssueProgress } from '@/lib/types';

/** Tamamlanmış bir issue'nun makale listesini gösterir (accordion içi) */
function IssueArticleList({ articles }: { articles: string[] }) {
  if (articles.length === 0) return (
    <p className="px-3 py-1.5 text-xs text-slate-400 italic">Makale başlığı kaydedilmedi</p>
  );
  return (
    <ul className="px-3 py-1 space-y-0.5">
      {articles.map((title, i) => (
        <li key={i} className="flex items-start gap-1.5 text-xs text-slate-500">
          <span className="text-slate-300 flex-shrink-0 mt-0.5">›</span>
          <span className="line-clamp-2">{title}</span>
        </li>
      ))}
    </ul>
  );
}

/** Tamamlanmış bir issue satırı (tıklanabilir accordion) */
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

function JournalQueue({ scraper }: { scraper: ScraperStatus }) {
  // expandedJournals: tamamlanan dergilerin accordion durumu
  const [expandedJournals, setExpandedJournals] = useState<Set<string>>(new Set());
  // expandedIssues: "journalName|issueTitle" key ile issue accordion durumu
  const [expandedIssues, setExpandedIssues] = useState<Set<string>>(new Set());

  const toggleJournal = (name: string) =>
    setExpandedJournals(prev => { const s = new Set(prev); s.has(name) ? s.delete(name) : s.add(name); return s; });

  const toggleIssue = (key: string) =>
    setExpandedIssues(prev => { const s = new Set(prev); s.has(key) ? s.delete(key) : s.add(key); return s; });

  const completed = scraper.completed_journals ?? [];
  const pending   = scraper.pending_journals ?? [];
  const isActive  = !!scraper.current_journal && ['running', 'paused'].includes(scraper.status);
  const totalVisible = completed.length + (isActive ? 1 : 0) + pending.length;

  if (totalVisible === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Dergi Kuyruğu</span>
        <span className="text-xs text-slate-400">{scraper.current_journal_index}/{scraper.total_journals}</span>
      </div>

      {/* Scrollable list */}
      <div className="max-h-96 overflow-y-auto divide-y divide-slate-100">

        {/* ── Tamamlanan dergiler ── */}
        {completed.map((j, i) => {
          const isOpen = expandedJournals.has(j.name);
          const issues = j.issues ?? [];
          return (
            <div key={`done-${i}`} className="bg-white">
              {/* Dergi satırı */}
              <button
                onClick={() => toggleJournal(j.name)}
                className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-slate-50 transition-colors duration-150 text-left"
              >
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
                <span className="flex-1 text-xs text-slate-600 truncate" title={j.name}>{j.name}</span>
                {issues.length > 0 && (
                  <span className="text-xs text-slate-400 flex-shrink-0 mr-1">
                    {issues.length} sayı
                  </span>
                )}
                {j.articles_count > 0 && (
                  <span className="text-xs text-emerald-600 font-medium flex-shrink-0 flex items-center gap-1">
                    <FileText className="h-3 w-3" />{j.articles_count}
                  </span>
                )}
                <ChevronDown className={`h-3.5 w-3.5 text-slate-400 flex-shrink-0 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} />
              </button>

              {/* Issue accordion */}
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

        {/* ── Aktif dergi ── */}
        {isActive && scraper.current_journal && (
          <div className="bg-blue-50">
            {/* Dergi header */}
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

            {/* Bekleyen issue'lar */}
            {(scraper.pending_issues ?? []).length > 0 && (
              <div className="border-t border-blue-100 divide-y divide-blue-50">
                {(scraper.pending_issues ?? []).map((title, i) => (
                  <div key={i} className="px-3 py-1.5 flex items-center gap-2 opacity-40">
                    <Clock className="h-3 w-3 text-slate-400 flex-shrink-0" />
                    <span className="flex-1 text-xs text-slate-500 truncate">{title}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Bekleyen dergiler ── */}
        {pending.map((name, i) => (
          <div
            key={`pending-${i}`}
            className="flex items-center gap-2 px-4 py-2 bg-white"
          >
            <Clock className="h-3 w-3 text-slate-300 flex-shrink-0" />
            <span className="text-xs text-slate-400 truncate flex-1" title={name}>{name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==================== Scraper Control Card ====================

interface ScraperControlProps {
  scraper: ScraperStatus;
  title: string;
  description: string;
  onStart: (limit: number, depth?: number, issueOrder?: string) => Promise<void>;
  onStop: () => Promise<void>;
  onPause: () => Promise<void>;
  onResume: () => Promise<void>;
  showDepth?: boolean;
}

function ScraperControl({ scraper, title, description, onStart, onStop, onPause, onResume, showDepth }: ScraperControlProps) {
  const [actionLoading, setActionLoading] = useState(false);
  const [localElapsed, setLocalElapsed] = useState(scraper.elapsed_seconds);
  const [limit, setLimit] = useState<number>(25);
  const [depth, setDepth] = useState<number>(1);
  const [issueOrder, setIssueOrder] = useState<string>('newest_first');

  // Tekil journal modu aktifse idle gibi davran — gerçek durum JournalUrlScraper'da gösterilir
  const effectiveScraper = scraper.is_single_journal_mode
    ? { ...scraper, status: 'idle' as const, progress_percent: 0, current_journal: null, completed_journals: [], pending_journals: [] }
    : scraper;

  const config = statusConfig[effectiveScraper.status] || statusConfig.idle;

  // Gelen scraper nesnesindeki süre güncellendiğinde local state'i senkronize et
  useEffect(() => {
    setLocalElapsed(scraper.elapsed_seconds);
  }, [scraper.elapsed_seconds]);

  // Scraper çalışıyorsa her saniye süreyi artır
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (scraper.status === 'running') {
      interval = setInterval(() => {
        setLocalElapsed((prev) => prev + 1);
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [scraper.status]);

  const handleAction = async (action: () => Promise<void>) => {
    setActionLoading(true);
    try {
      await action();
    } catch (err) {
      console.error(err);
    } finally {
      setActionLoading(false);
    }
  };

  const isRunning = effectiveScraper.status === 'running';
  const isPaused = effectiveScraper.status === 'paused';
  const canStart = ['idle', 'stopped', 'completed', 'error'].includes(effectiveScraper.status);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <Badge variant={config.variant} className="text-sm">
            {config.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Progress */}
        <div>
          <div className="flex justify-between text-sm mb-2">
            <span className="text-slate-600">İlerleme</span>
            <span className="font-semibold">{effectiveScraper.progress_percent.toFixed(1)}%</span>
          </div>
          <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${effectiveScraper.status === 'error' ? 'bg-red-500' :
                effectiveScraper.status === 'completed' ? 'bg-emerald-500' :
                  'bg-gradient-to-r from-emerald-500 to-teal-400'
                }`}
              style={{ width: `${effectiveScraper.progress_percent}%` }}
            />
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-slate-900">{effectiveScraper.journals_scraped}</p>
            <p className="text-xs text-slate-500">/ {effectiveScraper.total_journals} Dergi</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-slate-900">{effectiveScraper.issues_scraped}</p>
            <p className="text-xs text-slate-500">Sayı</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-emerald-600">{effectiveScraper.articles_scraped}</p>
            <p className="text-xs text-slate-500">Yeni Makale</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <p className={`text-2xl font-bold ${effectiveScraper.errors_count > 0 ? 'text-red-600' : 'text-slate-900'}`}>
              {effectiveScraper.errors_count}
            </p>
            <p className="text-xs text-slate-500">Hata</p>
          </div>
        </div>

        {/* Journal Queue — tekil journal modunda gösterme */}
        {!scraper.is_single_journal_mode && (effectiveScraper.current_journal || (effectiveScraper.completed_journals?.length ?? 0) > 0) && (
          <JournalQueue scraper={effectiveScraper} />
        )}

        {/* Last Error */}
        {effectiveScraper.last_error && (
          <div className="bg-red-50 rounded-lg p-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs text-red-600 font-medium mb-1">Son Hata</p>
              <p className="text-sm text-red-800">{effectiveScraper.last_error}</p>
            </div>
          </div>
        )}

        {/* Time Info */}
        <div className="flex items-center justify-between text-sm text-slate-500">
          {effectiveScraper.started_at && (
            <span>Başlangıç: {new Date(effectiveScraper.started_at).toLocaleTimeString('tr-TR')}</span>
          )}
          {localElapsed > 0 && (
            <span>Geçen süre: {Math.floor(localElapsed / 60)} dk {Math.floor(localElapsed % 60)} sn</span>
          )}
        </div>

        {/* Actions Menu */}
        <div className="flex flex-col gap-3 pt-4 border-t border-slate-100">
          {canStart && (
            <div className="flex flex-col gap-3 w-full">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <label htmlFor={`limit-${title}`} className="text-sm text-slate-600 whitespace-nowrap">
                    Makale Limiti:
                  </label>
                  <input
                    id={`limit-${title}`}
                    type="number"
                    min="1"
                    max="5000"
                    value={limit}
                    onChange={(e) => setLimit(parseInt(e.target.value) || 25)}
                    className="w-20 px-2 py-1.5 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-slate-400"
                  />
                </div>

                {showDepth && (
                  <div className="flex items-center gap-2">
                    <label htmlFor={`depth-${title}`} className="text-sm text-slate-600 whitespace-nowrap">
                      Issue Derinliği:
                    </label>
                    <input
                      id={`depth-${title}`}
                      type="number"
                      min="1"
                      max="50"
                      value={depth}
                      onChange={(e) => setDepth(parseInt(e.target.value) || 1)}
                      className="w-16 px-2 py-1.5 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-slate-400"
                      title="Her journal'dan kaç issue işlenecek (1 = sadece en yeni)"
                    />
                  </div>
                )}
              </div>

              {/* Issue Sırası Toggle */}
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-600 whitespace-nowrap">Issue Sırası:</span>
                <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                  <button
                    id={`issue-order-newest-${title}`}
                    type="button"
                    onClick={() => setIssueOrder('newest_first')}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                      issueOrder === 'newest_first'
                        ? 'bg-slate-700 text-white'
                        : 'bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                    title="Issue'ları en yeniden en eskiye işle"
                  >
                    Yeniden Eskiye
                  </button>
                  <button
                    id={`issue-order-oldest-${title}`}
                    type="button"
                    onClick={() => setIssueOrder('oldest_first')}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors border-l border-slate-200 ${
                      issueOrder === 'oldest_first'
                        ? 'bg-slate-700 text-white'
                        : 'bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                    title="Issue'ları en eskiden en yeniye işle"
                  >
                    Eskiden Yeniye
                  </button>
                </div>
              </div>

              <Button
                variant="primary"
                onClick={() => handleAction(() => onStart(limit, showDepth ? depth : undefined, issueOrder))}
                isLoading={actionLoading}
                className="w-full"
              >
                <Play className="h-4 w-4 mr-2" />
                Başlat
              </Button>
            </div>
          )}

          <div className="flex gap-3 w-full">
            {isRunning && (
              <>
                <Button variant="warning" onClick={() => handleAction(onPause)} isLoading={actionLoading} className="flex-1">
                  <Pause className="h-4 w-4 mr-2" />
                  Duraklat
                </Button>
                <Button variant="secondary" onClick={() => handleAction(onStop)} isLoading={actionLoading} className="flex-1">
                  <Square className="h-4 w-4 mr-2" />
                  Durdur
                </Button>
              </>
            )}
            {isPaused && (
              <>
                <Button variant="primary" onClick={() => handleAction(onResume)} isLoading={actionLoading} className="flex-1">
                  <Play className="h-4 w-4 mr-2" />
                  Devam Et
                </Button>
                <Button variant="danger" onClick={() => handleAction(onStop)} isLoading={actionLoading} className="flex-1">
                  <Square className="h-4 w-4 mr-2" />
                  Durdur
                </Button>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Log Types & Helpers ====================

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  scraper_type: string;
}

const SCRAPER_OPTIONS = [
  { value: 'ieee', label: 'IEEE Xplore', variant: 'info' as const },
  { value: 'sciencedirect', label: 'ScienceDirect', variant: 'success' as const },
  { value: 'acm', label: 'ACM Digital Library', variant: 'warning' as const },
];

function scraperLabel(type: string) {
  if (type === 'ieee') return 'IEEE';
  if (type === 'acm') return 'ACM';
  return 'SD';
}

function scraperBadgeVariant(type: string): 'info' | 'warning' | 'success' {
  if (type === 'ieee') return 'info';
  if (type === 'acm') return 'warning';
  return 'success';
}

function getLevelColor(level: string) {
  switch (level) {
    case 'error': return 'text-red-600 bg-red-50';
    case 'warning': return 'text-amber-600 bg-amber-50';
    case 'success': return 'text-emerald-600 bg-emerald-50';
    default: return 'text-blue-600 bg-blue-50';
  }
}

function wsEventToLogEntry(e: ScraperEvent): LogEntry {
  return {
    timestamp: e.timestamp,
    level: e.type === 'error' ? 'error' : (e.data?.level as string) || 'info',
    message: (e.data?.message as string) || JSON.stringify(e.data),
    scraper_type: e.scraper_type,
  };
}

// ==================== Multi-Select Dropdown ====================

interface ScraperMultiSelectProps {
  selected: string[];
  onChange: (selected: string[]) => void;
}

function ScraperMultiSelect({ selected, onChange }: ScraperMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggle = (value: string) => {
    if (selected.includes(value)) {
      if (selected.length === 1) return; // en az 1 seçili kalmalı
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  const allSelected = selected.length === SCRAPER_OPTIONS.length;

  const toggleAll = () => {
    onChange(allSelected ? [SCRAPER_OPTIONS[0].value] : SCRAPER_OPTIONS.map((o) => o.value));
  };

  const displayLabel = allSelected
    ? 'Tüm Scraperlar'
    : selected.map((v) => scraperLabel(v)).join(', ');

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white hover:bg-slate-50 transition-colors min-w-[160px] justify-between"
      >
        <span className="text-slate-700 truncate">{displayLabel}</span>
        <ChevronDown className={`h-4 w-4 text-slate-400 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-52 bg-white border border-slate-200 rounded-lg shadow-lg z-20 py-1">
          {/* Tümünü seç / kaldır */}
          <button
            onClick={toggleAll}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 transition-colors text-slate-600"
          >
            <span className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${allSelected ? 'bg-slate-700 border-slate-700' : 'border-slate-300'}`}>
              {allSelected && <CheckCircle2 className="h-3 w-3 text-white" />}
            </span>
            Tümü
          </button>
          <div className="border-t border-slate-100 my-1" />
          {SCRAPER_OPTIONS.map((opt) => {
            const isChecked = selected.includes(opt.value);
            return (
              <button
                key={opt.value}
                onClick={() => toggle(opt.value)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 transition-colors"
              >
                <span className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${isChecked ? 'bg-slate-700 border-slate-700' : 'border-slate-300'}`}>
                  {isChecked && <CheckCircle2 className="h-3 w-3 text-white" />}
                </span>
                <Badge variant={opt.variant} className="text-xs">{opt.label}</Badge>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ==================== Single Log Row ====================

function LogRow({ log }: { log: LogEntry }) {
  return (
    <div className="flex items-start gap-2 text-sm py-0.5">
      <span className="text-xs text-slate-400 w-16 flex-shrink-0 pt-0.5">
        {new Date(log.timestamp).toLocaleTimeString('tr-TR')}
      </span>
      <Badge variant={scraperBadgeVariant(log.scraper_type)} className="text-xs flex-shrink-0">
        {scraperLabel(log.scraper_type)}
      </Badge>
      <span className={`px-1.5 py-0.5 rounded text-xs flex-shrink-0 ${getLevelColor(log.level)}`}>
        {log.level}
      </span>
      <span className="text-slate-700 flex-1 break-words">{log.message}</span>
    </div>
  );
}

// ==================== Split Panel (kendi WS bağlantısı) ====================

function useSplitLogPanel(scraperType: string) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const clearedAtRef = useRef<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pingRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
    const baseUrl = apiUrl
      .replace('/api/v1', '')
      .replace('http://', 'ws://')
      .replace('https://', 'wss://');
    const wsUrl = `${baseUrl}/ws/scrapers/events?scrapers=${scraperType}`;

    let ws: WebSocket;
    let destroyed = false;

    // Geçmiş logları REST API'den çek
    const loadHistory = async () => {
      try {
        const data = await getScraperLogs(scraperType, 500);
        const entries: LogEntry[] = (data.logs || []).map((l: LogEntry & { scraper_type?: string }) => ({
          ...l,
          scraper_type: l.scraper_type ?? scraperType,
        }));
        setLogs((prev) => {
          // WS ile gelen yeniler + eski REST logları, duplike olmadan birleştir
          const existing = new Set(prev.map((e) => `${e.timestamp}|${e.message}`));
          const fresh = entries.filter((e) => !existing.has(`${e.timestamp}|${e.message}`));
          return [...prev, ...fresh].sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 1000);
        });
      } catch { /* ignore */ }
    };

    const connect = () => {
      if (destroyed) return;
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (destroyed) { ws.close(); return; }
        setConnected(true);
        loadHistory();
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, 15000);
      };

      ws.onmessage = (e) => {
        try {
          const event: ScraperEvent = JSON.parse(e.data);
          if (event.type === 'pong' || event.type === 'connected' || event.type === 'subscribed') return;
          if (event.type === 'log' || event.type === 'error') {
            const entry = wsEventToLogEntry(event);
            if (clearedAtRef.current && entry.timestamp <= clearedAtRef.current) return;
            setLogs((prev) => [entry, ...prev].slice(0, 1000));
          }
        } catch { /* ignore */ }
      };

      ws.onclose = () => {
        setConnected(false);
        if (pingRef.current) { clearInterval(pingRef.current); pingRef.current = null; }
        if (!destroyed) setTimeout(connect, 5000);
      };
    };

    connect();

    return () => {
      destroyed = true;
      if (pingRef.current) clearInterval(pingRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [scraperType]);

  const clearLogs = useCallback(() => {
    clearedAtRef.current = new Date().toISOString();
    setLogs([]);
  }, []);

  return { logs, connected, clearLogs };
}

function SplitPanel({ scraperType, label }: { scraperType: string; label: string }) {
  const { logs, connected, clearLogs } = useSplitLogPanel(scraperType);
  const [search, setSearch] = useState('');

  const filtered = search.trim()
    ? logs.filter((l) => l.message.toLowerCase().includes(search.toLowerCase()))
    : logs;

  return (
    <div className="flex flex-col border border-slate-200 rounded-xl overflow-hidden bg-white min-h-[300px]">
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 border-b border-slate-200 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Badge variant={scraperBadgeVariant(scraperType)} className="text-xs">{label}</Badge>
          <span className="text-xs text-slate-500">Loglar</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1 text-xs ${connected ? 'text-emerald-600' : 'text-slate-400'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
            {connected ? 'Canlı' : 'Bağlanıyor...'}
          </span>
          {logs.length > 0 && (
            <button
              onClick={clearLogs}
              className="text-xs text-slate-400 hover:text-red-500 transition-colors px-1.5 py-0.5 rounded hover:bg-red-50"
              title="Logları temizle"
            >
              Temizle
            </button>
          )}
        </div>
      </div>
      <div className="px-3 py-2 border-b border-slate-100 flex-shrink-0">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Logda ara..."
          className="w-full px-2 py-1 text-xs border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-slate-400 bg-white"
        />
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-1 max-h-[500px]">
        {filtered.length === 0 ? (
          <p className="text-slate-400 text-xs text-center py-6">
            {logs.length === 0 ? 'Henüz log yok' : 'Arama sonucu bulunamadı'}
          </p>
        ) : (
          filtered.map((log, i) => <LogRow key={i} log={log} />)
        )}
      </div>
    </div>
  );
}

// ==================== Live Event Log ====================

function ScraperLogs({ wsEvents, isWsConnected }: { wsEvents: ScraperEvent[]; isWsConnected: boolean }) {
  const { subscribe, subscribedScrapers } = useGlobalScraperEvents();
  const [viewMode, setViewMode] = useState<'combined' | 'split'>('combined');
  const [polledLogs, setPolledLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [clearedAt, setClearedAt] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      const scraperParam = subscribedScrapers.length === 3 ? 'all' : subscribedScrapers[0] ?? 'all';
      const data = await getScraperLogs(scraperParam, 500);
      setPolledLogs(data.logs || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [subscribedScrapers]);

  useEffect(() => {
    if (viewMode === 'combined') fetchLogs();
  }, [fetchLogs, viewMode]);

  useEffect(() => {
    if (!isWsConnected && viewMode === 'combined') {
      const interval = setInterval(fetchLogs, 5000);
      return () => clearInterval(interval);
    }
  }, [isWsConnected, fetchLogs, viewMode]);

  // Subscription değişince backend'e bildir (combined modda)
  const handleSelectionChange = useCallback((selected: string[]) => {
    subscribe(selected);
  }, [subscribe]);

  // Mod değişince subscription'ı sıfırla
  const handleModeChange = useCallback((mode: 'combined' | 'split') => {
    setViewMode(mode);
    if (mode === 'split') {
      // Split modda global WS tüm scraper'ları alır (status/progress için)
      subscribe(['ieee', 'sciencedirect', 'acm']);
    }
  }, [subscribe]);

  const handleClear = useCallback(() => {
    const now = new Date().toISOString();
    setClearedAt(now);
    setPolledLogs([]);
  }, []);

  // Combined mod: WS events + polled logs merge
  const wsLogEntries: LogEntry[] = wsEvents
    .filter((e) => (e.type === 'log' || e.type === 'error') && subscribedScrapers.includes(e.scraper_type))
    .map(wsEventToLogEntry)
    .filter((e) => !clearedAt || e.timestamp > clearedAt);

  const combinedLogs = [...wsLogEntries, ...polledLogs]
    .filter((l, i, arr) => arr.findIndex((x) => x.timestamp === l.timestamp && x.message === l.message) === i)
    .slice(0, 500)
    .filter((l) => !search.trim() || l.message.toLowerCase().includes(search.toLowerCase()));

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Son Loglar</CardTitle>
            <CardDescription>
              {isWsConnected ? 'Canlı takip (WebSocket)' : 'Scraper aktivite logları (polling)'}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Mod toggle */}
            <div className="flex items-center border border-slate-200 rounded-lg overflow-hidden">
              <button
                onClick={() => handleModeChange('combined')}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs transition-colors ${viewMode === 'combined' ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}
              >
                <AlignJustify className="h-3.5 w-3.5" />
                Birleşik
              </button>
              <button
                onClick={() => handleModeChange('split')}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs transition-colors ${viewMode === 'split' ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}
              >
                <Columns2 className="h-3.5 w-3.5" />
                Bölünmüş
              </button>
            </div>

            {/* Multi-select (yalnızca combined modda) */}
            {viewMode === 'combined' && (
              <ScraperMultiSelect
                selected={subscribedScrapers}
                onChange={handleSelectionChange}
              />
            )}

            {/* Canlı indikatör */}
            {isWsConnected && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-600">
                <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                Canlı
              </span>
            )}
          </div>
        </div>

        {/* Arama + Temizle (combined modda) */}
        {viewMode === 'combined' && (
          <div className="flex items-center gap-2 mt-3">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Logda ara..."
              className="flex-1 px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400 bg-white"
            />
            <button
              onClick={handleClear}
              className="px-3 py-1.5 text-xs text-slate-500 border border-slate-200 rounded-lg hover:text-red-500 hover:border-red-200 hover:bg-red-50 transition-colors whitespace-nowrap"
            >
              Temizle
            </button>
          </div>
        )}
      </CardHeader>

      <CardContent>
        {viewMode === 'split' ? (
          // ── SPLIT MOD ──
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <SplitPanel scraperType="ieee" label="IEEE Xplore" />
            <SplitPanel scraperType="sciencedirect" label="ScienceDirect" />
            <SplitPanel scraperType="acm" label="ACM Digital Library" />
          </div>
        ) : loading ? (
          // ── COMBINED MOD yükleniyor ──
          <div className="animate-pulse space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-8 bg-slate-100 rounded" />
            ))}
          </div>
        ) : combinedLogs.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-4">
            {search.trim() ? 'Arama sonucu bulunamadı' : 'Henüz log yok'}
          </p>
        ) : (
          // ── COMBINED MOD loglar ──
          <div className="space-y-1 max-h-[500px] overflow-y-auto">
            {combinedLogs.map((log, idx) => (
              <LogRow key={idx} log={log} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ==================== Main Page ====================

export default function ScrapersPage() {
  const [status, setStatus] = useState<AllScrapersStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [openAlexExpanded, setOpenAlexExpanded] = useState(false);
  const [journalUrlExpanded, setJournalUrlExpanded] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getScrapersStatus();
      setStatus(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  // fetchStatus ref — onEvent closure'ında stale olmadan kullanmak için
  const fetchStatusRef = useRef(fetchStatus);
  useEffect(() => { fetchStatusRef.current = fetchStatus; }, [fetchStatus]);

  // Global WebSocket connection
  const { connectionStatus, events: wsEvents, isConnected } = useGlobalScraperEvents({
    onEvent: (event) => {
      if (event.type === 'status_update' || event.type === 'progress') {
        if (event.data) {
          setStatus(prev => {
            if (!prev) return prev;

            const newState = { ...prev };
            const sType = event.scraper_type;

            if (sType === 'ieee' || sType === 'sciencedirect' || sType === 'acm') {
              newState[sType] = {
                ...newState[sType],
                ...event.data
              };
            }

            // any_running / all_completed'ı yeniden hesapla
            const statuses = [newState.ieee?.status, newState.sciencedirect?.status, newState.acm?.status];
            newState.any_running = statuses.some(s => s === 'running' || s === 'starting' || s === 'paused');
            newState.all_completed = statuses.every(s => s === 'completed' || s === 'stopped' || s === 'idle' || s === 'error');

            return newState;
          });

          // Scraper terminal state'e geçince REST'ten kesin status çek
          const terminal = ['completed', 'stopped', 'error'];
          if (terminal.includes((event.data as Record<string, unknown>)?.status as string)) {
            setTimeout(() => fetchStatusRef.current(), 1500);
          }
        }
      }
    },
  });

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    // WS bağlıysa poll yapma (event'lere güven), değilse 5 saniyede bir poll yap
    if (!isConnected) {
      const interval = setInterval(fetchStatus, 5000);
      return () => clearInterval(interval);
    }
  }, [fetchStatus, isConnected]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Scraper Kontrol</h1>
          <p className="mt-1 text-slate-500">Web scraper yönetimi ve izleme</p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {[...Array(3)].map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="animate-pulse space-y-4">
                  <div className="h-6 bg-slate-200 rounded w-1/3" />
                  <div className="h-4 bg-slate-100 rounded w-full" />
                  <div className="h-32 bg-slate-50 rounded" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Scraper Kontrol</h1>
          <p className="mt-1 text-slate-500">Web scraper yönetimi ve izleme</p>
        </div>
        <div className="flex items-center gap-2">
          <ConnectionBadge status={connectionStatus} />
          {status?.any_running && (
            <Badge variant="success" className="animate-pulse">
              <span className="w-2 h-2 bg-emerald-500 rounded-full mr-2" />
              Aktif
            </Badge>
          )}
          <Button variant="ghost" size="sm" onClick={fetchStatus}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* URL ile Tekil Journal Scraping */}
      <div className="border border-slate-200 rounded-xl overflow-hidden bg-white shadow-sm">
        <button
          onClick={() => setJournalUrlExpanded(!journalUrlExpanded)}
          className="w-full flex items-center justify-between p-4 bg-slate-50 hover:bg-slate-100 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 text-blue-700 rounded-lg">
              <Link2 className="h-5 w-5" />
            </div>
            <div className="text-left">
              <h2 className="font-semibold text-slate-900">URL ile Journal İşle</h2>
              <p className="text-sm text-slate-500">ACM, ScienceDirect veya IEEE Xplore URL&#39;si girerek tekil dergi scraping yapın</p>
            </div>
          </div>
          <ChevronUp
            className={`h-5 w-5 text-slate-400 transition-transform ${journalUrlExpanded ? 'rotate-180' : ''}`}
          />
        </button>
        {journalUrlExpanded && (
          <div className="p-4 border-t border-slate-200">
            <JournalUrlScraper />
          </div>
        )}
      </div>

      {/* OpenAlex Tarayıcısı - Collapsible */}
      <div className="border border-slate-200 rounded-xl overflow-hidden bg-white shadow-sm">
        <button
          onClick={() => setOpenAlexExpanded(!openAlexExpanded)}
          className="w-full flex items-center justify-between p-4 bg-slate-50 hover:bg-slate-100 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-100 text-indigo-700 rounded-lg">
              <FileText className="h-5 w-5" />
            </div>
            <div className="text-left">
              <h2 className="font-semibold text-slate-900">Eksik Veri Taraması (OpenAlex)</h2>
              <p className="text-sm text-slate-500">Atıf metriği olmayan makaleleri ve dergileri OpenAlex üzerinden tarayın</p>
            </div>
          </div>
          <ChevronUp
            className={`h-5 w-5 text-slate-400 transition-transform ${openAlexExpanded ? 'rotate-180' : ''}`}
          />
        </button>
        {openAlexExpanded && (
          <div className="p-4 border-t border-slate-200">
            <OpenAlexScanner />
          </div>
        )}
      </div>

      {/* Scraper Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {status && (
          <>
            <ScraperControl
              scraper={status.ieee}
              title="IEEE Xplore Scraper"
              description="IEEE akademik makalelerini toplar"
              showDepth
              onStart={async (limit, depth, issueOrder) => { await startIeeeScraper(false, limit, depth ?? 1, issueOrder ?? 'newest_first'); await fetchStatus(); }}
              onStop={async () => { await stopIeeeScraper(); await fetchStatus(); }}
              onPause={async () => { await pauseIeeeScraper(); await fetchStatus(); }}
              onResume={async () => { await resumeIeeeScraper(); await fetchStatus(); }}
            />
            <ScraperControl
              scraper={status.sciencedirect}
              title="ScienceDirect Scraper"
              description="Elsevier ScienceDirect makalelerini toplar"
              showDepth
              onStart={async (limit, depth, issueOrder) => { await startScienceDirectScraper(false, limit, depth ?? 1, issueOrder ?? 'newest_first'); await fetchStatus(); }}
              onStop={async () => { await stopScienceDirectScraper(); await fetchStatus(); }}
              onPause={async () => { await pauseScienceDirectScraper(); await fetchStatus(); }}
              onResume={async () => { await resumeScienceDirectScraper(); await fetchStatus(); }}
            />
            <ScraperControl
              scraper={status.acm}
              title="ACM Digital Library Scraper"
              description="ACM akademik makalelerini toplar"
              showDepth
              onStart={async (limit, depth, issueOrder) => { await startAcmScraper(false, limit, depth ?? 1, issueOrder ?? 'newest_first'); await fetchStatus(); }}
              onStop={async () => { await stopAcmScraper(); await fetchStatus(); }}
              onPause={async () => { await pauseAcmScraper(); await fetchStatus(); }}
              onResume={async () => { await resumeAcmScraper(); await fetchStatus(); }}
            />
          </>
        )}
      </div>

      {/* Logs with WebSocket */}
      <ScraperLogs wsEvents={wsEvents} isWsConnected={isConnected} />
    </div>
  );
}
