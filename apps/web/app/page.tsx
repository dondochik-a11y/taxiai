"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { District, Forecast, Recommendation, SurgeNow, User } from "@/lib/types";
import { MoscowMap, type MapMode } from "@/components/map/MoscowMap";

const HORIZONS = [15, 30, 60, 120];
const MODES: { value: MapMode; label: string }[] = [
  { value: "demand", label: "спрос" },
  { value: "surge", label: "кэф" },
];

export default function DashboardPage() {
  const [districts, setDistricts] = useState<District[]>([]);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [horizon, setHorizon] = useState(30);
  const [mode, setMode] = useState<MapMode>("demand");
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [recError, setRecError] = useState<string | null>(null);
  const [loadingRec, setLoadingRec] = useState(false);
  const userId = useStoredUserId();

  const [surgeNow, setSurgeNow] = useState<SurgeNow[]>([]);

  useEffect(() => {
    api.get<District[]>("/v1/districts").then(setDistricts).catch(() => setDistricts([]));
  }, []);

  // The current кэф is a live feed — refresh it on the worker's 5-min cadence.
  useEffect(() => {
    const load = () =>
      api.get<SurgeNow[]>("/v1/surge/current").then(setSurgeNow).catch(() => setSurgeNow([]));
    load();
    const t = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    api
      .get<Forecast[]>(`/v1/forecasts?horizon_minutes=${horizon}`)
      .then(setForecasts)
      .catch(() => setForecasts([]));
  }, [horizon]);

  const forecastByDistrict = useMemo(() => {
    const map = new Map<number, Forecast>();
    forecasts.forEach((f) => map.set(f.district_id, f));
    return map;
  }, [forecasts]);

  const districtById = useMemo(() => new Map(districts.map((d) => [d.id, d])), [districts]);

  const surgeNowByDistrict = useMemo(() => {
    const map = new Map<number, SurgeNow>();
    surgeNow.forEach((s) => map.set(s.district_id, s));
    return map;
  }, [surgeNow]);

  async function requestRecommendation(lat: number, lng: number) {
    try {
      const rec = await api.post<Recommendation>(`/v1/recommendations/${userId}`, {
        lat,
        lng,
        horizon_minutes: horizon,
      });
      setRecommendation(rec);
    } catch (err) {
      setRecError(err instanceof Error ? err.message : "Не удалось получить рекомендацию");
    } finally {
      setLoadingRec(false);
    }
  }

  // Geolocation needs a secure context (localhost or HTTPS), so on a phone over
  // plain LAN http it always fails — the home district from the profile is the fallback.
  async function fallbackToHomeDistrict(reason: string) {
    try {
      const user = await api.get<User>(`/v1/users/${userId}`);
      const homeId = user.driver_profile?.home_district_id as number | null | undefined;
      const home = homeId != null ? districtById.get(homeId) : undefined;
      if (home) {
        setRecError(`${reason} Считаю от домашнего района «${home.name}».`);
        await requestRecommendation(home.centroid_lat, home.centroid_lng);
        return;
      }
    } catch {
      // fall through to the plain error below
    }
    setRecError(`${reason} Укажите домашний район в настройках, чтобы получать рекомендации без геолокации.`);
    setLoadingRec(false);
  }

  function askForRecommendation() {
    if (!userId) {
      setRecError("Сначала заполните профиль в разделе «Настройки».");
      return;
    }
    setLoadingRec(true);
    setRecError(null);
    if (!("geolocation" in navigator)) {
      fallbackToHomeDistrict("Геолокация недоступна в этом браузере.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => requestRecommendation(pos.coords.latitude, pos.coords.longitude),
      () => fallbackToHomeDistrict("Не удалось определить местоположение.")
    );
  }

  return (
    <div className="flex flex-col gap-3 md:gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-lg md:text-xl font-semibold">Карта спроса</h1>
        <div className="flex items-center rounded-full border border-white/10 overflow-hidden shrink-0">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              className={`px-4 py-1.5 text-sm font-medium ${
                mode === m.value
                  ? "bg-[var(--series-1)] text-white"
                  : "text-[var(--text-secondary)]"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 overflow-x-auto no-scrollbar -mx-4 px-4">
        <span className="text-sm text-[var(--text-muted)] shrink-0">
          {mode === "surge" ? "прогноз на:" : "горизонт:"}
        </span>
        {HORIZONS.map((h) => (
          <button
            key={h}
            onClick={() => setHorizon(h)}
            data-active={horizon === h}
            className="chip shrink-0"
          >
            {h} мин
          </button>
        ))}
      </div>

      <button
        onClick={askForRecommendation}
        disabled={loadingRec}
        className="btn-primary w-full md:w-auto md:self-start"
        style={{ background: "var(--status-good)", color: "#000" }}
      >
        {loadingRec ? "Ищу лучший район..." : "🎯 Куда ехать?"}
      </button>

      {userId === null && (
        <p className="text-sm text-[var(--text-secondary)]">
          Профиль ещё не создан —{" "}
          <Link href="/onboarding" className="text-[var(--series-1)] underline">
            заполните настройки
          </Link>
          , чтобы получать персональные рекомендации.
        </p>
      )}

      {recError && <p className="text-sm" style={{ color: "var(--status-critical)" }}>{recError}</p>}

      {recommendation && (
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span
              className="text-xs font-semibold px-2.5 py-1 rounded-full"
              style={{
                background: recommendation.action === "move" ? "var(--status-warning)" : "var(--status-good)",
                color: "black",
              }}
            >
              {recommendation.action === "move" ? "→ переехать" : "✓ оставаться"}
            </span>
            <span className="font-semibold text-base">
              {districtById.get(recommendation.recommended_district_id)?.name ?? "—"}
            </span>
            <span className="text-sm text-[var(--text-secondary)] tabular">
              {(recommendation.probability * 100).toFixed(0)}% · чек ≈
              {recommendation.expected_avg_check.toFixed(0)} ₽
            </span>
          </div>
          {recommendation.rationale_text && (
            <p className="text-sm text-[var(--text-secondary)]">{recommendation.rationale_text}</p>
          )}
        </div>
      )}

      <MoscowMap
        districts={districts}
        forecastByDistrict={forecastByDistrict}
        surgeNowByDistrict={surgeNowByDistrict}
        mode={mode}
      />
    </div>
  );
}
