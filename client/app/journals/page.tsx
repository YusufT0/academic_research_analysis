'use client';

import { useEffect, useState } from 'react';
import { Search, Filter, ExternalLink, ChevronLeft, ChevronRight, BookOpen, FileText } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { getJournals, type JournalFilters } from '@/lib/api';
import type { Journal, PaginatedResponse } from '@/lib/types';

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
  }
  
  return url;
}

export default function JournalsPage() {
  const [data, setData] = useState<PaginatedResponse<Journal> | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filters, setFilters] = useState<JournalFilters>({
    page: 1,
    page_size: 12,
    sort_by: 'article_count',
    sort_order: 'desc',
  });

  useEffect(() => {
    async function fetchJournals() {
      setLoading(true);
      try {
        const result = await getJournals({ ...filters, search: searchTerm || undefined });
        setData(result);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    
    const debounce = setTimeout(fetchJournals, 300);
    return () => clearTimeout(debounce);
  }, [filters, searchTerm]);

  const handlePageChange = (newPage: number) => {
    setFilters((prev) => ({ ...prev, page: newPage }));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Dergiler</h1>
          <p className="mt-1 text-slate-500">
            Toplam {data?.total.toLocaleString() || 0} dergi
          </p>
        </div>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type="text"
                placeholder="Dergi ara..."
                className="w-full pl-10 pr-4 py-2 rounded-lg border border-slate-300 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div className="flex gap-3">
              <select
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                value={filters.source_website || ''}
                onChange={(e) => setFilters((prev) => ({ ...prev, source_website: e.target.value || undefined, page: 1 }))}
              >
                <option value="">Tüm Kaynaklar</option>
                <option value="ieeexplore">IEEE Xplore</option>
                <option value="sciencedirect">ScienceDirect</option>
              </select>
              <select
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                value={`${filters.sort_by}-${filters.sort_order}`}
                onChange={(e) => {
                  const [sortBy, sortOrder] = e.target.value.split('-');
                  setFilters((prev) => ({ ...prev, sort_by: sortBy, sort_order: sortOrder as 'asc' | 'desc', page: 1 }));
                }}
              >
                <option value="article_count-desc">Makale Sayısı</option>
                <option value="name-asc">İsim (A → Z)</option>
                <option value="name-desc">İsim (Z → A)</option>
                <option value="issue_count-desc">Sayı Sayısı</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Journals Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {loading ? (
          [...Array(6)].map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="animate-pulse space-y-3">
                  <div className="h-5 bg-slate-200 rounded w-3/4"></div>
                  <div className="h-4 bg-slate-100 rounded w-1/2"></div>
                  <div className="h-8 bg-slate-50 rounded"></div>
                </div>
              </CardContent>
            </Card>
          ))
        ) : data?.items.length === 0 ? (
          <div className="col-span-full">
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-slate-500">Dergi bulunamadı</p>
              </CardContent>
            </Card>
          </div>
        ) : (
          data?.items.map((journal) => (
            <Card key={journal.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-6">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-slate-900 line-clamp-2">{journal.name}</h3>
                    <div className="flex items-center gap-2 mt-2">
                      <Badge variant={journal.source_website === 'ieeexplore' ? 'info' : 'success'}>
                        {journal.source_website === 'ieeexplore' ? 'IEEE' : 'ScienceDirect'}
                      </Badge>
                      {journal.open_access && (
                        <Badge variant="success">Open Access</Badge>
                      )}
                    </div>
                  </div>
                  {journal.url && (
                    <a
                      href={getFullUrl(journal.url, journal.source_website)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-400 hover:text-emerald-600"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                </div>
                
                {journal.publisher && (
                  <p className="text-sm text-slate-500 mt-2">{journal.publisher}</p>
                )}
                
                <div className="flex items-center gap-4 mt-4 pt-4 border-t border-slate-100">
                  <div className="flex items-center gap-1.5 text-sm">
                    <BookOpen className="h-4 w-4 text-slate-400" />
                    <span className="font-medium">{journal.issue_count}</span>
                    <span className="text-slate-500">sayı</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-sm">
                    <FileText className="h-4 w-4 text-slate-400" />
                    <span className="font-medium">{journal.article_count}</span>
                    <span className="text-slate-500">makale</span>
                  </div>
                </div>
                
                {journal.subjects.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-3">
                    {journal.subjects.slice(0, 3).map((subject) => (
                      <span
                        key={subject}
                        className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded"
                      >
                        {subject}
                      </span>
                    ))}
                  </div>
                )}
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

