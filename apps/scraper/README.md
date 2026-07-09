# Radar kef scraper

Harvests real surge coefficients (кэф) from the **"Радар кэфа"** Android app and
POSTs them to the API's `/v1/kef/ingest`. Runs on the always-on home Mac against
a spare Xiaomi phone over `adb`. Background & rationale: see the `radar-kef-scraper`
project memory.

## How it works
Per district tap point (`tap_points.json`, calibrated to a **fixed** whole-Moscow
map view): tap → price bubble → screenshot → EasyOCR → pair to district → POST.
The radar caps **10 temporary markers/minute** and they auto-expire, so points are
processed in batches of ≤10 with a ~60 s gap (that also keeps us inside the radar's
own limit). ~104 districts ⇒ ~11 batches ⇒ ~11 min per full sweep.

## One-time setup

**Phone (Xiaomi/MIUI):**
1. Enable Developer options (tap Build number 7×).
2. Enable **USB debugging** *and* **USB debugging (Security settings)** — the second
   is required for `adb input tap` to work (needs Mi account + SIM).
3. Leave it charging on Wi-Fi with **Радар кэфа open on the fixed map view** used
   for calibration (whole Moscow). Don't pan/zoom, or re-run calibration.

**Mac:**
```bash
brew install --cask android-platform-tools   # adb
cd apps/scraper
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
adb devices                                   # confirm the phone shows "device"
```

## Run once (manual)
```bash
export RADAR_API_URL="https://93.189.228.203.sslip.io/api/v1/kef/ingest"
export SSL_CERT_FILE="$(.venv/bin/python -m certifi)"   # macOS framework-python cert fix
.venv/bin/python radar_scraper.py
# test with fewer batches: RADAR_MAX_BATCHES=2 .venv/bin/python radar_scraper.py
```

## Schedule (every 30 min)
Edit the paths/URL in `com.taxiai.radar.plist`, then:
```bash
cp com.taxiai.radar.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.taxiai.radar.plist
```

## Re-calibration
If the map view drifts, re-derive `tap_points.json`: screenshot the fixed view,
OCR the city labels (Химки/Мытищи/Кусково/Мосрентген) for pixel anchors, fit the
pixel↔latlng web-mercator transform, project the 130 district centroids, and keep
the 104 that land on-screen & clear of UI. (Scratch scripts: `calibrate.py`,
validated 104/104 against real district polygons via PostGIS `ST_Contains`.)
