'use client';

import { TopicTrendsSection } from './TopicTrendsSection';

export default function TrendsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Trend Analizi</h1>
        <p className="mt-1 text-slate-500">
          NLP kümeleme modeline göre konu, dergi, yayıncı ve kelime bazlı trend analizi
        </p>
      </div>

      <TopicTrendsSection />
    </div>
  );
}
