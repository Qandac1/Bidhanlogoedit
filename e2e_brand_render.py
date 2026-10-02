"""One video through the bot's BRANDING flow from John's account, exactly as he does it: forward his own message
to the bot, wait for the "Ready to render" panel, print it, press "Render now", wait for the delivered video.
Usage: /opt/media-os/venv/bin/python e2e_brand_render.py <msg_id> [--max-min 40]
Prints PANEL ..., then RESULT <msg id> <w>x<h> <size> <duration> or TIMEOUT."""
import asyncio
import sys
import time

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(mid, max_min):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True)
    async with app:
        mark = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.forward_messages(BOT, BOT, mid)
        panel = None
        for _ in range(60):
            async for m in app.get_chat_history(BOT, limit=8):
                if m.id > mark and m.text and "Ready to render" in m.text and m.reply_markup:
                    panel = m
                    break
            if panel:
                break
            await asyncio.sleep(3)
        if not panel:
            print("NO PANEL")
            return 1
        await asyncio.sleep(3)
        panel = await app.get_messages(BOT, panel.id)
        print("PANEL %d\n%s" % (panel.id, panel.text))
        go = [b.callback_data for row in panel.reply_markup.inline_keyboard for b in row if "Render now" in b.text]
        if not go:
            print("NO RENDER BUTTON")
            return 1
        try:
            await app.request_callback_answer(BOT, panel.id, go[0], timeout=15)
        except Exception as exc:
            print("  (callback: %s)" % type(exc).__name__)
        t_end = time.time() + max_min * 60
        while time.time() < t_end:
            await asyncio.sleep(20)
            async for m in app.get_chat_history(BOT, limit=6):
                if m.id > panel.id and m.video and m.from_user and m.from_user.is_bot:
                    v = m.video
                    print("RESULT %d %dx%d %.1f MB %ss" % (m.id, v.width, v.height, v.file_size / 1e6, v.duration))
                    return 0
                if m.id > panel.id and m.text and ("❌" in m.text or "failed" in m.text.lower()):
                    print("FAILED %d %s" % (m.id, m.text[:300]))
                    return 1
        print("TIMEOUT")
        return 1


if __name__ == "__main__":
    a = sys.argv[1:]
    mx = float(a[a.index("--max-min") + 1]) if "--max-min" in a else 40.0
    sys.exit(asyncio.run(main(int(a[0]), mx)))
