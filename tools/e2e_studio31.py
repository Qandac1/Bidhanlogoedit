"""End-to-end through Telegram (John's userbot): THE STUDIO (bot30 + bot31).
  1  /studio -> the bot answers with a keyboard button that opens the Studio page (place.html?t=<token>)
  2  over HTTPS: the page, its cfg.json (both sets, 8 fonts, the colours), every logo image and every font file
  3  an EMPTY save (what the page sends when nothing was touched) -> "Nothing was changed."
  4  --save-same: the DUB-SYNC set's caption is sent back with EXACTLY its current values -> "Studio saved" with a
     preview picture; John's stored settings are compared before / after (must be equal: nothing changes).
Nothing else is sent; no setting is changed.
Usage: /opt/media-os/venv/bin/python e2e_studio31.py [--save-same]
Prints STUDIO_URL, PAGE, CFG, IMG, FONT, EMPTY, SAVED, SETTINGS, E2E_STUDIO OK | FAILED."""
import asyncio
import json
import sys
import urllib.request

from pyrogram import Client
from pyrogram.raw import functions

BOT = "BidhaanLogoEdit_bot"
SAVE = "--save-same" in sys.argv
SETTINGS = "/var/lib/docker/volumes/bidhanlogoedit_bot_data/_data/user_settings.json"


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "e2e"}), timeout=20) as r:
            return r.status, r.read()
    except Exception as e:
        return getattr(e, "code", 0) or 0, b""


def record(uid):
    try:
        return json.load(open(SETTINGS)).get(str(uid))
    except Exception as e:
        return {"error": str(e)}


async def answers(app, mark, tries=20):
    out = []
    for _ in range(tries):
        await asyncio.sleep(2)
        out = [m async for m in app.get_chat_history(BOT, limit=6) if m.id > mark and m.from_user and m.from_user.is_bot]
        if out:
            await asyncio.sleep(3)                      # the preview picture follows the text
            out = [m async for m in app.get_chat_history(BOT, limit=6) if m.id > mark and m.from_user and m.from_user.is_bot]
            break
    return out


async def main():
    ok = True
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data", no_updates=True)
    async with app:
        me = (await app.get_me()).id
        before = record(me)
        mark = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.send_message(BOT, "/studio")
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
        if not url or "t=" not in url:
            print("NO STUDIO BUTTON in the bot's answer (%r)" % url)
            print("E2E_STUDIO FAILED")
            return
        base, token = url.split("place.html")[0], url.split("t=", 1)[1].split("&")[0]
        print("STUDIO_URL %splace.html?t=...  button %r" % (base, btn))
        c, body = get(url)
        print("PAGE %d (%d bytes) | studio page: %s" % (c, len(body), b"cfg.json" in body and b"Timeline" in body))
        ok &= c == 200 and len(body) > 20000 and b"cfg.json" in body
        c, body = get("%st/%s/cfg.json" % (base, token))
        cfg = json.loads(body) if c == 200 else {}
        sets = cfg.get("sets") or {}
        print("CFG %d | v %s | active %s | sets %s | fonts %d | colours %d" % (c, cfg.get("v"), cfg.get("active"), sorted(sets), len(cfg.get("fonts") or []), len(cfg.get("colors") or [])))
        ok &= c == 200 and cfg.get("v") == 3 and sorted(sets) == ["banner", "dub"] and len(cfg.get("fonts") or []) == 8
        for prof in ("banner", "dub"):
            s = sets.get(prof) or {}
            print("  %-6s start %s s | caption %r font %r colour %r | logos %s" % (
                prof, s.get("start"), ((s.get("cap") or {}).get("text") or "")[:28], (s.get("cap") or {}).get("font"), (s.get("cap") or {}).get("color"),
                [(x["n"], "on" if x["on"] else "off", round(x["mx"], 3), round(x["my"], 3), round(x["w"], 3)) for x in s.get("logos") or []]))
        seen = set()
        for prof in sets:
            for x in sets[prof].get("logos") or []:
                if x["img"] in seen:
                    continue
                seen.add(x["img"])
                c, body = get(base + x["img"])
                print("IMG %s %d (%d bytes)" % (x["n"], c, len(body)))
                ok &= c == 200 and len(body) > 500
        for f in cfg.get("fonts") or []:
            c, body = get(base + f["file"])
            print("FONT %-10s %d (%d bytes)" % (f["label"], c, len(body)))
            ok &= c == 200 and len(body) > 10000
        peer = await app.resolve_peer(BOT)
        mark2 = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
        await app.invoke(functions.messages.SendWebViewData(bot=peer, random_id=app.rnd_id(), button_text=btn,
                                                            data=json.dumps({"k": "studio", "v": 3, "sets": {}})))
        got = await answers(app, mark2)
        txt = " | ".join((m.text or "") for m in got)
        print("EMPTY save -> %r" % txt[:80])
        ok &= "Nothing was changed" in txt
        if SAVE:
            cap = (sets.get("dub") or {}).get("cap")
            if not cap:
                print("no caption block in the dub-sync set -- the same-values save is skipped")
            else:
                mark3 = [m.id async for m in app.get_chat_history(BOT, limit=1)][0]
                await app.invoke(functions.messages.SendWebViewData(bot=peer, random_id=app.rnd_id(), button_text=btn,
                                                                    data=json.dumps({"k": "studio", "v": 3, "sets": {"dub": {"cap": cap}}})))
                got = await answers(app, mark3)
                txt = " | ".join((m.text or "").replace("\n", " | ") for m in got if m.text)
                photo = any(m.photo for m in got)
                # the bot sends a preview only when there is something to show (a logo that is on, or a caption)
                need = bool(cap.get("text")) or any(x["on"] for x in (sets.get("dub") or {}).get("logos") or [])
                print("SAVED %s | preview picture: %s (%s)" % (txt[:260] or "NO ANSWER", photo, "expected" if need else "none expected: no logo on, no caption"))
                ok &= "Studio saved" in txt and (photo or not need)
        await asyncio.sleep(2)
        after = record(me)

        def flat(d, pre=""):
            out = {}
            for k, v in (d or {}).items():
                if isinstance(v, dict):
                    out.update(flat(v, pre + k + "."))
                else:
                    out[pre + k] = v
            return out

        fb, fa = flat(before), flat(after)
        diff = []
        for k in sorted(set(fb) | set(fa)):
            x, y = fb.get(k), fa.get(k)
            if x == y:
                continue
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool) and abs(float(x) - float(y)) < 1e-9:
                continue
            # the two settings bot31 brought are written out with their defaults on a save: the same look as before
            if x is None and ((k.endswith("caption_font") and y == "") or (k.endswith("caption_color") and y == "white")):
                continue
            diff.append((k, x, y))
        print("SETTINGS before / after the test: %s%s" % ("EQUAL (%d values)" % len(fa) if not diff else "DIFFERENT", "" if not diff else " " + str(diff)[:500]))
        ok &= not diff
    print("E2E_STUDIO " + ("OK" if ok else "FAILED"))


asyncio.run(main())
