"""Check the newest video in John's Saved Messages: name, length, size, thumbnail (downloaded).
Usage: /opt/media-os/venv/bin/python check_saved.py <thumb out.jpg>"""
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
        async for m in app.get_chat_history("me", limit=5):
            if m.video:
                v = m.video
                print("msg %d %s | %s | %d s (%d:%02d:%02d) | %dx%d | %.2f GB | thumbs %d" % (
                    m.id, m.date, v.file_name, v.duration, v.duration // 3600, v.duration % 3600 // 60,
                    v.duration % 60, v.width, v.height, v.file_size / 1e9, len(v.thumbs or [])))
                print((m.caption or "")[:120].replace("\n", " | "))
                if v.thumbs:
                    await app.download_media(v.thumbs[-1].file_id, file_name=sys.argv[1])
                    print("thumb ->", sys.argv[1])
                break


asyncio.run(main())
