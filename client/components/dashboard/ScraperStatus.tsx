'use client';

import { useEffect, useState } from 'react';
import { Play, Pause, Square, RefreshCw, CheckCircle, XCircle, Clock } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { getScrapersStatus, startAllScrapers, stopAllScrapers } from '@/lib/api';
import type { AllScrapersStatus, ScraperStatus } from '@/lib/types';

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
  const config = statusConfig[scraper.status] || statusConfig.idle;
  
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-semibold text-slate-900">{title}</h4>
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
      
      {/* Current Journal */}
      {scraper.current_journal && (
        <div className="mt-3 pt-3 border-t border-slate-100">
          <p className="text-xs text-slate-500">Şu an işleniyor:</p>
          <p className="text-sm font-medium text-slate-700 truncate">{scraper.current_journal}</p>
        </div>
      )}
      
      {/* Last Error */}
      {scraper.last_error && (
        <div className="mt-2 p-2 bg-red-50 rounded text-xs text-red-600">
          {scraper.last_error}
        </div>
      )}
    </div>
  );
}

export default function ScraperStatusComponent() {
  const [status, setStatus] = useState<AllScrapersStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchStatus = async () => {
    try {
      const data = await getScrapersStatus();
      setStatus(data);
    } catch (err) {
      console.error('Scraper durumu alınamadı:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    // Her 3 saniyede güncelle
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleStartAll = async () => {
    setActionLoading(true);
    try {
      await startAllScrapers(true);
      await fetchStatus();
    } catch (err) {
      console.error('Başlatma hatası:', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStopAll = async () => {
    setActionLoading(true);
    try {
      await stopAllScrapers();
      await fetchStatus();
    } catch (err) {
      console.error('Durdurma hatası:', err);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Scraper Durumu</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-4">
            <div className="h-24 bg-slate-100 rounded"></div>
            <div className="h-24 bg-slate-100 rounded"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Scraper Durumu</CardTitle>
        <div className="flex gap-2">
          {status?.any_running ? (
            <Button 
              variant="danger" 
              size="sm" 
              onClick={handleStopAll}
              isLoading={actionLoading}
            >
              <Square className="h-4 w-4 mr-1" />
              Tümünü Durdur
            </Button>
          ) : (
            <Button 
              variant="primary" 
              size="sm" 
              onClick={handleStartAll}
              isLoading={actionLoading}
            >
              <Play className="h-4 w-4 mr-1" />
              Tümünü Başlat
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {status && (
            <>
              <ScraperCard scraper={status.ieee} title="IEEE Xplore" />
              <ScraperCard scraper={status.sciencedirect} title="ScienceDirect" />
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

