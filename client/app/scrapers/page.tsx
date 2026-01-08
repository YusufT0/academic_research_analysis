'use client';

import { useEffect, useState } from 'react';
import { 
  Play, 
  Pause, 
  Square, 
  RefreshCw, 
  CheckCircle, 
  XCircle, 
  Clock,
  Settings,
  AlertTriangle
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
  getScraperLogs
} from '@/lib/api';
import type { AllScrapersStatus, ScraperStatus } from '@/lib/types';

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

interface ScraperControlProps {
  scraper: ScraperStatus;
  title: string;
  description: string;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
  onPause: () => Promise<void>;
  onResume: () => Promise<void>;
}

function ScraperControl({ scraper, title, description, onStart, onStop, onPause, onResume }: ScraperControlProps) {
  const [actionLoading, setActionLoading] = useState(false);
  const config = statusConfig[scraper.status] || statusConfig.idle;

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
              className={`h-full rounded-full transition-all duration-500 ${
                scraper.status === 'error' ? 'bg-red-500' :
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

        {/* Current Journal */}
        {scraper.current_journal && (
          <div className="bg-blue-50 rounded-lg p-4">
            <p className="text-xs text-blue-600 font-medium mb-1">Şu an işleniyor</p>
            <p className="text-sm font-semibold text-blue-900">{scraper.current_journal}</p>
            <p className="text-xs text-blue-600 mt-1">
              {scraper.current_journal_index} / {scraper.total_journals}
            </p>
          </div>
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
          {scraper.elapsed_seconds > 0 && (
            <span>Geçen süre: {Math.floor(scraper.elapsed_seconds / 60)} dk {Math.floor(scraper.elapsed_seconds % 60)} sn</span>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-4 border-t border-slate-100">
          {canStart && (
            <Button
              variant="primary"
              onClick={() => handleAction(onStart)}
              isLoading={actionLoading}
              className="flex-1"
            >
              <Play className="h-4 w-4 mr-2" />
              Başlat
            </Button>
          )}
          {isRunning && (
            <>
              <Button
                variant="secondary"
                onClick={() => handleAction(onPause)}
                isLoading={actionLoading}
                className="flex-1"
              >
                <Pause className="h-4 w-4 mr-2" />
                Duraklat
              </Button>
              <Button
                variant="danger"
                onClick={() => handleAction(onStop)}
                isLoading={actionLoading}
                className="flex-1"
              >
                <Square className="h-4 w-4 mr-2" />
                Durdur
              </Button>
            </>
          )}
          {isPaused && (
            <>
              <Button
                variant="primary"
                onClick={() => handleAction(onResume)}
                isLoading={actionLoading}
                className="flex-1"
              >
                <Play className="h-4 w-4 mr-2" />
                Devam Et
              </Button>
              <Button
                variant="danger"
                onClick={() => handleAction(onStop)}
                isLoading={actionLoading}
                className="flex-1"
              >
                <Square className="h-4 w-4 mr-2" />
                Durdur
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ScraperLogs() {
  const [logs, setLogs] = useState<Array<{timestamp: string; level: string; message: string; scraper_type: string}>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchLogs() {
      try {
        const data = await getScraperLogs('all', 30);
        setLogs(data.logs || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, []);

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
        <CardTitle>Son Loglar</CardTitle>
        <CardDescription>Scraper aktivite logları</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="animate-pulse space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-8 bg-slate-100 rounded"></div>
            ))}
          </div>
        ) : logs.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-4">Henüz log yok</p>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {logs.map((log, idx) => (
              <div key={idx} className="flex items-start gap-2 text-sm">
                <span className="text-xs text-slate-400 w-16 flex-shrink-0">
                  {new Date(log.timestamp).toLocaleTimeString('tr-TR')}
                </span>
                <Badge variant={log.scraper_type === 'ieee' ? 'info' : 'success'} className="text-xs">
                  {log.scraper_type === 'ieee' ? 'IEEE' : 'SD'}
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

export default function ScrapersPage() {
  const [status, setStatus] = useState<AllScrapersStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = async () => {
    try {
      const data = await getScrapersStatus();
      setStatus(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Scraper Kontrol</h1>
          <p className="mt-1 text-slate-500">Web scraper yönetimi ve izleme</p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[...Array(2)].map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="animate-pulse space-y-4">
                  <div className="h-6 bg-slate-200 rounded w-1/3"></div>
                  <div className="h-4 bg-slate-100 rounded w-full"></div>
                  <div className="h-32 bg-slate-50 rounded"></div>
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
          {status?.any_running && (
            <Badge variant="success" className="animate-pulse">
              <span className="w-2 h-2 bg-emerald-500 rounded-full mr-2"></span>
              Aktif
            </Badge>
          )}
          <Button variant="ghost" size="sm" onClick={fetchStatus}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Scraper Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {status && (
          <>
            <ScraperControl
              scraper={status.ieee}
              title="IEEE Xplore Scraper"
              description="IEEE akademik makalelerini toplar"
              onStart={async () => { await startIeeeScraper(false, 10); await fetchStatus(); }}
              onStop={async () => { await stopIeeeScraper(); await fetchStatus(); }}
              onPause={async () => { await pauseIeeeScraper(); await fetchStatus(); }}
              onResume={async () => { await resumeIeeeScraper(); await fetchStatus(); }}
            />
            <ScraperControl
              scraper={status.sciencedirect}
              title="ScienceDirect Scraper"
              description="Elsevier ScienceDirect makalelerini toplar"
              onStart={async () => { await startScienceDirectScraper(false, 5); await fetchStatus(); }}
              onStop={async () => { await stopScienceDirectScraper(); await fetchStatus(); }}
              onPause={async () => { await pauseScienceDirectScraper(); await fetchStatus(); }}
              onResume={async () => { await resumeScienceDirectScraper(); await fetchStatus(); }}
            />
          </>
        )}
      </div>

      {/* Logs */}
      <ScraperLogs />
    </div>
  );
}

