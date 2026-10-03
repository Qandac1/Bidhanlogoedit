"""bot21 = live bot + the disk-space guard (harness from test_bot_opening). Run inside the bot container:
    python3 test_bot_space21.py <live bot dir copy> <bot21 dir copy>
  A. NO BREAK: with enough free space the patched bot runs the same steps in the same order, delivers the same
     bytes and writes the same report as the live bot -- and never starts the space guard.
  B. FULL DISK at the start, nothing can be cleared: the job stops BEFORE the engine with a plain disk message.
  C. LOW at the start, the guard clears enough: the film runs normally.
  D. The opening step dies with -28 once: it is run again and the film gets its opening (no INCOMPLETE).
  E. The opening step dies with -28 twice: INCOMPLETE says the disk was full.
  F. The opening-voice step dies with -28 once: run again, the voice is restored (no INCOMPLETE).
  G. The exact lines of Sardar 2 (2026-10-03) are recognised as a full disk; Kondal's alignment line is not.
  H. The space a film needs: Sardar 2's sources -> ~36 GB; a trailer -> 15; never above 90.
Prints SPACE21_TESTS ALL PASS."""
import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIVE, NEW = sys.argv[1], sys.argv[2]
T = Path(tempfile.mkdtemp(prefix="artest_"))
FIX = T / "fixture.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", "-c:a", "aac", "-shortest", str(FIX)], check=True)
E28 = "finished with error code: -28 (No space left on device)"
FAKES = {
    "engine": r'''
import os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("engine_%s\n" % a[0])
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
    "opening_restore": r'''
import os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("opening_restore\n")
mode = os.environ.get("OG_MODE", "none")
n = open(os.environ["FAKE_LOG"]).read().split().count("opening_restore")
if mode == "enospc-always" or (mode == "enospc-once" and n == 1):
    print("OPENING_GATE ADD 13.07 57.88 44.8")
    print("OPENING_RESTORE FAILED %s")
elif mode in ("done", "enospc-once"):
    shutil.copy(a[1], a[2])
    open(a[2], "ab").write(b"OPENED")
    print("OPENING_NOTE the film now starts at 0:29 of the Somali copy (first shared picture): 29s of film added")
    print("OPENING_RESTORE DONE 28.88")
else:
    print("OPENING_GATE OK")
    print("OPENING_RESTORE NOT NEEDED")
''' % E28,
    "restore_head": r'''
import os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("restore_head\n")
mode = os.environ.get("RH_MODE", "ok")
n = open(os.environ["FAKE_LOG"]).read().split().count("restore_head")
if mode == "enospc-once" and n == 1:
    print("t: dub voice 5670 s in 900 stretches; in the output: 99.3%%")
    print('DIALOGUE_AUDIT RESTORE {"dub_from": 102.006, "dub_to": 186.4, "hd_from": 83.789, "k": -18.217, "at": 5.4}')
    print("RESTORE_HEAD FAILED %s")
elif mode == "enospc-once":
    shutil.copy(a[1], a[2])
    open(a[2], "ab").write(b"VOICED")
    print("t: in the output: 100.0%%")
    print("DIALOGUE_AUDIT GREEN")
    print("RESTORE_HEAD DONE 84.39")
else:
    print("t: in the output: 100.0%%")
    print("DIALOGUE_AUDIT GREEN")
    print("RESTORE_HEAD NOT NEEDED")
''' % E28,
    "auto_repair": 'import os; open(os.environ["FAKE_LOG"],"a").write("auto_repair\\n"); print("AUTO_REPAIR NOTHING 0")',
    "tail_restore": 'import os; open(os.environ["FAKE_LOG"],"a").write("tail_restore\\n"); print("TAIL_RESTORE NOT NEEDED")',
    "cut_audit": 'import os; open(os.environ["FAKE_LOG"],"a").write("cut_audit\\n"); print("UNJUSTIFIED CUTS: 0")',
    "frame_audit": 'import os; open(os.environ["FAKE_LOG"],"a").write("frame_audit\\n"); '
                   'print("t: 1 shots with HD checked, 0 show the dub\'s own picture"); '
                   'print("  ok 1 (100.0%) | wrong clip (moved) 0 | HD the dub lacks (no_hd) 0 | unsure 0"); '
                   'print("FRAME_AUDIT GREEN")',
    "append_credits": 'import os; open(os.environ["FAKE_LOG"],"a").write("append_credits\\n"); '
                      'print("CREDITS: appended 5.0s of the film\'s own end credits")',
    "space_guard": r'''
import os, sys
open(os.environ["FAKE_LOG"], "a").write("space_guard_%s\n" % sys.argv[2])
if os.environ.get("GUARD_FREES") == "1":
    open(os.environ["FREED_FLAG"], "w").write("1")
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
    return m


old, new = load(LIVE, "job_live"), load(NEW, "job_21")
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:700]), flush=True)
    ok &= bool(cond)


def run(m, tag, og="none", rh="ok"):
    d = T / tag
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    work = d / "work"
    work.mkdir()
    log = d / "log.txt"
    log.write_text("")
    os.environ.update({"FAKE_LOG": str(log), "FIXTURE": str(FIX), "FAKE_OUT": str(d / "out"),
                       "ENGINE_WORK": str(work), "OG_MODE": og, "RH_MODE": rh, "FREED_FLAG": str(d / "freed")})
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: work
    res = asyncio.run(m.run_dubsync(FIX, FIX, "artest", None, 320, 240, 23, lambda *a: None, bitrate_k=500))
    cap = m.summary_caption("artest", res, 4.0, 1000) if res.ok else ""
    return res, cap, log.read_text().split()


def film(res):
    return open(res.path, "rb").read() if res.ok and res.path and os.path.exists(res.path) else b""


