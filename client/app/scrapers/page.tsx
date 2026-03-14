'use client';

import { useEffect, useState, useCallback } from 'react';
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
  CheckCircle2,
  Clock,
  Loader2,
  FileText,
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
import { ChevronUp } from 'lucide-react';

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

function JournalQueue({ scraper }: { scraper: ScraperStatus }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // Makale başlıklarını aktif dergi bazında biriktirir (state ile → React render tetiklenir)
  const [articlesByJournal, setArticlesByJournal] = useState<Record<string, string[]>>({});

  // current_article değiştiğinde aktif dergiye ekle
  useEffect(() => {
    if (!scraper.current_journal || !scraper.current_article) return;
    const key = scraper.current_journal;
    const title = scraper.current_article;
    setArticlesByJournal(prev => {
      const list = prev[key] ?? [];
      if (list.includes(title)) return prev;           // zaten var, render tetikleme
      return { ...prev, [key]: [...list, title] };
    });
  }, [scraper.current_article, scraper.current_journal]);

  const toggleExpand = (name: string) =>
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });

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
      <div className="max-h-72 overflow-y-auto divide-y divide-slate-100">

        {/* Tamamlananlar */}
        {completed.map((j, i) => {
          const isOpen = expanded.has(j.name);
          const localArticles = articlesByJournal[j.name] ?? [];
          return (
            <div key={`done-${i}`} className="bg-white">
              <button
                onClick={() => toggleExpand(j.name)}
                className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-slate-50 transition-colors duration-150 text-left"
              >
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
                <span className="flex-1 text-xs text-slate-600 truncate" title={j.name}>{j.name}</span>
                {j.articles_count > 0 && (
                  <span className="text-xs text-emerald-600 font-medium flex-shrink-0 flex items-center gap-1">
                    <FileText className="h-3 w-3" />{j.articles_count}
                  </span>
                )}
                <ChevronDown
                  className={`h-3.5 w-3.5 text-slate-400 flex-shrink-0 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`}
                />
              </button>

              {/* Accordion — CSS grid trick for smooth expand */}
              <div className={`grid transition-all duration-300 ease-in-out ${isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
                <div className="overflow-hidden">
                  {localArticles.length > 0 ? (
                    <ul className="px-4 pb-2 pt-1 space-y-1 bg-slate-50">
                      {localArticles.map((title, ti) => (
                        <li key={ti} className="flex items-start gap-1.5 text-xs text-slate-500">
                          <span className="text-slate-300 flex-shrink-0 mt-0.5">›</span>
                          <span className="line-clamp-2">{title}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="px-4 pb-2 pt-1 text-xs text-slate-400 bg-slate-50">Makale başlığı kaydedilmedi</p>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {/* Aktif dergi */}
        {isActive && scraper.current_journal && (
          <div className="bg-blue-50">
            {/* Journal header */}
            <div className="flex items-center gap-2 px-4 py-2.5">
              <Loader2 className="h-3.5 w-3.5 text-blue-500 flex-shrink-0 animate-spin" />
              <span className="flex-1 text-xs font-semibold text-blue-800 truncate" title={scraper.current_journal}>
                {scraper.current_journal}
              </span>
              {scraper.total_articles > 0 && (
                <span className="text-xs text-blue-400 flex-shrink-0">
                  {scraper.current_article_index}/{scraper.total_articles}
                </span>
              )}
            </div>

            {/* Article list accordion — shown as soon as article_list arrives */}
            {(() => {
              const artList = scraper.article_list ?? [];
              const curIdx = scraper.current_article_index; // 1-based
              if (artList.length === 0 && scraper.total_articles === 0) return null;

              const displayList = artList.length > 0
                ? artList
                : Array.from({ length: scraper.total_articles }, (_, i) => `Makale ${i + 1}`);

              return (
                <ul className="pb-2 space-y-0.5 max-h-48 overflow-y-auto">
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
                        className={`flex items-start gap-2 px-4 py-1 text-xs transition-colors duration-300 ${
                          isLoading ? 'bg-blue-100' : isDone ? 'opacity-60' : 'opacity-40'
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

        {/* Bekleyenler */}
        {pending.map((name, i) => (
          <div
            key={`pending-${i}`}
            className="flex items-center gap-2 px-4 py-2 bg-white"
            style={{ animationDelay: `${i * 30}ms` }}
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
  onStart: (limit: number) => Promise<void>;
  onStop: () => Promise<void>;
  onPause: () => Promise<void>;
  onResume: () => Promise<void>;
}

function ScraperControl({ scraper, title, description, onStart, onStop, onPause, onResume }: ScraperControlProps) {
  const [actionLoading, setActionLoading] = useState(false);
  const [localElapsed, setLocalElapsed] = useState(scraper.elapsed_seconds);
  const [limit, setLimit] = useState<number>(25);
  const config = statusConfig[scraper.status] || statusConfig.idle;

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

  const isRunning = scraper.status === 'running';
  const isPaused = scraper.status === 'paused';
  const canStart = ['idle', 'stopped', 'completed', 'error'].includes(scraper.status);

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
            <span className="font-semibold">{scraper.progress_percent.toFixed(1)}%</span>
          </div>
          <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${scraper.status === 'error' ? 'bg-red-500' :
                scraper.status === 'completed' ? 'bg-emerald-500' :
                  'bg-gradient-to-r from-emerald-500 to-teal-400'
                }`}
              style={{ width: `${scraper.progress_percent}%` }}
            />
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-slate-900">{scraper.journals_scraped}</p>
            <p className="text-xs text-slate-500">/ {scraper.total_journals} Dergi</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-slate-900">{scraper.issues_scraped}</p>
            <p className="text-xs text-slate-500">Sayı</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-emerald-600">{scraper.articles_scraped}</p>
            <p className="text-xs text-slate-500">Yeni Makale</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 text-center">
            <p className={`text-2xl font-bold ${scraper.errors_count > 0 ? 'text-red-600' : 'text-slate-900'}`}>
              {scraper.errors_count}
            </p>
            <p className="text-xs text-slate-500">Hata</p>
          </div>
        </div>

        {/* Journal Queue */}
        {(scraper.current_journal || (scraper.completed_journals?.length ?? 0) > 0) && (
          <JournalQueue scraper={scraper} />
        )}

        {/* Last Error */}
        {scraper.last_error && (
          <div className="bg-red-50 rounded-lg p-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs text-red-600 font-medium mb-1">Son Hata</p>
              <p className="text-sm text-red-800">{scraper.last_error}</p>
            </div>
          </div>
        )}

        {/* Time Info */}
        <div className="flex items-center justify-between text-sm text-slate-500">
          {scraper.started_at && (
            <span>Başlangıç: {new Date(scraper.started_at).toLocaleTimeString('tr-TR')}</span>
          )}
          {localElapsed > 0 && (
            <span>Geçen süre: {Math.floor(localElapsed / 60)} dk {Math.floor(localElapsed % 60)} sn</span>
          )}
        </div>

        {/* Actions Menu */}
        <div className="flex flex-col gap-3 pt-4 border-t border-slate-100">
          {canStart && (
            <div className="flex items-center gap-3 w-full">
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

              <Button
                variant="primary"
                onClick={() => handleAction(() => onStart(limit))}
                isLoading={actionLoading}
                className="flex-1"
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

// ==================== Live Event Log ====================

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  scraper_type: string;
}

function ScraperLogs({ wsEvents, isWsConnected }: { wsEvents: ScraperEvent[]; isWsConnected: boolean }) {
  const [polledLogs, setPolledLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchLogs = useCallback(async () => {
    try {
      const data = await getScraperLogs('all', 30);
      setPolledLogs(data.logs || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Sadece ilk yüklemede ve fetchLogs değiştiğinde (asla değişmez) bir kere çalışır
  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Polled logs (fallback + initial)
  useEffect(() => {
    // WS bağlıysa poll yapma (event'lere güven, gerçek zamanlı akar), değilse 5 saniyede bir poll yap
    if (!isWsConnected) {
      const interval = setInterval(fetchLogs, 5000);
      return () => clearInterval(interval);
    }
  }, [isWsConnected, fetchLogs]);

  // Merge: WS events + polled logs
  const wsLogEntries: LogEntry[] = wsEvents
    .filter((e) => e.type === 'log' || e.type === 'error')
    .map((e) => ({
      timestamp: e.timestamp,
      level: e.type === 'error' ? 'error' : (e.data?.level as string) || 'info',
      message: (e.data?.message as string) || JSON.stringify(e.data),
      scraper_type: e.scraper_type,
    }));

  const allLogs = [...wsLogEntries, ...polledLogs].slice(0, 50);

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'error': return 'text-red-600 bg-red-50';
      case 'warning': return 'text-amber-600 bg-amber-50';
      case 'success': return 'text-emerald-600 bg-emerald-50';
      default: return 'text-blue-600 bg-blue-50';
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Son Loglar</CardTitle>
            <CardDescription>
              {isWsConnected ? 'Canlı takip (WebSocket)' : 'Scraper aktivite logları (polling)'}
            </CardDescription>
          </div>
          {isWsConnected && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-600">
              <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              Canlı
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="animate-pulse space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-8 bg-slate-100 rounded" />
            ))}
          </div>
        ) : allLogs.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-4">Henüz log yok</p>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {allLogs.map((log, idx) => (
              <div key={idx} className="flex items-start gap-2 text-sm">
                <span className="text-xs text-slate-400 w-16 flex-shrink-0">
                  {new Date(log.timestamp).toLocaleTimeString('tr-TR')}
                </span>
                <Badge
                  variant={log.scraper_type === 'ieee' ? 'info' : log.scraper_type === 'acm' ? 'warning' : 'success'}
                  className="text-xs"
                >
                  {log.scraper_type === 'ieee' ? 'IEEE' : log.scraper_type === 'acm' ? 'ACM' : 'SD'}
                </Badge>
                <span className={`px-2 py-0.5 rounded text-xs ${getLevelColor(log.level)}`}>
                  {log.level}
                </span>
                <span className="text-slate-700 flex-1">{log.message}</span>
              </div>
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

  // Global WebSocket connection
  const { connectionStatus, events: wsEvents, isConnected } = useGlobalScraperEvents({
    onEvent: (event) => {
      // WS event'ı geldiğinde gönderilen payload'ı kullanarak durumu LOKAL olarak güncelle!
      // ESKİ KOD: fetchStatus() çağırıyordu. Bu da saniyede onlarca HTTP isteğine yol açıp backend'i çökertiyordu.
      if (event.type === 'status_update' || event.type === 'progress') {
        if (event.data) {
          setStatus(prev => {
            if (!prev) return prev;

            // Mevcut state'in klonunu al ve sadece güncellenen scraper'ı değiştir
            const newState = { ...prev };
            const sType = event.scraper_type;

            if (sType === 'ieee' || sType === 'sciencedirect' || sType === 'acm') {
              newState[sType] = {
                ...newState[sType],
                ...event.data
              };
            }

            return newState;
          });
        }
      }
    },
  });

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
              onStart={async (limit) => { await startIeeeScraper(false, limit); await fetchStatus(); }}
              onStop={async () => { await stopIeeeScraper(); await fetchStatus(); }}
              onPause={async () => { await pauseIeeeScraper(); await fetchStatus(); }}
              onResume={async () => { await resumeIeeeScraper(); await fetchStatus(); }}
            />
            <ScraperControl
              scraper={status.sciencedirect}
              title="ScienceDirect Scraper"
              description="Elsevier ScienceDirect makalelerini toplar"
              onStart={async (limit) => { await startScienceDirectScraper(false, limit); await fetchStatus(); }}
              onStop={async () => { await stopScienceDirectScraper(); await fetchStatus(); }}
              onPause={async () => { await pauseScienceDirectScraper(); await fetchStatus(); }}
              onResume={async () => { await resumeScienceDirectScraper(); await fetchStatus(); }}
            />
            <ScraperControl
              scraper={status.acm}
              title="ACM Digital Library Scraper"
              description="ACM akademik makalelerini toplar"
              onStart={async (limit) => { await startAcmScraper(false, limit); await fetchStatus(); }}
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
