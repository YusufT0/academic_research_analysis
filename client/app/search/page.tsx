'use client';

import { useState } from 'react';
import { Search, ExternalLink, FileText, User, Tag, BookOpen } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { searchArticles } from '@/lib/api';
import type { SearchResult } from '@/lib/types';

// Relative URL'leri tam URL'ye çevir
function getFullUrl(url: string): string {
  if (!url) return '';
  
  // Zaten tam URL ise direkt döndür
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  
  // URL'den kaynak siteyi tahmin et
  if (url.includes('/xpl/') || url.includes('/document/') || url.includes('punumber=')) {
    return `https://ieeexplore.ieee.org${url.startsWith('/') ? '' : '/'}${url}`;
  } else if (url.includes('/science/') || url.includes('/pii/')) {
    return `https://www.sciencedirect.com${url.startsWith('/') ? '' : '/'}${url}`;
  }
  
  return url;
}

type SearchType = 'text' | 'title' | 'keyword' | 'author';

const searchTypes: { value: SearchType; label: string; icon: React.ReactNode }[] = [
  { value: 'text', label: 'Tam Metin', icon: <FileText className="h-4 w-4" /> },
  { value: 'title', label: 'Başlık', icon: <BookOpen className="h-4 w-4" /> },
  { value: 'keyword', label: 'Anahtar Kelime', icon: <Tag className="h-4 w-4" /> },
  { value: 'author', label: 'Yazar', icon: <User className="h-4 w-4" /> },
];

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState<SearchType>('text');
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setSearched(true);
    try {
      const data = await searchArticles(query.trim(), searchType, 100);
      setResults(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Makale Ara</h1>
        <p className="mt-1 text-slate-500">Başlık, özet, anahtar kelime veya yazar adına göre arama yapın</p>
      </div>

      {/* Search Form */}
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSearch} className="space-y-4">
            {/* Search Type Selection */}
            <div className="flex flex-wrap gap-2">
              {searchTypes.map((type) => (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => setSearchType(type.value)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    searchType === type.value
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                  }`}
                >
                  {type.icon}
                  {type.label}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  type="text"
                  placeholder={
                    searchType === 'text' ? 'Makale başlığı veya özetinde ara...' :
                    searchType === 'title' ? 'Başlıkta ara...' :
                    searchType === 'keyword' ? 'Anahtar kelime girin...' :
                    'Yazar adı girin...'
                  }
                  className="w-full pl-12 pr-4 py-3 rounded-lg border border-slate-300 text-base focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <Button type="submit" size="lg" isLoading={loading}>
                <Search className="h-5 w-5 mr-2" />
                Ara
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Results */}
      {searched && (
        <div className="space-y-4">
          {/* Results Header */}
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">
              {loading ? 'Aranıyor...' : `${results?.count || 0} sonuç bulundu`}
            </h2>
            {results && (
              <Badge variant="info">
                "{results.query}" için {results.search_type} araması
              </Badge>
            )}
          </div>

          {/* Results List */}
          {loading ? (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <Card key={i}>
                  <CardContent className="pt-6">
                    <div className="animate-pulse space-y-3">
                      <div className="h-5 bg-slate-200 rounded w-3/4"></div>
                      <div className="h-4 bg-slate-100 rounded w-1/2"></div>
                      <div className="h-16 bg-slate-50 rounded"></div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : results?.items.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Search className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                <p className="text-slate-500">Aramanızla eşleşen sonuç bulunamadı</p>
                <p className="text-sm text-slate-400 mt-1">Farklı anahtar kelimeler deneyin</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {results?.items.map((article) => (
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
                        </div>
                        
                        {article.authors.length > 0 && (
                          <p className="text-sm text-slate-500 mt-2">
                            <User className="h-3.5 w-3.5 inline mr-1" />
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
                                className="inline-block px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs rounded cursor-pointer hover:bg-emerald-100"
                                onClick={() => {
                                  setQuery(keyword);
                                  setSearchType('keyword');
                                }}
                              >
                                {keyword}
                              </span>
                            ))}
                          </div>
                        )}
                        
                        {article.doi && (
                          <p className="text-xs text-slate-400 mt-2">
                            DOI: {article.doi}
                          </p>
                        )}
                      </div>
                      
                      <a
                        href={getFullUrl(article.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-shrink-0 p-2 text-slate-400 hover:text-emerald-600 transition-colors"
                      >
                        <ExternalLink className="h-5 w-5" />
                      </a>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Initial State */}
      {!searched && (
        <Card>
          <CardContent className="py-16 text-center">
            <Search className="h-16 w-16 text-slate-200 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-700">Aramaya Başlayın</h3>
            <p className="text-slate-500 mt-1">Yukarıdaki arama kutusunu kullanarak makale arayın</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

