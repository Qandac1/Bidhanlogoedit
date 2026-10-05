"""End-to-end through Telegram (John's userbot): /trailer with the trailer's OWN SOMALI VERSION (bot35).

  /trailer -> the official trailer -> the Somali version of the same trailer (a short video) -> waits for the
  result, printing every change of the panel and the final caption. Every file is FORWARDED from where it already
  is (the bot chat or Saved Messages); nothing new is uploaded. Each step waits for the bot's acknowledgement.

Usage: /opt/media-os/venv/bin/python e2e_trailer_swap.py <trailer> <somali trailer> [--wait MIN]
  each = bot:<msg id in the bot chat>  or  saved:<msg id in Saved Messages>   (John's numbering)
Prints RESULT PASS (a video came, its caption) | RESULT REFUSED (the bot asked for the film) | RESULT FAIL."""
import asyncio
import sys
import time

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"
a = sys.argv[1:]
WAIT = float(a[a.index("--wait") + 1]) * 60 if "--wait" in a else 1200.0
SRC = a[:2]


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main():
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        t0 = time.time()
        start_id = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.send_message(BOT, "/trailer")

        async def the_prompt(until, want):
            while True:
                async for m in app.get_chat_history(BOT, limit=10):
                    if m.id > start_id and m.from_user and m.from_user.is_bot and "Somali trailer" in (m.text or "") and want in (m.text or ""):
                        return m
                if time.time() > until:
                    return None
                await asyncio.sleep(2)

        if await the_prompt(time.time() + 30, "Send the official") is None:
            print("no prompt from the bot within 30 s -- nothing was sent to it")
            print("RESULT FAIL")
            return
        where, mid = SRC[0].split(":")
        await app.forward_messages(BOT, BOT if where == "bot" else "me", int(mid))
        p2 = await the_prompt(time.time() + 30, "Trailer received")
        if p2 is None:
            print("the bot did not acknowledge the trailer within 30 s -- cancelling")
            await app.send_message(BOT, "/cancel")
            print("RESULT FAIL")
            return
        print("[%4.0fs] step 2 prompt: %s" % (time.time() - t0, (p2.text or "").replace("\n", " / ")[:300]), flush=True)
        where, mid = SRC[1].split(":")
        await app.forward_messages(BOT, BOT if where == "bot" else "me", int(mid))
        print("[%4.0fs] the Somali version forwarded (%s)" % (time.time() - t0, SRC[1]), flush=True)
        last = ""
        while time.time() - t0 < WAIT:
            await asyncio.sleep(6)
            async for m in app.get_chat_history(BOT, limit=8):
                if m.id <= start_id or not (m.from_user and m.from_user.is_bot):
                    continue
                txt = m.text or m.caption or ""
                if m.video:
                    print("[%4.0fs] VIDEO delivered (msg %d, %d s, %.1f MB): %s" % (time.time() - t0, m.id, m.video.duration or 0, (m.video.file_size or 0) / 1e6,
                                                                                txt.replace("\n", " / ")), flush=True)
                    print("RESULT PASS")
                    return
                if "queued" in txt or "Cover:" in txt:
                    print("[%4.0fs] the file went to the LOGO flow: %s" % (time.time() - t0, txt[:200].replace("\n", " / ")), flush=True)
                    await app.send_message(BOT, "/cancel")
                    print("RESULT FAIL")
                    return
                if "not this trailer in Somali" in txt:
                    print("[%4.0fs] %s" % (time.time() - t0, txt.replace("\n", " / ")[:400]), flush=True)
                    print("RESULT REFUSED")
                    return
                if txt.startswith(("🎬 **Somali trailer**", "🎬 Somali trailer")) and "❌" in txt:
                    print("[%4.0fs] %s" % (time.time() - t0, txt.replace("\n", " / ")[:400]), flush=True)
                    print("RESULT FAIL")
                    return
                if txt.startswith(("🎬 **Somali trailer**", "🎬 Somali trailer")) and txt != last:
                    last = txt
                    stage = [ln for ln in txt.split("\n") if ln.startswith(("⏳", "✅"))]
                    print("[%4.0fs] %s" % (time.time() - t0, " | ".join(stage)[-220:]), flush=True)
        print("RESULT FAIL (no result in %.0f min)" % (WAIT / 60))


asyncio.run(main())
