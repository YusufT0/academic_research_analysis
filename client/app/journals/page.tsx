'use client';

import { Suspense, useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { Search, Filter, ExternalLink, ChevronLeft, ChevronRight, BookOpen, FileText, Unlock, Star, Presentation, Activity } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { getJournals, getJournal, getJournalYearRange, type JournalFilters } from '@/lib/api';
import { YearRangeSlider } from '@/components/ui/YearRangeSlider';
import type { Journal, PaginatedResponse } from '@/lib/types';
import { JournalCard } from './JournalCard';

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

function JournalsContent() {
  const searchParams = useSearchParams();
  const journalIdParam = searchParams.get('journal_id');
  const issueIdParam = searchParams.get('issue_id');
  const articleIdParam = searchParams.get('article_id');

  const [data, setData] = useState<PaginatedResponse<Journal> | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [yearRange, setYearRange] = useState<{ min: number; max: number } | null>(null);
  const initializedUrlParam = useRef(false);
  const skipSearchTrigger = useRef(false);

  const [filters, setFilters] = useState<JournalFilters>({
    page: 1,
    page_size: 12,
    sort_by: 'article_count',
    sort_order: 'desc',
  });

  useEffect(() => {
    getJournalYearRange().then((r) => {
      setYearRange({ min: r.min_year, max: r.max_year });
      setFilters((prev) => ({ ...prev, year_min: r.min_year, year_max: r.max_year }));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    async function fetchJournals() {
      setLoading(true);
      try {
        if (journalIdParam && !initializedUrlParam.current) {
          initializedUrlParam.current = true;
          const journal = await getJournal(journalIdParam);
          if (journal) {
            skipSearchTrigger.current = true;
            setSearchTerm(journal.name);
            setData({ items: [journal], total: 1, page: 1, page_size: 1, total_pages: 1, has_next: false, has_prev: false });
            return;
          }
        }

        if (skipSearchTrigger.current) {
          skipSearchTrigger.current = false;
          return;
        }

        const result = await getJournals({ ...filters, search: searchTerm || undefined });
        setData(result);
      } catch (err) {
        console.error(err);
      } finally {
        if (!skipSearchTrigger.current) {
          setLoading(false);
        }
      }
    }
    
    const debounce = setTimeout(fetchJournals, 300);
    return () => clearTimeout(debounce);
  }, [filters, searchTerm, journalIdParam]);

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
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Sol yarı — arama + filtreler */}
            <div className="flex-1 flex items-center gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="Dergi ara..."
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>

              <select
                className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                value={filters.source_website || ''}
                onChange={(e) => setFilters((prev) => ({ ...prev, source_website: e.target.value || undefined, page: 1 }))}
              >
                <option value="">Tüm Kaynaklar</option>
                <option value="ieeexplore">IEEE Xplore</option>
                <option value="sciencedirect">ScienceDirect</option>
                <option value="acm">ACM Digital Library</option>
              </select>

              <select
                className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                value={`${filters.sort_by}-${filters.sort_order}`}
                onChange={(e) => {
                  const [sortBy, sortOrder] = e.target.value.split('-');
                  setFilters((prev) => ({ ...prev, sort_by: sortBy, sort_order: sortOrder as 'asc' | 'desc', page: 1 }));
                }}
              >
                <option value="article_count-desc">Makale Sayısı</option>
                <option value="total_citation_count-desc">Toplam Atıf Sayısı</option>
                <option value="h_index-desc">H-Index</option>
                <option value="i10_index-desc">i10-Index</option>
                <option value="name-asc">İsim (A → Z)</option>
                <option value="name-desc">İsim (Z → A)</option>
                <option value="issue_count-desc">Sayı Sayısı</option>
              </select>
            </div>

            {/* Sağ yarı — yıl aralığı slider */}
            {yearRange && (
              <div className="flex-1 flex flex-col justify-center">
                <YearRangeSlider
                  label="Sayı Yılı Aralığı"
                  min={yearRange.min}
                  max={yearRange.max}
                  value={[filters.year_min ?? yearRange.min, filters.year_max ?? yearRange.max]}
                  onChange={([min, max]) =>
                    setFilters((prev) => ({ ...prev, year_min: min, year_max: max, page: 1 }))
                  }
                />
              </div>
            )}
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
            <JournalCard 
              key={journal.id} 
              journal={journal} 
              getFullUrl={getFullUrl} 
              defaultExpandedIssueId={journal.id === journalIdParam ? issueIdParam : null}
              highlightArticleId={journal.id === journalIdParam ? articleIdParam : null}
            />
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

export default function JournalsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-500">Yükleniyor...</div>}>
      <JournalsContent />
    </Suspense>
  );
}
