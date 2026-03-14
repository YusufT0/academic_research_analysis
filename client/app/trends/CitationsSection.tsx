'use client';

import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/Card';
import { Medal, Star, Target, TrendingUp, Presentation } from 'lucide-react';
import type { CitationStats } from '@/lib/types';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';

const COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const DISTRIBUTION_LABELS: Record<string, string> = {
  "0": "Atıf Almayan (0)",
  "1": "Düşük (1-4)",
  "5": "Orta (5-19)",
  "20": "Yüksek (20-49)",
  "50": "Çok Yüksek (50-99)",
  "100+": "Zirve (100+)"
};

export function CitationsSection({ data }: { data: CitationStats }) {
  // Format data for Recharts
  const distributionData = data.citation_distribution.map((d, i) => ({
    name: DISTRIBUTION_LABELS[d._id.toString()] || `${d._id} Atıf`,
    amount: d.count
  }));

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
            <div className="h-72 w-full">
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={distributionData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    outerRadius={90}
                    fill="#8884d8"
                    dataKey="amount"
                    label={({ name, percent }) => `${name} (${((percent || 0) * 100).toFixed(0)}%)`}
                  >
                    {distributionData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [`${value} makale`, 'Adet']} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
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
                    <p className="text-sm font-semibold text-slate-900 truncate" title={article.title}>{article.title}</p>
                    <p className="text-xs text-slate-500 truncate">{article.authors.slice(0, 2).join(', ')}{article.authors.length > 2 ? ' et al.' : ''} • {article.publication_year}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-lg font-bold text-emerald-600">{article.citation_count}</p>
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
                    <p className="text-sm font-semibold text-slate-900 truncate" title={journal.name}>{journal.name}</p>
                    <p className="text-xs text-slate-500 truncate">Toplam Dergi Atıfı: {journal.total_citation_count}</p>
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