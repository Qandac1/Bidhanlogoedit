"""OPENING GATE in the bot (John 2026-09-28: "never again" -- CBI 5, Bheemaa, Achcham, Raincoat lost
part of the film's start). After the voice restore, tools/opening_restore.py decides the start by
proof: the first proven stretch extrapolated back to the end of the HD intro; dub seconds there are
film unless PROVEN otherwise. Proven film missing at the start is put back (HD picture + dub sound,
after the HD intro); "unsure" only is reported, nothing changed.
  * report: "🎬 opening: put back N s ..." | "⚠️ opening: the film's start is NOT complete -- why"
            | "ℹ️ opening: <report>"
  * contract: a failed or not-run opening check is INCOMPLETE at the top of the report
Additive: needs patch_bot_restorefix (+ its chain). Usage: python3 patch_bot_opening.py <bot dir>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "OPENING_RESTORE" in s:
    raise SystemExit("already patched")
assert "RESTORE_HEAD" in s and "_contract_missing" in s, "needs restorefix chain first"


def rep(t, old, new, what):
    assert t.count(old) == 1, "anchor %s found %d times" % (what, t.count(old))
    return t.replace(old, new)


s = rep(s, '''RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"''',
        '''RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"
OPENING_RESTORE = "/opt/dubsync2/tools/opening_restore.py"''', "constant")
s = rep(s, '''    except Exception as _rhx:
        stats["voice_restore"] = "not run (%s)" % type(_rhx).__name__
''', '''    except Exception as _rhx:
        stats["voice_restore"] = "not run (%s)" % type(_rhx).__name__

    # ---- OPENING GATE + SELF-REPAIR (John 2026-09-28: "never again") -------
    # The film's start is decided by PROOF, never by "nothing matched here": the first proven
    # stretch extrapolated back to the end of the HD intro; dub seconds there are film unless
    # proven otherwise (tools/opening_gate.py). Proven film missing at the start is put back (HD
    # picture + the dub's sound, after the HD intro); "unsure" only -> reported, nothing changed.
    try:
        if _cancelled():
            return DubResult(False, None, "cancelled", stats)
        _og_out = OUT_DIR / f"{title}_opening.mp4"
        _og = await asyncio.create_subprocess_exec(
            DLG_PY, OPENING_RESTORE, title, str(out), str(_og_out),
            f"{int(bitrate_k)}k" if bitrate_k else "2000k",
            "%.3f" % float(stats.get("hd_intro_s", 0.0) or 0.0),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        if register:
            register(_og)
        _ogt = (await asyncio.wait_for(_og.communicate(), timeout=3600))[0].decode("utf-8", "replace")
        await _og.wait()
        _ol = [x.strip() for x in _ogt.splitlines() if x.strip()]
        _of = [x for x in _ol if x.startswith("OPENING_RESTORE")]
        _ogg = [x for x in _ol if x.startswith("OPENING_GATE")]
        if _ogg:
            stats["opening_gate"] = _ogg[-1][:160]
        if _of and _of[-1].startswith("OPENING_RESTORE DONE") and _og_out.exists() \
                and _og_out.stat().st_size > 0:
            out.unlink(missing_ok=True)
            _og_out.rename(out)
            stats["opening_restored_s"] = float(_of[-1].split()[-1])
        elif _of and _of[-1].startswith("OPENING_RESTORE REPORT"):
            stats["opening_report"] = _of[-1][len("OPENING_RESTORE REPORT"):].strip()[:200]
        elif _of and _of[-1].startswith("OPENING_RESTORE NOT NEEDED"):
            pass
        else:
            stats["opening_restore"] = (_of[-1] if _of else "no result: " + (_ol[-1] if _ol else "no output"))[:200]
            _og_out.unlink(missing_ok=True)
    except Exception as _ogx:
        stats["opening_restore"] = "not run (%s)" % type(_ogx).__name__
''', "step")
s = rep(s, '''        _pc = st.get("picture_check") or {}
        if _pc.get("checked"):''', '''        if st.get("opening_restored_s"):
            lines.append(f"🎬 opening: put back {st['opening_restored_s']:.0f}s of the film's start "
                         "(proven by its frames / voice)")
        elif st.get("opening_restore"):
            lines.append("⚠️ opening: the film's start is NOT complete -- " + str(st["opening_restore"])[:140])
        elif st.get("opening_report"):
            lines.append("ℹ️ opening: start material not proven film, left out: dub " + str(st["opening_report"])[:120])
        _pc = st.get("picture_check") or {}
        if _pc.get("checked"):''', "report")
s = rep(s, '''        miss.append("opening voice: the film's opening Somali voice is not in the film -- "
                    + str(st.get("voice_restore") or "the repair did not run")[:120])''',
        '''        miss.append("opening voice: the film's opening Somali voice is not in the film -- "
                    + str(st.get("voice_restore") or "the repair did not run")[:120])
    if st.get("opening_restore"):
        miss.append("opening: the film's start may be missing -- " + str(st["opening_restore"])[:120])''',
        "contract")
open(J, "w", encoding="utf-8", newline="\n").write(s)
print("patched", J)
