"""Forward John's own messages (his numbering in the bot chat) back into the bot chat, as if he
re-sent them -- e.g. videos to brand again. Checks each is a video/file first and prints its name.
Usage: /opt/media-os/venv/bin/python forward_to_bot.py <msg_id> [<msg_id> ...]
Prints FORWARDED <n>."""
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
    n = 0
    async with app:
        for mid in ids:
            m = await app.get_messages(BOT, mid)
            f = m and (m.video or m.document)
            if not f:
                print("message %d is not a video/file -- skipped" % mid)
                continue
            print("forwarding %d: %s (%s s)" % (mid, getattr(f, "file_name", "?"), getattr(f, "duration", "?")))
            await app.forward_messages(BOT, BOT, mid)
            n += 1
            await asyncio.sleep(3)
    print("FORWARDED %d" % n)


asyncio.run(main([int(x) for x in sys.argv[1:]]))
