"""bot35: /trailer -- WHEN THE SOMALI TRAILER ALREADY EXISTS, ITS REAL SOUND IS THE RESULT.

John 2026-10-05, after the trailers built from the film: "you were creating your own fake ... I sent you the Agent
Somali trailer that has already been created". Measured: the channel voiced that trailer separately; none of its 24
spoken pieces is in the Somali film, so no build from the film can say those words. The engine can put that real
sound onto the clean official picture (trailer_dub.py swap). The bot now decides by itself which job it has:

trailer_flow.py:
  intake    step 2 ("send the Somali film") also takes the SOMALI VERSION OF THE TRAILER: a video about as long
            as the trailer (within 20 s or a quarter of its length). No button, no question.
  _run_swap downloads the two, runs `swap` with a live panel, sends the official picture with the Somali trailer's
            own sound and a plain caption. The engine refuses a pair that is not one trailer (other picture, other
            cut, other speed): nothing is sent, the user is told why, and the intake is back at step 2 with the
            trailer kept -- "send the Somali FILM".
  A long second video (the film) is the flow of before, prompt for prompt.
Usage: python patch_bot_trailerswap35.py <bot dir>     (patches <bot dir>/trailer_flow.py in place; needs bot34)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "trailer_flow.py"
s = P.read_text()
if "_run_swap" in s:
    sys.exit("already patched: %s" % P)
assert "_take_step" in s, "bot34 (patch_bot_trailerguard34.py) must be in first"


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''        await _show(st, m, "🎬 **Somali trailer**\\n\\n✅ Trailer received\\n"
                           "**2/4** Now send the **Somali film** (the full dubbed movie).", _kb_cancel())
    elif st["step"] == "film" and _is_video(m):
        st["film"], st["step"] = m, "orig"
''', '''        await _show(st, m, "🎬 **Somali trailer**\\n\\n✅ Trailer received\\n"
                           "**2/4** Now send the **Somali film** (the full dubbed movie).\\n"
                           "If this trailer already exists in Somali, send **that** instead: its real sound goes "
                           "onto the clean picture.", _kb_cancel())
    elif st["step"] == "film" and _is_video(m) and _is_somali_trailer(st["trailer"], m):
        st["somali_trailer"] = m                 # the trailer's own Somali version: its sound is the result
        _start(uid)
    elif st["step"] == "film" and _is_video(m):
        st["film"], st["step"] = m, "orig"
''', "intake: step 2 also takes the trailer's own Somali version")

rep('''def _start(uid: int) -> None:
    st = _intake.pop(uid)
    asyncio.get_event_loop().create_task(_run_fast(uid, st) if st.get("orig") is not None else _run(uid, st))
''', '''SWAP_STAGES = [("dl_trailer", "Download trailer", 20), ("dl_somali", "Download the Somali trailer", 20),
               ("swap", "Put its real sound on the clean picture", 90), ("send", "Send it to you", EXPECT["send"])]
SWAP_NEAR_S, SWAP_NEAR_SHARE = 20.0, 0.25     # "about as long as the trailer": within this many s or this share of it


def _seconds(m) -> float:
    v = m.video or m.document
    return float(getattr(v, "duration", 0) or 0)


def _is_somali_trailer(trailer_msg, m) -> bool:
    """Is this second video the trailer's own Somali version (about as long as the trailer), not the film?
    Only lengths Telegram tells decide; a file without a length is the film, as before."""
    d1, d2 = _seconds(trailer_msg), _seconds(m)
    return d1 > 0 and d2 > 0 and abs(d2 - d1) <= max(SWAP_NEAR_S, SWAP_NEAR_SHARE * d1)


def swap_caption(rep: dict) -> str:
    """The message under a trailer that carries the Somali trailer's own sound, from the engine's report."""
    txt = ("🎬 **Somali trailer** — the Somali trailer's **own sound** on the clean official picture\\n"
           "Sound: the Somali version you sent, every line (moved %+.2f s to sit on the picture). "
           "Picture: the official trailer, untouched." % float(rep.get("offset", 0.0)))
    if float(rep.get("somali_from", 0.0)) > 0.5:
        txt += "\\nThe first %.1f s are the official trailer's own sound: the Somali version starts later." % float(rep["somali_from"])
    return txt


async def _run_swap(uid: int, st: dict) -> None:
    """Official trailer + its own Somali version -> the official picture with the Somali version's sound."""
    status = st["prompt"]
    jobdir = JOBS / ("%d_%d" % (uid, int(time.time())))
    jobdir.mkdir(parents=True, exist_ok=True)
    _cancelled.discard(uid)
    _fast.pop(uid, None)
    p = _Panel(status, _title(st["trailer"]), SWAP_STAGES)

    async def say(txt, kb=None):
        p.close()
        try:
            await status.edit("🎬 **Somali trailer**\\n\\n" + txt, reply_markup=kb or _kb_cancel())
        except Exception:
            pass
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
        for key, name in (("dl_trailer", "trailer"), ("dl_somali", "somali_trailer")):
            m = st[name]
            p.exp[key] = max(10, (getattr(m.video or m.document, "file_size", 0) or 0) / 12e6)
            p.begin(key)
            got[name] = await _deps["build_job"](uid, m, status, prog=p, key=key)
            p.done(key)
            if uid in _cancelled:
                return p.close()
        out = str(jobdir / "somali_trailer.mp4")
        cmd = [ENGINE[0], "-u", ENGINE[1], "swap", "--trailer", got["trailer"]["src"], "--somali", got["somali_trailer"]["src"],
               "--out", out, "--report", str(jobdir / "swap.json")]
        p.begin("swap")
        await p.draw(force=True)
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        _procs[uid] = proc
        tail, refused = [], None
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=900)
            except asyncio.TimeoutError:
                proc.kill()
                raise RuntimeError("the swap did not answer for 15 minutes — stopped")
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            tail = (tail + [line])[-6:]
            if line.startswith("REFUSED"):
                refused = line.split(":", 1)[-1].strip()
            elif line.startswith("picture:"):
                p.note["swap"] = "the same picture"
                await p.draw(force=True)
            elif line.startswith("sound:"):
                p.note["swap"] = "its sound placed on the picture"
                await p.draw(force=True)
        rc = await proc.wait()
        _procs.pop(uid, None)
        if uid in _cancelled:
            return p.close()
        if refused is not None:
            # not this trailer's Somali version: back to step 2 with the trailer kept
            _intake[uid] = {"step": "film", "trailer": st["trailer"], "film": None, "orig": None, "subs": None,
                            "movie_subs": None, "prompt": status}
            return await say("⚠️ That short video is **not this trailer in Somali**: %s.\\n\\n"
                             "**2/4** Send the **Somali film** (the full dubbed movie) and the bot builds the trailer "
                             "from it." % refused)
        if rc != 0 or not os.path.exists(out):
            raise RuntimeError("the swap failed: " + " › ".join(tail[-3:])[:400])
        p.done("swap")
        p.exp["send"] = max(10, os.path.getsize(out) / 2e6)
        p.begin("send")
        await p.draw(force=True)
        try:
            rep = json.load(open(jobdir / "swap.json"))
        except Exception:
            rep = {}

        async def up(cur, tot):
            if tot:
                await p.set("send", 100 * cur / tot, "%.0f / %.0f MB" % (cur / 1e6, tot / 1e6))
        await _deps["app"].send_video(uid, out, supports_streaming=True, progress=up, caption=swap_caption(rep))
        p.done("send")
        await p.draw(force=True)
        p.close()
    except Exception as exc:
        log.exception("trailer swap job failed")
        _procs.pop(uid, None)
        await say("❌ %s" % exc)


def _start(uid: int) -> None:
    st = _intake.pop(uid)
    if st.get("somali_trailer") is not None:
        asyncio.get_event_loop().create_task(_run_swap(uid, st))
        return
    asyncio.get_event_loop().create_task(_run_fast(uid, st) if st.get("orig") is not None else _run(uid, st))
''', "_run_swap; _start picks it when the second video is the trailer's own Somali version")

P.write_text(s)
print("patched %s" % P)
