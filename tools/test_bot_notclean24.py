"""bot24 = live bot + the NOT CLEAN headline. Run inside the bot container:
    python3 test_bot_notclean24.py <live bot dir copy> <bot24 dir copy>
  A. NO BREAK: a clean film -> same steps, same film bytes, the SAME report text as the live bot.
  B. Picture check 84.6 % (Toxic) -> headline "NOT CLEAN: do not publish", the reason in the first lines, the film
     still delivered. (control) the live bot heads the same film "complete".
  C. Repeats 60.2 s / D. unconfirmed 14.39 % -> NOT CLEAN with their own lines.
  E. The thresholds, exactly at and just past each bound.
  F. The real numbers of 8 delivered films: Toxic, Saguni, Achcham HEVC -> not clean; Tyson, Srinivasa, Highway,
     the Sardar trailer, Half Girlfriend -> clean.
  G. INCOMPLETE and NOT CLEAN together: headline INCOMPLETE, both blocks in the first lines.
  H. _quality_fail never raises on broken input.
  I. bot.py: when a title's zoom window changes (set / other / cleared) its saved analyses are moved aside;
     unchanged -> kept.
Prints NOTCLEAN24_TESTS ALL PASS."""
import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIVE, NEW = sys.argv[1], sys.argv[2]
T = Path(tempfile.mkdtemp(prefix="nc24_"))
FIX = T / "fixture.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", "-c:a", "aac", "-shortest", str(FIX)], check=True)
FAKES = {
    "engine": r'''
import json, os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("engine_%s\n" % a[0])
w = os.environ["ENGINE_WORK"]
os.makedirs(w, exist_ok=True)
if a[0] == "analyze":
    json.dump({"conform_offset": {"accepted": True, "reason": "accepted"}, "edl": []}, open(os.path.join(w, "edl.json"), "w"))
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
    "frame_audit": r'''
import os
open(os.environ["FAKE_LOG"], "a").write("frame_audit\n")
n, ok = int(os.environ.get("FA_N", "1")), int(os.environ.get("FA_OK", "1"))
print("t: %d shots with HD checked, 0 show the dub's own picture" % n)
print("  ok %d (%.1f%%) | wrong clip (moved) %d | HD the dub lacks (no_hd) 0 | unsure 0" % (ok, 100.0 * ok / n, n - ok))
print("FRAME_AUDIT " + ("GREEN" if ok == n else "RED"))
''',
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
    if hasattr(m, "SHORT_GEOM"):
        m.SHORT_GEOM = str(T / "short_geom.json")
        m.PARKED_WORK = T / "parked"
    return m


old, new = load(LIVE, "job_live"), load(NEW, "job_24")
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


def run(m, tag, n=1, n_ok=1, q=None):
    d = T / tag
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    work = d / "work"
    work.mkdir()
    log = d / "log.txt"
    log.write_text("")
    os.environ.update({"FAKE_LOG": str(log), "FIXTURE": str(FIX), "FAKE_OUT": str(d / "out"),
                       "ENGINE_WORK": str(work), "FA_N": str(n), "FA_OK": str(n_ok)})
    Q.clear()
    Q.update(q or {"locked_pct": 100.0, "shots": 1})
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: work
    res = asyncio.run(m.run_dubsync(FIX, FIX, "artest", None, 320, 240, 23, lambda *a: None, bitrate_k=500))
    cap = m.summary_caption("artest", res, 4.0, 1000) if res.ok else ""
    return res, cap, log.read_text().split()


def film(res):
    return open(res.path, "rb").read() if res.ok and res.path and os.path.exists(res.path) else b""


# ---- A. no break ------------------------------------------------------------------------------------------
for tag, kw in (("clean", {}), ("good-film", {"n": 3211, "n_ok": 3131, "q": {"locked_pct": 100.0, "shots": 3211,
                                                                         "replay_s": 3.0, "offset_unconf": 0.81}})):
    ro, co, lo = run(old, "A_old_" + tag, **kw)
    rn, cn, ln = run(new, "A_new_" + tag, **kw)
    check("A[%s]: same steps in the same order as the live bot" % tag, lo == ln, (lo, ln))
    check("A[%s]: same film bytes" % tag, film(ro) == film(rn) and len(film(rn)) > 1000)
    check("A[%s]: the SAME report text" % tag, co == cn and "NOT CLEAN" not in cn, cn[:600])
    so = {k: str(v).replace("A_old_", "A_") for k, v in ro.stats.items()}
    sn = {k: str(v).replace("A_new_", "A_") for k, v in rn.stats.items() if k != "quality_fail"}
    check("A[%s]: same stats (%d values) + quality_fail == []" % (tag, len(sn)),
          so == sn and rn.stats.get("quality_fail") == [], {k: (so.get(k), sn.get(k)) for k in set(so) | set(sn)
                                                             if so.get(k) != sn.get(k)})

# ---- B. the Toxic picture check ---------------------------------------------------------------------------
TOX = {"locked_pct": 100.0, "shots": 4711}
res, cap, log = run(new, "B", n=4711, n_ok=3985, q=TOX)
first = cap.splitlines()
check("B: headline says NOT CLEAN: do not publish", "NOT CLEAN: do not publish" in first[0] and "complete" not in first[0], first[0])
check("B: the reason is in the first lines", any("only 84.6% of 4711 shots show what the Somali copy shows (726 are wrong or unproven)" in x
                                                 for x in first[2:5]), first[:6])
check("B: the film is still delivered", res.ok and len(film(res)) > 1000)
ro, co, lo = run(old, "B_old", n=4711, n_ok=3985, q=TOX)
check("B: (control) the live bot heads the same film 'complete'", "dub-sync complete" in co.splitlines()[0], co.splitlines()[0])
check("B: everything below the new first lines is the live report", co.splitlines()[2:] == [x for x in first[2:]
      if "NOT CLEAN" not in x and "only 84.6%" not in x and "Most likely this HD" not in x], (co.splitlines()[2:6], first[2:8]))

# ---- C / D. repeats, unconfirmed --------------------------------------------------------------------------
res, cap, log = run(new, "C", q={"locked_pct": 100.0, "shots": 1, "replay_s": 60.2})
check("C: 60.2 s of repeats -> NOT CLEAN with its line", "NOT CLEAN" in cap.splitlines()[0]
      and "repeats: 60.2 s of footage plays twice" in cap, cap[:500])
res, cap, log = run(new, "D", q={"locked_pct": 100.0, "shots": 1, "offset_unconf": 14.39})
check("D: 14.39 % unconfirmed -> NOT CLEAN with its line", "NOT CLEAN" in cap.splitlines()[0]
      and "placement: 14.4% of the shots could not be confirmed" in cap, cap[:500])


# ---- E / F. thresholds and real films ---------------------------------------------------------------------
def qf(pic, rep, unc, n=1000):
    new._quality_report = lambda title: {"replay_s": rep, "offset_unconf": unc}
    st = {"picture_check": {"ok_pct": pic, "checked": n, "ok": int(round(n * pic / 100.0))}} if pic is not None else {}
    return new._quality_fail(st, "t")


for what, args, want in (("picture 94.5 % = clean", (94.5, 0.0, 0.0), 0), ("picture 94.4 % = not clean", (94.4, 0.0, 0.0), 1),
                         ("repeats 10.0 s = clean", (99.0, 10.0, 0.0), 0), ("repeats 10.1 s = not clean", (99.0, 10.1, 0.0), 1),
                         ("unconfirmed 5.0 % = clean", (99.0, 0.0, 5.0), 0), ("unconfirmed 5.1 % = not clean", (99.0, 0.0, 5.1), 1),
                         ("no picture check, clean numbers = clean", (None, 0.0, 0.0), 0)):
    check("E: " + what, len(qf(*args)) == want, qf(*args))
for name, args, want in (("Toxic 2026", (84.6, 60.2, 14.39), 3), ("W.M.R. Saguni", (93.5, 22.6, 6.9), 3),
                         ("Achcham HEVC 09-27", (None, 51.5, 7.8), 2), ("Tyson", (97.5, 3.0, 0.81), 0),
                         ("Srinivasa Kalyanam", (95.3, 5.5, 1.36), 0), ("Highway", (96.2, 0.5, 2.94), 0),
                         ("Sardar trailer", (95.2, 0.0, 0.0), 0), ("Half Girlfriend", (99.3, 0.0, 0.19), 0)):
    check("F: %s -> %s" % (name, "NOT CLEAN (%d rules)" % want if want else "clean"), len(qf(*args)) == want, qf(*args))

# ---- G. INCOMPLETE and NOT CLEAN --------------------------------------------------------------------------
new._quality_report = lambda title: dict(Q)
res, cap, log = run(new, "G", n=4711, n_ok=3985, q=TOX)
res.stats["contract_missing"] = ["opening: the film's start may be missing -- test"]
cap = new.summary_caption("artest", res, 4.0, 1000)
check("G: headline INCOMPLETE, both blocks in the first lines", "INCOMPLETE" in cap.splitlines()[0]
      and "did not finish" in cap and "NOT CLEAN — do not publish" in cap, cap[:700])

# ---- H. never raises --------------------------------------------------------------------------------------
def boom(title):
    raise RuntimeError("x")


new._quality_report = boom
try:
    r1 = new._quality_fail({"picture_check": {"ok_pct": "x"}}, "t")
    r2 = new._quality_fail({}, "t")
    r3 = new._quality_fail({"picture_check": None}, "t")
    check("H: broken input -> [] and no exception", r1 == [] and r2 == [] and r3 == [], (r1, r2, r3))
except Exception as exc:
    check("H: broken input -> [] and no exception", False, exc)

# ---- I. bot.py: a changed zoom window moves the title's analyses aside --------------------------------------
RUN = r"""
import json, os, sys
from pathlib import Path
d, t = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, d); os.chdir(d)
import bot, dubsync_job
bot.HD_WINDOWS = str(t / "hd_windows.json")
dubsync_job.PARKED_WORK = t / "parked"
work = t / "workroot" / "abc123abc123"
dubsync_job._work_dir_for = lambda hd, dub: work
W, W2 = [0.775, 0.8112, 0.0, -0.08], [0.7713, 0.7977, -0.0006, -0.0964]
out = []
def fresh():
    work.mkdir(parents=True, exist_ok=True); (work / "embeds.npz").write_text("old framing")
def state():
    try: reg = json.load(open(bot.HD_WINDOWS))
    except Exception: reg = {}
    return [(reg.get("t1") or {}).get("window"), (work / "embeds.npz").exists(),
            len(list((t / "parked").glob("*"))) if (t / "parked").exists() else 0]
fresh(); out.append(("none->none", bot._sync_hd_window("t1", None, "h", "d"), state()))
out.append(("none->W", bot._sync_hd_window("t1", W, "h", "d"), state()))
fresh(); out.append(("W->W", bot._sync_hd_window("t1", W, "h", "d"), state()))
out.append(("W->W2", bot._sync_hd_window("t1", W2, "h", "d"), state()))
fresh(); out.append(("W2->none", bot._sync_hd_window("t1", None, "h", "d"), state()))
dubsync_job._work_dir_for = lambda hd, dub: (_ for _ in ()).throw(RuntimeError("x"))
out.append(("park fails", bot._sync_hd_window("t1", W, "h", "d"), state()))
print("RESULT " + json.dumps(out))
"""
(T / "runner_i.py").write_text(RUN)
(T / "it").mkdir()
pr = subprocess.run([sys.executable, str(T / "runner_i.py"), NEW, str(T / "it")], capture_output=True, text=True)
line = [x for x in pr.stdout.splitlines() if x.startswith("RESULT ")]
import json as _json
got = {a: (b, c) for a, b, c in _json.loads(line[-1][7:])} if line else {}
check("I: the runner ran", bool(got), (pr.stderr or pr.stdout)[-600:])
if got:
    W, W2 = [0.775, 0.8112, 0.0, -0.08], [0.7713, 0.7977, -0.0006, -0.0964]
    check("I: no window before, none now -> nothing moved, the analysis kept",
          got["none->none"] == ([], [None, True, 0]), got["none->none"])
    check("I: a NEW window -> the old analysis moved aside (not deleted), the window saved",
          got["none->W"][0] == ["abc123abc123"] and got["none->W"][1] == [W, False, 1], got["none->W"])
    check("I: the SAME window again -> nothing moved, the analysis kept",
          got["W->W"] == ([], [W, True, 1]), got["W->W"])
    check("I: a DIFFERENT window -> moved aside again", got["W->W2"][0] == ["abc123abc123"] and got["W->W2"][1][0] == W2
          and got["W->W2"][1][1:] == [False, 2], got["W->W2"])
    check("I: the window CLEARED -> moved aside, the entry gone", got["W2->none"][0] == ["abc123abc123"]
          and got["W2->none"][1] == [None, False, 3], got["W2->none"])
    check("I: a failing move never raises; the window is still saved", got["park fails"][0] == []
          and got["park fails"][1][0] == W, got["park fails"])

shutil.rmtree(T, ignore_errors=True)
print("NOTCLEAN24_TESTS ALL PASS" if ok else "NOTCLEAN24_TESTS FAILED")
sys.exit(0 if ok else 1)
