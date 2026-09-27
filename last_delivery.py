"""Read-only: the newest "dub-sync complete" delivery in the bot chat whose caption contains WORD.
Prints: <unix time> <message id> <first caption line>   (nothing when none in the last 200)"""
import asyncio
import sys

from pyrogram import Client


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(word):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True)
    async with app:
        async for m in app.get_chat_history("BidhaanLogoEdit_bot", limit=200):
            cap = m.caption or ""
            if (m.video or m.document) and "dub-sync complete" in cap and word.lower() in cap.lower():
                print(int(m.date.timestamp()), m.id, cap.splitlines()[0])
                return


asyncio.run(main(sys.argv[1]))
