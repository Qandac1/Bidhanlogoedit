"""Print a bot-chat message's full text and its inline buttons (text -> callback data).
Usage: /opt/media-os/venv/bin/python msg_buttons.py <msg_id>"""
import asyncio
import sys

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(mid):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True)
    async with app:
        m = await app.get_messages(BOT, mid)
        print(m.text or m.caption or "")
        kb = getattr(m.reply_markup, "inline_keyboard", None) or []
        for row in kb:
            print("  BUTTONS:", " | ".join("%s -> %s" % (b.text, b.callback_data) for b in row))


asyncio.run(main(int(sys.argv[1])))
