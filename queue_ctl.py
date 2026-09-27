"""Drive the Bidhaan bot dub-sync queue from John's account (userbot), like tapping the panel.

  queue_ctl.py show       -- send /queue, print the panel text and its buttons
  queue_ctl.py stop-all   -- press "Stop all mine": the queue marks waiting films removed
                             FIRST (so none auto-starts), then cancels the running one.
                             A cancelled film keeps its analysis cache (work/<hash>, 30 days):
                             resending the same pair resumes after the finished stages.
Run with /opt/media-os/venv/bin/python.
"""
import asyncio
import sys

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(act):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True)
    async with app:
        sent = await app.send_message(BOT, "/queue")
        panel = None
        for _ in range(20):
            await asyncio.sleep(1)
            async for m in app.get_chat_history(BOT, limit=5):
                if (m.id > sent.id and m.from_user and m.from_user.is_bot
                        and "Dub-sync queue" in (m.text or "")):
                    panel = m
                    break
            if panel:
                break
        if panel is None:
            sys.exit("no /queue panel came back")
        print(panel.text)
        rows = panel.reply_markup.inline_keyboard if panel.reply_markup else []
        btns = [b for row in rows for b in row]
        print("BUTTONS:", [b.text for b in btns])
        if act == "stop-all":
            b = next((b for b in btns if (b.callback_data or "") == "dq:stop"), None)
            if b is None:
                sys.exit("no Stop-all button (nothing running or waiting)")
            try:
                r = await app.request_callback_answer(BOT, panel.id, b.callback_data, timeout=30)
                print("ANSWER:", getattr(r, "message", r))
            except Exception as ex:
                print("callback sent (%s)" % type(ex).__name__)
            await asyncio.sleep(3)
            m = await app.get_messages(BOT, panel.id)
            print("PANEL NOW:\n" + (m.text or ""))


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "show"))
