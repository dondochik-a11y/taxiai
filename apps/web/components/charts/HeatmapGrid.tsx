"use client";

import { useState } from "react";

// Sequential single-hue heatmap (weekday x hour), per the dataviz skill:
// magnitude -> one hue, light->dark; 2px gap between cells; hover tooltip;
// a scale legend so the ramp is never color-alone.
const SEQUENTIAL_STEPS = ["#104281", "#184f95", "#256abf", "#3987e5", "#86b6ef"];

const WEEKDAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export interface HeatmapCell {
  weekday: number; // 0=Mon..6=Sun
  hour: number; // 0-23
  value: number; // 0-1
}

function colorFor(value: number): string {
  const idx = Math.min(SEQUENTIAL_STEPS.length - 1, Math.max(0, Math.round(value * (SEQUENTIAL_STEPS.length - 1))));
  return SEQUENTIAL_STEPS[idx];
}

export function HeatmapGrid({ title, cells }: { title: string; cells: HeatmapCell[] }) {
  const [hovered, setHovered] = useState<HeatmapCell | null>(null);
  const byKey = new Map(cells.map((c) => [`${c.weekday}-${c.hour}`, c]));

  return (
    <div className="rounded-lg border border-white/10 bg-[var(--surface-1)] p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm text-[var(--text-secondary)]">{title}</h3>
        <div className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
          <span>меньше</span>
          {SEQUENTIAL_STEPS.map((c) => (
            <span key={c} className="w-3 h-3 rounded-sm inline-block" style={{ background: c }} />
          ))}
          <span>больше</span>
        </div>
      </div>
      <div className="relative overflow-x-auto">
        <div className="grid gap-[2px]" style={{ gridTemplateColumns: "32px repeat(24, minmax(14px, 1fr))" }}>
          <div />
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} className="text-[10px] text-[var(--text-muted)] text-center">
              {h % 3 === 0 ? h : ""}
            </div>
          ))}
          {WEEKDAY_LABELS.map((label, weekday) => (
            <div key={weekday} className="contents">
              <div className="text-xs text-[var(--text-secondary)] flex items-center">{label}</div>
              {Array.from({ length: 24 }, (_, hour) => {
                const cell = byKey.get(`${weekday}-${hour}`);
                return (
                  <div
                    key={hour}
                    className="aspect-square rounded-[2px] cursor-default"
                    style={{ background: cell ? colorFor(cell.value) : "var(--gridline)" }}
                    onMouseEnter={() => cell && setHovered(cell)}
                    onMouseLeave={() => setHovered(null)}
                  />
                );
              })}
            </div>
          ))}
        </div>
        {hovered && (
          <div className="absolute top-0 right-0 text-xs bg-black/80 border border-white/10 rounded px-2 py-1 text-[var(--text-primary)] pointer-events-none">
            {WEEKDAY_LABELS[hovered.weekday]} {hovered.hour}:00 — спрос {(hovered.value * 100).toFixed(0)}%
          </div>
        )}
      </div>
    </div>
  );
}
