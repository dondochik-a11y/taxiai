"""Worker process entrypoint (docker-compose `worker` service):
- every 5 minutes: append a synthetic live-feed tick (weather/demand/trips),
  matching the spec's "collect every 5 minutes" requirement. When real
  ingestion providers replace the synthetic generator later, this is the one
  place that changes — swap the call to scripts.simulate_live_feed.run_tick
  for real provider polling calls.
- every 15 minutes: recompute the forecasts table from the latest trained
  model (no-op with a warning if no model has been trained yet — run
  `make train` first).
- every 15 minutes: detect real-time arrivals near Moscow airports via OpenSky
  (live mode only) — complementary to the daily AviationStack schedule sync,
  see app/jobs/ingest_opensky.py.
- once a day: re-run pattern mining over accumulated history; sync real public
  holidays (isDayOff.ru, live mode) and real upcoming flights (AviationStack,
  live mode) — both no-ops in mock mode; prune kef_observations older than
  90 days and log last-hour radar coverage.
- weekly (Mon 03:30 UTC): retrain the demand model over the full accumulated
  history in a subprocess, then immediately regenerate forecasts.

Traffic doesn't need its own scheduled job here: it's ingested inline inside
the 5-minute tick (scripts/simulate_live_feed.py::_maybe_ingest_traffic),
which self-throttles to once per hour.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: E402

from app.db.base import Base  # noqa: E402,F401  (must import before any single app.models.* submodule)
from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("taxiai.worker")


def _run_tick_job() -> None:
    from scripts.simulate_live_feed import run_tick

    try:
        run_tick()
    except Exception:
        logger.exception("simulate_live_feed tick failed")


def _run_forecast_job() -> None:
    from app.ml.inference import generate_forecasts

    session = SessionLocal()
    try:
        forecasts = generate_forecasts(session)
        logger.info("Generated %d forecast rows", len(forecasts))
    except Exception:
        logger.exception("Forecast generation failed (has `make train` been run yet?)")
    finally:
        session.close()


def _run_pattern_mining_job() -> None:
    from app.ml.pattern_mining import mine_patterns

    session = SessionLocal()
    try:
        insights = mine_patterns(session)
        logger.info("Pattern mining found %d insights", len(insights))
    except Exception:
        logger.exception("Pattern mining failed")
    finally:
        session.close()


def _run_calendar_sync_job() -> None:
    from app.jobs.ingest_calendar import sync_holidays

    session = SessionLocal()
    try:
        n = sync_holidays(session)
        if n:
            logger.info("Synced %d new holiday rows from isDayOff.ru", n)
    except Exception:
        logger.exception("Holiday sync failed")
    finally:
        session.close()


def _run_flights_sync_job() -> None:
    from app.jobs.ingest_flights import sync_flights

    session = SessionLocal()
    try:
        n = sync_flights(session)
        if n:
            logger.info("Synced %d new flight rows from AviationStack", n)
    except Exception:
        logger.exception("Flight sync failed")
    finally:
        session.close()


def _run_retrain_job() -> None:
    """Weekly model retrain over the full accumulated history (synthetic
    backfill + everything the live providers have written since). Runs in a
    subprocess so the multi-GB pandas peak is fully released back to the OS
    when it exits — the worker process itself stays small. The forecast job
    picks the new artifact up automatically (mtime-checked cache in
    app/ml/inference.py); one forecast pass is triggered right away so the map
    doesn't wait out the 15-minute tick on a stale model."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "app.jobs.retrain_model"],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if result.returncode != 0:
        logger.error("Model retrain failed:\n%s", result.stderr[-2000:])
        return
    logger.info("Model retrained:\n%s", result.stdout.strip()[-500:])
    _run_forecast_job()


def _run_kef_retention_job() -> None:
    """kef_observations grows ~5k rows/day from the radar scraper; 90 days is
    plenty for the future promote-into-training decision while keeping the
    table lean. The coverage line doubles as the daily is-the-scraper-alive
    signal."""
    from sqlalchemy import text

    session = SessionLocal()
    try:
        deleted = session.execute(
            text("DELETE FROM kef_observations WHERE observed_at < now() - interval '90 days'")
        ).rowcount
        coverage = session.execute(
            text(
                "SELECT count(DISTINCT district_id) FROM kef_observations "
                "WHERE observed_at > now() - interval '1 hour' AND district_id IS NOT NULL"
            )
        ).scalar()
        session.commit()
        logger.info(
            "kef retention: deleted %d; radar coverage last hour: %d districts",
            deleted,
            coverage or 0,
        )
    except Exception:
        logger.exception("kef retention failed")
    finally:
        session.close()


def _run_opensky_job() -> None:
    from app.jobs.ingest_opensky import sync_realtime_arrivals

    session = SessionLocal()
    try:
        n = sync_realtime_arrivals(session)
        if n:
            logger.info("Detected %d real-time arrivals via OpenSky", n)
    except Exception:
        logger.exception("OpenSky arrival detection failed")
    finally:
        session.close()


def main() -> None:
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(_run_tick_job, "interval", minutes=5, id="live_feed_tick")
    scheduler.add_job(_run_forecast_job, "interval", minutes=15, id="forecast_tick")
    scheduler.add_job(_run_opensky_job, "interval", minutes=15, id="opensky_tick")
    scheduler.add_job(_run_pattern_mining_job, "interval", hours=24, id="pattern_mining_tick")
    scheduler.add_job(_run_calendar_sync_job, "interval", hours=24, id="calendar_sync_tick")
    scheduler.add_job(_run_flights_sync_job, "interval", hours=24, id="flights_sync_tick")
    scheduler.add_job(_run_kef_retention_job, "interval", hours=24, id="kef_retention_tick")
    # Mon 03:30 UTC = 06:30 MSK — night lull, and the freshly retrained model
    # is in place before the Monday morning rush.
    scheduler.add_job(_run_retrain_job, "cron", day_of_week="mon", hour=3, minute=30, id="weekly_retrain")
    logger.info("Worker scheduler starting.")
    _run_tick_job()  # run one immediately on startup instead of waiting 5 min
    _run_calendar_sync_job()  # cheap/keyless — safe to also run once at startup
    scheduler.start()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
