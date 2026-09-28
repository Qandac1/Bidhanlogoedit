"""Download Saved Messages media by id into a folder: saved_download.py <outdir> <id> [id...]
[--chat NAME] reads another chat instead (e.g. BidhaanLogoEdit_bot: a delivered film)."""
import asyncio
import sys

from pyrogram import Client


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(out, ids, chat="me"):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        for m in await app.get_messages(chat, ids):
            if not m or m.empty:
                print("missing", ids); continue
            p = await app.download_media(m, file_name=f"{out}/msg{m.id}_")
            print(m.id, p)


a = sys.argv[1:]
chat = "me"
if "--chat" in a:
    i = a.index("--chat")
    chat = a[i + 1]
    del a[i:i + 2]
asyncio.run(main(a[0], [int(x) for x in a[1:]], chat))
