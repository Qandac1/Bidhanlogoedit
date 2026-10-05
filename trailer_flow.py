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
import math
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
_procs: dict[int, object] = {}  # uid -> the running engine `prepare` (❌ Cancel stops it)
_cancelled: set[int] = set()
_fast: dict[int, dict] = {}     # uid -> the intake of a fast-way job that ended early (for "the long way with these files")

# Typical stage lengths, measured on the Jigarthanda e2e job (cached film transcript):
# shots 2m35s, placing 2m31s, clips 36s, best answers 6s, building 1m54s.  The film
# transcript (first trailer of a film only): ~12 min voice + ~7 min words per film hour.
EXPECT = {"shots": 160, "lines": 300, "place": 150, "clips": 40, "best": 15, "build": 120, "send": 30}
TEXT_S_PER_FILM_S = 19 * 60 / 3600
PART_A = 12 / 19                 # share of the transcript stage that is voice separation


def _bar(pct: float, width: int = 12) -> str:
    """Same look as the /dub panel: ▰▰▰▰▱▱▱▱  42%"""
    pct = max(0.0, min(100.0, pct))
    n = int(round(pct / 100 * width))
    return "▰" * n + "▱" * (width - n) + "  %3.0f%%" % pct


def _clock(s: float) -> str:
    s = int(s)
    return "%dm %02ds" % (s // 60, s % 60) if s >= 60 else "%ds" % s


class _Panel:
    """A /trailer job in ONE live message, the /dub panel's look: checklist (✅ done,
    ⏳ running with its own bar, ⬜ to come), overall bar, elapsed + time left.

    Bars move on REAL progress where there is some (downloads, film transcript chunks,
    best answers, upload).  A stage without its own numbers creeps along its typical
    length and stops at 90 % until the engine says it is done -- never shows finished
    when it isn't.  Re-drawn every 15 s so a long stage never looks frozen."""

    def __init__(self, msg, title: str, stages: list, cancel: bool = True):
        self.msg, self.title, self.cancel = msg, title, cancel
        self.stages = list(stages)                     # [(key, label, expected s)]
        self.exp = {k: float(e) for k, _, e in stages}
        self.pct = {k: 0.0 for k, _, _ in stages}
        self.note = {k: "" for k, _, _ in stages}
        self.t0: dict[str, float] = {}
        self.measured: set[str] = set()
        self.optional: set[str] = set()                # shown only once started
        self.active = ""
        self.started = time.time()
        self.shown = 0.0
        self._last, self._last_edit, self._hb = "", 0.0, None
        self.closed = False

    # ── state ───────────────────────────────────────────────────────────
    def begin(self, key: str, note: str = "") -> None:
        """A new stage starts; the one running before it is finished."""
        if self.active and self.active != key:
            self.pct[self.active] = 100.0
        if key != self.active:
            self.t0[key] = time.time()
        self.active = key
        if note:
            self.note[key] = note

    def done(self, key: str, note: str = "") -> None:
        self.pct[key] = 100.0
        self.t0.setdefault(key, time.time())
        self.note[key] = note                          # a finished stage drops its live numbers
        if self.active == key:
            self.active = ""

    async def set(self, key: str, pct: float, note: str = "", force: bool = False) -> None:
        """Real progress (also the signature bot.py's download helper calls)."""
        if key != self.active and self.pct.get(key, 0) < 100:
            self.begin(key)
        self.measured.add(key)
        self.pct[key] = max(self.pct[key], max(0.0, min(100.0, pct)))
        if note:
            self.note[key] = note
        await self.draw(force)

    def _frac(self, key: str) -> float:
        if self.pct[key] >= 100:
            return 1.0
        if key == self.active and key not in self.measured:
            return min(0.9, (time.time() - self.t0[key]) / max(self.exp[key], 1))
        return self.pct[key] / 100

    def _visible(self):
        return [s for s in self.stages if s[0] not in self.optional or s[0] in self.t0]

    def overall(self) -> float:
        vis = self._visible()
        tot = sum(self.exp[k] for k, _, _ in vis) or 1
        self.shown = max(self.shown, 100 * sum(self.exp[k] * self._frac(k) for k, _, _ in vis) / tot)
        return self.shown

    def left(self) -> str:
        secs = 0.0
        for k, _, _ in self._visible():
            f = self._frac(k)
            if f >= 1:
                continue
            if k == self.active:
                el = time.time() - self.t0[k]
                if k in self.measured and f > 0.05:
                    secs += el * (1 - f) / f
                else:
                    secs += max(self.exp[k] - el, 20)
            else:
                secs += self.exp[k]
        if secs == 0 and not self.active:
            return "finished"
        return "~%d min left" % max(1, round(secs / 60)) if secs >= 90 else "almost done"

    # ── drawing ─────────────────────────────────────────────────────────
    def render(self) -> str:
        rows = []
        for k, label, _ in self._visible():
            extra = ("  · " + self.note[k]) if self.note[k] else ""
            if self.pct[k] >= 100:
                rows.append("✅ %s%s" % (label, extra))
            elif k == self.active:
                rows.append("⏳ **%s**%s\n`%s`" % (label, extra, _bar(100 * self._frac(k))))
            else:
                rows.append("⬜ %s" % label)
        return ("🎬 **Somali trailer** · `%s`\n\n%s\n\n**Overall** `%s`\n⏱ %s · %s"
                % (self.title[:40], "\n".join(rows), _bar(self.overall()),
                   _clock(time.time() - self.started), self.left()))

    async def draw(self, force: bool = False) -> None:
        if self.closed or (not force and time.time() - self._last_edit < 4):
            return
        txt = self.render()
        if txt == self._last:
            return
        self._last, self._last_edit = txt, time.time()
        try:
            await self.msg.edit(txt, reply_markup=_kb_cancel() if self.cancel else None)
        except Exception:
            pass

    def start(self) -> None:
        async def beat():
            while not self.closed:
                await asyncio.sleep(15)
                await self.draw(force=True)
        self._hb = asyncio.get_event_loop().create_task(beat())

    def close(self) -> None:
        self.closed = True
        if self._hb and not self._hb.done():
            self._hb.cancel()


def _load_subs_mod():
    """The engine's subtitle reader, loaded by file path (stdlib only) so the bot's own
    module names can't clash with the engine's."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("trl_subs", "/opt/dubsync2/trailerdub/subs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _srt_is_english(m) -> tuple[bool, str]:
    """(english?, what it looks like) for a .srt message; unreadable counts as English
    so the engine (which checks again) decides."""
    try:
        p = str(JOBS / ("intake_%d_%d.srt" % (m.from_user.id, m.id)))
        await m.download(file_name=p)
        subs = _load_subs_mod()
        cues = subs.load_srt(p)
        os.remove(p)
        tag = re.search(r"\[([^\]]*auto-generated[^\]]*)\]", (m.document.file_name or ""), re.I)
        return subs.is_english(cues), (tag.group(1) if tag else "not English")
    except Exception:
        log.exception("srt language check")
        return True, ""


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
    _intake[uid] = {"step": "trailer", "trailer": None, "film": None, "orig": None, "subs": None, "movie_subs": None}
    _fast.pop(uid, None)
    _intake[uid]["prompt"] = await m.reply(
        "🎬 **Somali trailer**\n\n**1/4** Send the official **trailer** (video).",
        reply_markup=_kb_cancel())
    m.stop_propagation()


MOVIE_SUBS_ASK = ("🎬 **Somali trailer**\n\n✅ Trailer received\n✅ Somali film received\n%s\n"
                  "**4/4** Send the **MOVIE's English subtitles** (.srt — the whole film, from subdl.com "
                  "or opensubtitles.org). With them most lines are placed automatically. Or tap **Skip**.")


ORIG_ASK = ("🎬 **Somali trailer**\n\n✅ Trailer received\n✅ Somali film received\n"
            "⚡ **Fast way (optional):** send the **same film with the trailer's own language** — the HD master "
            "with its original sound. The bot then finds the lines by their **sound**, and by their **words** when "
            "that file has English subtitles inside: no questions, about 10 minutes. Best with the trailer in the "
            "film's **original** language.\n"
            "Or tap **Skip** for the long way (subtitles + your taps).")
SUBS_ASK = ("🎬 **Somali trailer**\n\n✅ Trailer received\n✅ Somali film received\n"
            "**3/4** Send the **trailer's** English subtitles (.srt) if you have them "
            "(exact timing and words), or tap **No subtitles**.")
SUBS_ASK_FAST = ("🎬 **Somali trailer**\n\n✅ Trailer received\n✅ Somali film received\n✅ Film with its own sound received\n"
                 "Last: the **trailer's English** subtitles (.srt) if you have them — exact words and timing find "
                 "more lines. Or tap **No subtitles** (the bot listens to the trailer itself).")
FAST_STAGES = [("dl_trailer", "Download trailer", 20), ("dl_film", "Download Somali film", 120),
               ("dl_orig", "Download the film with its own sound", 180),
               ("sound", "Find every line (by sound, then by words)", 900),
               ("build", "Build the Somali trailer", 150), ("send", "Send it to you", EXPECT["send"])]
FAST_MIN_LINES, FAST_MIN_SHARE = 3, 0.25     # fewer lines proven (sound + words) than this: the fast way is not for this pair


def _is_video(m) -> bool:
    if m.video:
        return True
    d = m.document
    return bool(d and ((d.mime_type or "").startswith("video") or
                       re.search(r"\.(mp4|mkv|mov|avi|webm|ts)$", d.file_name or "", re.I)))


def _is_subs(m) -> bool:
    d = m.document
    return bool(d and re.search(r"\.(srt|vtt)$", d.file_name or "", re.I))


async def _show(st: dict, m, text: str, kb) -> None:
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
        await _show(st, m, "🎬 **Somali trailer**\n\n✅ Trailer received\n"
                           "**2/4** Now send the **Somali film** (the full dubbed movie).", _kb_cancel())
    elif st["step"] == "film" and _is_video(m):
        st["film"], st["step"] = m, "orig"
        await _show(st, m, ORIG_ASK, _kb_cancel([IKB("⏭ Skip", "trl:noorig")]))
    elif st["step"] == "orig" and _is_video(m):                 # the fast way
        st["orig"], st["step"] = m, "subs"
        await _show(st, m, SUBS_ASK_FAST, _kb_cancel([IKB("⏭ No subtitles", "trl:nosubs")]))
    elif st["step"] == "orig" and _is_subs(m):
        # subtitles sent straight away = no film with its own sound: the long way, as before (this file is the
        # trailer's subtitles)
        st["step"] = "subs"
        return await _take_step(_, m)
    elif st["step"] == "subs" and st.get("orig") is not None and _is_subs(m):
        st["subs"] = m                                          # English: words + times; any other language: the engine decides
        _start(uid)
    elif st["step"] == "subs" and _is_subs(m):
        # lines are matched to the MOVIE's English subtitles by their words: YouTube
        # auto-captions in the trailer's language can't be -> listen to the trailer instead
        en, what = await _srt_is_english(m)
        st["subs"], st["step"] = (m if en else None), "movie_subs"
        got = ("✅ Trailer subtitles received" if en else
               "⚠️ Trailer subtitles are **%s**, not English — the bot will **listen to the "
               "trailer** instead (about 5 min more). Official English ones are better if you have them." % what)
        await _show(st, m, MOVIE_SUBS_ASK % got, _kb_cancel([IKB("⏭ Skip", "trl:nomovie")]))
    elif st["step"] == "movie_subs" and _is_subs(m):
        en, what = await _srt_is_english(m)
        if not en:
            await m.reply("⚠️ These movie subtitles are **%s**, not English — they can't be matched. "
                          "Send the film's **English** .srt, or tap **Skip**." % what)
            return m.stop_propagation()
        st["movie_subs"] = m
        _start(uid)
    else:
        await m.reply("Waiting for the %s. /cancel or ❌ to stop." %
                      {"trailer": "trailer video", "film": "Somali film video",
                       "orig": "film with the trailer's own language (video) or the Skip button",
                       "subs": "trailer subtitles (.srt) or the No subtitles button",
                       "movie_subs": "movie subtitles (.srt) or the Skip button"}[st["step"]])
    m.stop_propagation()


def _start(uid: int) -> None:
    st = _intake.pop(uid)
    asyncio.get_event_loop().create_task(_run_fast(uid, st) if st.get("orig") is not None else _run(uid, st))


def _mmss_fast(t: float) -> str:
    t = int(t)
    return "%d:%02d" % (t // 60, t % 60)


def fast_caption(rep: dict) -> str:
    """The message under a fast-way trailer, from the build's report."""
    lines = rep.get("lines") or []
    placed = [ln for ln in lines if ln.get("status") == "placed"]
    left = [ln for ln in lines if ln.get("status") != "placed"]
    by_text = sum(1 for ln in placed if str(ln.get("why", "")).startswith("text"))
    by_sound = sum(1 for ln in placed if str(ln.get("why", "")).startswith("sound"))
    how = []
    if by_sound:
        how.append("%d by their sound" % by_sound)
    if by_text:
        how.append("%d by their words" % by_text)
    if len(placed) - by_sound - by_text:
        how.append("%d by the picture" % (len(placed) - by_sound - by_text))
    txt = ("🎬 **Somali trailer** — the fast way\nSomali on **%d of the trailer's %d lines**%s. No questions asked."
           % (len(placed), len(lines), (" (" + ", ".join(how) + ")") if how else ""))
    if left:
        txt += "\nStill original (%d): %s." % (len(left), ", ".join(_mmss_fast(ln["t0"]) for ln in left[:12])
                                                + (" …" if len(left) > 12 else ""))
    return txt + "\nPicture identical to the official trailer."


async def _run_fast(uid: int, st: dict) -> None:
    """Trailer + Somali film + the film with the trailer's own language -> the Somali trailer, no questions."""
    status = st["prompt"]
    jobdir = JOBS / ("%d_%d" % (uid, int(time.time())))
    jobdir.mkdir(parents=True, exist_ok=True)
    _cancelled.discard(uid)
    _fast.pop(uid, None)
    p = _Panel(status, _title(st["trailer"]), FAST_STAGES)

    async def say(txt, kb=None):
        p.close()
        try:
            await status.edit("🎬 **Somali trailer**\n\n" + txt, reply_markup=kb or _kb_cancel())
        except Exception:
            pass

    async def long_way(why):
        _fast[uid] = {k: st.get(k) for k in ("trailer", "film", "subs", "prompt")}
        await say("⚠️ %s\n\nThe fast way needs the trailer's own voices inside the film file (or English subtitles "
                  "inside it). Use the trailer in the film's **original** language with a film file that has that "
                  "sound — or go the long way (subtitles + your taps) with the files you sent." % why,
                  IKM([[IKB("🔁 The long way with these files", "trl:long")], [IKB("❌ Cancel", "trl:cancel")]]))
    try:
        if _deps["busy"]():
            try:
                await status.edit("🎬 **Somali trailer**\n\n⏳ Waiting for the film that is running now to "
                                  "finish — your films go first.", reply_markup=_kb_cancel())
            except Exception:
                pass
            while _deps["busy"]():
                await asyncio.sleep(30)
                if uid in _cancelled:
                    return
        p.start()
        got = {}
        for key, name in (("dl_trailer", "trailer"), ("dl_film", "film"), ("dl_orig", "orig")):
            m = st[name]
            p.exp[key] = max(10, (getattr(m.video or m.document, "file_size", 0) or 0) / 12e6)
            p.begin(key)
            got[name] = await _deps["build_job"](uid, m, status, prog=p, key=key)
            p.done(key)
            if uid in _cancelled:
                return p.close()
        out = str(jobdir / "somali_trailer.mp4")
        cmd = [ENGINE[0], "-u", ENGINE[1], "build", "--trailer", got["trailer"]["src"], "--film", got["film"]["src"],
               "--orig", got["orig"]["src"], "--out", out, "--report", str(jobdir / "report.json")]
        if st.get("subs") is not None:
            sp = str(jobdir / "subs.srt")
            await st["subs"].download(file_name=sp)
            cmd += ["--subs", sp]
        p.begin("sound")
        await p.draw(force=True)
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        _procs[uid] = proc
        t0, tail, stop = time.time(), [], None
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=60)
            except asyncio.TimeoutError:
                if time.time() - t0 > HARD_CAP_S:
                    proc.kill()
                    raise RuntimeError("the build took longer than 4 hours — stopped")
                continue
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            tail = (tail + [line])[-6:]
            m = re.match(r"sound chain: (\d+) of (\d+) lines proven", line)
            if line.startswith("REFUSED"):
                stop = ("refused", line.split(":", 1)[-1].strip())
            elif "no sound track of this film carries" in line or line.startswith("sound chain skipped"):
                stop = ("long", "The trailer's lines could **not be found in that film file** — neither by their "
                                "sound nor by their words.")
            elif m:
                n, tot = int(m.group(1)), int(m.group(2))
                if n < FAST_MIN_LINES or n < FAST_MIN_SHARE * tot:
                    stop = ("long", "Only **%d of %d** lines could be found in that film file." % (n, tot))
                else:
                    p.done("sound", "%d of %d lines found" % (n, tot))
                    p.begin("build")
                    await p.draw(force=True)
            elif line.startswith("[sound] film track"):
                p.note["sound"] = line[8:].split(":", 1)[0].strip() + " listened to"
            elif line.startswith("listening to the trailer") or line.startswith("the trailer subtitles are not English"):
                p.note["sound"] = "listening to the trailer's lines"
                await p.draw(force=True)
            elif line.startswith("[text] ") and "placed by what is said" in line:
                p.note["sound"] = line[7:].split(" (", 1)[0]
                await p.draw(force=True)
            if stop:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                break
        rc = await proc.wait()
        _procs.pop(uid, None)
        if uid in _cancelled:
            return p.close()
        if stop and stop[0] == "refused":
            return await say("⛔ " + stop[1])
        if stop:
            return await long_way(stop[1])
        if rc != 0 or not os.path.exists(out):
            raise RuntimeError("building failed: " + " › ".join(tail[-3:])[:400])
        p.done("build")
        p.exp["send"] = max(10, os.path.getsize(out) / 2e6)
        p.begin("send")
        await p.draw(force=True)
        try:
            rep = json.load(open(jobdir / "report.json"))
        except Exception:
            rep = {}

        async def up(cur, tot):
            if tot:
                await p.set("send", 100 * cur / tot, "%.0f / %.0f MB" % (cur / 1e6, tot / 1e6))
        await _deps["app"].send_video(uid, out, supports_streaming=True, progress=up, caption=fast_caption(rep))
        p.done("send")
        await p.draw(force=True)
        p.close()
    except Exception as exc:
        log.exception("trailer fast job failed")
        _procs.pop(uid, None)
        await say("❌ %s" % exc)


