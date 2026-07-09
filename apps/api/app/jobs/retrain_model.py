"""Thin wrapper around app.ml.train_demand_model: the subprocess target for
the weekly retrain job in app/jobs/scheduler.py (Mon 03:30 UTC). Can also be
run manually any time via `make train`.
"""
from app.ml.train_demand_model import main as retrain

if __name__ == "__main__":
    retrain()
