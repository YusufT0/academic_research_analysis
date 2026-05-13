'use client';

import { useMemo, memo } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, type PieLabelRenderProps } from 'recharts';

/** Same order as TopicTrendChart.COLOR_PALETTE — fallback when colorMap misses a key */
const TREND_COLOR_FALLBACK = [
  '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#14b8a6',
  '#a855f7', '#eab308', '#64748b', '#0ea5e9', '#d946ef',
  '#22c55e', '#f43f5e', '#fb923c', '#a3e635', '#38bdf8',
];

const DEFAULT_AI_COLORS = [
  '#10b981', '#14b8a6', '#06b6d4', '#3b82f6', '#6366f1',
  '#8b5cf6', '#a855f7', '#ec4899', '#f59e0b', '#ef4444',
  '#64748b',
];

const RADIAN = Math.PI / 180;

function PieLabel({
  cx, cy, midAngle, outerRadius, name, percent,
}: PieLabelRenderProps) {
  if (cx == null || cy == null || midAngle == null || outerRadius == null || name == null || percent == null) return null;
  const radius = outerRadius + 22;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  const anchor = x > cx ? 'start' : 'end';
  const MAX = 15;
  const display = name.length > MAX ? name.slice(0, MAX) + '…' : name;
  return (
    <g>
      <title>{`${name}: ${(percent * 100).toFixed(0)}%`}</title>
      <text
        x={x}
        y={y}
        textAnchor={anchor}
        dominantBaseline="central"
        fontSize={16}
        fill="#374151"
      >
        {display} ({(percent * 100).toFixed(0)}%)
      </text>
    </g>
  );
}

export interface TopicDistributionPieProps {
  data: Record<string, number>;
  /** When set, slice fill matches line chart topic colors */
  colorMap?: Map<string, string>;
  maxSlices?: number;
}

function TopicDistributionPieInner({ data, colorMap, maxSlices = 10 }: TopicDistributionPieProps) {
  const chartData = useMemo(() => {
    return Object.entries(data)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, maxSlices);
  }, [data, maxSlices]);

  const fills = useMemo(() => {
    const palette = colorMap ? TREND_COLOR_FALLBACK : DEFAULT_AI_COLORS;
    return chartData.map((row, i) =>
      colorMap?.get(row.name) ?? palette[i % palette.length],
    );
  }, [chartData, colorMap]);

  if (chartData.length === 0) {
    return <p className="text-sm text-slate-400 text-center py-8">Konu verisi bulunamadı</p>;
  }

  return (
    <div className="min-h-[300px]" style={{ overflow: 'visible' }}>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart margin={{ top: 30, right: 50, bottom: 30, left: 50 }}>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={48}
            outerRadius={78}
            paddingAngle={2}
            dataKey="value"
            isAnimationActive={false}
            labelLine={{ strokeWidth: 1 }}
            label={PieLabel}
          >
            {chartData.map((row, i) => (
              <Cell key={row.name} fill={fills[i]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0' }}
            formatter={(value, name) => [`${value} makale`, String(name)]}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function sameRecord(a: Record<string, number>, b: Record<string, number>) {
  const ak = Object.keys(a);
  const bk = Object.keys(b);
  if (ak.length !== bk.length) return false;
  for (const k of ak) {
    if (a[k] !== b[k]) return false;
  }
  return true;
}

function sameColorMap(a?: Map<string, string>, b?: Map<string, string>) {
  if (a === b) return true;
  if (!a || !b || a.size !== b.size) return false;
  for (const [k, v] of a) {
    if (b.get(k) !== v) return false;
  }
  return true;
}

/** Zoom vb. üst state değişimlerinde yeniden çizilmemesi için sarmalanmış pie */
export const TopicDistributionPie = memo(
  TopicDistributionPieInner,
  (prev, next) =>
    prev.maxSlices === next.maxSlices &&
    sameRecord(prev.data, next.data) &&
    sameColorMap(prev.colorMap, next.colorMap),
);
TopicDistributionPie.displayName = 'TopicDistributionPie';
