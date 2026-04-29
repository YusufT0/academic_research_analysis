'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft, ExternalLink, Unlock, Star, TrendingUp, Target,
  Users, FileText, Calendar, Tag, Hash, Building2, Link2, BookOpen, Info,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { getArticle } from '@/lib/api';
import type { Article } from '@/lib/types';

function getFullUrl(url: string, sourceWebsite: string): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (sourceWebsite === 'ieeexplore') return `https://ieeexplore.ieee.org${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'sciencedirect') return `https://www.sciencedirect.com${url.startsWith('/') ? '' : '/'}${url}`;
  if (sourceWebsite === 'acm') return `https://dl.acm.org${url.startsWith('/') ? '' : '/'}${url}`;
  return url;
}

function MetaItem({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
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

export default function ArticleDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchArticle() {
      try {
        const data = await getArticle(id);
        setArticle(data);
      } catch {
        setError('Makale bulunamadı.');
      } finally {
        setLoading(false);
      }
    }
    if (id) fetchArticle();
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-6 max-w-4xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-200 rounded w-3/4" />
          <div className="h-4 bg-slate-100 rounded w-1/2" />
          <div className="h-40 bg-slate-100 rounded" />
          <div className="h-40 bg-slate-100 rounded" />
        </div>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="text-center py-20">
        <p className="text-slate-500 mb-4">{error || 'Makale bulunamadı.'}</p>
        <Button variant="secondary" onClick={() => router.push('/articles')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Makaleler Listesine Dön
        </Button>
      </div>
    );
  }

  const sourceLabel =
    article.source_website === 'ieeexplore' ? 'IEEE' :
    article.source_website === 'acm' ? 'ACM' : 'ScienceDirect';
  const sourceBadgeVariant: 'info' | 'warning' | 'success' =
    article.source_website === 'ieeexplore' ? 'info' :
    article.source_website === 'acm' ? 'warning' : 'success';

  const fullUrl = getFullUrl(article.url, article.source_website);

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Back + Actions */}
      <div className="flex items-center justify-between">
        <Button variant="secondary" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Geri
        </Button>
        {fullUrl && (
          <a
            href={fullUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            Kaynakta Aç
          </a>
        )}
      </div>

      {/* Title Card */}
      <Card>
        <CardContent className="pt-6">
          <h1 className="text-2xl font-bold text-slate-900 leading-tight mb-3">{article.title}</h1>

          <div className="flex flex-wrap items-center gap-2 mb-3">
            <Link
              href={`/journals?journal_id=${article.journal_id}`}
              className="text-sm text-slate-600 font-medium hover:text-emerald-700 hover:underline cursor-pointer transition-colors"
            >
              {article.journal_name}
            </Link>
            {article.publication_year && <Badge variant="default">{article.publication_year}</Badge>}
            <Badge variant={sourceBadgeVariant}>{sourceLabel}</Badge>
            {article.article_type && (
              <span className="text-xs text-slate-400 italic">{article.article_type}</span>
            )}
            {article.open_access && (
              <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200">
                <Unlock className="h-3.5 w-3.5" />
                <span>Açık Erişim</span>
              </div>
            )}
          </div>

          {article.citation_count > 0 && (
            <div className="inline-flex items-center gap-4 text-xs font-medium bg-gradient-to-r from-purple-50 to-indigo-50 text-indigo-900 px-3 py-2 rounded-md border border-indigo-100 mb-3">
              <div className="flex items-center gap-1.5 font-bold">
                <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                <span>{article.citation_count} Atıf</span>
              </div>
              {article.citation_percentile && (
                <div className="flex items-center gap-1.5 border-l border-indigo-200 pl-4">
                  <TrendingUp className="h-3.5 w-3.5 text-indigo-500" />
                  <span>%{article.citation_percentile} Dilim</span>
                </div>
              )}
              {article.fwci != null && (
                <div className="flex items-center gap-1.5 border-l border-indigo-200 pl-4">
                  <Target className="h-3.5 w-3.5 text-indigo-500" />
                  <span>FWCI: {article.fwci.toFixed(2)}</span>
                </div>
              )}
            </div>
          )}

          {article.authors.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {article.authors.map((author, i) => (
                <Link
                  key={i}
                  href={`/authors/${encodeURIComponent(author)}`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-full cursor-pointer transition-all hover:bg-emerald-100 hover:border-emerald-400 hover:shadow-[0_0_8px_rgba(16,185,129,0.35)]"
                >
                  <span className="text-[10px] text-emerald-500 font-mono">{i + 1}</span>
                  {author}
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Abstract */}
      {article.abstract && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-blue-600" />
              Abstract
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="relative">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-blue-400 to-blue-200 rounded-full" />
              <p className="pl-4 text-sm text-slate-700 leading-relaxed">{article.abstract}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Introduction */}
      {article.introduction && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BookOpen className="h-4 w-4 text-violet-600" />
              Giriş
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="relative">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-violet-400 to-violet-200 rounded-full" />
              <p className="pl-4 text-sm text-slate-700 leading-relaxed">{article.introduction}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Keywords */}
      {article.keywords.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Tag className="h-4 w-4 text-teal-600" />
              Anahtar Kelimeler
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {article.keywords.map((kw, i) => (
                <span
                  key={i}
                  className="inline-block px-3 py-1 bg-teal-50 text-teal-800 text-xs font-medium rounded-full border border-teal-200"
                >
                  {kw}
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Metadata */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Hash className="h-4 w-4 text-slate-500" />
            Metadata
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-10">
            <MetaItem icon={<Hash className="h-3.5 w-3.5" />} label="DOI" value={
              article.doi ? (
                <a href={`https://doi.org/${article.doi}`} target="_blank" rel="noopener noreferrer"
                  className="text-indigo-600 hover:text-indigo-800 underline underline-offset-2 font-mono text-xs break-all">
                  {article.doi}
                </a>
              ) : null
            } />
            <MetaItem icon={<Calendar className="h-3.5 w-3.5" />} label="Yayın Tarihi" value={article.publication_date} />
            <MetaItem icon={<BookOpen className="h-3.5 w-3.5" />} label="Dergi" value={article.journal_name} />
            <MetaItem icon={<FileText className="h-3.5 w-3.5" />} label="Sayfalar" value={article.pages} />
            <MetaItem icon={<Building2 className="h-3.5 w-3.5" />} label="Yayıncı" value={article.publisher} />
            <MetaItem icon={<Info className="h-3.5 w-3.5" />} label="Makale Türü" value={article.article_type} />
            <MetaItem icon={<Hash className="h-3.5 w-3.5" />} label="Sayı No" value={article.issue_number} />
            <MetaItem icon={<Unlock className="h-3.5 w-3.5" />} label="Açık Erişim" value={
              article.open_access
                ? <span className="text-emerald-600 font-semibold">Evet</span>
                : <span className="text-slate-500">Hayır</span>
            } />
            <MetaItem icon={<Star className="h-3.5 w-3.5" />} label="Atıf Sayısı"
              value={article.citation_count > 0 ? article.citation_count.toLocaleString() : null} />
            <MetaItem icon={<TrendingUp className="h-3.5 w-3.5" />} label="Atıf Yüzdeliği"
              value={article.citation_percentile ? `%${article.citation_percentile}` : null} />
            <MetaItem icon={<Target className="h-3.5 w-3.5" />} label="FWCI"
              value={article.fwci != null ? article.fwci.toFixed(3) : null} />
            <MetaItem icon={<Calendar className="h-3.5 w-3.5" />} label="Son Atıf Güncelleme" value={
              article.last_citation_update_date
                ? new Date(article.last_citation_update_date).toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
                : null
            } />
            <MetaItem icon={<Link2 className="h-3.5 w-3.5" />} label="OpenAlex ID" value={
              article.openalex_id
                ? <span className="font-mono text-xs text-slate-600">{article.openalex_id}</span>
                : null
            } />
            <MetaItem icon={<Info className="h-3.5 w-3.5" />} label="OpenAlex İndeksli" value={
              article.is_openalex_indexed !== undefined
                ? article.is_openalex_indexed
                  ? <span className="text-emerald-600 font-semibold">Evet</span>
                  : <span className="text-slate-400">Hayır</span>
                : null
            } />
            <MetaItem icon={<Calendar className="h-3.5 w-3.5" />} label="Sisteme Eklenme" value={
              article.created_at
                ? new Date(article.created_at).toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
                : null
            } />
            <MetaItem icon={<Calendar className="h-3.5 w-3.5" />} label="Son Güncelleme" value={
              article.updated_at
                ? new Date(article.updated_at).toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
                : null
            } />
          </div>
        </CardContent>
      </Card>

      {/* References */}
      {article.references && article.references.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4 text-slate-500" />
              Referanslar ({article.references.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2 list-decimal list-inside">
              {article.references.map((ref, i) => (
                <li key={i} className="text-sm text-slate-600 leading-relaxed">{ref}</li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
