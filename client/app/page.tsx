'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  TrendingUp, ArrowUpRight, BarChart3, PieChart, Users,
  FileText, BookOpen, BookMarked,
} from 'lucide-react';
import ScraperStatus from '@/components/dashboard/ScraperStatus';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { getArticleStats, getCitationStats, getArticles, getGeneralStats } from '@/lib/api';
import type { ArticleStats, CitationStats, Article, GeneralStats } from '@/lib/types';
import { TopicTrendsSection } from './trends/TopicTrendsSection';
import { CitationsSection } from './trends/CitationsSection';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getFullUrl(url: string, sourceWebsite: string): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (sourceWebsite === 'ieeexplore') return `https://ieeexplore.ieee.org${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'sciencedirect') return `https://www.sciencedirect.com${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'acm') return `https://dl.acm.org${url.startsWith('/') ? '' : '/'}${url}`;
  return url;
}

// ─── Recent Articles ──────────────────────────────────────────────────────────

function RecentArticles() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getArticles({ page: 1, page_size: 5, sort_by: 'created_at', sort_order: 'desc' })
      .then(d => setArticles(d.items))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Son Eklenen Makaleler</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="animate-pulse space-y-3">
            {[...Array(5)].map((_, i) => <div key={i} className="h-16 bg-slate-100 rounded" />)}
          </div>
        ) : articles.length === 0 ? (
          <p className="text-slate-500 text-sm">Henüz makale yok</p>
        ) : (
          <div className="space-y-3">
            {articles.map((article) => (
              <div key={article.id} className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                <Link href={`/articles?article_id=${article.id}`} className="flex-1 min-w-0 group">
                  <h4 className="font-medium text-slate-900 text-sm line-clamp-2 group-hover:text-indigo-600 transition-colors">
                    {article.title}
                  </h4>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-slate-500">{article.journal_name}</span>
                    {article.publication_year && <Badge variant="default">{article.publication_year}</Badge>}
                  </div>
                </Link>
                <a
                  href={getFullUrl(article.url, article.source_website)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-emerald-600 hover:text-emerald-700 flex-shrink-0"
                >
                  <ArrowUpRight className="h-4 w-4" />
                </a>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Yearly Trend Chart ───────────────────────────────────────────────────────

function YearlyTrendChart({ data }: { data: Record<string, number> }) {
  const years = Object.entries(data).sort((a, b) => Number(a[0]) - Number(b[0])).slice(-10);
  const maxCount = Math.max(...years.map(([, c]) => c), 1);

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

// ─── Keyword Cloud ────────────────────────────────────────────────────────────

function KeywordCloud({ keywords }: { keywords: Array<{ _id: string; count: number }> }) {
  if (!keywords || keywords.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4">
        <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
          <BarChart3 className="h-8 w-8 text-slate-400" />
        </div>
        <h3 className="text-lg font-medium text-slate-700 mb-2">Henüz Anahtar Kelime Yok</h3>
        <p className="text-sm text-slate-500 text-center max-w-xs">
          Makaleler tarandıkça anahtar kelimeler burada görünecek.
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
      {keywords.map((kw) => (
        <span
          key={kw._id}
          className={`${getSize(kw.count)} hover:text-emerald-500 cursor-pointer transition-colors px-2 py-1 rounded hover:bg-emerald-50`}
          title={`${kw.count} makale`}
        >
          {kw._id}
        </span>
      ))}
    </div>
  );
}

// ─── Source Distribution ──────────────────────────────────────────────────────

function SourceDistribution({ data }: { data: ArticleStats['by_source'] }) {
  const sources = Object.entries(data);
  const total = sources.reduce((sum, [, s]) => sum + s.count, 0);

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
      <div className="flex h-4 rounded-full overflow-hidden">
        {sources.map(([source, info]) => (
          <div key={source} className={`${colors[source] || 'bg-slate-400'} transition-all duration-500`} style={{ width: `${(info.count / total) * 100}%` }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-4">
        {sources.map(([source, info]) => (
          <div key={source} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg flex-1 min-w-[calc(50%-0.5rem)]">
            <div className={`w-4 h-4 rounded ${colors[source] || 'bg-slate-400'}`} />
            <div className="flex-1">
              <p className="font-medium text-slate-900">{labels[source] || source}</p>
              <p className="text-sm text-slate-500">{info.count.toLocaleString()} makale</p>
            </div>
            <p className="text-lg font-bold text-slate-900">{((info.count / total) * 100).toFixed(1)}%</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Top Authors ──────────────────────────────────────────────────────────────

function TopAuthors({ authors }: { authors: Array<{ _id: string; count: number }> }) {
  const maxCount = Math.max(...authors.map(a => a.count), 1);
  return (
    <div className="space-y-2">
      {authors.slice(0, 10).map((author, idx) => (
        <Link
          key={author._id}
          href={`/authors/${encodeURIComponent(author._id)}`}
          className="flex items-center gap-3 rounded-lg px-1 py-0.5 hover:bg-slate-50 transition-colors group"
        >
          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${idx < 3 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
            {idx + 1}
          </span>
          <span className="flex-1 text-sm font-medium text-slate-700 truncate group-hover:text-emerald-600 transition-colors">{author._id}</span>
          <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden flex-shrink-0">
            <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${(author.count / maxCount) * 100}%` }} />
          </div>
          <span className="text-sm font-semibold text-slate-900 w-8 text-right flex-shrink-0">{author.count}</span>
        </Link>
      ))}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const [stats, setStats] = useState<ArticleStats | null>(null);
  const [generalStats, setGeneralStats] = useState<GeneralStats | null>(null);
  const [citationStats, setCitationStats] = useState<CitationStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    Promise.all([getArticleStats(), getCitationStats(), getGeneralStats()])
      .then(([articleData, citationData, generalData]) => {
        setStats(articleData);
        setCitationStats(citationData);
        setGeneralStats(generalData);
      })
      .catch(console.error)
      .finally(() => setStatsLoading(false));
  }, []);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Genel Bakış</h1>
        <p className="mt-1 text-slate-500">
          {stats ? `Toplam ${stats.total.toLocaleString()} makale analiz edildi` : 'Akademik araştırma trend analiz sistemi'}
        </p>
      </div>

      {/* Birleşik İstatistik Kartları */}
      {statsLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          {[...Array(6)].map((_, i) => (
            <Card key={i}><div className="animate-pulse h-20 bg-slate-100 rounded" /></Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <Link href="/articles" className="block group">
            <Card className="h-full hover:border-blue-300 hover:shadow-md transition-all">
              <div className="flex flex-col items-center p-4 text-center">
                <div className="rounded-full p-2 bg-blue-100 mb-2 group-hover:bg-blue-200 transition-colors"><FileText className="h-5 w-5 text-blue-600" /></div>
                <p className="text-2xl font-bold text-slate-900">{(generalStats?.database.articles ?? stats?.total ?? 0).toLocaleString()}</p>
                <p className="text-xs text-slate-500 mt-1 group-hover:text-blue-600 transition-colors">Toplam Makale</p>
              </div>
            </Card>
          </Link>
          <Link href="/journals" className="block group">
            <Card className="h-full hover:border-emerald-300 hover:shadow-md transition-all">
              <div className="flex flex-col items-center p-4 text-center">
                <div className="rounded-full p-2 bg-emerald-100 mb-2 group-hover:bg-emerald-200 transition-colors"><BookOpen className="h-5 w-5 text-emerald-600" /></div>
                <p className="text-2xl font-bold text-slate-900">{(generalStats?.database.journals ?? 0).toLocaleString()}</p>
                <p className="text-xs text-slate-500 mt-1 group-hover:text-emerald-600 transition-colors">Toplam Dergi</p>
              </div>
            </Card>
          </Link>
          <Link href="/journals" className="block group">
            <Card className="h-full hover:border-purple-300 hover:shadow-md transition-all">
              <div className="flex flex-col items-center p-4 text-center">
                <div className="rounded-full p-2 bg-purple-100 mb-2 group-hover:bg-purple-200 transition-colors"><BookMarked className="h-5 w-5 text-purple-600" /></div>
                <p className="text-2xl font-bold text-slate-900">{(generalStats?.database.issues ?? 0).toLocaleString()}</p>
                <p className="text-xs text-slate-500 mt-1 group-hover:text-purple-600 transition-colors">Toplam Yayın (Issue)</p>
              </div>
            </Card>
          </Link>
          <Link href="/authors" className="block group">
            <Card className="h-full hover:border-indigo-300 hover:shadow-md transition-all">
              <div className="flex flex-col items-center p-4 text-center">
                <div className="rounded-full p-2 bg-indigo-100 mb-2 group-hover:bg-indigo-200 transition-colors"><Users className="h-5 w-5 text-indigo-600" /></div>
                <p className="text-2xl font-bold text-slate-900">{(stats?.unique_authors_count ?? 0).toLocaleString()}</p>
                <p className="text-xs text-slate-500 mt-1 group-hover:text-indigo-600 transition-colors">Toplam Yazar</p>
              </div>
            </Card>
          </Link>
          <Card>
            <div className="flex flex-col items-center p-4 text-center">
              <div className="rounded-full p-2 bg-teal-100 mb-2"><BarChart3 className="h-5 w-5 text-teal-600" /></div>
              <p className="text-2xl font-bold text-slate-900">{(stats?.unique_keywords_count ?? 0).toLocaleString()}</p>
              <p className="text-xs text-slate-500 mt-1">Farklı Anahtar Kelime</p>
            </div>
          </Card>
          <Card>
            <div className="flex flex-col items-center p-4 text-center">
              <div className="rounded-full p-2 bg-rose-100 mb-2"><TrendingUp className="h-5 w-5 text-rose-600" /></div>
              <p className="text-2xl font-bold text-slate-900">{(stats?.unique_years_count ?? 0).toLocaleString()}</p>
              <p className="text-xs text-slate-500 mt-1">Farklı Yıl</p>
            </div>
          </Card>
        </div>
      )}

      {/* Konu Trend Analizi — stats'ın hemen altında */}
      <TopicTrendsSection />

      {/* Scraper Durumu + Son Makaleler */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ScraperStatus />
        <RecentArticles />
      </div>

      {stats ? (
        <>
          {/* Yıllık Trend + Kaynak Dağılımı */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-emerald-600" />
                  <CardTitle>Yıllara Göre Yayın Trendi</CardTitle>
                </div>
                <CardDescription>Son 10 yılın makale dağılımı</CardDescription>
              </CardHeader>
              <CardContent><YearlyTrendChart data={stats.by_year} /></CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <PieChart className="h-5 w-5 text-emerald-600" />
                  <CardTitle>Kaynak Dağılımı</CardTitle>
                </div>
                <CardDescription>Platformlara göre makale dağılımı</CardDescription>
              </CardHeader>
              <CardContent><SourceDistribution data={stats.by_source} /></CardContent>
            </Card>
          </div>

          {/* Anahtar Kelimeler + En Aktif Yazarlar */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-emerald-600" />
                  <CardTitle>Popüler Anahtar Kelimeler (ACM)</CardTitle>
                </div>
                <CardDescription>En sık kullanılan anahtar kelimeler</CardDescription>
              </CardHeader>
              <CardContent><KeywordCloud keywords={stats.top_keywords} /></CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Users className="h-5 w-5 text-emerald-600" />
                  <CardTitle>En Aktif Yazarlar</CardTitle>
                </div>
                <CardDescription>En çok makalesi olan yazarlar</CardDescription>
              </CardHeader>
              <CardContent><TopAuthors authors={stats.top_authors} /></CardContent>
            </Card>
          </div>
        </>
      ) : null}

      {/* Atıf İstatistikleri */}
      {citationStats && <CitationsSection data={citationStats} />}
    </div>
  );
}
