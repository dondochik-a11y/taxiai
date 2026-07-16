"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { DailyPlanWindow } from "@/lib/types";

function formatHour(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

function timeOfDayLabel(startHour: number): string {
  if (startHour < 6) return "Ночное окно";
  if (startHour < 12) return "Утреннее окно";
  if (startHour < 17) return "Дневное окно";
  return "Вечернее окно";
}

function hoursLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} час`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} часа`;
  return `${count} часов`;
}

function ClockIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

export default function PlanPage() {
  const userId = useStoredUserId();
  const [windows, setWindows] = useState<DailyPlanWindow[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .get<DailyPlanWindow[]>("/v1/forecasts/daily-plan")
      .then(setWindows)
      .catch(() => setError(true));
  }, []);

  const todayLabel = new Date().toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="max-w-lg mx-auto flex flex-col gap-4">
      <div>
        <h1 className="text-lg md:text-xl font-semibold mb-1">План на день</h1>
        <p className="text-sm text-[var(--text-secondary)]">
          Лучшие часы для выхода на линию — {todayLabel}.
        </p>
      </div>

      {error && (
        <p className="text-sm" style={{ color: "var(--status-critical)" }}>
          Не удалось загрузить план. Проверьте соединение и обновите страницу.
        </p>
      )}

      {!error && windows === null && (
        <div className="card p-4 text-sm text-[var(--text-secondary)]">Загрузка...</div>
      )}

      {windows !== null && windows.length === 0 && (
        <div className="card p-4 text-sm text-[var(--text-secondary)]">
          Пока недостаточно истории спроса, чтобы построить план на этот день недели. Загляните
          позже.
        </div>
      )}

      {windows !== null && windows.length > 0 && (
        <div className="flex flex-col gap-3">
          {windows.map((w, i) => (
            <div key={`${w.start_hour}-${w.end_hour}`} className="card p-4 flex items-center gap-4">
              <span className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center text-[var(--series-1)] shrink-0">
                <ClockIcon className="w-5 h-5" />
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-lg font-semibold tabular">
                  {formatHour(w.start_hour)}–{formatHour(w.end_hour)}
                </div>
                <div className="text-xs text-[var(--text-muted)]">
                  {timeOfDayLabel(w.start_hour)} · {hoursLabel(w.end_hour - w.start_hour)} работы
                </div>
              </div>
              <span className="chip" data-active={i === 0}>
                окно {i + 1}
              </span>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-[var(--text-muted)]">
        Окна рассчитаны по средней истории спроса для этого дня недели — это ориентир на утро, а не
        прогноз на ближайший час. Актуальный спрос смотрите на{" "}
        <Link href="/" className="text-[var(--series-1)] underline">
          карте
        </Link>
        .
      </p>

      {userId === null && (
        <p className="text-xs text-[var(--text-muted)]">
          Чтобы получать план на день в Telegram,{" "}
          <Link href="/onboarding" className="text-[var(--series-1)] underline">
            настройте профиль
          </Link>
          .
        </p>
      )}
    </div>
  );
}