def _title(m) -> str:
    v = m.video or m.document
    name = getattr(v, "file_name", None) or (m.caption or "").split("\n")[0] or "trailer"
    return re.sub(r"\.(mp4|mkv|mov|avi|webm|ts)$", "", name, flags=re.I)


FINISH_STAGES = [("best", "Best Somali line for each question", EXPECT["best"]),
                 ("build", "Build the Somali trailer", EXPECT["build"]),
                 ("send", "Send it to you", EXPECT["send"])]
PREP_STAGES = [("dl_trailer", "Download trailer", 20), ("dl_film", "Download Somali film", 120),
               ("shots", "Find the trailer's shots in the film", EXPECT["shots"]),
               ("lines", "Listen to the trailer's lines", EXPECT["lines"]),
               ("text", "Somali transcript of the film", 60),
               ("place", "Place the proven lines", EXPECT["place"]),
               ("clips", "Listening clips", EXPECT["clips"])]
STEP_STAGE = (("Finding the trailer's shots", "shots"), ("The trailer subtitles are not English", "lines"),
              ("Listening to the trailer", "lines"), ("Somali transcript of the film", "text"),
              ("Placing the lines", "place"), ("Making the listening clips", "clips"))


async def _prep_line(p: _Panel, line: str, dur: float) -> None:
    """One line of the engine's `prepare` output -> the panel."""
    step = line[5:] if line.startswith("STEP ") else ""
    stage = next((k for pre, k in STEP_STAGE if step.startswith(pre)), None)
    if line.startswith("FILM cached="):
        p.exp["text"] = 20 if line.endswith("1") else max(dur, 600) * TEXT_S_PER_FILM_S
    elif stage:
        p.begin(stage, "subtitles not English" if step.startswith("The trailer subtitles") else "")
        await p.draw(force=True)
    elif step.startswith("trailer language:"):
        p.note["lines"] = "language: " + step.split(":", 1)[1].strip()
    elif step.startswith("film transcript: cached"):
        await p.set("text", 100, "already made for this film", force=True)
    elif step.startswith("film transcript: separating"):
        p.note["text"] = "first time for this film · part 1/2 Somali voice"
    elif step.startswith("film transcript: Somali text"):
        await p.set("text", 100 * PART_A, "first time for this film · part 2/2 Somali words")
    else:
        a = re.match(r"chunk \d+ \(\d+-(\d+) s\)", line)                  # part A: film seconds done
        b = re.match(r"(?:STEP )?transcript chunk (\d+):", line)          # part B: chunk index
        if a and dur:
            await p.set("text", 100 * PART_A * min(1.0, int(a.group(1)) / dur))
        elif b and dur:
            await p.set("text", 100 * (PART_A + (1 - PART_A) * min(1.0, (int(b.group(1)) + 1) / math.ceil(dur / 600))))


