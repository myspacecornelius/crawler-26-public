'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

interface EmailSegment {
  name: string;
  value: number;
  color: string;
}

interface EmailStatusDonutProps {
  data?: EmailSegment[];
  isLoading?: boolean;
}

export default function EmailStatusDonut({ data, isLoading }: EmailStatusDonutProps) {
  if (isLoading) {
    return (
      <div
        className="glass-card hive-border rounded-xl p-5"
        role="status"
        aria-label="Loading email status chart"
      >
        <div className="h-4 w-28 bg-white/10 rounded mb-4 animate-pulse" />
        <div className="h-[260px] bg-white/5 rounded-lg animate-pulse" />
      </div>
    );
  }

  const segments = data ?? [];
  const total = segments.reduce((sum, s) => sum + s.value, 0);

  if (total === 0) {
    return (
      <div className="glass-card hive-border rounded-xl p-5">
        <h3 className="font-semibold text-gray-100 mb-4">Email Quality</h3>
        <div className="h-[260px] flex items-center justify-center text-gray-500 text-sm">
          No email data available yet.
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card hive-border rounded-xl p-5" role="img" aria-label={`Email quality breakdown: ${total.toLocaleString()} total emails`}>
      <h3 className="font-semibold text-gray-100 mb-4">Email Quality</h3>
      <div style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={segments}
              cx="50%"
              cy="45%"
              innerRadius={55}
              outerRadius={85}
              paddingAngle={2}
              dataKey="value"
              strokeWidth={0}
              aria-label="Email status distribution"
            >
              {segments.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.1)',
                backgroundColor: 'rgba(17,24,39,0.95)',
                boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.3)',
                fontSize: 12,
                color: '#e5e7eb',
              }}
              formatter={((value: number) => [
                `${value.toLocaleString()} (${Math.round((value / total) * 100)}%)`,
              ]) as never}
            />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: 12, color: '#9ca3af' }}
              formatter={(value: string) => {
                const seg = segments.find((s) => s.name === value);
                return `${value}: ${seg?.value.toLocaleString() ?? 0}`;
              }}
            />
            <text
              x="50%"
              y="42%"
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-gray-100"
              style={{ fontSize: 22, fontWeight: 700 }}
              role="text"
              aria-label={`Total: ${total.toLocaleString()} emails`}
            >
              {total.toLocaleString()}
            </text>
            <text
              x="50%"
              y="52%"
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-gray-400"
              style={{ fontSize: 11 }}
            >
              total emails
            </text>
          </PieChart>
        </ResponsiveContainer>
      </div>
      {/* Screen reader accessible table */}
      <table className="sr-only" aria-label="Email quality data">
        <thead>
          <tr><th>Status</th><th>Count</th><th>Percentage</th></tr>
        </thead>
        <tbody>
          {segments.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td>{s.value}</td>
              <td>{Math.round((s.value / total) * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
