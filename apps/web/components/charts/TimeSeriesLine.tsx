"use client";

import { useState } from "react";

// Single-series line chart (daily net income) — no legend needed (title names
// the series), 2px line per the mark spec, hover crosshair + tooltip.
export interface TimeSeriesPoint {
  date: string;
  value: number;
}

const WIDTH = 640;
const HEIGHT = 200;
const PAD_LEFT = 48;
const PAD_BOTTOM = 24;
const PAD_TOP = 12;

export function TimeSeriesLine({ title, points }: { title: string; points: TimeSeriesPoint[] }) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (points.length === 0) {
    return (
      <div className="rounded-lg border border-white/10 bg-[var(--surface-1)] p-4">
        <h3 className="text-sm text-[var(--text-secondary)] mb-2">{title}</h3>
        <p className="text-sm text-[var(--text-muted)]">Пока нет данных.</p>
      </div>
    );
  }

  const values = points.map((p) => p.value);
  const maxV = Math.max(...values, 1);
  const minV = Math.min(0, ...values);
  const plotW = WIDTH - PAD_LEFT - 8;
  const plotH = HEIGHT - PAD_TOP - PAD_BOTTOM;

  const x = (i: number) => PAD_LEFT + (i / Math.max(points.length - 1, 1)) * plotW;
  const y = (v: number) => PAD_TOP + plotH - ((v - minV) / (maxV - minV || 1)) * plotH;

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.value)}`).join(" ");
  const yTicks = [minV, (minV + maxV) / 2, maxV];

  return (
    <div className="rounded-lg border border-white/10 bg-[var(--surface-1)] p-4">
      <h3 className="text-sm text-[var(--text-secondary)] mb-2">{title}</h3>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto"
        onMouseLeave={() => setHoverIdx(null)}
      >
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={PAD_LEFT}
              x2={WIDTH - 8}
              y1={y(t)}
              y2={y(t)}
              stroke="var(--gridline)"
              strokeWidth={1}
            />
            <text x={4} y={y(t) + 4} fontSize={10} fill="var(--text-muted)">
              {Math.round(t)}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <rect
            key={i}
            x={x(i) - plotW / points.length / 2}
            y={PAD_TOP}
            width={plotW / points.length}
            height={plotH}
            fill="transparent"
            onMouseEnter={() => setHoverIdx(i)}
          />
        ))}
        {hoverIdx !== null && (
          <>
            <line
              x1={x(hoverIdx)}
              x2={x(hoverIdx)}
              y1={PAD_TOP}
              y2={PAD_TOP + plotH}
              stroke="var(--baseline)"
              strokeWidth={1}
            />
            <circle cx={x(hoverIdx)} cy={y(points[hoverIdx].value)} r={4} fill="var(--series-1)" stroke="var(--surface-1)" strokeWidth={2} />
          </>
        )}
      </svg>
      {hoverIdx !== null && (
        <p className="text-xs text-[var(--text-secondary)] tabular">
          {points[hoverIdx].date}: {points[hoverIdx].value.toFixed(0)} ₽
        </p>
      )}
    </div>
  );
}
