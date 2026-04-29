'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
  ScatterChart, Scatter, ZAxis,
} from 'recharts';
import { Brain, TrendingUp, Tags, Waypoints, FileText, ExternalLink } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import type {
  NlpSearchResponse,
  NlpBarChartData,
  NlpPieChartData,
  NlpScatterPoint,
} from '@/lib/types';

const PIE_COLORS = [
  '#10b981', '#14b8a6', '#06b6d4', '#3b82f6', '#6366f1',
  '#8b5cf6', '#a855f7', '#ec4899', '#f59e0b', '#ef4444',
  '#64748b',
];

interface AiAnalysisSectionProps {
  searchResult: NlpSearchResponse;
  barData: NlpBarChartData | null;
  pieData: NlpPieChartData | null;
  scatterData: NlpScatterPoint[] | null;
  barLoading: boolean;
  pieLoading: boolean;
  scatterLoading: boolean;
}

function ChartSkeleton() {
  return (
    <div className="animate-pulse flex flex-col items-center justify-center h-56">
      <div className="h-40 w-full bg-slate-100 rounded-lg" />
      <div className="h-3 w-1/2 bg-slate-100 rounded mt-3" />
    </div>
  );
}

function ClusterInfoCard({ data }: { data: NlpSearchResponse }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-violet-600" />
          <CardTitle>AI Cluster Bilgisi</CardTitle>
        </div>
        <CardDescription>Sorgunuza en yakın konu kümesi</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-500">Cluster:</span>
            <Badge variant="info">
              {data.cluster_label ?? `#${data.cluster_id}`}
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 bg-violet-50 rounded-lg text-center">
              <p className="text-2xl font-bold text-violet-700">
                {(data.similarity_score * 100).toFixed(1)}%
              </p>
              <p className="text-xs text-violet-500 mt-1">Benzerlik Skoru</p>
            </div>
            <div className="p-3 bg-emerald-50 rounded-lg text-center">
              <p className="text-2xl font-bold text-emerald-700">
                {data.total_in_cluster ?? data.articles.length}
              </p>
              <p className="text-xs text-emerald-500 mt-1">Kümede Makale</p>
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 text-xs text-slate-400">
            Model: {data.model_version}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function YearlyBarChart({ data }: { data: NlpBarChartData }) {
  const chartData = useMemo(() => {
    return Object.entries(data)
      .map(([dateStr, count]) => {
        const d = new Date(dateStr);
        const label = isNaN(d.getTime()) ? dateStr : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
        return { date: label, count };
      })
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [data]);

  if (chartData.length === 0) {
    return <p className="text-sm text-slate-400 text-center py-8">Tarih verisi bulunamadı</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" height={60} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0' }}
          formatter={(value) => [`${value} makale`, 'Sayı']}
        />
        <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function TopicPieChart({ data }: { data: NlpPieChartData }) {
  const chartData = useMemo(() => {
    return Object.entries(data)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
  }, [data]);

  if (chartData.length === 0) {
    return <p className="text-sm text-slate-400 text-center py-8">Konu verisi bulunamadı</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={85}
          paddingAngle={2}
          dataKey="value"
          label={({ name, percent }) => { const n = String(name ?? ''); return `${n.length > 12 ? n.slice(0, 12) + '…' : n} (${((percent ?? 0) * 100).toFixed(0)}%)`; }}
          labelLine={{ strokeWidth: 1 }}
        >
          {chartData.map((_, i) => (
            <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(value) => [`${value} makale`, 'Sayı']} />
        <Legend
          layout="horizontal"
          verticalAlign="bottom"
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

function EmbeddingScatter({ data }: { data: NlpScatterPoint[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-slate-400 text-center py-8">Scatter verisi bulunamadı</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="x" type="number" tick={{ fontSize: 10 }} name="X" />
        <YAxis dataKey="y" type="number" tick={{ fontSize: 10 }} name="Y" />
        <ZAxis range={[30, 30]} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0' }}
          formatter={(value) => Number(value).toFixed(3)}
        />
        <Scatter data={data} fill="#6366f1" fillOpacity={0.7} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function NlpArticleRow({ article }: { article: NlpSearchResponse['articles'][number] }) {
  return (
    <div className="flex items-start justify-between gap-3 p-4 rounded-lg border border-slate-100 hover:border-emerald-200 hover:bg-emerald-50/30 transition-colors">
      <div className="flex-1 min-w-0">
        <Link href={`/articles?article_id=${article.id}`}>
          <h4 className="font-medium text-slate-900 leading-snug hover:text-emerald-700 transition-colors cursor-pointer line-clamp-2">
            {article.title}
          </h4>
        </Link>
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          {article.cluster_id != null && (
            <Badge variant="info">Cluster #{article.cluster_id}</Badge>
          )}
          {article.similarity_score != null && (
            <span className="text-xs text-slate-400">
              Benzerlik: {(article.similarity_score * 100).toFixed(1)}%
            </span>
          )}
        </div>
        {article.abstract && (
          <p className="text-sm text-slate-500 mt-2 line-clamp-2">{article.abstract}</p>
        )}
      </div>
      <Link
        href={`/articles?article_id=${article.id}`}
        className="flex-shrink-0 p-1.5 text-slate-400 hover:text-emerald-600 transition-colors"
      >
        <ExternalLink className="h-4 w-4" />
      </Link>
    </div>
  );
}

export default function AiAnalysisSection({
  searchResult,
  barData,
  pieData,
  scatterData,
  barLoading,
  pieLoading,
  scatterLoading,
}: AiAnalysisSectionProps) {
  return (
    <div className="space-y-6 mt-6">
      {/* Section Heading */}
      <div className="flex items-center gap-3">
        <div className="h-8 w-1 bg-gradient-to-b from-violet-500 to-emerald-500 rounded-full" />
        <div>
          <h2 className="text-xl font-bold text-slate-900">AI Trend Analizi</h2>
          <p className="text-sm text-slate-500">
            &ldquo;{searchResult.query}&rdquo; sorgusu icin NLP analiz sonuclari
          </p>
        </div>
      </div>

      {/* 2x2 Grid: Cluster Info + 3 Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ClusterInfoCard data={searchResult} />

        {/* Bar Chart */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-emerald-600" />
              <CardTitle>Yayın Trendi</CardTitle>
            </div>
            <CardDescription>Tarih bazlı makale dağılımı</CardDescription>
          </CardHeader>
          <CardContent>
            {barLoading ? <ChartSkeleton /> : barData ? <YearlyBarChart data={barData} /> : <p className="text-sm text-slate-400 text-center py-8">Veri yüklenemedi</p>}
          </CardContent>
        </Card>

        {/* Pie Chart */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Tags className="h-5 w-5 text-teal-600" />
              <CardTitle>Konu Dağılımı</CardTitle>
            </div>
            <CardDescription>Anahtar kelime küme dağılımı</CardDescription>
          </CardHeader>
          <CardContent>
            {pieLoading ? <ChartSkeleton /> : pieData ? <TopicPieChart data={pieData} /> : <p className="text-sm text-slate-400 text-center py-8">Veri yüklenemedi</p>}
          </CardContent>
        </Card>

        {/* Scatter Plot */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Waypoints className="h-5 w-5 text-indigo-600" />
              <CardTitle>Embedding Haritası</CardTitle>
            </div>
            <CardDescription>Anahtar kelimelerin 2D UMAP projeksiyonu</CardDescription>
          </CardHeader>
          <CardContent>
            {scatterLoading ? <ChartSkeleton /> : scatterData ? <EmbeddingScatter data={scatterData} /> : <p className="text-sm text-slate-400 text-center py-8">Veri yüklenemedi</p>}
          </CardContent>
        </Card>
      </div>

      {/* Matched Articles */}
      {searchResult.articles.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-emerald-600" />
                <CardTitle>Eşleşen Makaleler</CardTitle>
              </div>
              <Badge variant="success">{searchResult.articles.length} sonuç</Badge>
            </div>
            <CardDescription>NLP modelinin bulduğu en benzer makaleler</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {searchResult.articles.map((article) => (
                <NlpArticleRow key={article.id} article={article} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
