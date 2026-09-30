"""bot16: the film's END with its Somali voice + credits never silently missing (John 2026-09-30, Hebbuli).
  * after the opening step, before the dialogue gate: tools/tail_restore.py -- the film's last scene the channel
    covered with its own credits box goes on with its Somali voice on the HD's own picture (proven by the voice's
    on/off pattern against the HD's speech on the film line); the delivered file becomes its output.
  * report: "🎬 ending: ..." when it ran; "⚠️ ending: ..." when it failed (the film ends as before, fail-open).
  * report: an end-credits SKIP is shown ("⚠️ end credits not added -- why"); before, a skip printed nothing and
    John found the credits missing himself.
Usage: python3 patch_bot_tail.py <dubsync_job.py>"""
import sys

P = sys.argv[1]
s = open(P, encoding="utf-8").read()
if "TAIL_RESTORE" in s:
    raise SystemExit("already patched")


def rep(old, new, what):
    global s
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


rep('''    # ---- DIALOGUE GATE + SELF-REPAIR (John 2026-09-27) -----------------------
''', '''    # ---- THE END: the film's last scene with its Somali voice (John 2026-09-30) -----
    # A channel can cover the film's last scene with its own credits box while the Somali voice goes on
    # (Hebbuli 1:54:08-1:54:23). That voice is the scene's dialogue when its on/off pattern follows the HD's
    # speech on the film line: the HD's own picture of that scene is appended with the Somali sound
    # (tools/tail_restore.py). Fail-open: anything else and the film ends as before.
    try:
        if _cancelled():
            return DubResult(False, None, "cancelled", stats)
        _tl_out = OUT_DIR / f"{title}_tail.mp4"
        _tl = await asyncio.create_subprocess_exec(
            DLG_PY, TAIL_RESTORE, title, str(out), str(_tl_out),
            f"{int(bitrate_k)}k" if bitrate_k else "2000k",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        if register:
            register(_tl)
        _tlt = (await asyncio.wait_for(_tl.communicate(), timeout=1800))[0].decode("utf-8", "replace")
        await _tl.wait()
        _tll = [x.strip() for x in _tlt.splitlines() if x.strip()]
        _tlf = [x for x in _tll if x.startswith("TAIL_RESTORE")]
        _tln = [x for x in _tll if x.startswith("TAIL_NOTE ")]
        if _tln:
            stats["tail_note"] = _tln[-1][len("TAIL_NOTE "):][:260]
        if _tlf and _tlf[-1].startswith("TAIL_RESTORE DONE") and _tl_out.exists() and _tl_out.stat().st_size > 0:
            out.unlink(missing_ok=True)
            _tl_out.rename(out)
            stats["tail_restored_s"] = float(_tlf[-1].split()[-1])
        elif _tlf and _tlf[-1].startswith("TAIL_RESTORE NOT NEEDED"):
            _tl_out.unlink(missing_ok=True)
        else:
            stats["tail_restore"] = (_tlf[-1] if _tlf else "no result: " + (_tll[-1] if _tll else "no output"))[:200]
            _tl_out.unlink(missing_ok=True)
    except Exception as _tlx:
        stats["tail_restore"] = "not run (%s)" % type(_tlx).__name__

    # ---- DIALOGUE GATE + SELF-REPAIR (John 2026-09-27) -----------------------
''', "tail step before the dialogue gate")

rep('''APPEND_CREDITS = "/opt/dubsync2/append_credits.py"
''', '''APPEND_CREDITS = "/opt/dubsync2/append_credits.py"
TAIL_RESTORE = "/opt/dubsync2/tools/tail_restore.py"
''', "TAIL_RESTORE constant")

rep('''        elif str(st.get("credits", "")).startswith("CREDITS FAILED"):
            lines.append("⚠️ end credits not added — %s" % st["credits"][16:90])''',
'''        elif str(st.get("credits", "")).startswith("CREDITS FAILED"):
            lines.append("⚠️ end credits not added — %s" % st["credits"][16:90])
        elif str(st.get("credits", "")).startswith("SKIP"):
            lines.append("⚠️ end credits not added — %s" % st["credits"][5:150].strip())''', "credits skip line")

rep('''        elif st.get("opening_report"):
            lines.append("ℹ️ opening: start material not proven film, left out: dub " + str(st["opening_report"])[:120])''',
'''        elif st.get("opening_report"):
            lines.append("ℹ️ opening: start material not proven film, left out: dub " + str(st["opening_report"])[:120])
        if st.get("tail_restored_s"):
            lines.append("🎬 ending: " + str(st.get("tail_note") or
                                             "the film's last scene put back with its Somali voice (%.0fs)"
                                             % st["tail_restored_s"]))
        elif st.get("tail_restore"):
            lines.append("⚠️ ending: the last scene's Somali voice could not be put back -- "
                         + str(st["tail_restore"])[:140])''', "ending report line")

open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patched", P)
