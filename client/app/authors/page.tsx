'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { Users, FileText, BookOpen, ChevronLeft, ChevronRight, Hash, Search, Filter } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { getAuthors, type AuthorFilters } from '@/lib/api';

function AuthorsContent() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [searchInput, setSearchInput] = useState('');
  
  const [filters, setFilters] = useState<AuthorFilters>({
    page: 1,
    page_size: 20,
    sort_by: 'article_count_desc',
    search: '',
    min_articles: 1,
  });

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((prev) => ({
        ...prev,
        page: 1, // Reset page
        search: searchInput.length >= 2 ? searchInput : '',
      }));
    }, 500);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    async function fetchAuthors() {
      setLoading(true);
      try {
        const result = await getAuthors(filters);
        setData(result);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchAuthors();
  }, [filters]);

  const handlePageChange = (newPage: number) => {
    setFilters((prev) => ({ ...prev, page: newPage }));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Yazarlar</h1>
          <p className="mt-1 text-slate-500">
            Sistemde kayıtlı yazar ağı analizleri
          </p>
        </div>
        
        <div className="flex flex-wrap items-center gap-2">
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Yazar adı ara..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="pl-9 bg-white"
              />
            </div>
            
            <div className="relative">
                <select 
                    className="h-10 border border-slate-200 rounded-md bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500 appearance-none pr-8 cursor-pointer"
                    value={filters.sort_by}
                    onChange={(e) => setFilters(prev => ({ ...prev, sort_by: e.target.value, page: 1 }))}
                >
                    <option value="article_count_desc">En Çok Makale (Azalan)</option>
                    <option value="article_count_asc">En Az Makale (Artan)</option>
                    <option value="name_asc">İsim (A-Z)</option>
                    <option value="name_desc">İsim (Z-A)</option>
                </select>
                <Filter className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
            </div>

            <div className="relative flex items-center bg-white border border-slate-200 rounded-md h-10 px-3 min-w-32">
                <label className="text-xs text-slate-500 font-medium mr-2 shrink-0">Min. Makale:</label>
                <input 
                    type="number" 
                    min="1" 
                    value={filters.min_articles || 1}
                    onChange={(e) => setFilters(prev => ({ ...prev, min_articles: parseInt(e.target.value) || 1, page: 1 }))}
                    className="w-full text-sm font-semibold text-slate-700 outline-none bg-transparent"
                />
            </div>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-500 bg-slate-50 px-4 py-2 rounded-lg border border-slate-100 pb-2">
          <span>Toplam <strong>{data?.total.toLocaleString() || 0}</strong> sonuç listeleniyor.</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          [...Array(8)].map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="pt-6 h-32 bg-slate-50">{null}</CardContent>
            </Card>
          ))
        ) : data?.items.length === 0 ? (
          <div className="col-span-full py-12 text-center text-slate-500">Yazar bulunamadı.</div>
        ) : (
          data?.items.map((author: any) => (
            <Card key={author.name} className="hover:shadow-md hover:border-indigo-100 transition-all group border border-slate-200">
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1 w-full overflow-hidden">
                    <Link href={`/authors/${encodeURIComponent(author.name)}`}>
                        <h3 className="font-bold text-[15px] truncate text-slate-800 group-hover:text-indigo-600 transition-colors" title={author.name}>
                        {author.name}
                        </h3>
                    </Link>
                    <div className="flex items-center gap-3 mt-2">
                      <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-slate-50 px-2 py-1 rounded-md border border-slate-100">
                        <FileText className="h-3.5 w-3.5 text-emerald-500" />
                        <span className="font-semibold">{author.article_count}</span> Makale
                      </div>
                    </div>
                  </div>
                </div>
                {author.top_keywords?.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-100">
                    <div className="flex flex-wrap gap-1">
                        {author.top_keywords.map((kw: string) => (
                            <span key={kw} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[9px] uppercase font-semibold">
                                <Hash className="h-3 w-3" /> {kw}
                            </span>
                        ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))
        )}
      </div>

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

export default function AuthorsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center">Yükleniyor...</div>}>
      <AuthorsContent />
    </Suspense>
  );
}
