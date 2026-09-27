"""summary_caption shows the dialogue gate: restored / green / red + removed stretches."""
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import dubsync_job as dj  # noqa: E402
ok = True
base = {"gate": "passed", "cut_gate": "UNJUSTIFIED CUTS: 0"}
cases = [
    ("restored", dict(base, dialogue_gate="DIALOGUE_AUDIT GREEN", dialogue_pct="100.0%", voice_restored_s=30.7), "restored 31s"),
    ("green+adverts", dict(base, dialogue_gate="DIALOGUE_AUDIT GREEN", dialogue_pct="99.4%",
                           dialogue_lines=["voice dub 1:19:04.14 - 1:19:21.81 (17.7 s): material the HD does not have (advert / promo) -- cut correctly"]), "✅ dialogue: 99.4%"),
    ("red", dict(base, dialogue_gate="DIALOGUE_AUDIT RED", dialogue_pct="98.0%"), "⚠️ dialogue: film voice was cut"),
]
for name, st, want in cases:
    cap = dj.summary_caption("x", dj.DubResult(True, Path("/tmp/x.mp4"), "released", st), 6000.0, 1.5e9)
    got = [l for l in cap.splitlines() if "dialogue" in l or l.startswith("   · dub")]
    r = any(want in l for l in got)
    ok &= r
    print(name, "PASS" if r else "FAIL", "|", " / ".join(got))
print("SELFHEAL_CAPTION_TESTS", "ALL PASS" if ok else "FAILED")
