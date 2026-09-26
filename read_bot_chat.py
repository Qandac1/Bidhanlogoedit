"""Read-only: the last N messages in John's chat with @BidhaanLogoEdit_bot (userbot john_ie)."""
import asyncio
import sys

from pyrogram import Client


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        async for m in app.get_chat_history("BidhaanLogoEdit_bot", limit=n):
            who = "bot" if m.from_user and m.from_user.is_bot else "John"
            kind = "video" if m.video else "voice" if m.voice else "doc" if m.document else "text"
            txt = (m.text or m.caption or "").replace("\n", " | ")[:300]
            print(m.id, m.date.strftime("%H:%M:%S"), who, kind, txt)


asyncio.run(main())