async def _run(uid: int, st: dict) -> None:
    status = st["prompt"]
    jobdir = JOBS / ("%d_%d" % (uid, int(time.time())))
    jobdir.mkdir(parents=True, exist_ok=True)
    _cancelled.discard(uid)
    p = _Panel(status, _title(st["trailer"]), PREP_STAGES)
    p.optional.add("lines")

    async def say(txt):
        p.close()
        try:
            await status.edit("🎬 **Somali trailer**\n\n" + txt, reply_markup=_kb_cancel())
        except Exception:
            pass
    try:
        if _deps["busy"]():
            try:
                await status.edit("🎬 **Somali trailer**\n\n⏳ Waiting for the film that is running now to "
                                  "finish — your films go first.", reply_markup=_kb_cancel())
            except Exception:
                pass
            while _deps["busy"]():
                await asyncio.sleep(30)
                if uid in _cancelled:
                    return
        p.start()
        p.exp["dl_trailer"] = max(10, (getattr(st["trailer"].video or st["trailer"].document, "file_size", 0) or 0) / 12e6)
        p.exp["dl_film"] = max(20, (getattr(st["film"].video or st["film"].document, "file_size", 0) or 0) / 12e6)
        p.begin("dl_trailer")
        tj = await _deps["build_job"](uid, st["trailer"], status, prog=p, key="dl_trailer")
        p.done("dl_trailer")
        p.begin("dl_film")
        fj = await _deps["build_job"](uid, st["film"], status, prog=p, key="dl_film")
        dur = float(fj.get("duration") or 0)
        p.done("dl_film", "%d min film" % (dur // 60) if dur else "")
        p.exp["text"] = max(dur, 600) * TEXT_S_PER_FILM_S        # until the engine says it is cached
        if uid in _cancelled:
            return p.close()
        cmd = [*ENGINE, "prepare", "--trailer", tj["src"], "--film", fj["src"], "--job", str(jobdir)]
        if st.get("subs"):
            sp = str(jobdir / "subs.srt")
            await st["subs"].download(file_name=sp)
            cmd += ["--subs", sp]
        else:
            p.optional.discard("lines")                           # no subtitles: listening is a stage
        if st.get("movie_subs"):
            mp = str(jobdir / "movie.srt")
            await st["movie_subs"].download(file_name=mp)
            cmd += ["--movie-subs", mp]
        p.begin("shots")
        await p.draw(force=True)
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        _procs[uid] = proc
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
            if line.startswith(("PREPARED", "REFUSED")):
                result = line
            else:
                await _prep_line(p, line, dur)
        rc = await proc.wait()
        _procs.pop(uid, None)
        if uid in _cancelled:
            return p.close()
        if result and result.startswith("REFUSED"):
            return await say("⛔ " + result[8:])
        if rc != 0 or not result:
            raise RuntimeError("prepare failed: " + " › ".join(tail[-3:])[:400])
        p.close()
        job = json.load(open(jobdir / "job.json"))
        qs = [c["i"] for c in job["cues"] if not c.get("auto")]
        auto = sum(1 for c in job["cues"] if c.get("auto"))
        _ask[uid] = {"jobdir": jobdir, "job": job, "qs": qs, "pos": 0, "choices": {}, "status": status,
                     "title": p.title}
        if not qs:
            return await _finish(uid)
        try:
            await status.edit(
                "🎬 **Somali trailer**\n\n✅ **%d** of %d lines placed automatically (proven).\n"
                "**%d** lines left. Choose:\n"
                "⚡ **Best answers** — the bot takes every Somali line it can **prove** (movie subtitles, "
                "conversation order); a line it can't prove stays original\n"
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
    """⚡ Best answers, by the engine (`trailer_dub.py best`): every question in trailer
    order, each re-built with the answers so far, taking the first answer that rests on
    PROOF (movie subtitles, or conversation order between proven lines); lines without a
    proven answer stay original.  On Jigarthanda identical to the approved Test 4 (20/20);
    on Agent 2023 (0 proven lines) the old "#1 every time" chained guesses into wrong lines."""
    st = _ask.get(uid)
    if not st:
        return
    jd, status = st["jobdir"], st["status"]
    p = _Panel(status, st.get("title", "trailer"), FINISH_STAGES, cancel=False)
    p.start()
    p.begin("best")
    try:
        proc = await asyncio.create_subprocess_exec(*ENGINE, "best", "--job", str(jd), stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        tail, done = [], None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            tail = (tail + [line])[-4:]
            mm = re.match(r"BEST (\d+)/(\d+)", line)
            if mm:
                await p.set("best", 100 * int(mm.group(1)) / max(int(mm.group(2)), 1))
            elif line.startswith("BEST_DONE"):
                done = line
        if await proc.wait() != 0 or not done:
            raise RuntimeError("best answers failed: " + " › ".join(tail)[:300])
        st["choices"] = json.load(open(jd / "choices.json"))
    except Exception as exc:
        p.close()
        log.exception("best answers failed")
        try:
            await status.edit("🎬 **Somali trailer**\n\n❌ %s" % exc)
        except Exception:
            pass
        return
    ans = re.search(r"answered=(\d+) of (\d+)", done)
    p.done("best", "%s of %s lines proven" % ans.groups() if ans else "")
    st["pos"] = len(st["qs"])
    await _finish(uid, p)


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
            _cancelled.add(uid)
            proc = _procs.pop(uid, None)
            if proc is not None and proc.returncode is None:
                proc.kill()                                  # a running prepare stops too
            await cq.answer("Cancelled")
            try:
                await cq.message.edit("🎬 Somali trailer — cancelled.")
            except Exception:
                pass
            return
        if data == "trl:noorig":
            if uid in _intake and _intake[uid]["step"] == "orig":
                await cq.answer("The long way: subtitles + your taps")
                _intake[uid]["step"] = "subs"
                try:
                    await _intake[uid]["prompt"].edit(SUBS_ASK, reply_markup=_kb_cancel([IKB("⏭ No subtitles", "trl:nosubs")]))
                except Exception:
                    pass
            else:
                await cq.answer()
            return
        if data == "trl:long":
            st0 = _fast.pop(uid, None)
            if st0 and uid not in _intake:
                await cq.answer("The long way with the files you sent")
                st0.update(orig=None, movie_subs=None)
                asyncio.get_event_loop().create_task(_run(uid, st0))
            else:
                await cq.answer("This trailer job has ended.", show_alert=True)
            return
        if data == "trl:nosubs" and uid in _intake and _intake[uid]["step"] == "subs" and _intake[uid].get("orig") is not None:
            await cq.answer("No subtitles — the bot finds the lines itself")
            _start(uid)
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


async def _finish(uid: int, p: _Panel | None = None) -> None:
    st = _ask.pop(uid, None)
    if not st:
        if p is not None:
            p.close()
        return
    app = _deps["app"]
    jd = st["jobdir"]
    if p is None:                                 # after the questions: a fresh panel message
        msg = await app.send_message(uid, "🎬 Building your Somali trailer…")
        p = _Panel(msg, st.get("title", "trailer"), [s for s in FINISH_STAGES if s[0] != "best"], cancel=False)
        p.start()
    p.begin("build")
    await p.draw(force=True)
    out = str(jd / "somali_trailer.mp4")
    try:
        proc = await asyncio.create_subprocess_exec(*ENGINE, "finish", "--job", str(jd), "--out", out,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        raw, _ = await proc.communicate()
        txt = raw.decode("utf-8", "replace")
        m = re.search(r"FINISHED placed=(\d+) lines=(\d+)", txt)
        if proc.returncode != 0 or not m or not os.path.exists(out):
            p.close()
            tail = " › ".join(txt.strip().splitlines()[-3:])[:400]
            return await p.msg.edit("🎬 **Somali trailer**\n\n❌ Building failed: " + tail)
        cues = st["job"]["cues"]
        auto = sum(1 for c in cues if c.get("auto"))
        picked = sum(1 for v in st["choices"].values() if v)
        p.done("build")
        p.exp["send"] = max(10, os.path.getsize(out) / 2e6)
        p.begin("send")
        await p.draw(force=True)
        how = "best answers (proven)" if st.get("mode") == "auto" else "you picked"
        left = len(cues) - auto - picked
        hint = ("\nThe %d original lines: send /trailer again and choose 🎧 to pick them by ear "
                "(this film's transcript is saved, so it's quick)." % left
                if left and st.get("mode") == "auto" else "")

        async def up(cur, tot):
            if tot:
                await p.set("send", 100 * cur / tot, "%.0f / %.0f MB" % (cur / 1e6, tot / 1e6))
        await app.send_video(uid, out, supports_streaming=True, progress=up, caption=(
            "🎬 **Somali trailer**\nSomali on **%d of the trailer's %d lines** — %d proven automatically, "
            "%d %s; %d stay original.\nPicture identical to the official trailer.%s" %
            (auto + picked, len(cues), auto, picked, how, left, hint)))
        p.done("send")
        await p.draw(force=True)
    except Exception as exc:
        log.exception("trailer finish failed")
        p.close()
        try:
            await p.msg.edit("🎬 **Somali trailer**\n\n❌ %s" % exc)
        except Exception:
            pass
    finally:
        p.close()
