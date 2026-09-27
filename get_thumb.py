"""Download the thumbnail Telegram shows for a video message in John's chat with the Bidhaan bot.
Usage: /opt/media-os/venv/bin/python get_thumb.py <msg_id> <out.jpg>"""
import asyncio
import sys

from pyrogram import Client


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


async def main():
    async with Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                      workdir="/opt/media-os/data", no_updates=True) as app:
        m = await app.get_messages("BidhaanLogoEdit_bot", int(sys.argv[1]))
        th = (m.video.thumbs or [None])[-1] if m.video else None
        if th is None:
            print("NO THUMB")
            return
        p = await app.download_media(th.file_id, file_name=sys.argv[2])
        print("thumb", th.width, "x", th.height, "->", p)


asyncio.run(main())
