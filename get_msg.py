"""Print the FULL text/caption of messages in John's chat with the Bidhaan bot (his numbering).
Usage: /opt/media-os/venv/bin/python get_msg.py <msg_id> [<msg_id> ...]"""
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
        for m in await app.get_messages("BidhaanLogoEdit_bot", [int(x) for x in sys.argv[1:]]):
            print("=== %s %s" % (m.id, m.date))
            print(m.text or m.caption or "")
            if m.video:
                v = m.video
                print("[video: %s, %d s, %dx%d, %.2f GB, thumbs: %s]" % (
                    v.file_name, v.duration, v.width, v.height, v.file_size / 1024 ** 3,
                    len(v.thumbs or [])))


asyncio.run(main())
