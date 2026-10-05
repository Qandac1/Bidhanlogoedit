"""bot34: /trailer intake -- A FILE SENT TO /trailer NEVER FALLS THROUGH TO THE OTHER FLOWS OF THE BOT.

2026-10-05 15:00, first real test of the fast way, 24 s after a bot restart: Telegram refused the edit of the
/trailer prompt (MESSAGE_ID_INVALID). The exception left _take before m.stop_propagation(), so the trailer, the
Somali film and the film with its own sound went on to bot.py and were queued as "3 videos" for logo branding.
The same hole was in the flow of before bot33 (every intake step edits the prompt first).

trailer_flow.py:
  _show()   the intake's message shows the next step; an edit Telegram refuses sends the text as a NEW message and
            the intake goes on with that one
  _take()   is now a guard around the steps (_take_step, the code of before): whatever fails inside, the file
            stays with /trailer, the user is told to send it again, propagation is stopped
  FAST_STAGES  the finding stage is expected to take 900 s, not 420 (the first real bot run, Agent 2023: 15 min 16 s --
            the picture thumbnails of two films it had never seen are made in this stage); only the panel's clock
Nothing else changes: the prompts, the order of the steps, _run / _run_fast / the buttons.
Usage: python patch_bot_trailerguard34.py <bot dir>     (patches <bot dir>/trailer_flow.py in place; needs bot33)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "trailer_flow.py"
s = P.read_text()
if "_take_step" in s:
    sys.exit("already patched: %s" % P)
assert "_run_fast" in s, "bot33 (patch_bot_trailerfast33.py) must be in first"


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''async def _take(_, m):
    uid = m.from_user.id
    st = _intake.get(uid)
    if not st:
        return                                   # not ours: bot.py handles it as before
    if st["step"] == "trailer" and _is_video(m):
        st["trailer"], st["step"] = m, "film"
        await st["prompt"].edit("🎬 **Somali trailer**\\n\\n✅ Trailer received\\n"
                                "**2/4** Now send the **Somali film** (the full dubbed movie).",
                                reply_markup=_kb_cancel())
    elif st["step"] == "film" and _is_video(m):
        st["film"], st["step"] = m, "orig"
        await st["prompt"].edit(ORIG_ASK, reply_markup=_kb_cancel([IKB("⏭ Skip", "trl:noorig")]))
    elif st["step"] == "orig" and _is_video(m):                 # the fast way
        st["orig"], st["step"] = m, "subs"
        await st["prompt"].edit(SUBS_ASK_FAST, reply_markup=_kb_cancel([IKB("⏭ No subtitles", "trl:nosubs")]))
''', '''async def _show(st: dict, m, text: str, kb) -> None:
    """The intake's one message shows the next step. An edit that Telegram refuses (the message is gone:
    MESSAGE_ID_INVALID right after a restart, 2026-10-05) sends the text as a NEW message, and the intake goes on
    with that one."""
    try:
        await st["prompt"].edit(text, reply_markup=kb)
    except Exception as exc:
        if type(exc).__name__ == "MessageNotModified":
            return
        log.warning("trailer prompt could not be edited (%s) -- sent again as a new message", exc)
        st["prompt"] = await m.reply(text, reply_markup=kb)


async def _take(_, m):
    """A file sent while this user is in the /trailer intake STAYS with /trailer: whatever fails inside a step,
    the user is told and propagation is stopped (2026-10-05: a failed prompt edit let three films fall through
    to the logo queue)."""
    if not _intake.get(m.from_user.id):
        return                                   # not ours: bot.py handles it as before
    from pyrogram import ContinuePropagation, StopPropagation
    try:
        await _take_step(_, m)
    except (StopPropagation, ContinuePropagation):
        raise
    except Exception:
        log.exception("trailer intake step failed")
        try:
            await m.reply("⚠️ That did not go through — please send the file again, or /cancel.")
        except Exception:
            pass
    m.stop_propagation()


async def _take_step(_, m):
    uid = m.from_user.id
    st = _intake.get(uid)
    if not st:
        return                                   # not ours: bot.py handles it as before
    if st["step"] == "trailer" and _is_video(m):
        st["trailer"], st["step"] = m, "film"
        await _show(st, m, "🎬 **Somali trailer**\\n\\n✅ Trailer received\\n"
                           "**2/4** Now send the **Somali film** (the full dubbed movie).", _kb_cancel())
    elif st["step"] == "film" and _is_video(m):
        st["film"], st["step"] = m, "orig"
        await _show(st, m, ORIG_ASK, _kb_cancel([IKB("⏭ Skip", "trl:noorig")]))
    elif st["step"] == "orig" and _is_video(m):                 # the fast way
        st["orig"], st["step"] = m, "subs"
        await _show(st, m, SUBS_ASK_FAST, _kb_cancel([IKB("⏭ No subtitles", "trl:nosubs")]))
''', "_show; _take guards the steps; the three video steps use _show")

rep('''        st["step"] = "subs"
        return await _take(_, m)
''', '''        st["step"] = "subs"
        return await _take_step(_, m)
''', "the straight-to-subtitles step stays inside the guard")

rep('''        await st["prompt"].edit(MOVIE_SUBS_ASK % got, reply_markup=_kb_cancel([IKB("⏭ Skip", "trl:nomovie")]))
''', '''        await _show(st, m, MOVIE_SUBS_ASK % got, _kb_cancel([IKB("⏭ Skip", "trl:nomovie")]))
''', "the movie-subtitles step uses _show")

rep('''               ("sound", "Find every line (by sound, then by words)", 420),''',
    '''               ("sound", "Find every line (by sound, then by words)", 900),''',
    "the fast way's finding stage: 15 min is its real length on films the engine sees for the first time")

P.write_text(s)
print("patched %s" % P)
