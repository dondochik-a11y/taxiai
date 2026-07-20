"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { District, Forecast, Recommendation, SurgeNow, User } from "@/lib/types";
import { MoscowMap, type MapMode } from "@/components/map/MoscowMap";

const HORIZONS = [15, 30, 60, 120];
const MODES: { value: MapMode; label: string }[] = [
  { value: "demand", label: "спрос" },
  { value: "surge", label: "кэф" },
];
const BOT_URL = "https://t.me/taxiai1bot";

// Yandex Maps routing deep link: empty origin (~) = "from my location", to the
// district centroid, driving mode — closes the info→action dead-end.
function yandexRouteUrl(lat: number, lng: number): string {
  return `https://yandex.ru/maps/?rtext=~${lat},${lng}&rtt=auto`;
}

type Freshness = "fresh" | "degraded" | "synthetic";
function freshnessOf(source: SurgeNow["source"] | undefined): Freshness {
  if (source === "radar" || source === "live") return "fresh";
  if (source === "radar_stale" || source === "radar_near") return "degraded";
  return "synthetic";
}

function fmtClock(d: Date): string {
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

// Reads the `?district=<id>` deep link and the `?rec=1` shortcut. useSearchParams()
// opts the subtree out of prerendering, so it lives in its own component behind a
// <Suspense> boundary (App Router requirement) and lifts values up via callbacks.
function DeepLinkReader({
  onDistrict,
  onRec,
}: {
  onDistrict: (id: number) => void;
  onRec: () => void;
}) {
  const searchParams = useSearchParams();
  const rawDistrict = searchParams.get("district");
  const rawRec = searchParams.get("rec");
  useEffect(() => {
    if (rawDistrict == null) return;
    const id = Number(rawDistrict);
    if (Number.isInteger(id)) onDistrict(id);
  }, [rawDistrict, onDistrict]);
  useEffect(() => {
    if (rawRec === "1") onRec();
  }, [rawRec, onRec]);
  return null;
}

export default function DashboardPage() {
  const [districts, setDistricts] = useState<District[]>([]);
  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [horizon, setHorizon] = useState(30);
  const [mode, setMode] = useState<MapMode>("demand");
  // Surge mode has an extra «сейчас» view (the live radar кэф, the default);
  // picking a horizon chip switches the map to the model forecast instead.
  const [surgeNowView, setSurgeNowView] = useState(true);
  const [focusDistrictId, setFocusDistrictId] = useState<number | undefined>(undefined);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [recError, setRecError] = useState<string | null>(null);
  const [loadingRec, setLoadingRec] = useState(false);
  const [recFocus, setRecFocus] = useState(false);
  const userId = useStoredUserId();

  const [surgeNow, setSurgeNow] = useState<SurgeNow[]>([]);
  const [surgeUpdatedAt, setSurgeUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    api.get<District[]>("/v1/districts").then(setDistricts).catch(() => setDistricts([]));
  }, []);

  // The current кэф is a live feed — refresh it on the worker's 5-min cadence
  // and stamp the time so the UI can show freshness.
  useEffect(() => {
    const load = () =>
      api
        .get<SurgeNow[]>("/v1/surge/current")
        .then((s) => {
          setSurgeNow(s);
          setSurgeUpdatedAt(new Date());
        })
        .catch(() => setSurgeNow([]));
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

  // A single global data-source badge from the dominant freshness tier across
  // the live feed — "кэф в реальном времени" vs "радар не на связи".
  const sourceBadge = useMemo(() => {
    if (surgeNow.length === 0) return null;
    const tally: Record<Freshness, number> = { fresh: 0, degraded: 0, synthetic: 0 };
    surgeNow.forEach((s) => (tally[freshnessOf(s.source)] += 1));
    const dominant = (Object.keys(tally) as Freshness[]).reduce((a, b) =>
      tally[b] > tally[a] ? b : a
    );
    if (dominant === "fresh") return { text: "кэф в реальном времени", cls: "text-success" };
    if (dominant === "degraded")
      return { text: "данные радара с задержкой", cls: "text-[var(--text-secondary)]" };
    return { text: "синтетические данные — радар не на связи", cls: "text-danger" };
  }, [surgeNow]);

  // Deep link `?district=<id>`: switch to кэф mode and focus that district.
  const focusOnDistrict = useCallback((id: number) => {
    setMode("surge");
    setFocusDistrictId(id);
  }, []);
  const onRecShortcut = useCallback(() => setRecFocus(true), []);

  const requestRecommendation = useCallback(
    async (lat: number, lng: number, silent = false) => {
      try {
        const rec = await api.post<Recommendation>(`/v1/recommendations/${userId}`, {
          lat,
          lng,
          horizon_minutes: horizon,
        });
        setRecommendation(rec);
        if (silent) setRecError(null);
      } catch (err) {
        setRecError(err instanceof Error ? err.message : "Не удалось получить рекомендацию");
      } finally {
        setLoadingRec(false);
      }
    },
    [userId, horizon]
  );

  // Geolocation needs a secure context (localhost or HTTPS), so on a phone over
  // plain LAN http it always fails — the home district from the profile is the
  // fallback. On the silent auto path we degrade quietly (no error banner).
  const fallbackToHomeDistrict = useCallback(
    async (reason: string, silent = false) => {
      try {
        const user = await api.get<User>(`/v1/users/${userId}`);
        const homeId = user.driver_profile?.home_district_id as number | null | undefined;
        const home = homeId != null ? districtById.get(homeId) : undefined;
        if (home) {
          if (!silent) setRecError(`${reason} Считаю от домашнего района «${home.name}».`);
          await requestRecommendation(home.centroid_lat, home.centroid_lng, silent);
          return;
        }
      } catch {
        // fall through to the message below
      }
      if (!silent)
        setRecError(
          `${reason} Укажите домашний район в настройках, чтобы получать рекомендации без геолокации.`
        );
      setLoadingRec(false);
    },
    [userId, districtById, requestRecommendation]
  );

  const askForRecommendation = useCallback(
    (silent = false) => {
      if (!userId) {
        if (!silent) setRecError("Сначала заполните профиль в разделе «Настройки».");
        return;
      }
      setLoadingRec(true);
      if (!silent) setRecError(null);
      if (!("geolocation" in navigator)) {
        fallbackToHomeDistrict("Геолокация недоступна в этом браузере.", silent);
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => requestRecommendation(pos.coords.latitude, pos.coords.longitude, silent),
        () => fallbackToHomeDistrict("Не удалось определить местоположение.", silent)
      );
    },
    [userId, fallbackToHomeDistrict, requestRecommendation]
  );

  // GLANCEABLE ANSWER: request the recommendation automatically once we have a
  // profile and the district list (needed for the home fallback). The auto path
  // is silent — a failed geolocation must NOT greet the driver with an error;
  // it degrades to the home district. `?rec=1` (the manifest shortcut) makes the
  // first request the explicit, from-my-location one instead.
  const autoRequestedRef = useRef(false);
  useEffect(() => {
    if (autoRequestedRef.current) return;
    if (typeof userId !== "string") return;
    if (districts.length === 0) return;
    autoRequestedRef.current = true;
    askForRecommendation(!recFocus);
  }, [userId, districts.length, recFocus, askForRecommendation]);

  const recDistrict = recommendation
    ? districtById.get(recommendation.recommended_district_id)
    : undefined;
  const recSurge = recommendation
    ? surgeNowByDistrict.get(recommendation.recommended_district_id)?.surge ??
      forecastByDistrict.get(recommendation.recommended_district_id)?.predicted_surge ??
      null
    : null;
  const showHeroSkeleton = loadingRec && !recommendation;

  return (
    <div className="flex flex-col gap-3 md:gap-4">
      <Suspense fallback={null}>
        <DeepLinkReader onDistrict={focusOnDistrict} onRec={onRecShortcut} />
      </Suspense>

      {/* ---- GLANCEABLE HERO: куда ехать сейчас ---- */}
      {showHeroSkeleton ? (
        <div className="card p-5">
          <div className="skeleton h-3.5 w-32 rounded" />
          <div className="skeleton h-12 w-44 rounded mt-3" />
          <div className="skeleton h-4 w-56 rounded mt-3" />
        </div>
      ) : recommendation && recDistrict ? (
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
            куда ехать сейчас
          </div>
          <div className="mt-1.5 flex items-end justify-between gap-4">
            <div className="min-w-0">
              <div className="text-lg md:text-xl font-semibold truncate">
                {recommendation.action === "move"
                  ? `→ ехать в ${recDistrict.name}`
                  : `✓ оставаться в ${recDistrict.name}`}
              </div>
              <div className="text-sm text-[var(--text-secondary)] tabular mt-0.5">
                вероятность заказа {(recommendation.probability * 100).toFixed(0)}% · чек ≈
                {recommendation.expected_avg_check.toFixed(0)} ₽
              </div>
            </div>
            {recSurge != null && (
              <div className="text-right shrink-0">
                <div className="figure text-4xl md:text-5xl leading-none">
                  ×{recSurge.toFixed(1)}
                </div>
                <div className="text-xs text-[var(--text-muted)] mt-1">ожидаемый кэф</div>
              </div>
            )}
          </div>
          {recommendation.rationale_text && (
            <p className="text-sm text-[var(--text-secondary)] mt-2.5">
              {recommendation.rationale_text}
            </p>
          )}
          <div className="mt-3.5 flex flex-wrap gap-2">
            <button
              onClick={() => askForRecommendation(false)}
              disabled={loadingRec}
              className="btn-cta"
            >
              {loadingRec ? "Считаю..." : "Пересчитать от моего места"}
            </button>
            <a
              href={yandexRouteUrl(recDistrict.centroid_lat, recDistrict.centroid_lng)}
              target="_blank"
              rel="noopener noreferrer"
              className="chip"
            >
              Проехать сюда
            </a>
          </div>
        </div>
      ) : (
        <div className="card p-5 flex flex-col gap-3 items-start">
          <div>
            <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
              куда ехать сейчас
            </div>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              {userId === null
                ? "Заполните профиль, чтобы получить персональную рекомендацию."
                : "Нажмите, чтобы посчитать лучший район от вашего места."}
            </p>
          </div>
          {userId === null ? (
            <Link href="/onboarding" className="btn-cta">
              Заполнить профиль
            </Link>
          ) : (
            <button
              onClick={() => askForRecommendation(false)}
              disabled={loadingRec || userId === undefined}
              className="btn-cta"
            >
              {loadingRec ? "Ищу лучший район..." : "Куда ехать?"}
            </button>
          )}
        </div>
      )}

      {recError && <p className="text-sm text-danger">{recError}</p>}

      {/* ---- Map controls ---- */}
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-lg md:text-xl font-semibold">Карта спроса</h1>
        <div className="flex items-center gap-2 shrink-0" role="group" aria-label="Режим карты">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              data-active={mode === m.value}
              className="chip"
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 overflow-x-auto no-scrollbar -mx-4 px-4">
        <span className="text-sm text-[var(--text-muted)] shrink-0">
          {mode === "surge" ? "кэф:" : "горизонт:"}
        </span>
        {mode === "surge" && (
          <button
            onClick={() => setSurgeNowView(true)}
            data-active={surgeNowView}
            className="chip shrink-0"
          >
            сейчас
          </button>
        )}
        {HORIZONS.map((h) => (
          <button
            key={h}
            onClick={() => {
              setHorizon(h);
              if (mode === "surge") setSurgeNowView(false);
            }}
            data-active={horizon === h && (mode !== "surge" || !surgeNowView)}
            className="chip shrink-0"
          >
            {mode === "surge" ? `прогноз ${h} мин` : `${h} мин`}
          </button>
        ))}
      </div>

      {/* ---- Live-data status: source badge + freshness stamp ---- */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" aria-live="polite">
        {sourceBadge && <span className={sourceBadge.cls}>● {sourceBadge.text}</span>}
        {surgeUpdatedAt && (
          <span className="text-[var(--text-muted)] tabular">
            кэф обновлён {fmtClock(surgeUpdatedAt)}
          </span>
        )}
        <a
          href={BOT_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--series-1)] underline underline-offset-2 ml-auto"
          title="Уведомления и «куда ехать?» прямо в Telegram"
        >
          Открыть бота в Telegram
        </a>
      </div>

      <MoscowMap
        districts={districts}
        forecastByDistrict={forecastByDistrict}
        surgeNowByDistrict={surgeNowByDistrict}
        mode={mode}
        surgeFromForecast={mode === "surge" && !surgeNowView}
        focusDistrictId={focusDistrictId}
        onSelectDistrict={focusOnDistrict}
      />
    </div>
  );
}
