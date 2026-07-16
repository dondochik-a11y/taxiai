"use client";

import { useEffect, useRef, useState } from "react";
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
  degraded: "0.75",
  synthetic: "0.85",
};
const DEMAND_FILL_OPACITY = 0.55;

function stepIndex(value: number, steps: string[]): number {
  return Math.min(steps.length - 1, Math.max(0, Math.round(value * (steps.length - 1))));
}

function colorFor(value: number): string {
  return SEQUENTIAL_STEPS[stepIndex(value, SEQUENTIAL_STEPS)];
}

function surgeColorFor(norm: number): { bg: string; ink: string } {
  const idx = stepIndex(norm, SURGE_STEPS);
  // Two lightest steps need dark ink; the rest take white.
  return { bg: SURGE_STEPS[idx], ink: idx < 2 ? "#1f1410" : "#ffffff" };
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

interface MoscowMapProps {
  districts: District[];
  forecastByDistrict: Map<number, Forecast>;
  /** Current кэф per district (/v1/surge/current) — real radar readings when
   * the scraper is feeding, real prices when the Yandex key is configured,
   * synthetic feed otherwise. */
  surgeNowByDistrict?: Map<number, SurgeNow>;
  mode?: MapMode;
  onSelectDistrict?: (districtId: number) => void;
}

export function MoscowMap({
  districts,
  forecastByDistrict,
  surgeNowByDistrict,
  mode = "demand",
  onSelectDistrict,
}: MoscowMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  // Latest hover payloads + select callback, read by the polygon-layer event
  // handlers that are bound exactly once (so listeners never stack up).
  const hoverInfoRef = useRef<Map<number, HoverInfo>>(new Map());
  const onSelectRef = useRef<MoscowMapProps["onSelectDistrict"]>(onSelectDistrict);
  onSelectRef.current = onSelectDistrict;

  const [mapReady, setMapReady] = useState(false);
  const [shapes, setShapes] = useState<DistrictShapeCollection | null>(null);
  const [hovered, setHovered] = useState<HoverInfo | null>(null);

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
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => setMapReady(true));
    mapRef.current = map;
  }, []);

  // Polygon fills + fallback circle markers, rebuilt whenever data changes.
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

    const styled = districts.map((d) => {
      const forecast = forecastByDistrict.get(d.id);
      const surgeNow = surgeNowByDistrict?.get(d.id);
      const demand = forecast?.predicted_demand_level ?? 0;
      // The radar shows the CURRENT кэф when the live feed has it; the model
      // forecast is the fallback (and stays available in the hover panel).
      const surge = surgeNow?.surge ?? forecast?.predicted_surge ?? SURGE_MIN;
      const surgeNorm = Math.min(1, Math.max(0, (surge - SURGE_MIN) / (SURGE_MAX - SURGE_MIN)));
      const freshness = freshnessOf(surgeNow?.source);
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
        fill = colorFor(demand);
        fillOpacity = DEMAND_FILL_OPACITY;
      }
      return { d, forecast, surgeNow, demand, surge, surgeNorm, freshness, shape, fill, fillOpacity, ink };
    });

    // --- polygon layers ---------------------------------------------------
    if (mapReady) {
      const fc = {
        type: "FeatureCollection" as const,
        features: styled
          .filter((s) => s.shape)
          .map((s) => ({
            type: "Feature" as const,
            properties: {
              district_id: s.d.id,
              fill: s.fill,
              fill_opacity: s.fillOpacity,
            },
            geometry: s.shape!.geometry,
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

    // --- markers: circles for polygon-less districts (rail/airport hubs,
    // or everything while the asset loads); compact кэф label chips at the
    // centroids of polygon districts in surge mode --------------------------
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    styled.forEach((s) => {
      const { d, forecast, surgeNow } = s;
      const hasPolygon = Boolean(s.shape) && mapReady;
      if (hasPolygon && mode !== "surge") return; // the fill carries demand

      const el = document.createElement("div");
      el.style.cursor = "pointer";
      el.style.display = "flex";
      el.style.alignItems = "center";
      el.style.justifyContent = "center";
      if (mode === "surge") {
        el.style.background = s.fill;
        el.style.color = s.ink;
        el.style.border = "1px solid rgba(0,0,0,0.35)";
        el.style.opacity = MARKER_OPACITY[s.freshness];
        el.style.font = "600 10px/1 system-ui, sans-serif";
        el.textContent = s.surge.toFixed(1);
        if (hasPolygon) {
          // Label chip over the polygon — the number is the payload, the
          // fill already encodes intensity.
          el.style.borderRadius = "999px";
          el.style.padding = "3px 6px";
        } else {
          const size = 22 + s.surgeNorm * 14;
          el.style.borderRadius = "50%";
          el.style.width = `${size}px`;
          el.style.height = `${size}px`;
        }
      } else {
        const size = 16 + s.demand * 20;
        el.style.borderRadius = "50%";
        el.style.width = `${size}px`;
        el.style.height = `${size}px`;
        el.style.background = s.fill;
        el.style.border = "2px solid rgba(255,255,255,0.4)";
      }

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([d.centroid_lng, d.centroid_lat])
        .addTo(map);

      el.addEventListener("mouseenter", () => setHovered({ district: d, forecast, surgeNow }));
      el.addEventListener("mouseleave", () => setHovered(null));
      el.addEventListener("click", (ev) => {
        // Don't let the tap fall through to the polygon underneath.
        ev.stopPropagation();
        setHovered({ district: d, forecast, surgeNow });
        onSelectRef.current?.(d.id);
      });

      markersRef.current.push(marker);
    });
  }, [districts, forecastByDistrict, surgeNowByDistrict, mode, shapes, mapReady]);

  // Highlight the hovered polygon with a bright outline.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.getLayer(HOVER_LAYER)) return;
    map.setFilter(HOVER_LAYER, ["==", ["get", "district_id"], hovered?.district.id ?? -1]);
  }, [hovered, mapReady]);

  const legendSteps = mode === "surge" ? SURGE_STEPS : SEQUENTIAL_STEPS;
  const hoveredAgo = hovered?.surgeNow ? agoLabel(hovered.surgeNow.observed_at) : null;

  return (
    <div className="relative rounded-2xl overflow-hidden border border-white/10">
      <div ref={containerRef} className="w-full h-[56dvh] md:h-[520px]" />
      <div className="absolute bottom-12 md:bottom-3 left-3 bg-black/70 border border-white/10 rounded-lg px-3 py-2 text-xs text-[var(--text-secondary)]">
        <div className="flex items-center gap-1">
          <span>{mode === "surge" ? "кэф: ×1.0" : "спрос: меньше"}</span>
          {legendSteps.map((c) => (
            <span key={c} className="w-3 h-3 rounded-full inline-block" style={{ background: c }} />
          ))}
          <span>{mode === "surge" ? "×2.8" : "больше"}</span>
        </div>
        {mode === "surge" && (
          <div className="text-[var(--text-muted)] mt-1">бледные районы — данные не в реальном времени</div>
        )}
      </div>
      {hovered && (
        <div className="absolute top-3 left-3 right-3 md:right-auto bg-black/85 backdrop-blur border border-white/10 rounded-xl px-3.5 py-2.5 text-sm text-[var(--text-primary)] md:max-w-xs">
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
              <div className="text-[var(--text-muted)]">прогноз через {hovered.forecast.horizon_minutes} мин</div>
            </div>
          ) : (
            !hovered.surgeNow && <div className="text-[var(--text-muted)]">нет прогноза</div>
          )}
        </div>
      )}
    </div>
  );
}
