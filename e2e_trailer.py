"""End-to-end through Telegram (John's userbot): the whole /trailer feature.

/trailer -> trailer video (uploaded) -> Somali Jigarthanda (message 58680) -> subtitles
-> for each question: tap the suggestion that holds the Somali line verified by
reading (2026-09-26), else None; press "4-6" once -> wait for the Somali trailer."""
import asyncio
import glob
import json
import os
import time

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"
TRAILER = "/opt/dubsync2/trailers_in/jigarthanda.mp4"
SRT = "/opt/dubsync2/trailers_in/jigarthanda.en.srt"
FILM_MSG = 58680
TRUTH = {5: 2389.3, 6: 2394.7, 8: 2229.1, 9: 2240.05, 13: 3030.0, 14: 3030.8, 15: 3035.0,
         23: 908.9, 25: 914.4, 34: 7519.7, 40: 9261.0}


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def buttons(m):
    rm = m.reply_markup
    if not rm or not getattr(rm, "inline_keyboard", None):
        return []
    return [b.callback_data for row in rm.inline_keyboard for b in row]


async def click(app, mid, data):
    try:
        await app.request_callback_answer(BOT, mid, data, timeout=15)
    except Exception as exc:
        print("  (callback answer: %s)" % type(exc).__name__)


async def main():
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        t0 = time.time()
        start_id = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.send_message(BOT, "/trailer")
        await asyncio.sleep(4)
        await app.send_video(BOT, TRAILER, caption="Jigarthanda DoubleX trailer")
        await asyncio.sleep(6)
        await app.forward_messages(BOT, BOT, FILM_MSG)
        await asyncio.sleep(6)
        await app.send_document(BOT, SRT)
        print("[%4.0fs] inputs sent" % (time.time() - t0), flush=True)
        done_pos, used_more, last_status = set(), False, ""
        jobdir = None
        while time.time() - t0 < 3600:
            await asyncio.sleep(10)
            async for m in app.get_chat_history(BOT, limit=12):
                if m.id <= start_id or not (m.from_user and m.from_user.is_bot):
                    continue
                txt = m.text or m.caption or ""
                if m.video:
                    print("[%4.0fs] VIDEO delivered: %s" % (time.time() - t0, txt.replace("\n", " / ")), flush=True)
                    print("RESULT PASS: Somali trailer delivered through /trailer")
                    return
                if txt.startswith("🎬 **Somali trailer**") or txt.startswith("🎬 Somali trailer"):
                    if txt != last_status:
                        last_status = txt
                        print("[%4.0fs] status: %s" % (time.time() - t0, txt[:220].replace("\n", " / ")), flush=True)
                    if "❌" in txt or "⛔" in txt:
                        print("RESULT FAIL: job stopped")
                        return
                bs = buttons(m)
                picks = [b for b in bs if b.startswith("trl:pick:")]
                if not picks or not m.voice:
                    continue
                pos = int(picks[0].split(":")[2])
                if pos in done_pos or "➡️" in txt:
                    continue
                if jobdir is None:
                    jobdir = sorted(glob.glob("/opt/dubsync2/trailers_out/jobs/*/job.json"), key=os.path.getmtime)[-1]
                job = json.load(open(jobdir))
                qs = [c["i"] for c in job["cues"] if not c.get("auto") and c.get("suggest")]
                is_page2 = "Somali 4, 5, 6" in txt
                i = qs[pos]
                sug = job["cues"][i]["suggest"]
                k = 0
                if i in TRUTH:
                    k = next((n for n, s in enumerate(sug, 1)
                              if s["film_t"] - 2.0 <= TRUTH[i] <= s["film_t1"] + 0.5), 0)
                if not used_more and not is_page2 and k == 0 and any(b.startswith("trl:more:") for b in bs):
                    used_more = True
                    print("[%4.0fs] Q%d line %d: pressing 4-6" % (time.time() - t0, pos + 1, i + 1), flush=True)
                    await click(app, m.id, "trl:more:%d" % pos)
                    continue
                if is_page2 and not (4 <= k <= 6):
                    k = 0
                if not is_page2 and k > 3:
                    await click(app, m.id, "trl:more:%d" % pos)
                    continue
                done_pos.add(pos)
                print("[%4.0fs] Q%d line %d %-38s -> %s" % (time.time() - t0, pos + 1, i + 1,
                                                          job["cues"][i]["text"][:38], k or "None"), flush=True)
                await click(app, m.id, "trl:pick:%d:%d" % (pos, k))
        print("RESULT TIMEOUT")


asyncio.run(main())
