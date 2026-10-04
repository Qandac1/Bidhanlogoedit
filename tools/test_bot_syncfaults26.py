"""bot26 = live bot + SYNC FAULTS in the report. Run inside the bot container:
    python3 test_bot_syncfaults26.py <live bot dir copy> <bot26 dir copy> [--real]
  A. NO BREAK: a film without a sync fault -> same steps (+ the one new read-only step), same film bytes, the SAME
     report text and the same stats as the live bot.
  B. Highway's numbers (2 lag runs, 103 s) -> headline NOT CLEAN, the "lips:" reason in the first lines, both
     stretches listed with their film times, the film still delivered. (control) the live bot: "complete".
  C. Mannar's numbers (2 lag runs + 2 pinned runs, 106 s) -> NOT CLEAN; the pinned line names the INTERVAL card.
  D. Kondal's numbers (19 s) -> headline unchanged (complete), the stretch still listed.
  E. The bar: 19.9 s clean, 20.0 s not clean.
  F. Picture AND lips reasons together -> both in the first lines, the old hint kept.
  G. The tool fails / writes garbage / is missing -> no stat, the delivery and the report as the live bot's.
  H. _quality_fail / _sync_fault_lines never raise on broken input; more than 6 stretches -> 6 + "+N more".
  --real: the REAL tools/sync_faults.py on real work dirs -> Highway NOT CLEAN (103 s), Tyson clean.
Prints SYNCFAULTS26_TESTS ALL PASS."""
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REAL = "--real" in sys.argv
if REAL:
    sys.argv.remove("--real")
LIVE, NEW = sys.argv[1], sys.argv[2]
T = Path(tempfile.mkdtemp(prefix="sf26_"))
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
    "sync_faults": r'''
import json, os, sys
open(os.environ["FAKE_LOG"], "a").write("sync_faults\n")
if os.environ.get("SF_MODE") == "fail":
    sys.exit(1)
out = sys.argv[sys.argv.index("--json") + 1]
if os.environ.get("SF_MODE") == "garbage":
    open(out, "w").write("not json")
else:
    open(out, "w").write(os.environ.get("SF_JSON") or json.dumps(
        {"lag": [], "lag_s": 0.0, "pinned": [], "pinned_s": 0.0, "total_s": 0.0}))
print("SYNC_FAULTS fake")
''',
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
              "append_credits", "tail_restore", "space_guard", "sync_faults"):
        if hasattr(m, k.upper()) or k == "space_guard":
            setattr(m, k.upper(), str(T / (k + ".py")))
    m._quality_report = lambda title: dict(Q)
    if hasattr(m, "SHORT_GEOM"):
        m.SHORT_GEOM = str(T / "short_geom.json")
        m.PARKED_WORK = T / "parked"
    if hasattr(m, "HD_WINDOWS_FILE"):
        m.HD_WINDOWS_FILE = str(T / "hd_windows.json")
    return m


old, new = load(LIVE, "job_live"), load(NEW, "job_26")
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


def run(m, tag, n=1, n_ok=1, q=None, sf=None, mode=""):
    d = T / tag
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    work = d / "work"
    work.mkdir()
    log = d / "log.txt"
    log.write_text("")
    os.environ.update({"FAKE_LOG": str(log), "FIXTURE": str(FIX), "FAKE_OUT": str(d / "out"),
                       "ENGINE_WORK": str(work), "FA_N": str(n), "FA_OK": str(n_ok),
                       "SF_JSON": json.dumps(sf) if sf else "", "SF_MODE": mode})
    Q.clear()
    Q.update(q or {"locked_pct": 100.0, "shots": 1})
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: work
    res = asyncio.run(m.run_dubsync(FIX, FIX, "artest", None, 320, 240, 23, lambda *a: None, bitrate_k=500))
    cap = m.summary_caption("artest", res, 4.0, 1000) if res.ok else ""
    return res, cap, log.read_text().split()


