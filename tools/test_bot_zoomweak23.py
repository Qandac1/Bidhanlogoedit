"""bot23 inside the bot container:  python3 test_bot_zoomweak23.py <live bot dir copy> <bot23 dir copy> [--real]
  LOGIC (fake pair_check / pair_zoom scripts, one process per bot copy):
    strong same (10, 8 parts)         -> no zoom search, same result as the live bot
    weak same (6, 7 parts) + zoom 10  -> same film WITH the window          (live: same, no window = the Toxic bug)
    weak same + zoom not better       -> same film, NO window               (as live)
    unknown (4 parts) + zoom 10       -> same film with the window          (live: unknown)
    unknown + zoom 3                  -> unknown, no window                 (as live)
    different + zoom 10 / zoom 2      -> exactly as live (bot18)
    short clip (few steps)            -> no zoom search, as live
    zoom search crashes               -> verdict unchanged, no window, never raises
    swapped files + weak              -> the zoom search gets the real HD first
  --real: Toxic 2026 (HD + Somali copy in raw/): the real check + zoom -> same, window ~ [0.775, 0.811, 0, -0.08];
          Highway (real unzoomed pair) -> same, no zoom search.
Prints ZOOMWEAK23_TESTS ALL PASS."""
import json
import os
import subprocess
import sys
import tempfile

LIVE, NEW = sys.argv[1], sys.argv[2]
REAL = "--real" in sys.argv
T = tempfile.mkdtemp(prefix="zw23_")
open(T + "/pc.py", "w").write('import os\nopen(os.environ["ZLOG"], "a").write("check\\n")\nprint(os.environ["PC_JSON"])\n')
open(T + "/pz.py", "w").write('import os, sys\nopen(os.environ["ZLOG"], "a").write("zoom %s\\n" % sys.argv[sys.argv.index("--hd") + 1])\n'
                              'j = os.environ.get("PZ_JSON", "")\n'
                              'if j == "CRASH":\n    sys.exit(1)\nprint(j)\n')
RUNNER = r'''
import asyncio, json, os, sys
from pathlib import Path
d = sys.argv[1]
sys.path.insert(0, d); os.chdir(d)
import bot
if sys.argv[2] == "fake":
    bot.PAIR_CHECK = [sys.executable, sys.argv[3] + "/pc.py"]
    bot.PAIR_ZOOM = [sys.executable, sys.argv[3] + "/pz.py"]
r = asyncio.run(bot._same_film_check(Path(sys.argv[4]), Path(sys.argv[5])))
print("RESULT " + json.dumps({k: r.get(k) for k in ("verdict", "hd_window", "swap", "parts", "zoom")}))
'''
open(T + "/runner.py", "w").write(RUNNER)
fails = 0


def check(ok, what, extra=""):
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what + (("  | " + str(extra)[:400]) if extra and not ok else ""), flush=True)


def run(d, pc, pz, mode="fake", hd="/x/hd.mkv", dub="/x/dub.mp4"):
    log = T + "/log.txt"
    open(log, "w").write("")
    env = dict(os.environ, ZLOG=log, PC_JSON=json.dumps(pc) if pc is not None else "", PZ_JSON=pz if pz == "CRASH" else json.dumps(pz))
    p = subprocess.run([sys.executable, T + "/runner.py", d, mode, T, hd, dub], capture_output=True, text=True, env=env,
                       timeout=3000)
    line = [x for x in p.stdout.splitlines() if x.startswith("RESULT ")]
    if not line:
        return {"error": (p.stderr or p.stdout)[-400:]}, open(log).read().split("\n")
    return json.loads(line[-1][7:]), [x for x in open(log).read().split("\n") if x]


W = [0.775, 0.8112, 0.0, -0.08]
Z10, Z8, Z6, Z3 = ({"zoom_parts": n, "zoom_window": W} for n in (10, 8, 6, 3))


