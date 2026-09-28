"""Proves patch_bot_speedretry on the bot's REAL run_dubsync with a fake engine.
Runs inside the bot container:  python3 test_bot_speedretry.py <patched bot dir>
The fake analyze writes speed.json + edl.json into the work dir: refused unless the job runs
with DUBSYNC2_RETIME_MIN (the retry) and speed.json was removed first (the engine re-measures).
  normal      accepted first time        -> analyze once, no env, delivered
  retry_ok    refused, consistent 2.2 %  -> analyze twice (2nd with env, speed.json gone), delivered
  still       refused both times         -> refusal saying it was analysed twice
  weak        refused, windows disagree  -> no retry, refusal
  retimed     refused, already retimed   -> no retry, refusal
Prints SPEEDRETRY_TESTS ALL PASS"""
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NEW = sys.argv[1]
T = Path(tempfile.mkdtemp(prefix="srtest_"))
FIX = T / "fixture.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", "-c:a", "aac", "-shortest", str(FIX)], check=True)
ENGINE = r'''
import json, os, shutil, sys
a = sys.argv[1:]
w = os.environ["FAKE_WORK"]
env = os.environ.get("DUBSYNC2_RETIME_MIN")
log = open(os.environ["FAKE_LOG"], "a")
log.write("engine %s env=%s speedjson=%s\n" % (a[0], env, os.path.exists(os.path.join(w, "speed.json"))))
if a[0] == "analyze":
    scen = os.environ["SCEN"]
    retry = env is not None
    sp = {"normal": {"decision": "same speed", "ratio": 1.001, "windows": 14, "same_side": 0.5, "gain": 0.001},
          "retry_ok": {"decision": "same speed", "ratio": 0.978, "windows": 14, "same_side": 1.0, "gain": 0.036},
          "still": {"decision": "same speed", "ratio": 0.978, "windows": 14, "same_side": 1.0, "gain": 0.036},
          "weak": {"decision": "same speed", "ratio": 1.010, "windows": 16, "same_side": 0.75, "gain": 0.018},
          "retimed": {"decision": "retime", "ratio": 0.93, "windows": 16, "same_side": 1.0, "gain": 0.2}}[scen]
    if retry:
        sp = dict(sp, decision="retime")
    json.dump(sp, open(os.path.join(w, "speed.json"), "w"))
    ok = scen == "normal" or (scen == "retry_ok" and retry)
    json.dump({"conform_offset": {"accepted": ok, "reason": "accepted" if ok else "refused: test",
                                  "unconfirmed_pct": 70.0}, "edl": []},
              open(os.path.join(w, "edl.json"), "w"))
if a[0] == "preview" and "--plan-only" not in a:
    name = a[a.index("--output-name") + 1]
    shutil.copy(os.environ["FIXTURE"], os.path.join(os.environ["FAKE_OUT"], name))
    open(os.path.join(w, "provenance.json"), "w").write("[]")
    print("Expected duration: 4.0s")
    print("Provenance: %s/provenance.json" % w)
if a[0] == "preview" and "--plan-only" in a:
    print("accidental: 0.0s")
if a[0] == "integrity":
    print("RELEASE APPROVED")
'''
TOOLS = {
    "switch_audio": 'import shutil,sys; a=sys.argv[1:]; shutil.copy(a[a.index("--video")+1], a[a.index("--out")+1])',
    "opening_restore": 'print("OPENING_GATE OK"); print("OPENING_RESTORE NOT NEEDED")',
    "restore_head": 'print("t: in the output: 100.0%"); print("DIALOGUE_AUDIT GREEN"); print("RESTORE_HEAD NOT NEEDED")',
    "cut_audit": 'print("UNJUSTIFIED CUTS: 0")',
    "frame_audit": 'print("t: 1 shots with HD checked, 0 show the dub\'s own picture"); '
                   'print("  ok 1 (100.0%) | wrong clip (moved) 0 | HD the dub lacks (no_hd) 0 | unsure 0"); '
                   'print("FRAME_AUDIT GREEN")',
    "append_credits": 'print("CREDITS: appended 5.0s of the film\'s own end credits")',
}
(T / "engine.py").write_text(ENGINE)
for k, v in TOOLS.items():
    (T / (k + ".py")).write_text(v)
eng = T / "fake_engine"
eng.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, T / "engine.py"))
eng.chmod(0o755)
spec = importlib.util.spec_from_file_location("jnew", os.path.join(NEW, "dubsync_job.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["jnew"] = m
sys.path.insert(0, NEW)
spec.loader.exec_module(m)
m.DUBSYNC = str(eng)
m.DLG_PY = sys.executable
for k in TOOLS:
    setattr(m, k.upper(), str(T / (k + ".py")))
m._quality_report = lambda title: {}
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + detail[:700]))
    ok &= bool(cond)


def run(scen):
    d = T / scen
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    work = d / "work"
    work.mkdir()
    log = d / "log.txt"
    log.write_text("")
    os.environ.update({"FAKE_LOG": str(log), "FIXTURE": str(FIX), "FAKE_OUT": str(d / "out"),
                       "FAKE_WORK": str(work), "SCEN": scen})
    os.environ.pop("DUBSYNC2_RETIME_MIN", None)
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: work
    res = asyncio.run(m.run_dubsync(FIX, FIX, "srtest", None, 320, 240, 23, lambda *a: None, bitrate_k=500))
    cap = m.summary_caption("srtest", res, 4.0, 1000) if res.ok else ""
    an = [ln for ln in log.read_text().splitlines() if ln.startswith("engine analyze")]
    return res, cap, an, log.read_text()


res, cap, an, lg = run("normal")
check("normal: analysed once, no env, delivered", res.ok and len(an) == 1 and "env=None" in an[0]
      and "env=None" in lg.splitlines()[-1] and not res.stats.get("speed_retry"), "%s %s" % (res.message, an))
res, cap, an, lg = run("retry_ok")
check("retry_ok: analysed twice, second with env and speed.json removed", len(an) == 2
      and "env=None" in an[0] and "env=0.0100" in an[1] and "speedjson=False" in an[1], str(an))
check("retry_ok: delivered with the self-repair line", res.ok and "analysed again with the speed matched" in cap
      and "-2.20%" in cap, res.message + " | " + cap)
res, cap, an, lg = run("still")
check("still: refused after two analyses, message says so", (not res.ok) and len(an) == 2
      and "Analysed twice" in res.message and "-2.20%" in res.message, res.message + str(an))
res, cap, an, lg = run("weak")
check("weak: no retry, refused", (not res.ok) and len(an) == 1 and "Analysed twice" not in res.message,
      res.message + str(an))
res, cap, an, lg = run("retimed")
check("retimed: no retry, refused", (not res.ok) and len(an) == 1, res.message + str(an))
shutil.rmtree(T, ignore_errors=True)
print("SPEEDRETRY_TESTS", "ALL PASS" if ok else "FAILED")