def film(res):
    return open(res.path, "rb").read() if res.ok and res.path and os.path.exists(res.path) else b""


def lag(t0, t1, shots, off, o0, o1):
    return {"t0": t0, "t1": t1, "shots": shots, "off_s": off, "dub0": 1, "dub1": 2, "shown": 0.3, "best": 0.8,
            "out0": o0, "out1": o1}


def pin(t0, t1, shots, ab, o0, o1, cap="slow"):
    return {"t0": t0, "t1": t1, "shots": shots, "absorbed_s": ab, "cap": cap, "dub0": 1, "dub1": 2, "out0": o0, "out1": o1}


def sfj(lags, pins):
    tot, end = 0.0, None
    for a, b in sorted((x["t0"], x["t1"]) for x in lags + pins):
        if end is None or a > end:
            tot += b - a
            end = b
        elif b > end:
            tot += b - end
            end = b
    return {"lag": lags, "lag_s": round(sum(x["t1"] - x["t0"] for x in lags), 1), "pinned": pins,
            "pinned_s": round(sum(x["t1"] - x["t0"] for x in pins), 1), "total_s": round(tot, 1)}


HIGHWAY = sfj([lag(761.9, 805.1, 3, -0.75, "0:12:59", "0:13:42"), lag(4289.4, 4349.5, 6, -0.88, "1:11:46", "1:12:47")], [])
MANNAR = sfj([lag(4275.2, 4281.8, 2, -1.75, "1:11:15", "1:11:21"), lag(5174.0, 5180.0, 3, -2.38, "1:26:14", "1:26:20")],
             [pin(4145.9, 4175.6, 6, -3.5, "1:09:05", "1:09:35"), pin(4219.7, 4289.4, 25, -5.7, "1:10:19", "1:11:29")])
KONDAL = sfj([lag(1486.0, 1505.0, 2, 0.75, "0:24:46", "0:25:05")], [])

# ---- A. no break ------------------------------------------------------------------------------------------
for tag, kw in (("clean", {}), ("good-film", {"n": 3211, "n_ok": 3131, "q": {"locked_pct": 100.0, "shots": 3211,
                                                                         "replay_s": 3.0, "offset_unconf": 0.81}})):
    ro, co, lo = run(old, "A_old_" + tag, **kw)
    rn, cn, ln = run(new, "A_new_" + tag, **kw)
    check("A[%s]: same steps as the live bot + the one new read-only step, right after the picture check" % tag,
          lo == [x for x in ln if x != "sync_faults"] and ln.count("sync_faults") == 1
          and ln.index("sync_faults") == ln.index("frame_audit") + 1, (lo, ln))
    check("A[%s]: same film bytes" % tag, film(ro) == film(rn) and len(film(rn)) > 1000)
    check("A[%s]: the SAME report text" % tag, co == cn and "lips: " not in cn, cn[:600])
    so = {k: str(v).replace("A_old_", "A_") for k, v in ro.stats.items()}
    sn = {k: str(v).replace("A_new_", "A_") for k, v in rn.stats.items()}
    check("A[%s]: the same stats (%d values), no sync_faults key" % (tag, len(sn)), so == sn and "sync_faults" not in rn.stats,
          {k: (so.get(k), sn.get(k)) for k in set(so) | set(sn) if so.get(k) != sn.get(k)})

# ---- B. Highway -------------------------------------------------------------------------------------------
HQ = {"locked_pct": 100.0, "shots": 1767, "replay_s": 0.5, "offset_unconf": 2.94}
res, cap, log = run(new, "B", n=1767, n_ok=1700, q=HQ, sf=HIGHWAY)
first = cap.splitlines()
check("B: headline says NOT CLEAN: do not publish", "NOT CLEAN: do not publish" in first[0] and "complete" not in first[0], first[0])
check("B: the reason is in the first lines",
      any("lips: the picture runs off the Somali sound for 103 s in 2 stretch(es) -- the first at 0:12:59" in x for x in first[2:5]), first[:6])
