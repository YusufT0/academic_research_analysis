'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/Card';
import { Medal, Star, Target, TrendingUp, Presentation } from 'lucide-react';
import type { CitationStats } from '@/lib/types';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const SORT_ORDER: Record<string, number> = {
  "0": 0,
  "1": 1,
  "5": 2,
  "20": 3,
  "50": 4,
  "100+": 5,
};

const DISTRIBUTION_LABELS: Record<string, string> = {
  "0": "Atıf Almayan (0)",
  "1": "Düşük (1-4)",
  "5": "Orta (5-19)",
  "20": "Yüksek (20-49)",
  "50": "Çok Yüksek (50-99)",
  "100+": "Zirve (100+)"
};

export function CitationsSection({ data }: { data: CitationStats }) {
  // Format and sort data in correct order
  const allDistributionData = [...data.citation_distribution]
    .sort((a, b) => (SORT_ORDER[a._id.toString()] ?? 99) - (SORT_ORDER[b._id.toString()] ?? 99))
    .map((d) => ({
      name: DISTRIBUTION_LABELS[d._id.toString()] || `${d._id} Atıf`,
      amount: d.count,
    }));

  const [hiddenItems, setHiddenItems] = useState<Set<string>>(new Set());

  const distributionData = allDistributionData.filter((d) => !hiddenItems.has(d.name));

  function toggleItem(name: string) {
    setHiddenItems((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  const yearlyData = data.citations_by_pub_year.map(d => ({
    year: d._id.toString(),
    citations: d.total_citations,
    articles: d.article_count
  }));

  return (
    <div className="space-y-6 mt-8 border-t pt-8 border-slate-200">
      <div className="flex items-center gap-2 mb-4">
        <Star className="h-6 w-6 text-yellow-500" />
        <h2 className="text-2xl font-bold text-slate-900">Atıf Yoğunlukları ve Etki Analizi</h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Yıllara Göre Toplam Atıf (Bar Chart) */}
        <Card>
          <CardHeader>
             <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-indigo-600" />
              <CardTitle>Yıllara Göre Toplam Atıf Yoğunluğu</CardTitle>
            </div>
            <CardDescription>Yayın yılına göre toplanan atıflar</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-72 w-full">
              <ResponsiveContainer>
                <BarChart data={yearlyData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="year" />
                  <YAxis yAxisId="left" orientation="left" stroke="#8b5cf6" />
                  <YAxis yAxisId="right" orientation="right" stroke="#3b82f6" hide />
                  <Tooltip />
                  <Legend />
                  <Bar yAxisId="left" dataKey="citations" name="Toplam Atıf" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                  <Bar yAxisId="right" dataKey="articles" name="Makale Sayısı" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Atıf Dağılımı (Pie Chart) */}
        <Card>
          <CardHeader>
             <div className="flex items-center gap-2">
              <Target className="h-5 w-5 text-indigo-600" />
              <CardTitle>Makale Atıf Dağılımı (Gruplu)</CardTitle>
            </div>
            <CardDescription>Hangi aralıkta kaç makale atıf almış?</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-64 w-full">
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={distributionData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    outerRadius={90}
                    innerRadius={40}
                    fill="#8884d8"
                    dataKey="amount"
                    label={({ cx, cy, midAngle = 0, innerRadius, outerRadius, percent }) => {
                      if ((percent || 0) < 0.05) return null;
                      const RADIAN = Math.PI / 180;
                      const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
                      const x = cx + radius * Math.cos(-midAngle * RADIAN);
                      const y = cy + radius * Math.sin(-midAngle * RADIAN);
                      return (
                        <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight={600}>
                          {`${((percent || 0) * 100).toFixed(0)}%`}
                        </text>
                      );
                    }}
                  >
                    {distributionData.map((entry) => {
                      const originalIndex = allDistributionData.findIndex((d) => d.name === entry.name);
                      return (
                        <Cell key={`cell-${entry.name}`} fill={COLORS[originalIndex % COLORS.length]} />
                      );
                    })}
                  </Pie>
                  <Tooltip formatter={(value) => [`${value} makale`, 'Adet']} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {/* Tıklanabilir özel legend */}
            <div className="flex flex-wrap justify-center gap-x-4 gap-y-2 mt-3">
              {allDistributionData.map((entry, index) => {
                const hidden = hiddenItems.has(entry.name);
                return (
                  <button
                    key={entry.name}
                    onClick={() => toggleItem(entry.name)}
                    className="flex items-center gap-1.5 text-xs transition-opacity"
                    style={{ opacity: hidden ? 0.35 : 1 }}
                  >
                    <span
                      className="inline-block w-3 h-3 rounded-sm flex-shrink-0"
                      style={{ backgroundColor: COLORS[index % COLORS.length] }}
                    />
                    <span className={hidden ? 'line-through text-slate-400' : 'text-slate-600'}>
                      {entry.name}
                    </span>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Top 10 Makale */}
        <Card className="lg:col-span-1">
          <CardHeader>
             <div className="flex items-center gap-2">
              <Medal className="h-5 w-5 text-yellow-600" />
              <CardTitle>En Çok Atıf Alan 10 Makale</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2">
              {data.top_cited_articles.map((article, idx) => (
                <div key={article._id} className="flex gap-4 p-3 bg-slate-50 rounded-lg items-center hover:bg-slate-100 transition-colors">
                  <div className="text-xl font-bold text-slate-300 w-6 text-center">{idx + 1}</div>
                  <div className="flex-1 min-w-0">
                    <Link
                      href={`/articles?article_id=${article._id}`}
                      className="text-sm font-semibold text-slate-900 hover:text-indigo-600 truncate block transition-colors"
                      title={article.title}
                    >
                      {article.title}
                    </Link>
                    <p className="text-xs text-slate-500 truncate mt-0.5">
                      {article.authors.slice(0, 2).map((author, i) => (
                        <span key={author}>
                          <Link
                            href={`/authors/${encodeURIComponent(author)}`}
                            className="hover:text-indigo-600 hover:underline transition-colors"
                          >
                            {author}
                          </Link>
                          {i < Math.min(article.authors.length, 2) - 1 ? ', ' : ''}
                        </span>
                      ))}
                      {article.authors.length > 2 ? ' et al.' : ''}
                      {article.publication_year ? ` • ${article.publication_year}` : ''}
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-lg font-bold text-emerald-600">{article.citation_count.toLocaleString()}</p>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wider">Atıf</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Top 10 Dergi H-Index */}
        <Card className="lg:col-span-1">
          <CardHeader>
             <div className="flex items-center gap-2">
              <Presentation className="h-5 w-5 text-purple-600" />
              <CardTitle>Etki Değeri En Yüksek 10 Dergi (H-Index)</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2">
              {data.top_h_index_journals.map((journal, idx) => (
                <div key={journal._id} className="flex gap-4 p-3 bg-slate-50 rounded-lg items-center hover:bg-slate-100 transition-colors">
                  <div className="text-xl font-bold text-slate-300 w-6 text-center">{idx + 1}</div>
                  <div className="flex-1 min-w-0">
                    <Link
                      href={`/journals?journal_id=${journal._id}`}
                      className="text-sm font-semibold text-slate-900 hover:text-indigo-600 truncate block transition-colors"
                      title={journal.name}
                    >
                      {journal.name}
                    </Link>
                    <p className="text-xs text-slate-500 truncate">Toplam Dergi Atıfı: {journal.total_citation_count.toLocaleString()}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-lg font-bold text-indigo-600">{journal.h_index}</p>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wider">H-Index</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

      </div>
    </div>
  );
}