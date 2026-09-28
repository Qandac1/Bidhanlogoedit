"""Read-only: list bot-chat messages with ids a..b (video name, duration, caption)."""
import asyncio
import sys

from pyrogram import Client


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(a, b):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        for m in await app.get_messages("BidhaanLogoEdit_bot", list(range(a, b + 1))):
            if not m or m.empty:
                continue
            # private-chat message ids are shared by ALL of John's chats: keep only the bot chat
            # (2026-09-28: boinker_bot / Taobao spam was listed as if the Bidhaan bot sent it)
            if (getattr(m.chat, "username", "") or "").lower() != "bidhaanlogoedit_bot":
                continue
            v = m.video or m.document
            who = "bot" if m.from_user and m.from_user.is_bot else "John"
            print(m.id, who, (getattr(v, "file_name", None) if v else "text"),
                  (int(getattr(v, "duration", 0) or 0) if v else ""), (m.caption or m.text or "")[:70].replace("\n", " "))


asyncio.run(main(int(sys.argv[1]), int(sys.argv[2])))