check("B: the hint points at the lips spots (not at 'another version')",
      any("Watch the ⚠️ lips spots below (film times)" in x for x in first[2:6]) and "Most likely this HD" not in cap, first[:7])
check("B: both stretches are listed with their film times",
      "⚠️ lips: 0:12:59-0:13:42 (43 s) -- the picture is 0.8 s off the sound (3 shots in a row say so)" in cap
      and "⚠️ lips: 1:11:46-1:12:47 (60 s) -- the picture is 0.9 s off the sound (6 shots in a row say so)" in cap, cap[-900:])
check("B: the film is still delivered", res.ok and len(film(res)) > 1000)
check("B: the stat is kept", (res.stats.get("sync_faults") or {}).get("total_s") == HIGHWAY["total_s"], res.stats.get("sync_faults"))
ro, co, lo = run(old, "B_old", n=1767, n_ok=1700, q=HQ)
check("B: (control) the live bot heads the same film 'complete'", "dub-sync complete" in co.splitlines()[0], co.splitlines()[0])
check("B: everything else is the live report",
      co.splitlines()[2:] == [x for x in first[2:] if "NOT CLEAN" not in x and not x.startswith("⚠️ lips: ")
                              and "lips: the picture runs off" not in x and "lips spots below" not in x],
      (co.splitlines()[2:6], first[2:8]))

# ---- C. Mannar ----------------------------------------------------------------------------------------------
res, cap, log = run(new, "C", n=3282, n_ok=3200, q={"locked_pct": 100.0, "shots": 3282}, sf=MANNAR)
check("C: lag + pinned runs (%.0f s) -> NOT CLEAN" % MANNAR["total_s"], "NOT CLEAN" in cap.splitlines()[0]
      and "lips: the picture runs off the Somali sound for %.0f s in 4 stretch(es) -- the first at 1:09:05" % MANNAR["total_s"] in cap,
      cap[:600])
check("C: the pinned stretch names what it is",
      "⚠️ lips: 1:10:19-1:11:29 (70 s) -- the Somali copy holds 5.7 s more than the HD here (an INTERVAL card or a "
      "freeze?); the picture is off the sound until it has caught up" in cap, cap[-1200:])
_ll = [x for x in cap.splitlines() if x.startswith("⚠️ lips: ")]
check("C: the four stretches come in film order", [x.split("lips: ")[1][:7] for x in _ll] == ["1:09:05", "1:10:19", "1:11:15", "1:26:14"], _ll)

# ---- D. Kondal: under the bar, still listed -------------------------------------------------------------------
res, cap, log = run(new, "D", n=3384, n_ok=3300, q={"locked_pct": 100.0, "shots": 3384}, sf=KONDAL)
check("D: 19 s -> the headline stays 'complete'", "dub-sync complete" in cap.splitlines()[0], cap.splitlines()[0])
check("D: ... and the stretch is still listed", "⚠️ lips: 0:24:46-0:25:05 (19 s) -- the picture is 0.8 s off the sound" in cap, cap[-700:])

# ---- E. the bar -----------------------------------------------------------------------------------------------
new._quality_report = lambda title: {}
for tot, want in ((19.9, 0), (20.0, 1), (0.0, 0)):
    st = {"sync_faults": {"lag": [lag(100.0, 100.0 + tot, 2, -0.8, "0:01:40", "0:02:00")], "pinned": [], "total_s": tot}}
    check("E: %.1f s -> %s" % (tot, "NOT CLEAN" if want else "clean"), len(new._quality_fail(st, "t")) == want, new._quality_fail(st, "t"))
new._quality_report = lambda title: dict(Q)

