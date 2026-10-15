import { useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { ConvergencePoint } from '../../hooks/useSolver';

interface ConvergenceChartProps {
  data: ConvergencePoint[];
  isRunning: boolean;
}

export function ConvergenceChart({ data, isRunning }: ConvergenceChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (data.length === 0) {
    return (
      <div className="chart-empty">
        {isRunning ? (
          <div className="chart-pulse">
            <span className="pulse-dot" />
            Waiting for first iteration…
          </div>
        ) : (
          <span className="chart-placeholder">Convergence chart will appear here</span>
        )}
      </div>
    );
  }

  const minCost = Math.min(...data.map((d) => d.cost));
  const maxCost = Math.max(...data.map((d) => d.cost));

  return (
    <div className="chart-container">
      <div className="chart-header">
        <span className="chart-title">Convergence</span>
        <span className="chart-meta">
          Best: <strong>{minCost.toFixed(1)}</strong>
          {isRunning && <span className="live-badge">LIVE</span>}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart
          data={data}
          onMouseMove={(s) => {
            if (s.activePayload) setHovered(s.activePayload[0]?.value as number);
          }}
          onMouseLeave={() => setHovered(null)}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="iter"
            stroke="rgba(255,255,255,0.3)"
            tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.5)' }}
            label={{ value: 'Iteration', position: 'insideBottom', fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
          />
          <YAxis
            domain={[minCost * 0.98, maxCost * 1.02]}
            stroke="rgba(255,255,255,0.3)"
            tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.5)' }}
            tickFormatter={(v: number) => v.toFixed(0)}
            width={45}
          />
          <Tooltip
            contentStyle={{
              background: 'rgba(15,15,30,0.9)',
              border: '1px solid rgba(99,102,241,0.4)',
              borderRadius: 8,
              color: '#e2e8f0',
              fontSize: 11,
            }}
            formatter={(v: number) => [v.toFixed(2), 'Best cost']}
            labelFormatter={(l: number) => `Iteration ${l}`}
          />
          <Line
            type="monotone"
            dataKey="cost"
            stroke="#6366f1"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#818cf8', strokeWidth: 0 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      {hovered !== null && (
        <div className="chart-hover-val">{hovered.toFixed(2)}</div>
      )}
    </div>
  );
}
