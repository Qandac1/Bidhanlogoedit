"""Name, size, duration and resolution of the files in bot-chat messages (John's numbering).
Usage: /opt/media-os/venv/bin/python msg_files.py <msg_id> [...]"""
import asyncio
import sys

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(ids):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True)
    async with app:
        for m in await app.get_messages(BOT, ids):
            f = m and (m.video or m.document)
            if not f:
                print(m.id if m else "?", "no file")
                continue
            print("%d | %s | %.2f GB | %s s | %sx%s" % (m.id, getattr(f, "file_name", "?"), (f.file_size or 0) / 1e9,
                                                      getattr(f, "duration", "?"), getattr(f, "width", "?"),
                                                      getattr(f, "height", "?")))


asyncio.run(main([int(x) for x in sys.argv[1:]]))
