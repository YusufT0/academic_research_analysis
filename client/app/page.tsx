'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { TrendingUp, ArrowUpRight, ArrowDownRight, BarChart3 } from 'lucide-react';
import StatsCards from '@/components/dashboard/StatsCards';
import ScraperStatus from '@/components/dashboard/ScraperStatus';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { getArticleStats, getArticles } from '@/lib/api';
import type { ArticleStats, Article } from '@/lib/types';

// Relative URL'leri tam URL'ye çevir
function getFullUrl(url: string, sourceWebsite: string): string {
  if (!url) return '';
  
  // Zaten tam URL ise direkt döndür
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  
  // Relative URL'yi kaynak siteye göre tam URL'ye çevir
  if (sourceWebsite === 'ieeexplore') {
    return `https://ieeexplore.ieee.org${url.startsWith('/') ? '' : '/'}${url}`;
  } else if (sourceWebsite === 'sciencedirect') {
    return `https://www.sciencedirect.com${url.startsWith('/') ? '' : '/'}${url}`;
  } else if (sourceWebsite === 'acm') {
    return `https://dl.acm.org${url.startsWith('/') ? '' : '/'}${url}`;
  }

  return url;
}

function RecentArticles() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchArticles() {
      try {
        const data = await getArticles({ page: 1, page_size: 5, sort_by: 'created_at', sort_order: 'desc' });
        setArticles(data.items);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchArticles();
  }, []);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Son Eklenen Makaleler</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 bg-slate-100 rounded"></div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Son Eklenen Makaleler</CardTitle>
      </CardHeader>
      <CardContent>
        {articles.length === 0 ? (
          <p className="text-slate-500 text-sm">Henüz makale yok</p>
        ) : (
          <div className="space-y-3">
            {articles.map((article) => (
              <div key={article.id} className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                <Link href={`/articles?article_id=${article.id}`} className="flex-1 min-w-0 group">
                  <h4 className="font-medium text-slate-900 text-sm line-clamp-2 group-hover:text-indigo-600 transition-colors">{article.title}</h4>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-slate-500">{article.journal_name}</span>
                    {article.publication_year && (
                      <Badge variant="default">{article.publication_year}</Badge>
                    )}
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

function TopKeywords() {
  const [stats, setStats] = useState<ArticleStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const data = await getArticleStats();
        setStats(data);
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
      <Card>
        <CardHeader>
          <CardTitle>Popüler Anahtar Kelimeler</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-2">
            {[...Array(10)].map((_, i) => (
              <div key={i} className="h-6 bg-slate-100 rounded"></div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Popüler Anahtar Kelimeler</CardTitle>
      </CardHeader>
      <CardContent>
        {!stats || stats.top_keywords.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 px-4">
            <div className="w-14 h-14 bg-slate-100 rounded-full flex items-center justify-center mb-3">
              <BarChart3 className="h-7 w-7 text-slate-400" />
            </div>
            <h3 className="text-base font-medium text-slate-700 mb-1">Henüz Anahtar Kelime Yok</h3>
            <p className="text-sm text-slate-500 text-center max-w-xs">
              Makaleler tarandıkça anahtar kelimeler burada görünecek.
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {stats.top_keywords.slice(0, 15).map((keyword, idx) => (
              <Badge 
                key={keyword._id} 
                variant={idx < 3 ? 'success' : idx < 7 ? 'info' : 'default'}
                className="cursor-pointer hover:opacity-80"
              >
                {keyword._id} ({keyword.count})
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function YearlyDistribution() {
  const [stats, setStats] = useState<ArticleStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const data = await getArticleStats();
        setStats(data);
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
      <Card>
        <CardHeader>
          <CardTitle>Yıllara Göre Dağılım</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse h-40 bg-slate-100 rounded"></div>
        </CardContent>
      </Card>
    );
  }

  const years = stats ? Object.entries(stats.by_year).sort((a, b) => Number(b[0]) - Number(a[0])).slice(0, 8) : [];
  const maxCount = Math.max(...years.map(([, count]) => count), 1);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Yıllara Göre Dağılım</CardTitle>
      </CardHeader>
      <CardContent>
        {years.length === 0 ? (
          <p className="text-slate-500 text-sm">Henüz veri yok</p>
        ) : (
          <div className="space-y-3">
            {years.map(([year, count]) => (
              <div key={year} className="flex items-center gap-3">
                <span className="text-sm font-medium text-slate-600 w-12">{year}</span>
                <div className="flex-1 h-6 bg-slate-100 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
                <span className="text-sm font-semibold text-slate-900 w-12 text-right">{count}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Dashboard</h1>
        <p className="mt-1 text-slate-500">Akademik araştırma trend analiz sistemi genel görünümü</p>
      </div>

      {/* Stats Cards */}
      <StatsCards />

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Scraper Status */}
        <ScraperStatus />
        
        {/* Recent Articles */}
        <RecentArticles />
      </div>

      {/* Bottom Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Keywords */}
        <TopKeywords />
        
        {/* Yearly Distribution */}
        <YearlyDistribution />
      </div>
    </div>
  );
}
