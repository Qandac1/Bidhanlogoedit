"""bot33: /trailer -- THE FAST WAY: with the film in the trailer's own language the lines are found by their SOUND.

Measured 2026-10-05 on Jigarthanda (engine: trailerdub/soundleg.py, build --orig): 38 of 41 lines Somali with no
subtitles of the film, no transcript (the long way's first hour) and no questions; the picture bit-identical.
Works when the trailer's language is one of that film file's sound tracks (the trailer in the film's ORIGINAL
language); a trailer dubbed separately (Ghost's Hindi trailer) has no line to find -- the bot says so and offers the
long way with the same files.
Since 2026-10-05 15:00 the engine also finds lines by WHAT IS SAID when that film file carries English subtitles
(trailerdub/textleg.py; Agent 2023: 10 -> 19 of 32 lines, most of its trailer lines are another recording than the
film's): the texts say "sound and words", the caption counts both, and the engine listens to the trailer itself
when no English trailer subtitles are given.

trailer_flow.py:
  intake    after the Somali film ONE optional step: "send the film with the trailer's own language, or Skip".
            Skip (or subtitles sent straight away) = the flow of before, step for step.
  _run_fast downloads the three files, runs  trailer_dub.py build --orig  with a live panel, sends the trailer with
            a plain count (which lines stayed original, by their time).  No sound track with the trailer's voices,
            or too few lines found -> stopped early, "the long way with these files" button.
  the long way (_run, _question, _finish) is untouched.
Usage: python patch_bot_trailerfast33.py <bot dir>     (patches <bot dir>/trailer_flow.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "trailer_flow.py"
s = P.read_text()
if "_run_fast" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''_cancelled: set[int] = set()
''', '''_cancelled: set[int] = set()
_fast: dict[int, dict] = {}     # uid -> the intake of a fast-way job that ended early (for "the long way with these files")
''', "state for the fall-back")

rep('''def _is_video(m) -> bool:
''', '''ORIG_ASK = ("🎬 **Somali trailer**\\n\\n✅ Trailer received\\n✅ Somali film received\\n"
            "⚡ **Fast way (optional):** send the **same film with the trailer's own language** — the HD master "
            "with its original sound. The bot then finds the lines by their **sound**, and by their **words** when "
            "that file has English subtitles inside: no questions, about 10 minutes. Best with the trailer in the "
            "film's **original** language.\\n"
            "Or tap **Skip** for the long way (subtitles + your taps).")
SUBS_ASK = ("🎬 **Somali trailer**\\n\\n✅ Trailer received\\n✅ Somali film received\\n"
            "**3/4** Send the **trailer's** English subtitles (.srt) if you have them "
            "(exact timing and words), or tap **No subtitles**.")
SUBS_ASK_FAST = ("🎬 **Somali trailer**\\n\\n✅ Trailer received\\n✅ Somali film received\\n✅ Film with its own sound received\\n"
                 "Last: the **trailer's English** subtitles (.srt) if you have them — exact words and timing find "
                 "more lines. Or tap **No subtitles** (the bot listens to the trailer itself).")
FAST_STAGES = [("dl_trailer", "Download trailer", 20), ("dl_film", "Download Somali film", 120),
               ("dl_orig", "Download the film with its own sound", 180),
               ("sound", "Find every line (by sound, then by words)", 420),
               ("build", "Build the Somali trailer", 150), ("send", "Send it to you", EXPECT["send"])]
FAST_MIN_LINES, FAST_MIN_SHARE = 3, 0.25     # fewer lines proven (sound + words) than this: the fast way is not for this pair


def _is_video(m) -> bool:
''', "texts and stages of the fast way")

rep('''    elif st["step"] == "film" and _is_video(m):
        st["film"], st["step"] = m, "subs"
        await st["prompt"].edit(
            "🎬 **Somali trailer**\\n\\n✅ Trailer received\\n✅ Somali film received\\n"
            "**3/4** Send the **trailer's** English subtitles (.srt) if you have them "
            "(exact timing and words), or tap **No subtitles**.",
            reply_markup=_kb_cancel([IKB("⏭ No subtitles", "trl:nosubs")]))
    elif st["step"] == "subs" and _is_subs(m):
''', '''    elif st["step"] == "film" and _is_video(m):
        st["film"], st["step"] = m, "orig"
        await st["prompt"].edit(ORIG_ASK, reply_markup=_kb_cancel([IKB("⏭ Skip", "trl:noorig")]))
    elif st["step"] == "orig" and _is_video(m):                 # the fast way
        st["orig"], st["step"] = m, "subs"
        await st["prompt"].edit(SUBS_ASK_FAST, reply_markup=_kb_cancel([IKB("⏭ No subtitles", "trl:nosubs")]))
    elif st["step"] == "orig" and _is_subs(m):
        # subtitles sent straight away = no film with its own sound: the long way, as before (this file is the
        # trailer's subtitles)
        st["step"] = "subs"
        return await _take(_, m)
    elif st["step"] == "subs" and st.get("orig") is not None and _is_subs(m):
        st["subs"] = m                                          # English: words + times; any other language: the engine decides
        _start(uid)
    elif st["step"] == "subs" and _is_subs(m):
''', "intake: the optional step")

rep('''                      {"trailer": "trailer video", "film": "Somali film video",
''', '''                      {"trailer": "trailer video", "film": "Somali film video",
                       "orig": "film with the trailer's own language (video) or the Skip button",
''', "intake: what is waited for")

rep('''def _start(uid: int) -> None:
    st = _intake.pop(uid)
    asyncio.get_event_loop().create_task(_run(uid, st))
''', '''def _start(uid: int) -> None:
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
    txt = ("🎬 **Somali trailer** — the fast way\\nSomali on **%d of the trailer's %d lines**%s. No questions asked."
           % (len(placed), len(lines), (" (" + ", ".join(how) + ")") if how else ""))
    if left:
        txt += "\\nStill original (%d): %s." % (len(left), ", ".join(_mmss_fast(ln["t0"]) for ln in left[:12])
                                                + (" …" if len(left) > 12 else ""))
    return txt + "\\nPicture identical to the official trailer."


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
            await status.edit("🎬 **Somali trailer**\\n\\n" + txt, reply_markup=kb or _kb_cancel())
        except Exception:
            pass

    async def long_way(why):
        _fast[uid] = {k: st.get(k) for k in ("trailer", "film", "subs", "prompt")}
        await say("⚠️ %s\\n\\nThe fast way needs the trailer's own voices inside the film file (or English subtitles "
                  "inside it). Use the trailer in the film's **original** language with a film file that has that "
                  "sound — or go the long way (subtitles + your taps) with the files you sent." % why,
                  IKM([[IKB("🔁 The long way with these files", "trl:long")], [IKB("❌ Cancel", "trl:cancel")]]))
    try:
        if _deps["busy"]():
            try:
                await status.edit("🎬 **Somali trailer**\\n\\n⏳ Waiting for the film that is running now to "
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
            m = re.match(r"sound chain: (\\d+) of (\\d+) lines proven", line)
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
''', "_start picks the way; _run_fast")

rep('''        if data == "trl:nosubs":
            if uid in _intake and _intake[uid]["step"] == "subs":
''', '''        if data == "trl:noorig":
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
''', "buttons: Skip, the long way, No subtitles on the fast way")

rep('''    _intake[uid] = {"step": "trailer", "trailer": None, "film": None, "subs": None, "movie_subs": None}
''', '''    _intake[uid] = {"step": "trailer", "trailer": None, "film": None, "orig": None, "subs": None, "movie_subs": None}
    _fast.pop(uid, None)
''', "intake: the new field")

P.write_text(s)
print("patched %s" % P)
