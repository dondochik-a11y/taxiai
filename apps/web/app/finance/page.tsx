"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { FinanceSummary, Trip } from "@/lib/types";
import { StatTile } from "@/components/charts/StatTile";
import { TimeSeriesLine, type TimeSeriesPoint } from "@/components/charts/TimeSeriesLine";
import { CostBreakdownBars } from "@/components/charts/CostBreakdownBars";
import { HeatmapGrid, type HeatmapCell } from "@/components/charts/HeatmapGrid";

const HISTORY_DAYS = 14;

function isoDateDaysAgo(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

export default function FinancePage() {
  const userId = useStoredUserId();
  const [today, setToday] = useState<FinanceSummary | null>(null);
  const [history, setHistory] = useState<TimeSeriesPoint[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);

  useEffect(() => {
    if (!userId) return;
    api.get<FinanceSummary>(`/v1/finance/daily-summary?user_id=${userId}`).then(setToday).catch(() => setToday(null));

    Promise.all(
      Array.from({ length: HISTORY_DAYS }, (_, i) => HISTORY_DAYS - 1 - i).map(async (daysAgo) => {
        const date = isoDateDaysAgo(daysAgo);
        try {
          const summary = await api.get<FinanceSummary>(
            `/v1/finance/daily-summary?user_id=${userId}&summary_date=${date}`
          );
          return { date, value: summary.net_income };
        } catch {
          return { date, value: 0 };
        }
      })
    ).then(setHistory);

    api.get<Trip[]>(`/v1/trips?user_id=${userId}&limit=500`).then(setTrips).catch(() => setTrips([]));
  }, [userId]);

  const costItems = useMemo(() => {
    if (!today) return [];
    return [
      { label: "Топливо", value: today.fuel_cost },
      { label: "Аренда", value: today.rental_cost },
      { label: "Мойки", value: today.wash_cost },
      { label: "Штрафы", value: today.fines_cost },
      { label: "Налог", value: today.tax_estimate },
      { label: "Амортизация", value: today.depreciation_estimate },
    ].filter((i) => i.value > 0);
  }, [today]);

  const heatmapCells: HeatmapCell[] = useMemo(() => {
    const sums = new Map<string, { total: number; count: number }>();
    trips.forEach((t) => {
      const d = new Date(t.start_time);
      const weekday = (d.getDay() + 6) % 7; // JS getDay: 0=Sun -> convert to 0=Mon
      const key = `${weekday}-${d.getHours()}`;
      const entry = sums.get(key) ?? { total: 0, count: 0 };
      entry.total += t.price;
      entry.count += 1;
      sums.set(key, entry);
    });
    const avgs = Array.from(sums.entries()).map(([key, v]) => {
      const [weekday, hour] = key.split("-").map(Number);
      return { weekday, hour, avg: v.total / v.count };
    });
    const max = Math.max(...avgs.map((a) => a.avg), 1);
    return avgs.map((a) => ({ weekday: a.weekday, hour: a.hour, value: a.avg / max }));
  }, [trips]);

  if (userId === undefined) return null;

  if (userId === null) {
    return (
      <p className="text-sm text-[var(--text-secondary)]">
        Профиль ещё не создан —{" "}
        <Link href="/onboarding" className="text-[var(--series-1)] underline">
          заполните настройки
        </Link>
        .
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-lg md:text-xl font-semibold">Финансы</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Доход сегодня" value={`${(today?.gross_income ?? 0).toFixed(0)} ₽`} />
        <StatTile label="Чистыми сегодня" value={`${(today?.net_income ?? 0).toFixed(0)} ₽`} />
        <StatTile label="Доход в час" value={`${(today?.income_per_hour ?? 0).toFixed(0)} ₽/ч`} />
        <StatTile label="Доход за км" value={`${(today?.income_per_km ?? 0).toFixed(1)} ₽/км`} />
      </div>

      <TimeSeriesLine title={`Чистый доход, последние ${HISTORY_DAYS} дней`} points={history} />

      <div className="grid md:grid-cols-2 gap-4">
        {costItems.length > 0 && <CostBreakdownBars title="Расходы сегодня" items={costItems} />}
        <HeatmapGrid title="Средний чек по дню недели и часу" cells={heatmapCells} />
      </div>
    </div>
  );
}
