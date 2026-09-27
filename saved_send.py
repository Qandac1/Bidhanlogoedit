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

VIDEO = (".mp4", ".mov", ".mkv", ".webm")
PHOTO = (".jpg", ".jpeg", ".png", ".webp")


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(a):
    items = json.load(open(a.manifest)) if a.manifest else [{"path": f, "caption": os.path.basename(f)} for f in a.files]
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True)
    ok = 0
    async with app:
        if a.header:
            await app.send_message("me", a.header)
        for it in items:
            p, cap = it["path"], it.get("caption", "")[:1000]
            try:
                if p.lower().endswith(VIDEO):
                    await app.send_video("me", p, caption=cap, supports_streaming=True)
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
ap.add_argument("files", nargs="*")
asyncio.run(main(ap.parse_args()))
