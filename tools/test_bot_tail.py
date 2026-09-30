"""bot16 report lines: the ending put back is named; a failed ending is a warning; an end-credits SKIP is shown
(before, a skip printed nothing). Calls the real summary_caption. Usage: python3 test_bot_tail.py <bot dir>"""
import sys

sys.path.insert(0, sys.argv[1])
import dubsync_job as j  # noqa: E402

j._quality_report = lambda title: {"replay_s": 0.0}
cases = [
    ({"gate": "passed", "tail_restored_s": 15.5, "tail_note": "the film's last scene goes on with its Somali voice for 16 s"},
     "🎬 ending: the film's last scene goes on with its Somali voice for 16 s", "ending put back"),
    ({"gate": "passed", "tail_restore": "TAIL_RESTORE FAILED auto-align"},
     "⚠️ ending: the last scene's Somali voice could not be put back", "ending failed"),
    ({"gate": "passed", "credits": "SKIP: only 1.0s of credits after the last spoken scene"},
     "⚠️ end credits not added — only 1.0s of credits after the last spoken scene", "credits skip shown"),
    ({"gate": "passed", "credits_s": 206.0, "credits": "appended 206.0s"},
     "🎬 end credits kept: 3:26 of the film's own credits", "credits kept (unchanged)"),
]
fails = 0
for st, want, what in cases:
    cap = j.summary_caption("t", j.DubResult(ok=True, path=None, message="", stats=st), 3600, 1e9)
    ok = want in cap
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        print("   ", [ln for ln in cap.splitlines() if "ending" in ln or "credits" in ln])
none = j.summary_caption("t", j.DubResult(ok=True, path=None, message="", stats={"gate": "passed"}), 3600, 1e9)
ok = "ending" not in none
fails += not ok
print(("PASS " if ok else "FAIL ") + "no ending line when the step did not run")
print("TAIL_TESTS", "ALL PASS" if not fails else "%d FAILED" % fails)
