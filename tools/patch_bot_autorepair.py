"""The bot FIXES the wrong clips its cut check proves, instead of only reporting them (John
2026-09-28: "you told me the bot fixes its own problems, not only reports"). Half Girlfriend
1:38:47: the cut gate said "DEFECT -- the film carried straight on here", the bot delivered it
anyway. Now, after the sound + dialogue steps and BEFORE the cut gate / picture check (so they
judge the repaired film), tools/auto_repair.py re-places each such shot at the carry-on place --
only when the shot's own frames prove it (the montage at 1:31:49 is correctly left) -- and
splices it in (sound untouched). The report says what was repaired ("self-repaired") or why the
step could not run. Additive; fail-open: a failure never blocks the delivery, it is reported.
Needs patch_bot_contract (the self-repaired lines).
Usage: python3 patch_bot_autorepair.py <dir with dubsync_job.py>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "AUTO_REPAIR" in s:
    raise SystemExit("already patched")
assert "_contract_missing" in s, "needs patch_bot_contract first"


def rep(s, old, new, what):
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    return s.replace(old, new)


s = rep(s, '''RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"''', '''RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"
AUTO_REPAIR = "/opt/dubsync2/tools/auto_repair.py"''', "constant")
s = rep(s, '''    # ---- GATE: jumps the dub did NOT make (skipped footage) ----------------''', '''    # ---- SELF-REPAIR: wrong clips the cut check proves (John 2026-09-28) -----
    # "the film carried straight on here": the shot is re-placed at the carry-on place only when
    # its own frames prove it (tools/auto_repair.py), spliced in, the sound untouched -- before
    # the gates below, so they judge the repaired film.
    try:
        if _cancelled():
            return DubResult(False, None, "cancelled", stats)
        _ar_out = OUT_DIR / f"{title}_repaired.mp4"
        _ar = await asyncio.create_subprocess_exec(
            DLG_PY, AUTO_REPAIR, title, str(out), str(_ar_out),
            "%.3f" % float(stats.get("hd_intro_s", 0.0) or 0.0),
            "--bitrate", f"{int(bitrate_k)}k" if bitrate_k else "2000k",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        if register:
            register(_ar)
        _art = (await asyncio.wait_for(_ar.communicate(), timeout=3600))[0].decode("utf-8", "replace")
        await _ar.wait()
        _arl = [x.strip() for x in _art.splitlines() if x.strip()]
        _fin = [x for x in _arl if x.startswith("AUTO_REPAIR")]
        if _fin and _fin[-1].startswith("AUTO_REPAIR DONE") and _ar_out.exists() \\
                and _ar_out.stat().st_size > 0:
            out.unlink(missing_ok=True)
            _ar_out.rename(out)
            for _x in _arl:
                if _x.startswith("defect at film"):
                    _t = float(_x.split()[3])
                    _idx = _x.split("dub#")[1].split()[0] if "dub#" in _x else ""
                    if any(y.startswith("PROVEN dub#%s:" % _idx) for y in _arl):
                        stats.setdefault("contract_healed", []).append(
                            "wrong clip at %d:%02d:%02d re-placed (its frames proved it)"
                            % (_t // 3600, _t % 3600 // 60, _t % 60))
        elif _fin and "FAILED" in _fin[-1]:
            stats["auto_repair"] = _fin[-1][:200]
            _ar_out.unlink(missing_ok=True)
    except Exception as _arx:
        stats["auto_repair"] = "not run (%s)" % type(_arx).__name__

    # ---- GATE: jumps the dub did NOT make (skipped footage) ----------------''', "step")
s = rep(s, '''    for _h in (st.get("contract_healed") or [])[:4]:
        lines.append("🩹 self-repaired: " + _h)''', '''    for _h in (st.get("contract_healed") or [])[:6]:
        lines.append("🩹 self-repaired: " + _h)
    if st.get("auto_repair"):
        lines.append("⚠️ wrong-clip self-repair: " + str(st["auto_repair"])[:160])''', "caption")
open(J, "w", encoding="utf-8").write(s)
print("patched", J)
