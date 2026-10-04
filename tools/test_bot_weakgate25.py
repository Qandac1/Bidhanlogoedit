"""bot25 = live bot + the weak-analysis gate. Run inside the bot container:
    python3 test_bot_weakgate25.py <live bot dir copy> <bot25 dir copy>
  A. NO BREAK: a good analysis (2.0 % unconfirmed) -> no zoom search; same steps, film bytes, report as live.
  B. THE TOXIC FILM: 14.39 % unconfirmed, the zoom search finds a window (10 parts vs 3 plain) -> window saved (other
     titles kept), old analysis moved aside, analysed again (0.08 %), rendered, the report says what happened.
     (control) the live bot renders the 14.39 % plan straight away.
  C. 14.39 % and NO zoomed framing -> NOT rendered (no preview stage ran), a plain message.
  D. 7 % and no zoom gain (10 vs 10 parts: Saguni) -> rendered as live; the report is headed NOT CLEAN (bot24).
  E. 12 % with a window ALREADY saved for the title -> no second zoom search -> NOT rendered.
  F. The zoom search crashes / times out -> treated as "no zoom": 14 % stops, 7 % renders.
  G. Bounds: 5.0 % no gate; 5.1 % gate (zoom searched); 10.0 % renders; 10.1 % stops.
Prints WEAKGATE25_TESTS ALL PASS."""
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIVE, NEW = sys.argv[1], sys.argv[2]
T = Path(tempfile.mkdtemp(prefix="wg25_"))
FIX = T / "fixture.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", "-c:a", "aac", "-shortest", str(FIX)], check=True)
REG = T / "hd_windows.json"
FAKES = {
    "engine": r'''
import json, os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("engine_%s\n" % a[0])
w = os.environ["ENGINE_WORK"]
os.makedirs(w, exist_ok=True)
if a[0] == "analyze":
    try:
        zoomed = "artest" in json.load(open(os.environ["FAKE_REG"]))
    except Exception:
        zoomed = False
    unc = float(os.environ["AN_UNC2"] if zoomed else os.environ["AN_UNC"])
    json.dump({"conform_offset": {"accepted": True, "reason": "accepted (frame-dense)", "unconfirmed_pct": unc},
               "edl": []}, open(os.path.join(w, "edl.json"), "w"))
    json.dump({"decision": "same speed", "ratio": 1.0, "windows": 16, "hd_original": "/x/raw/artest_hd_ORIG.mp4"},
              open(os.path.join(w, "speed.json"), "w"))
if a[0] == "preview" and "--plan-only" not in a:
    shutil.copy(os.environ["FIXTURE"], os.path.join(os.environ["FAKE_OUT"], a[a.index("--output-name") + 1]))
    open(os.path.join(w, "provenance.json"), "w").write("[]")
    print("Expected duration: 4.0s")
    print("Provenance: %s/provenance.json" % w)
if a[0] == "preview" and "--plan-only" in a:
    print("accidental: 0.0s")
if a[0] == "integrity":
    print("RELEASE APPROVED")
''',
    "pz": 'import os, sys\nopen(os.environ["FAKE_LOG"], "a").write("zoom_search\\n")\nj = os.environ.get("PZ_JSON", "")\n'
          'if j == "CRASH":\n    sys.exit(1)\nprint(j)\n',
    "switch_audio": 'import os,shutil,sys; a=sys.argv[1:]; open(os.environ["FAKE_LOG"],"a").write("switch_audio\\n"); '
                    'shutil.copy(a[a.index("--video")+1], a[a.index("--out")+1])',
    "opening_restore": 'import os; open(os.environ["FAKE_LOG"],"a").write("opening_restore\\n"); '
                       'print("OPENING_GATE OK"); print("OPENING_RESTORE NOT NEEDED")',
    "restore_head": 'import os; open(os.environ["FAKE_LOG"],"a").write("restore_head\\n"); '
                    'print("t: in the output: 100.0%"); print("DIALOGUE_AUDIT GREEN"); print("RESTORE_HEAD NOT NEEDED")',
    "auto_repair": 'import os; open(os.environ["FAKE_LOG"],"a").write("auto_repair\\n"); print("AUTO_REPAIR NOTHING 0")',
    "tail_restore": 'import os; open(os.environ["FAKE_LOG"],"a").write("tail_restore\\n"); print("TAIL_RESTORE NOT NEEDED")',
    "cut_audit": 'import os; open(os.environ["FAKE_LOG"],"a").write("cut_audit\\n"); print("UNJUSTIFIED CUTS: 0")',
    "frame_audit": 'import os; open(os.environ["FAKE_LOG"],"a").write("frame_audit\\n"); '
                   'print("t: 1 shots with HD checked, 0 show the dub\'s own picture"); '
                   'print("  ok 1 (100.0%) | wrong clip (moved) 0 | HD the dub lacks (no_hd) 0 | unsure 0"); '
                   'print("FRAME_AUDIT GREEN")',
    "append_credits": 'import os; open(os.environ["FAKE_LOG"],"a").write("append_credits\\n"); '
                      'print("CREDITS: appended 5.0s of the film\'s own end credits")',
    "space_guard": 'import os,sys; open(os.environ["FAKE_LOG"],"a").write("space_guard_%s\\n" % sys.argv[2])',
}
for k, v in FAKES.items():
    (T / (k + ".py")).write_text(v)
