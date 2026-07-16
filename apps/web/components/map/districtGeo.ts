// Loader + name matching for the static district-boundary asset.
//
// public/moscow-districts.geojson holds real administrative boundaries for
// the 125 Moscow районы (old Moscow + Zelenograd), built from OSM
// admin_level=8 relations and simplified to ~110 KB (Douglas-Peucker
// ~0.00035°, 5-decimal coordinates). Each feature's properties.name is the
// canonical seed name from packages/shared/constants/moscow_districts.json,
// but matching still goes through normalizeDistrictName() on both sides so
// ё/е, dashes and «район …» prefixes never break it. The 5 non-district
// demand hubs (rail stations, airports) have no boundary on purpose — the
// map falls back to centroid circles for anything unmatched.

import type { MultiPolygon, Polygon } from "geojson";

export interface DistrictShapeFeature {
  type: "Feature";
  properties: { name: string };
  geometry: Polygon | MultiPolygon;
}

export interface DistrictShapeCollection {
  type: "FeatureCollection";
  features: DistrictShapeFeature[];
}

/** ё→е, strip «район»/«поселение»/«муниципальный округ», drop punctuation. */
export function normalizeDistrictName(name: string): string {
  return name
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/\b(поселение|район|муниципальный округ)\b/g, "")
    .replace(/[^а-яa-z0-9]+/g, "");
}

let shapesPromise: Promise<DistrictShapeCollection | null> | null = null;

/** Fetch the boundary asset once per page load; null on any failure so the
 * map can silently fall back to centroid circles. */
export function loadDistrictShapes(): Promise<DistrictShapeCollection | null> {
  if (!shapesPromise) {
    shapesPromise = fetch("/moscow-districts.geojson")
      .then((r) => (r.ok ? (r.json() as Promise<DistrictShapeCollection>) : null))
      .catch(() => null);
  }
  return shapesPromise;
}
