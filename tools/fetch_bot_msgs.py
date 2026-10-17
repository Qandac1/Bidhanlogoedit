"""Download the videos of messages in a chat AS THE BOT (its own account, a separate in-memory session that takes no
updates -- the running bot is not touched; John's account is not used). For re-running a job whose source files the
server already cleaned: the bot-side message ids are in the bot's dub_queue.json ("mids").
Run INSIDE the bot container (API_ID / API_HASH / BOT_TOKEN come from its environment, never printed):
    python3 fetch_bot_msgs.py <chat id> <out dir> <msg id> [<msg id> ...]
Prints one line per file (name, size, path) and FETCH_DONE <n>."""
import asyncio
import os
import sys

from pyrogram import Client

chat, out = int(sys.argv[1]), sys.argv[2]
ids = [int(x) for x in sys.argv[3:]]
os.makedirs(out, exist_ok=True)


async def main():
    app = Client("fetch39", api_id=int(os.environ["API_ID"]), api_hash=os.environ["API_HASH"],
                 bot_token=os.environ["BOT_TOKEN"], in_memory=True, no_updates=True)
    n = 0
    async with app:
        for m in await app.get_messages(chat, ids):
            media = m.video or m.document if m else None
            if not media:
                print("msg %s: no video/document" % (m.id if m else "?"))
                continue
            name = getattr(media, "file_name", None) or "msg%d.mp4" % m.id
            dest = os.path.join(out, "%d_%s" % (m.id, name.replace("/", "_")))
            path = await m.download(file_name=dest)
            size = os.path.getsize(path) if path and os.path.exists(path) else 0
            whole = size == getattr(media, "file_size", size)
            print("msg %d  %s  %.1f MB  %s  %s" % (m.id, name, size / 1e6, "whole" if whole else "SHORT", path), flush=True)
            n += whole
    print("FETCH_DONE %d" % n)


asyncio.run(main())
