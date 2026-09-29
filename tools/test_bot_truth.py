"""Proves patch_bot_truth (bot13; harness from test_bot_dubaudio): Somali-voiced film cut by
mistake and a voice MEASURED off the lips are INCOMPLETE with the reason at the top; a voice on the lips
gets a green line; a lip-sync measurement that finds no voice or cannot run is reported and never blocks.
Usage: python3 test_bot_truth.py <patched bot dir>   prints TRUTH_TESTS ALL PASS"""
import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NEW = sys.argv[1]
T = Path(tempfile.mkdtemp(prefix="artest_"))
FIX = T / "fixture.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", "-c:a", "aac", "-shortest", str(FIX)], check=True)
FAKES = {
    "engine": r'''
import os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("engine %s\n" % a[0])
w = os.environ["ENGINE_WORK"]
if a[0] == "preview" and "--plan-only" not in a:
    shutil.copy(os.environ["FIXTURE"], os.path.join(os.environ["FAKE_OUT"], a[a.index("--output-name") + 1]))
    os.makedirs(w, exist_ok=True)
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
    "opening_restore": 'print("OPENING_GATE OK"); print("OPENING_RESTORE NOT NEEDED")',
    "restore_head": r'''
import os
open(os.environ["FAKE_LOG"], "a").write("restore_head\n")
if os.environ.get("RH_MODE") == "red":
    print("srinivasa: dub voice 5318 s in 287 stretches; in the output: 97.7%")
    print("  voice dub 2:10:10.53 - 2:10:28.50 (18.0 s): FILM cut by mistake (its frames are in the HD) -- RED")
    print("DIALOGUE_AUDIT RED")
    print("RESTORE_HEAD NOT NEEDED")
elif os.environ.get("RH_MODE") == "refused":
    print("bheemaa: dub voice 6000 s in 900 stretches; in the output: 99.4%")
    print('DIALOGUE_AUDIT RESTORE {"dub_from": 19.958, "dub_to": 57.88, "hd_from": 11.413, "k": -8.545, "at": 4.52}')
    print("RESTORE_HEAD FAILED auto-align: the film's sound at 4.52 does not match the dub near 57.88 (best 0.21) -- refusing")
else:
    print("t: in the output: 100.0%")
    print("DIALOGUE_AUDIT GREEN")
    print("RESTORE_HEAD NOT NEEDED")
''',
    "av_sync": r'''
import os, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("av_sync %s\n" % a[a.index("--at") + 1])
mode = os.environ.get("AV_MODE", "ok")
if mode == "ok":
    print("AV_SYNC +0.012 5")
elif mode == "off":
    print("AV_SYNC +0.341 5")
elif mode == "late":
    print("AV_SYNC -0.402 3")
elif mode == "none":
    print("AV_SYNC none 0")
else:
    raise SystemExit("crash")
''',
    "auto_repair": r'''
import os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("auto_repair\n")
mode = os.environ["AR_MODE"]
print("defect at film 5926.24 (dub 6000.30): dub#1903 shown at HD 6572.38; carry-on candidate HD 6567.11")
print("defect at film 5509.44 (dub 5583.50): dub#1769 shown at HD 6138.19; carry-on candidate HD 6137.69")
if mode == "done":
    print("PROVEN dub#1903: HD 6567.11 (1.000x)")
    print("NOT PROVEN dub#1769: the new placement is not better by its own frames")
    shutil.copy(a[1], a[2])
    open(a[2], "ab").write(b"REPAIRED")
    print("AUTO_REPAIR DONE 1 2")
elif mode == "nothing":
    print("AUTO_REPAIR NOTHING 2")
else:
    print("AUTO_REPAIR FAILED repair step")
''',
    "cut_audit": 'import os; open(os.environ["FAKE_LOG"],"a").write("cut_audit\\n"); print("UNJUSTIFIED CUTS: 0")',
    "frame_audit": 'import os; open(os.environ["FAKE_LOG"],"a").write("frame_audit\\n"); '
                   'print("t: 1 shots with HD checked, 0 show the dub\'s own picture"); '
                   'print("  ok 1 (100.0%) | wrong clip (moved) 0 | HD the dub lacks (no_hd) 0 | unsure 0"); '
                   'print("FRAME_AUDIT GREEN")',
    "append_credits": 'import os; open(os.environ["FAKE_LOG"],"a").write("append_credits\\n"); '
                      'print("CREDITS: appended 5.0s of the film\'s own end credits")',
}
for k, v in FAKES.items():
    (T / (k + ".py")).write_text(v)
eng = T / "fake_engine"
eng.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, T / "engine.py"))
eng.chmod(0o755)
spec = importlib.util.spec_from_file_location("jar", os.path.join(NEW, "dubsync_job.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["jar"] = m
sys.path.insert(0, NEW)
spec.loader.exec_module(m)
m.DUBSYNC = str(eng)
m.DLG_PY = sys.executable
for k in ("switch_audio", "restore_head", "opening_restore", "av_sync", "auto_repair", "cut_audit", "frame_audit",
          "append_credits"):
    setattr(m, k.upper(), str(T / (k + ".py")))
m._quality_report = lambda title: {"locked_pct": 100.0, "shots": 1}   # a real film always has one: the dialogue section renders
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:600]))
    ok &= bool(cond)


def run(mode):
    d = T / mode
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    work = d / "work"
    work.mkdir()
    log = d / "log.txt"
    log.write_text("")
    os.environ.update({"FAKE_LOG": str(log), "FIXTURE": str(FIX), "FAKE_OUT": str(d / "out"),
                       "ENGINE_WORK": str(work), "AR_MODE": mode})
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: work
    res = asyncio.run(m.run_dubsync(FIX, FIX, "artest", None, 320, 240, 23, lambda *a: None, bitrate_k=500))
    cap = m.summary_caption("artest", res, 4.0, 1000) if res.ok else ""
    return res, cap, log.read_text().split()





def top(cap):
    return "\n".join(cap.splitlines()[:6])


os.environ["RH_MODE"] = "ok"
os.environ["AV_MODE"] = "ok"
res, cap, order = run("nothing")
check("on the lips: complete", res.ok and "INCOMPLETE" not in cap, cap)
check("on the lips: green lip-sync line", "👄 lip sync: the Somali voice is on the lips (measured at 5 places, +0.01 s)" in cap, cap)
check("the measurement runs on the finished film at 5 places", any(o.startswith("av_sync") for o in order)
      and len([x for x in open(os.environ["FAKE_LOG"]).read().split("av_sync ")[1].split()[0].split(",")]) == 5,
      order)
os.environ["AV_MODE"] = "off"
res, cap, order = run("nothing")
check("0.34 s early: INCOMPLETE at the top with the number",
      "INCOMPLETE" in cap.splitlines()[0] and "lip sync: the Somali voice is 0.34 s BEFORE the lips" in top(cap), cap)
check("0.34 s early: red lip-sync line, never green", "⛔ lip sync" in cap and "👄" not in cap, cap)
os.environ["AV_MODE"] = "late"
res, cap, order = run("nothing")
check("0.40 s late: INCOMPLETE, says AFTER", "INCOMPLETE" in cap and "0.40 s AFTER the lips" in cap, cap)
for mode in ("none", "crash"):
    os.environ["AV_MODE"] = mode
    res, cap, order = run("nothing")
    check("measurement %s: never blocks (complete)" % mode, res.ok and "INCOMPLETE" not in cap, cap)
    check("measurement %s: says it was not measured" % mode, "ℹ️ lip sync: not measured" in cap, cap)
os.environ["AV_MODE"] = "ok"
os.environ["RH_MODE"] = "red"
res, cap, order = run("nothing")
check("film voice cut: INCOMPLETE at the top", "INCOMPLETE" in cap.splitlines()[0], cap)
check("film voice cut: the exact missing seconds at the top",
      "dialogue: film with Somali voice was cut by mistake -- dub 2:10:10.53 - 2:10:28.50" in top(cap), cap)
os.environ["RH_MODE"] = "ok"
res, cap, order = run("nothing")
check("everything fine again: complete, the other steps still run",
      res.ok and "INCOMPLETE" not in cap and all(x in order for x in ("restore_head", "auto_repair", "cut_audit",
                                                                        "frame_audit", "append_credits")), order)
shutil.rmtree(T, ignore_errors=True)
print("TRUTH_TESTS", "ALL PASS" if ok else "FAILED")
