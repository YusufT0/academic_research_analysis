'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { Search, ExternalLink, FileText, User, Tag, Filter, X, BookOpen, Sparkles, Brain, AlertTriangle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { elasticSearch, getSearchSuggestions, searchArticles, nlpSearch, getNlpBarChartInput, getNlpPieChartInput, getNlpScatterChartInput, getNlpStatus } from '@/lib/api';
import type { ElasticSearchResult, ElasticSearchHit, SearchSuggestion, SearchResult, NlpSearchResponse, NlpBarChartData, NlpPieChartData, NlpScatterPoint } from '@/lib/types';
import AiAnalysisSection from './AiAnalysisSection';

// ==================== Helpers ====================

function getFullUrl(url: string): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (url.includes('/xpl/') || url.includes('/document/') || url.includes('punumber=')) {
    return `https://ieeexplore.ieee.org${url.startsWith('/') ? '' : '/'}${url}`;
  } else if (url.includes('/science/') || url.includes('/pii/')) {
    return `https://www.sciencedirect.com${url.startsWith('/') ? '' : '/'}${url}`;
  } else if (url.includes('/doi/') || url.includes('/toc/') || url.includes('/abs/')) {
    return `https://dl.acm.org${url.startsWith('/') ? '' : '/'}${url}`;
  }
  return url;
}

function HighlightedText({ html }: { html: string }) {
  // ES <em> tag'lerini styled <mark>'a dönüştür
  const sanitized = html.replace(/<em>/g, '<mark class="bg-amber-200/60 text-amber-900 rounded px-0.5">').replace(/<\/em>/g, '</mark>');
  return <span dangerouslySetInnerHTML={{ __html: sanitized }} />;
}

// ==================== Debounce Hook ====================

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debouncedValue;
}

// ==================== Active Filters ====================

// ==================== Active Filters ====================

interface ActiveFilters {
  source_website?: string;
  year?: number;
  journal_name?: string;
}

const formatSourceName = (key: string) => {
  if (key === 'ieeexplore') return 'IEEE Xplore';
  if (key === 'sciencedirect') return 'Science Direct';
  if (key === 'acm') return 'ACM Digital Library';
  return key;
};

