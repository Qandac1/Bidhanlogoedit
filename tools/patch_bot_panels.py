"""bot14: the banner flow and the dub-sync flow stay separate (John 2026-09-29: "before they were different:
/dub for dub-sync, send a file for logo / trim"). Three bugs seen that evening, each fixed at its cause:
  1. After a dub film was started, the "Next movie?" intake stayed open with no limit and SILENTLY took
     the next video as that movie's HD (17:59) and then as its Somali dub (18:09) -- only an old message far
     up the chat was edited, so John saw no reply. Now a file arriving in that intake gets a NEW message:
     "Next dub-sync movie, or brand this video?" -- two buttons. An explicit /dub still takes files directly.
  2. That left a dub selection (QASRIGA + QASRIGA) behind; every settings redraw then drew the BANNER job's
     panel as "Ready to dub-sync" with a Start button that would have dub-synced the film against itself.
     Now the dub panel is drawn only on the dub panel's own message, and /cancel clears an unstarted
     dub selection.
  3. /cancel during the banner scan said "Download cancelled" while the scan went on (the scan runs ffmpeg
     in a thread and registers no process; a re-send then ran a second scan beside it). Now the scan
     registers its job folder and /cancel kills every process working inside that folder.
Additive on bot13. Usage: python3 patch_bot_panels.py <bot dir>"""
import os
import sys

B = os.path.join(sys.argv[1], "bot.py")
s = open(B, encoding="utf-8").read()
if "_kill_procs_in" in s:
    raise SystemExit("already patched")


def rep(old, new, what):
    global s
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


rep('_dubflow: dict[int, dict] = {}            # uid -> guided dub-sync intake\n',
    '_dubflow: dict[int, dict] = {}            # uid -> guided dub-sync intake\n'
    '_dubchoice: dict = {}                     # uid -> a file waiting for "next dub movie or brand it?"\n',
    "state")

rep('''async def _cancel_everything(uid: int) -> list:''',
    '''def _kill_procs_in(path: str) -> bool:
    """Kill every process working inside this job's own folder. A step that runs ffmpeg in a THREAD
    (the banner scan) registers no process, so /cancel said "cancelled" while the scan went on
    (2026-09-29). Matches the folder with a trailing slash, never this bot itself."""
    import signal
    if not path:
        return False
    key, me, hit = path.rstrip("/") + "/", os.getpid(), False
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            with open("/proc/%s/cmdline" % d, "rb") as f:
                cmd = f.read().replace(b"\\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if key in cmd:
            try:
                os.kill(int(d), signal.SIGKILL)
                hit = True
            except OSError:
                pass
    return hit


async def _cancel_everything(uid: int) -> list:''', "kill helper")

rep('''    if _dubflow.pop(uid, None) is not None:
        done.append("🎬 dub-sync intake cancelled")
''',
    '''    if _dubflow.pop(uid, None) is not None:
        done.append("🎬 dub-sync intake cancelled")
    _dubchoice.pop(uid, None)
    # an unstarted dub selection must not outlive a cancel: it drew the next banner panel as
    # "Ready to dub-sync" (2026-09-29)
    if _dubsel.pop(uid, None) is not None:
        done.append("🎬 unstarted dub-sync selection cleared")
''', "cancel clears selection")

rep('''        task = a.get("task")
        if task is not None and not task.done():
            try:
                task.cancel()
                killed = True
            except Exception:
                pass
''',
    '''        task = a.get("task")
        if task is not None and not task.done():
            try:
                task.cancel()
                killed = True
            except Exception:
                pass
        # a step running ffmpeg in a thread registers no process: stop everything in the job's folder
        if a.get("work") and _kill_procs_in(a["work"]):
            killed = True
''', "cancel kills the folder")

rep('''                sp = asyncio.create_task(scan_poll())
''',
    '''                _act(uid).update(work=work, phase="Banner scan")   # so /cancel can stop it (bot14)
                sp = asyncio.create_task(scan_poll())
''', "scan registers its folder")

rep('''async def _refresh_active_panel(cq, uid: int, job: dict) -> None:
    """Redraw whichever panel is open — dub or branding."""
    if _dubsel.get(uid):
''',
    '''async def _refresh_active_panel(cq, uid: int, job: dict) -> None:
    """Redraw whichever panel is open — dub or branding. The dub panel only on the dub panel's OWN
    message: a leftover dub selection drew a banner job as "Ready to dub-sync" (2026-09-29)."""
    _sel = _dubsel.get(uid)
    _pm = (_sel or {}).get("panel")
    if _sel and (getattr(_pm, "id", None) == getattr(cq.message, "id", -1)
                 or (_pm is None and not _pending.get(uid))):
''', "panel choice")

rep('''async def _dubflow_take(uid: int, m: Message) -> bool:
    """Consume a file for the guided flow. True if it was taken."""
    fl = _dubflow.get(uid)
    if not fl:
        return False
''',
    '''async def _dubflow_take(uid: int, m: Message) -> bool:
    """Consume a file for the guided flow. True if it was taken."""
    fl = _dubflow.get(uid)
    if not fl:
        return False
    if fl.get("next") and fl["step"] == "hd" and not fl.get("chosen"):
        # after a film was started, a file is NOT silently taken as the next dub movie -- John sends
        # banner videos too (2026-09-29: two banner sends vanished into this intake). Ask, visibly.
        _dubchoice[uid] = m
        await m.reply("🎬 **Next dub-sync movie**, or 🎨 **brand this video** (logo / trim / banners)?",
                      reply_markup=IKM([[IKB("🎬 Next dub-sync movie", "dubflow:asdub"),
                                         IKB("🎨 Brand this video", "dubflow:asbrand")]]))
        return True
''', "intake asks")

rep('''                await _dubflow_start(uid, cq.message, DUB_NEXT_HD,
                                     IKM([[IKB("✅ Done", "dubflow:done"), IKB("📋 Queue", "dq:show")]]))
                return
''',
    '''                await _dubflow_start(uid, cq.message, DUB_NEXT_HD,
                                     IKM([[IKB("✅ Done", "dubflow:done"), IKB("📋 Queue", "dq:show")]]))
                _dubflow[uid]["next"] = True        # files here are ASKED about, never taken silently
                return
''', "next intake flagged")

rep('''    if data == "dubflow:cancel":
''',
    '''    if data in ("dubflow:asdub", "dubflow:asbrand"):
        m0 = _dubchoice.pop(uid, None)
        if m0 is None:
            return await cq.answer("That file is gone — send it again.", show_alert=True)
        await cq.answer()
        if data == "dubflow:asbrand":
            _dubflow.pop(uid, None)
            try:
                await cq.message.edit("🎨 Branding this video — your dub-sync queue is untouched.")
            except Exception:
                pass
            _enqueue(uid, m0)
            return
        fl = _dubflow.get(uid)
        if fl is None:
            try:
                await cq.message.edit("⚠️ The dub-sync intake was closed — send /dub to add a movie.")
            except Exception:
                pass
            return
        fl["chosen"] = True
        fl["prompt"] = cq.message              # the visible, recent message carries the next steps
        await _dubflow_take(uid, m0)
        return

    if data == "dubflow:cancel":
''', "choice buttons")
open(B, "w", encoding="utf-8", newline="\n").write(s)
print("patched", B)
