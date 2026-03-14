'use client';

import { useEffect, useState } from 'react';
import { TrendingUp, BarChart3, PieChart, Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { getArticleStats, getCitationStats } from '@/lib/api';
import type { ArticleStats, CitationStats } from '@/lib/types';
import { CitationsSection } from './CitationsSection';

function YearlyTrendChart({ data }: { data: Record<string, number> }) {
  const years = Object.entries(data)
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .slice(-10);
  
  const maxCount = Math.max(...years.map(([, count]) => count), 1);

  return (
    <div className="space-y-2">
      {years.map(([year, count]) => (
        <div key={year} className="flex items-center gap-3">
          <span className="text-sm font-medium text-slate-600 w-12">{year}</span>
          <div className="flex-1 h-8 bg-slate-100 rounded-lg overflow-hidden relative">
            <div 
              className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-lg transition-all duration-700 flex items-center justify-end pr-2"
              style={{ width: `${Math.max((count / maxCount) * 100, 5)}%` }}
            >
              <span className="text-xs font-semibold text-white">{count}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function KeywordCloud({ keywords }: { keywords: Array<{ _id: string; count: number }> }) {
  // Veri yoksa veya boşsa empty state göster
  if (!keywords || keywords.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4">
        <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
          <BarChart3 className="h-8 w-8 text-slate-400" />
        </div>
        <h3 className="text-lg font-medium text-slate-700 mb-2">Henüz Anahtar Kelime Yok</h3>
        <p className="text-sm text-slate-500 text-center max-w-xs">
          Makaleler tarandıkça anahtar kelimeler burada görünecek. Scraper'ları çalıştırarak veri toplamaya başlayabilirsiniz.
        </p>
      </div>
    );
  }

  const maxCount = Math.max(...keywords.map(k => k.count), 1);
  
  const getSize = (count: number) => {
    const ratio = count / maxCount;
    if (ratio > 0.7) return 'text-xl font-bold text-emerald-700';
    if (ratio > 0.4) return 'text-lg font-semibold text-emerald-600';
    if (ratio > 0.2) return 'text-base font-medium text-slate-700';
    return 'text-sm text-slate-500';
  };

  return (
    <div className="flex flex-wrap gap-3 justify-center p-4">
      {keywords.map((keyword) => (
        <span
          key={keyword._id}
          className={`${getSize(keyword.count)} hover:text-emerald-500 cursor-pointer transition-colors px-2 py-1 rounded hover:bg-emerald-50`}
          title={`${keyword.count} makale`}
        >
          {keyword._id}
        </span>
      ))}
    </div>
  );
}

function SourceDistribution({ data }: { data: ArticleStats['by_source'] }) {
  const sources = Object.entries(data);
  const total = sources.reduce((sum, [, src]) => sum + src.count, 0);

  const colors: Record<string, string> = {
    ieeexplore: 'bg-blue-500',
    sciencedirect: 'bg-orange-500',
    acm: 'bg-amber-500',
  };

  const labels: Record<string, string> = {
    ieeexplore: 'IEEE Xplore',
    sciencedirect: 'ScienceDirect',
    acm: 'ACM Digital Library',
  };

  return (
    <div className="space-y-4">
      {/* Donut-like visualization */}
      <div className="flex h-4 rounded-full overflow-hidden">
        {sources.map(([source, info]) => (
          <div
            key={source}
            className={`${colors[source] || 'bg-slate-400'} transition-all duration-500`}
            style={{ width: `${(info.count / total) * 100}%` }}
          />
        ))}
      </div>
      
      {/* Legend */}
      <div className="flex flex-wrap gap-4">
        {sources.map(([source, info]) => (
          <div key={source} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg flex-1 min-w-[calc(50%-0.5rem)]">
            <div className={`w-4 h-4 rounded ${colors[source] || 'bg-slate-400'}`} />
            <div className="flex-1">
              <p className="font-medium text-slate-900">{labels[source] || source}</p>
              <p className="text-sm text-slate-500">{info.count.toLocaleString()} makale</p>
            </div>
            <div className="text-right">
              <p className="text-lg font-bold text-slate-900">
                {((info.count / total) * 100).toFixed(1)}%
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Additional Stats */}
      <div className="mt-4 pt-4 border-t border-slate-100 space-y-3">
        <div className="flex flex-wrap justify-center gap-3">
          {sources.map(([source, info]) => (
            <div key={`${source}-abstract`} className="text-center flex-1 min-w-[100px]">
              <p className="text-xs text-slate-500 mb-1">{labels[source] || source} - Özet</p>
              <p className="font-semibold text-slate-900">
                {info.with_abstract} <span className="text-xs text-slate-400">/ {info.count}</span>
              </p>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap justify-center gap-3">
          {sources.map(([source, info]) => (
            <div key={`${source}-doi`} className="text-center flex-1 min-w-[100px]">
              <p className="text-xs text-slate-500 mb-1">{labels[source] || source} - DOI</p>
              <p className="font-semibold text-slate-900">
                {info.with_doi} <span className="text-xs text-slate-400">/ {info.count}</span>
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function TopAuthors({ authors }: { authors: Array<{ _id: string; count: number }> }) {
  const maxCount = Math.max(...authors.map(a => a.count), 1);

  return (
    <div className="space-y-2">
      {authors.slice(0, 10).map((author, idx) => (
        <div key={author._id} className="flex items-center gap-3">
          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
            idx < 3 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'
          }`}>
            {idx + 1}
          </span>
          <span className="flex-1 text-sm font-medium text-slate-700 truncate">{author._id}</span>
          <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-emerald-500 rounded-full"
              style={{ width: `${(author.count / maxCount) * 100}%` }}
            />
          </div>
          <span className="text-sm font-semibold text-slate-900 w-8 text-right">{author.count}</span>
        </div>
      ))}
    </div>
  );
}

export default function TrendsPage() {
  const [stats, setStats] = useState<ArticleStats | null>(null);
  const [citationStats, setCitationStats] = useState<CitationStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const [articleData, citationData] = await Promise.all([
          getArticleStats(),
          getCitationStats()
        ]);
        setStats(articleData);
        setCitationStats(citationData);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Trend Analizi</h1>
          <p className="mt-1 text-slate-500">Akademik araştırma verilerinin görselleştirilmesi</p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="animate-pulse h-64 bg-slate-100 rounded"></div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-500">Veriler yüklenemedi</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Trend Analizi</h1>
        <p className="mt-1 text-slate-500">
          Toplam {stats.total.toLocaleString()} makale analiz edildi
        </p>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Yearly Trend */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-emerald-600" />
              <CardTitle>Yıllara Göre Yayın Trendi</CardTitle>
            </div>
            <CardDescription>Son 10 yılın makale dağılımı</CardDescription>
          </CardHeader>
          <CardContent>
            <YearlyTrendChart data={stats.by_year} />
          </CardContent>
        </Card>

        {/* Source Distribution */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <PieChart className="h-5 w-5 text-emerald-600" />
              <CardTitle>Kaynak Dağılımı</CardTitle>
            </div>
            <CardDescription>Platformlara göre makale dağılımı</CardDescription>
          </CardHeader>
          <CardContent>
            <SourceDistribution data={stats.by_source} />
          </CardContent>
        </Card>

        {/* Keyword Cloud */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-emerald-600" />
              <CardTitle>Popüler Anahtar Kelimeler</CardTitle>
            </div>
            <CardDescription>En sık kullanılan anahtar kelimeler</CardDescription>
          </CardHeader>
          <CardContent>
            <KeywordCloud keywords={stats.top_keywords} />
          </CardContent>
        </Card>

        {/* Top Authors */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-emerald-600" />
              <CardTitle>En Aktif Yazarlar</CardTitle>
            </div>
            <CardDescription>En çok makalesi olan yazarlar</CardDescription>
          </CardHeader>
          <CardContent>
            <TopAuthors authors={stats.top_authors} />
          </CardContent>
        </Card>
      </div>

      {/* Summary Stats */}
      <Card>
        <CardHeader>
          <CardTitle>Özet İstatistikler</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-3xl font-bold text-emerald-600">{stats.total.toLocaleString()}</p>
              <p className="text-sm text-slate-500 mt-1">Toplam Makale</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-3xl font-bold text-blue-600">{stats.top_keywords.length}</p>
              <p className="text-sm text-slate-500 mt-1">Farklı Anahtar Kelime</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-3xl font-bold text-purple-600">{stats.top_authors.length}</p>
              <p className="text-sm text-slate-500 mt-1">Farklı Yazar</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-3xl font-bold text-amber-600">{Object.keys(stats.by_year).length}</p>
              <p className="text-sm text-slate-500 mt-1">Farklı Yıl</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Citations Section */}
      {citationStats && <CitationsSection data={citationStats} />}
    </div>
  );
}

