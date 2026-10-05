"""Through Telegram (John's userbot): does /trailer get its prompt, and does the prompt STAY?  (bot33 first e2e,
2026-10-05: the prompt was gone 4 s after /trailer and the three films fell into the logo batch.)

  [--cancel-first]  /cancel first (clears a logo batch a failed test left behind)
  /trailer -> wait -> every bot message since, with its id, at 3 s / 8 s / 15 s -> the Cancel button of the prompt
Sends nothing else. Usage: /opt/media-os/venv/bin/python e2e_trailer_prompt.py [--cancel-first]
Prints PROMPT OK (stayed) | PROMPT GONE | NO PROMPT."""
import asyncio
import sys
import time

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def bot_msgs(app, after):
    out = []
    async for m in app.get_chat_history(BOT, limit=12):
        if m.id > after:
            out.append((m.id, "bot" if (m.from_user and m.from_user.is_bot) else "john", (m.text or m.caption or "")[:90].replace("\n", " / ")))
    return sorted(out)


async def main():
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        if "--cancel-first" in sys.argv:
            await app.send_message(BOT, "/cancel")
            await asyncio.sleep(5)
        start = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        t0 = time.time()
        await app.send_message(BOT, "/trailer")
        seen = {}
        for wait in (3, 5, 7):
            await asyncio.sleep(wait)
            rows = await bot_msgs(app, start)
            print("[%2.0fs] %s" % (time.time() - t0, rows), flush=True)
            for i, who, txt in rows:
                if who == "bot" and "Somali trailer" in txt:
                    seen[i] = txt
        if not seen:
            print("NO PROMPT")
            return
        pid = max(seen)
        still = [r for r in await bot_msgs(app, start) if r[0] == pid]
        print("PROMPT OK (stayed)" if still else "PROMPT GONE")
        if "--with-file" in sys.argv:
            # one real intake step: the trailer is forwarded; the bot must say "Trailer received" (in its prompt or,
            # if Telegram refuses the edit, in a new message) and the file must NOT reach the logo flow
            where, mid = sys.argv[sys.argv.index("--with-file") + 1].split(":")
            await app.forward_messages(BOT, BOT if where == "bot" else "me", int(mid))
            got, rows = False, []
            for _ in range(10):
                await asyncio.sleep(3)
                rows = [r for r in await bot_msgs(app, start) if r[1] == "bot"]
                got = any("Trailer received" in t for _i, _w, t in rows)
                if got:
                    break
            logo = [t for _i, _w, t in rows if "queued" in t or "Cover:" in t or "preset" in t.lower()]
            print("after the trailer file: %s" % rows)
            print("INTAKE STEP OK (Trailer received, nothing went to the logo flow)" if got and not logo
                  else "INTAKE STEP FAILED (received=%s, logo flow messages=%s)" % (got, logo))
            pid = max(i for i, _w, t in rows if "Somali trailer" in t) if any("Somali trailer" in t for _i, _w, t in rows) else pid
            still = True
        if still:
            try:
                await app.request_callback_answer(BOT, pid, "trl:cancel", timeout=15)
            except Exception as exc:
                print("  (cancel answer: %s)" % type(exc).__name__)
            await asyncio.sleep(3)
            print("after Cancel: %s" % [r for r in await bot_msgs(app, start) if r[1] == "bot"])


asyncio.run(main())
