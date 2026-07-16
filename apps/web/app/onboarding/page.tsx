"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearStoredUserId, storeUserId } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import { LinkTelegram } from "@/components/LinkTelegram";
import type { District, User, UserCreate } from "@/lib/types";

const TARIFFS = [
  { value: "economy", label: "Эконом" },
  { value: "comfort", label: "Комфорт" },
  { value: "comfort_plus", label: "Комфорт+" },
  { value: "business", label: "Бизнес" },
];
const FUEL_TYPES = [
  { value: "petrol92", label: "АИ-92" },
  { value: "petrol95", label: "АИ-95" },
  { value: "diesel", label: "Дизель" },
  { value: "gas", label: "Газ" },
  { value: "electric", label: "Электро" },
];

const DEFAULTS = {
  city: "Moscow",
  carMake: "Hyundai",
  carModel: "Solaris",
  tariffPlan: "economy",
  fuelType: "petrol95",
  fuelConsumption: 8.0,
  fuelPrice: 60.0,
  rentalCostPerDay: 2500,
  homeDistrictId: "" as number | "",
  scheduleStart: "08:00",
  scheduleEnd: "20:00",
};

export default function OnboardingPage() {
  const router = useRouter();
  const storedUserId = useStoredUserId();
  const [districts, setDistricts] = useState<District[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // null — create mode; string — editing an existing profile
  const [editingId, setEditingId] = useState<string | null>(null);
  // Set (asynchronously) once the prefill request settles; with no stored id
  // there is nothing to fetch, so the render gate below skips this flag.
  const [prefillSettled, setPrefillSettled] = useState(false);

  const [city, setCity] = useState(DEFAULTS.city);
  const [carMake, setCarMake] = useState(DEFAULTS.carMake);
  const [carModel, setCarModel] = useState(DEFAULTS.carModel);
  const [tariffPlan, setTariffPlan] = useState(DEFAULTS.tariffPlan);
  const [fuelType, setFuelType] = useState(DEFAULTS.fuelType);
  const [fuelConsumption, setFuelConsumption] = useState(DEFAULTS.fuelConsumption);
  const [fuelPrice, setFuelPrice] = useState(DEFAULTS.fuelPrice);
  const [rentalCostPerDay, setRentalCostPerDay] = useState(DEFAULTS.rentalCostPerDay);
  const [homeDistrictId, setHomeDistrictId] = useState<number | "">(DEFAULTS.homeDistrictId);
  const [scheduleStart, setScheduleStart] = useState(DEFAULTS.scheduleStart);
  const [scheduleEnd, setScheduleEnd] = useState(DEFAULTS.scheduleEnd);

  useEffect(() => {
    api.get<District[]>("/v1/districts").then(setDistricts).catch(() => setDistricts([]));
  }, []);

  // With a stored id this page is the profile editor: load and prefill.
  useEffect(() => {
    if (typeof storedUserId !== "string") return; // hydrating, or no profile stored
    let cancelled = false;
    api
      .get<User>(`/v1/users/${storedUserId}`)
      .then((user) => {
        if (cancelled) return;
        setCity(user.city);
        const p = user.driver_profile;
        if (p) {
          setCarMake(p.car_make ?? "");
          setCarModel(p.car_model ?? "");
          setTariffPlan(p.tariff_plan ?? DEFAULTS.tariffPlan);
          setFuelType(p.fuel_type ?? DEFAULTS.fuelType);
          setFuelConsumption(p.fuel_consumption_l_per_100km ?? DEFAULTS.fuelConsumption);
          setFuelPrice(p.fuel_price_per_liter ?? DEFAULTS.fuelPrice);
          setRentalCostPerDay(p.rental_cost_per_day ?? DEFAULTS.rentalCostPerDay);
          setHomeDistrictId(p.home_district_id ?? "");
          const firstWindow = Object.values(p.work_schedule ?? {}).find(
            (day) => Array.isArray(day) && day.length > 0
          )?.[0];
          if (typeof firstWindow === "string" && /^\d{2}:\d{2}-\d{2}:\d{2}$/.test(firstWindow)) {
            const [start, end] = firstWindow.split("-");
            setScheduleStart(start);
            setScheduleEnd(end);
          }
        }
        setEditingId(user.id);
      })
      .catch(() => {
        // Stale id (user deleted / другая база) — fall back to create mode.
        if (!cancelled) clearStoredUserId();
      })
      .finally(() => {
        if (!cancelled) setPrefillSettled(true);
      });
    return () => {
      cancelled = true;
    };
  }, [storedUserId]);

  function resetForm() {
    setCity(DEFAULTS.city);
    setCarMake(DEFAULTS.carMake);
    setCarModel(DEFAULTS.carModel);
    setTariffPlan(DEFAULTS.tariffPlan);
    setFuelType(DEFAULTS.fuelType);
    setFuelConsumption(DEFAULTS.fuelConsumption);
    setFuelPrice(DEFAULTS.fuelPrice);
    setRentalCostPerDay(DEFAULTS.rentalCostPerDay);
    setHomeDistrictId(DEFAULTS.homeDistrictId);
    setScheduleStart(DEFAULTS.scheduleStart);
    setScheduleEnd(DEFAULTS.scheduleEnd);
  }

  function handleLogout() {
    clearStoredUserId();
    setEditingId(null);
    setSaved(false);
    setError(null);
    resetForm();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSaved(false);
    const payload: UserCreate = {
      city,
      driver_profile: {
        car_make: carMake,
        car_model: carModel,
        tariff_plan: tariffPlan,
        fuel_type: fuelType,
        fuel_consumption_l_per_100km: fuelConsumption,
        fuel_price_per_liter: fuelPrice,
        rental_cost_per_day: rentalCostPerDay,
        home_district_id: homeDistrictId === "" ? null : Number(homeDistrictId),
        work_schedule: {
          mon: [`${scheduleStart}-${scheduleEnd}`],
          tue: [`${scheduleStart}-${scheduleEnd}`],
          wed: [`${scheduleStart}-${scheduleEnd}`],
          thu: [`${scheduleStart}-${scheduleEnd}`],
          fri: [`${scheduleStart}-${scheduleEnd}`],
        },
      },
    };
    try {
      if (editingId) {
        await api.patch<User>(`/v1/users/${editingId}`, payload);
        setSaved(true);
      } else {
        const user = await api.post<User>("/v1/users", payload);
        storeUserId(user.id);
        router.push("/");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить профиль");
    } finally {
      setSubmitting(false);
    }
  }

  if (storedUserId === undefined) return null; // hydrating
  if (typeof storedUserId === "string" && !prefillSettled) return null; // prefill in flight

  const isEdit = editingId !== null;

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-lg md:text-xl font-semibold mb-1">
        {isEdit ? "Профиль" : "Настройка"}
      </h1>
      <p className="text-sm text-[var(--text-secondary)] mb-5">
        {isEdit
          ? "Измените данные и сохраните — расчёты обновятся автоматически."
          : "Заполните один раз — дальше AI всё считает автоматически."}
      </p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Section title="🚗 Машина">
          <Field label="Город">
            <input className="input" value={city} onChange={(e) => setCity(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Марка">
              <input className="input" value={carMake} onChange={(e) => setCarMake(e.target.value)} />
            </Field>
            <Field label="Модель">
              <input className="input" value={carModel} onChange={(e) => setCarModel(e.target.value)} />
            </Field>
          </div>
          <Field label="Тариф">
            <div className="flex gap-2 flex-wrap">
              {TARIFFS.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  data-active={tariffPlan === t.value}
                  className="chip"
                  onClick={() => setTariffPlan(t.value)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </Field>
        </Section>

        <Section title="⛽ Экономика">
          <Field label="Топливо">
            <div className="flex gap-2 flex-wrap">
              {FUEL_TYPES.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  data-active={fuelType === f.value}
                  className="chip"
                  onClick={() => setFuelType(f.value)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Расход, л/100км">
              <input
                type="number"
                step="0.1"
                inputMode="decimal"
                className="input"
                value={fuelConsumption}
                onChange={(e) => setFuelConsumption(Number(e.target.value))}
              />
            </Field>
            <Field label="Цена топлива, ₽/л">
              <input
                type="number"
                step="0.1"
                inputMode="decimal"
                className="input"
                value={fuelPrice}
                onChange={(e) => setFuelPrice(Number(e.target.value))}
              />
            </Field>
          </div>
          <Field label="Аренда, ₽/день">
            <input
              type="number"
              inputMode="numeric"
              className="input"
              value={rentalCostPerDay}
              onChange={(e) => setRentalCostPerDay(Number(e.target.value))}
            />
          </Field>
        </Section>

        <Section title="🕐 Смена">
          <Field label="Домашний район">
            <select
              className="input"
              value={homeDistrictId}
              onChange={(e) => setHomeDistrictId(e.target.value === "" ? "" : Number(e.target.value))}
            >
              <option value="">— не выбрано —</option>
              {districts.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Начало смены">
              <input
                type="time"
                className="input"
                value={scheduleStart}
                onChange={(e) => setScheduleStart(e.target.value)}
              />
            </Field>
            <Field label="Конец смены">
              <input
                type="time"
                className="input"
                value={scheduleEnd}
                onChange={(e) => setScheduleEnd(e.target.value)}
              />
            </Field>
          </div>
        </Section>

        {error && <p className="text-sm" style={{ color: "var(--status-critical)" }}>{error}</p>}
        {saved && (
          <p className="text-sm" style={{ color: "var(--status-good)" }}>
            Профиль сохранён ✓
          </p>
        )}
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? "Сохранение..." : isEdit ? "Сохранить изменения" : "Начать работу"}
        </button>
      </form>

      <div className="mt-4">
        <LinkTelegram />
      </div>

      {isEdit && (
        <button
          type="button"
          onClick={handleLogout}
          className="mt-6 w-full text-center text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors py-2"
        >
          Сменить аккаунт
        </button>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-4 flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-[var(--text-secondary)]">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="text-[var(--text-secondary)]">{label}</span>
      {children}
    </label>
  );
}
