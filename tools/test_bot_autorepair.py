"""Proves patch_bot_autorepair on the bot's REAL run_dubsync with fake engine tools (bot container):
  done     the repair tool proves + fixes one wrong clip -> the film is the repaired file, the report
           says "self-repaired: wrong clip at 1:38:46 re-placed", and the repair ran BEFORE the cut
           gate and the picture check (they judge the repaired film)
  nothing  nothing proven -> the film is unchanged, no repair line, no warning
  failed   the tool fails -> the film is unchanged and the report says why (never silent)
Usage: python3 test_bot_autorepair.py <patched bot dir>     prints AUTOREPAIR_TESTS ALL PASS"""
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
    "restore_head": 'import os; open(os.environ["FAKE_LOG"],"a").write("restore_head\\n"); '
                    'print("t: in the output: 100.0%"); print("DIALOGUE_AUDIT GREEN"); print("RESTORE_HEAD NOT NEEDED")',
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
for k in ("switch_audio", "restore_head", "opening_restore", "auto_repair", "cut_audit", "frame_audit", "append_credits"):
    setattr(m, k.upper(), str(T / (k + ".py")))
m._quality_report = lambda title: {}
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


res, cap, order = run("done")
check("done: film is the repaired file", res.ok and open(res.path, "rb").read().endswith(b"REPAIRED"), res.path)
check("done: report names the repair", "self-repaired: wrong clip at 1:38:46 re-placed" in cap, cap)
check("done: not-proven shot not claimed", "1:31:49" not in cap, cap)
check("done: repair before cut gate + picture check",
      order.index("auto_repair") < order.index("cut_audit") < order.index("frame_audit"), order)
res, cap, order = run("nothing")
check("nothing: film unchanged, no repair line, no warning", res.ok and not open(res.path, "rb").read().endswith(b"REPAIRED")
      and "self-repaired: wrong clip" not in cap and "wrong-clip self-repair" not in cap, cap)
res, cap, order = run("failed")
check("failed: film unchanged, report says why", res.ok and not open(res.path, "rb").read().endswith(b"REPAIRED")
      and "wrong-clip self-repair: AUTO_REPAIR FAILED" in cap, cap)
shutil.rmtree(T, ignore_errors=True)
print("AUTOREPAIR_TESTS", "ALL PASS" if ok else "FAILED")
