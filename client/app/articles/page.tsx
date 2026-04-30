'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  Filter, ExternalLink, ChevronLeft, ChevronRight, Unlock, Star, TrendingUp, Target,
  ChevronDown, Users, FileText, Calendar, Tag, Hash, Building2, Link2, BookOpen, Info, Network
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { getArticles, getArticle, getArticleYearRange, type ArticleFilters } from '@/lib/api';
import type { Article, PaginatedResponse } from '@/lib/types';
import { YearRangeSlider } from '@/components/ui/YearRangeSlider';

function getFullUrl(url: string, sourceWebsite: string): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (sourceWebsite === 'ieeexplore') return `https://ieeexplore.ieee.org${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'sciencedirect') return `https://www.sciencedirect.com${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'acm') return `https://dl.acm.org${url.startsWith('/') ? '' : '/'}${url}`;
  return url;
}

function MetaItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex items-start gap-2.5 py-2.5 border-b border-slate-100 last:border-0">
      <div className="mt-0.5 text-slate-400 flex-shrink-0">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-0.5">{label}</div>
        <div className="text-sm text-slate-800 break-words">{value}</div>
      </div>
    </div>
  );
}

function SectionHeading({
  icon,
  title,
  count,
  color,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2.5 mb-3">
      <div className={`p-1.5 rounded-lg ${color}`}>{icon}</div>
      <h4 className="text-xs font-bold text-slate-600 uppercase tracking-widest">
        {title}
        {count !== undefined && (
          <span className="ml-1.5 font-normal normal-case text-slate-400">({count})</span>
        )}
      </h4>
    </div>
  );
}

