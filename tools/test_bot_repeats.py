"""bot15 report line: "repeated footage" counts only repeats WE added; the Somali copy's own repeats are named,
not counted as a problem. Calls the real summary_caption with fixed quality numbers.
Usage: python3 test_bot_repeats.py <patched bot dir>   prints REPEAT_TESTS ALL PASS"""
import sys

sys.path.insert(0, sys.argv[1])
import dubsync_job as j  # noqa: E402

cases = [
    ({"replay_s": 0.0, "replay_dub_s": 0.0, "visible_s": 0.0},
     "repeated footage: **none** (each HD frame used once)", "nothing repeated: the old green line"),
    ({"replay_s": 0.0, "replay_dub_s": 10.3, "visible_s": 0.0, "backward": 4},
     "repeated footage we added: **none** · 10.3s the Somali copy itself shows twice", "only the copy's own repeats"),
    ({"replay_s": 2.7, "replay_worst": 2},
     "⚠️ repeated footage we added: 2.7s (worst 2x)", "our repeats, no fingerprints (old film)"),
    ({"replay_s": 3.1, "replay_worst": 2, "replay_dub_s": 10.3},
     "⚠️ repeated footage we added: 3.1s (worst 2x) · 10.3s the Somali copy itself shows twice", "both"),
]
fails = 0
for q, want, what in cases:
    j._quality_report = lambda title, q=q: dict(q)
    res = j.DubResult(ok=True, path=None, message="", stats={"gate": "passed"})
    cap = j.summary_caption("t", res, 3600, 1e9)
    ok = want in cap
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        print("   caption lines:", [ln for ln in cap.splitlines() if "repeat" in ln])
print("REPEAT_TESTS", "ALL PASS" if not fails else "%d FAILED" % fails)
