"""bot36, before it is installed: A REAL OPENING OF THE STUDIO made by the PATCHED bot copy, for a look in a browser.
Run inside the bot container (nice):  python3 stage_site36.py <patched bot dir> <out site dir> <a video> [uid]
Loads the patched bot.py the way the tests do (nothing is started, nothing is sent), reads the user's REAL settings
(read only), and writes into <out site dir>/t/<token>/ what /studio would write for a waiting banner video: cfg.json
(both sets, 20 fonts with their line pitch), the logo images, frame.jpg, frames.json and the 24 pictures of <video>.
Prints  STAGE_SITE token=<token> fonts=<n> frames=<n> caption=<the banner caption as stored, repr>"""
import asyncio
import importlib.util
import json
import os
import sys

NEW, OUT, VID = sys.argv[1], sys.argv[2], sys.argv[3]
os.environ["BIDHAAN_WEB_PUBLIC"] = OUT
sys.path.insert(0, NEW)
os.chdir(NEW)
spec = importlib.util.spec_from_file_location("bot_stage36", os.path.join(NEW, "bot.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["bot_stage36"] = m
spec.loader.exec_module(m)
import branding as br  # noqa: E402

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
br.FONT_DIRS = (FONTS,) + tuple(br.FONT_DIRS)
users = json.load(open(m.SETTINGS_FILE)) if os.path.exists(m.SETTINGS_FILE) else {}
uid = int(sys.argv[4]) if len(sys.argv) > 4 else int(max(users, key=lambda k: len(json.dumps(users[k]))) if users else 1)
token = "stage36" + os.urandom(6).hex()
d = os.path.join(OUT, "t", token)
os.makedirs(d, exist_ok=True)
_w, _h, dur = br.probe(VID)


async def go():
    prof = m._profile_of(uid)
    m._ui_profile[uid] = "banner"                      # in THIS process only: the banner flow
    m._pending[uid] = {"src": VID, "duration": dur, "w": _w, "h": _h, "name": os.path.basename(VID)}
    ok = await m._studio_frames_start(uid, VID, dur, d, token)
    cfg = m._studio_cfg(uid, token, ok, dur, ok)
    tk = m._studio_tasks.get(uid)
    if tk is not None:
        await tk
    return cfg, prof


cfg, prof = asyncio.run(go())
fj = json.load(open(os.path.join(d, "frames.json")))
print("STAGE_SITE token=%s fonts=%d frames=%d done=%s dur=%.1f caption=%r active=%s"
      % (token, len(cfg["fonts"]), len(fj["frames"]), fj["done"], dur, cfg["sets"]["banner"]["cap"]["text"], cfg["active"]))
