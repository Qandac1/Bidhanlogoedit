"""Live: /cancel the running queue film (a test film) -> the queue must start the next one by
itself; wait for it to be delivered and time it.  Prints the queue file at the end."""
import asyncio
import json
import subprocess
import time

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def queue():
    out = subprocess.run(["docker", "exec", "bidhaan-logoedit", "cat", "/app/data/dub_queue.json"],
                         capture_output=True, text=True).stdout
    return json.loads(out or "[]")


async def main():
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        last = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        t0 = time.time()
        await app.send_message(BOT, "/cancel")
        got = None
        while time.time() - t0 < 20 * 60 and not got:
            await asyncio.sleep(10)
            async for m in app.get_chat_history(BOT, limit=10):
                if m.id > last and (m.video or m.document) and "dub-sync complete" in (m.caption or ""):
                    got = m
                    break
        print("next film delivered after %.0fs: %s" % (time.time() - t0, (got.caption or "")[:90].replace("\n", " ") if got else "NOT YET"))
    for e in queue()[-3:]:
        print("  %-10s started %s ended %s" % (e["state"], e.get("started"), e.get("ended")))


asyncio.run(main())
