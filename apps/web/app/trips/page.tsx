"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { AiTripAnalysis, District, Trip } from "@/lib/types";

export default function TripsPage() {
  const userId = useStoredUserId();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [analyses, setAnalyses] = useState<Record<string, AiTripAnalysis | "loading" | "none">>({});

  useEffect(() => {
    api.get<District[]>("/v1/districts").then(setDistricts).catch(() => setDistricts([]));
  }, []);

  useEffect(() => {
    if (!userId) return;
    api.get<Trip[]>(`/v1/trips?user_id=${userId}&limit=50`).then(setTrips).catch(() => setTrips([]));
  }, [userId]);

  const districtName = (id: number) => districts.find((d) => d.id === id)?.name ?? `#${id}`;

  async function toggleExpand(trip: Trip) {
    if (expanded === trip.id) {
      setExpanded(null);
      return;
    }
    setExpanded(trip.id);
    if (!analyses[trip.id]) {
      setAnalyses((prev) => ({ ...prev, [trip.id]: "loading" }));
      try {
        const analysis = await api.get<AiTripAnalysis>(`/v1/trips/${trip.id}/analysis`);
        setAnalyses((prev) => ({ ...prev, [trip.id]: analysis }));
      } catch {
        setAnalyses((prev) => ({ ...prev, [trip.id]: "none" }));
      }
    }
  }

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
    <div className="flex flex-col gap-3">
      <h1 className="text-lg md:text-xl font-semibold mb-1">Поездки</h1>
      {trips.length === 0 && (
        <div className="card p-8 flex flex-col items-center gap-2 text-center">
          <span className="text-3xl">🛣️</span>
          <p className="text-sm text-[var(--text-secondary)]">Поездок пока нет.</p>
          <p className="text-xs text-[var(--text-muted)]">
            Они появятся здесь автоматически, когда начнёте работать.
          </p>
        </div>
      )}
      {trips.map((trip) => (
        <div key={trip.id} className="card overflow-hidden">
          <button
            onClick={() => toggleExpand(trip)}
            className="w-full flex items-center justify-between gap-3 px-4 py-3.5 text-left"
          >
            <div className="flex flex-col gap-0.5 min-w-0">
              <span className="text-sm font-medium truncate">
                {districtName(trip.start_district_id)}
                <span className="text-[var(--text-muted)]"> → </span>
                {districtName(trip.end_district_id)}
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {new Date(trip.start_time).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                {" · "}
                {trip.distance_km.toFixed(1)} км
              </span>
            </div>
            <span className="font-semibold tabular shrink-0">{trip.price.toFixed(0)} ₽</span>
          </button>
          {expanded === trip.id && (
            <div className="px-4 pb-4 text-sm border-t border-white/10 pt-3">
              {analyses[trip.id] === "loading" && (
                <p className="text-[var(--text-muted)]">Загрузка анализа...</p>
              )}
              {analyses[trip.id] === "none" && (
                <p className="text-[var(--text-muted)]">Анализ для этой поездки ещё не готов.</p>
              )}
              {analyses[trip.id] && analyses[trip.id] !== "loading" && analyses[trip.id] !== "none" && (
                <div className="flex flex-col gap-1">
                  <p className="text-[var(--text-primary)]">
                    {(analyses[trip.id] as AiTripAnalysis).summary_text}
                  </p>
                  {(analyses[trip.id] as AiTripAnalysis).suggested_action && (
                    <p className="text-[var(--series-1)]">
                      {(analyses[trip.id] as AiTripAnalysis).suggested_action}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
