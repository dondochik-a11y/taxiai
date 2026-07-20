"use client";

import { memo, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { District, Forecast, SurgeNow } from "@/lib/types";
import {
  loadDistrictShapes,
  normalizeDistrictName,
  type DistrictShapeCollection,
} from "./districtGeo";

// Districts are drawn as real boundary polygons from the static asset
// public/moscow-districts.geojson (OSM admin_level=8, see districtGeo.ts).
// Districts without a boundary — the rail-station/airport demand hubs, or
// everything if the asset fails to load — keep the original circle markers
// at their centroids, so nothing ever disappears from the map.
const SEQUENTIAL_STEPS = ["#104281", "#184f95", "#256abf", "#3987e5", "#86b6ef"];

// Surge radar: a second, warm sequential ramp (light→dark, single hue family)
// so the two map modes are never confusable. The lightest steps sit below 3:1
// contrast on the light OSM tiles, which is why surge districts always carry
// the numeric label — the label is the required relief, not decoration.
const SURGE_STEPS = ["#fc9272", "#fb6a4a", "#ef3b2c", "#cb181d", "#99000d"];
// Surge is derived as 1 + demand_level * 1.8 (see the backend forecast job),
// so ×1.0..×2.8 is the full range the model can emit.
const SURGE_MIN = 1.0;
const SURGE_MAX = 2.8;

const SHAPE_SOURCE = "districts";
const FILL_LAYER = "district-fills";
const OUTLINE_LAYER = "district-outlines";
const STALE_LAYER = "district-stale-outline";
const HOVER_LAYER = "district-hover-outline";

export type MapMode = "demand" | "surge";

const SOURCE_LABELS: Record<SurgeNow["source"], string> = {
  radar: "реальный кэф (Радар)",
  radar_stale: "реальный кэф (Радар, >45 мин назад)",
  radar_near: "реальный кэф соседних районов",
  live: "реальные цены Яндекс Go",
  synthetic: "синтетические данные",
};

// Data-freshness tiers for surge mode: real readings render at full strength,
// stale/neighbour-derived ones fade, synthetic (or no feed at all, when the
// кэф falls back to the model forecast) also desaturates hard — the map must
// never present degraded data as real.
type Freshness = "fresh" | "degraded" | "synthetic";

function freshnessOf(source: SurgeNow["source"] | undefined): Freshness {
  if (source === "radar" || source === "live") return "fresh";
  if (source === "radar_stale" || source === "radar_near") return "degraded";
  return "synthetic";
}

const FILL_OPACITY: Record<Freshness, number> = {
  fresh: 0.62,
  degraded: 0.36,
  synthetic: 0.28,
};
// The numeric label stays readable in every tier — it is the required relief
// for the low-contrast light ramp steps — so markers fade much less than fills.
const MARKER_OPACITY: Record<Freshness, string> = {
  fresh: "1",
  degraded: "0.8",
  synthetic: "0.85",
};
const DEMAND_FILL_OPACITY = 0.55;

// Yandex Maps routing deep link (from my location → centroid, driving).
function yandexRouteUrl(lat: number, lng: number): string {
  return `https://yandex.ru/maps/?rtext=~${lat},${lng}&rtt=auto`;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    !!window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function stepIndex(value: number, steps: string[]): number {
  return Math.min(steps.length - 1, Math.max(0, Math.round(value * (steps.length - 1))));
}

function colorFor(value: number): string {
  return SEQUENTIAL_STEPS[stepIndex(value, SEQUENTIAL_STEPS)];
}

function surgeColorFor(norm: number): { bg: string; ink: string } {
  const idx = stepIndex(norm, SURGE_STEPS);
  // The three lightest steps need dark ink: white on the mid step #ef3b2c is
  // only 3.94:1 and fails AA, so the dark-ink threshold is idx < 3.
  return { bg: SURGE_STEPS[idx], ink: idx < 3 ? "#1f1410" : "#ffffff" };
}

/** Mix a hex color toward its own gray, keeping luminance (synthetic tier). */
function desaturate(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const gray = 0.299 * r + 0.587 * g + 0.114 * b;
  const mix = (c: number) => Math.round(c + (gray - c) * amount);
  return `rgb(${mix(r)},${mix(g)},${mix(b)})`;
}

/** «обновлено N мин назад» from an ISO timestamp (backend emits UTC). */
function agoLabel(iso: string): string | null {
  // Defensive: a naive timestamp (no zone suffix) is UTC on this backend.
  const hasZone = /Z$|[+-]\d\d:?\d\d$/.test(iso);
  const t = new Date(hasZone ? iso : `${iso}Z`).getTime();
  if (!Number.isFinite(t)) return null;
  const min = Math.round((Date.now() - t) / 60000);
  if (min < 1) return "обновлено только что";
  if (min < 60) return `обновлено ${min} мин назад`;
  return `обновлено ${Math.floor(min / 60)} ч назад`;
}

interface HoverInfo {
  district: District;
  forecast: Forecast | undefined;
  surgeNow: SurgeNow | undefined;
}

/** A district resolved to everything the map needs to paint it. */
interface StyledDistrict {
  d: District;
  demand: number;
  /** Demand rescaled to this render's actual min–max spread across districts —
   * model forecasts differ by hundredths, so the absolute 0..1 scale would
   * paint every horizon the same colour. The legend is relative («меньше…
   * больше»), which keeps this honest. */
  demandNorm: number;
  surge: number;
  surgeNorm: number;
  freshness: Freshness;
  fill: string;
  ink: string;
}

/** Visual signature of a marker — markers only re-render when this changes, so
 * the 5-min surge poll updates a handful of chips instead of rebuilding all. */
function markerSignature(
  s: StyledDistrict,
  mode: MapMode,
  hasPolygon: boolean,
  fromForecast: boolean
): string {
  const v = mode === "surge" ? s.surge.toFixed(2) : s.demandNorm.toFixed(3);
  return `${mode}|${fromForecast ? 1 : 0}|${hasPolygon ? 1 : 0}|${s.fill}|${s.ink}|${s.freshness}|${v}`;
}

function styleMarkerEl(
  el: HTMLDivElement,
  s: StyledDistrict,
  mode: MapMode,
  hasPolygon: boolean,
  fromForecast: boolean
): void {
  el.style.cursor = "pointer";
  el.style.display = "flex";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.boxSizing = "border-box";
  if (mode === "surge") {
    const stale = s.freshness !== "fresh";
    el.style.background = s.fill;
    el.style.color = s.ink;
    // Non-opacity freshness cue: a dashed border + ⚠ glyph flag "not real-time"
    // for users who can't perceive the opacity fade.
    el.style.border = stale ? "1.5px dashed rgba(20,20,25,0.7)" : "1px solid rgba(0,0,0,0.35)";
    el.style.opacity = MARKER_OPACITY[s.freshness];
    el.style.font = "600 12px/1 system-ui, sans-serif";
    const glyph = s.freshness === "synthetic" ? "⚠ " : "";
    el.textContent = `${glyph}${s.surge.toFixed(1)}`;
    if (hasPolygon) {
      el.style.borderRadius = "999px";
      el.style.padding = "3px 7px";
      el.style.width = "";
      el.style.height = "";
    } else {
      const size = 28 + s.surgeNorm * 16;
      el.style.borderRadius = "50%";
      el.style.width = `${size}px`;
      el.style.height = `${size}px`;
      el.style.padding = "";
    }
    el.setAttribute(
      "aria-label",
      `${s.d.name}: ${fromForecast ? "прогноз кэфа" : "кэф"} ×${s.surge.toFixed(1)}${
        stale ? ", данные не в реальном времени" : ""
      }`
    );
  } else {
    const size = 16 + s.demandNorm * 20;
    el.style.borderRadius = "50%";
    el.style.width = `${size}px`;
    el.style.height = `${size}px`;
    el.style.background = s.fill;
    el.style.color = "";
    el.style.border = "2px solid rgba(255,255,255,0.4)";
    el.style.opacity = "1";
    el.style.font = "";
    el.style.padding = "";
    el.textContent = "";
    el.setAttribute("aria-label", `${s.d.name}: спрос ${(s.demand * 100).toFixed(0)}%`);
  }
}

interface MoscowMapProps {
  districts: District[];
  forecastByDistrict: Map<number, Forecast>;
  /** Current кэф per district (/v1/surge/current) — real radar readings when
   * the scraper is feeding, real prices when the Yandex key is configured,
   * synthetic feed otherwise. */
  surgeNowByDistrict?: Map<number, SurgeNow>;
  mode?: MapMode;
  /** Surge mode only: paint the map by the selected-horizon model forecast
   * instead of the live кэф feed (the «прогноз N мин» chips). */
  surgeFromForecast?: boolean;
  onSelectDistrict?: (districtId: number) => void;
  /** Deep-link focus: center the map on this district and open its info panel
   * once the map + data are ready. Unknown ids are ignored. */
  focusDistrictId?: number;
}

function MoscowMapImpl({
  districts,
  forecastByDistrict,
  surgeNowByDistrict,
  mode = "demand",
  surgeFromForecast = false,
  onSelectDistrict,
  focusDistrictId,
}: MoscowMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  // Markers are keyed by district id + carry their last visual signature, so a
  // data refresh diffs and updates only changed chips (no full teardown).
  const markersRef = useRef<Map<number, { marker: maplibregl.Marker; el: HTMLDivElement }>>(
    new Map()
  );
  const markerSigRef = useRef<Map<number, string>>(new Map());
  // Latest hover payloads + select callback, read by the polygon-layer and
  // marker event handlers that are bound exactly once (so listeners never stack
  // up and never capture stale forecast/surge data).
  const hoverInfoRef = useRef<Map<number, HoverInfo>>(new Map());
  const onSelectRef = useRef<MoscowMapProps["onSelectDistrict"]>(onSelectDistrict);
  onSelectRef.current = onSelectDistrict;

  const [mapReady, setMapReady] = useState(false);
  const [shapes, setShapes] = useState<DistrictShapeCollection | null>(null);
  const [hovered, setHovered] = useState<HoverInfo | null>(null);
  // Tracks the last district id we auto-focused via deep link, so the periodic
  // surge/forecast refreshes don't keep re-centering or re-opening the panel.
  const focusedIdRef = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    loadDistrictShapes().then((fc) => {
      if (alive) setShapes(fc);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [37.6173, 55.7558],
      zoom: 9.3,
      // Compact (collapsible) attribution so it doesn't cover the legend on
      // phone-width maps; OSM attribution stays one tap away.
      attributionControl: { compact: true },
    });
    // Zoom control lives top-right (the info panel is bottom on mobile, so it is
    // never buried); enlarged to a ≥44px touch target via the scoped <style>.
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => setMapReady(true));
    mapRef.current = map;
  }, []);

  // Polygon fills + fallback circle markers, refreshed whenever data changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const featureByName = new Map(
      (shapes?.features ?? []).map((f) => [normalizeDistrictName(f.properties.name), f])
    );

    hoverInfoRef.current = new Map(
      districts.map((d) => [
        d.id,
        {
          district: d,
          forecast: forecastByDistrict.get(d.id),
          surgeNow: surgeNowByDistrict?.get(d.id),
        },
      ])
    );

    // Demand colours are relative to this render's spread (see StyledDistrict).
    const demands = districts.map((d) => forecastByDistrict.get(d.id)?.predicted_demand_level ?? 0);
    const demandMin = Math.min(...demands);
    const demandSpread = Math.max(...demands) - demandMin;

    const styled = districts.map((d) => {
      const surgeNow = surgeNowByDistrict?.get(d.id);
      const forecast = forecastByDistrict.get(d.id);
      const demand = forecast?.predicted_demand_level ?? 0;
      const demandNorm = demandSpread > 1e-9 ? (demand - demandMin) / demandSpread : 0.5;
      // «сейчас»: the radar shows the CURRENT кэф when the live feed has it,
      // model forecast as fallback. «прогноз N мин»: forecast first — that is
      // what the user asked to see (freshness cues are for live data only).
      const surge = surgeFromForecast
        ? forecast?.predicted_surge ?? surgeNow?.surge ?? SURGE_MIN
        : surgeNow?.surge ?? forecast?.predicted_surge ?? SURGE_MIN;
      const surgeNorm = Math.min(1, Math.max(0, (surge - SURGE_MIN) / (SURGE_MAX - SURGE_MIN)));
      const freshness: Freshness = surgeFromForecast ? "fresh" : freshnessOf(surgeNow?.source);
      const shape = featureByName.get(normalizeDistrictName(d.name));

      let fill: string;
      let fillOpacity: number;
      let ink = "#ffffff";
      if (mode === "surge") {
        const c = surgeColorFor(surgeNorm);
        fill = freshness === "synthetic" ? desaturate(c.bg, 0.65) : c.bg;
        ink = c.ink;
        fillOpacity = FILL_OPACITY[freshness];
      } else {
        fill = colorFor(demandNorm);
        fillOpacity = DEMAND_FILL_OPACITY;
      }
      const s: StyledDistrict = { d, demand, demandNorm, surge, surgeNorm, freshness, fill, ink };
      return { s, shape, fillOpacity };
    });

    // --- polygon layers ---------------------------------------------------
    if (mapReady) {
      const fc = {
        type: "FeatureCollection" as const,
        features: styled
          .filter((x) => x.shape)
          .map((x) => ({
            type: "Feature" as const,
            properties: {
              district_id: x.s.d.id,
              fill: x.s.fill,
              fill_opacity: x.fillOpacity,
              // Categorical (non-opacity) freshness flag → dashed outline.
              stale: mode === "surge" && x.s.freshness !== "fresh",
            },
            geometry: x.shape!.geometry,
          })),
      };
      const source = map.getSource(SHAPE_SOURCE) as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(fc);
      } else {
        map.addSource(SHAPE_SOURCE, { type: "geojson", data: fc });
        map.addLayer({
          id: FILL_LAYER,
          type: "fill",
          source: SHAPE_SOURCE,
          paint: {
            "fill-color": ["get", "fill"],
            "fill-opacity": ["get", "fill_opacity"],
          },
        });
        map.addLayer({
          id: OUTLINE_LAYER,
          type: "line",
          source: SHAPE_SOURCE,
          paint: {
            "line-color": "rgba(20,20,25,0.45)",
            "line-width": 0.8,
          },
        });
        // Dashed amber outline for "not real-time" districts — a categorical
        // cue that survives colour-blindness and the opacity fade.
        map.addLayer({
          id: STALE_LAYER,
          type: "line",
          source: SHAPE_SOURCE,
          filter: ["==", ["get", "stale"], true],
          paint: {
            "line-color": "rgba(250,178,25,0.95)",
            "line-width": 1.6,
            "line-dasharray": [2, 2],
          },
        });
        map.addLayer({
          id: HOVER_LAYER,
          type: "line",
          source: SHAPE_SOURCE,
          filter: ["==", ["get", "district_id"], -1],
          paint: {
            "line-color": "rgba(255,255,255,0.95)",
            "line-width": 2,
          },
        });

        const pick = (e: maplibregl.MapLayerMouseEvent): HoverInfo | undefined => {
          const id = e.features?.[0]?.properties?.district_id as number | undefined;
          return id != null ? hoverInfoRef.current.get(id) : undefined;
        };
        map.on("mousemove", FILL_LAYER, (e) => {
          const info = pick(e);
          map.getCanvas().style.cursor = info ? "pointer" : "";
          setHovered(info ?? null);
        });
        map.on("mouseleave", FILL_LAYER, () => {
          map.getCanvas().style.cursor = "";
          setHovered(null);
        });
        // On touch devices there is no hover — tap opens the same info panel.
        map.on("click", FILL_LAYER, (e) => {
          const info = pick(e);
          if (info) {
            setHovered(info);
            onSelectRef.current?.(info.district.id);
          }
        });
      }
    }

    // --- markers: circles for polygon-less districts (rail/airport hubs, or
    // everything while the asset loads); compact кэф label chips at the
    // centroids of polygon districts in surge mode. Diffed by district id so a
    // 5-min poll touches only the chips whose value changed. ------------------
    const needed = new Map<number, { s: StyledDistrict; hasPolygon: boolean }>();
    styled.forEach((x) => {
      const hasPolygon = Boolean(x.shape) && mapReady;
      if (hasPolygon && mode !== "surge") return; // the fill carries demand
      needed.set(x.s.d.id, { s: x.s, hasPolygon });
    });

    // Remove markers that no longer apply (mode switch, district gone).
    for (const [id, entry] of markersRef.current) {
      if (!needed.has(id)) {
        entry.marker.remove();
        markersRef.current.delete(id);
        markerSigRef.current.delete(id);
      }
    }

    needed.forEach(({ s, hasPolygon }, id) => {
      const sig = markerSignature(s, mode, hasPolygon, surgeFromForecast);
      const existing = markersRef.current.get(id);
      if (existing) {
        if (markerSigRef.current.get(id) !== sig) {
          styleMarkerEl(existing.el, s, mode, hasPolygon, surgeFromForecast);
          markerSigRef.current.set(id, sig);
        }
        return;
      }
      const el = document.createElement("div");
      styleMarkerEl(el, s, mode, hasPolygon, surgeFromForecast);
      el.setAttribute("role", "button");
      el.tabIndex = 0;
      const activate = (ev: Event) => {
        ev.stopPropagation();
        setHovered(hoverInfoRef.current.get(id) ?? null);
        onSelectRef.current?.(id);
      };
      el.addEventListener("mouseenter", () => setHovered(hoverInfoRef.current.get(id) ?? null));
      el.addEventListener("mouseleave", () => setHovered(null));
      el.addEventListener("click", activate);
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          activate(ev);
        }
      });
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([s.d.centroid_lng, s.d.centroid_lat])
        .addTo(map);
      markersRef.current.set(id, { marker, el });
      markerSigRef.current.set(id, sig);
    });
  }, [districts, forecastByDistrict, surgeNowByDistrict, mode, surgeFromForecast, shapes, mapReady]);

  // Highlight the hovered polygon with a bright outline.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.getLayer(HOVER_LAYER)) return;
    map.setFilter(HOVER_LAYER, ["==", ["get", "district_id"], hovered?.district.id ?? -1]);
  }, [hovered, mapReady]);

  // Deep-link focus: once the map and district list are ready, center on the
  // requested district and open its info panel (as if tapped). We only act when
  // the id itself changes — the ref guard keeps 5-min data refreshes from
  // re-centering. An id with no matching district is silently ignored, and the
  // effect retries harmlessly until the districts finish loading.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || focusDistrictId == null) return;
    if (focusedIdRef.current === focusDistrictId) return;
    const d = districts.find((x) => x.id === focusDistrictId);
    if (!d) return;
    focusedIdRef.current = focusDistrictId;
    const dest = { center: [d.centroid_lng, d.centroid_lat] as [number, number], zoom: 11.5 };
    if (prefersReducedMotion()) map.jumpTo(dest);
    else map.flyTo({ ...dest, duration: 800 });
    setHovered({
      district: d,
      forecast: forecastByDistrict.get(d.id),
      surgeNow: surgeNowByDistrict?.get(d.id),
    });
  }, [focusDistrictId, mapReady, districts, forecastByDistrict, surgeNowByDistrict]);

  // Shared select+recenter used by the keyboard/SR district list.
  const selectDistrict = (id: number) => {
    const d = districts.find((x) => x.id === id);
    if (!d) return;
    const map = mapRef.current;
    if (map && mapReady) {
      const dest = { center: [d.centroid_lng, d.centroid_lat] as [number, number], zoom: 11.5 };
      if (prefersReducedMotion()) map.jumpTo(dest);
      else map.flyTo({ ...dest, duration: 800 });
    }
    setHovered(
      hoverInfoRef.current.get(id) ?? {
        district: d,
        forecast: forecastByDistrict.get(id),
        surgeNow: surgeNowByDistrict?.get(id),
      }
    );
    onSelectRef.current?.(id);
  };

  const legendSteps = mode === "surge" ? SURGE_STEPS : SEQUENTIAL_STEPS;
  const hoveredAgo = hovered?.surgeNow ? agoLabel(hovered.surgeNow.observed_at) : null;

  return (
    <div
      className="taxi-map relative rounded-2xl overflow-hidden border border-white/10"
      role="region"
      aria-label="Карта спроса по районам Москвы"
    >
      {/* Scoped: give the MapLibre zoom control a ≥44px touch target. */}
      <style>{`
        .taxi-map .maplibregl-ctrl-group button {
          width: 44px;
          height: 44px;
        }
        .taxi-map .maplibregl-ctrl-group button .maplibregl-ctrl-icon {
          transform: scale(1.25);
        }
      `}</style>
      <div ref={containerRef} className="w-full h-[56dvh] md:h-[520px]" />

      {/* Keyboard/screen-reader access to the data the mouse-only map hides. */}
      <ul className="sr-only">
        {districts.map((d) => {
          const sn = surgeNowByDistrict?.get(d.id);
          const fc = forecastByDistrict.get(d.id);
          const parts = [d.name];
          if (sn) parts.push(`кэф ×${sn.surge.toFixed(1)} (${SOURCE_LABELS[sn.source]})`);
          if (fc) parts.push(`спрос ${(fc.predicted_demand_level * 100).toFixed(0)}%`);
          return (
            <li key={d.id}>
              <button type="button" onClick={() => selectDistrict(d.id)}>
                {parts.join(", ")}
              </button>
            </li>
          );
        })}
      </ul>

      {/* Legend: top-left on mobile (info panel owns the bottom), bottom-left on desktop. */}
      <div
        className="absolute top-3 left-3 md:top-auto md:bottom-3 backdrop-blur border border-white/10 rounded-lg px-3 py-2 text-xs text-[var(--text-secondary)]"
        style={{ background: "var(--overlay)" }}
      >
        <div className="flex items-center gap-1">
          <span>{mode === "surge" ? "кэф: ×1.0" : "спрос: меньше"}</span>
          {legendSteps.map((c) => (
            <span key={c} className="w-3 h-3 rounded-full inline-block" style={{ background: c }} />
          ))}
          <span>{mode === "surge" ? "×2.8" : "больше"}</span>
        </div>
        {mode === "surge" && !surgeFromForecast && (
          <div className="text-[var(--text-muted)] mt-1 flex items-center gap-1.5">
            <span
              className="inline-block w-4 h-0 align-middle"
              style={{ borderTop: "1.5px dashed rgba(250,178,25,0.95)" }}
              aria-hidden="true"
            />
            <span>⚠ / пунктир — данные не в реальном времени</span>
          </div>
        )}
        {mode === "surge" && surgeFromForecast && (
          <div className="text-[var(--text-muted)] mt-1">прогноз модели, не live-данные</div>
        )}
      </div>

      {/* Info panel: bottom (thumb zone) on mobile, top-left on desktop. */}
      {hovered && (
        <div
          className="absolute bottom-3 left-3 right-3 md:right-auto md:bottom-auto md:top-3 backdrop-blur border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-[var(--text-primary)] md:max-w-xs"
          style={{ background: "var(--overlay)" }}
        >
          <button
            className="absolute top-1.5 right-2.5 text-[var(--text-muted)] md:hidden"
            onClick={() => setHovered(null)}
            aria-label="Закрыть"
          >
            ✕
          </button>
          <div className="font-semibold">{hovered.district.name}</div>
          {hovered.surgeNow && (
            <div className="text-[var(--text-secondary)] tabular">
              кэф сейчас ×{hovered.surgeNow.surge.toFixed(1)}{" "}
              <span className="text-[var(--text-muted)]">
                ({SOURCE_LABELS[hovered.surgeNow.source]})
              </span>
              {hoveredAgo && <div className="text-[var(--text-muted)]">{hoveredAgo}</div>}
            </div>
          )}
          {hovered.forecast ? (
            <div className="text-[var(--text-secondary)] tabular">
              кэф ≈×{hovered.forecast.predicted_surge.toFixed(1)} · спрос{" "}
              {(hovered.forecast.predicted_demand_level * 100).toFixed(0)}% · чек ≈
              {hovered.forecast.predicted_avg_check.toFixed(0)} ₽ · ожидание ~
              {Math.round(hovered.forecast.predicted_wait_time_seconds / 60)} мин
              <div className="text-[var(--text-muted)]">
                прогноз через {hovered.forecast.horizon_minutes} мин
              </div>
            </div>
          ) : (
            !hovered.surgeNow && <div className="text-[var(--text-muted)]">нет прогноза</div>
          )}
          <a
            href={yandexRouteUrl(hovered.district.centroid_lat, hovered.district.centroid_lng)}
            target="_blank"
            rel="noopener noreferrer"
            className="chip mt-2"
          >
            Проехать сюда
          </a>
        </div>
      )}
    </div>
  );
}

export const MoscowMap = memo(MoscowMapImpl);