# ---- F. picture AND lips ----------------------------------------------------------------------------------------
res, cap, log = run(new, "F", n=4711, n_ok=3985, q={"locked_pct": 100.0, "shots": 4711}, sf=HIGHWAY)
first = cap.splitlines()
check("F: both reasons in the first lines, the old hint kept",
      any("picture: only 84.6%" in x for x in first[2:6]) and any("lips: the picture runs off" in x for x in first[2:6])
      and "Most likely this HD is not the version" in cap and "Watch the ⚠️ lips spots below" not in cap, first[:8])

# ---- G. the tool fails -------------------------------------------------------------------------------------------
ro, co, lo = run(old, "G_old", n=1767, n_ok=1700, q=HQ)
for mode in ("fail", "garbage"):
    rn, cn, ln = run(new, "G_" + mode, n=1767, n_ok=1700, q=HQ, mode=mode)
    check("G[%s]: no stat, the film delivered, the live bot's report" % mode,
          "sync_faults" not in rn.stats and rn.ok and film(rn) == film(ro) and cn == co, cn[:400])
_keep = new.SYNC_FAULTS
new.SYNC_FAULTS = str(T / "no_such_tool.py")
rn, cn, ln = run(new, "G_missing", n=1767, n_ok=1700, q=HQ)
new.SYNC_FAULTS = _keep
check("G[missing tool]: no stat, the film delivered, the live bot's report",
      "sync_faults" not in rn.stats and rn.ok and film(rn) == film(ro) and cn == co, cn[:400])

# ---- H. never raises ---------------------------------------------------------------------------------------------
new._quality_report = lambda title: {}
try:
    r = [new._quality_fail({"sync_faults": x}, "t") for x in (None, "x", {"total_s": "x"}, {"total_s": 99, "lag": None, "pinned": None},
                                                                {"total_s": 99, "lag": [{}], "pinned": []})]
    ll = [new._sync_fault_lines(x) for x in (None, "x", {"lag": "x"}, {"lag": [{}]}, {"pinned": [{"t0": "a"}]})]
    check("H: broken input -> no exception", all(isinstance(x, list) for x in r + ll), (r, ll))
except Exception as exc:
    check("H: broken input -> no exception", False, repr(exc))
many = sfj([lag(100.0 * k, 100.0 * k + 10, 2, -0.8, "0:%02d:00" % k, "0:%02d:10" % k) for k in range(1, 10)], [])
ll = new._sync_fault_lines(many)
check("H: 9 stretches -> 6 lines + '+3 more'", len(ll) == 7 and "+3 more stretch(es)" in ll[-1], ll)
new._quality_report = lambda title: dict(Q)

# ---- --real: the real tool on real work dirs ----------------------------------------------------------------------
if REAL:
    def real(work):
        out = T / ("real_%s.json" % os.path.basename(work))
        pr = subprocess.run([sys.executable, "/opt/dubsync2/tools/sync_faults.py", work, "--intro", "17.5", "--json", str(out)],
                            capture_output=True, text=True)
        return json.loads(out.read_text()), (pr.stdout.strip().splitlines() or ["?"])[-1]

    new._quality_report = lambda title: {}
    hw, line = real("/opt/dubsync2/work/3b222577e00c")
    bad = new._quality_fail({"sync_faults": hw}, "t")
    check("real: Highway's records -> NOT CLEAN, 103 s in 2 stretches", len(bad) == 1 and "103 s in 2 stretch(es)" in bad[0], (line, bad))
    ll = new._sync_fault_lines(hw)
    check("real: Highway's two stretches are listed with their film times", len(ll) == 2 and "1:11:46-1:12:47" in ll[1], ll)
    ty, line = real("/opt/dubsync2/work/2f19f486948f")
    check("real: Tyson's records -> clean, nothing listed", new._quality_fail({"sync_faults": ty}, "t") == []
          and new._sync_fault_lines(ty) == [], (line, ty))

shutil.rmtree(T, ignore_errors=True)
print("SYNCFAULTS26_TESTS ALL PASS" if ok else "SYNCFAULTS26_TESTS FAILED")
sys.exit(0 if ok else 1)
