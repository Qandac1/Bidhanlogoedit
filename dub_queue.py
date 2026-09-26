"""Dub-sync QUEUE -- send movie after movie; the bot conforms them one at a time.

John 2026-09-26: "send different movies so the bot will do them one by one, and I get
each dub-synced Somali film".  One GLOBAL queue: the server runs ONE dub-sync at a time
(two in parallel collapse the CPU demucs).  Each entry is one movie: its HD + dub
messages and the choices made on the confirm panel (swap, branding, mode).  A worker
starts the next film the moment the previous one ends -- delivered, failed or
cancelled.  Each film runs in its OWN task, so /cancel stops that film only and the
queue carries on.  The film itself is bot.py's _run_dubsync, unchanged.

Saved to STORE after every change; after a bot restart the queue is picked up again
(a film that was running starts over, at the front).  If this module cannot load,
bot.py starts dub-syncs directly, exactly as before.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import InlineKeyboardButton as IKB
from pyrogram.types import InlineKeyboardMarkup as IKM

log = logging.getLogger("dubqueue")
STORE = "/app/data/dub_queue.json"
KEEP_FINISHED = 8            # finished entries still shown in /queue
BUSY_POLL_S = 20

_deps: dict = {}
_q: list[dict] = []          # {id, uid, chat, mids, hd_i, brand, mode, title, state, added, started, ended, note}
_panels: dict[int, object] = {}
_wake: asyncio.Event | None = None
_worker: asyncio.Task | None = None
_current: dict = {}          # {"entry", "task"} while a film runs


def register(app, allowed, run, busy_other, cancel_running, start_flow) -> None:
    """Called once from bot.py.
    run(uid, msgs, hd_i, brand, mode)  -- the dub-sync job (bot._run_dubsync)
    busy_other() -> True while something else heavy runs (a trailer, a direct dub-sync)
    cancel_running(uid) -- stop the film that runs now (bot._cancel_everything)
    start_flow(uid, message) -- open the /dub intake for one more movie"""
    _deps.update(app=app, allowed=allowed, run=run, busy_other=busy_other,
                 cancel_running=cancel_running, start_flow=start_flow)
    app.add_handler(MessageHandler(_cmd, filters.command(["queue", "jobs"]) & filters.private), group=-2)
    app.add_handler(CallbackQueryHandler(_cb, filters.regex(r"^dq:")), group=-2)


# ---- state ------------------------------------------------------------------
def _save() -> None:
    try:
        tmp = STORE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_q, f)
        os.replace(tmp, STORE)
    except Exception:
        log.exception("dub queue: save failed")


def _waiting() -> list:
    return [e for e in _q if e["state"] == "waiting"]


def _trim_finished() -> None:
    fin = sorted([e for e in _q if e["state"] not in ("waiting", "running")],
                 key=lambda e: e.get("ended") or 0)          # oldest-ended go first
    for e in fin[:-KEEP_FINISHED]:
        _q.remove(e)


def _ensure_worker() -> None:
    global _wake, _worker
    if _wake is None:
        _wake = asyncio.Event()
    if _worker is None or _worker.done():
        _worker = asyncio.get_event_loop().create_task(_work())
    _wake.set()


async def enqueue(uid: int, msgs: list, hd_i: int, brand: bool, mode: str, title: str) -> int:
    """Add one movie; returns its place (1 = starts now, 2 = next, ...)."""
    nid = int(time.time() * 1000)                # unique: two movies can arrive in one ms
    taken = {x["id"] for x in _q}
    while nid in taken:
        nid += 1
    e = {"id": nid, "uid": uid, "chat": msgs[0].chat.id,
         "mids": [m.id for m in msgs], "hd_i": hd_i, "brand": brand, "mode": mode,
         "title": title[:60], "state": "waiting", "added": time.time(),
         "started": None, "ended": None, "note": ""}
    _q.append(e)
    _save()
    place = len(_waiting()) + (1 if _current else 0)
    _ensure_worker()
    await _refresh_panels()
    return place


async def resume() -> None:
    """At bot start: pick the saved queue up again."""
    global _q
    try:
        with open(STORE) as f:
            _q = json.load(f)
    except FileNotFoundError:
        _q = []
        return
    except Exception:
        log.exception("dub queue: could not read %s", STORE)
        _q = []
        return
    again = [e for e in _q if e["state"] == "running"]
    for e in again:                      # the restart stopped it: run it again, first
        e.update(state="waiting", started=None, note="restarted -- running it again")
        _q.remove(e)
        _q.insert(0, e)
    _save()
    if _waiting():
        _ensure_worker()
        for uid in {e["uid"] for e in _waiting()}:
            n = sum(1 for e in _waiting() if e["uid"] == uid)
            try:
                await _deps["app"].send_message(
                    uid, "🔁 The bot restarted — your **dub-sync queue** carries on "
                         "(%d movie%s). /queue shows it." % (n, "" if n == 1 else "s"))
            except Exception:
                pass


# ---- the worker ---------------------------------------------------------------
async def _messages(e: dict):
    try:
        got = await _deps["app"].get_messages(e["chat"], e["mids"])
    except Exception:
        return None
    got = got if isinstance(got, list) else [got]
    if len(got) != 2 or any(getattr(m, "empty", False) or m is None for m in got):
        return None
    return got


def _busy() -> bool:
    try:
        return bool(_deps["busy_other"]())
    except Exception:
        log.exception("dub queue: busy check failed")
        return False


async def _work() -> None:
    """Never dies: a failure inside one film's turn marks that film and moves on."""
    while True:
        e = next(iter(_waiting()), None)
        if e is None:
            _wake.clear()
            await _wake.wait()
            continue
        try:
            await _turn(e)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("dub queue: turn failed")
            if e["state"] in ("waiting", "running"):
                e.update(state="failed", ended=time.time(), note=str(exc)[:120])
            _save()
            await _refresh_panels()


