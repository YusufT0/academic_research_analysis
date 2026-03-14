'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Search, Filter, ExternalLink, ChevronLeft, ChevronRight, Unlock, Star, TrendingUp, Target } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { getArticles, type ArticleFilters } from '@/lib/api';
import type { Article, PaginatedResponse } from '@/lib/types';

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

function ArticlesContent() {
  const searchParams = useSearchParams();
  const articleId = searchParams.get('article_id');

  const [data, setData] = useState<PaginatedResponse<Article> | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<ArticleFilters>({
    page: 1,
    page_size: 10,
    sort_by: 'publication_year',
    sort_order: 'desc',
    id: articleId || undefined,
  });
  const [showFilters, setShowFilters] = useState(false);

  // URL'den article_id geliyorsa veya değişiyorsa güncelle
  useEffect(() => {
    if (articleId) {
      setFilters(prev => ({ ...prev, id: articleId, page: 1 }));
    } else {
      setFilters(prev => {
        const newFilters = { ...prev };
        delete newFilters.id;
        return newFilters;
      });
    }
  }, [articleId]);

  useEffect(() => {
    async function fetchArticles() {
      setLoading(true);
      try {
        const result = await getArticles(filters);
        setData(result);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchArticles();
  }, [filters]);

  const handlePageChange = (newPage: number) => {
    setFilters((prev) => ({ ...prev, page: newPage }));
  };

  const handleFilterChange = (key: keyof ArticleFilters, value: string | number | boolean | undefined) => {
    setFilters((prev) => ({ ...prev, [key]: value, page: 1 }));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Makaleler</h1>
          <p className="mt-1 text-slate-500">
            Toplam {data?.total.toLocaleString() || 0} makale
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => setShowFilters(!showFilters)}
        >
          <Filter className="h-4 w-4 mr-2" />
          Filtreler
        </Button>
      </div>

      {/* Filters */}
      {showFilters && (
        <Card>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Kaynak</label>
                <select
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  value={filters.source_website || ''}
                  onChange={(e) => handleFilterChange('source_website', e.target.value || undefined)}
                >
                  <option value="">Tümü</option>
                  <option value="ieeexplore">IEEE Xplore</option>
                  <option value="sciencedirect">ScienceDirect</option>
                  <option value="acm">ACM Digital Library</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Yıl</label>
                <select
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  value={filters.publication_year || ''}
                  onChange={(e) => handleFilterChange('publication_year', e.target.value ? Number(e.target.value) : undefined)}
                >
                  <option value="">Tümü</option>
                  {[2025, 2024, 2023, 2022, 2021, 2020].map((year) => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Açık Erişim</label>
                <select
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  value={filters.open_access === undefined ? '' : String(filters.open_access)}
                  onChange={(e) => handleFilterChange('open_access', e.target.value === '' ? undefined : e.target.value === 'true')}
                >
                  <option value="">Tümü</option>
                  <option value="true">Evet</option>
                  <option value="false">Hayır</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Sıralama</label>
                <select
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  value={`${filters.sort_by}-${filters.sort_order}`}
                  onChange={(e) => {
                    const [sortBy, sortOrder] = e.target.value.split('-');
                    setFilters((prev) => ({ ...prev, sort_by: sortBy, sort_order: sortOrder as 'asc' | 'desc' }));
                  }}
                >
                  <option value="publication_year-desc">Yıl (Yeni → Eski)</option>
                  <option value="publication_year-asc">Yıl (Eski → Yeni)</option>
                  <option value="title-asc">Başlık (A → Z)</option>
                  <option value="title-desc">Başlık (Z → A)</option>
                  <option value="citation_count-desc">Atıf Sayısı</option>
                  <option value="citation_percentile-desc">Atıf Yüzdeliği (En Yüksek)</option>
                  <option value="fwci-desc">FWCI (En Yüksek)</option>
                </select>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Articles List */}
      <div className="space-y-4">
        {loading ? (
          [...Array(5)].map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="animate-pulse space-y-3">
                  <div className="h-5 bg-slate-200 rounded w-3/4"></div>
                  <div className="h-4 bg-slate-100 rounded w-1/2"></div>
                  <div className="h-20 bg-slate-50 rounded"></div>
                </div>
              </CardContent>
            </Card>
          ))
        ) : data?.items.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-slate-500">Makale bulunamadı</p>
            </CardContent>
          </Card>
        ) : (
          data?.items.map((article) => (
            <Card key={article.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-slate-900 text-lg leading-tight">
                      {article.title}
                    </h3>
                    
                    <div className="flex flex-wrap items-center gap-2 mt-2">
                      <span className="text-sm text-slate-600">{article.journal_name}</span>
                      {article.publication_year && (
                        <Badge variant="default">{article.publication_year}</Badge>
                      )}
                      <Badge variant={article.source_website === 'ieeexplore' ? 'info' : article.source_website === 'acm' ? 'warning' : 'success'}>
                        {article.source_website === 'ieeexplore' ? 'IEEE' : article.source_website === 'acm' ? 'ACM' : 'ScienceDirect'}
                      </Badge>
                    </div>

                    {/* Stats and Open Access */}
                    <div className="flex flex-wrap items-center gap-3 mt-3">
                      {article.open_access && (
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200 shadow-sm" title="Tam metin ücretsiz erişime açıktır">
                          <Unlock className="h-3.5 w-3.5" />
                          <span>Açık Erişim</span>
                        </div>
                      )}
                      
                      {article.citation_count > 0 && (
                        <div className="flex items-center gap-4 text-xs font-medium bg-gradient-to-r from-purple-50 to-indigo-50 text-indigo-900 px-3 py-1 rounded-md border border-indigo-100 shadow-sm">
                           <div className="flex items-center gap-1.5 font-bold">
                              <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                              <span>{article.citation_count} Atıf</span>
                           </div>
                           
                           {article.citation_percentile && (
                             <div className="flex items-center gap-1.5 border-l border-indigo-200 pl-4" title="Kendi alanında ve aynı yılda yayınlananlar arasındaki atıf yüzdeliği (100 en iyi)">
                               <TrendingUp className="h-3.5 w-3.5 text-indigo-500" />
                               <span>%{article.citation_percentile} Dilim</span>
                             </div>
                           )}

                           {article.fwci != null && (
                             <div className="flex items-center gap-1.5 border-l border-indigo-200 pl-4" title="Field-Weighted Citation Impact: 1.0 dünya ortalamasıdır. (Örn: 1.5 demek ortalamadan %50 daha fazla atıf alıyor demektir)">
                               <Target className="h-3.5 w-3.5 text-indigo-500" />
                               <span>FWCI: {article.fwci.toFixed(2)}</span>
                             </div>
                           )}
                        </div>
                      )}
                    </div>
                    
                    {article.authors.length > 0 && (
                      <p className="text-sm text-slate-500 mt-2">
                        {article.authors.slice(0, 3).join(', ')}
                        {article.authors.length > 3 && ` ve ${article.authors.length - 3} diğer`}
                      </p>
                    )}
                    
                    {article.abstract && (
                      <p className="text-sm text-slate-600 mt-3 line-clamp-3">
                        {article.abstract}
                      </p>
                    )}
                    
                    {article.keywords.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {article.keywords.slice(0, 5).map((keyword) => (
                          <span
                            key={keyword}
                            className="inline-block px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded"
                          >
                            {keyword}
                          </span>
                        ))}
                        {article.keywords.length > 5 && (
                          <span className="text-xs text-slate-400">+{article.keywords.length - 5}</span>
                        )}
                      </div>
                    )}
                  </div>
                  
                  <a
                    href={getFullUrl(article.url, article.source_website)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 p-2 text-slate-400 hover:text-emerald-600 transition-colors"
                  >
                    <ExternalLink className="h-5 w-5" />
                  </a>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            Sayfa {data.page} / {data.total_pages}
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handlePageChange(data.page - 1)}
              disabled={!data.has_prev}
            >
              <ChevronLeft className="h-4 w-4" />
              Önceki
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handlePageChange(data.page + 1)}
              disabled={!data.has_next}
            >
              Sonraki
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}


export default function ArticlesPage() {
  return (
    <Suspense fallback={<div className='p-8 text-center'>Yükleniyor...</div>}>
      <ArticlesContent />
    </Suspense>
  );
}
