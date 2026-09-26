"""End-to-end through Telegram (John's userbot): the new pair check at job start.

  A  wrong pair  : Battle of Defense HD (59529) + CBI 5 Somali dub (59562)
                   -> must stop with "Pre-flight check failed ... pictures do not match"
  B  swapped pair: Battle of Defense Somali dub sent FIRST as the HD (copied without
                   its caption, so the name check cannot tell) + the real HD second
                   -> must say "swapped", pass the check, start the engine; then the
                   test presses Cancel so it does not run a 1.5 h job.
Usage: e2e_paircheck.py A|B"""
import asyncio
import sys
import time

from pyrogram import Client

BOT = "BidhaanLogoEdit_bot"
TESTS = {"A": {"first": 59529, "second": 59562, "strip": False},
         "B": {"first": 59530, "second": 59529, "strip": True}}


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def buttons(m):
    if not m.reply_markup or not getattr(m.reply_markup, "inline_keyboard", None):
        return []
    return [b.callback_data for row in m.reply_markup.inline_keyboard for b in row]


async def main(which):
    t = TESTS[which]
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        last = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.send_message(BOT, "/dub")
        await asyncio.sleep(4)
        for mid in (t["first"], t["second"]):
            if t["strip"]:
                await app.copy_message(BOT, BOT, mid, caption="")
            else:
                await app.forward_messages(BOT, BOT, mid)
            await asyncio.sleep(5)
        panel = None
        for _ in range(10):
            async for m in app.get_chat_history(BOT, limit=6):
                if m.id > last and "dub:start" in buttons(m):
                    panel = m
                    break
            if panel:
                break
            await asyncio.sleep(3)
        if not panel:
            print("FAIL: no dub panel appeared")
            return 1
        print("panel", panel.id, "->", (panel.text or "")[:200].replace("\n", " / "))
        try:
            await app.request_callback_answer(BOT, panel.id, "dub:start", timeout=10)
        except Exception as exc:          # the bot may answer late; the click still lands
            print("callback answer:", type(exc).__name__)
        t0, seen, verdict = time.time(), set(), None
        while time.time() - t0 < 1500 and verdict is None:
            await asyncio.sleep(15)
            async for m in app.get_chat_history(BOT, limit=8):
                if m.id < panel.id or not (m.from_user and m.from_user.is_bot):
                    continue
                txt = (m.text or m.caption or "")
                key = (m.id, txt[:120])
                if key not in seen:
                    seen.add(key)
                    print("[%4.0fs] %d: %s" % (time.time() - t0, m.id, txt[:300].replace("\n", " / ")), flush=True)
                if which == "A":
                    if "Pre-flight check failed" in txt:
                        verdict = "PASS" if "pictures do not match" in txt else "FAIL (other pre-flight reason)"
                    elif any(s in txt for s in ("Preparing master", "Analysing shots")):
                        verdict = "FAIL: wrong pair was NOT stopped"
                else:
                    swapped = any("swapped them" in (x[1] or "") for x in seen)
                    if "Pre-flight check failed" in txt:
                        verdict = "FAIL: real pair was refused"
                    elif swapped and any(s in txt for s in ("Preparing master", "Analysing shots")):
                        try:
                            await app.request_callback_answer(BOT, m.id, "cancel", timeout=10)
                        except Exception:
                            pass
                        verdict = "PASS (swapped, check passed, engine started; test cancelled the job)"
                    elif not swapped and any(s in txt for s in ("Analysing shots",)):
                        verdict = "FAIL: engine started without the swap"
                if verdict:
                    break
        print("RESULT %s: %s  (%.0f s after Start)" % (which, verdict or "TIMEOUT", time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
