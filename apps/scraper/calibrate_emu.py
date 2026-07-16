#!/usr/bin/env python3
"""Calibrate emulator map: GPS anchors -> pixel transform -> tap_points."""
import json, math, re, subprocess, sys, time
from pathlib import Path
import easyocr

SERIAL = "emulator-5554"
HERE = Path(__file__).parent
KEF_RE = re.compile(r"^\d\.\d$")

ANCHORS = [
    (37.45, 55.88), (37.78, 55.88), (37.45, 55.52), (37.78, 55.52), (37.62, 55.72),
]

def adb(*a, **kw):
    return subprocess.run(["adb", "-s", SERIAL, *a], capture_output=True, text=True, **kw)

def screencap(p):
    with open(p, "wb") as f:
        subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"], stdout=f, check=True)

def merc(lat):
    return math.log(math.tan(math.pi/4 + math.radians(lat)/2))

def find_kef_bubble(reader, img):
    """Return (cx, cy) of the single kef bubble, or None."""
    cands = []
    for box, text, conf in reader.readtext(img):
        t = text.strip()
        if KEF_RE.match(t) and conf > 0.4:
            cx = sum(p[0] for p in box)/4; cy = sum(p[1] for p in box)/4
            cands.append((conf, cx, cy, t))
    if not cands:
        return None
    cands.sort(reverse=True)
    return cands[0][1], cands[0][2], cands[0][3]

def main():
    reader = easyocr.Reader(["ru", "en"], gpu=False, verbose=False)
    pairs = []
    for i, (lng, lat) in enumerate(ANCHORS):
        adb("emu", "geo", "fix", str(lng), str(lat))
        time.sleep(6)
        shot = HERE / f"_anchor{i}.png"
        found = None
        for attempt in range(3):
            screencap(shot)
            found = find_kef_bubble(reader, str(shot))
            if found: break
            time.sleep(4)
        if not found:
            print(f"anchor {i} ({lng},{lat}): NO bubble found", file=sys.stderr)
            continue
        cx, cy, t = found
        print(f"anchor {i}: ({lng},{lat}) -> px ({cx:.0f},{cy:.0f}) kef={t}")
        pairs.append((lng, lat, cx, cy))
    if len(pairs) < 3:
        print("not enough anchors", file=sys.stderr); return 1

    # fit x = A*lng + B ; y = C*merc(lat) + D  (least squares)
    import statistics
    def fit(xs, ys):
        n=len(xs); sx=sum(xs); sy=sum(ys)
        sxx=sum(x*x for x in xs); sxy=sum(x*y for x,y in zip(xs,ys))
        A=(n*sxy - sx*sy)/(n*sxx - sx*sx); B=(sy - A*sx)/n
        return A,B
    A,B = fit([p[0] for p in pairs], [p[2] for p in pairs])
    C,D = fit([merc(p[1]) for p in pairs], [p[3] for p in pairs])
    resx = [abs(A*p[0]+B - p[2]) for p in pairs]
    resy = [abs(C*merc(p[1])+D - p[3]) for p in pairs]
    print(f"transform: x={A:.2f}*lng+{B:.1f}  y={C:.2f}*merc+{D:.1f}")
    print(f"residuals px: x max {max(resx):.1f}, y max {max(resy):.1f}")
    if max(resx) > 20 or max(resy) > 20:
        print("WARNING: residuals high — camera may have moved during calibration", file=sys.stderr)

    districts = json.loads((HERE/"districts.json").read_text())
    OFFSET_Y = 70  # bubble center sits ~70px above the ground point
    pts, dropped = [], []
    for d in districts:
        x = A*d["centroid_lng"] + B
        y = C*merc(d["centroid_lat"]) + D + OFFSET_Y
        # UI exclusion: top icons/banner, right button column, bottom hint/bar
        ok = 40 <= x <= 1040 and 400 <= y <= 1950 and not (x > 870 and y > 1450) and not (x > 870 and y < 500)
        (pts if ok else dropped).append({"id": d["id"], "name": d["name"], "x": round(x), "y": round(y)})
    (HERE/"tap_points_emu.json").write_text(json.dumps(pts, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"kept {len(pts)} / {len(districts)} districts; dropped: {[d['name'] for d in dropped]}")
    json.dump([A,B,C,D], open(HERE/"transform_emu.json","w"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
