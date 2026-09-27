"""Bot fixes, John 2026-09-27 (no premium account; quality first; real thumbnails):
  dubsync_job.py
    A1 a cancelled job also stops its proxy encoder and deletes the half-written proxy
       (13:07 a cancel left the encoder running; the next job's encoder wrote the same file)
    A2 switch_audio producing no file keeps its output as a log and says why
       (Pushpa 2 shipped "dub only" and the reason was thrown away)
  bot.py
    B1 never squeeze a film to fit 2 GB when MEGA is set up -- over 2 GB goes to MEGA
       (Pushpa 2: 2000k -> 1039k); the premium-expired notice no longer says "sized to fit"
    (no source-based bitrate floor: John's own 2000k setting -- the one his banner uploads use --
     gives ~3.8 GB for a 3h40 film, the "around 3 GB" he asked for; a floor made it ~6 GB)
    B3 real thumbnail: a bright, detailed frame from inside the film (Telegram used the black
       first frame); used for Telegram video, premium video and the MEGA link message
Usage: python3 patch_bot_all.py <dir with bot.py and dubsync_job.py>   (idempotent: refuses twice)
"""
import os
import sys

d = sys.argv[1]
J = os.path.join(d, "dubsync_job.py")
B = os.path.join(d, "bot.py")
sj = open(J, encoding="utf-8").read()
sb = open(B, encoding="utf-8").read()
if "_make_thumb" in sb or "half-written proxy" in sj:
    raise SystemExit("already patched")


def rep(s, old, new, what):
    assert s.count(old) == 1, "anchor not found exactly once: " + what
    return s.replace(old, new)


# ---- A1: cancel kills the proxy encoder, removes the partial file ---------------------------
sj = rep(sj, '''    assert proc.stdout is not None
    while True:
        try:
            chunk = await asyncio.wait_for(proc.stdout.read(4096),
                                           timeout=STALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            stalled = True
            break''', '''    assert proc.stdout is not None
    while True:
        try:
            chunk = await asyncio.wait_for(proc.stdout.read(4096),
                                           timeout=STALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            stalled = True
            break
        except asyncio.CancelledError:
            # the job was cancelled: stop the encoder and delete the half-written proxy, or it
            # runs on and the next job's encoder writes the same file (2026-09-27, Achcham)
            try:
                proc.kill()
            except Exception:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except Exception:
                pass
            dst.unlink(missing_ok=True)
            raise''', "A1 proxy loop")

# ---- A2: keep switch_audio's output when it produces no file --------------------------------
sj = rep(sj, '''        if _sa_out.exists() and _sa_out.stat().st_size > 0:
            out = _sa_out
            stats["audio"] = "dub dialogue + HD master music"
        else:
            stats["audio"] = "dub only (switch_audio produced no file)"''', '''        if _sa_out.exists() and _sa_out.stat().st_size > 0:
            out = _sa_out
            stats["audio"] = "dub dialogue + HD master music"
        else:
            # keep the reason: Pushpa 2 shipped "dub only" and the cause was thrown away
            _why = ""
            try:
                (OUT_DIR / f"{title}_switch_audio.log").write_text(_txt)
                _tail = [x.strip() for x in _txt.splitlines() if x.strip()]
                _why = _tail[-1][:160] if _tail else ""
            except Exception:
                pass
            stats["audio"] = ("dub only (switch_audio produced no file"
                              + (f": {_why}" if _why else "") + ")")''', "A2 audio result")

# ---- B1: no squeeze when MEGA can take it -----------------------------------------------------
sb = rep(sb, '''    cap = PREMIUM_LIMIT if _premium_session() else TG_LIMIT
    if estimate_size_bytes(dur, vk, audio_k) <= cap:
        return vk, ""''', '''    cap = PREMIUM_LIMIT if _premium_session() else TG_LIMIT
    if estimate_size_bytes(dur, vk, audio_k) <= cap:
        return vk, ""
    # John 2026-09-27: quality is never traded for Telegram's cap -- a film over it goes out as
    # a MEGA link at full quality (Pushpa 2 was squeezed 2000k -> 1039k to fit 2 GB)
    try:
        if delivery.mega_is_configured():
            return vk, " → over 2 GB: MEGA link, full quality"
    except Exception:
        pass''', "B1 fit bitrate")
sb = rep(sb, '''                await app.send_message(
                    uid, "⚠️ Your premium login has expired, so this film is being "
                         "sized to fit Telegram's 2 GB limit. Send /loginpremium to "
                         "get up to 4 GB again.")''', '''                await app.send_message(
                    uid, ("ℹ️ No premium login: a film over 2 GB is delivered as a MEGA "
                          "link, at full quality." if delivery.mega_is_configured() else
                          "⚠️ Your premium login has expired, so this film is being "
                          "sized to fit Telegram's 2 GB limit. Send /loginpremium to "
                          "get up to 4 GB again."))''', "B1 premium notice")

