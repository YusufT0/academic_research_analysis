'use client';

import { Suspense, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Users,
  FileText,
  Star,
  Activity,
  Briefcase,
  TrendingUp,
  ChevronLeft,
  ChevronRight,
  Building2,
  Tag,
  AtSign,
  Info
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { getAuthorProfile, getAuthorArticles } from '@/lib/api';
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend
} from 'recharts';

function AuthorProfileContent() {
  const router = useRouter();
  const params = useParams();
  const rawName = params?.name as string;
  const name = rawName ? decodeURIComponent(rawName) : '';

  const [authorProfile, setAuthorProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [affPage, setAffPage] = useState(1);

  // Articles state
  const [articlesData, setArticlesData] = useState<any>(null);
  const [articlesPage, setArticlesPage] = useState(1);
  const [articlesLoading, setArticlesLoading] = useState(false);

  useEffect(() => {
    async function fetchProfile() {
      if (!name) return;
      setLoading(true);
      try {
        const result = await getAuthorProfile(name);
        setAuthorProfile(result);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchProfile();
  }, [name]);

  useEffect(() => {
    async function fetchArticles() {
      if (!name) return;
      setArticlesLoading(true);
      try {
        const result = await getAuthorArticles(name, articlesPage, 15);
        setArticlesData(result);
      } catch (err) {
        console.error("Failed to fetch author articles", err);
      } finally {
        setArticlesLoading(false);
      }
    }
    fetchArticles();
  }, [name, articlesPage]);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse p-4">
        <div className="h-24 bg-slate-100 rounded-xl w-3/4 max-w-2xl" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-32 bg-slate-100 rounded-xl" />)}
        </div>
        <div className="h-96 bg-slate-100 rounded-xl mt-6" />
      </div>
    );
  }

  if (!authorProfile) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Users className="h-16 w-16 text-slate-200 mb-4" />
        <h2 className="text-2xl font-bold text-slate-700">Yazar Bulunamadı</h2>
        <p className="text-slate-500 mt-2 max-w-md">"{name}" isimli yazar veritabanımızda bulunmamaktadır.</p>
        <Button className="mt-6" variant="secondary" onClick={() => router.back()}>
          Geri Dön
        </Button>
      </div>
    );
  }

  const dbStats = authorProfile.db_stats || {};
  const metrics = authorProfile.openalex_metrics || {};
  const articles = authorProfile.articles || [];

  const AFFILIATIONS_PER_PAGE = 10;
  const totalAffs = metrics.affiliations?.length || 0;
  const totalAffPages = Math.ceil(totalAffs / AFFILIATIONS_PER_PAGE);
  const paginatedAffiliations = metrics.affiliations?.slice((affPage - 1) * AFFILIATIONS_PER_PAGE, affPage * AFFILIATIONS_PER_PAGE) || [];

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header */}
      <div className="flex items-center gap-4 border-b border-slate-200 pb-5">
        <Button variant="secondary" size="sm" onClick={() => router.back()} className="rounded-full w-10 h-10 p-0 flex items-center justify-center">
          <ChevronLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold text-slate-900">{name}</h1>
          <p className="text-slate-500 flex items-center gap-2 mt-1">
            <Users className="h-4 w-4" /> Yazar Profili
            {metrics?.ids?.orcid && (
              <a href={metrics.ids.orcid} target="_blank" rel="noreferrer" className="text-indigo-500 hover:text-indigo-700 transition-colors ml-2 text-xs font-bold flex items-center gap-1 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100 shadow-sm">
                <AtSign className="h-3 w-3" /> ORCID Git
              </a>
            )}
            {metrics?.ids?.scopus && (
              <a href={metrics.ids.scopus} target="_blank" rel="noreferrer" className="text-orange-600 hover:text-orange-800 transition-colors ml-1 text-xs font-bold flex items-center gap-1 bg-orange-50 px-2 py-0.5 rounded-full border border-orange-100 shadow-sm">
                <AtSign className="h-3 w-3" /> Scopus
              </a>
            )}
          </p>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-indigo-50 to-white border-indigo-100 shadow-sm">
          <CardContent className="p-6 relative overflow-hidden">
            <div className="absolute -right-4 -top-4 opacity-[0.03]">
                <FileText className="w-32 h-32" />
            </div>
            <div className="flex items-center gap-3 relative z-10">
              <div className="p-3 bg-indigo-100 text-indigo-600 rounded-xl shadow-sm">
                <FileText className="h-6 w-6" />
              </div>
              <div>
                <p className="text-xs font-bold text-indigo-400 uppercase tracking-wider">DB Makale Sayısı</p>
                <h3 className="text-3xl font-bold text-indigo-950 mt-1">{dbStats.article_count}</h3>
              </div>
            </div>
            {metrics.works_count > 0 && (
                <p className="text-[10px] font-semibold text-slate-500 mt-4 pt-3 border-t border-indigo-100 flex items-center gap-1 uppercase tracking-wider">
                    <Info className="h-3 w-3 text-indigo-400" /> OpenAlex Toplam: {metrics.works_count.toLocaleString()}
                </p>
            )}
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-emerald-50 to-white border-emerald-100 shadow-sm">
          <CardContent className="p-6 relative overflow-hidden">
             <div className="absolute -right-4 -top-4 opacity-[0.03]">
                <Star className="w-32 h-32" />
            </div>
            <div className="flex items-center gap-3 relative z-10">
              <div className="p-3 bg-emerald-100 text-emerald-600 rounded-xl shadow-sm">
                <Star className="h-6 w-6 fill-current" />
              </div>
              <div>
                <p className="text-xs font-bold text-emerald-400 uppercase tracking-wider">Toplam Atıf</p>
                <h3 className="text-3xl font-bold text-emerald-950 mt-1">{metrics.cited_by_count?.toLocaleString() || 0}</h3>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-amber-50 to-white border-amber-100 shadow-sm">
          <CardContent className="p-6 relative overflow-hidden">
             <div className="absolute -right-4 -top-4 opacity-[0.03]">
                <TrendingUp className="w-32 h-32" />
            </div>
            <div className="flex items-center gap-3 relative z-10">
              <div className="p-3 bg-amber-100 text-amber-600 rounded-xl shadow-sm">
                <TrendingUp className="h-6 w-6" />
              </div>
              <div>
                <p className="text-xs font-bold text-amber-400 uppercase tracking-wider">H-Index</p>
                <h3 className="text-3xl font-bold text-amber-950 mt-1">{metrics.h_index || '-'}</h3>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-fuchsia-50 to-white border-fuchsia-100 shadow-sm">
          <CardContent className="p-6 relative overflow-hidden">
             <div className="absolute -right-4 -top-4 opacity-[0.03]">
                <Activity className="w-32 h-32" />
            </div>
            <div className="flex items-center gap-3 relative z-10">
              <div className="p-3 bg-fuchsia-100 text-fuchsia-600 rounded-xl shadow-sm">
                <Activity className="h-6 w-6" />
              </div>
              <div>
                <p className="text-xs font-bold text-fuchsia-400 uppercase tracking-wider">i10-Index</p>
                <h3 className="text-3xl font-bold text-fuchsia-950 mt-1">{metrics.i10_index || '-'}</h3>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {metrics.counts_by_year && metrics.counts_by_year.length > 0 && (
        <Card className="shadow-sm border-slate-200">
            <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/50">
              <CardTitle className="text-xs font-bold text-slate-600 uppercase tracking-widest flex items-center gap-2">
                <TrendingUp className="h-4 w-4" /> Yıllara Göre Yayın ve Atıf İstatİstİklerİ (OpenAlex)
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-6 h-80">
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={[...metrics.counts_by_year].reverse()}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                        <XAxis dataKey="year" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748B' }} dy={10} />
                        <YAxis yAxisId="left" orientation="left" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748B' }} />
                        <YAxis yAxisId="right" orientation="right" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#64748B' }} />
                        <Tooltip 
                            contentStyle={{ borderRadius: '8px', border: '1px solid #E2E8F0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                            cursor={{ fill: '#F1F5F9' }}
                        />
                        <Legend wrapperStyle={{ paddingTop: '20px' }} />
                        <Bar yAxisId="left" name="Makale Sayısı" dataKey="works_count" fill="#6366F1" radius={[4, 4, 0, 0]} maxBarSize={40} />
                        <Line yAxisId="right" name="Atıf Sayısı" type="monotone" dataKey="cited_by_count" stroke="#10B981" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
                    </ComposedChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Sol Kolon: Kurumlar ve Ağ (3/12 width on large, 4/12 width on xl) */}
        <div className="lg:col-span-4 xl:col-span-3 space-y-6">
            {totalAffs > 0 && (
                <Card className="shadow-sm border-slate-200">
                <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/50">
                  <CardTitle className="text-xs font-bold text-slate-600 uppercase tracking-widest flex items-center gap-2">
                    <Building2 className="h-4 w-4" /> Kurum Bİlgİlerİ (OpenAlex) <Badge className="ml-1 px-1.5 py-0 bg-slate-200 text-slate-700">{totalAffs}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-4 space-y-5">
                  {paginatedAffiliations.map((aff: any, idx: number) => (
                    <div key={idx} className="flex gap-3 items-start relative before:absolute before:left-[11px] before:top-8 before:bottom-[-20px] before:w-px before:bg-slate-200 last:before:hidden">
                      <div className="mt-0.5 p-1.5 bg-slate-100 text-slate-500 rounded-full border border-slate-200 z-10">
                        <Briefcase className="h-3 w-3" />
                      </div>
                      <div className="flex-1 pb-1">
                        <p className="text-sm font-semibold text-slate-800 leading-tight">{aff.name}</p>
                        <p className="text-xs font-medium text-slate-500 mt-1">
                          {aff.years?.join(', ') || 'Bilinmiyor'} 
                          {aff.country_code && <span className="text-slate-400 font-normal"> ({aff.country_code})</span>}
                        </p>
                      </div>
                    </div>
                  ))}

                  {totalAffPages > 1 && (
                      <div className="flex items-center justify-between mt-6 pt-4 border-t border-slate-100">
                          <span className="text-xs text-slate-500">Sayfa {affPage} / {totalAffPages}</span>
                          <div className="flex gap-1.5">
                              <Button variant="secondary" size="sm" className="h-7 cursor-pointer" onClick={() => setAffPage(p => Math.max(1, p - 1))} disabled={affPage === 1}>
                                  <ChevronLeft className="h-3 w-3" />
                              </Button>
                              <Button variant="secondary" size="sm" className="h-7 cursor-pointer" onClick={() => setAffPage(p => Math.min(totalAffPages, p + 1))} disabled={affPage === totalAffPages}>
                                  <ChevronRight className="h-3 w-3" />
                              </Button>
                          </div>
                      </div>
                  )}
                </CardContent>
              </Card>
            )}

            <Card className="shadow-sm border-slate-200">
              <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/50">
                <CardTitle className="text-xs font-bold text-slate-600 uppercase tracking-widest flex items-center gap-2">
                  <Users className="h-4 w-4" /> Sık Ortak Yazarlar (DB)
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-4 space-y-2">
                {dbStats.co_authors?.length > 0 ? dbStats.co_authors.map((ca: any, idx: number) => (
                    <Link key={idx} href={`/authors/${encodeURIComponent(ca.name)}`} className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 transition-colors border border-transparent hover:border-slate-200 group">
                        <span className="text-sm font-semibold text-slate-700 group-hover:text-indigo-600 transition-colors line-clamp-1 flex-1 pr-2">{ca.name}</span>
                        <Badge variant="default" className="bg-slate-100 text-slate-600 font-bold border-slate-200 shrink-0">{ca.count}</Badge>
                    </Link>
                )) : (
                    <p className="text-sm text-slate-500 py-2 text-center">Ortak yazar bulunamadı.</p>
                )}
              </CardContent>
            </Card>

            {metrics.topics && metrics.topics.length > 0 && (
              <Card className="shadow-sm border-slate-200">
                <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/50">
                  <CardTitle className="text-xs font-bold text-slate-600 uppercase tracking-widest flex items-center gap-2">
                    <Tag className="h-4 w-4" /> Akademİk Konular (OpenAlex)
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-4">
                    <div className="flex flex-wrap gap-2">
                        {metrics.topics.map((t: string, i: number) => (
                            <Badge key={i} variant="default" className="bg-slate-50 text-slate-700 border-slate-200 py-1 px-2 font-medium">
                                {t}
                            </Badge>
                        ))}
                    </div>
                </CardContent>
              </Card>
            )}
        </div>

        {/* Sağ Kolon: Makaleler (8/12 width on large, 9/12 width on xl) */}
        <div className="lg:col-span-8 xl:col-span-9 space-y-6">
            <Card className="h-full shadow-sm border-slate-200 overflow-hidden flex flex-col relative">
              <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/80">
                <CardTitle className="text-sm font-bold text-slate-600 uppercase tracking-widest flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4" /> Sistemdekİ Makalelerİ ({articlesData?.total || 0})
                  </div>
                  {articlesData && articlesData.total_pages > 1 && (
                      <div className="flex items-center gap-2">
                          <Button 
                              variant="secondary" 
                              size="sm" 
                              className="h-7 text-xs px-2" 
                              onClick={() => setArticlesPage(p => Math.max(1, p - 1))} 
                              disabled={articlesPage === 1 || articlesLoading}
                          >
                              <ChevronLeft className="h-3 w-3 mr-1" /> Önceki
                          </Button>
                          <span className="text-xs font-medium text-slate-500 min-w-16 text-center">
                              {articlesPage} / {articlesData.total_pages}
                          </span>
                          <Button 
                              variant="secondary" 
                              size="sm" 
                              className="h-7 text-xs px-2" 
                              onClick={() => setArticlesPage(p => Math.min(articlesData.total_pages, p + 1))} 
                              disabled={!articlesData.has_next || articlesLoading}
                          >
                              Sonraki <ChevronRight className="h-3 w-3 ml-1" />
                          </Button>
                      </div>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className={`pt-0 p-0 flex-1 overflow-y-auto divide-y divide-slate-100 transition-opacity duration-200 ${articlesLoading ? 'opacity-50' : 'opacity-100'}`}>
                  {articlesData?.items?.length > 0 ? articlesData.items.map((art: any) => (
                      <div key={art.id} className="p-5 hover:bg-indigo-50/40 transition-colors group">
                          <Link href={`/articles?article_id=${art.id}`} className="block">
                              <h4 className="font-bold text-slate-800 text-base leading-snug group-hover:text-indigo-700 transition-colors">
                                  {art.title}
                              </h4>
                              <div className="flex flex-wrap items-center gap-3 mt-3">
                                <Badge variant="default" className="bg-indigo-50 text-indigo-700 border border-indigo-100 font-semibold shadow-sm">
                                    {art.journal_name}
                                </Badge>
                                {art.publication_year && (
                                    <span className="text-xs font-bold text-slate-400 bg-slate-50 px-2 py-0.5 rounded border border-slate-100">
                                      {art.publication_year}
                                    </span>
                                )}
                                {art.citation_count > 0 && (
                                    <span className="text-xs font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded flex items-center gap-1 border border-amber-200 shadow-sm">
                                        <Star className="h-3 w-3 fill-amber-500 text-amber-500" /> {art.citation_count} Atıf
                                    </span>
                                )}
                              </div>
                          </Link>
                      </div>
                  )) : (
                      <div className="p-12 text-center max-w-sm mx-auto">
                          <FileText className="h-12 w-12 text-slate-200 mx-auto mb-3" />
                          <h4 className="font-semibold text-slate-700">Kayıtlı makale yok</h4>
                          <p className="text-sm text-slate-500 mt-1">Bu yazarın sistemimizde henüz detaylı olarak kaydedilmiş bir makalesi görünmüyor.</p>
                      </div>
                  )}
              </CardContent>
            </Card>
        </div>
      </div>
    </div>
  );
}

export default function AuthorProfilePage() {
  return (
    <Suspense fallback={<div className="p-8 text-center animate-pulse">Yükleniyor...</div>}>
      <AuthorProfileContent />
    </Suspense>
  );
}
