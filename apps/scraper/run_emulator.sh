#!/bin/zsh
# Keeps the headless Android emulator (AVD "radar") running for the kef scraper.
# Managed by launchd (com.taxiai.emulator.plist, KeepAlive) — do not run twice:
# a second instance fails on the AVD lock.
#
# The subshell re-pins the mock GPS after every boot: the scraper's district
# pairing assumes the car marker is parked away from all tap points, and a cold
# boot would otherwise leave the emulator at its default location.
SDK=/opt/homebrew/share/android-commandlinetools
ADB="$SDK/platform-tools/adb"
PARK_LNG=37.7698
PARK_LAT=55.4759

(
  "$ADB" -s emulator-5554 wait-for-device
  sleep 25
  "$ADB" -s emulator-5554 emu geo fix "$PARK_LNG" "$PARK_LAT"
) &

# -dns-server: pin public resolvers. Without it the emulator inherits the
# host's DNS at boot; a VPN utility on the Mac swaps that to a fake-ip
# resolver (198.18.0.2) unreachable from the guest, and every app request
# then dies in DNS (all-zero sweeps, 2026-07-17).
exec "$SDK/emulator/emulator" -avd radar \
  -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect \
  -dns-server 8.8.8.8,1.1.1.1
