"""bot39b inside the bot container:  python3 test_refusedzoom39.py <live bot dir copy> <bot39b dir copy>
  A. _refused_zoom_ok: a window that clearly beats the plain framing (Sardar: 10 vs 1) -> yes; a zoomed copy the plain
     check already scored high (10 vs 9) with ORB measuring 0.775 -> yes; ORB ~1.0 (not zoomed: W.M.R. Saguni 10 vs
     10) -> no; no ORB window -> no; lines up in 6 parts only -> no; grid and ORB disagree (0.78 / 0.90) -> no;
     an error -> no
  B. _strong_share on the REAL kept analyses: Aegan (wrongly refused) >= 0.90; the right refusals below it (Alias
     Janaki, Patth, Stumped, a different trailer cut); no record -> None
  C. the refusal's extra line: "analysed twice ... still refused" after a window, "no zoomed framing" without one
  E. v2 _edl_zoom_ok on the REAL numbers: Aegan (zoom search 5 parts, ORB on the analysis's shots 10 pairs 0.778,
     pure zoom, grid 0.75) -> yes; a clean film (1.00) -> no; 3 pairs / wrong shape / grid disagrees / errors -> no
  F. the bot's own call of tools/edl_zoom.py on Aegan's kept analysis -> the same window
  D. dubsync_job.py only GAINS lines; the new block sits right before the refusal (after the short-clip retry), the
     message line right after the short-clip line; it compiles and imports
Prints REFUSEDZOOM39_TESTS ALL PASS."""
import importlib
import os
import py_compile
import subprocess
import sys

LIVE, NEW = sys.argv[1], sys.argv[2]
W = "/opt/dubsync2/work/"
fails = 0


def check(ok, what, extra=""):
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what + (("  | " + str(extra)[:400]) if extra and not ok else ""), flush=True)


sys.path.insert(0, NEW)
os.chdir(NEW)
dj = importlib.import_module("dubsync_job")
check(os.path.dirname(os.path.abspath(dj.__file__)) == os.path.abspath(NEW), "the module under test is the patched copy",
      dj.__file__)
ok = dj._refused_zoom_ok
sardar = {"zoom_parts": 10, "plain_small_parts": 1, "zoom_window": [0.7713, 0.7977, -0.0006, -0.0964]}
aegan = {"zoom_parts": 10, "plain_small_parts": 9, "zoom_window": [0.775, 0.75, 0.0, -0.072],
         "zoom_orb_window": [0.776, 0.752, -0.003, -0.07], "zoom_orb_parts": 10}
saguni = {"zoom_parts": 10, "plain_small_parts": 10, "zoom_window": [0.99, 0.99, 0.0, 0.0],
          "zoom_orb_window": [0.995, 0.99, 0.0, 0.0], "zoom_orb_parts": 10}
check(ok(sardar), "A1. clearly beats the plain framing (10 vs 1) -> yes")
check(ok(aegan), "A2. zoomed copy the plain check scored high (10 vs 9), ORB 0.776 -> yes")
check(not ok(saguni), "A3. ORB ~1.0 (not zoomed, 10 vs 10) -> no")
check(not ok(dict(aegan, zoom_orb_window=None)), "A4. no ORB window -> no")
check(not ok(dict(aegan, zoom_parts=6)), "A5. lines up in 6 parts only -> no")
check(not ok(dict(aegan, zoom_window=[0.90, 0.87, 0, 0])), "A6. grid 0.90 vs ORB 0.776 -> no")
check(not ok({"zoom_error": "TimeoutError: "}), "A7. the zoom search failed -> no")
ss = dj._strong_share
vals = {k: ss(W + d) for k, d in (("Aegan", "7bf4b17e1a68"), ("Alias Janaki", "f31827a18787"), ("Patth", "2985a7af4395"),
                                  ("Stumped", "b8d1c8611d0c"), ("clip", "3fdf8f9be959"), ("none", "nonexistent"))}
txt = ", ".join("%s %s" % (k, "-" if v is None else "%.3f" % v) for k, v in vals.items())
check(vals["Aegan"] is not None and vals["Aegan"] >= dj.REFUSED_ZOOM_MIN_STRONG, "B1. Aegan's shots found >= 0.90 (%s)" % txt)
check(all(vals[k] is not None and vals[k] < dj.REFUSED_ZOOM_MIN_STRONG for k in ("Alias Janaki", "Patth", "Stumped", "clip")),
      "B2. the right refusals stay below the bar (the clip is also a short pair: excluded before this)")
