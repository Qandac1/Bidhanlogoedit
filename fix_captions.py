"""Edit the caption of recent Saved Messages whose caption contains a given text.
Usage: /opt/media-os/venv/bin/python fix_captions.py "<old text>" "<new caption>" [...pairs]"""
import asyncio
import sys

from pyrogram import Client


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(pairs):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True)
    async with app:
        async for m in app.get_chat_history("me", limit=15):
            cap = m.caption or ""
            for old, new in pairs:
                if old in cap:
                    await app.edit_message_caption("me", m.id, new)
                    print("edited", m.id, "->", new)


a = sys.argv[1:]
asyncio.run(main(list(zip(a[0::2], a[1::2]))))
