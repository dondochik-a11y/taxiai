"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { Expense, ExpenseCategory, ExpenseCreate, FinanceSummary, Trip, WeeklySummary } from "@/lib/types";
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

  const loadFinance = useCallback(() => {
    if (!userId) return;
    setLoading(true);

    // One call for the whole window (today + the prior HISTORY_DAYS-1), replacing
    // the old N separate /daily-summary requests. The backend returns days
    // oldest→newest; the last entry is today.
    const weeklyReq = api
      .get<WeeklySummary>(`/v1/finance/weekly-summary/${userId}?days=${HISTORY_DAYS}`)
      .then((weekly) => {
        setDays(weekly.days.map((summary) => ({ date: summary.summary_date, summary })));
        setToday(weekly.days.length ? weekly.days[weekly.days.length - 1] : null);
      })
      .catch(() => {
        setDays([]);
        setToday(null);
      });

    api.get<Trip[]>(`/v1/trips?user_id=${userId}&limit=500`).then(setTrips).catch(() => setTrips([]));

    weeklyReq.finally(() => setLoading(false));
  }, [userId]);

  useEffect(() => {
    loadFinance();
  }, [loadFinance]);

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
      { label: "Прочее", value: today.other_cost },
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

      <ExpenseEntryForm userId={userId} onSaved={loadFinance} />

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

// Manual expense entry (office task #101): wash / fine / other. Fuel is absent
// on purpose — the summary already estimates it from distance. Every logged
// expense reduces net income immediately.
const EXPENSE_OPTIONS: { value: ExpenseCategory; label: string }[] = [
  { value: "wash", label: "Мойка" },
  { value: "fine", label: "Штраф" },
  { value: "other", label: "Прочее" },
];

function ExpenseEntryForm({ userId, onSaved }: { userId: string; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<ExpenseCategory>("wash");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const amountNum = Number(amount);
    if (!amountNum || amountNum <= 0) {
      setError("Укажите сумму расхода больше 0.");
      return;
    }
    setSubmitting(true);
    const payload: ExpenseCreate = { category, amount: amountNum };
    if (note.trim() !== "") payload.note = note.trim();
    try {
      await api.post<Expense>(`/v1/finance/expenses?user_id=${userId}`, payload);
      setAmount("");
      setNote("");
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось записать расход");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="btn-primary self-start">
        + Записать расход
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="card p-4 flex flex-col gap-3">
      <div className="flex gap-2 flex-wrap">
        {EXPENSE_OPTIONS.map((o) => (
          <button
            key={o.value}
            type="button"
            data-active={category === o.value}
            className="chip"
            onClick={() => setCategory(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-[var(--text-secondary)]">Сумма, ₽</span>
          <input
            type="number"
            inputMode="decimal"
            step="1"
            className="input"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="300"
            autoFocus
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-[var(--text-secondary)]">Заметка</span>
          <input
            className="input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="—"
          />
        </label>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={submitting} className="btn-primary flex-1">
          {submitting ? "Сохранение..." : "Записать"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-sm text-[var(--text-muted)] px-3"
        >
          Отмена
        </button>
      </div>
    </form>
  );
}
