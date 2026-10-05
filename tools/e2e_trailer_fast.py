"""End-to-end through Telegram (John's userbot): /trailer, THE FAST WAY (bot33).

  /trailer -> the trailer -> the Somali film -> the film with the trailer's own language -> "No subtitles" (or a
  trailer .srt) -> waits for the Somali trailer, printing every change of the panel and the final caption.
Every file is FORWARDED from where it already is (the bot chat or Saved Messages): nothing new is uploaded except
an .srt given with --srt.

Usage: /opt/media-os/venv/bin/python e2e_trailer_fast.py <trailer> <somali film> <own-language film> [--srt FILE] [--wait MIN]
  each of the three = bot:<msg id in the bot chat>  or  saved:<msg id in Saved Messages>   (John's numbering)
Prints RESULT PASS (a video came) | RESULT LONGWAY (the bot offered the long way) | RESULT FAIL."""
import asyncio
import sys
import time

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"
a = sys.argv[1:]
SRT = a[a.index("--srt") + 1] if "--srt" in a else None
WAIT = float(a[a.index("--wait") + 1]) * 60 if "--wait" in a else 3600.0
SRC = [x for x in a[:3]]


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def buttons(m):
    rm = m.reply_markup
    if not rm or not getattr(rm, "inline_keyboard", None):
        return []
    return [(b.text, b.callback_data) for row in rm.inline_keyboard for b in row]


async def main():
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        t0 = time.time()
        start_id = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.send_message(BOT, "/trailer")

        async def the_prompt(until, want=None):
            """The bot's /trailer message, waited for (a fixed pause was too short right after a bot restart:
            2026-10-05 the films were sent before the prompt stood and fell into the logo batch)."""
            while True:
                async for m in app.get_chat_history(BOT, limit=10):
                    if m.id > start_id and m.from_user and m.from_user.is_bot and "Somali trailer" in (m.text or ""):
                        if want is None or want in (m.text or ""):
                            return m
                if time.time() > until:
                    return None
                await asyncio.sleep(2)

        if await the_prompt(time.time() + 30, "Send the official") is None:
            print("no prompt from the bot within 30 s -- nothing was sent to it")
            print("RESULT FAIL")
            return
        for (what, src), want in zip(zip(("trailer", "Somali film", "own-language film"), SRC),
                                     ("Trailer received", "Somali film received", "Film with its own sound received")):
            where, mid = src.split(":")
            await app.forward_messages(BOT, BOT if where == "bot" else "me", int(mid))
            print("[%4.0fs] %s forwarded (%s)" % (time.time() - t0, what, src), flush=True)
            if await the_prompt(time.time() + 30, want) is None:
                print("the bot did not acknowledge the %s (\"%s\") within 30 s -- stopping, cancelling the intake" % (what, want))
                await app.send_message(BOT, "/cancel")
                print("RESULT FAIL")
                return
        prompt = await the_prompt(time.time() + 5)
        print("[%4.0fs] prompt: %s | buttons %s" % (time.time() - t0, (prompt.text or "").replace("\n", " / ")[:260], buttons(prompt)), flush=True)
        if "Film with its own sound received" not in (prompt.text or ""):
            print("the bot did not take the third file as the film with its own sound")
            print("RESULT FAIL")
            return
        if SRT:
            await app.send_document(BOT, SRT)
        else:
            try:
                await app.request_callback_answer(BOT, prompt.id, "trl:nosubs", timeout=15)
            except Exception as exc:
                print("  (callback answer: %s)" % type(exc).__name__)
        last = ""
        while time.time() - t0 < WAIT:
            await asyncio.sleep(10)
            async for m in app.get_chat_history(BOT, limit=8):
                if m.id <= start_id or not (m.from_user and m.from_user.is_bot):
                    continue
                txt = m.text or m.caption or ""
                if m.video:
                    print("[%4.0fs] VIDEO delivered (msg %d): %s" % (time.time() - t0, m.id, txt.replace("\n", " / ")), flush=True)
                    print("RESULT PASS")
                    return
                if "long way with these files" in " ".join(t for t, _d in buttons(m)):
                    print("[%4.0fs] the bot stopped the fast way: %s" % (time.time() - t0, txt.replace("\n", " / ")[:400]), flush=True)
                    print("RESULT LONGWAY")
                    return
                if txt.startswith(("🎬 **Somali trailer**", "🎬 Somali trailer")) and ("❌" in txt or "⛔" in txt):
                    print("[%4.0fs] %s" % (time.time() - t0, txt.replace("\n", " / ")[:400]), flush=True)
                    print("RESULT FAIL")
                    return
                if m.id == prompt.id and txt != last:
                    last = txt
                    stage = [ln for ln in txt.split("\n") if ln.startswith(("⏳", "✅"))]
                    print("[%4.0fs] %s" % (time.time() - t0, " | ".join(stage)[-200:]), flush=True)
        print("RESULT FAIL (no result in %.0f min)" % (WAIT / 60))


asyncio.run(main())
