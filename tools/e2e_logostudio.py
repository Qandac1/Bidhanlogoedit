"""End-to-end through Telegram (John's userbot): the LOGO STUDIO (bot29).
  1  /logopos -> the bot must answer with a keyboard button that opens the studio page
  2  the page and every logo image of the link must load over HTTPS (HTTP 200)
  3  --save-same: the studio's Save is sent back through Telegram (messages.SendWebViewData, what the page's
     Save does) with the logos that are ON at EXACTLY their current place and size and NO start time -- so
     nothing in John's settings changes -- and the bot must answer "Logo saved" with a preview picture.
Usage: /opt/media-os/venv/bin/python e2e_logostudio.py [--save-same]
Prints STUDIO_URL, PAGE <code>, IMG <name> <code>, SAVED ..., E2E_LOGOSTUDIO OK | FAILED."""
import asyncio
import base64
import json
import sys
import urllib.request

from pyrogram import Client
from pyrogram.raw import functions

BOT = "BidhaanLogoEdit_bot"
SAVE = "--save-same" in sys.argv


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def code(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "e2e"}), timeout=20) as r:
            return r.status, len(r.read())
    except Exception as e:
        return getattr(e, "code", 0) or 0, 0


async def main():
    ok = True
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data", no_updates=True)
    async with app:
        mark = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.send_message(BOT, "/logopos")
        url, btn = "", ""
        for _ in range(15):
            await asyncio.sleep(2)
            async for m in app.get_chat_history(BOT, limit=4):
                kb = getattr(m.reply_markup, "keyboard", None)
                if m.id > mark and kb:
                    b = kb[0][0]
                    w = getattr(b, "web_app", None)
                    if w is not None:
                        url, btn = w.url, b.text
            if url:
                break
        if not url:
            print("NO STUDIO BUTTON in the bot's answer")
            print("E2E_LOGOSTUDIO FAILED")
            return
        print("STUDIO_URL %s...  button %r" % (url.split("?")[0], btn))
        d = url.split("d=", 1)[1]
        pay = json.loads(base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)).decode())
        print("PAYLOAD start %s s | %s" % (pay.get("start"), [(x["n"], "on" if x["on"] else "off", x["c"], round(x["mx"], 4),
                                                             round(x["my"], 4), round(x["w"], 4)) for x in pay["logos"]]))
        c, n = code(url)
        print("PAGE %d (%d bytes)" % (c, n))
        ok &= c == 200 and n > 5000
        base = url.split("place.html")[0]
        for x in pay["logos"]:
            c, n = code(base + x["img"])
            print("IMG %s %d (%d bytes)" % (x["n"], c, n))
            ok &= c == 200 and n > 500
        if SAVE:
            same = [{"n": x["n"], "on": True, "x": x["mx"], "y": x["my"], "w": x["w"]} for x in pay["logos"] if x["on"] and x["c"] == "TL"]
            if not same:
                print("no logo is ON at a top-left place -- the no-change save is skipped")
            else:
                mark2 = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
                await app.invoke(functions.messages.SendWebViewData(
                    bot=await app.resolve_peer(BOT), random_id=app.rnd_id(), button_text=btn,
                    data=json.dumps({"k": "logo_place", "v": 2, "logos": same})))
                got, photo = "", False
                for _ in range(20):
                    await asyncio.sleep(2)
                    async for m in app.get_chat_history(BOT, limit=5):
                        if m.id > mark2 and m.from_user and m.from_user.is_bot:
                            if "Logo saved" in (m.text or ""):
                                got = (m.text or "").replace("\n", " | ")
                            if m.photo:
                                photo = True
                    if got and photo:
                        break
                print("SAVED %s | preview picture: %s" % (got[:230] or "NO ANSWER", photo))
                ok &= bool(got) and photo
    print("E2E_LOGOSTUDIO " + ("OK" if ok else "FAILED"))


asyncio.run(main())
