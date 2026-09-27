"""Proves patch_bot_audit: the parser reads real frame_audit.py output, and summary_caption
shows the picture check (red with spots, and green). Run inside the bot container:
  python3 test_bot_audit.py <staged dir> <frame_audit output .txt>"""
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import dubsync_job as dj  # noqa: E402

txt = open(sys.argv[2]).read()
pa = dj._parse_frame_audit(txt)
print("parsed:", {k: v for k, v in pa.items() if k != "spots"}, "spots:", pa["spots"][:3])
ok = pa.get("verdict") == "red" and pa.get("checked", 0) > 0 and len(pa["spots"]) >= 1

res = dj.DubResult(True, Path("/tmp/x.mp4"), "released", {"gate": "passed", "picture_check": pa,
                                                           "cut_gate": "UNJUSTIFIED CUTS: 0"})
cap = dj.summary_caption("achchamyenbadhumad_bc85dc", res, 7000.0, 1.5e9)
red = [ln for ln in cap.splitlines() if "picture check" in ln or ln.startswith("   · ")]
print("\n".join(red))
ok &= any("⚠️ picture check" in ln for ln in red)

green = dict(pa, verdict="green", wrong=0, no_hd=0, spots=[])
res2 = dj.DubResult(True, Path("/tmp/x.mp4"), "released", {"gate": "passed", "picture_check": green})
cap2 = dj.summary_caption("achchamyenbadhumad_bc85dc", res2, 7000.0, 1.5e9)
g = [ln for ln in cap2.splitlines() if "picture check" in ln]
print("\n".join(g))
ok &= any("✅ picture check: all" in ln for ln in g)
print("BOT_AUDIT_TESTS", "ALL PASS" if ok else "FAILED")
