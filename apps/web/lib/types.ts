// Hand-written to mirror apps/api/app/schemas/*.py. For a larger surface this
// should be generated from the backend's OpenAPI schema (openapi-typescript);
// kept manual for this MVP pass to avoid adding a codegen step for ~7 endpoints.

export interface District {
  id: number;
  name: string;
  name_en: string | null;
  okrug: string | null;
  centroid_lat: number;
  centroid_lng: number;
  airport_nearby: boolean;
  metro_stations_count: number | null;
}

export interface SurgeNow {
  district_id: number;
  surge: number;
  observed_at: string;
  // "radar" = real kef from the Радар-кэфа app (fresh), "radar_stale" = same
  // but 45–180 min old, "radar_near" = median of nearest radar-covered
  // districts, "live" = derived from real Yandex Taxi prices,
  // "synthetic" = generated feed (only when the radar is fully down)
  source: "radar" | "radar_stale" | "radar_near" | "live" | "synthetic";
}

export interface Forecast {
  district_id: number;
  generated_at: string;
  horizon_minutes: number;
  target_time: string;
  predicted_demand_level: number;
  predicted_surge: number;
  predicted_avg_check: number;
  predicted_wait_time_seconds: number;
  model_version: string;
}

export interface DailyPlanWindow {
  start_hour: number;
  end_hour: number;
}

export interface Trip {
  id: string;
  start_time: string;
  end_time: string;
  start_district_id: number;
  end_district_id: number;
  distance_km: number;
  duration_seconds: number;
  time_to_pickup_seconds: number;
  wait_time_seconds: number;
  price: number;
  tariff: string;
  surge_multiplier_at_start: number | null;
}

export interface AiTripAnalysis {
  summary_text: string;
  estimated_missed_earnings: number | null;
  suggested_action: string | null;
  model_used: string;
}

export interface FinanceSummary {
  summary_date: string;
  gross_income: number;
  net_income: number;
  fuel_cost: number;
  rental_cost: number;
  wash_cost: number;
  fines_cost: number;
  tax_estimate: number;
  depreciation_estimate: number;
  trips_count: number;
  online_hours: number;
  income_per_hour: number;
  income_per_km: number;
}

export interface Recommendation {
  id: string;
  current_district_id: number;
  recommended_district_id: number;
  recommended_horizon_minutes: number;
  action: "stay" | "move";
  probability: number;
  expected_avg_check: number;
  rationale_text: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface DriverProfileIn {
  car_make?: string | null;
  car_model?: string | null;
  car_year?: number | null;
  tariff_plan?: string;
  fuel_type?: string;
  fuel_consumption_l_per_100km?: number;
  fuel_price_per_liter?: number;
  rental_cost_per_day?: number | null;
  rental_cost_per_week?: number | null;
  work_schedule?: Record<string, string[]>;
  home_district_id?: number | null;
}

export interface UserCreate {
  city?: string;
  email?: string | null;
  phone?: string | null;
  telegram_id?: number | null;
  driver_profile: DriverProfileIn;
}

export interface User {
  id: string;
  city: string;
  email: string | null;
  phone: string | null;
  telegram_id: number | null;
  driver_profile: (DriverProfileIn & Record<string, unknown>) | null;
}