def pc(parts, steps, swap=False):
    return {"parts": parts, "chain": 0.5, "chain_steps": steps, "matched_share": 0.2, "swap": swap}


for name, c, z, want_new, zoom_calls, same_as_live in (
        ("strong same (10 parts)", pc(10, 500), Z10, ("same", None), 0, True),
        ("strong same (8 parts)", pc(8, 73), Z10, ("same", None), 0, True),
        ("weak same (6 parts) + zoom 10 = the Toxic case", pc(6, 169), Z10, ("same", W), 1, False),
        ("weak same (7 parts) + zoom 8", pc(7, 300), Z8, ("same", W), 1, False),
        ("weak same (6 parts) + zoom not better (6)", pc(6, 169), Z6, ("same", None), 1, True),
        ("unknown (4 parts) + zoom 10", pc(4, 91), Z10, ("same", W), 1, False),
        ("unknown (4 parts) + zoom 3", pc(4, 91), Z3, ("unknown", None), 1, True),
        ("different (1 part) + zoom 10 (Sardar, bot18)", pc(1, 208), Z10, ("same", W), 1, True),
        ("different (1 part) + zoom 3", pc(1, 208), Z3, ("different", None), 1, True),
        ("short clip (6 parts, 11 steps)", pc(6, 11), Z10, ("unknown", None), 0, True),
        ("weak same + the zoom search crashes", pc(6, 169), "CRASH", ("same", None), 1, True)):
    rn, ln = run(NEW, c, z)
    ro, lo = run(LIVE, c, z)
    check((rn.get("verdict"), rn.get("hd_window")) == want_new and sum(x.startswith("zoom") for x in ln) == zoom_calls,
          "%s -> %s, window %s, zoom searches %d" % (name, want_new[0], "set" if want_new[1] else "none", zoom_calls),
          (rn, ln))
    if same_as_live:
        check((rn.get("verdict"), rn.get("hd_window")) == (ro.get("verdict"), ro.get("hd_window")),
              "   ... the same verdict and window as the live bot", (ro, rn))
    else:
        check(ro.get("hd_window") is None, "   ... (control) the live bot sets no window here", ro)
rn, ln = run(NEW, pc(6, 169, swap=True), Z10)
check(rn.get("swap") is True and any(x == "zoom /x/dub.mp4" for x in ln) and rn.get("hd_window") == W,
      "swapped files + weak: the zoom search gets the real HD (the other file) first", (rn, ln))

if REAL:
    R = "/opt/dubsync2/raw/"
    rn, _ = run(NEW, None, None, mode="real", hd=R + "toxic20261080p10bi_9f9800_hd_ORIG.mp4",
                dub=R + "toxic20261080p10bi_9f9800_dub_ORIG.mp4")
    w = rn.get("hd_window") or [0, 0, 0, 0]
    check(rn.get("verdict") == "same" and (rn.get("zoom") or {}).get("zoom_parts", 0) >= 8,
          "REAL Toxic 2026: same film, %s of 10 parts zoomed (plain %s)" % ((rn.get("zoom") or {}).get("zoom_parts"),
                                                                           rn.get("parts")), rn)
    check(all(abs(a - b) <= 0.03 for a, b in zip(w, W)), "REAL Toxic window %s ~ [0.775, 0.811, 0, -0.08]" % w)
    rn, _ = run(NEW, None, None, mode="real", hd=R + "highway2014hindi10_2a645f_hd_ORIG.mp4",
                dub=R + "highway2014hindi10_2a645f_dub_ORIG.mp4")
    check(rn.get("verdict") == "same" and rn.get("zoom") is None and not rn.get("hd_window"),
          "REAL Highway (unzoomed): same, no zoom search (%s parts)" % rn.get("parts"), rn)
print("ZOOMWEAK23_TESTS", "ALL PASS" if not fails else "%d FAILED" % fails)
sys.exit(0 if not fails else 1)