os.environ["GUARD_FREES"] = "0"
# ---- A. no break ------------------------------------------------------------------------------------------
for og in ("none", "done"):
    ro, co, lo = run(old, "A_old_" + og, og=og)
    rn, cn, ln = run(new, "A_new_" + og, og=og)
    check("A[%s]: same steps in the same order as the live bot" % og, lo == ln, (lo, ln))
    check("A[%s]: the space guard never started" % og, not any(x.startswith("space_guard") for x in ln), ln)
    check("A[%s]: same film bytes" % og, film(ro) == film(rn) and len(film(rn)) > 1000)
    check("A[%s]: same report" % og, co == cn and "disk" not in cn.lower(), cn)
    # the two runs live in two test folders (A_old_.. / A_new_..): compare with that name taken out
    so = {k: str(v).replace("A_old_", "A_") for k, v in ro.stats.items()}
    sn = {k: str(v).replace("A_new_", "A_") for k, v in rn.stats.items()}
    check("A[%s]: same stats (%d values)" % (og, len(sn)), so == sn,
          {k: (so.get(k), sn.get(k)) for k in set(so) | set(sn) if so.get(k) != sn.get(k)})

# ---- B. full disk at the start ----------------------------------------------------------------------------
real_free = new._free_gb
new._free_gb = lambda: 5.0
res, cap, log = run(new, "B")
check("B: the job stops before the engine", not res.ok and not any(x.startswith("engine") for x in log), log)
check("B: the guard was asked for the film's need first", log == ["space_guard_15"], log)
check("B: the message says the disk is full, in plain words",
      "disk is full" in res.message and "5 GB free" in res.message and "Nothing was rendered" in res.message,
      res.message)

# ---- C. low at the start, the guard clears enough ---------------------------------------------------------
os.environ["GUARD_FREES"] = "1"
new._free_gb = lambda: 100.0 if os.path.exists(os.environ["FREED_FLAG"]) else 5.0
res, cap, log = run(new, "C")
check("C: the film runs after the guard cleared space", res.ok and log[0] == "space_guard_15"
      and any(x.startswith("engine_preview") for x in log), log)
check("C: the note says what happened", "old caches cleared" in str(res.stats.get("space_note")), res.stats.get("space_note"))
check("C: no INCOMPLETE", "INCOMPLETE" not in cap, cap)
os.environ["GUARD_FREES"] = "0"
new._free_gb = real_free

# ---- D. opening dies on a full disk once ------------------------------------------------------------------
res, cap, log = run(new, "D", og="enospc-once")
check("D: the opening step ran twice", log.count("opening_restore") == 2, log)
check("D: the film has its opening", b"OPENED" in film(res), res.stats.get("opening_restore"))
check("D: no INCOMPLETE", "INCOMPLETE" not in cap and "opening_restore" not in res.stats, cap)
# the live bot on the same film: INCOMPLETE (what John got)
res_o, cap_o, log_o = run(old, "D_old", og="enospc-once")
check("D: (control) the live bot delivers this film INCOMPLETE", "INCOMPLETE" in cap_o and log_o.count("opening_restore") == 1, cap_o)

# ---- E. opening dies on a full disk twice -----------------------------------------------------------------
res, cap, log = run(new, "E", og="enospc-always")
check("E: tried twice, then INCOMPLETE", log.count("opening_restore") == 2 and "INCOMPLETE" in cap.splitlines()[0], cap)
check("E: the unrepaired film is still delivered", res.ok and b"OPENED" not in film(res))

# ---- F. the opening voice dies on a full disk once --------------------------------------------------------
res, cap, log = run(new, "F", rh="enospc-once")
check("F: the voice step ran twice", log.count("restore_head") == 2, log)
check("F: the voice is in the film", b"VOICED" in film(res) and res.stats.get("voice_restored_s") == 84.39,
      res.stats.get("voice_restore"))
check("F: no INCOMPLETE", "INCOMPLETE" not in cap, cap)
res_o, cap_o, log_o = run(old, "F_old", rh="enospc-once")
check("F: (control) the live bot delivers this film INCOMPLETE", "INCOMPLETE" in cap_o, cap_o)

# ---- G. the real lines ------------------------------------------------------------------------------------
check("G: Sardar 2's lines are a full disk",
      new._is_enospc("RESTORE_HEAD FAILED  finished with error code: -28 (No space left on device)")
      and new._is_enospc("OPENING_RESTORE FAILED  finished with error code: -28 (No space left on device)"))
check("G: Kondal's alignment line is not",
      not new._is_enospc("OPENING_RESTORE FAILED auto-align: the film's sound at 0.000 is dub 83.600 (corr 1.00)")
      and not new._is_enospc(None) and not new._is_enospc(""))

# ---- H. how much a film needs -----------------------------------------------------------------------------
big, small = T / "big.bin", T / "small.bin"
for f, n in ((big, 3_565_004_786), (small, 1_623_416_891)):
    with open(f, "wb") as fh:
        fh.truncate(n)                                        # sparse: no real disk used
need = new._job_need_gb(big, small)
check("H: Sardar 2's two files need ~36 GB", 35.0 <= need <= 37.0, need)
check("H: a trailer needs the 15 GB floor", new._job_need_gb(FIX, FIX) == 15.0)
with open(big, "wb") as fh:
    fh.truncate(40_000_000_000)
check("H: never above 90 GB", new._job_need_gb(big, big) == 90.0)
check("H: a step needs 3 x the film + 3 GB", abs(new._step_need_gb(small) - (3 * 1.623416891 + 3)) < 0.01)

shutil.rmtree(T, ignore_errors=True)
print("SPACE21_TESTS ALL PASS" if ok else "SPACE21_TESTS FAILED")
sys.exit(0 if ok else 1)
