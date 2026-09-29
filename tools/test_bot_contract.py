"""Proves patch_bot_contract on the bot's REAL run_dubsync, with fake engine tools that fail on cue.
Runs inside the bot container:  python3 test_bot_contract.py <current bot dir> <patched bot dir>
Scenarios (each run through the current AND the patched module):
  ok          everything works              -> patched caption == current caption (no regression)
  pushpa      the bot's hash points at an empty work dir, the engine wrote another one
              (what shipped Pushpa 2 dub-only, no credits) -> patched: sound mix + credits, healed
  sa_once     the audio step fails once      -> patched: built on the second try
  sa_always   the audio step always fails    -> patched: INCOMPLETE at the top of the report
  cr_once     the credits step fails once    -> patched: added on the second try
  cancel      John cancels during the audio  -> patched: stops, no later step starts
  short_audio the mixed file's sound is shorter than its picture -> patched: reported
Prints CONTRACT_TESTS ALL PASS"""
import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CUR, NEW = sys.argv[1], sys.argv[2]
T = Path(tempfile.mkdtemp(prefix="ctest_"))
FIX = T / "fixture.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", "-c:a", "aac", "-shortest", str(FIX)], check=True)

FAKES = {
    "engine": r'''
import os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("engine %s\n" % a[0])
if a[0] == "preview" and "--plan-only" not in a:
    name = a[a.index("--output-name") + 1]
    shutil.copy(os.environ["FIXTURE"], os.path.join(os.environ["FAKE_OUT"], name))
    w = os.environ["ENGINE_WORK"]
    os.makedirs(w, exist_ok=True)
    open(os.path.join(w, "provenance.json"), "w").write("[]")
    print("Expected duration: 4.0s")
    print("Provenance: %s/provenance.json" % w)
if a[0] == "preview" and "--plan-only" in a:
    print("accidental: 0.0s")
if a[0] == "integrity":
    print("RELEASE APPROVED")
''',
    "switch_audio": r'''
import os, shutil, subprocess, sys, time
a = sys.argv[1:]
log = os.environ["FAKE_LOG"]
n = open(log).read().count("switch_audio") + 1
open(log, "a").write("switch_audio\n")
mode = os.environ.get("SA_MODE", "ok")
work = a[a.index("--work") + 1]
vid, out = a[a.index("--video") + 1], a[a.index("--out") + 1]
if mode == "cancel":
    open(os.environ["CANCEL_FLAG"], "w").write("1")
    time.sleep(1)
    sys.exit(1)
if not os.path.exists(os.path.join(work, "provenance.json")):
    print("FileNotFoundError: %s/provenance.json" % work); sys.exit(1)
if mode == "always" or (mode == "once" and n == 1):
    print("MemoryError: out of memory while mixing"); sys.exit(1)
if mode == "short":
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", vid, "-map", "0:v", "-map", "0:a", "-c:v", "copy",
                    "-af", "atrim=0:1.5", "-c:a", "aac", out], check=True)
else:
    shutil.copy(vid, out)
print("HD passages: 3")
''',
    "opening_restore": 'print("OPENING_GATE OK"); print("OPENING_RESTORE NOT NEEDED")',
    "restore_head": r'''
import os
open(os.environ["FAKE_LOG"], "a").write("restore_head\n")
print("t: dub voice 100 s in 10 stretches; in the output: 100.0%")
print("DIALOGUE_AUDIT GREEN")
print("RESTORE_HEAD NOT NEEDED")
''',
    "cut_audit": r'''
import os
open(os.environ["FAKE_LOG"], "a").write("cut_audit\n")
print("UNJUSTIFIED CUTS: 0")
''',
    "frame_audit": r'''
import os
open(os.environ["FAKE_LOG"], "a").write("frame_audit\n")
print("t: 10 shots with HD checked, 0 show the dub's own picture")
print("  ok 10 (100.0%) | wrong clip (moved) 0 | HD the dub lacks (no_hd) 0 | unsure 0")
print("  repeats (HD shown twice): 0, 0.0 s")
print("FRAME_AUDIT GREEN")
''',
    "append_credits": r'''
import os, sys
a = sys.argv[1:]
log = os.environ["FAKE_LOG"]
n = open(log).read().count("append_credits") + 1
open(log, "a").write("append_credits\n")
work = a[a.index("--work") + 1]
if not os.path.exists(os.path.join(work, "provenance.json")):
    print("SKIP: no provenance.json (not a conform render)"); sys.exit(0)
if os.environ.get("CR_MODE") == "once" and n == 1:
    print("CREDITS FAILED: ffmpeg concat error"); sys.exit(0)
print("CREDITS: appended 5.0s of the film's own end credits with their music (HD 1.0 -> 6.0 s)")
''',
}
for k, v in FAKES.items():
    (T / (k + ".py")).write_text(v)