eng = T / "fake_engine"
eng.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, T / "engine.py"))
eng.chmod(0o755)
Q = {"locked_pct": 100.0, "shots": 1}


def load(d, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, "dubsync_job.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    sys.path.insert(0, d)
    spec.loader.exec_module(m)
    sys.path.remove(d)
    m.DUBSYNC = str(eng)
    m.DLG_PY = sys.executable
    for k in ("switch_audio", "restore_head", "opening_restore", "auto_repair", "cut_audit", "frame_audit",
              "append_credits", "tail_restore", "space_guard"):
        if hasattr(m, k.upper()) or k == "space_guard":
            setattr(m, k.upper(), str(T / (k + ".py")))
    m._quality_report = lambda title: dict(Q)
    m.SHORT_GEOM = str(T / "short_geom.json")
    m.PARKED_WORK = T / "parked"
    if hasattr(m, "HD_WINDOWS_FILE"):
        m.HD_WINDOWS_FILE = str(REG)
        m.PAIR_ZOOM_CMD = [sys.executable, str(T / "pz.py")]
    return m


old, new = load(LIVE, "job_live"), load(NEW, "job_25")
ok = True
W = [0.775, 0.8112, 0.0, -0.08]
Z_GAIN = json.dumps({"zoom_parts": 10, "plain_small_parts": 3, "zoom_window": W})
Z_NOGAIN = json.dumps({"zoom_parts": 10, "plain_small_parts": 10, "zoom_window": [0.9252, 1.0, 0.0, 0.0]})
Z_NONE = json.dumps({"zoom_parts": 2, "plain_small_parts": 2, "zoom_window": None})


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


def run(m, tag, unc, unc2=0.08, pz=Z_NONE, reg=None, q_unc=None):
    d = T / tag
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    work = d / "workroot" / "abc123abc123"
    work.mkdir(parents=True)
    (work / "embeds.npz").write_text("made with the old framing")
    log = d / "log.txt"
    log.write_text("")
    REG.unlink(missing_ok=True)
    if reg is not None:
        json.dump(reg, open(REG, "w"))
    os.environ.update({"FAKE_LOG": str(log), "FIXTURE": str(FIX), "FAKE_OUT": str(d / "out"), "ENGINE_WORK": str(work),
                       "AN_UNC": str(unc), "AN_UNC2": str(unc2), "PZ_JSON": pz, "FAKE_REG": str(REG)})
    Q.clear()
    Q.update({"locked_pct": 100.0, "shots": 1})
    if q_unc is not None:
        Q["offset_unconf"] = q_unc
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: work
    res = asyncio.run(m.run_dubsync(FIX, FIX, "artest", None, 320, 240, 23, lambda *a: None, bitrate_k=500))
    cap = m.summary_caption("artest", res, 4.0, 1000) if res.ok else ""
    try:
        regnow = json.load(open(REG))
    except Exception:
        regnow = None
    return res, cap, log.read_text().split(), work, regnow


def film(res):
    return open(res.path, "rb").read() if res.ok and res.path and os.path.exists(res.path) else b""


# ---- A. no break ------------------------------------------------------------------------------------------
ro, co, lo, _, _ = run(old, "A_old", 2.0)
rn, cn, ln, _, rg = run(new, "A_new", 2.0)
check("A: same steps in the same order as the live bot, no zoom search", lo == ln and "zoom_search" not in ln, (lo, ln))
check("A: same film bytes", film(ro) == film(rn) and len(film(rn)) > 1000)
check("A: the SAME report text", co == cn, cn[:500])
so = {k: str(v).replace("A_old", "A_") for k, v in ro.stats.items()}
sn = {k: str(v).replace("A_new", "A_") for k, v in rn.stats.items()}
check("A: same stats (%d values)" % len(sn), so == sn, {k: (so.get(k), sn.get(k)) for k in set(so) | set(sn) if so.get(k) != sn.get(k)})
check("A: the window registry untouched", rg is None, rg)

# ---- B. the Toxic film ------------------------------------------------------------------------------------
res, cap, log, work, rg = run(new, "B", 14.39, 0.08, pz=Z_GAIN, reg={"other_123456": {"window": [0.77, 0.8, 0, -0.1]}})
check("B: zoom searched once, analysed twice, then rendered", log.count("zoom_search") == 1 and log.count("engine_analyze") == 2
      and log.index("zoom_search") < [i for i, x in enumerate(log) if x == "engine_analyze"][1]
      and any(x == "engine_preview" for x in log), log)
check("B: the window is saved, the other title kept", rg is not None and rg.get("artest", {}).get("window") == W
      and "other_123456" in rg, rg)
parked = list((T / "parked").glob("abc123abc123_*"))
check("B: the old analysis moved aside, not deleted", len(parked) >= 1 and (parked[-1] / "embeds.npz").exists()
      and not (work / "embeds.npz").exists(), parked)
check("B: the film is delivered", res.ok and len(film(res)) > 1000, res.message[:300])
check("B: the report says what happened", "weak analysis (14.4% of shots unconfirmed): the Somali copy is ZOOMED" in cap
      and "78% x 81%" in cap and "NOT CLEAN" not in cap.splitlines()[0], cap[:900])
res_o, cap_o, log_o, _, _ = run(old, "B_old", 14.39, 0.08, pz=Z_GAIN)
check("B: (control) the live bot renders the 14.39 % plan without looking", res_o.ok and log_o.count("engine_analyze") == 1
      and "zoom_search" not in log_o, log_o)

# ---- C. weak and no zoom ----------------------------------------------------------------------------------
res, cap, log, work, rg = run(new, "C", 14.39, pz=Z_NONE)
check("C: NOT rendered -- no preview stage ran", not res.ok and not any(x.startswith("engine_preview") for x in log)
      and log.count("zoom_search") == 1 and log.count("engine_analyze") == 1, log)
check("C: a plain message", "NOT rendered" in res.message and "14.4%" in res.message and "Nothing was rendered" in res.message
      and "no zoomed framing explains it" in res.message, res.message)
check("C: no window saved", rg is None, rg)

# ---- D. 7 %, no zoom gain (Saguni) ------------------------------------------------------------------------
res, cap, log, work, rg = run(new, "D", 7.0, pz=Z_NOGAIN, q_unc=7.0)
check("D: rendered once (zoom searched, no gain, no second analysis)", res.ok and log.count("zoom_search") == 1
      and log.count("engine_analyze") == 1 and rg is None, (log, rg))
check("D: the report is headed NOT CLEAN (bot24)", "NOT CLEAN" in cap.splitlines()[0], cap[:300])

# ---- E. a window already saved ----------------------------------------------------------------------------
res, cap, log, work, rg = run(new, "E", 12.0, 12.0, pz=Z_GAIN, reg={"artest": {"window": W}})
check("E: window already known -> no zoom search, NOT rendered", not res.ok and "zoom_search" not in log
      and not any(x.startswith("engine_preview") for x in log), log)
check("E: the message does not claim a zoom search", "no zoomed framing explains it" not in res.message, res.message)

# ---- F. the zoom search crashes ---------------------------------------------------------------------------
res, cap, log, work, rg = run(new, "F1", 14.0, pz="CRASH")
check("F: crash + 14 % -> NOT rendered, no exception", not res.ok and "NOT rendered" in res.message, res.message[:300])
res, cap, log, work, rg = run(new, "F2", 7.0, pz="CRASH", q_unc=7.0)
check("F: crash + 7 % -> rendered", res.ok and log.count("engine_analyze") == 1, log)

# ---- G. bounds --------------------------------------------------------------------------------------------
for unc, zs, rendered in ((5.0, 0, True), (5.1, 1, True), (10.0, 1, True), (10.1, 1, False)):
    res, cap, log, work, rg = run(new, "G%s" % str(unc).replace(".", "_"), unc, pz=Z_NONE, q_unc=unc)
    check("G: %.1f %% -> zoom searches %d, %s" % (unc, zs, "rendered" if rendered else "NOT rendered"),
          log.count("zoom_search") == zs and res.ok is rendered, (log, res.message[:120]))

# an "accepted" record above the engine's own bar (it refuses above 15 %) is not the engine's: as live
res, cap, log, work, rg = run(new, "G70", 70.0, pz=Z_GAIN)
res_o, cap_o, log_o, _, _ = run(old, "G70_old", 70.0, pz=Z_GAIN)
check("G: accepted + 70 %% (not an engine value) -> exactly as live, no zoom search", log == log_o and res.ok
      and "zoom_search" not in log and cap == cap_o, (log, log_o))

shutil.rmtree(T, ignore_errors=True)
print("WEAKGATE25_TESTS ALL PASS" if ok else "WEAKGATE25_TESTS FAILED")
sys.exit(0 if ok else 1)
