"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, storeUserId } from "@/lib/apiClient";
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

export default function OnboardingPage() {
  const router = useRouter();
  const [districts, setDistricts] = useState<District[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [city, setCity] = useState("Moscow");
  const [carMake, setCarMake] = useState("Hyundai");
  const [carModel, setCarModel] = useState("Solaris");
  const [tariffPlan, setTariffPlan] = useState("economy");
  const [fuelType, setFuelType] = useState("petrol95");
  const [fuelConsumption, setFuelConsumption] = useState(8.0);
  const [fuelPrice, setFuelPrice] = useState(60.0);
  const [rentalCostPerDay, setRentalCostPerDay] = useState(2500);
  const [homeDistrictId, setHomeDistrictId] = useState<number | "">("");
  const [scheduleStart, setScheduleStart] = useState("08:00");
  const [scheduleEnd, setScheduleEnd] = useState("20:00");

  useEffect(() => {
    api.get<District[]>("/v1/districts").then(setDistricts).catch(() => setDistricts([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
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
      const user = await api.post<User>("/v1/users", payload);
      storeUserId(user.id);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить профиль");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-lg md:text-xl font-semibold mb-1">Профиль водителя</h1>
      <p className="text-sm text-[var(--text-secondary)] mb-5">
        Заполните один раз — дальше AI всё считает автоматически.
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
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? "Сохранение..." : "Начать работу"}
        </button>
      </form>
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
