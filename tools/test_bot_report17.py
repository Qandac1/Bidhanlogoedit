"""bot17 report lines on REAL data (Hebbuli bot16 run, message 61515, work 4c9f768a6a0e).
  1. the spots list: regenerated with the engine's own human_repeat_lines from the run's integrity_report.json
     and checked EQUAL to the 8 lines John got; then _label_own_repeats puts the repeats we added first and
     names the copy's own -- nothing lost, nothing invented; a list that does not match is left as it was.
  2. the stale "film starts at" line is left out when the opening step ran (kept when it did not).
  3. expected length: covered by the patch anchors (opening + tail added after their steps).
Usage: python3 test_bot_report17.py <bot dir> <repeat_split.py under test>   (run with the dubsync2 venv python)"""
import json
import sys

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, "/opt/dubsync2/src")
import dubsync_job as j  # noqa: E402
from dubsync2.integrity import Region, human_repeat_lines  # noqa: E402

W = "/opt/dubsync2/work/4c9f768a6a0e"
j.REPEAT_SPLIT = sys.argv[2]
fails = 0


def check(ok, what, extra=""):
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what + (("  " + extra) if extra and not ok else ""))


GOT = ["🔁 1:04:49 ↔ 1:05:01  (2.1s)  overlap", "🔁 48:44 ↔ 49:03  (1.6s)  overlap",
       "🔁 1:04:45 ↔ 1:04:56  (1.5s)  overlap", "🔁 1:04:41 ↔ 1:04:55  (1.5s)  overlap",
       "🔁 1:04:48 ↔ 1:04:59  (0.9s)  overlap", "🔁 1:04:47 ↔ 1:04:58  (0.9s)  overlap",
       "🔁 1:04:46 ↔ 1:04:57  (0.8s)  overlap", "🔁 48:47 ↔ 49:03  (0.8s)  overlap"]
regions = [Region(**r) for r in json.load(open(W + "/integrity_report.json"))["regions"]]
lines = human_repeat_lines(regions, offset=0.0)
check(lines[:8] == GOT, "regenerated spots == the 8 lines John got", str(lines[:8]))
lab = j._label_own_repeats(lines, W)
check(sorted(x.split(" · ")[0] for x in lab) == sorted(lines), "same spots, none lost or invented")
own = [x for x in lab if "Somali copy shows it twice too" in x]
ours = [x for x in lab if "Somali copy shows it twice too" not in x]
check(lab == ours + own, "the repeats we added come first")
check(any(x.startswith("🔁 1:04:49 ↔ 1:05:01") for x in own), "1:04:49 (dub 65:4x, copy twice, 1.0 b) named own")
check(any(x.startswith("🔁 48:44 ↔ 49:03") for x in own), "48:44 (dub 49:37 = 49:54, 0.9 b) named own")
check(len(ours) >= 1, "a repeat the copy does NOT have stays unlabelled", str(ours))
bad = lines[:3] + ["🔁 9:99 ↔ 9:99  (7.7s)  overlap"]
check(j._label_own_repeats(bad, W) == bad, "a list that does not match the report is left as it was")
print("   own %d, ours %d: %s" % (len(own), len(ours), ours))

j._quality_report = lambda title: {"replay_s": 0.0}
st = {"gate": "passed", "film_start": "1:09", "opening_restored_s": 59.08,
      "opening_note": "the film now starts at 0:38 of the Somali copy"}
cap = j.summary_caption("t", j.DubResult(ok=True, path=None, message="", stats=st), 3600, 1e9)
check("film starts at 1:09" not in cap, "stale film-start line left out after the opening step")
st2 = {"gate": "passed", "film_start": "1:09"}
cap2 = j.summary_caption("t", j.DubResult(ok=True, path=None, message="", stats=st2), 3600, 1e9)
check("✂️ film starts at 1:09 — intro/bumpers cut automatically" in cap2, "film-start line kept when no opening step")
print("REPORT17_TESTS", "ALL PASS" if not fails else "%d FAILED" % fails)
