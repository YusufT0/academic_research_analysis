'use client';

import { useEffect, useState } from 'react';
import { FileText, BookOpen, Layers, Database } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { getGeneralStats } from '@/lib/api';
import type { GeneralStats } from '@/lib/types';

interface StatCardProps {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  description?: string;
  color: string;
}

function StatCard({ title, value, icon, description, color }: StatCardProps) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-slate-500">{title}</p>
          <p className="mt-1 text-3xl font-bold text-slate-900">{value.toLocaleString()}</p>
          {description && (
            <p className="mt-1 text-sm text-slate-400">{description}</p>
          )}
        </div>
        <div className={`rounded-full p-3 ${color}`}>
          {icon}
        </div>
      </div>
    </Card>
  );
}

export default function StatsCards() {
  const [stats, setStats] = useState<GeneralStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchStats() {
      try {
        const data = await getGeneralStats();
        setStats(data);
      } catch (err) {
        setError('İstatistikler yüklenemedi');
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    fetchStats();
    // Her 30 saniyede güncelle
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <div className="animate-pulse">
              <div className="h-4 w-24 bg-slate-200 rounded mb-2"></div>
              <div className="h-8 w-16 bg-slate-200 rounded"></div>
            </div>
          </Card>
        ))}
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="rounded-lg bg-red-50 p-4 text-red-700">
        {error || 'Veriler alınamadı'}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        title="Toplam Makale"
        value={stats.database.articles}
        icon={<FileText className="h-6 w-6 text-blue-600" />}
        color="bg-blue-100"
      />
      <StatCard
        title="Toplam Dergi"
        value={stats.database.journals}
        icon={<BookOpen className="h-6 w-6 text-emerald-600" />}
        color="bg-emerald-100"
      />
      <StatCard
        title="Toplam Sayı"
        value={stats.database.issues}
        icon={<Layers className="h-6 w-6 text-purple-600" />}
        color="bg-purple-100"
      />
      <StatCard
        title="Veri Tabanı Boyutu"
        value={`${stats.database.data_size_mb} MB`}
        icon={<Database className="h-6 w-6 text-amber-600" />}
        color="bg-amber-100"
      />
    </div>
  );
}

