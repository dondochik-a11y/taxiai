# Radar kef scraper

Harvests real surge coefficients (кэф) from the **"Радар кэфа"** Android app and
POSTs them to the API's `/v1/kef/ingest`. Runs on the always-on home Mac against
a **headless Android emulator** (AVD `radar`); the original USB Xiaomi flow still
works and is kept as a fallback. Background & rationale: see the
`radar-kef-scraper` and `radar-emulator-migration` project memories.

## How it works
Per district tap point (`tap_points.json`, calibrated to a **fixed** whole-Moscow
map view, zoom 10): tap → kef bubble → screenshot → EasyOCR → pair to district →
POST. The radar caps **10 temporary markers/minute**, so points are processed in
batches of ≤10 with a ~60 s gap. 120 districts ⇒ 13 batches ⇒ ~13 min per sweep.

## Emulator setup (current prod path)
One-time, already done on the home Mac (M1):
```bash
brew install --cask android-commandlinetools && brew install openjdk
export JAVA_HOME=/opt/homebrew/opt/openjdk
yes | sdkmanager --licenses
sdkmanager --install platform-tools emulator "system-images;android-34;google_apis;arm64-v8a"
echo no | avdmanager create avd -n radar -k "system-images;android-34;google_apis;arm64-v8a" --device pixel_5
# then in ~/.android/avd/radar.avd/config.ini: hw.lcd 1080x2400 @ 440dpi (matches the
# phone the pipeline was proven on), hw.ramSize 2048, disk.dataPartition.size 4096M
```
App install (APK pulled from the phone, `~/.taxiai/emulator/radar-kefa-*.apk`):
```bash
adb -s emulator-5554 install -r ~/.taxiai/emulator/radar-kefa-*.apk
adb -s emulator-5554 shell pm grant com.taxihelper.coef android.permission.ACCESS_FINE_LOCATION
adb -s emulator-5554 shell pm grant com.taxihelper.coef android.permission.ACCESS_COARSE_LOCATION
adb -s emulator-5554 shell pm grant com.taxihelper.coef android.permission.ACCESS_BACKGROUND_LOCATION
adb -s emulator-5554 shell appops set com.taxihelper.coef SYSTEM_ALERT_WINDOW allow
adb -s emulator-5554 shell dumpsys deviceidle whitelist +com.taxihelper.coef
```
Then tap through onboarding once (terms checkbox; the «Полный доступ» paywall
closes with BACK) and in the app settings set: **Режим отображения → Коэффициент**
(fresh installs default to prices in ₽!), **Время показа временного маркера → 10 с**,
**Тема → Ночь**. All of these live in Flutter shared_prefs, so with `adb root` they
can also be set directly (`flutter.map_zoom`, `flutter.themeMode`, etc. in
`/data/data/com.taxihelper.coef/shared_prefs/FlutterSharedPreferences.xml` — string
values carry a base64 `VGhpcyBpcyB0aGUgcHJlZml4IGZvciBEb3VibGUu` prefix).

The map camera (whole-Moscow view) is pinned via those prefs: lat 55.715,
lng 37.62, zoom 10.0 — the app restores it on every launch, and the quick-boot
snapshot preserves it across emulator restarts. The mock GPS is parked at
(37.7698, 55.4759) — a spot ≥350 px from every tap point so the car's own kef
bubble never pairs with a tapped district (`run_emulator.sh` re-pins it on boot).

## Re-calibration (`calibrate_emu.py`)
Fully automatic — no OCR of city labels needed: the script drives the mock GPS
to 5 known coordinates, finds the car's kef bubble on screen with EasyOCR, fits
a linear web-mercator pixel↔latlng transform (residuals <1 px), projects the 130
district centroids from `districts.json` (from prod `/api/v1/districts`), filters
the ones clear of UI (120 survive), and writes `tap_points_emu.json`. Run it after
any change to the camera view, then copy the result over `tap_points.json`.

## Run once (manual)
```bash
export ANDROID_SERIAL=emulator-5554
export RADAR_API_URL="https://93.189.228.203.sslip.io/api/v1/kef/ingest"
export SSL_CERT_FILE="$(.venv/bin/python -m certifi)"
.venv/bin/python radar_scraper.py
# test with fewer batches: RADAR_MAX_BATCHES=2 .venv/bin/python radar_scraper.py
```

## Schedule
Two launchd agents (deploy outside ~/Documents — TCC! — live copies in `~/.taxiai/`):
- **com.taxiai.emulator.plist** — keeps the headless emulator alive
  (RunAtLoad + KeepAlive, wrapper `run_emulator.sh` re-pins GPS after boot).
- **com.taxiai.radar.plist** — the sweep every 30 min (`ANDROID_SERIAL=emulator-5554`).

```bash
cp radar_scraper.py tap_points.json ~/.taxiai/scraper/
mkdir -p ~/.taxiai/emulator && cp run_emulator.sh ~/.taxiai/emulator/
cp com.taxiai.radar.plist com.taxiai.emulator.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.taxiai.emulator.plist
launchctl load ~/Library/LaunchAgents/com.taxiai.radar.plist
```
After changing `radar_scraper.py`/`tap_points.json` in the repo, re-copy them to
`~/.taxiai/scraper/` — the repo is the source of truth, launchd runs the copy.

## Phone fallback (legacy)
The original flow (USB Xiaomi, `tap_points_phone.json`) still works: plug the
phone, leave «Радар кэфа» on its calibrated whole-Moscow view, and run with
`ANDROID_SERIAL=<phone-serial>` and `tap_points_phone.json` in place of
`tap_points.json`. MIUI gotchas (USB debugging (Security settings), taps-don't-
count-as-activity, secure keyguard after reboot) are documented in the
`radar-kef-scraper` memory.

## Known behaviours
- The app's PRO trial self-activates on a fresh install (~5 h). The scraper's
  tap-price flow works in the free tier too (proven on the phone), but free mode
  staggers marker responses harder (`config_uxMarkerStaggerDelayMsFree=8000`) —
  if post-trial read-rates drop, raise `SETTLE_WAIT`.
- ~80% bubble read-rate per batch on the emulator (vs ~54% on the phone).
- A promo popup («Наш таксопарк») occasionally covers the bottom-left on launch;
  a batch may lose a few southern points that cycle. The top PRO banner hijack
  (Chrome CustomTab) is defended by the foreground check per batch.
