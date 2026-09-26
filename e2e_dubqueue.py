"""End-to-end through Telegram (John's userbot): the dub-sync QUEUE.

Uses the 85 s Awarapan 2 pair (HD 59090 + Somali dub 59091, ~1 min per dub-sync):
  1. /queue shows the panel
  2. /dub + the pair + Start -> "Dub-sync starting" and a "Next movie?" prompt
  3. the pair again through that prompt + Start -> "Queued #2"
  4. 📋 Queue on the prompt -> the list shows ▶️ Now + ⏳ 1.
  5. both films delivered, film 2's job starting only after film 1 was delivered
Usage: e2e_dubqueue.py"""
import asyncio
import time

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"
HD, DUB = 59090, 59091


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def buttons(m):
    if not m.reply_markup or not getattr(m.reply_markup, "inline_keyboard", None):
        return []
    return [b.callback_data for row in m.reply_markup.inline_keyboard for b in row]


async def newest(app, after, pred, tries=12, wait=3):
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


async def main():
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    ok = True
    async with app:
        t0 = time.time()
        last = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.send_message(BOT, "/queue")
        q = await newest(app, last + 1, lambda m: "Dub-sync queue" in (m.text or ""))
        print("1 /queue:", (q.text or "")[:160].replace("\n", " / ") if q else "NO PANEL")
        ok &= q is not None

        await app.send_message(BOT, "/dub")
        await asyncio.sleep(4)
        mark = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]   # the /dub prompt: it BECOMES the panel
        for mid in (HD, DUB):
            await app.forward_messages(BOT, BOT, mid)
            await asyncio.sleep(5)
        p1 = await newest(app, mark, lambda m: "dub:start" in buttons(m))
        print("2 panel:", p1.id if p1 else None)
        await press(app, p1.id, "dub:start")
        await asyncio.sleep(4)
        p1 = await app.get_messages(BOT, p1.id)
        nxt = await newest(app, p1.id + 1, lambda m: "dubflow:done" in buttons(m))
        print("  after Start:", (p1.text or "")[:80].replace("\n", " / "), "| next prompt:", bool(nxt))
        ok &= "starting" in (p1.text or "").lower() and nxt is not None

        mark = nxt.id                              # the "Next movie?" prompt becomes panel 2
        for mid in (HD, DUB):
            await app.forward_messages(BOT, BOT, mid)
            await asyncio.sleep(5)
        p2 = await newest(app, mark, lambda m: "dub:start" in buttons(m))
        await press(app, p2.id, "dub:start")
        await asyncio.sleep(4)
        p2 = await app.get_messages(BOT, p2.id)
        print("3 second Start:", (p2.text or "")[:100].replace("\n", " / "))
        queued = "Queued #2" in (p2.text or "")
        nxt2 = await newest(app, p2.id + 1, lambda m: "dq:show" in buttons(m))
        if nxt2:
            await press(app, nxt2.id, "dq:show")
            lst = await newest(app, nxt2.id + 1, lambda m: "Dub-sync queue" in (m.text or ""))
            print("4 list:", (lst.text or "")[:220].replace("\n", " / ") if lst else "NO LIST")
            await press(app, nxt2.id, "dubflow:done")
        # 5) deliveries, in order
        got, starts = [], []
        seen = set()
        deadline = time.time() + 25 * 60
        while time.time() < deadline and len(got) < 2:
            async for m in app.get_chat_history(BOT, limit=15):
                if m.id <= last or m.id in seen:
                    continue
                txt = (m.caption or m.text or "")
                if m.video or m.document:
                    if "dub-sync complete" in txt:
                        seen.add(m.id)
                        got.append((m.id, time.time() - t0))
                        print("5 delivered msg %d at %.0fs: %s" % (m.id, time.time() - t0, txt[:70].replace("\n", " ")))
            await asyncio.sleep(10)
        import json
        import subprocess
        qj = json.loads(subprocess.run(["docker", "exec", "bidhaan-logoedit", "cat", "/app/data/dub_queue.json"],
                                       capture_output=True, text=True).stdout or "[]")
        mine = sorted([e for e in qj if e.get("started")], key=lambda e: e["added"])[-2:]
        for e in mine:
            print("  queue: %-12s started %.0f ended %s" % (e["state"], e["started"], e.get("ended")))
        order_ok = (len(mine) == 2 and all(e["state"] == "finished" for e in mine)
                    and mine[1]["started"] >= mine[0]["ended"])
        print("  film 2 started after film 1 ended:", order_ok)
        await app.send_message(BOT, "/queue")
        q = await newest(app, (got[-1][0] if got else last) + 1, lambda m: "Dub-sync queue" in (m.text or ""))
        print("6 /queue:", (q.text or "")[:260].replace("\n", " / ") if q else "NO PANEL")
        ok &= queued and len(got) == 2 and order_ok
    print("RESULT", "PASS" if ok else "FAIL")


asyncio.run(main())
