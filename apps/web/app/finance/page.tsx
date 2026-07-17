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

type DayEntry = { date: string; summary: FinanceSummary | null };

// Day-over-day delta helper. Percentage change vs yesterday; omitted when there
// is no prior value to compare against (avoids a meaningless "+∞").
function dayDelta(
  cur: number,
  prev: number | undefined
): { text: string; direction: "up" | "down"; goodDirection: "up" | "down" } | undefined {
  if (prev === undefined || prev === 0) return undefined;
  const diff = cur - prev;
  if (Math.round(diff) === 0) return undefined;
  const pct = Math.round((Math.abs(diff) / Math.abs(prev)) * 100);
  return { text: `${pct}%`, direction: diff > 0 ? "up" : "down", goodDirection: "up" };
}

export default function FinancePage() {
  const userId = useStoredUserId();
  const [today, setToday] = useState<FinanceSummary | null>(null);
  const [days, setDays] = useState<DayEntry[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!userId) return;
    setLoading(true);

    const todayReq = api
      .get<FinanceSummary>(`/v1/finance/daily-summary?user_id=${userId}`)
      .then((s) => setToday(s))
      .catch(() => setToday(null));

    const historyReq = Promise.all(
      Array.from({ length: HISTORY_DAYS }, (_, i) => HISTORY_DAYS - 1 - i).map(async (daysAgo) => {
        const date = isoDateDaysAgo(daysAgo);
        try {
          const summary = await api.get<FinanceSummary>(
            `/v1/finance/daily-summary?user_id=${userId}&summary_date=${date}`
          );
          return { date, summary };
        } catch {
          return { date, summary: null };
        }
      })
    ).then(setDays);

    api.get<Trip[]>(`/v1/trips?user_id=${userId}&limit=500`).then(setTrips).catch(() => setTrips([]));

    Promise.all([todayReq, historyReq]).finally(() => setLoading(false));
  }, [userId]);

  const history: TimeSeriesPoint[] = useMemo(
    () => days.map((d) => ({ date: d.date, value: d.summary?.net_income ?? 0 })),
    [days]
  );

  const yesterday = useMemo(() => {
    const y = isoDateDaysAgo(1);
    return days.find((d) => d.date === y)?.summary ?? null;
  }, [days]);

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
      return { weekday, hour, avg: v.total / v.count, count: v.count };
    });
    const max = Math.max(...avgs.map((a) => a.avg), 1);
    return avgs.map((a) => ({
      weekday: a.weekday,
      hour: a.hour,
      value: a.avg / max,
      raw: a.avg,
      count: a.count,
    }));
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

  if (loading) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-h1">Финансы</h1>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-24 rounded-2xl" />
          ))}
        </div>
        <div className="skeleton h-56 rounded-2xl" />
        <div className="grid md:grid-cols-2 gap-4">
          <div className="skeleton h-48 rounded-2xl" />
          <div className="skeleton h-48 rounded-2xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-h1">Финансы</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile
          label="Доход сегодня"
          value={`${(today?.gross_income ?? 0).toFixed(0)} ₽`}
          delta={dayDelta(today?.gross_income ?? 0, yesterday?.gross_income)}
        />
        <StatTile
          label="Чистыми сегодня"
          value={`${(today?.net_income ?? 0).toFixed(0)} ₽`}
          delta={dayDelta(today?.net_income ?? 0, yesterday?.net_income)}
        />
        <StatTile
          label="Доход в час"
          value={`${(today?.income_per_hour ?? 0).toFixed(0)} ₽/ч`}
          delta={dayDelta(today?.income_per_hour ?? 0, yesterday?.income_per_hour)}
        />
        <StatTile
          label="Доход за км"
          value={`${(today?.income_per_km ?? 0).toFixed(1)} ₽/км`}
          delta={dayDelta(today?.income_per_km ?? 0, yesterday?.income_per_km)}
        />
      </div>

      <TimeSeriesLine title={`Чистый доход, последние ${HISTORY_DAYS} дней`} points={history} />

      <div className="grid md:grid-cols-2 gap-4">
        {costItems.length > 0 && <CostBreakdownBars title="Расходы сегодня" items={costItems} />}
        <HeatmapGrid
          title="Средний чек по дню недели и часу"
          cells={heatmapCells}
          metricLabel="средний чек"
          formatValue={(v) => `${Math.round(v).toLocaleString("ru-RU")} ₽`}
        />
      </div>
    </div>
  );
}
