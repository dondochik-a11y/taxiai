"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { District, Forecast, SurgeNow } from "@/lib/types";

// District polygons aren't exposed by the API (the backend only has small
// placeholder squares, not real administrative boundaries — see
// packages/shared/constants/moscow_districts.json). Rendering those as if
// they were real shapes would be more misleading than honest, so demand is
// shown as sequential-hue circle markers at each district's centroid instead
// — a legitimate point-referenced choropleth alternative, and no Yandex Maps
// key is needed since this only renders open base tiles + client-side data.
const SEQUENTIAL_STEPS = ["#104281", "#184f95", "#256abf", "#3987e5", "#86b6ef"];

// Surge radar: a second, warm sequential ramp (light→dark, single hue family)
// so the two map modes are never confusable. The lightest steps sit below 3:1
// contrast on the light OSM tiles, which is why surge markers always carry the
// numeric label — the label is the required relief, not decoration.
const SURGE_STEPS = ["#fc9272", "#fb6a4a", "#ef3b2c", "#cb181d", "#99000d"];
// Surge is derived as 1 + demand_level * 1.8 (see the backend forecast job),
// so ×1.0..×2.8 is the full range the model can emit.
const SURGE_MIN = 1.0;
const SURGE_MAX = 2.8;

export type MapMode = "demand" | "surge";

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

interface MoscowMapProps {
  districts: District[];
  forecastByDistrict: Map<number, Forecast>;
  /** Current кэф per district (/v1/surge/current) — real prices when the
   * Yandex key is configured, synthetic feed otherwise. */
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
  const [hovered, setHovered] = useState<{
    district: District;
    forecast: Forecast | undefined;
    surgeNow: SurgeNow | undefined;
  } | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = new maplibregl.Map({
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
    });
    mapRef.current.addControl(new maplibregl.NavigationControl(), "top-right");
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    districts.forEach((d) => {
      const forecast = forecastByDistrict.get(d.id);
      const surgeNow = surgeNowByDistrict?.get(d.id);
      const demand = forecast?.predicted_demand_level ?? 0;
      // The radar shows the CURRENT кэф when the live feed has it; the model
      // forecast is the fallback (and stays available in the hover panel).
      const surge = surgeNow?.surge ?? forecast?.predicted_surge ?? SURGE_MIN;
      const surgeNorm = Math.min(1, Math.max(0, (surge - SURGE_MIN) / (SURGE_MAX - SURGE_MIN)));

      const el = document.createElement("div");
      el.style.borderRadius = "50%";
      el.style.cursor = "pointer";
      el.style.display = "flex";
      el.style.alignItems = "center";
      el.style.justifyContent = "center";
      if (mode === "surge") {
        const { bg, ink } = surgeColorFor(surgeNorm);
        const size = 22 + surgeNorm * 14;
        el.style.width = `${size}px`;
        el.style.height = `${size}px`;
        el.style.background = bg;
        el.style.border = "1px solid rgba(0,0,0,0.35)";
        el.style.color = ink;
        el.style.font = "600 10px/1 system-ui, sans-serif";
        el.textContent = surge.toFixed(1);
      } else {
        const size = 16 + demand * 20;
        el.style.width = `${size}px`;
        el.style.height = `${size}px`;
        el.style.background = colorFor(demand);
        el.style.border = "2px solid rgba(255,255,255,0.4)";
      }

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([d.centroid_lng, d.centroid_lat])
        .addTo(map);

      el.addEventListener("mouseenter", () => setHovered({ district: d, forecast, surgeNow }));
      el.addEventListener("mouseleave", () => setHovered(null));
      el.addEventListener("click", () => onSelectDistrict?.(d.id));

      markersRef.current.push(marker);
    });
  }, [districts, forecastByDistrict, surgeNowByDistrict, mode, onSelectDistrict]);

  const legendSteps = mode === "surge" ? SURGE_STEPS : SEQUENTIAL_STEPS;

  return (
    <div className="relative rounded-lg overflow-hidden border border-white/10">
      <div ref={containerRef} className="w-full h-[520px]" />
      <div className="absolute bottom-3 left-3 bg-black/70 border border-white/10 rounded px-3 py-2 text-xs text-[var(--text-secondary)] flex items-center gap-1">
        <span>{mode === "surge" ? "кэф: ×1.0" : "спрос: меньше"}</span>
        {legendSteps.map((c) => (
          <span key={c} className="w-3 h-3 rounded-full inline-block" style={{ background: c }} />
        ))}
        <span>{mode === "surge" ? "×2.8" : "больше"}</span>
      </div>
      {hovered && (
        <div className="absolute top-3 left-3 bg-black/80 border border-white/10 rounded px-3 py-2 text-sm text-[var(--text-primary)] max-w-xs">
          <div className="font-semibold">{hovered.district.name}</div>
          {hovered.surgeNow && (
            <div className="text-[var(--text-secondary)] tabular">
              кэф сейчас ×{hovered.surgeNow.surge.toFixed(1)}{" "}
              <span className="text-[var(--text-muted)]">
                ({hovered.surgeNow.source === "live" ? "реальные цены Яндекс Go" : "синтетические данные"})
              </span>
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
