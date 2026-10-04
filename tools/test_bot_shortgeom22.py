"""bot22 = live bot + the short-pair geometry retry (harness from test_bot_space21). Run inside the bot container:
    python3 test_bot_shortgeom22.py <live bot dir copy> <bot22 dir copy>
  A. NO BREAK: an accepted pair -> same steps, same film bytes, same report, same stats as the live bot; the
     list file is never written.
  B. THE TOXIC CASE: a short pair refused, accepted once the title is listed -> analysed twice, title listed (other
     titles kept), old work dir moved aside (not deleted), film delivered, report says what happened.
     (control) the live bot refuses the same pair.
  C. A WRONG short pair (refused even when listed) -> analysed twice, refused, the message says it was analysed
     twice; nothing rendered.
  D. A LONG pair refused -> no geometry retry: same refusal as the live bot, analysed once, list untouched.
  E. Speed retry first: a short pair whose speed difference qualifies -> the speed retry runs first exactly as
     live; accepted there -> the list is never written.
  F. _media_s reads a real file's duration; a short pair = both 20 s .. 5 min; a 4 s pair is handled as live.
Prints SHORTGEOM22_TESTS ALL PASS."""
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
T = Path(tempfile.mkdtemp(prefix="sgtest_"))
FIX = T / "fixture.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", "-c:a", "aac", "-shortest", str(FIX)], check=True)
REG = T / "short_geom.json"
FAKES = {
    "engine": r'''
import json, os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("engine_%s\n" % a[0])
w = os.environ["ENGINE_WORK"]
os.makedirs(w, exist_ok=True)
if a[0] == "analyze":
    mode = os.environ.get("AN_MODE", "accept")
    try:
        listed = "artest" in json.load(open(os.environ["FAKE_REG"]))
    except Exception:
        listed = False
    acc = (mode == "accept" or (mode == "geom" and listed)
           or (mode == "speed" and bool(os.environ.get("DUBSYNC2_RETIME_MIN"))))
    co = {"accepted": True, "reason": "accepted"} if acc else \
         {"accepted": False, "reason": "refused: only 21% of shots confirmed", "unconfirmed_pct": 77.21}
    json.dump({"conform_offset": co, "edl": []}, open(os.path.join(w, "edl.json"), "w"))
    sp = {"decision": "same speed", "ratio": 1.022, "windows": 14, "same_side": 1.0, "gain": 0.02} \
        if mode == "speed" else {"decision": "not measurable (0 usable windows)", "ratio": 1.0, "windows": 0}
    sp["hd_original"] = "/x/raw/artest_hd_ORIG.mp4"
    json.dump(sp, open(os.path.join(w, "speed.json"), "w"))
    open(os.path.join(w, "marker_%s" % ("listed" if listed else "plain")), "w").write("1")
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
    m._quality_report = lambda title: {"locked_pct": 100.0, "shots": 1}
    if hasattr(m, "SHORT_GEOM"):
        m.SHORT_GEOM = str(REG)
        m.PARKED_WORK = T / "parked"
    return m


old, new = load(LIVE, "job_live"), load(NEW, "job_22")
ok = True
real_media = new._media_s


def as_trailer(on):
    """The fixture is a 4 s clip (too short to be a trailer): report 120 s for the short-pair scenarios."""
    new._media_s = (lambda p: 120.0) if on else real_media


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:700]), flush=True)
    ok &= bool(cond)


def run(m, tag, an="accept"):
    d = T / tag
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    work = d / "work" / "abc123"
    work.mkdir(parents=True)
    (work / "old_cache.npz").write_text("made without the geometry")
    log = d / "log.txt"
    log.write_text("")
    os.environ.update({"FAKE_LOG": str(log), "FIXTURE": str(FIX), "FAKE_OUT": str(d / "out"),
                       "ENGINE_WORK": str(work), "AN_MODE": an, "FAKE_REG": str(REG)})
    os.environ.pop("DUBSYNC2_RETIME_MIN", None)
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: work
    res = asyncio.run(m.run_dubsync(FIX, FIX, "artest", None, 320, 240, 23, lambda *a: None, bitrate_k=500))
    cap = m.summary_caption("artest", res, 4.0, 1000) if res.ok else ""
    return res, cap, log.read_text().split(), work


def film(res):
    return open(res.path, "rb").read() if res.ok and res.path and os.path.exists(res.path) else b""


def reg():
    try:
        return json.load(open(REG))
    except Exception:
        return None


# ---- A. no break ------------------------------------------------------------------------------------------
REG.unlink(missing_ok=True)
ro, co, lo, _ = run(old, "A_old")
rn, cn, ln, _ = run(new, "A_new")
check("A: same steps in the same order as the live bot", lo == ln, (lo, ln))
check("A: same film bytes", film(ro) == film(rn) and len(film(rn)) > 1000)
check("A: same report", co == cn, cn)
so = {k: str(v).replace("A_old", "A_") for k, v in ro.stats.items()}
sn = {k: str(v).replace("A_new", "A_") for k, v in rn.stats.items()}
check("A: same stats (%d values)" % len(sn), so == sn, {k: (so.get(k), sn.get(k)) for k in set(so) | set(sn)
                                                         if so.get(k) != sn.get(k)})
check("A: the list file was never written", reg() is None, reg())

# ---- B. the Toxic case ------------------------------------------------------------------------------------
as_trailer(True)
json.dump({"othertitle_123456": {"set": "earlier"}}, open(REG, "w"))
res, cap, log, work = run(new, "B", an="geom")
check("B: analysed twice", log.count("engine_analyze") == 2, log)
check("B: the title is listed, the other title kept", set(reg() or {}) == {"artest", "othertitle_123456"}, reg())
check("B: the second analysis ran listed", (work / "marker_listed").exists() and not (work / "marker_plain").exists(),
      os.listdir(work))
parked = list((T / "parked").glob("abc123_*"))
check("B: the old work dir moved aside, not deleted", len(parked) == 1 and (parked[0] / "old_cache.npz").exists()
      and not (work / "old_cache.npz").exists(), parked)
check("B: the film is delivered", res.ok and len(film(res)) > 1000, res.message[:300])
check("B: the report says what happened", "analysed again with its picture measured inside the clip" in cap
      and "77.21" in cap, cap[:1500])
REG.unlink(missing_ok=True)                       # the control starts with nothing listed, as the live bot would
res_o, cap_o, log_o, _ = run(old, "B_old", an="geom")
check("B: (control) the live bot refuses this pair", not res_o.ok and "NOT rendered" in res_o.message
      and log_o.count("engine_analyze") == 1, (res_o.message[:200], log_o))

# ---- C. a wrong short pair --------------------------------------------------------------------------------
REG.unlink(missing_ok=True)
res, cap, log, work = run(new, "C", an="never")
check("C: analysed twice, then refused", not res.ok and log.count("engine_analyze") == 2
      and not any(x.startswith("engine_preview") for x in log), log)
check("C: the message says it was analysed twice", "NOT rendered" in res.message
      and "Short clip: analysed twice" in res.message, res.message)

# ---- D. a long pair -----------------------------------------------------------------------------------------
REG.unlink(missing_ok=True)
new._media_s = lambda p: 5000.0
res, cap, log, work = run(new, "D", an="never")
res_o, cap_o, log_o, _ = run(old, "D_old", an="never")
as_trailer(True)
check("D: a long pair is analysed once, as live", log.count("engine_analyze") == 1 and log == log_o, (log, log_o))
check("D: same refusal message as live", res.message == res_o.message, (res.message, res_o.message))
check("D: the list file untouched", reg() is None, reg())

# ---- E. speed retry first ---------------------------------------------------------------------------------
REG.unlink(missing_ok=True)
res, cap, log, work = run(new, "E", an="speed")
res_o, cap_o, log_o, _ = run(old, "E_old", an="speed")
check("E: the speed retry runs first, as live (analysed twice, accepted)",
      res.ok and log.count("engine_analyze") == 2 and log == log_o, (log, log_o))
check("E: the list file never written", reg() is None, reg())
check("E: same film bytes as live", film(res) == film(res_o))

# ---- F. durations -----------------------------------------------------------------------------------------
as_trailer(False)
check("F: _media_s reads 4 s", abs(new._media_s(FIX) - 4.0) < 0.2, new._media_s(FIX))
check("F: two 4 s files are NOT a short pair (under 20 s: not a trailer)", not new._short_pair(FIX, FIX))
check("F: _media_s of a missing file is 0", new._media_s(T / "nope.mp4") == 0.0)
for a, b, want in ((120.0, 262.0, True), (20.0, 299.9, True), (19.9, 120.0, False), (120.0, 300.0, False),
                   (120.0, 7200.0, False), (0.0, 120.0, False)):
    it = iter((a, b))
    new._media_s = lambda p: next(it)
    check("F: pair %.1f s + %.1f s -> short pair %s" % (a, b, want), new._short_pair("x", "y") is want)
new._media_s = real_media
# a 4 s refused pair: no geometry retry (exactly the live bot)
REG.unlink(missing_ok=True)
res, cap, log, work = run(new, "F4", an="never")
res_o, cap_o, log_o, _ = run(old, "F4_old", an="never")
check("F: a refused 4 s pair is handled exactly as live (no retry)", log == log_o and res.message == res_o.message
      and reg() is None, (log, log_o))

shutil.rmtree(T, ignore_errors=True)
print("SHORTGEOM22_TESTS ALL PASS" if ok else "SHORTGEOM22_TESTS FAILED")
sys.exit(0 if ok else 1)