# ---- B3: thumbnail helpers + use --------------------------------------------------------------
sb = rep(sb, '''def _fit_bitrate(vk: int, dur: float, audio_k: int) -> tuple[int, str]:''', '''async def _run_quiet(*cmd, timeout: float = 90.0) -> bytes:
    """asyncio subprocess (never the blocking module inside the event loop -- see
    dubsync_job._make_proxy); stdout bytes, b"" on any failure."""
    try:
        p = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.DEVNULL,
                                                 stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(p.communicate(), timeout=timeout)
        return out or b""
    except Exception:
        return b""


async def _make_thumb(path: str, dur: float) -> str | None:
    """A real picture for the chat tile (John 2026-09-27: the bot's videos showed Telegram's
    black first frame). Samples frames from 15-75 % of the film and keeps the one with the most
    detail that is neither dark nor washed out; 320 px JPEG, well under Telegram's 200 KB."""
    try:
        import tempfile
        from PIL import Image, ImageStat
        tmpd = tempfile.mkdtemp(prefix="thumb_")
        best = None
        for frac in (0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75):
            f = os.path.join(tmpd, "f%02d.jpg" % int(frac * 100))
            await _run_quiet("ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % max(1.0, dur * frac),
                             "-i", path, "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "3", f)
            if not os.path.exists(f):
                continue
            st = ImageStat.Stat(Image.open(f).convert("L"))
            score = st.stddev[0] - 0.5 * abs(st.mean[0] - 115.0)
            if best is None or score > best[0]:
                best = (score, f)
        if best is None:
            return None
        out = os.path.join(tmpd, "thumb.jpg")
        im = Image.open(best[1]).convert("RGB")
        im.thumbnail((320, 320))
        im.save(out, "JPEG", quality=85)
        return out
    except Exception:
        log.exception("thumbnail failed (Telegram will use its own)")
        return None


def _fit_bitrate(vk: int, dur: float, audio_k: int) -> tuple[int, str]:''', "B3 helpers")

# add a thumb keyword to _premium_send and pass it on
sb = rep(sb, '''async def _premium_send(out_path: str, caption: str, duration: int,
                        w: int, h: int, target_uid: int | None = None,
                        progress=None) -> str:''', '''async def _premium_send(out_path: str, caption: str, duration: int,
                        w: int, h: int, target_uid: int | None = None,
                        progress=None, thumb: str | None = None) -> str:''', "B3 premium sig")
sb = rep(sb, '''        sent = await pu.send_video(dest, out_path, caption=caption,
                                   duration=duration, width=w, height=h,
                                   supports_streaming=True, progress=progress)''', '''        sent = await pu.send_video(dest, out_path, caption=caption,
                                   duration=duration, width=w, height=h, thumb=thumb,
                                   supports_streaming=True, progress=progress)''', "B3 premium send")
sb = rep(sb, '''            await status.edit(f"⬆️ Uploading… ({human_size(sz)})")
            await reply_to.reply_video(out, duration=int(odur), width=ow, height=oh,
                                       supports_streaming=True, caption=cap,
                                       file_name=name, progress=_ulp)''', '''            await status.edit(f"⬆️ Uploading… ({human_size(sz)})")
            _th = await _make_thumb(out, float(odur or 0))
            await reply_to.reply_video(out, duration=int(odur), width=ow, height=oh,
                                       supports_streaming=True, caption=cap, thumb=_th,
                                       file_name=name, progress=_ulp)''', "B3 telegram send")
sb = rep(sb, '''            where = await _premium_send(out, cap, int(odur), ow, oh,
                                        target_uid=uid, progress=_pp)''', '''            where = await _premium_send(out, cap, int(odur), ow, oh,
                                        target_uid=uid, progress=_pp,
                                        thumb=await _make_thumb(out, float(odur or 0)))''', "B3 premium call")
sb = rep(sb, '''            link = await asyncio.to_thread(delivery.mega_upload, out, name, _mcb)
            await reply_to.reply(f"{cap}\\n📥 **MEGA link:**\\n{link}")''', '''            link = await asyncio.to_thread(delivery.mega_upload, out, name, _mcb)
            _msg = f"{cap}\\n📥 **MEGA link:**\\n{link}"
            _th = await _make_thumb(out, float(odur or 0))
            try:
                if _th and len(_msg) <= 1024:
                    await reply_to.reply_photo(_th, caption=_msg)
                else:
                    if _th:
                        await reply_to.reply_photo(_th)
                    await reply_to.reply(_msg)
            except Exception:
                await reply_to.reply(_msg)''', "B3 MEGA send")

open(J, "w", encoding="utf-8").write(sj)
open(B, "w", encoding="utf-8").write(sb)
print("patched", J, B)
