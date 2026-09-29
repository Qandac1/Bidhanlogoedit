"""Queue films for dub-sync through the bot, from John's account, exactly as he does it.

Generalised from the proven e2e_dubqueue.py (2026-09-26). For each pair of message ids
already in the bot chat (HD first, then the dub): the first goes through /dub + the pair +
Start, every
further one through the "Next movie?" prompt + the pair + Start ("Queued #n").
It prints each confirm panel (so the choices -- swap, branding, mode -- can be checked)
and exits once everything is queued; watch progress with queue_ctl.py show.

IDS ARE JOHN'S NUMBERING (what the userbot sees): find them with
  find_msgs.py <word>   -> "BidhaanLogoEdit_bot <id> <date> <file> ..."
NOT the "mids" in /app/data/dub_queue.json -- those are the BOT's numbering of the same
chat; forwarding them from John's side forwards unrelated old messages (2026-09-27).
Full films: the bot reads both files before the panel appears -- waits up to 10 min.

Usage: /opt/media-os/venv/bin/python e2e_queue_films.py [--no-brand] [--from-saved] HD,DUB [HD,DUB ...]
  --from-saved: the ids are in John's Saved Messages (forwarded from there to the bot).
  --no-brand: press "Branding" on each panel until it reads "Branding: OFF" (John 2026-09-29: a clean
  film, no logo); Start is NEVER pressed unless the panel shows OFF.
Prints QUEUED OK when every film started or was queued.
"""
import asyncio
import sys

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def labels(m):
    if not m.reply_markup or not getattr(m.reply_markup, "inline_keyboard", None):
        return []
    return [b.text for row in m.reply_markup.inline_keyboard for b in row]


def buttons(m):
    if not m.reply_markup or not getattr(m.reply_markup, "inline_keyboard", None):
        return []
    return [b.callback_data for row in m.reply_markup.inline_keyboard for b in row]


async def newest(app, after, pred, tries=15, wait=3):
    for _ in range(tries):
        async for m in app.get_chat_history(BOT, limit=12):
            if m.id >= after and pred(m):
                return m
        await asyncio.sleep(wait)
    return None


async def press(app, mid, data):
    try:
        await app.request_callback_answer(BOT, mid, data, timeout=15)
    except Exception as exc:
        print("  (callback: %s)" % type(exc).__name__)


async def main(pairs):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"),
                 workdir="/opt/media-os/data", no_updates=True)
    ok = True
    async with app:
        await app.send_message(BOT, "/dub")
        await asyncio.sleep(4)
        mark = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        prompt = None
        for n, (hd, dub) in enumerate(pairs, 1):
            for mid in (hd, dub):
                src = await app.get_messages(SRC, mid)
                if not (src and (src.video or src.document)):
                    print("film %d: message %d is not a video/file in %s -- stop" % (n, mid, SRC))
                    return
                await app.forward_messages(BOT, SRC, mid)
                await asyncio.sleep(6)
            panel = await newest(app, mark, lambda m: "dub:start" in buttons(m), tries=200)
            if panel is None:
                print("film %d: NO CONFIRM PANEL" % n)
                ok = False
                break
            print("film %d panel:\n  %s" % (n, (panel.text or "").replace("\n", "\n  ")[:900]))
            if NO_BRAND:
                for _ in range(2):
                    if any("Branding: OFF" in x for x in labels(panel)):
                        break
                    await press(app, panel.id, "dub:brand")
                    await asyncio.sleep(3)
                    panel = await app.get_messages(BOT, panel.id)
                if not any("Branding: OFF" in x for x in labels(panel)):
                    print("film %d: the panel does not show Branding: OFF (%s) -- NOT started" % (n, labels(panel)))
                    ok = False
                    break
                print("film %d: Branding: OFF confirmed on the panel" % n)
            await press(app, panel.id, "dub:start")
            await asyncio.sleep(5)
            panel = await app.get_messages(BOT, panel.id)
            txt = panel.text or ""
            started = "starting" in txt.lower() or ("Queued #%d" % n) in txt or "Queued" in txt
            print("film %d after Start: %s" % (n, txt[:160].replace("\n", " / ")))
            ok &= started
            prompt = await newest(app, panel.id + 1, lambda m: "dubflow:done" in buttons(m))
            if prompt is None:
                print("film %d: no 'Next movie?' prompt" % n)
                ok = n == len(pairs)
                break
            mark = prompt.id
        if prompt is not None:
            await press(app, prompt.id, "dubflow:done")
    print("QUEUED OK" if ok else "QUEUE FAILED")


NO_BRAND = "--no-brand" in sys.argv
# --from-saved: the pair ids are in John's Saved Messages (new films he sends himself), not the bot chat
SRC = "me" if "--from-saved" in sys.argv else BOT
pairs = [tuple(int(x) for x in a.split(",")) for a in sys.argv[1:] if not a.startswith("--")]
asyncio.run(main(pairs))
