"""/trailer -- Somali trailer: official trailer + Somali film -> the same trailer in Somali.

Separate from /dub: its own command, its own intake state, its own buttons (all
callback data starts with "trl:"). Handlers sit in group -2 and only CLAIM what is
theirs (a file while this user is in the /trailer intake, a "trl:" button); every
other message and button falls through to bot.py's handlers exactly as before.

Engine: /opt/dubsync2/trailer_dub.py
  prepare -> lines placed only when PROVEN (picture + meaning, meaning, pull-in),
             listening clips for the rest
  (John taps the right Somali line for each question; every tap is saved)
  finish  -> the Somali trailer (picture untouched)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import InlineKeyboardButton as IKB
from pyrogram.types import InlineKeyboardMarkup as IKM

log = logging.getLogger("trailer")
ENGINE = ["/opt/dubsync2/.venv/bin/python", "/opt/dubsync2/trailer_dub.py"]
JOBS = Path("/opt/dubsync2/trailers_out/jobs")
HARD_CAP_S = 4 * 3600          # a prepare that runs longer than this is stopped

_deps: dict = {}
_intake: dict[int, dict] = {}   # uid -> {"step", "trailer", "film", "prompt"}
_ask: dict[int, dict] = {}      # uid -> {"jobdir", "job", "qs", "pos", "choices", "status"}


def register(app, allowed, build_job, busy) -> None:
    """Called once from bot.py. allowed(uid)->bool; build_job(uid, msg, status)->{"src"...};
    busy()->True while another (dub / branding) job runs."""
    _deps.update(app=app, allowed=allowed, build_job=build_job, busy=busy)
    app.add_handler(MessageHandler(_cmd, filters.command("trailer") & filters.private), group=-2)
    app.add_handler(MessageHandler(_take, (filters.video | filters.document) & filters.private), group=-2)
    app.add_handler(CallbackQueryHandler(_cb, filters.regex(r"^trl:")), group=-2)


def _kb_cancel(extra=None) -> IKM:
    rows = [extra] if extra else []
    return IKM(rows + [[IKB("❌ Cancel", "trl:cancel")]])


async def _cmd(_, m):
    uid = m.from_user.id
    if not _deps["allowed"](uid):
        await m.reply("⛔ This bot is private.")
        return m.stop_propagation()
    _ask.pop(uid, None)
    _intake[uid] = {"step": "trailer", "trailer": None, "film": None, "subs": None, "movie_subs": None}
    _intake[uid]["prompt"] = await m.reply(
        "🎬 **Somali trailer**\n\n**1/4** Send the official **trailer** (video).",
        reply_markup=_kb_cancel())
    m.stop_propagation()


MOVIE_SUBS_ASK = ("🎬 **Somali trailer**\n\n✅ Trailer received\n✅ Somali film received\n%s\n"
                  "**4/4** Send the **MOVIE's English subtitles** (.srt — the whole film, from subdl.com "
                  "or opensubtitles.org). With them most lines are placed automatically. Or tap **Skip**.")


def _is_video(m) -> bool:
    if m.video:
        return True
    d = m.document
    return bool(d and ((d.mime_type or "").startswith("video") or
                       re.search(r"\.(mp4|mkv|mov|avi|webm|ts)$", d.file_name or "", re.I)))


def _is_subs(m) -> bool:
    d = m.document
    return bool(d and re.search(r"\.(srt|vtt)$", d.file_name or "", re.I))


async def _take(_, m):
    uid = m.from_user.id
    st = _intake.get(uid)
    if not st:
        return                                   # not ours: bot.py handles it as before
    if st["step"] == "trailer" and _is_video(m):
        st["trailer"], st["step"] = m, "film"
        await st["prompt"].edit("🎬 **Somali trailer**\n\n✅ Trailer received\n"
                                "**2/4** Now send the **Somali film** (the full dubbed movie).",
                                reply_markup=_kb_cancel())
    elif st["step"] == "film" and _is_video(m):
        st["film"], st["step"] = m, "subs"
        await st["prompt"].edit(
            "🎬 **Somali trailer**\n\n✅ Trailer received\n✅ Somali film received\n"
            "**3/4** Send the **trailer's** English subtitles (.srt) if you have them "
            "(exact timing and words), or tap **No subtitles**.",
            reply_markup=_kb_cancel([IKB("⏭ No subtitles", "trl:nosubs")]))
    elif st["step"] == "subs" and _is_subs(m):
        st["subs"], st["step"] = m, "movie_subs"
        await st["prompt"].edit(MOVIE_SUBS_ASK % "✅ Trailer subtitles received",
                                reply_markup=_kb_cancel([IKB("⏭ Skip", "trl:nomovie")]))
    elif st["step"] == "movie_subs" and _is_subs(m):
        st["movie_subs"] = m
        _start(uid)
    else:
        await m.reply("Waiting for the %s. /cancel or ❌ to stop." %
                      {"trailer": "trailer video", "film": "Somali film video",
                       "subs": "trailer subtitles (.srt) or the No subtitles button",
                       "movie_subs": "movie subtitles (.srt) or the Skip button"}[st["step"]])
    m.stop_propagation()


def _start(uid: int) -> None:
    st = _intake.pop(uid)
    asyncio.get_event_loop().create_task(_run(uid, st))


async def _run(uid: int, st: dict) -> None:
    status = st["prompt"]
    jobdir = JOBS / ("%d_%d" % (uid, int(time.time())))
    jobdir.mkdir(parents=True, exist_ok=True)

    async def say(txt):
        try:
            await status.edit("🎬 **Somali trailer**\n\n" + txt, reply_markup=_kb_cancel())
        except Exception:
            pass
    try:
        if _deps["busy"]():
            await say("⏳ Waiting for the film that is running now to finish — your films go first.")
            while _deps["busy"]():
                await asyncio.sleep(30)
        await say("⬇️ Downloading the trailer…")
        tj = await _deps["build_job"](uid, st["trailer"], status)
        await say("⬇️ Downloading the Somali film…")
        fj = await _deps["build_job"](uid, st["film"], status)
        cmd = [*ENGINE, "prepare", "--trailer", tj["src"], "--film", fj["src"], "--job", str(jobdir)]
        if st.get("subs"):
            sp = str(jobdir / "subs.srt")
            await st["subs"].download(file_name=sp)
            cmd += ["--subs", sp]
        if st.get("movie_subs"):
            mp = str(jobdir / "movie.srt")
            await st["movie_subs"].download(file_name=mp)
            cmd += ["--movie-subs", mp]
        await say("🔎 Preparing…")
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        t0, tail, result = time.time(), [], None
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=60)
            except asyncio.TimeoutError:
                if time.time() - t0 > HARD_CAP_S:
                    proc.kill()
                    raise RuntimeError("preparing took longer than 4 hours — stopped")
                continue
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if line:
                tail = (tail + [line])[-6:]
            if line.startswith("STEP "):
                await say("🔎 " + line[5:] + "\n⏱ %d min" % ((time.time() - t0) // 60))
            elif line.startswith(("PREPARED", "REFUSED")):
                result = line
        rc = await proc.wait()
        if result and result.startswith("REFUSED"):
            return await say("⛔ " + result[8:])
        if rc != 0 or not result:
            raise RuntimeError("prepare failed: " + " › ".join(tail[-3:])[:400])
        job = json.load(open(jobdir / "job.json"))
        qs = [c["i"] for c in job["cues"] if not c.get("auto")]
        auto = sum(1 for c in job["cues"] if c.get("auto"))
        _ask[uid] = {"jobdir": jobdir, "job": job, "qs": qs, "pos": 0, "choices": {}, "status": status}
        if not qs:
            return await _finish(uid)
        try:
            await status.edit(
                "🎬 **Somali trailer**\n\n✅ **%d** of %d lines placed automatically (proven).\n"
                "**%d** lines left. Choose:\n"
                "⚡ **Best answers** — the bot takes its best Somali line for each (how Test 4 was made)\n"
                "🎧 **Check each line** — listen and tap: the trailer's line plays, then Somali "
                "**1** (1 beep), **2** (2 beeps), **3** (3 beeps)" % (auto, len(job["cues"]), len(qs)),
                reply_markup=IKM([[IKB("⚡ Best answers for all lines", "trl:auto")],
                                  [IKB("🎧 Let me check each line", "trl:manual")],
                                  [IKB("❌ Cancel", "trl:cancel")]]))
        except Exception:
            await _question(uid)
    except Exception as exc:
        log.exception("trailer job failed")
        await say("❌ %s" % exc)


def _mmss(t: float) -> str:
    return "%d:%02d" % (t // 60, t % 60)


async def _ask_engine(jobdir: Path, i: int, clips: bool = True) -> list:
    """Candidates for line i built fresh with every pick so far (engine `ask`), strongest
    evidence first; listening clips rendered unless clips=False (the automatic mode)."""
    extra = [] if clips else ["--no-clips"]
    proc = await asyncio.create_subprocess_exec(*ENGINE, "ask", "--job", str(jobdir), "--cue", str(i), *extra,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    raw, _ = await proc.communicate()
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("ASK "):
            return json.load(open(jobdir / ("cands_%02d.json" % i)))
    raise RuntimeError("could not build the question for line %d" % (i + 1))


def _choice(cd: dict):
    """A candidate as it is stored in choices.json."""
    if cd.get("covered_by") is not None:
        return "cov:%d" % cd["covered_by"]
    return [cd["film_t"], cd["film_t1"]]


async def _auto(uid: int) -> None:
    """⚡ Best answers: #1 for every line, in trailer order (each re-built with the answers
    so far), then a second pass where later answers changed a line's #1 -- exactly how
    Test 4 was made (John: "this is how any feature trailer should be")."""
    st = _ask.get(uid)
    if not st:
        return
    jd, status = st["jobdir"], st["status"]
    first = {}
    try:
        await status.edit("🎬 **Somali trailer**\n\n⚡ Choosing the best Somali line for %d lines…" % len(st["qs"]))
    except Exception:
        pass
    for i in st["qs"]:
        cands = await _ask_engine(jd, i, clips=False)
        if cands:
            first[i] = cands[0]
            st["choices"][str(i)] = _choice(cands[0])
            json.dump(st["choices"], open(jd / "choices.json", "w"))
    for i in list(first):
        st["choices"].pop(str(i), None)
        json.dump(st["choices"], open(jd / "choices.json", "w"))
        cands = await _ask_engine(jd, i, clips=False)
        best = cands[0] if cands and not _same(cands[0], first[i]) else first[i]
        st["choices"][str(i)] = _choice(best)
        json.dump(st["choices"], open(jd / "choices.json", "w"))
    st["pos"] = len(st["qs"])
    await _finish(uid)


def _same(a: dict, b: dict) -> bool:
    if a.get("covered_by") is not None or b.get("covered_by") is not None:
        return a.get("covered_by") == b.get("covered_by")
    return abs(a["film_t"] - b["film_t"]) < 0.5


async def _question(uid: int) -> None:
    st = _ask.get(uid)
    if not st:
        return
    round2 = st.get("round", 1) == 2
    while True:
        while st["pos"] < len(st["qs"]):
            i = st["qs"][st["pos"]]
            cands = await _ask_engine(st["jobdir"], i)
            first1 = st.setdefault("first1", {}).get(i)
            if cands and not (round2 and first1 is not None and _same(cands[0], first1)):
                break
            st["choices"].setdefault(str(i), 0)      # nothing (new) to offer: stays original
            st["pos"] += 1
        if st["pos"] < len(st["qs"]):
            break
        # ROUND 2: lines answered None are asked again only if the picks made after them
        # gave them a new first answer (lines just BEFORE a later pick, e.g. 14-15 before 16)
        left = [i for i in st["qs"] if st["choices"].get(str(i)) == 0] if not round2 else []
        if not left:
            return await _finish(uid)
        st.update(round=2, qs=left, pos=0)
        round2 = True
    if not round2:
        st["first1"][i] = cands[0]
    st["cands"] = cands
    c = st["job"]["cues"][i]
    n1 = min(3, len(cands))
    row = [IKB(str(k), "trl:pick:%d:%d" % (st["pos"], k)) for k in range(1, n1 + 1)]
    row2 = ([IKB("▶ 4–%d" % min(6, len(cands)), "trl:more:%d" % st["pos"])] if len(cands) > 3 else [])
    row2 += [IKB("✖ None", "trl:pick:%d:0" % st["pos"])]
    kb = IKM([row, row2, [IKB("🎬 Finish now (rest stays original)", "trl:finish")]])
    opts = []
    for k, cd in enumerate(cands[:3], 1):
        tag = (" (conversation order)" if cd["how"].startswith(("conversation", "inside"))
               else " (movie subtitles)" if cd["how"].startswith("movie") else "")
        opts.append("**%d**%s — %s" % (k, tag, (cd.get("so") or "")[:48] or "(Somali voice, no clear words)"))
    head = ("🔁 **Round 2** — new answer from your picks · " if round2 else "") + \
        "question %d/%d" % (st["pos"] + 1, len(st["qs"]))
    cap = ("🎧 **Line %d of %d** · %s–%s · %s\n“%s”\n\n%s"
           % (i + 1, len(st["job"]["cues"]), _mmss(c["t0"]), _mmss(c["t1"]), head, c["text"],
              "\n".join(opts)))
    await _deps["app"].send_voice(uid, str(st["jobdir"] / ("ask_%02d_p1.ogg" % i)), caption=cap[:1000],
                                  reply_markup=kb)


async def _cb(_, cq):
    uid = cq.from_user.id
    data = cq.data
    try:
        if not _deps["allowed"](uid):
            await cq.answer("private", show_alert=True)
            return
        if data == "trl:cancel":
            _intake.pop(uid, None)
            _ask.pop(uid, None)
            await cq.answer("Cancelled")
            try:
                await cq.message.edit("🎬 Somali trailer — cancelled.")
            except Exception:
                pass
            return
        if data == "trl:nosubs":
            if uid in _intake and _intake[uid]["step"] == "subs":
                await cq.answer("No trailer subtitles — the bot will listen to the trailer itself")
                _intake[uid]["step"] = "movie_subs"
                try:
                    await _intake[uid]["prompt"].edit(
                        MOVIE_SUBS_ASK % "⏭ No trailer subtitles",
                        reply_markup=_kb_cancel([IKB("⏭ Skip", "trl:nomovie")]))
                except Exception:
                    pass
            else:
                await cq.answer()
            return
        if data == "trl:nomovie":
            if uid in _intake and _intake[uid]["step"] == "movie_subs":
                await cq.answer("No movie subtitles")
                _start(uid)
            else:
                await cq.answer()
            return
        st = _ask.get(uid)
        if not st:
            await cq.answer("This trailer job has ended.", show_alert=True)
            return
        if data in ("trl:auto", "trl:manual"):
            if st.get("mode"):
                await cq.answer("Already started")
                return
            st["mode"] = data[4:]
            await cq.answer("⚡ Best answers" if data == "trl:auto" else "🎧 Here comes line 1")
            if data == "trl:auto":
                asyncio.get_event_loop().create_task(_auto(uid))
            else:
                await _question(uid)
            return
        if data == "trl:finish":
            await cq.answer("Building now")
            _ask[uid]["pos"] = len(st["qs"])
            return await _finish(uid)
        parts = data.split(":")
        pos = int(parts[2])
        if pos != st["pos"]:
            await cq.answer("Already answered")
            return
        i = st["qs"][pos]
        cands = st.get("cands") or []
        if parts[1] == "more":
            row = [IKB(str(k), "trl:pick:%d:%d" % (pos, k)) for k in range(4, len(cands) + 1)]
            opts = ["**%d** — %s" % (k, (cands[k - 1].get("so") or "")[:48]) for k in range(4, len(cands) + 1)]
            await cq.answer()
            await _deps["app"].send_voice(uid, str(st["jobdir"] / ("ask_%02d_p2.ogg" % i)),
                                          caption=("🎧 Line %d of %d — Somali 4, 5, 6\n" %
                                                   (i + 1, len(st["job"]["cues"]))) + "\n".join(opts),
                                          reply_markup=IKM([row, [IKB("✖ None", "trl:pick:%d:0" % pos)]]))
            return
        k = int(parts[3])
        if 1 <= k <= len(cands):
            cd = cands[k - 1]
            if cd.get("covered_by") is not None:
                st["choices"][str(i)] = "cov:%d" % cd["covered_by"]
            else:
                st["choices"][str(i)] = [cd["film_t"], cd["film_t1"]]
        else:
            k = 0
            st["choices"][str(i)] = 0
        json.dump(st["choices"], open(st["jobdir"] / "choices.json", "w"))
        st["pos"] += 1
        await cq.answer("✅ %s" % ("Somali %d" % k if k else "none — stays original"))
        try:
            await cq.message.edit_caption((cq.message.caption or "") + "\n\n➡️ %s" %
                                          ("Somali %d" % k if k else "none"))
        except Exception:
            pass
        await _question(uid)
    finally:
        cq.stop_propagation()


async def _finish(uid: int) -> None:
    st = _ask.pop(uid, None)
    if not st:
        return
    app = _deps["app"]
    jd = st["jobdir"]
    msg = await app.send_message(uid, "🎬 Building your Somali trailer…")
    out = str(jd / "somali_trailer.mp4")
    proc = await asyncio.create_subprocess_exec(*ENGINE, "finish", "--job", str(jd), "--out", out,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    raw, _ = await proc.communicate()
    txt = raw.decode("utf-8", "replace")
    m = re.search(r"FINISHED placed=(\d+) lines=(\d+)", txt)
    if proc.returncode != 0 or not m or not os.path.exists(out):
        tail = " › ".join(txt.strip().splitlines()[-3:])[:400]
        return await msg.edit("❌ Building failed: " + tail)
    cues = st["job"]["cues"]
    auto = sum(1 for c in cues if c.get("auto"))
    picked = sum(1 for v in st["choices"].values() if v)
    await msg.edit("✅ Done — sending…")
    how = "best answers" if st.get("mode") == "auto" else "you picked"
    await app.send_video(uid, out, supports_streaming=True, caption=(
        "🎬 **Somali trailer**\nSomali on **%d of the trailer's %d lines** — %d proven automatically, "
        "%d %s; %d stay original.\nPicture identical to the official trailer." %
        (auto + picked, len(cues), auto, picked, how, len(cues) - auto - picked)))
