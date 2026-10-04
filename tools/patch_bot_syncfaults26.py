"""bot26: SYNC FAULTS in the report -- stretches where the picture runs off the Somali sound are named with their
film times, and a film with 20 s or more of them is headed NOT CLEAN.

John 2026-10-04: "I want honest and truth". Two kinds of stretch were sitting in the bot's own records and no line
of the report read them:
  * LAG RUNS -- the picture check's "moved" shots that come several in a row with ONE offset: Highway (09-29,
    "picture check 96.2 %", headed complete) had dub#1083-1092 listed -0.75/-1.0 s -- a minute with the picture
    ahead of the sound;
  * PINNED RUNS -- many shots in a row at the speed cap: Mannar 1:10:19-1:11:29, the copy's INTERVAL card the HD
    lacks, the picture 2-8 s off until it has caught up.
tools/sync_faults.py (engine repo; stdlib, no video, < 1 s) reads both from frame_audit.json + provenance.json.
Measured on the 34 films' records on the server (sync_survey.py): 23 have none; Kondal 19 s; ten have 35-285 s.

After the picture check the bot runs it and keeps the result only when there IS a fault (a clean film: no new
stat, the same report). The report lists every stretch ("⚠️ lips: 1:11:46-1:12:47 ..."); `_quality_fail` adds a
"lips:" reason at >= SYNC_FAULT_MAX_S (20 s) -> the NOT CLEAN headline of bot24.
Usage: python patch_bot_syncfaults26.py <bot dir>     (patches <bot dir>/dubsync_job.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "dubsync_job.py"
s = P.read_text()
if "SYNC_FAULT_MAX_S" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''def _quality_fail(st: dict, title: str) -> list:
    """The measured rules a delivery breaks (plain lines for the top of the report); [] = clean. Never raises."""
''', '''# bot26 (John 2026-10-04: "honest and truth"): stretches where the picture runs off the Somali sound, read from
# the bot's own records by tools/sync_faults.py -- the picture check's "moved" shots in a row with ONE offset
# (Highway: a minute 0.9 s off, headed complete), shots in a row at the speed cap (Mannar: the copy's INTERVAL
# card, the picture 2-8 s off for 70 s). 34 films' records: 23 have none, Kondal 19 s, ten have 35-285 s.
SYNC_FAULTS = "/opt/dubsync2/tools/sync_faults.py"
SYNC_FAULT_MAX_S = 20.0      # seconds of film with the picture off the sound: at or above this = NOT CLEAN


def _sync_fault_lines(sf: dict, limit: int = 6) -> list:
    """One plain report line per stretch where the picture runs off the sound (film times); [] = none.
    Never raises."""
    out = []
    try:
        rows = [("lag", x) for x in (sf.get("lag") or [])] + [("pin", x) for x in (sf.get("pinned") or [])]
        rows.sort(key=lambda kx: float(kx[1].get("t0", 0.0)))
        for kind, x in rows:
            d = float(x.get("t1", 0.0)) - float(x.get("t0", 0.0))
            span = "%s-%s (%.0f s)" % (x.get("out0", "?"), x.get("out1", "?"), d)
            if kind == "lag":
                out.append("⚠️ lips: %s -- the picture is %.1f s off the sound (%d shots in a row say so)"
                           % (span, abs(float(x.get("off_s", 0.0))), int(x.get("shots", 0))))
            else:
                more = x.get("cap") != "fast"
                out.append("⚠️ lips: %s -- the Somali copy holds %.1f s %s than the HD here%s; the picture is "
                           "off the sound until it has caught up"
                           % (span, abs(float(x.get("absorbed_s", 0.0))), "more" if more else "less",
                              " (an INTERVAL card or a freeze?)" if more else ""))
        if len(out) > limit:
            out = out[:limit] + ["   · +%d more stretch(es) (sync_faults.json)" % (len(out) - limit)]
    except Exception:
        return []
    return out


def _quality_fail(st: dict, title: str) -> list:
    """The measured rules a delivery breaks (plain lines for the top of the report); [] = clean. Never raises."""
''', "constants + report lines")

rep('''            bad.append("placement: %.1f%% of the shots could not be confirmed by their picture"
                       % float(q["offset_unconf"]))
    except Exception:
        pass
    return bad
''', '''            bad.append("placement: %.1f%% of the shots could not be confirmed by their picture"
                       % float(q["offset_unconf"]))
    except Exception:
        pass
    try:
        _sf = st.get("sync_faults") or {}
        if float(_sf.get("total_s") or 0.0) >= SYNC_FAULT_MAX_S:
            _all = list(_sf.get("lag") or []) + list(_sf.get("pinned") or [])
            _first = min(_all, key=lambda x: float(x.get("t0", 0.0)))
            bad.append("lips: the picture runs off the Somali sound for %.0f s in %d stretch(es) -- the first at %s"
                       % (float(_sf["total_s"]), len(_all), _first.get("out0", "?")))
    except Exception:
        pass
    return bad
''', "the NOT CLEAN rule")

rep('''        _pa = _parse_frame_audit(_fat)
        if _pa.get("verdict"):
            stats["picture_check"] = _pa
    except Exception as _faexc:
        stats["picture_check"] = {"error": type(_faexc).__name__}
''', '''        _pa = _parse_frame_audit(_fat)
        if _pa.get("verdict"):
            stats["picture_check"] = _pa
    except Exception as _faexc:
        stats["picture_check"] = {"error": type(_faexc).__name__}

    # ---- SYNC FAULTS (bot26): stretches where the picture runs off the sound, read from the records above
    # (frame_audit.json + provenance.json; no video, under a second). Fail-open; kept only when there IS one.
    try:
        _sfp = _post_work / "sync_faults.json"
        _sfr = await asyncio.create_subprocess_exec(
            DLG_PY, SYNC_FAULTS, str(_post_work),
            "--intro", "%.3f" % float(stats.get("hd_intro_s", 0.0) or 0.0), "--json", str(_sfp),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        await asyncio.wait_for(_sfr.communicate(), timeout=120)
        _sfd = json.loads(_sfp.read_text())
        if isinstance(_sfd, dict) and (_sfd.get("lag") or _sfd.get("pinned")):
            stats["sync_faults"] = _sfd
    except Exception:
        pass
''', "run sync_faults after the picture check")

rep('''        lines.append("   Most likely this HD is not the version the Somali copy was made from, or the copy is "
                     "reframed/zoomed. Watch the 🔁 spots below; tell Claude before posting.")
''', '''        if all(str(_x).startswith("lips:") for _x in _bad):
            lines.append("   Watch the ⚠️ lips spots below (film times) before posting; tell Claude.")
        else:
            lines.append("   Most likely this HD is not the version the Somali copy was made from, or the copy is "
                         "reframed/zoomed. Watch the 🔁 spots below; tell Claude before posting.")
''', "the hint under NOT CLEAN")

rep('''        elif _pc.get("error"):
            lines.append(f"⚠️ picture check not run ({_pc['error']})")
''', '''        elif _pc.get("error"):
            lines.append(f"⚠️ picture check not run ({_pc['error']})")
        lines.extend(_sync_fault_lines(st.get("sync_faults") or {}))
''', "list the stretches in the report")

P.write_text(s)
print("patched %s" % P)
