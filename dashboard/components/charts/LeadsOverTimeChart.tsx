'use client';

import { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

interface DataPoint {
  date: string;
  verified: number;
  guessed: number;
}

interface LeadsOverTimeChartProps {
  data?: DataPoint[];
  isLoading?: boolean;
}

const RANGES = ['7d', '30d', '90d', 'All'] as const;

export default function LeadsOverTimeChart({ data, isLoading }: LeadsOverTimeChartProps) {
  const [range, setRange] = useState<(typeof RANGES)[number]>('30d');

  if (isLoading) {
    return (
      <div
        className="glass-card hive-border rounded-xl p-5"
        role="status"
        aria-label="Loading leads chart"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="h-4 w-36 bg-white/10 rounded animate-pulse" />
          <div className="flex gap-1">
            {RANGES.map((r) => (
              <div key={r} className="h-7 w-10 bg-white/10 rounded-md animate-pulse" />
            ))}
          </div>
        </div>
        <div className="h-[260px] bg-white/5 rounded-lg animate-pulse" />
      </div>
    );
  }

  const chartData = data ?? [];
  const filteredData = (() => {
    if (range === '7d') return chartData.slice(-7);
    if (range === '30d') return chartData.slice(-30);
    if (range === '90d') return chartData.slice(-90);
    return chartData;
  })();

  const hasData = filteredData.length > 0;

  return (
    <div className="glass-card hive-border rounded-xl p-5" role="img" aria-label="Leads generated over time chart">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-100">Leads Generated</h3>
        <div className="flex gap-1" role="group" aria-label="Time range selector">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              aria-pressed={range === r}
              aria-label={`Show ${r === 'All' ? 'all' : `last ${r}`} data`}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                range === r
                  ? 'bg-brand-500/20 text-brand-400 border border-brand-500/30'
                  : 'text-gray-400 hover:text-gray-300 hover:bg-white/5'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <div style={{ width: '100%', height: 260 }}>
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={filteredData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gradVerified" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="gradGuessed" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: '#6b7280' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.1)',
                  backgroundColor: 'rgba(17,24,39,0.95)',
                  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.3)',
                  fontSize: 12,
                  color: '#e5e7eb',
                }}
              />
              <Legend
                iconType="circle"
                iconSize={8}
                wrapperStyle={{ fontSize: 12, paddingTop: 8, color: '#9ca3af' }}
              />
              <Area
                type="monotone"
                dataKey="verified"
                name="Verified"
                stackId="1"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#gradVerified)"
              />
              <Area
                type="monotone"
                dataKey="guessed"
                name="Guessed"
                stackId="1"
                stroke="#f59e0b"
                strokeWidth={2}
                fill="url(#gradGuessed)"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-gray-500 text-sm">
            No lead data available yet. Run a campaign to see trends.
          </div>
        )}
      </div>
    </div>
  );
}
