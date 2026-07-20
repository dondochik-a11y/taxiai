"""Trains a single lightweight demand-forecasting model (scikit-learn
HistGradientBoostingRegressor — tabular gradient boosting, not deep learning)
over the synthetic (or, later, real) demand history. `horizon_minutes` is
itself a feature, so one model serves all four forecast horizons rather than
training four separate models.

Run via `make train` (manual for MVP; app/jobs/retrain_model.py can schedule
this later once there's enough live data drift to matter).

This is presented honestly: a lightweight statistical model trained on
regional history, not a fabricated claim of production-grade accuracy. The
printed MAE is whatever the holdout evaluation actually produces.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402
from sklearn.metrics import mean_absolute_error  # noqa: E402

from app.ml import features as feat  # noqa: E402

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "demand_model.joblib"
MODEL_VERSION = "hgbr-v2"  # v2: clock features shifted to the forecast target time

HOLDOUT_DAYS = 14

# OOM guard: the prod VPS has ~4 GB RAM, and by mid-July 2026 the full-history
# training set crossed 4M rows — the float32 fit-input copy alone stopped
# fitting, and the weekly retrain died to the kernel OOM killer with nothing in
# the log (the artifact silently stayed at its Jul 9 version). A uniform random
# subsample preserves the time/district distribution; HGBR's MAE barely moves.
MAX_TRAIN_ROWS = 1_000_000
MAX_HOLDOUT_ROWS = 300_000


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading raw data...")
    demand_df = feat.load_demand()
    if demand_df.empty:
        raise RuntimeError("No demand_snapshots found — run scripts/seed_synthetic_history.py first.")
    weather_df = feat.load_weather_hourly()
    traffic_df = feat.load_traffic()
    calendar_df = feat.load_calendar()
    districts_df = feat.load_districts()
    district_ids = sorted(districts_df["id"].tolist())

    print("Building features...")
    feature_df = feat.build_features(demand_df, weather_df, traffic_df, calendar_df, districts_df)
    training_df = feat.make_training_set(feature_df, district_ids)
    del feature_df, demand_df, weather_df, traffic_df  # free before the fit copies
    print(f"Training set: {len(training_df)} rows across horizons {feat.HORIZONS_MINUTES}")

    columns = feat.feature_columns_for(district_ids)
    max_time = training_df["observed_at"].max()
    holdout_start = max_time - timedelta(days=HOLDOUT_DAYS)

    train_mask = training_df["observed_at"] < holdout_start
    train_df, holdout_df = training_df[train_mask], training_df[~train_mask]
    if holdout_df.empty:
        print("Not enough history for a time-based holdout; training on everything.")
        train_df, holdout_df = training_df, training_df.iloc[0:0]
    del training_df

    if len(train_df) > MAX_TRAIN_ROWS:
        print(f"Subsampling {MAX_TRAIN_ROWS} of {len(train_df)} train rows (OOM guard)")
        train_df = train_df.sample(n=MAX_TRAIN_ROWS, random_state=42)
    if len(holdout_df) > MAX_HOLDOUT_ROWS:
        print(f"Subsampling {MAX_HOLDOUT_ROWS} of {len(holdout_df)} holdout rows (OOM guard)")
        holdout_df = holdout_df.sample(n=MAX_HOLDOUT_ROWS, random_state=42)

    model = HistGradientBoostingRegressor(max_depth=6, learning_rate=0.08, max_iter=300)
    # float32 halves the peak RAM of the fit-input copy — matters for the
    # weekly in-container retrain, and HGBR bins to uint8 internally anyway.
    model.fit(train_df[columns].astype(np.float32), train_df["label"])

    if not holdout_df.empty:
        preds = model.predict(holdout_df[columns].astype(np.float32))
        mae = mean_absolute_error(holdout_df["label"], preds)
        print(f"Holdout MAE (demand_level, 0-1 scale): {mae:.4f} on {len(holdout_df)} rows")
        # Per-horizon breakdown — one aggregate number hides where the model
        # actually degrades (long horizons should be worse; if they aren't,
        # the horizon features are being ignored).
        for horizon in feat.HORIZONS_MINUTES:
            m = (holdout_df["horizon_minutes"] == horizon).to_numpy()
            if m.any():
                h_mae = mean_absolute_error(holdout_df["label"].to_numpy()[m], preds[m])
                print(f"  horizon {horizon:>3} min: MAE {h_mae:.4f} on {int(m.sum())} rows")

    joblib.dump(
        {
            "model": model,
            "feature_columns": columns,
            "district_ids": district_ids,
            "model_version": MODEL_VERSION,
        },
        MODEL_PATH,
    )
    print(f"Saved model artifact to {MODEL_PATH}")


if __name__ == "__main__":
    main()