async def _turn(e: dict) -> None:
    """One film: wait for a free machine, fetch its two messages, run it in its own task."""
    if _busy():
        e["note"] = "waiting for the job that runs now"
        await _refresh_panels()
        while _busy():
            await asyncio.sleep(BUSY_POLL_S)
        e["note"] = ""
        if e["state"] != "waiting":
            return                                # removed while it waited
    msgs = await _messages(e)
    if msgs is None:
        e.update(state="failed", ended=time.time(), note="its files are no longer in the chat")
        _save()
        await _refresh_panels()
        return
    e.update(state="running", started=time.time(), note="")
    _save()
    await _refresh_panels()
    t = asyncio.get_event_loop().create_task(
        _deps["run"](e["uid"], msgs, e["hd_i"], e["brand"], e["mode"]))
    _current.update(entry=e, task=t)
    try:
        await asyncio.wait({t})
    finally:
        _current.clear()
    e["ended"] = time.time()
    if t.cancelled():
        e["state"] = "cancelled"
    elif t.exception() is not None:
        e.update(state="failed", note=str(t.exception())[:120])
    else:
        e["state"] = "finished"                   # ✅ or ❌: the film's own message says which
    _trim_finished()
    _save()
    await _refresh_panels()


# ---- the panel ------------------------------------------------------------------
def _dur(s: float) -> str:
    s = int(max(0, s))
    return "%dh %02dm" % (s // 3600, s % 3600 // 60) if s >= 3600 else "%dm" % (s // 60)


def panel_text(uid: int) -> str:
    rows = []
    run = [e for e in _q if e["state"] == "running"]
    wait = _waiting()
    fin = [e for e in _q if e["state"] not in ("waiting", "running")]
    for e in run:
        who = "" if e["uid"] == uid else " _(another user)_"
        rows.append("▶️ **Now** `%s`%s · %s" % (e["title"][:38], who, _dur(time.time() - (e["started"] or time.time()))))
    for n, e in enumerate(wait, 1):
        mine = e["uid"] == uid
        rows.append("⏳ **%d.** %s%s" % (n, ("`%s`" % e["title"][:38]) if mine else "_another user's movie_",
                                          (" · " + e["note"]) if e["note"] and mine else ""))
    mine_fin = sorted([e for e in fin if e["uid"] == uid], key=lambda e: e.get("ended") or 0)
    if mine_fin and rows:
        rows.append("")
    icon = {"finished": "🏁", "failed": "❌", "cancelled": "🛑", "removed": "✖️"}
    for e in mine_fin[-KEEP_FINISHED:]:
        took = (" · " + _dur(e["ended"] - e["started"])) if e.get("started") and e.get("ended") else ""
        rows.append("%s `%s`%s%s" % (icon.get(e["state"], "·"), e["title"][:38], took,
                                    (" · " + e["note"]) if e["note"] else ""))
    head = "📋 **Dub-sync queue** — one film at a time, each delivered when done"
    if not rows:
        return head + "\n\nEmpty. Send /dub (HD, then dub) and tap ✅ Start — or ➕ below."
    return head + "\n\n" + "\n".join(rows) + \
        "\n\n_🏁 finished: the film's own message says ✅ delivered or ❌ why not._"


def panel_kb(uid: int) -> IKM:
    rows = []
    for n, e in enumerate(_waiting(), 1):
        if e["uid"] != uid:
            continue
        r = []
        if n > 1:
            r.append(IKB("⬆️ %d" % n, "dq:up:%d" % e["id"]))
        r.append(IKB("✖ %d" % n, "dq:rm:%d" % e["id"]))
        rows.append(r)
    rows.append([IKB("➕ Add a movie", "dq:add"), IKB("🔄 Refresh", "dq:ref")])
    if any(e["uid"] == uid and e["state"] in ("waiting", "running") for e in _q):
        rows.append([IKB("🛑 Stop all mine", "dq:stop")])
    return IKM(rows)


async def _refresh_panels() -> None:
    for uid, msg in list(_panels.items()):
        try:
            await msg.edit(panel_text(uid), reply_markup=panel_kb(uid))
        except Exception:
            pass


async def _cmd(_, m):
    uid = m.from_user.id
    if not _deps["allowed"](uid):
        return
    _panels[uid] = await m.reply(panel_text(uid), reply_markup=panel_kb(uid))
    m.stop_propagation()


async def _cb(_, cq):
    uid = cq.from_user.id
    try:
        if not _deps["allowed"](uid):
            return await cq.answer("private", show_alert=True)
        parts = cq.data.split(":")
        act = parts[1]
        if act == "show":                         # a fresh list, the prompt above stays
            await cq.answer()
            _panels[uid] = await cq.message.reply(panel_text(uid), reply_markup=panel_kb(uid))
            return
        if act == "add":
            await cq.answer("Send the HD")
            await _deps["start_flow"](uid, cq.message)
            return
        if act in ("up", "rm"):
            eid = int(parts[2])
            e = next((x for x in _waiting() if x["id"] == eid and x["uid"] == uid), None)
            if e is None:
                return await cq.answer("Already started or gone.", show_alert=True)
            if act == "rm":
                e.update(state="removed", ended=time.time())
                await cq.answer("Removed")
            else:
                w = _waiting()
                i = w.index(e)
                if i > 0:
                    a, b = _q.index(w[i - 1]), _q.index(e)
                    _q[a], _q[b] = _q[b], _q[a]
                await cq.answer("Moved up")
            _trim_finished()
            _save()
        elif act == "stop":
            n = 0
            for e in _waiting():
                if e["uid"] == uid:
                    e.update(state="removed", ended=time.time(), note="stopped")
                    n += 1
            _save()
            cur = _current.get("entry")
            if cur and cur["uid"] == uid:
                await _deps["cancel_running"](uid)
            await cq.answer("Stopped%s" % (" (+%d waiting removed)" % n if n else ""))
        else:
            await cq.answer()
        _panels[uid] = cq.message
        try:
            await cq.message.edit(panel_text(uid), reply_markup=panel_kb(uid))
        except Exception:
            pass
    finally:
        cq.stop_propagation()


def running_title() -> str | None:
    e = _current.get("entry")
    return e["title"] if e else None
