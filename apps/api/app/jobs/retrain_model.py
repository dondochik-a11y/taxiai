"""Thin wrapper around app.ml.train_demand_model, kept separate so it can be
scheduled (e.g. nightly) later once there's enough live data drift to justify
automatic retraining. Not wired into app/jobs/scheduler.py by default for
MVP — run manually via `make train` for now.
"""
from app.ml.train_demand_model import main as retrain

if __name__ == "__main__":
    retrain()