check(vals["none"] is None, "B3. a missing record -> None")
# E. the analysis-measured window (v2): the REAL numbers of Aegan's zoom search + edl_zoom, and of a clean film
z_aegan = {"zoom_parts": 5, "zoom_grid_window": [0.75, 0.8532, 0.0, -0.07], "plain_small_parts": 0}
e_aegan = {"orb_window": [0.778, 0.8851, -0.0013, -0.0792], "orb_pairs": 10, "pairs_tried": 60, "shape_dev": 0.0,
           "window": [0.778, 0.8851, -0.0013, -0.0575]}
e_g20 = {"orb_window": [1.0002, 1.0539, 0.0001, 0.0008], "orb_pairs": 54, "shape_dev": 0.0001, "window": [1.0, 1.0, 0, 0]}
eok = dj._edl_zoom_ok
check(not ok(z_aegan), "E0. Aegan's own zoom search alone does not pass (5 of 10 parts) -- why v2 exists")
check(eok(e_aegan, z_aegan), "E1. Aegan: 10 ORB pairs, 77.8 %, pure zoom, the grid agrees -> yes")
check(not eok(e_g20, {"zoom_grid_window": [0.95, 1.0, 0, 0]}), "E2. a clean unzoomed film (1.00) -> no")
check(not eok(dict(e_aegan, orb_pairs=3), z_aegan), "E3. 3 pairs only -> no")
check(not eok(dict(e_aegan, shape_dev=0.1), z_aegan), "E4. not the copy's shape -> no")
check(not eok(e_aegan, {"zoom_grid_window": [0.9, 1.0, 0, 0]}), "E5. the grid window disagrees (0.90) -> no")
check(not eok({"error": "x"}, z_aegan) and not eok(e_aegan, {"zoom_error": "x"}), "E6. a failed tool on either side -> no")
# F. the real tool, the way the bot calls it, on Aegan's kept analysis (files on the server since 10-17 01:40)
import asyncio  # noqa: E402
hdp, dubp = "/opt/dubsync2/raw/aegan2008hybridytd_895432_hd_ORIG.mp4", "/opt/dubsync2/raw/aegan2008hybridytd_895432_dub_ORIG.MP4"
if os.path.exists(hdp) and os.path.exists(dubp):
    e = asyncio.run(dj._edl_zoom(W + "7bf4b17e1a68", hdp, dubp))
    check(eok(e, z_aegan) and abs(e["window"][0] - 0.778) < 0.02, "F. the bot's own call of tools/edl_zoom.py on Aegan: %s" % e)
else:
    check(False, "F. Aegan's files are not on the server -- fetch them first")
n1 = dj._refused_zoom_note({"refused_zoom": {"used_window": [0.775, 0.75, 0, -0.07]}, "refused_parked": []})
n2 = dj._refused_zoom_note({"refused_zoom": {"zoom_parts": 3}})
check("middle 78% x 75%" in n1 and "still refused" in n1 and "no zoomed framing" in n2, "C. the refusal's extra line: %r / %r" % (n1, n2))
d = subprocess.run(["diff", os.path.join(LIVE, "dubsync_job.py"), os.path.join(NEW, "dubsync_job.py")],
                   capture_output=True, text=True).stdout.splitlines()
removed = [x for x in d if x.startswith("< ")]
added = [x for x in d if x.startswith("> ")]
src = open(os.path.join(NEW, "dubsync_job.py")).read()
a, b, c = src.find('"-- still refused.)\\n" if "short_geom_retry" in stats else "")'), src.find("SELF-REPAIR 3 (bot39"), \
    src.find('_pct = _co.get("unconfirmed_pct")')
e1, e2 = src.find("if not _geom_retry and _short_pair(hd, dub)"), src.find('% _refused_zoom_note(stats)')
check(not removed and 100 < len(added) < 170 and e1 < b < c and a < e2 < a + 200,
      "D1. dubsync_job.py only gains lines (%d added, %d removed); the block after the short-clip retry, before the "
      "refusal; the message line after the short-clip line" % (len(added), len(removed)), removed[:3])
try:
    py_compile.compile(os.path.join(NEW, "dubsync_job.py"), doraise=True)
    check(True, "D2. dubsync_job.py compiles (and imported above)")
except py_compile.PyCompileError as ex:
    check(False, "D2. compiles", ex)
print("REFUSEDZOOM39_TESTS ALL PASS" if not fails else "REFUSEDZOOM39_TESTS %d FAILED" % fails)
sys.exit(1 if fails else 0)