function ArticleCard({ article }: { article: Article }) {
  const [expanded, setExpanded] = useState(false);
  const [fullArticle, setFullArticle] = useState<Article | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  async function handleExpand() {
    const next = !expanded;
    setExpanded(next);
    if (next && !fullArticle) {
      setDetailLoading(true);
      try {
        const data = await getArticle(article.id);
        setFullArticle(data);
      } catch {
        // fallback: liste verisini kullan
      } finally {
        setDetailLoading(false);
      }
    }
  }

  const detail = fullArticle ?? article;

  const sourceLabel =
    article.source_website === 'ieeexplore' ? 'IEEE' :
    article.source_website === 'acm' ? 'ACM' : 'ScienceDirect';
  const sourceBadgeVariant =
    article.source_website === 'ieeexplore' ? 'info' :
    article.source_website === 'acm' ? 'warning' : 'success';

  return (
    <Card
      className={`transition-all duration-300 ${
        expanded
          ? 'shadow-lg border-indigo-200 ring-1 ring-indigo-100'
          : 'hover:shadow-md hover:border-indigo-100'
      } group`}
    >
      <CardContent className="pt-6">
        {/* ── Clickable header ── */}
        <div className="cursor-pointer select-none" onClick={handleExpand}>
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <h3
                className={`font-semibold text-lg leading-tight transition-colors ${
                  expanded ? 'text-indigo-700' : 'text-slate-900 group-hover:text-indigo-700'
                }`}
              >
                {article.title}
              </h3>

              <div className="flex flex-wrap items-center gap-2 mt-2">
                <Link
                  href={`/journals?journal_id=${article.journal_id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="text-sm text-slate-600 font-medium hover:text-emerald-700 hover:underline cursor-pointer transition-colors"
                >
                  {article.journal_name}
                </Link>
                {article.publication_year && <Badge variant="default">{article.publication_year}</Badge>}
                <Badge variant={sourceBadgeVariant}>{sourceLabel}</Badge>
                {article.article_type && (
                  <span className="text-xs text-slate-400 italic">{article.article_type}</span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-3 mt-3">
                {article.open_access && (
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200 shadow-sm">
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
                      <div
                        className="flex items-center gap-1.5 border-l border-indigo-200 pl-4"
                        title="Kendi alanında ve aynı yılda yayınlananlar arasındaki atıf yüzdeliği (100 en iyi)"
                      >
                        <TrendingUp className="h-3.5 w-3.5 text-indigo-500" />
                        <span>%{article.citation_percentile} Dilim</span>
                      </div>
                    )}
                    {article.fwci != null && (
                      <div
                        className="flex items-center gap-1.5 border-l border-indigo-200 pl-4"
                        title="Field-Weighted Citation Impact: 1.0 dünya ortalamasıdır."
                      >
                        <Target className="h-3.5 w-3.5 text-indigo-500" />
                        <span>FWCI: {article.fwci.toFixed(2)}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {article.authors.length > 0 && (
                <p className="text-sm text-slate-500 mt-2">
                  {article.authors.slice(0, 3).map((author, i) => (
                    <Link
                      key={i}
                      href={`/authors/${encodeURIComponent(author)}`}
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center px-2.5 py-0.5 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs rounded-full cursor-pointer transition-all hover:bg-emerald-100 hover:border-emerald-400 hover:shadow-[0_0_8px_rgba(16,185,129,0.35)]"
                    >
                      {author}
                    </Link>
                  ))}
                  {article.authors.length > 3 && (
                    <span className="text-xs text-slate-400">+{article.authors.length - 3} diğer</span>
                  )}
                </p>
              )}

              {!expanded && article.abstract && (
                <p className="text-sm text-slate-600 mt-3 line-clamp-3">{article.abstract}</p>
              )}

              {!expanded && article.keywords.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {article.keywords.slice(0, 5).map((kw) => (
                    <span
                      key={kw}
                      className="inline-block px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded"
                    >
                      {kw}
                    </span>
                  ))}
                  {article.keywords.length > 5 && (
                    <span className="text-xs text-slate-400">+{article.keywords.length - 5} daha</span>
                  )}
                </div>
              )}
            </div>

            {/* Right controls */}
            <div className="flex-shrink-0 flex flex-col items-center gap-1.5">
              <a
                href={getFullUrl(article.url, article.source_website)}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="p-2 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 transition-all"
                title="Makaleyi aç"
              >
                <ExternalLink className="h-4.5 w-4.5" />
              </a>
              <div
                className={`p-2 rounded-lg transition-all duration-300 ${
                  expanded
                    ? 'bg-indigo-100 text-indigo-600'
                    : 'text-slate-400 group-hover:text-indigo-500 group-hover:bg-indigo-50'
                }`}
              >
                <ChevronDown
                  className={`h-4.5 w-4.5 transition-transform duration-300 ${expanded ? 'rotate-180' : ''}`}
                />
              </div>
            </div>
          </div>
        </div>

        {/* ── Expandable detail panel ── */}
        <div
          className={`grid transition-all duration-500 ease-in-out ${
            expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
          }`}
        >
          <div className="overflow-hidden">
            <div className="mt-5 border-t border-slate-100 pt-6 space-y-7">

              {/* Loading skeleton */}
              {detailLoading && (
                <div className="animate-pulse space-y-4">
                  <div className="h-3 bg-slate-200 rounded w-1/4" />
                  <div className="space-y-2">
                    <div className="h-3 bg-slate-100 rounded w-full" />
                    <div className="h-3 bg-slate-100 rounded w-5/6" />
                    <div className="h-3 bg-slate-100 rounded w-4/6" />
                  </div>
                </div>
              )}

              {/* Actions Box */}
              {!detailLoading && (
                <div className="flex flex-wrap items-center gap-3">
                  {(() => {
                    const isNotIndexed = detail.is_openalex_indexed === false;
                    const hasNoCitations = !detail.citation_count || detail.citation_count === 0;
                    const isDisabled = isNotIndexed || hasNoCitations;
                    
                    const tooltip = isNotIndexed 
                      ? "Bu makale OpenAlex veritabanında bulunamadı" 
                      : hasNoCitations 
                      ? "Bu makalenin henüz atıfı bulunmamaktadır" 
                      : "";

                    return (
                      <Link
                        href={isDisabled ? '#' : `/citation-map?article_id=${detail.id}&title=${encodeURIComponent(detail.title)}`}
                        onClick={(e) => { if (isDisabled) e.preventDefault(); }}
                        className={isDisabled ? 'pointer-events-none cursor-not-allowed opacity-80' : ''}
                        title={tooltip}
                      >
                        <Button 
                          type="button"
                          variant="secondary"
                          disabled={isDisabled}
                          className={`flex items-center gap-2 border ${
                            isNotIndexed 
                              ? 'bg-red-50 border-red-200 text-red-600 disabled:opacity-100 disabled:bg-red-50 disabled:text-red-600 disabled:border-red-200'
                              : 'border-indigo-200 text-indigo-700 hover:bg-indigo-50 disabled:opacity-50'
                          }`}
                        >
                          <Network className="w-4 h-4" /> Atıf Haritası Üzerinde İncele
                        </Button>
                      </Link>
                    );
                  })()}
                </div>
              )}

              {/* Journal Context Box */}
              {!detailLoading && detail.journal_id && detail.issue_id && (
                <div className="bg-indigo-50 p-4 rounded-xl border border-indigo-100 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-1 flex items-center gap-1.5">
                      <BookOpen className="h-3.5 w-3.5" /> Yayınlandığı Dergi & Sayı
                    </div>
                    <div className="text-sm font-medium text-slate-800">
                      {detail.journal_name}
                      {detail.issue_number ? ` - Sayı ${detail.issue_number}` : ''}
                      {detail.publication_year ? ` (${detail.publication_year})` : ''}
                    </div>
                  </div>
                  <Link 
                    href={`/journals?journal_id=${detail.journal_id}&issue_id=${detail.issue_id}&article_id=${detail.id}`}
                    className="flex-shrink-0 flex items-center justify-center gap-1.5 px-4 py-2 bg-white border border-indigo-200 text-indigo-700 text-xs font-semibold rounded-lg shadow-sm hover:bg-indigo-600 hover:text-white hover:border-indigo-600 transition-all"
                  >
                    Dergiler Sayfasına Git <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
              )}

              {/* Abstract */}
              {!detailLoading && detail.abstract && (
                <section>
                  <SectionHeading
                    icon={<FileText className="h-4 w-4 text-blue-600" />}
                    title="Abstract"
                    color="bg-blue-50"
                  />
                  <div className="relative">
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-blue-400 to-blue-200 rounded-full" />
                    <p className="pl-4 text-sm text-slate-700 leading-relaxed">{detail.abstract}</p>
                  </div>
                </section>
              )}

              {/* Introduction */}
              {!detailLoading && detail.introduction && (
                <section>
                  <SectionHeading
                    icon={<BookOpen className="h-4 w-4 text-violet-600" />}
                    title="Giriş"
                    color="bg-violet-50"
                  />
                  <div className="relative">
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-violet-400 to-violet-200 rounded-full" />
                    <p className="pl-4 text-sm text-slate-700 leading-relaxed">{detail.introduction}</p>
                  </div>
                </section>
              )}

              {/* Authors full list */}
              {!detailLoading && detail.authors.length > 0 && (
                <section>
                  <SectionHeading
                    icon={<Users className="h-4 w-4 text-amber-600" />}
                    title="Yazarlar"
                    count={detail.authors.length}
                    color="bg-amber-50"
                  />
                  <div className="flex flex-wrap gap-2">
                    {detail.authors.map((author, i) => (
                      <Link
                        key={i}
                        href={`/authors/${encodeURIComponent(author)}`}
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-full cursor-pointer transition-all hover:bg-emerald-100 hover:border-emerald-400 hover:shadow-[0_0_8px_rgba(16,185,129,0.35)]"
                      >
                        <span className="text-[10px] text-emerald-500 font-mono">{i + 1}</span>
                        {author}
                      </Link>
                    ))}
                  </div>
                </section>
              )}

              {/* Keywords full list */}
              {!detailLoading && detail.keywords.length > 0 && (
                <section>
                  <SectionHeading
                    icon={<Tag className="h-4 w-4 text-teal-600" />}
                    title="Anahtar Kelimeler"
                    count={detail.keywords.length}
                    color="bg-teal-50"
                  />
                  <div className="flex flex-wrap gap-2">
                    {detail.keywords.map((kw, i) => (
                      <span
                        key={i}
                        className="inline-block px-3 py-1 bg-teal-50 text-teal-800 text-xs font-medium rounded-full border border-teal-200 hover:bg-teal-100 transition-colors"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {/* Metadata */}
              {!detailLoading && (
              <section>
                <SectionHeading
                  icon={<Hash className="h-4 w-4 text-slate-500" />}
                  title="Metadata"
                  color="bg-slate-100"
                />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-10 bg-slate-50 rounded-xl border border-slate-100 px-5 py-1">
                  <MetaItem
                    icon={<Hash className="h-3.5 w-3.5" />}
                    label="DOI"
                    value={
                      detail.doi ? (
                        <a
                          href={`https://doi.org/${detail.doi}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-indigo-600 hover:text-indigo-800 underline underline-offset-2 font-mono text-xs break-all"
                        >
                          {detail.doi}
                        </a>
                      ) : null
                    }
                  />
                  <MetaItem
                    icon={<Calendar className="h-3.5 w-3.5" />}
                    label="Yayın Tarihi"
                    value={detail.publication_date}
                  />
                  <MetaItem
                    icon={<BookOpen className="h-3.5 w-3.5" />}
                    label="Dergi"
                    value={
                      detail.journal_name ? (
                        <Link
                          href={`/journals?journal_id=${detail.journal_id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-emerald-700 hover:underline cursor-pointer transition-colors"
                        >
                          {detail.journal_name}
                        </Link>
                      ) : null
                    }
                  />
                  <MetaItem
                    icon={<FileText className="h-3.5 w-3.5" />}
                    label="Sayfalar"
                    value={detail.pages}
                  />
                  <MetaItem
                    icon={<Building2 className="h-3.5 w-3.5" />}
                    label="Yayıncı"
                    value={detail.publisher}
                  />
                  <MetaItem
                    icon={<Info className="h-3.5 w-3.5" />}
                    label="Makale Türü"
                    value={detail.article_type}
                  />
                  <MetaItem
                    icon={<Hash className="h-3.5 w-3.5" />}
                    label="Sayı No"
                    value={detail.issue_number}
                  />
                  <MetaItem
                    icon={<Unlock className="h-3.5 w-3.5" />}
                    label="Açık Erişim"
                    value={
                      detail.open_access ? (
                        <span className="text-emerald-600 font-semibold">Evet</span>
                      ) : (
                        <span className="text-slate-500">Hayır</span>
                      )
                    }
                  />
                  <MetaItem
                    icon={<Star className="h-3.5 w-3.5" />}
                    label="Atıf Sayısı"
                    value={detail.citation_count > 0 ? detail.citation_count.toLocaleString() : null}
                  />
                  <MetaItem
                    icon={<TrendingUp className="h-3.5 w-3.5" />}
                    label="Atıf Yüzdeliği"
                    value={detail.citation_percentile ? `%${detail.citation_percentile}` : null}
                  />
                  <MetaItem
                    icon={<Target className="h-3.5 w-3.5" />}
                    label="FWCI"
                    value={detail.fwci != null ? detail.fwci.toFixed(3) : null}
                  />
                  <MetaItem
                    icon={<Calendar className="h-3.5 w-3.5" />}
                    label="Son Atıf Güncelleme"
                    value={
                      detail.last_citation_update_date
                        ? new Date(detail.last_citation_update_date).toLocaleDateString('tr-TR', {
                            day: '2-digit', month: 'long', year: 'numeric',
                          })
                        : null
                    }
                  />
                  <MetaItem
                    icon={<Link2 className="h-3.5 w-3.5" />}
                    label="OpenAlex ID"
                    value={
                      detail.openalex_id ? (
                        <span className="font-mono text-xs text-slate-600">{detail.openalex_id}</span>
                      ) : null
                    }
                  />
                  <MetaItem
                    icon={<Info className="h-3.5 w-3.5" />}
                    label="OpenAlex İndeksli"
                    value={
                      detail.is_openalex_indexed !== undefined ? (
                        detail.is_openalex_indexed ? (
                          <span className="text-emerald-600 font-semibold">Evet</span>
                        ) : (
                          <span className="text-slate-400">Hayır</span>
                        )
                      ) : null
                    }
                  />
                  <MetaItem
                    icon={<Calendar className="h-3.5 w-3.5" />}
                    label="Sisteme Eklenme"
                    value={
                      detail.created_at
                        ? new Date(detail.created_at).toLocaleDateString('tr-TR', {
                            day: '2-digit', month: 'long', year: 'numeric',
                          })
                        : null
                    }
                  />
                  <MetaItem
                    icon={<Calendar className="h-3.5 w-3.5" />}
                    label="Son Güncelleme"
                    value={
                      detail.updated_at
                        ? new Date(detail.updated_at).toLocaleDateString('tr-TR', {
                            day: '2-digit', month: 'long', year: 'numeric',
                          })
                        : null
                    }
                  />
                </div>
              </section>
              )}

            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ArticlesContent() {
  const searchParams = useSearchParams();
  const articleId = searchParams.get('article_id');

  const [data, setData] = useState<PaginatedResponse<Article> | null>(null);
  const [loading, setLoading] = useState(true);
  const [yearRange, setYearRange] = useState<{ min: number; max: number } | null>(null);
  const [yearRangeLoaded, setYearRangeLoaded] = useState(false);
  const [filters, setFilters] = useState<ArticleFilters>({
    page: 1,
    page_size: 10,
    sort_by: 'citation_count',
    sort_order: 'desc',
    id: articleId || undefined,
  });
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    getArticleYearRange().then((r) => {
      setYearRange({ min: r.min_year, max: r.max_year });
      setFilters((prev) => ({ ...prev, year_min: r.min_year, year_max: r.max_year, include_no_date: true }));
      setYearRangeLoaded(true);
    }).catch(() => {
      setYearRangeLoaded(true);
    });
  }, []);

  useEffect(() => {
    if (articleId) {
      setFilters((prev) => ({ ...prev, id: articleId, page: 1 }));
    } else {
      setFilters((prev) => {
        const next = { ...prev };
        delete next.id;
        return next;
      });
    }
  }, [articleId]);

  useEffect(() => {
    if (!yearRangeLoaded) return;
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
  }, [filters, yearRangeLoaded]);

  const handlePageChange = (newPage: number) => {
    setFilters((prev) => ({ ...prev, page: newPage }));
  };

  const handleFilterChange = (
    key: keyof ArticleFilters,
    value: string | number | boolean | undefined,
  ) => {
    setFilters((prev) => ({ ...prev, [key]: value, page: 1 }));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Makaleler</h1>
          <p className="mt-1 text-slate-500">
            {filters.id ? `${data?.total || 0} sonuç` : `Toplam ${data?.total.toLocaleString() || 0} makale`}
          </p>
        </div>
        {!filters.id && (
          <Button variant="secondary" onClick={() => setShowFilters(!showFilters)}>
            <Filter className="h-4 w-4 mr-2" />
            Filtreler
          </Button>
        )}
      </div>

      {/* Filters */}
      {showFilters && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col lg:flex-row gap-6">
              {/* Sol yarı — 3 dropdown */}
              <div className="flex-1 flex flex-col sm:flex-row gap-3">
                <div className="flex-1">
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
                <div className="flex-1">
                  <label className="block text-sm font-medium text-slate-700 mb-1">Açık Erişim</label>
                  <select
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    value={filters.open_access === undefined ? '' : String(filters.open_access)}
                    onChange={(e) =>
                      handleFilterChange(
                        'open_access',
                        e.target.value === '' ? undefined : e.target.value === 'true',
                      )
                    }
                  >
                    <option value="">Tümü</option>
                    <option value="true">Evet</option>
                    <option value="false">Hayır</option>
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-sm font-medium text-slate-700 mb-1">Sıralama</label>
                  <select
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    value={`${filters.sort_by}-${filters.sort_order}`}
                    onChange={(e) => {
                      const [sortBy, sortOrder] = e.target.value.split('-');
                      setFilters((prev) => ({
                        ...prev,
                        sort_by: sortBy,
                        sort_order: sortOrder as 'asc' | 'desc',
                      }));
                    }}
                  >
                    <option value="citation_count-desc">Atıf Sayısı (En Yüksek)</option>
                    <option value="publication_year-desc">Yıl (Yeni → Eski)</option>
                    <option value="publication_year-asc">Yıl (Eski → Yeni)</option>
                    <option value="title-asc">Başlık (A → Z)</option>
                    <option value="title-desc">Başlık (Z → A)</option>
                    <option value="citation_percentile-desc">Atıf Yüzdeliği (En Yüksek)</option>
                    <option value="fwci-desc">FWCI (En Yüksek)</option>
                  </select>
                </div>
              </div>

              {/* Sağ yarı — yıl aralığı slider + no-date toggle */}
              {yearRange && (
                <div className="flex-1 flex flex-col justify-center gap-3">
                  <YearRangeSlider
                    label="Yayın Yılı Aralığı"
                    min={yearRange.min}
                    max={yearRange.max}
                    value={[filters.year_min ?? yearRange.min, filters.year_max ?? yearRange.max]}
                    onChange={([min, max]) =>
                      setFilters((prev) => ({ ...prev, year_min: min, year_max: max, page: 1 }))
                    }
                  />
                  <label className="flex items-center gap-2 cursor-pointer select-none w-fit">
                    <input
                      type="checkbox"
                      className="w-4 h-4 rounded border-slate-300 text-indigo-600 accent-indigo-600 cursor-pointer"
                      checked={filters.include_no_date ?? true}
                      onChange={(e) => handleFilterChange('include_no_date', e.target.checked)}
                    />
                    <span className="text-sm text-slate-600">Tarihi olmayan makaleleri dahil et</span>
                  </label>
                </div>
              )}
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
                  <div className="h-5 bg-slate-200 rounded w-3/4" />
                  <div className="h-4 bg-slate-100 rounded w-1/2" />
                  <div className="h-20 bg-slate-50 rounded" />
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
          data?.items.map((article) => <ArticleCard key={article.id} article={article} />)
        )}
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && !filters.id && (
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
    <Suspense fallback={<div className="p-8 text-center">Yükleniyor...</div>}>
      <ArticlesContent />
    </Suspense>
  );
}
