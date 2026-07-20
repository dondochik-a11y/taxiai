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
- every PRICING_POLL_MINUTES (default 30): poll real Yandex ride prices per
  district into price_observations (live mode only — no-op until clid+apikey
  are set), feeding surge_service's "live" source.
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
from app.core.config import get_settings  # noqa: E402
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
        # returncode -9 with empty stderr = the kernel OOM killer; say so
        # explicitly — this exact failure went unnoticed for two weeks.
        detail = result.stderr.strip()[-300:] or (
            "код -9, пустой stderr — похоже на OOM killer" if result.returncode == -9 else f"код {result.returncode}"
        )
        _notify_telegram(f"❌ TaxiAI: еженедельное переобучение модели упало ({detail})")
        return
    logger.info("Model retrained:\n%s", result.stdout.strip()[-500:])
    _run_forecast_job()


def _run_price_poll_job() -> None:
    from app.jobs.poll_prices import poll_prices

    session = SessionLocal()
    try:
        n = poll_prices(session)
        if n:
            logger.info("Polled %d real Yandex ride prices", n)
    except Exception:
        logger.exception("Price poll failed")
    finally:
        session.close()


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


def _notify_telegram(text_msg: str) -> bool:
    """Push to Tim's notification bot (@clnotifi1bot, NOT the app bot). No-op
    False unless NOTIFY_TELEGRAM_TOKEN / NOTIFY_TELEGRAM_CHAT_ID are set."""
    import os
    import urllib.parse
    import urllib.request

    token = os.environ.get("NOTIFY_TELEGRAM_TOKEN")
    chat_id = os.environ.get("NOTIFY_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text_msg}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10
        )
        return True
    except Exception:
        logger.exception("Telegram notify failed")
        return False


# Radar watchdog state: assume alive at boot so a dead feed on the very first
# check still alerts, and a healthy boot stays silent.
_radar_was_alive = True
# Two emulator halves cover ~130 districts every ~13 min, so one hour of a
# healthy feed yields far more than this; below it the radar is effectively out.
RADAR_MIN_DISTRICTS = 10


def _run_radar_watchdog_job() -> None:
    """Hourly radar-liveness check with a Telegram push (Tim's @clnotifi1bot,
    NOT the app bot) on the dead↔alive transition — the daily retention log
    line is easy to miss, and a silent radar means the map quietly degrades to
    synthetic. No-op unless NOTIFY_TELEGRAM_TOKEN / NOTIFY_TELEGRAM_CHAT_ID
    are set in the environment."""
    from sqlalchemy import text

    session = SessionLocal()
    try:
        coverage = session.execute(
            text(
                "SELECT count(DISTINCT district_id) FROM kef_observations "
                "WHERE observed_at > now() - interval '1 hour' AND district_id IS NOT NULL"
            )
        ).scalar() or 0
    except Exception:
        logger.exception("Radar watchdog coverage query failed")
        return
    finally:
        session.close()

    global _radar_was_alive
    alive = coverage >= RADAR_MIN_DISTRICTS
    if alive == _radar_was_alive:
        return
    _radar_was_alive = alive
    msg = (
        f"✅ TaxiAI: радар кэфа снова в строю ({coverage} районов за час)."
        if alive
        else f"⚠️ TaxiAI: радар кэфа молчит — {coverage} районов за последний час "
        "(порог 10). Проверь Mac/эмуляторы."
    )
    if _notify_telegram(msg):
        logger.info("Radar watchdog alert sent (alive=%s, coverage=%d)", alive, coverage)


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
    scheduler.add_job(_run_radar_watchdog_job, "interval", hours=1, id="radar_watchdog_tick")
    # No-op until Yandex clid+apikey land in .env; cadence per negotiated limits.
    scheduler.add_job(
        _run_price_poll_job,
        "interval",
        minutes=get_settings().pricing_poll_minutes,
        id="price_poll_tick",
    )
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
