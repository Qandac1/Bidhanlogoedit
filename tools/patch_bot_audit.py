"""Bot: the picture check in every dub-sync report (John 2026-09-27: "the bot works like
security -- see what it's doing"). After the cut gate, run /opt/dubsync2/tools/frame_audit.py
on the FINAL placement (work/provenance.json, rewritten after the consensus lock): every shot
vs the dub's own frames. The report then says either
   ✅ picture check: all N shots match the dub
or ⚠️ picture check: M of N shots to look at, with the output times of each spot,
and frame_audit.json stays in the work dir. Read-only, fail-open (never blocks a delivery).
Usage: python3 patch_bot_audit.py <dir with dubsync_job.py>"""
import os
import sys

p = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(p, encoding="utf-8").read()
if "FRAME_AUDIT" in s:
    raise SystemExit("already patched")


def rep(old, new, what):
    global s
    assert s.count(old) == 1, "anchor not found exactly once: " + what
    s = s.replace(old, new)


rep('''APPEND_CREDITS = "/opt/dubsync2/append_credits.py"''',
    '''APPEND_CREDITS = "/opt/dubsync2/append_credits.py"
FRAME_AUDIT = "/opt/dubsync2/tools/frame_audit.py"


def _parse_frame_audit(text: str) -> dict:
    """frame_audit.py output -> {"verdict", "checked", "ok", "wrong", "no_hd", "spots": [...]}."""
    import re as _re
    out = {"spots": []}
    for ln in text.splitlines():
        s = ln.strip()
        m = _re.match(r"\\S+: (\\d+) shots with HD checked", s)
        if m:
            out["checked"] = int(m.group(1))
        m = _re.match(r"ok (\\d+) \\(([0-9.]+)%\\) \\| wrong clip \\(moved\\) (\\d+) \\| HD the dub lacks "
                      r"\\(no_hd\\) (\\d+)", s)
        if m:
            out["ok"], out["ok_pct"] = int(m.group(1)), float(m.group(2))
            out["wrong"], out["no_hd"] = int(m.group(3)), int(m.group(4))
        m = _re.match(r"SPOT dub \\S+ \\(out (\\S+)\\): (\\d+) shot\\(s\\).*?\\b(moved|no_hd)\\b", s)
        if m:
            out["spots"].append((m.group(1), int(m.group(2)), m.group(3)))
        if s.startswith("FRAME_AUDIT"):
            out["verdict"] = "green" if s.endswith("GREEN") else "red"
    return out''', "1 constants + parser")

rep('''        for _ln in _ct.splitlines():
            if _ln.startswith("UNJUSTIFIED CUTS"):
                stats["cut_gate"] = _ln.strip()
    except Exception as _cexc:
        stats["cut_gate"] = "not run (%s)" % type(_cexc).__name__
''', '''        for _ln in _ct.splitlines():
            if _ln.startswith("UNJUSTIFIED CUTS"):
                stats["cut_gate"] = _ln.strip()
    except Exception as _cexc:
        stats["cut_gate"] = "not run (%s)" % type(_cexc).__name__

    # ---- PICTURE CHECK: every shot vs the dub's own frames (John: "like security") ----
    # Read-only and fail-open: it reports, it never blocks a delivery.
    try:
        _fa = await asyncio.create_subprocess_exec(
            DLG_PY, FRAME_AUDIT, title,
            "--intro", "%.3f" % float(stats.get("hd_intro_s", 0.0) or 0.0),
            "--json", str(Path(_work_dir_for(hd, dub)) / "frame_audit.json"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        _fat = (await asyncio.wait_for(_fa.communicate(), timeout=1800))[0].decode("utf-8", "replace")
        await _fa.wait()
        _pa = _parse_frame_audit(_fat)
        if _pa.get("verdict"):
            stats["picture_check"] = _pa
    except Exception as _faexc:
        stats["picture_check"] = {"error": type(_faexc).__name__}
''', "2 run after the cut gate")

rep('''        if st.get("cut_gate"):
            _cg = st["cut_gate"]
            lines.append(("✅ cut gate: " + _cg) if _cg.startswith("UNJUSTIFIED CUTS: 0")
                         else ("⚠️ cut gate: " + _cg + " — jumps the dub did NOT make"))
''', '''        if st.get("cut_gate"):
            _cg = st["cut_gate"]
            lines.append(("✅ cut gate: " + _cg) if _cg.startswith("UNJUSTIFIED CUTS: 0")
                         else ("⚠️ cut gate: " + _cg + " — jumps the dub did NOT make"))
        _pc = st.get("picture_check") or {}
        if _pc.get("checked"):
            _bad = int(_pc.get("wrong", 0)) + int(_pc.get("no_hd", 0))
            if _pc.get("verdict") == "green":
                lines.append(f"✅ picture check: all {_pc['checked']} shots match the dub")
            else:
                lines.append(f"⚠️ picture check: {_pc.get('ok_pct', 0):.1f}% of {_pc['checked']} shots "
                             f"match the dub -- {_bad} to look at:")
                for _out, _n, _what in (_pc.get("spots") or [])[:8]:
                    lines.append(f"   · {_out} -- {_n} shot{'s' if _n != 1 else ''}, "
                                 + ("wrong clip" if _what == "moved" else "picture the HD lacks"))
                if len(_pc.get("spots") or []) > 8:
                    lines.append(f"   · +{len(_pc['spots']) - 8} more (frame_audit.json)")
        elif _pc.get("error"):
            lines.append(f"⚠️ picture check not run ({_pc['error']})")
''', "3 caption")

open(p, "w", encoding="utf-8").write(s)
print("patched", p)