eng = T / "fake_engine"
eng.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, T / "engine.py"))
eng.chmod(0o755)


def load(d, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, "dubsync_job.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m               # dataclasses look their module up while it loads
    sys.path.insert(0, d)
    spec.loader.exec_module(m)
    sys.path.remove(d)
    m.DUBSYNC = str(eng)
    m.DLG_PY = sys.executable
    for k in ("switch_audio", "restore_head", "opening_restore", "cut_audit", "frame_audit", "append_credits"):
        setattr(m, k.upper(), str(T / (k + ".py")))
    m._quality_report = lambda title: {}
    if hasattr(m, "AUDIO_MODE"):
        # these scenarios test the dub-talk / HD-music switch step (its retry, failures, cancel); the
        # bot12 default (the dub's sound, no switch) is proven by test_bot_dubaudio.py
        m.AUDIO_MODE = "switch"
    return m


def run(m, scen):
    d = T / (m.__name__ + "_" + scen)
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    bot_work, eng_work = d / "work_bot", d / "work_engine"
    bot_work.mkdir()
    log, flag = d / "log.txt", d / "cancel.flag"
    log.write_text("")
    env = {"FAKE_LOG": str(log), "FIXTURE": str(FIX), "FAKE_OUT": str(d / "out"),
           "ENGINE_WORK": str(eng_work if scen == "pushpa" else bot_work), "CANCEL_FLAG": str(flag),
           "SA_MODE": {"sa_once": "once", "sa_always": "always", "cancel": "cancel",
                       "short_audio": "short"}.get(scen, "ok"),
           "CR_MODE": "once" if scen == "cr_once" else "ok"}
    os.environ.update(env)
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: bot_work
    res = asyncio.run(m.run_dubsync(FIX, FIX, "ctest", None, 320, 240, 23, lambda *a: None,
                                    bitrate_k=500, should_cancel=lambda: flag.exists()))
    cap = m.summary_caption("ctest", res, 4.0, 1000) if res.ok else ""
    return res, cap, log.read_text()


cur, new = load(CUR, "cur"), load(NEW, "new")
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + detail[:600]))
    ok &= bool(cond)


r0, c0, _ = run(cur, "ok")
r1, c1, l1 = run(new, "ok")
check("ok: caption unchanged", c0 == c1, "\n--cur--\n%s\n--new--\n%s" % (c0, c1))
check("ok: nothing missing", r1.stats.get("contract_missing") == [], str(r1.stats.get("contract_missing")))

r0, c0, _ = run(cur, "pushpa")
r1, c1, _ = run(new, "pushpa")
check("pushpa: current bot ships dub-only (the bug reproduced)", str(r0.stats.get("audio")).startswith("dub only"),
      str(r0.stats.get("audio")))
check("pushpa: patched uses the engine's work dir -> sound mix",
      r1.stats.get("audio") == "dub dialogue + HD master music", str(r1.stats))
check("pushpa: patched adds the credits", str(r1.stats.get("credits", "")).startswith("appended"), str(r1.stats))
check("pushpa: heal reported", "self-repaired: work dir" in c1, c1)

r1, c1, _ = run(new, "sa_once")
check("sa_once: built on the second try", r1.stats.get("audio") == "dub dialogue + HD master music"
      and "second try" in c1 and not r1.stats.get("contract_missing"), c1)

r1, c1, _ = run(new, "sa_always")
check("sa_always: INCOMPLETE at the top", "INCOMPLETE" in c1.splitlines()[0]
      and "sound mix" in c1 and "MemoryError" in c1, c1)

r1, c1, _ = run(new, "cr_once")
check("cr_once: credits on the second try", str(r1.stats.get("credits", "")).startswith("appended")
      and "end credits: failed once" in c1 and not r1.stats.get("contract_missing"), c1)

r1, c1, l1 = run(new, "cancel")
check("cancel: patched stops at the audio step", (not r1.ok) and r1.message == "cancelled"
      and "restore_head" not in l1 and l1.count("switch_audio") == 1, "%s | %s" % (r1.message, l1))

r1, c1, _ = run(new, "short_audio")
check("short_audio: length mismatch reported", "file: picture" in c1 and "INCOMPLETE" in c1, c1)

shutil.rmtree(T, ignore_errors=True)
print("CONTRACT_TESTS", "ALL PASS" if ok else "FAILED")
