"""Download Saved Messages media by id into a folder: saved_download.py <outdir> <id> [id...]"""
import asyncio
import sys

from pyrogram import Client


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(out, ids):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        for m in await app.get_messages("me", ids):
            if not m or m.empty:
                print("missing", ids); continue
            p = await app.download_media(m, file_name=f"{out}/msg{m.id}_")
            print(m.id, p)


asyncio.run(main(sys.argv[1], [int(x) for x in sys.argv[2:]]))
