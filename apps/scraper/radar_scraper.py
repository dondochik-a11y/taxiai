#!/usr/bin/env python3
"""Harvest real surge coefficients (кэф) from the "Радар кэфа" Android app.

Runs on the always-on home Mac against a spare Xiaomi phone over adb. For each
of the calibrated district tap points (tap_points.json), it taps the point,
lets the price bubble appear, screenshots, OCRs the bubble with EasyOCR, pairs
it back to the district it tapped, and POSTs the readings to the API's
/v1/kef/ingest. Scheduled via launchd (see README).

Why it works this way — see the [[radar-kef-scraper]] memory:
  * the radar shows a number only when you TAP a point (no per-district labels);
  * bubbles accumulate, so we tap a whole non-overlapping batch, then read once;
  * >~1 tap/sec trips "Слишком частые тапы", so taps are paced;
  * force-stop+relaunch clears bubbles but KEEPS the map view (calibration holds);
  * district identity comes from OUR calibration, never the radar's labels.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import easyocr

# ---- config -----------------------------------------------------------------
ADB = os.environ.get("ADB", "adb")
SERIAL = os.environ.get("ANDROID_SERIAL")  # optional, if multiple devices
PKG = "com.taxihelper.coef"
API_URL = os.environ.get("RADAR_API_URL", "http://localhost:8000/v1/kef/ingest")

# The radar allows only 10 temporary markers PER MINUTE, and they auto-expire
# after a few tens of seconds. So we tap in batches of <=10, screenshot right
# away (before they vanish), then wait out the minute — which also means we
# never need to restart to clear, and we stay within the radar's own limit.
BATCH_MAX = 10            # radar's per-minute temporary-marker cap
TAP_DELAY = float(os.environ.get("RADAR_TAP_DELAY", "0.6"))  # within-batch spacing
INTER_BATCH_WAIT = int(os.environ.get("RADAR_INTER_BATCH_WAIT", "60"))  # reset the minute
BATCH_MIN_DIST = 145      # px; keep bubbles from overlapping within a batch
LAUNCH_WAIT = 6           # seconds to let the app draw the map after relaunch
SETTLE_WAIT = 1           # seconds after last tap before screenshot (before expiry)

HERE = Path(__file__).parent
TAP_POINTS = json.loads((HERE / "tap_points.json").read_text(encoding="utf-8"))
SPOOL_DIR = HERE / "spool"  # sweeps that failed to POST, waiting for the API
POST_RETRIES = 3

KEF_RE = re.compile(r"^\d\.\d$")
RATE_LIMIT_MARKS = ("лимит", "слишком частые")  # "Достигнут лимит…", "Слишком частые тапы"
PROMO_MARK = "таксопарк"
# A fullscreen subscription paywall ("Полный доступ … Пробный период") pops up
# some seconds AFTER launch once the app has network; every tap then lands on
# it and the whole sweep reads zero (seen 2026-07-17) — and its trial button
# opens a Chrome payment page. Same package, so the foreground guard can't
# catch it — detect by OCR text and close with BACK before any batch taps.
PAYWALL_MARKS = ("полный доступ", "пробный период", "начать пробный")


# ---- adb helpers ------------------------------------------------------------
def _adb(*args: str) -> subprocess.CompletedProcess:
    base = [ADB] + (["-s", SERIAL] if SERIAL else [])
    return subprocess.run(base + list(args), capture_output=True, text=True)


def _adb_shell(cmd: str) -> str:
    base = [ADB] + (["-s", SERIAL] if SERIAL else [])
    return subprocess.run(base + ["shell", cmd], capture_output=True, text=True).stdout


def restart_app(reader: easyocr.Reader | None = None) -> None:
    """Clear all tap bubbles by relaunching; the map camera is restored, so the
    calibration still holds. Sleeps run on the device (host sleep is fine too)."""
    _adb_shell(f"am force-stop {PKG}")
    _adb_shell(
        f"monkey -p {PKG} -c android.intent.category.LAUNCHER 1; sleep {LAUNCH_WAIT}"
    )
    # An "Наш таксопарк" promo popup appears on launch only occasionally and sits
    # bottom-left; if it shows, at worst a few southern points are missed that
    # cycle (detected via PROMO_MARK in the batch OCR below). Left best-effort.
    if reader is not None:
        dismiss_paywall(reader)


def dismiss_paywall(reader: easyocr.Reader) -> None:
    """The subscription paywall covers the map a few seconds after launch and
    swallows every tap; its trial button even opens a Chrome payment page, so
    NEVER batch-tap while it may be up. BACK closes it (the app stays alive)."""
    shot = HERE / "_paywall_check.png"
    for _ in range(3):
        time.sleep(4)  # the paywall pops in asynchronously once network is up
        screencap(shot)
        _, _, paywall = read_bubbles(reader, str(shot))
        if not paywall:
            return
        print("  paywall overlay detected; sending BACK")
        _adb_shell("input keyevent KEYCODE_BACK; sleep 1")


def screen_ready() -> tuple[bool, str]:
    """Wake the screen and dismiss a non-secure keyguard. adb taps do NOT count
    as user activity, so an unattended phone dims, sleeps and locks — after
    which every tap lands on nothing and screenshots come back black/empty.
    stay_on_while_plugged_in=7 prevents the sleep, but a reboot or a manual
    lock still leaves a secure keyguard we cannot pass without the PIN."""
    _adb_shell("input keyevent KEYCODE_WAKEUP; sleep 1; wm dismiss-keyguard; sleep 1")
    if "mWakefulness=Awake" not in _adb_shell("dumpsys power"):
        return False, "screen did not wake (mWakefulness != Awake)"
    m = re.search(r"^\s*showing=(\w+)", _adb_shell("dumpsys window policy"), re.M)
    if m and m.group(1) == "true":
        return False, (
            "secure lockscreen is up — unlock the phone once by hand "
            "(with USB attached and stay_on_while_plugged_in=7 it then stays awake)"
        )
    return True, ""


def ensure_radar_foreground(reader: easyocr.Reader | None = None) -> None:
    """A batch tap can land on an in-app promo banner and hijack the sweep into
    Chrome (seen live 2026-07-14: banner tap -> CustomTab -> every later batch
    read 0). Back out and relaunch the radar if focus has drifted."""
    if PKG not in _adb_shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'"):
        print("  foreground lost (promo banner tap?); backing out and relaunching")
        _adb_shell("input keyevent KEYCODE_BACK; sleep 1")
        restart_app(reader)


def paced_tap(points: list[dict]) -> None:
    """Tap every point in the batch, pacing on-device to dodge the rate limit."""
    parts = []
    for p in points:
        parts.append(f"input tap {p['x']} {p['y']}")
        parts.append(f"sleep {TAP_DELAY}")
    parts.append(f"sleep {SETTLE_WAIT}")
    _adb_shell("; ".join(parts))


def screencap(path: Path) -> None:
    base = [ADB] + (["-s", SERIAL] if SERIAL else [])
    with open(path, "wb") as f:
        subprocess.run(base + ["exec-out", "screencap", "-p"], stdout=f, check=True)


# ---- batching & pairing -----------------------------------------------------
def make_batches(points: list[dict]) -> list[list[dict]]:
    """Partition into batches that are internally non-overlapping AND <= BATCH_MAX
    (the radar's per-minute marker cap)."""
    batches: list[list[dict]] = []
    for p in points:
        for b in batches:
            if len(b) < BATCH_MAX and all(
                math.hypot(p["x"] - q["x"], p["y"] - q["y"]) >= BATCH_MIN_DIST for q in b
            ):
                b.append(p)
                break
        else:
            batches.append([p])
    return batches


def read_bubbles(reader: easyocr.Reader, img: str) -> tuple[list[tuple], bool, bool]:
    """Return (bubbles, rate_limited, paywall). Each bubble is (kmin, kmax, cx, cy)."""
    results = reader.readtext(img)
    texts = [t.lower() for _, t, _ in results]
    rate_limited = any(mark in t for t in texts for mark in RATE_LIMIT_MARKS)
    paywall = any(mark in t for t in texts for mark in PAYWALL_MARKS)

    reads = []
    for box, text, conf in results:
        t = text.strip()
        if KEF_RE.match(t) and conf > 0.4:
            cx = sum(pt[0] for pt in box) / 4
            cy = sum(pt[1] for pt in box) / 4
            reads.append((float(t), cx, cy))

    reads.sort(key=lambda r: (round(r[1] / 60), r[2]))
    bubbles, used = [], [False] * len(reads)
    for i, (v, x, y) in enumerate(reads):
        if used[i]:
            continue
        group = [(v, x, y)]
        used[i] = True
        for j in range(i + 1, len(reads)):
            v2, x2, y2 = reads[j]
            if not used[j] and abs(x2 - x) < 45 and abs(y2 - y) < 90:
                group.append((v2, x2, y2))
                used[j] = True
        vals = [g[0] for g in group]
        gx = sum(g[1] for g in group) / len(group)
        gy = sum(g[2] for g in group) / len(group)
        bubbles.append((min(vals), max(vals), gx, gy))
    return bubbles, rate_limited, paywall


def pair(bubbles: list[tuple], points: list[dict]) -> list[dict]:
    """Attach each bubble to the nearest tapped point (anchor ~70px below number)."""
    out = []
    for kmin, kmax, gx, gy in bubbles:
        best, bestd = None, 1e9
        for p in points:
            d = math.hypot(p["x"] - gx, p["y"] - (gy + 70))
            if d < bestd:
                bestd, best = d, p
        if best and bestd < 120:
            out.append({"district_id": best["id"], "kef_min": kmin, "kef_max": kmax})
    return out


# ---- main -------------------------------------------------------------------
def _post_payload(payload: dict) -> str:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return f"{resp.status}: {resp.read().decode()}"


def post_readings(readings: list[dict], observed_at: datetime) -> bool:
    """POST with retries; on persistent failure spool to disk for the next run.

    A sweep costs ~13 minutes of taps+OCR — losing it to a transient network
    blip (VPN flap, VPS restart) is the single biggest data leak in the
    pipeline. Old readings are still valuable: kef_observations is raw
    training history, only the live surge cascade ignores rows >45 min.
    """
    payload = {"observed_at": observed_at.isoformat(), "readings": readings}
    for attempt in range(1, POST_RETRIES + 1):
        try:
            print(f"  POST {_post_payload(payload)}")
            return True
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                # our payload is malformed; retrying or spooling can't fix it
                print(f"  POST rejected ({e.code} {e.reason}); dropping", file=sys.stderr)
                return False
            print(f"  POST attempt {attempt}/{POST_RETRIES}: HTTP {e.code}", file=sys.stderr)
        except Exception as e:
            print(f"  POST attempt {attempt}/{POST_RETRIES}: {e}", file=sys.stderr)
        if attempt < POST_RETRIES:
            time.sleep(15 * attempt)
    SPOOL_DIR.mkdir(exist_ok=True)
    spool_path = SPOOL_DIR / f"{observed_at:%Y%m%d-%H%M%S}.json"
    spool_path.write_text(json.dumps(payload), encoding="utf-8")
    # cap the spool so a long API outage can't fill the disk (96 = 24h of sweeps)
    for stale in sorted(SPOOL_DIR.glob("*.json"))[:-96]:
        stale.unlink()
    print(f"  API unreachable after {POST_RETRIES} attempts; spooled to {spool_path.name}")
    return False


def flush_spool() -> None:
    """Re-post sweeps spooled while the API was unreachable (oldest first)."""
    for path in sorted(SPOOL_DIR.glob("*.json")) if SPOOL_DIR.is_dir() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            print(f"  spool {path.name}: POST {_post_payload(payload)}")
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                print(f"  spool {path.name} rejected ({e.code}); dropping", file=sys.stderr)
                path.unlink()
                continue
            print(f"  spool {path.name} failed: HTTP {e.code}; keeping", file=sys.stderr)
            return  # API is unhappy again — leave the rest for the next run
        except Exception as e:
            print(f"  spool {path.name} failed: {e}; keeping", file=sys.stderr)
            return
        path.unlink()


def main() -> int:
    device = _adb("get-state").stdout.strip()
    if device != "device":
        print(f"no device (adb get-state='{device}'); is the phone connected?", file=sys.stderr)
        return 1

    ok, why = screen_ready()
    if not ok:
        print(f"screen not ready: {why}", file=sys.stderr)
        return 1

    reader = easyocr.Reader(["ru", "en"], gpu=False)
    batches = make_batches(TAP_POINTS)
    max_batches = int(os.environ.get("RADAR_MAX_BATCHES", "0"))  # 0 = all; >0 for testing
    if max_batches:
        batches = batches[:max_batches]
    print(f"{len(TAP_POINTS)} districts -> running {len(batches)} batches: {[len(b) for b in batches]}")

    all_readings: list[dict] = []
    posted_any = False
    shot = HERE / "_last_batch.png"

    restart_app(reader)  # once: clean slate; markers self-expire, so no per-batch restart
    for i, batch in enumerate(batches):
        ensure_radar_foreground(reader)
        paced_tap(batch)
        screencap(shot)
        bubbles, limited, paywall = read_bubbles(reader, str(shot))
        if paywall:
            # The wasted taps hit the overlay, not the map, so no markers were
            # spent — safe to retap the same batch after closing it. One of
            # them may have opened the Chrome payment page: relaunch cleanly.
            print("  paywall overlay detected mid-batch; relaunching and retrying")
            _adb_shell("input keyevent KEYCODE_BACK; sleep 1")
            restart_app(reader)
            paced_tap(batch)
            screencap(shot)
            bubbles, limited, _ = read_bubbles(reader, str(shot))
        readings = pair(bubbles, batch)
        all_readings.extend(readings)
        note = " [RATE-LIMITED]" if limited else ""
        print(f"batch {i+1}/{len(batches)}: {len(readings)}/{len(batch)} read{note}")
        # Post per batch, not at sweep end: rows reach the DB (and the live
        # surge cascade) within ~2 min of being read with an honest per-batch
        # timestamp, and a sweep killed mid-run keeps everything already read.
        if readings and post_readings(readings, datetime.now(timezone.utc)):
            posted_any = True
        if i < len(batches) - 1:
            time.sleep(INTER_BATCH_WAIT)  # let the per-minute cap reset & markers expire

    if not all_readings:
        print("no readings collected; nothing to post")
        return 1
    if posted_any:
        flush_spool()  # API is clearly reachable — drain anything spooled earlier
    print(f"sweep done: {len(all_readings)} readings across {len(batches)} batches")
    return 0 if posted_any else 1


if __name__ == "__main__":
    raise SystemExit(main())
