'use client';

import { useEffect, useState, useCallback } from 'react';
import { Play, Pause, Square, RefreshCw, CheckCircle, XCircle, Clock, ExternalLink } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { getScrapersStatus } from '@/lib/api';
import { useGlobalScraperEvents } from '@/components/providers/ScraperProvider';
import type { AllScrapersStatus, ScraperStatus } from '@/lib/types';
import Link from 'next/link';

const statusConfig: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'error' | 'info'; icon: React.ReactNode }> = {
  idle: { label: 'Bekliyor', variant: 'default', icon: <Clock className="h-3 w-3" /> },
  starting: { label: 'Başlatılıyor', variant: 'info', icon: <RefreshCw className="h-3 w-3 animate-spin" /> },
  running: { label: 'Çalışıyor', variant: 'success', icon: <Play className="h-3 w-3" /> },
  paused: { label: 'Duraklatıldı', variant: 'warning', icon: <Pause className="h-3 w-3" /> },
  stopping: { label: 'Durduruluyor', variant: 'warning', icon: <RefreshCw className="h-3 w-3 animate-spin" /> },
  stopped: { label: 'Durduruldu', variant: 'default', icon: <Square className="h-3 w-3" /> },
  error: { label: 'Hata', variant: 'error', icon: <XCircle className="h-3 w-3" /> },
  completed: { label: 'Tamamlandı', variant: 'success', icon: <CheckCircle className="h-3 w-3" /> },
};

function ScraperCard({ scraper, title }: { scraper: ScraperStatus; title: string }) {
  const [localElapsed, setLocalElapsed] = useState(scraper.elapsed_seconds);
  const config = statusConfig[scraper.status] || statusConfig.idle;

  useEffect(() => {
    setLocalElapsed(scraper.elapsed_seconds);
  }, [scraper.elapsed_seconds]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (scraper.status === 'running') {
      interval = setInterval(() => {
        setLocalElapsed((prev) => prev + 1);
      }, 1000);
    }
    return () => { if (interval) clearInterval(interval); };
  }, [scraper.status]);

  return (
    <Link href="/scrapers" className="block group cursor-pointer">
      <div className="rounded-lg border border-slate-200 p-4 hover:border-emerald-300 hover:shadow-sm transition-all">
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-semibold text-slate-900 group-hover:text-emerald-700 transition-colors flex items-center gap-1.5">
            {title}
            <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-50 transition-opacity" />
          </h4>
          <Badge variant={config.variant} className="flex items-center gap-1">
            {config.icon}
            {config.label}
          </Badge>
        </div>

        {/* Progress Bar */}
        <div className="mb-3">
          <div className="flex justify-between text-xs text-slate-500 mb-1">
            <span>İlerleme</span>
            <span>{scraper.progress_percent.toFixed(1)}%</span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${scraper.progress_percent}%` }}
            />
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-slate-500">Dergiler:</span>
            <span className="ml-1 font-medium">{scraper.journals_scraped}/{scraper.total_journals}</span>
          </div>
          <div>
            <span className="text-slate-500">Makaleler:</span>
            <span className="ml-1 font-medium">{scraper.articles_scraped}</span>
          </div>
          <div>
            <span className="text-slate-500">Sayılar:</span>
            <span className="ml-1 font-medium">{scraper.issues_scraped}</span>
          </div>
          <div>
            <span className="text-slate-500">Hatalar:</span>
            <span className={`ml-1 font-medium ${scraper.errors_count > 0 ? 'text-red-600' : ''}`}>
              {scraper.errors_count}
            </span>
          </div>
        </div>

        {scraper.current_journal && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <p className="text-xs text-slate-500">Şu an işleniyor:</p>
            <p className="text-sm font-medium text-slate-700 truncate">{scraper.current_journal}</p>
          </div>
        )}

        {scraper.last_error && (
          <div className="mt-2 p-2 bg-red-50 rounded text-xs text-red-600">
            {scraper.last_error}
          </div>
        )}
      </div>
    </Link>
  );
}

export default function ScraperStatusComponent() {
  const [status, setStatus] = useState<AllScrapersStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const { isConnected } = useGlobalScraperEvents({
    onEvent: (event) => {
      if (event.type === 'status_update' || event.type === 'progress') {
        if (event.data) {
          setStatus((prev: any) => {
            if (!prev) return prev;
            const newState = { ...prev };
            const sType = event.scraper_type;
            if (sType === 'ieee' || sType === 'sciencedirect' || sType === 'acm') {
              newState[sType] = { ...newState[sType], ...event.data };
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
      console.error('Scraper durumu alınamadı:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  useEffect(() => {
    if (!isConnected) {
      const interval = setInterval(fetchStatus, 3000);
      return () => clearInterval(interval);
    }
  }, [fetchStatus, isConnected]);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Scraper Durumu</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-3">
            {[...Array(3)].map((_, i) => <div key={i} className="h-24 bg-slate-100 rounded" />)}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <Link href="/scrapers" className="cursor-pointer group inline-flex items-center gap-2 hover:text-emerald-700 transition-colors">
          <CardTitle className="group-hover:text-emerald-700 transition-colors">Scraper Durumu</CardTitle>
          <ExternalLink className="h-4 w-4 text-slate-400 group-hover:text-emerald-500 transition-colors" />
        </Link>
      </CardHeader>
      <CardContent>
        {status && (
          <div className="space-y-3">
            <ScraperCard scraper={status.ieee} title="IEEE Xplore" />
            <ScraperCard scraper={status.sciencedirect} title="ScienceDirect" />
            <ScraperCard scraper={status.acm} title="ACM Digital Library" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

