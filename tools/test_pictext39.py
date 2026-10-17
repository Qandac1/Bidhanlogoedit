"""bot39c inside the bot container:  python3 test_pictext39.py <live dir copy> <bot39b dir copy> <bot39b+c dir copy>
The report a delivery gets, built by summary_caption() from the same stats with the live code and with bot39c:
  1. the Matchbox trailer's real picture numbers (146 checked, 133 ok, 0 wrong, 2 no_hd) -> the line keeps its words and
     gains "0 placed wrong, 2 HD picture the copy does not have, 11 too short / dark to check"; the advice is "No shot is
     placed wrong ..." instead of "another version / zoomed"; NOT CLEAN stays NOT CLEAN
  2. W.M.R. Saguni's real numbers (2689 / 2515 ok / 68 wrong / 17 no_hd) -> the split, and the old advice (shots ARE wrong)
  3. a clean film (97.5 %) and a lips-only NOT CLEAN -> the caption is byte-identical to the live one
  4. dubsync_job.py vs bot39b: 2 lines changed (the picture line), the rest added; compiles
Prints PICTEXT39_TESTS ALL PASS."""
import importlib.util
import os
import py_compile
import subprocess
import sys

LIVE, B, NEW = sys.argv[1], sys.argv[2], sys.argv[3]
fails = 0


def check(ok, what, extra=""):
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what + (("  | " + str(extra)[-700:]) if extra and not ok else ""), flush=True)


def load(d, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, "dubsync_job.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m                     # (dataclasses look their module up while the class is built)
    sys.path.insert(0, d)
    spec.loader.exec_module(m)
    sys.path.remove(d)
    return m


os.chdir(NEW)
live, new = load(LIVE, "dj_live"), load(NEW, "dj_new")


def caption(m, pc, extra=None):
    st = {"picture_check": pc, "audio": "dub dialogue + HD music", "dialogue_gate": "GREEN", "credits": "CREDITS OK",
          "gate": "passed"}
    st.update(extra or {})
    st["quality_fail"] = m._quality_fail(st, "zz_test_title_bot39c")    # as the job does (stats["quality_fail"])
    res = m.DubResult(True, "/nonexistent/x.mp4", "ok", st)
    return m.summary_caption("zz_test_title_bot39c", res, 172.0, 50_000_000)


mb = {"verdict": "red", "checked": 146, "ok": 133, "ok_pct": 91.1, "wrong": 0, "no_hd": 2, "spots": []}
sg = {"verdict": "red", "checked": 2689, "ok": 2515, "ok_pct": 93.5, "wrong": 68, "no_hd": 17, "spots": []}
good = {"verdict": "green", "checked": 2287, "ok": 2242, "ok_pct": 98.0, "wrong": 0, "no_hd": 2, "spots": []}
lips = {"sync_faults": {"total_s": 47.4, "lag": [{"t0": 8301.12, "t1": 8348.52, "shots": 2, "off_s": -0.56,
                                                  "out0": "2:18:31", "out1": "2:19:18"}], "pinned": []}}
a, b = caption(live, mb), caption(new, mb)
old_line = "picture: only 91.1% of 146 shots show what the Somali copy shows (13 are wrong or unproven"
check("NOT CLEAN" in a and "NOT CLEAN" in b and old_line in a and old_line in b
      and "0 placed wrong, 2 HD picture the copy does not have, 11 too short / dark to check" in b
      and "No shot is placed wrong" in b and "Most likely this HD" not in b and "Most likely this HD" in a,
      "1. the Matchbox trailer: still NOT CLEAN, the line gains the split, the advice points at the spots", (a, b))
print("     live : " + [x for x in a.splitlines() if "picture:" in x][0].strip())
print("     new  : " + [x for x in b.splitlines() if "picture:" in x][0].strip())
print("     new  : " + [x for x in b.splitlines() if "No shot is placed wrong" in x][0].strip())
a, b = caption(live, sg), caption(new, sg)
check("68 placed wrong, 17 HD picture the copy does not have, 89 too short / dark to check" in b
      and "Most likely this HD" in b, "2. W.M.R. Saguni: the split (68 placed wrong) and the old advice", b)
a, b = caption(live, good), caption(new, good)
check(a == b and "NOT CLEAN" not in b, "3a. a clean film: the caption is byte-identical")
a, b = caption(live, good, lips), caption(new, good, lips)
check(a == b and "NOT CLEAN" in b, "3b. a lips-only NOT CLEAN: the caption is byte-identical")
d = subprocess.run(["diff", os.path.join(B, "dubsync_job.py"), os.path.join(NEW, "dubsync_job.py")],
                   capture_output=True, text=True).stdout.splitlines()
removed = [x for x in d if x.startswith("< ")]
added = [x for x in d if x.startswith("> ")]
check(len(removed) == 2 and all("wrong or unproven" in x or "_pc.get(\"ok\")" in x for x in removed) and 20 < len(added) < 45,
      "4. dubsync_job.py vs bot39b: %d changed (the picture line), %d added" % (len(removed), len(added)), removed)
try:
    py_compile.compile(os.path.join(NEW, "dubsync_job.py"), doraise=True)
    check(True, "4b. compiles (and imported above)")
except py_compile.PyCompileError as ex:
    check(False, "4b. compiles", ex)
print("PICTEXT39_TESTS ALL PASS" if not fails else "PICTEXT39_TESTS %d FAILED" % fails)
sys.exit(1 if fails else 0)
