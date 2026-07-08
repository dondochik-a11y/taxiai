"""Group-by conditional-mean-vs-baseline pattern mining over demand_snapshots
— deliberately simple (not causal inference or deep pattern discovery), but
this correctly surfaces the injected synthetic signals as a proof of concept,
and the same aggregation code works unchanged over real data later.

Run standalone: python -m app.ml.pattern_mining
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ml import features as feat
from app.models.pattern_insight import PatternInsight
from app.synth import signal_config as cfg

MIN_SAMPLES = 30
MIN_EFFECT_PCT = 10.0


def _rain_effect_insights(merged) -> list[PatternInsight]:
    insights: list[PatternInsight] = []
    for district_id, name in merged[["district_id", "name"]].drop_duplicates().itertuples(index=False):
        sub = merged[merged["district_id"] == district_id]
        rain = sub.loc[sub["is_precipitation"] == 1, "demand_level"]
        dry = sub.loc[sub["is_precipitation"] == 0, "demand_level"]
        if len(rain) < MIN_SAMPLES or len(dry) < MIN_SAMPLES:
            continue
        dry_mean = dry.mean()
        if dry_mean <= 0:
            continue
        effect_pct = (rain.mean() - dry_mean) / dry_mean * 100
        if abs(effect_pct) < MIN_EFFECT_PCT:
            continue
        direction = "выше" if effect_pct > 0 else "ниже"
        insights.append(
            PatternInsight(
                pattern_text=(
                    f"Во время дождя/снега средний спрос в районе «{name}» {direction} на "
                    f"{abs(effect_pct):.0f}% (наблюдений: {len(rain)})."
                ),
                condition_json={"weather": "rain_or_snow", "district": name},
                effect_metric="demand_level",
                effect_magnitude_pct=round(effect_pct, 2),
                confidence=round(min(0.99, len(rain) / 500), 3),
                sample_size=int(len(rain)),
            )
        )
    return insights


def _friday_night_center_vs_airport_insight(merged) -> PatternInsight | None:
    center_names = set(cfg.CENTER_DISTRICTS)
    airport_names = set(cfg.AIRPORT_DISTRICTS)
    fri_late = merged[(merged["observed_at"].dt.weekday == 4) & (merged["observed_at"].dt.hour >= cfg.FRIDAY_LATE_HOUR)]

    center_vals = fri_late.loc[fri_late["name"].isin(center_names), "demand_level"]
    airport_vals = fri_late.loc[fri_late["name"].isin(airport_names), "demand_level"]
    if len(center_vals) < 20 or len(airport_vals) < 20 or center_vals.mean() <= 0:
        return None

    effect_pct = (airport_vals.mean() - center_vals.mean()) / center_vals.mean() * 100
    if abs(effect_pct) < MIN_EFFECT_PCT:
        return None

    direction = "выше" if effect_pct > 0 else "ниже"
    return PatternInsight(
        pattern_text=(
            f"По пятницам после {cfg.FRIDAY_LATE_HOUR}:00 спрос у аэропортов {direction}, чем в центре, "
            f"на {abs(effect_pct):.0f}% (наблюдений: {len(center_vals) + len(airport_vals)})."
        ),
        condition_json={"day": "friday", "hour_after": cfg.FRIDAY_LATE_HOUR, "comparison": "airport_vs_center"},
        effect_metric="demand_level",
        effect_magnitude_pct=round(effect_pct, 2),
        confidence=round(min(0.99, (len(center_vals) + len(airport_vals)) / 500), 3),
        sample_size=int(len(center_vals) + len(airport_vals)),
    )


def mine_patterns(session: Session) -> list[PatternInsight]:
    demand_df = feat.load_demand()
    if demand_df.empty:
        return []
    weather_df = feat.load_weather_hourly()
    districts_df = feat.load_districts()

    demand_df["hour_floor"] = demand_df["observed_at"].dt.floor("h")
    merged = demand_df.merge(weather_df.rename(columns={"observed_at": "hour_floor"}), on="hour_floor", how="left")
    merged = merged.merge(districts_df.rename(columns={"id": "district_id"}), on="district_id", how="left")
    merged["is_precipitation"] = merged["is_precipitation"].fillna(0)

    insights = _rain_effect_insights(merged)
    friday_insight = _friday_night_center_vs_airport_insight(merged)
    if friday_insight:
        insights.append(friday_insight)

    session.query(PatternInsight).delete()
    session.add_all(insights)
    session.commit()
    return insights


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        found = mine_patterns(db)
        for i in found:
            print(f"- {i.pattern_text} (effect {i.effect_magnitude_pct:+.1f}%, confidence {i.confidence})")
        if not found:
            print("No patterns crossed the effect/sample-size threshold yet.")
    finally:
        db.close()