// ==================== Main Component ====================

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [esResults, setEsResults] = useState<ElasticSearchResult | null>(null);
  const [fallbackResults, setFallbackResults] = useState<SearchResult | null>(null);
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [filters, setFilters] = useState<ActiveFilters>({});
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [page, setPage] = useState(1);
  const [useElastic, setUseElastic] = useState(true);
  const [showFilters, setShowFilters] = useState(false);

  // AI Analysis state
  const [aiResult, setAiResult] = useState<NlpSearchResponse | null>(null);
  const [aiBarData, setAiBarData] = useState<NlpBarChartData | null>(null);
  const [aiPieData, setAiPieData] = useState<NlpPieChartData | null>(null);
  const [aiScatterData, setAiScatterData] = useState<NlpScatterPoint[] | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiBarLoading, setAiBarLoading] = useState(false);
  const [aiPieLoading, setAiPieLoading] = useState(false);
  const [aiScatterLoading, setAiScatterLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);
  const debouncedQuery = useDebounce(query, 300);

  // Autocomplete
  useEffect(() => {
    if (!debouncedQuery || debouncedQuery.length < 2 || !useElastic) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;
    getSearchSuggestions(debouncedQuery, 5)
      .then((data) => { if (!cancelled) setSuggestions(data); })
      .catch(() => { if (!cancelled) setSuggestions([]); });

    return () => { cancelled = true; };
  }, [debouncedQuery, useElastic]);

  // Close suggestions on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSearch = useCallback(async (searchQuery?: string, searchPage = 1) => {
    const q = searchQuery || query;
    if (!q.trim()) return;

    setLoading(true);
    setSearched(true);
    setShowSuggestions(false);
    setPage(searchPage);

    try {
      if (useElastic) {
        const data = await elasticSearch({
          query: q.trim(),
          page: searchPage,
          page_size: 20,
          ...filters,
        });
        setEsResults(data);
        setFallbackResults(null);
      } else {
        const data = await searchArticles(q.trim(), 'text', searchPage, 20);
        setFallbackResults(data);
        setEsResults(null);
      }
    } catch (err) {
      console.error('Search error:', err);
      // ES hata verirse MongoDB'ye fallback
      if (useElastic) {
        try {
          const data = await searchArticles(q.trim(), 'text', searchPage, 20);
          setFallbackResults(data);
          setEsResults(null);
          setUseElastic(false);
        } catch {
          // Both failed
        }
      }
    } finally {
      setLoading(false);
    }
  }, [query, filters, useElastic]);

  const [aiTraining, setAiTraining] = useState(false);

  const handleAiAnalysis = useCallback(async () => {
    const q = query.trim();
    if (!q) return;

    setAiLoading(true);
    setAiTraining(false);
    setAiError(null);
    setAiResult(null);
    setAiBarData(null);
    setAiPieData(null);
    setAiScatterData(null);
    setSearched(true);
    setShowSuggestions(false);

    try {
      let needsTraining = false;
      try {
        const status = await getNlpStatus();
        needsTraining = !status.has_trained_model && !status.pkl_model_available && !status.cache_loaded;
      } catch {
        // Status endpoint unreachable - proceed anyway
      }

      if (needsTraining) {
        setAiTraining(true);
      }

      const searchRes = await nlpSearch(q, 20, true);
      setAiResult(searchRes);
      setAiLoading(false);
      setAiTraining(false);

      setAiBarLoading(true);
      setAiPieLoading(true);
      setAiScatterLoading(true);

      const [barRes, pieRes, scatterRes] = await Promise.allSettled([
        getNlpBarChartInput(),
        getNlpPieChartInput(),
        getNlpScatterChartInput(),
      ]);

      if (barRes.status === 'fulfilled') setAiBarData(barRes.value);
      setAiBarLoading(false);

      if (pieRes.status === 'fulfilled') setAiPieData(pieRes.value);
      setAiPieLoading(false);

      if (scatterRes.status === 'fulfilled') setAiScatterData(scatterRes.value);
      setAiScatterLoading(false);
    } catch (err: any) {
      console.error('AI analysis error:', err);
      const msg = err?.message || '';
      if (msg.includes('Yetersiz makale') || msg.includes('minimum')) {
        setAiError('Veritabanında yeterli sayıda abstract\'lı makale bulunamadı. Lütfen önce scraper çalıştırarak daha fazla makale toplayın.');
      } else if (msg.includes('API Error: 4')) {
        setAiError(`AI analizi başarısız: ${msg}. Sorgunuzu kontrol edin.`);
      } else {
        setAiError(msg || 'AI analizi sırasında bir hata oluştu. Backend loglarını kontrol edin.');
      }
      setAiLoading(false);
      setAiTraining(false);
      setAiBarLoading(false);
      setAiPieLoading(false);
      setAiScatterLoading(false);
    }
  }, [query]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch();
  };

  const selectSuggestion = (text: string) => {
    setQuery(text);
    setShowSuggestions(false);
    handleSearch(text);
  };

  const toggleFilter = (key: keyof ActiveFilters, value: string | number) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (next[key] === value) {
        delete next[key];
      } else {
        (next as Record<string, unknown>)[key] = value;
      }
      return next;
    });
  };

  const clearFilters = () => setFilters({});

  const activeFilterCount = Object.keys(filters).length;
  const totalResults = esResults?.total || fallbackResults?.total || 0;
  const items = esResults?.items || [];
  const facets = esResults?.facets;
  const totalPages = esResults?.total_pages || fallbackResults?.total_pages || 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Makale Ara</h1>
          <p className="mt-1 text-slate-500">
            {useElastic ? 'Elasticsearch full-text arama' : 'Veri tabanı araması'}
          </p>
        </div>
        <button
          onClick={() => setUseElastic(!useElastic)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${useElastic
            ? 'bg-amber-100 text-amber-800 hover:bg-amber-200'
            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
        >
          <Sparkles className="h-3.5 w-3.5" />
          {useElastic ? 'Elasticsearch' : 'MongoDB'}
        </button>
      </div>

      {/* Search Form */}
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={onSubmit} className="space-y-4">
            {/* Search Input + Autocomplete */}
            <div className="flex gap-3">
              <div className="flex-1 relative" ref={suggestionsRef}>
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="Başlık, özet, anahtar kelime veya yazar adında ara..."
                  className="w-full pl-12 pr-4 py-3 rounded-lg border border-slate-300 text-base focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none"
                  value={query}
                  onChange={(e) => { setQuery(e.target.value); setShowSuggestions(true); }}
                  onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                />

                {/* Autocomplete Dropdown */}
                {showSuggestions && suggestions.length > 0 && (
                  <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-white rounded-lg border border-slate-200 shadow-lg overflow-hidden">
                    {suggestions.map((s, i) => (
                      <button
                        key={i}
                        type="button"
                        className="w-full px-4 py-2.5 text-left text-sm hover:bg-slate-50 flex items-center gap-2"
                        onClick={() => selectSuggestion(s.text)}
                      >
                        <Search className="h-3.5 w-3.5 text-slate-400" />
                        <span>{s.text}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                {useElastic && (
                  <Button
                    type="button"
                    variant={showFilters ? 'primary' : 'secondary'}
                    onClick={() => setShowFilters(!showFilters)}
                    className="relative"
                  >
                    <Filter className="h-5 w-5" />
                    {activeFilterCount > 0 && (
                      <span className="absolute -top-1 -right-1 w-5 h-5 bg-emerald-500 text-white text-xs rounded-full flex items-center justify-center">
                        {activeFilterCount}
                      </span>
                    )}
                  </Button>
                )}
                <Button type="submit" size="lg" isLoading={loading}>
                  <Search className="h-5 w-5 mr-2" />
                  Ara
                </Button>
                <Button
                  type="button"
                  size="lg"
                  variant="secondary"
                  isLoading={aiLoading}
                  onClick={handleAiAnalysis}
                  className="bg-violet-100 text-violet-800 hover:bg-violet-200 border-violet-200"
                >
                  <Brain className="h-5 w-5 mr-2" />
                  AI Analiz
                </Button>
              </div>
            </div>

            {/* Active Filters */}
            {activeFilterCount > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-slate-500">Aktif filtreler:</span>
                {filters.source_website && (
                  <button onClick={() => toggleFilter('source_website', filters.source_website!)} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors">
                    Kaynak: {filters.source_website} <X className="h-3 w-3 ml-1" />
                  </button>
                )}
                {filters.year && (
                  <button onClick={() => toggleFilter('year', filters.year!)} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors">
                    Yıl: {filters.year} <X className="h-3 w-3 ml-1" />
                  </button>
                )}
                {filters.journal_name && (
                  <button onClick={() => toggleFilter('journal_name', filters.journal_name!)} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors">
                    Dergi: {filters.journal_name.substring(0, 30)} <X className="h-3 w-3 ml-1" />
                  </button>
                )}
                <button onClick={clearFilters} className="text-xs text-red-500 hover:text-red-700 ml-2">
                  Tümünü temizle
                </button>
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      {/* Results Area */}
      {searched && (
        <div className="flex gap-6">
          {/* Facet Sidebar */}
          {showFilters && facets && (
            <div className="w-64 flex-shrink-0 space-y-4">
              {/* Source Facets */}
              {facets.sources?.length > 0 && (
                <Card>
                  <CardHeader className="py-3 px-4">
                    <CardTitle className="text-sm">Kaynak</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-3">
                    <div className="space-y-1.5">
                      {facets.sources.map((s) => (
                        <button
                          key={s.key}
                          onClick={() => { toggleFilter('source_website', s.key); handleSearch(query); }}
                          className={`w-full flex items-center justify-between text-sm px-2 py-1.5 rounded transition-colors ${filters.source_website === s.key
                            ? 'bg-emerald-50 text-emerald-700 font-medium'
                            : 'text-slate-600 hover:bg-slate-50'
                            }`}
                        >
                          <span className="truncate">{formatSourceName(s.key)}</span>
                          <span className="text-xs text-slate-400 ml-2">{s.count}</span>
                        </button>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Year Facets */}
              {facets.years?.length > 0 && (
                <Card>
                  <CardHeader className="py-3 px-4">
                    <CardTitle className="text-sm">Yıl</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-3">
                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                      {facets.years.slice(0, 10).map((y) => (
                        <button
                          key={y.key}
                          onClick={() => { toggleFilter('year', parseInt(y.key)); handleSearch(query); }}
                          className={`w-full flex items-center justify-between text-sm px-2 py-1.5 rounded transition-colors ${filters.year === parseInt(y.key)
                            ? 'bg-emerald-50 text-emerald-700 font-medium'
                            : 'text-slate-600 hover:bg-slate-50'
                            }`}
                        >
                          <span>{y.key}</span>
                          <span className="text-xs text-slate-400 ml-2">{y.count}</span>
                        </button>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Journal Facets */}
              {facets.journals?.length > 0 && (
                <Card>
                  <CardHeader className="py-3 px-4">
                    <CardTitle className="text-sm">Dergi</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-3">
                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                      {facets.journals.slice(0, 8).map((j) => (
                        <button
                          key={j.key}
                          onClick={() => { toggleFilter('journal_name', j.key); handleSearch(query); }}
                          className={`w-full flex items-start justify-between text-sm px-2 py-1.5 rounded transition-colors ${filters.journal_name === j.key
                            ? 'bg-emerald-50 text-emerald-700 font-medium'
                            : 'text-slate-600 hover:bg-slate-50'
                            }`}
                        >
                          <span className="truncate text-left">{j.key}</span>
                          <span className="text-xs text-slate-400 ml-2 flex-shrink-0">{j.count}</span>
                        </button>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Results List */}
          <div className="flex-1 space-y-4">
            {/* Results Header */}
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900">
                {loading ? 'Aranıyor...' : `${totalResults.toLocaleString()} sonuç bulundu`}
              </h2>
              {(esResults || fallbackResults) && (
                <Badge variant="info">
                  Sayfa {page} / {totalPages}
                </Badge>
              )}
            </div>

            {/* Loading Skeleton */}
            {loading ? (
              <div className="space-y-4">
                {[...Array(3)].map((_, i) => (
                  <Card key={i}>
                    <CardContent className="pt-6">
                      <div className="animate-pulse space-y-3">
                        <div className="h-5 bg-slate-200 rounded w-3/4" />
                        <div className="h-4 bg-slate-100 rounded w-1/2" />
                        <div className="h-16 bg-slate-50 rounded" />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : totalResults === 0 ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <Search className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                  <p className="text-slate-500">Aramanızla eşleşen sonuç bulunamadı</p>
                  <p className="text-sm text-slate-400 mt-1">Farklı anahtar kelimeler deneyin</p>
                </CardContent>
              </Card>
            ) : (
              <>
                {/* ES Results with Highlights */}
                {esResults && items.map((article) => (
                  <ArticleCard key={article.id} article={article} />
                ))}

                {/* Fallback MongoDB Results */}
                {fallbackResults?.items.map((article) => (
                  <Card key={article.id} className="hover:shadow-md transition-shadow">
                    <CardContent className="pt-6">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <Link href={`/articles?article_id=${article.id}`}>
                            <h3 className="font-semibold text-slate-900 text-lg leading-tight hover:text-emerald-700 transition-colors cursor-pointer">{article.title}</h3>
                          </Link>
                          <div className="flex flex-wrap items-center gap-2 mt-2">
                            <span className="text-sm text-slate-600">{article.journal_name}</span>
                            {article.publication_year && <Badge variant="default">{article.publication_year}</Badge>}
                          </div>
                          {article.abstract && (
                            <p className="text-sm text-slate-600 mt-3 line-clamp-3">{article.abstract}</p>
                          )}
                        </div>
                        <a href={getFullUrl(article.url)} target="_blank" rel="noopener noreferrer" className="flex-shrink-0 p-2 text-slate-400 hover:text-emerald-600">
                          <ExternalLink className="h-5 w-5" />
                        </a>
                      </div>
                    </CardContent>
                  </Card>
                ))}

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-2 pt-4">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => handleSearch(query, page - 1)}
                    >
                      Önceki
                    </Button>
                    <span className="text-sm text-slate-600 px-4">
                      Sayfa {page} / {totalPages}
                    </span>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={page >= totalPages}
                      onClick={() => handleSearch(query, page + 1)}
                    >
                      Sonraki
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* AI Analysis Results */}
      {searched && aiError && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0" />
              <p className="text-sm text-amber-800">{aiError}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {searched && aiLoading && (
        <Card>
          <CardContent className="py-12 text-center">
            <Brain className="h-10 w-10 text-violet-400 mx-auto mb-3 animate-pulse" />
            {aiTraining ? (
              <>
                <p className="text-slate-600 font-medium">NLP modeli eğitiliyor...</p>
                <p className="text-sm text-slate-400 mt-1">
                  İlk kullanımda model eğitimi gerekiyor. Bu işlem makale sayısına bağlı olarak 1-5 dakika sürebilir.
                </p>
                <p className="text-xs text-slate-400 mt-2">Lütfen sayfayı kapatmayın</p>
              </>
            ) : (
              <>
                <p className="text-slate-600 font-medium">AI analizi yapılıyor...</p>
                <p className="text-sm text-slate-400 mt-1">NLP modeli sorgunuzu işliyor</p>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {aiResult && (
        <AiAnalysisSection
          searchResult={aiResult}
          barData={aiBarData}
          pieData={aiPieData}
          scatterData={aiScatterData}
          barLoading={aiBarLoading}
          pieLoading={aiPieLoading}
          scatterLoading={aiScatterLoading}
        />
      )}

      {/* Initial State */}
      {!searched && (
        <Card>
          <CardContent className="py-16 text-center">
            <Search className="h-16 w-16 text-slate-200 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-700">Aramaya Başlayın</h3>
            <p className="text-slate-500 mt-1">
              {useElastic
                ? 'Elasticsearch ile full-text arama, facet filtreleme ve autocomplete'
                : 'Veri tabanı üzerinden başlık, özet, yazar veya anahtar kelime araması'}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ==================== Article Card (ES Highlights) ====================

function ArticleCard({ article }: { article: ElasticSearchHit }) {
  const highlights = article.highlights;

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="pt-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            {/* Title with highlight */}
            <Link href={`/articles?article_id=${article.id}`}>
              <h3 className="font-semibold text-slate-900 text-lg leading-tight hover:text-emerald-700 transition-colors cursor-pointer">
                {highlights?.title?.[0]
                  ? <HighlightedText html={highlights.title[0]} />
                  : article.title}
              </h3>
            </Link>

            {/* Meta */}
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className="text-sm text-slate-600">{article.journal_name}</span>
              {article.publication_year && <Badge variant="default">{article.publication_year}</Badge>}
              <Badge variant={article.source_website === 'ieeexplore' ? 'info' : article.source_website === 'acm' ? 'warning' : 'success'} className="text-xs">
                {article.source_website === 'ieeexplore' ? 'IEEE' : article.source_website === 'acm' ? 'ACM' : 'ScienceDirect'}
              </Badge>
              {article.score && (
                <span className="text-xs text-slate-400">score: {article.score.toFixed(1)}</span>
              )}
            </div>

            {/* Authors */}
            {article.authors?.length > 0 && (
              <p className="text-sm text-slate-500 mt-2">
                <User className="h-3.5 w-3.5 inline mr-1" />
                {highlights?.authors?.[0]
                  ? <HighlightedText html={highlights.authors.join(', ')} />
                  : article.authors.slice(0, 3).join(', ')
                }
                {article.authors.length > 3 && ` ve ${article.authors.length - 3} diğer`}
              </p>
            )}

            {/* Abstract with highlight */}
            {(highlights?.abstract?.[0] || article.abstract) && (
              <p className="text-sm text-slate-600 mt-3 line-clamp-3">
                {highlights?.abstract?.[0]
                  ? <HighlightedText html={highlights.abstract[0]} />
                  : article.abstract}
              </p>
            )}

            {/* Keywords */}
            {article.keywords?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {article.keywords.slice(0, 5).map((kw) => (
                  <span key={kw} className="inline-block px-2 py-0.5 bg-emerald-50 text-emerald-700 text-xs rounded">
                    {kw}
                  </span>
                ))}
              </div>
            )}

            {/* DOI */}
            {article.doi && (
              <p className="text-xs text-slate-400 mt-2">DOI: {article.doi}</p>
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
  );
}
