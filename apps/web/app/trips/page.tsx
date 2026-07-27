"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { AiTripAnalysis, District, Trip, TripCreate } from "@/lib/types";

export default function TripsPage() {
  const userId = useStoredUserId();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [analyses, setAnalyses] = useState<Record<string, AiTripAnalysis | "loading" | "none">>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<District[]>("/v1/districts").then(setDistricts).catch(() => setDistricts([]));
  }, []);

  const loadTrips = useCallback(() => {
    if (!userId) return;
    setLoading(true);
    api
      .get<Trip[]>(`/v1/trips?user_id=${userId}&limit=50`)
      .then(setTrips)
      .catch(() => setTrips([]))
      .finally(() => setLoading(false));
  }, [userId]);

  useEffect(() => {
    loadTrips();
  }, [loadTrips]);

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
    <div className="max-w-2xl mx-auto flex flex-col gap-4">
      <h1 className="text-h1">Поездки</h1>
      <TripEntryForm userId={userId} districts={districts} onSaved={loadTrips} />
      {loading &&
        Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="skeleton h-[4.5rem] rounded-2xl" />
        ))}
      {!loading && trips.length === 0 && (
        <div className="card p-8 flex flex-col items-center gap-2 text-center">
          <span className="text-3xl">🛣️</span>
          <p className="text-sm text-[var(--text-secondary)]">Поездок пока нет.</p>
          <p className="text-xs text-[var(--text-muted)]">
            Они появятся здесь автоматически, когда начнёте работать.
          </p>
        </div>
      )}
      {!loading &&
        trips.map((trip) => (
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

// Minimal manual trip log (office task #101): amount + distance are enough; the
// server fills the rest and rolls it straight into the daily finance summary.
function TripEntryForm({
  userId,
  districts,
  onSaved,
}: {
  userId: string;
  districts: District[];
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState("");
  const [distance, setDistance] = useState("");
  const [durationMin, setDurationMin] = useState("");
  const [districtId, setDistrictId] = useState<number | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const priceNum = Number(price);
    const distanceNum = Number(distance);
    if (!priceNum || priceNum <= 0) {
      setError("Укажите сумму поездки больше 0.");
      return;
    }
    if (distance !== "" && distanceNum < 0) {
      setError("Расстояние не может быть отрицательным.");
      return;
    }
    setSubmitting(true);
    const payload: TripCreate = {
      price: priceNum,
      distance_km: distance === "" ? 0 : distanceNum,
    };
    if (districtId !== "") {
      payload.start_district_id = Number(districtId);
      payload.end_district_id = Number(districtId);
    }
    if (durationMin !== "" && Number(durationMin) > 0) {
      payload.duration_seconds = Math.round(Number(durationMin) * 60);
    }
    try {
      await api.post<Trip>(`/v1/trips?user_id=${userId}`, payload);
      setPrice("");
      setDistance("");
      setDurationMin("");
      setDistrictId("");
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось записать поездку");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="btn-primary">
        + Записать поездку
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="card p-4 flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-[var(--text-secondary)]">Сумма, ₽</span>
          <input
            type="number"
            inputMode="decimal"
            step="1"
            className="input"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="450"
            autoFocus
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-[var(--text-secondary)]">Километры</span>
          <input
            type="number"
            inputMode="decimal"
            step="0.1"
            className="input"
            value={distance}
            onChange={(e) => setDistance(e.target.value)}
            placeholder="12"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-[var(--text-secondary)]">Длительность, мин</span>
          <input
            type="number"
            inputMode="numeric"
            step="1"
            className="input"
            value={durationMin}
            onChange={(e) => setDurationMin(e.target.value)}
            placeholder="—"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-[var(--text-secondary)]">Район</span>
          <select
            className="input"
            value={districtId}
            onChange={(e) => setDistrictId(e.target.value === "" ? "" : Number(e.target.value))}
          >
            <option value="">— по умолчанию —</option>
            {districts.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
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
