"use client";

import { useMemo, useState } from "react";

// Sequential single-hue heatmap (weekday x hour). The ramp is re-anchored so
// even the LOWEST colored step clears ~3:1 on --surface-1 (the old navy steps
// were invisible). No-data / under-sampled cells render DISTINCTLY (flat, thin
// border) rather than as a fake low value. Mobile buckets the 24 hours into
// 6 four-hour bands so a week fits width-first; the fine 24-col grid returns at
// md:. Tooltip shows the real metric via a caller-supplied formatter.
const SEQUENTIAL_STEPS = ["#2f6fd0", "#4d84d6", "#6a9de2", "#86b6ef", "#a9cbf3"];

const WEEKDAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export interface HeatmapCell {
  weekday: number; // 0=Mon..6=Sun
  hour: number; // 0-23
  value: number; // 0-1 normalized magnitude (drives color)
  raw?: number; // real metric value (drives tooltip / formatter)
  count?: number; // sample size behind the cell
}

interface AggCell {
  value: number;
  raw: number;
  count: number;
}

function colorFor(value: number): string {
  const idx = Math.min(
    SEQUENTIAL_STEPS.length - 1,
    Math.max(0, Math.round(value * (SEQUENTIAL_STEPS.length - 1)))
  );
  return SEQUENTIAL_STEPS[idx];
}

export function HeatmapGrid({
  title,
  cells,
  formatValue,
  metricLabel,
  minCount = 3,
}: {
  title: string;
  cells: HeatmapCell[];
  /** Formats the raw metric for the tooltip, e.g. (v) => `${Math.round(v)} ₽`. */
  formatValue?: (raw: number) => string;
  /** Short metric name shown in the tooltip, e.g. "средний чек". */
  metricLabel?: string;
  /** Minimum samples before a cell is colored (else it reads as no-data). */
  minCount?: number;
}) {
  const [hovered, setHovered] = useState<{ weekday: number; label: string; text: string } | null>(
    null
  );

  const byKey = useMemo(() => new Map(cells.map((c) => [`${c.weekday}-${c.hour}`, c])), [cells]);

  const fmt = formatValue ?? ((v: number) => `${Math.round(v * 100)}%`);
  const label = metricLabel ? `${metricLabel} ` : "";

  // Aggregate the hours [startHour, startHour+span) for one weekday, weighting
  // by sample count so a busy hour dominates a quiet one within a band.
  const aggregate = (weekday: number, startHour: number, span: number): AggCell | null => {
    let count = 0;
    let weight = 0;
    let rawWeighted = 0;
    let valWeighted = 0;
    for (let h = startHour; h < startHour + span; h++) {
      const cell = byKey.get(`${weekday}-${h}`);
      if (!cell) continue;
      const w = cell.count ?? 1;
      count += cell.count ?? 0;
      weight += w;
      rawWeighted += (cell.raw ?? 0) * w;
      valWeighted += cell.value * w;
    }
    if (weight === 0) return null;
    return { count, raw: rawWeighted / weight, value: valWeighted / weight };
  };

  // Peak (colored) cell for the accessible summary.
  const peak = useMemo(() => {
    let best: { weekday: number; hour: number; raw: number } | null = null;
    for (const c of cells) {
      if ((c.count ?? 0) < minCount) continue;
      if (!best || (c.raw ?? 0) > best.raw)
        best = { weekday: c.weekday, hour: c.hour, raw: c.raw ?? 0 };
    }
    return best;
  }, [cells, minCount]);

  const summary =
    `${title}. ` +
    (peak
      ? `Пик: ${WEEKDAY_LABELS[peak.weekday]} в ${peak.hour}:00 — ${label}${fmt(peak.raw)}.`
      : "Недостаточно данных.");

  // One grid at a given granularity. hourStep=1 → 24 cols (fine, md+),
  // hourStep=4 → 6 bands (mobile).
  const renderGrid = (hourStep: number) => {
    const cols = 24 / hourStep;
    return (
      <div
        className="grid gap-[2px]"
        style={{ gridTemplateColumns: `28px repeat(${cols}, minmax(0, 1fr))` }}
      >
        <div />
        {Array.from({ length: cols }, (_, c) => {
          const startHour = c * hourStep;
          const show = hourStep === 1 ? startHour % 3 === 0 : true;
          return (
            <div key={c} className="text-[10px] text-[var(--text-muted)] text-center">
              {show ? startHour : ""}
            </div>
          );
        })}
        {WEEKDAY_LABELS.map((wl, weekday) => (
          <div key={weekday} className="contents">
            <div className="text-xs text-[var(--text-secondary)] flex items-center">{wl}</div>
            {Array.from({ length: cols }, (_, c) => {
              const startHour = c * hourStep;
              const agg = aggregate(weekday, startHour, hourStep);
              const colored = agg !== null && agg.count >= minCount;
              const timeLabel =
                hourStep === 1
                  ? `${String(startHour).padStart(2, "0")}:00`
                  : `${String(startHour).padStart(2, "0")}–${String(startHour + hourStep).padStart(2, "0")}`;
              const readout = agg
                ? { weekday, label: timeLabel, text: `${label}${fmt(agg.raw)}` }
                : null;
              return (
                <div
                  key={c}
                  className="aspect-square rounded-[2px] cursor-default"
                  style={
                    colored
                      ? { background: colorFor(agg!.value) }
                      : {
                          background: "var(--surface-1)",
                          boxShadow: "inset 0 0 0 1px var(--gridline)",
                        }
                  }
                  onMouseEnter={() => colored && readout && setHovered(readout)}
                  onPointerDown={() => colored && readout && setHovered(readout)}
                  onMouseLeave={() => setHovered(null)}
                />
              );
            })}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="card p-4" role="img" aria-label={summary}>
      <div className="flex items-center justify-between mb-3 gap-2">
        <h3 className="text-sm text-[var(--text-secondary)]">{title}</h3>
        <div className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
          <span>меньше</span>
          {SEQUENTIAL_STEPS.map((c) => (
            <span key={c} className="w-3 h-3 rounded-sm inline-block" style={{ background: c }} />
          ))}
          <span>больше</span>
        </div>
      </div>
      <div className="relative">
        {/* mobile: 6 four-hour bands (fits width, no horizontal scroll) */}
        <div className="md:hidden">{renderGrid(4)}</div>
        {/* md+: full 24-hour resolution */}
        <div className="hidden md:block">{renderGrid(1)}</div>

        {hovered && (
          <div
            className="absolute top-0 right-0 text-xs rounded px-2 py-1 text-[var(--text-primary)] pointer-events-none border border-white/10"
            style={{ background: "var(--overlay)" }}
          >
            {WEEKDAY_LABELS[hovered.weekday]} {hovered.label} — {hovered.text}
          </div>
        )}
      </div>

      <table className="sr-only">
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>День</th>
            {Array.from({ length: 24 }, (_, h) => (
              <th key={h}>{h}:00</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {WEEKDAY_LABELS.map((wl, weekday) => (
            <tr key={weekday}>
              <th>{wl}</th>
              {Array.from({ length: 24 }, (_, h) => {
                const cell = byKey.get(`${weekday}-${h}`);
                const ok = cell && (cell.count ?? 0) >= minCount;
                return <td key={h}>{ok ? fmt(cell!.raw ?? 0) : "—"}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
