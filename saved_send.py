"""Send files to John's Telegram Saved Messages through the VPS userbot.

Generalised from the proven /tmp/send_skips.py (side-by-side clips, 2026-09-25).
Usage:
  saved_send.py --header "text" [--footer "text"] --manifest items.json
      items.json = [{"path": "/x/clip_01.mp4", "caption": "..."}, ...]
  saved_send.py --header "text" FILE [FILE ...]          (caption = file name)
Videos go as streaming video, images as photos, everything else as a document. Prints "sent N/M".
Run with /opt/media-os/venv/bin/python (pyrogram).
"""
import argparse
import asyncio
import json
import os

from pyrogram import Client
from pyrogram.session.session import Session as _Session

_invoke = _Session.invoke


async def _invoke_patient(self, query, retries=None, timeout=None, sleep_threshold=None):
    """pyrogram's upload workers call session.invoke(part) with its FIXED 10 s flood limit and
    DROP the part on a longer wait (non-premium big uploads get FLOOD_PREMIUM_WAIT 11 s): the
    upload then fails after sending 2 GB (Half Girlfriend, 2026-09-28). Every call waits up to
    300 s instead; the client's own sleep_threshold does not reach those workers."""
    kw = {"sleep_threshold": 300 if sleep_threshold is None else max(sleep_threshold, 300)}
    if retries is not None:
        kw["retries"] = retries
    if timeout is not None:
        kw["timeout"] = timeout
    return await _invoke(self, query, **kw)


_Session.invoke = _invoke_patient

VIDEO = (".mp4", ".mov", ".mkv", ".webm")
PHOTO = (".jpg", ".jpeg", ".png", ".webp")


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def video_meta(p):
    """(duration s, width, height, thumbnail jpg or None) -- Telegram shows the black first frame
    and no length without these (John 2026-09-27). The thumbnail is the most detailed,
    well-exposed of 7 frames from 15-75 % of the video (as the bot's _make_thumb)."""
    import subprocess
    import tempfile
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", p],
                       capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    st = (j.get("streams") or [{}])[0]
    dur = float((j.get("format") or {}).get("duration") or 0)
    w, h = int(st.get("width") or 0), int(st.get("height") or 0)
    thumb = None
    try:
        from PIL import Image, ImageStat
        d = tempfile.mkdtemp(prefix="sthumb_")
        best = None
        for frac in (0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75):
            f = os.path.join(d, "f%02d.jpg" % int(frac * 100))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % max(1.0, dur * frac), "-i", p,
                            "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "3", f])
            if os.path.exists(f):
                s = ImageStat.Stat(Image.open(f).convert("L"))
                score = s.stddev[0] - 0.5 * abs(s.mean[0] - 115.0)
                if best is None or score > best[0]:
                    best = (score, f)
        if best:
            thumb = os.path.join(d, "thumb.jpg")
            Image.open(best[1]).convert("RGB").save(thumb, "JPEG", quality=85)
    except Exception as ex:
        print("thumbnail skipped:", ex)
    return int(dur), w, h, thumb


async def main(a):
    items = json.load(open(a.manifest)) if a.manifest else [{"path": f, "caption": os.path.basename(f)} for f in a.files]
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True,
                 sleep_threshold=300)  # non-premium big uploads get FLOOD_PREMIUM_WAIT 11+ s: wait, never crash
    ok = 0
    async with app:
        if a.header:
            await app.send_message("me", a.header)
        for it in items:
            p, cap = it["path"], it.get("caption", "")[:1000]
            try:
                if p.lower().endswith(VIDEO):
                    dur, w, h, th = video_meta(p)
                    last = [-10]

                    def prog(cur, tot):
                        pct = int(cur * 100 / tot) if tot else 0
                        if pct >= last[0] + 10:
                            last[0] = pct
                            print("  upload %d%%" % pct, flush=True)
                    await app.send_video("me", p, caption=cap, supports_streaming=True,
                                         duration=dur, width=w, height=h, thumb=th,
                                         file_name=it.get("file_name") or os.path.basename(p),
                                         progress=prog)
                elif p.lower().endswith(PHOTO):
                    await app.send_photo("me", p, caption=cap)
                else:
                    await app.send_document("me", p, caption=cap)
                ok += 1
                print("sent", p)
            except Exception as ex:
                print("FAILED", p, str(ex)[:150])
        if a.footer:
            await app.send_message("me", a.footer)
    print("sent %d/%d" % (ok, len(items)))


ap = argparse.ArgumentParser()
ap.add_argument("--header", default="")
ap.add_argument("--footer", default="")
ap.add_argument("--manifest", default="")
ap.add_argument("--header-file", default="", help="header text read from a file (multi-line tables)")
ap.add_argument("files", nargs="*")
_a = ap.parse_args()
if _a.header_file:
    _a.header = open(_a.header_file, encoding="utf-8").read().strip()[:4000]
asyncio.run(main(_a))
