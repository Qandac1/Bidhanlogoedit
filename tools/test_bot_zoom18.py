"""bot18 on REAL files, inside the bot container (python3 test_bot_zoom18.py <bot dir> <pair_zoom.py under test>):
  1. _set_hd_window: saves, clears, survives a broken registry, never raises.
  2. _same_film_check, the real check + zoom search:
       Sardar HD + Sardar Somali (zoomed copy)  -> "same", window ~ [0.771, 0.798, -0.001, -0.096]
       Sardar HD + Highway Somali (wrong pair)  -> "different" (refused as before)
       Highway HD + Highway Somali (real pair)  -> "same", no zoom search run (exactly as before)"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

D = sys.argv[1]
sys.path.insert(0, D)
os.chdir(D)
import bot  # noqa: E402

bot.PAIR_ZOOM = ["/opt/dubsync2/.venv/bin/python", sys.argv[2]]
fails = 0


def check(ok, what, extra=""):
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what + (("  " + str(extra)[:300]) if extra and not ok else ""), flush=True)


tmp = tempfile.mkdtemp()
bot.HD_WINDOWS = os.path.join(tmp, "hd_windows.json")
bot._set_hd_window("t1", [0.77131, 0.7977, -0.0006, -0.0964])
reg = json.load(open(bot.HD_WINDOWS))
check(reg.get("t1", {}).get("window") == [0.7713, 0.7977, -0.0006, -0.0964], "window saved for the title", reg)
bot._set_hd_window("t2", None)
check(json.load(open(bot.HD_WINDOWS)) == reg, "clearing another title leaves the file as it was")
bot._set_hd_window("t1", None)
check("t1" not in json.load(open(bot.HD_WINDOWS)), "a job without a window clears its title")
open(bot.HD_WINDOWS, "w").write("{broken")
bot._set_hd_window("t3", [0.8, 0.8, 0, 0])
check(json.load(open(bot.HD_WINDOWS)).get("t3") is not None, "a broken registry is replaced, not a crash")
bot.HD_WINDOWS = "/proc/nope/hd_windows.json"
try:
    bot._set_hd_window("t4", [0.8, 0.8, 0, 0])
    check(True, "an unwritable registry never raises")
except Exception as exc:
    check(False, "an unwritable registry never raises", exc)

S, R = "/opt/dubsync2/scratch/sardar/", "/opt/dubsync2/raw/"


async def main():
    r = await bot._same_film_check(Path(S + "msg61733_"), Path(S + "msg61735_"))
    w = r.get("hd_window") or [0, 0, 0, 0]
    check(r.get("verdict") == "same" and r.get("zoom", {}).get("zoom_parts", 0) >= 8,
          "Sardar (zoomed copy): same film, %s of 10 parts zoomed (plain %s)" % (r.get("zoom", {}).get("zoom_parts"),
                                                                              r.get("parts")), r)
    check(all(abs(a - b) <= 0.01 for a, b in zip(w, [0.771, 0.798, -0.001, -0.096])),
          "Sardar window %s ~ the measured [0.771, 0.798, -0.001, -0.096]" % w)
    check(r.get("swap") is False, "Sardar: no swap (HD %s, dub %s Somali)" % (r.get("hd_somali"), r.get("dub_somali")))
    r = await bot._same_film_check(Path(S + "msg61733_"), Path(R + "highway2014hindi10_2a645f_dub_ORIG.mp4"))
    check(r.get("verdict") == "different" and not r.get("hd_window"),
          "wrong pair (Sardar HD + Highway Somali): still refused, zoom %s parts" % r.get("zoom", {}).get("zoom_parts"), r)
    r = await bot._same_film_check(Path(R + "highway2014hindi10_2a645f_hd_ORIG.mp4"),
                                   Path(R + "highway2014hindi10_2a645f_dub_ORIG.mp4"))
    check(r.get("verdict") == "same" and "zoom" not in r and not r.get("hd_window"),
          "real unzoomed pair (Highway): same, no zoom search -- as before (%s parts)" % r.get("parts"), r)


asyncio.run(main())
print("ZOOM18_TESTS", "ALL PASS" if not fails else "%d FAILED" % fails)
