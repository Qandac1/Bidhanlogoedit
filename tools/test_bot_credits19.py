"""bot19: the credits line when the film already ends on its own end; other credits lines unchanged.
Calls the real summary_caption. Usage: python3 test_bot_credits19.py <bot dir>"""
import sys

sys.path.insert(0, sys.argv[1])
import dubsync_job as j  # noqa: E402

j._quality_report = lambda title: {"replay_s": 0.0}
cases = [
    ({"gate": "passed", "credits": "SKIP: HD continues only 0.9s past the film -- the dub kept its ending"},
     "🎬 end credits kept: the Somali copy runs to the film's own end", "film runs to its own end"),
    ({"gate": "passed", "credits": "SKIP: only 1.0s of credits after the last spoken scene"},
     "⚠️ end credits not added — only 1.0s of credits after the last spoken scene", "a real skip still warns"),
    ({"gate": "passed", "credits_s": 62.0, "credits": "appended 62.0s"},
     "🎬 end credits kept: 1:02 of the film's own credits", "credits appended (unchanged)"),
]
fails = 0
for st, want, what in cases:
    cap = j.summary_caption("t", j.DubResult(ok=True, path=None, message="", stats=st), 3600, 1e9)
    ok = want in cap and not (what == "film runs to its own end" and "not added" in cap)
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what)
print("CREDITS19_TESTS", "ALL PASS" if not fails else "%d FAILED" % fails)
