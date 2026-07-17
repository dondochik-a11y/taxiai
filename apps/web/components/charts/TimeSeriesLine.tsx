"use client";

import { useState } from "react";

// Single-series line chart (daily net income) — no legend needed (title names
// the series), 2px line per the mark spec, hover/tap crosshair + tooltip, a
// distinct zero baseline (the series can go negative), first/mid/last x-axis
// dates, and a permanent label on the latest point.
export interface TimeSeriesPoint {
  date: string;
  value: number;
}

const WIDTH = 640;
const HEIGHT = 200;
const PAD_LEFT = 52;
const PAD_RIGHT = 12;
const PAD_BOTTOM = 30;
const PAD_TOP = 14;

const rub = (v: number) =>
  `${v < 0 ? "−" : ""}${Math.abs(Math.round(v)).toLocaleString("ru-RU")} ₽`;

const shortDate = (iso: string) =>
  new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });

export function TimeSeriesLine({ title, points }: { title: string; points: TimeSeriesPoint[] }) {
  const [pinned, setPinned] = useState<number | null>(null);

  if (points.length === 0) {
    return (
      <div className="card p-4">
        <h3 className="text-sm text-[var(--text-secondary)] mb-2">{title}</h3>
        <p className="text-sm text-[var(--text-muted)]">Пока нет данных.</p>
      </div>
    );
  }

  const values = points.map((p) => p.value);
  const maxV = Math.max(...values, 1);
  const minV = Math.min(0, ...values);
  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotH = HEIGHT - PAD_TOP - PAD_BOTTOM;

  const x = (i: number) => PAD_LEFT + (i / Math.max(points.length - 1, 1)) * plotW;
  const y = (v: number) => PAD_TOP + plotH - ((v - minV) / (maxV - minV || 1)) * plotH;

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.value)}`).join(" ");
  const yTicks = [minV, (minV + maxV) / 2, maxV];
  const hasZeroBaseline = minV < 0;

  const latestIdx = points.length - 1;
  const latest = points[latestIdx];
  const midIdx = Math.floor(latestIdx / 2);

  const summaryLabel =
    `${title}. Минимум ${rub(minV)}, максимум ${rub(maxV)}, ` +
    `последнее значение ${rub(latest.value)} (${shortDate(latest.date)}).`;

  return (
    <div className="card p-4">
      <h3 className="text-sm text-[var(--text-secondary)] mb-2">{title}</h3>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto"
        role="img"
        aria-label={summaryLabel}
        onMouseLeave={() => setPinned(null)}
      >
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={PAD_LEFT}
              x2={WIDTH - PAD_RIGHT}
              y1={y(t)}
              y2={y(t)}
              stroke="var(--gridline)"
              strokeWidth={1}
            />
            <text
              x={PAD_LEFT - 6}
              y={y(t) + 4}
              fontSize={10}
              textAnchor="end"
              fill="var(--text-muted)"
              className="figure"
            >
              {rub(t)}
            </text>
          </g>
        ))}

        {/* Distinct zero baseline when the series dips negative */}
        {hasZeroBaseline && (
          <line
            x1={PAD_LEFT}
            x2={WIDTH - PAD_RIGHT}
            y1={y(0)}
            y2={y(0)}
            stroke="var(--baseline)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        )}

        {/* x-axis: first / mid / last dates */}
        {[0, midIdx, latestIdx].map((idx, k) => (
          <text
            key={idx}
            x={x(idx)}
            y={HEIGHT - 8}
            fontSize={10}
            textAnchor={k === 0 ? "start" : k === 2 ? "end" : "middle"}
            fill="var(--text-muted)"
          >
            {shortDate(points[idx].date)}
          </text>
        ))}

        <path
          d={path}
          fill="none"
          stroke="var(--series-1)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* permanent latest-value dot */}
        <circle cx={x(latestIdx)} cy={y(latest.value)} r={3} fill="var(--series-1)" />

        {points.map((p, i) => (
          <rect
            key={i}
            x={x(i) - plotW / points.length / 2}
            y={PAD_TOP}
            width={plotW / points.length}
            height={plotH}
            fill="transparent"
            onMouseEnter={() => setPinned(i)}
            onPointerDown={() => setPinned(i)}
            onClick={() => setPinned(i)}
          />
        ))}

        {pinned !== null && (
          <>
            <line
              x1={x(pinned)}
              x2={x(pinned)}
              y1={PAD_TOP}
              y2={PAD_TOP + plotH}
              stroke="var(--baseline)"
              strokeWidth={1}
            />
            <circle
              cx={x(pinned)}
              cy={y(points[pinned].value)}
              r={4}
              fill="var(--series-1)"
              stroke="var(--surface-1)"
              strokeWidth={2}
            />
          </>
        )}
      </svg>

      <p className="text-xs text-[var(--text-secondary)] figure">
        {pinned !== null
          ? `${shortDate(points[pinned].date)}: ${rub(points[pinned].value)}`
          : `Последнее — ${shortDate(latest.date)}: ${rub(latest.value)}`}
      </p>

      <table className="sr-only">
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>Дата</th>
            <th>Значение, ₽</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.date}>
              <td>{shortDate(p.date)}</td>
              <td>{Math.round(p.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
