'use client';

import { useState, useEffect } from 'react';
import { Play, Square, Activity, Database, AlertCircle, RefreshCw } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { useScraperEvents } from '@/lib/useScraperEvents';
import { getOpenAlexStatus, startOpenAlexScan, stopOpenAlexScan } from '@/lib/api';

interface ScannerStatus {
  status: string;
  total_articles: number;
  processed_articles: number;
  total_journals: number;
  processed_journals: number;
  updated_count: number;
  start_time: string | null;
}

export function OpenAlexScanner() {
  const [status, setStatus] = useState<ScannerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initial status load
  useEffect(() => {
    fetchStatus();
  }, []);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const data: any = await getOpenAlexStatus();
      setStatus(data);
    } catch (err) {
      console.error(err);
      setError('Durum alınamadı.');
    } finally {
      setLoading(false);
    }
  };

  // Listen to WebSocket events
  useScraperEvents({
    onEvent: (event) => {
      if (event.scraper_type === 'openalex') {
        if (event.type === 'progress' || event.type === 'status_update' || event.type === 'completed' || event.type === 'stopped') {
          // Progress event typically contains updated numbers in data
          if (event.data) {
            setStatus((prev) => ({
              ...(prev as ScannerStatus),
              ...(event.data as unknown as Partial<ScannerStatus>),
              status: event.type === 'completed' ? 'completed' : event.type === 'stopped' ? 'stopped' : 'running'
            }));
          }
        }
        if (event.type === 'error') {
          setError(String(event.data?.message || 'Bilinmeyen Hata'));
        }
      }
    }
  });

  const handleStart = async () => {
    setError(null);
    try {
      const res: any = await startOpenAlexScan();
      setStatus(res.status);
    } catch (err: any) {
      setError(err?.message || 'Başlatılamadı');
    }
  };

  const handleStop = async () => {
    try {
      const res: any = await stopOpenAlexScan();
      setStatus(res.status);
    } catch (err: any) {
      setError(err?.message || 'Durdurulamadı');
    }
  };

  const isRunning = status?.status === 'running';

  const totalItems = (status?.total_articles || 0) + (status?.total_journals || 0);
  const processedItems = (status?.processed_articles || 0) + (status?.processed_journals || 0);
  const progressPercent = totalItems > 0 ? (processedItems / totalItems) * 100 : 0;

  return (
    <Card className="mb-6 border-purple-200 shadow-sm">
      <CardHeader className="bg-purple-50/50 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-purple-600" />
            <CardTitle className="text-lg text-purple-900">OpenAlex Eksik Veri Taraması</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={fetchStatus}
              disabled={loading}
              className="h-8"
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
            {!isRunning ? (
              <Button
                variant="primary"
                size="sm"
                onClick={handleStart}
                disabled={loading}
                className="bg-purple-600 hover:bg-purple-700 h-8"
              >
                <Play className="h-4 w-4 mr-2" />
                Başlat
              </Button>
            ) : (
              <Button
                variant="danger"
                size="sm"
                onClick={handleStop}
                disabled={loading}
                className="h-8"
              >
                <Square className="h-4 w-4 mr-2" />
                Durdur
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg flex items-center text-sm">
            <AlertCircle className="h-4 w-4 mr-2 flex-shrink-0" />
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="text-sm font-medium text-slate-500 mb-1">Durum</div>
            <div className="flex items-center gap-2 text-slate-900 font-semibold uppercase text-sm">
              {isRunning && <Activity className="h-4 w-4 text-purple-500 animate-pulse" />}
              {status?.status || 'Bilinmiyor'}
            </div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="text-sm font-medium text-slate-500 mb-1">Makaleler</div>
            <div className="text-xl font-semibold text-slate-900">
              {status?.processed_articles || 0} / {status?.total_articles || 0}
            </div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="text-sm font-medium text-slate-500 mb-1">Dergiler</div>
            <div className="text-xl font-semibold text-slate-900">
              {status?.processed_journals || 0} / {status?.total_journals || 0}
            </div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="text-sm font-medium text-slate-500 mb-1">Güncellenen</div>
            <div className="text-xl font-semibold text-emerald-600">
              {status?.updated_count || 0}
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-slate-500">
            <span>İlerleme</span>
            <span>%{progressPercent.toFixed(1)}</span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-purple-500 transition-all duration-500 ease-in-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
