"""bot29 = live bot + THE LOGO ANYWHERE (/logopos page, /logoset, the save through Telegram's web_app_data).
Run inside the bot container:   python3 test_bot_logoplace29.py <live bot dir copy> <bot29 dir copy>
Nothing is sent anywhere (fake messages); the settings go to a TEMPORARY file, never the bot's own.
  A. NO BREAK: with untouched settings the brand settings handed to the renders are the live bot's; every
     settings menu is the same except ONE new row in Logos.
  B. What the page sends is cleaned: unknown names, doubles, garbage dropped; size 3-70 %; the logo kept inside.
  C. A saved place reaches the renders: corner TL, margins = left / top, width = size (also when the global
     size multiplier is not 100 %); the other logos and settings are untouched.
  D. REAL ffmpeg with the bot's own render filter: the logo lands at the chosen place and size.
  E. Opening the page: the logos that are ON are copied into a fresh folder, the link carries them; no logo on ->
     a plain message, no folder left; old folders are swept, fresh ones kept.
  F. /logoset: good numbers saved + answered + preview picture; bad input -> the usage line, nothing changed;
     a named logo is switched on; a user who is not allowed -> nothing.
  G. The save coming from the page (web_app_data): saved; another kind of data / broken JSON -> ignored.
  H. The page file and the bot agree on the names of the fields.
Prints LOGOPLACE29_TESTS ALL PASS."""
import asyncio
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

LIVE, NEW = sys.argv[1], sys.argv[2]
T = tempfile.mkdtemp(prefix="lp29_")
os.environ["BIDHAAN_WEB_PUBLIC"] = os.path.join(T, "web")
os.environ["BIDHAAN_WEB_BASE"] = "https://example.test/logo"


def load(d, name):
    sys.path.insert(0, d)
    cwd = os.getcwd()
    os.chdir(d)
    try:
        for k in ("branding", "detect", "config", "delivery", "trim", "dub_queue", "dubsync_job"):
            sys.modules.pop(k, None)
        spec = importlib.util.spec_from_file_location(name, os.path.join(d, "bot.py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
    finally:
        os.chdir(cwd)
        sys.path.remove(d)
    m.SETTINGS_FILE = os.path.join(T, name + "_settings.json")       # never the bot's own settings
    m._allowed = lambda uid: uid != 999
    return m


old, new = load(LIVE, "bot_live"), load(NEW, "bot_29")
UID = 424243
ok = True
SENT = []


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


class FakeMsg:
    def __init__(self, text="", uid=UID, web=None, photo=None):
        self.text, self.caption, self.video, self.document, self.photo = text, None, None, None, photo
        self.from_user = SimpleNamespace(id=uid)
        self.chat = SimpleNamespace(id=uid)
        self.reply_to_message = None
        self.web_app_data = SimpleNamespace(data=web) if web is not None else None

    async def reply(self, text, reply_markup=None, **kw):
        SENT.append(("text", text, reply_markup))
        return FakeMsg(text)

    async def reply_photo(self, photo, caption="", **kw):
        SENT.append(("photo", photo, caption, os.path.getsize(photo) if os.path.exists(photo) else 0))
        return FakeMsg(caption)


def run(coro):
    SENT.clear()
    asyncio.run(coro)
    return list(SENT)


def kb_dump(km):
    return [[(b.text, getattr(b, "callback_data", None)) for b in row] for row in km.inline_keyboard]


# ---- A. no break ------------------------------------------------------------------------------------------
check("A: untouched settings -> the brand settings for the renders are the live bot's",
      old._brand_payload(UID) == new._brand_payload(UID), (old._brand_payload(UID), new._brand_payload(UID)))
diff = []
for which in ("logos", "trim", "text", "output", "times", "cover"):
    try:
        a, b = kb_dump(old.submenu(which, UID, None)), kb_dump(new.submenu(which, UID, None))
    except Exception as e:
        a, b = "ERR %r" % e, None
        try:
            b = kb_dump(new.submenu(which, UID, None))
        except Exception as e2:
            b = "ERR %r" % e2
    if which == "logos":
        extra = [r for r in b if r not in a]
        check("A: Settings -> Logos has ONE new row (the place button), every old row still there in order",
              [r for r in b if r in a] == a and extra == [[("🎨 Logo studio — move, size, time", "lg:place:open")]], (a, b))
    elif a != b:
        diff.append(which)
check("A: the other settings menus are the same", not diff, diff)

# ---- B. cleaning ------------------------------------------------------------------------------------------
C = new._place_clean
cases = [
    ([{"n": "bidhaan2", "x": 0.12, "y": 0.08, "w": 0.15}], [("bidhaan2", 0.12, 0.08, 0.15, True)]),
    ([{"n": "bidhaan2", "x": -0.5, "y": 2.0, "w": 0.15}], [("bidhaan2", 0.0, 0.98, 0.15, True)]),
    ([{"n": "bidhaan2", "x": 0.95, "y": 0.5, "w": 0.2}], [("bidhaan2", 0.8, 0.5, 0.2, True)]),
    ([{"n": "bidhaan2", "x": 0.1, "y": 0.1, "w": 5}], [("bidhaan2", 0.1, 0.1, 0.7, True)]),
    ([{"n": "bidhaan2", "x": 0.1, "y": 0.1, "w": 0.0001}], [("bidhaan2", 0.1, 0.1, 0.03, True)]),
    ([{"n": "evil", "x": 0.1, "y": 0.1, "w": 0.2}], []),
    ([{"n": "bidhaan", "x": 0.1, "y": 0.1, "w": 0.2}, {"n": "bidhaan", "x": 0.5, "y": 0.5, "w": 0.2}], [("bidhaan", 0.1, 0.1, 0.2, True)]),
    ([{"n": "streamnxt", "x": "a", "y": 0.1, "w": 0.2}, {"n": "bidhaan2", "x": "0.25", "y": "0.5", "w": "0.1"}], [("bidhaan2", 0.25, 0.5, 0.1, True)]),
    ([{"n": "bidhaan2", "x": 0.1, "y": 0.1, "w": 0.2, "on": False}], [("bidhaan2", 0.1, 0.1, 0.2, False)]),
    ([{"n": "bidhaan2", "x": 0.1, "y": 0.1, "w": 0.2, "on": True}, {"n": "streamnxt", "x": 0.5, "y": 0.5, "w": 0.1, "on": 0}],
     [("bidhaan2", 0.1, 0.1, 0.2, True), ("streamnxt", 0.5, 0.5, 0.1, True)]),
    ([{"n": "bidhaan2", "x": float("nan"), "y": 0.1, "w": 0.2}], []),
    ([{"n": "bidhaan2", "x": float("inf"), "y": 0.1, "w": 0.2}], []),
    (None, []), ("garbage", []), ({"n": "bidhaan2"}, []), ([1, None, "x", []], []), ([{}], []),
]
try:
    bad = [(i, C(i), o) for i, o in cases if C(i) != o]
    check("B: %d things the page could send -> cleaned or dropped (a logo is off only on a clear false)" % len(cases), not bad, bad)
    S = new._place_start
    st = [(S(20), 20.0), (S("45"), 45.0), (S(-5), 0.0), (S(1e7), 10800.0), (S(12.6), 13.0), (S(None), None), (S("x"), None),
          (S(float("nan")), None), (S([1]), None)]
    check("B: the second the logo appears -> 0 .. 3 h, whole seconds, garbage dropped", all(a == b for a, b in st), st)
except Exception as e:
    check("B: cleaning never raises", False, repr(e))

# ---- C. a saved place reaches the renders -------------------------------------------------------------------
new.set_user(UID, logo_scale=1.25, streamnxt_on=True)
before = new._brand_payload(UID)
lines = new._place_apply(UID, C([{"n": "bidhaan2", "x": 0.3, "y": 0.4, "w": 0.2}]))
after = new._brand_payload(UID)
lg = [x for x in after["logos"] if abs(x["margin_x"] - 0.3) < 1e-9]
check("C: the renders get corner TL, left 30 %, top 40 %, width 20 % (size multiplier 125 % taken out)",
      len(lg) == 1 and lg[0]["corner"] == "TL" and abs(lg[0]["margin_y"] - 0.4) < 1e-9 and abs(lg[0]["frac"] - 0.2) < 1e-4, after["logos"])
check("C: the answer says it in plain numbers", lines == ["• Bidhaan L: left 30.0 %, top 40.0 %, size 20.0 % of the picture's width"], lines)
others_b = [x for x in before["logos"] if "streamnxt" in x["path"]]
others_a = [x for x in after["logos"] if "streamnxt" in x["path"]]
check("C: the other logo and every other setting are untouched",
      others_a == others_b and {k: v for k, v in after.items() if k != "logos"} == {k: v for k, v in before.items() if k != "logos"},
      (others_b, others_a))

# ---- D. real ffmpeg, the bot's own render filter ------------------------------------------------------------
BLUE = os.path.join(T, "blue.png")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=blue:size=60x20", "-frames:v", "1", BLUE], check=True)
new.set_user(UID, custom_logo=BLUE, logo_scale=1.0, streamnxt_on=False, bidhaan_on=False)
new._place_apply(UID, C([{"n": "bidhaan2", "x": 0.3, "y": 0.4, "w": 0.2}]))
import branding  # noqa: E402  (the patched copy's own, loaded with bot_29)
pay = new._brand_payload(UID)
cfg = branding.RenderConfig(logos=[branding.Logo(**x) for x in pay["logos"]], cover_png=BLUE, scroll_text="",
                            width=640, height=360, logo_start=0.0)
fc = branding.build_filter(640, 360, 1.0, [], cfg)
raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=640x360:r=25", "-i", BLUE, "-i", BLUE,
                      "-filter_complex", fc + ";[outv]format=rgb24[g]", "-map", "[g]", "-frames:v", "1",
                      "-f", "rawvideo", "-"], capture_output=True).stdout
xs, ys = [], []
for i in range(0, len(raw), 3):
    if raw[i + 2] > 180 and raw[i] < 90 and raw[i + 1] < 90:
        p = i // 3
        xs.append(p % 640)
        ys.append(p // 640)
bb = (min(xs), min(ys), max(xs) - min(xs) + 1) if xs else None
check("D: in a real frame the logo's left edge is at 192 px (30 %%), its top at 144 px (40 %%), 128 px wide (20 %%): %s" % (bb,),
      bb is not None and abs(bb[0] - 192) <= 2 and abs(bb[1] - 144) <= 2 and abs(bb[2] - 128) <= 2, (bb, fc))

# ---- E. opening the page ------------------------------------------------------------------------------------
m = FakeMsg("/logopos")
sent = run(new._place_open(m, UID, None))
root = os.path.join(T, "web", "t")
dirs = os.listdir(root) if os.path.isdir(root) else []
kb = sent[0][2] if sent else None
url = kb.keyboard[0][0].web_app.url if kb is not None and hasattr(kb, "keyboard") else ""
check("E: one message with a keyboard button that opens the page at the web address",
      len(sent) == 1 and url.startswith("https://example.test/logo/place.html?d=") and kb.keyboard[0][0].text == "🎨 Open Logo studio", (sent, url))
d = url.split("d=", 1)[1] if "d=" in url else ""
pl = json.loads(base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)).decode()) if d else {}
byn = {x["n"]: x for x in pl.get("logos", [])}
check("E: the link carries EVERY logo with its switch (Bidhaan L on at 30 / 40 / 20 %, the others off), images in a fresh folder",
      len(dirs) == 1 and set(byn) == {"bidhaan2", "bidhaan", "streamnxt"} and byn["bidhaan2"]["on"] is True
      and byn["bidhaan"]["on"] is False and byn["streamnxt"]["on"] is False and byn["bidhaan2"]["c"] == "TL"
      and abs(byn["bidhaan2"]["mx"] - 0.3) < 1e-9 and abs(byn["bidhaan2"]["w"] - 0.2) < 1e-4
      and all(os.path.exists(os.path.join(T, "web", x["img"])) for x in pl["logos"]) and pl["bg"] == "", (dirs, pl))
new.set_user(UID, logo_start_min=20 / 60.0)
sent2 = run(new._place_open(FakeMsg("/logopos"), UID, None))
u2 = sent2[0][2].keyboard[0][0].web_app.url.split("d=", 1)[1]
pl2 = json.loads(base64.urlsafe_b64decode(u2 + "=" * (-len(u2) % 4)).decode())
check("E: ... and the second the logo appears (20 s)", pl2.get("start") == 20, pl2.get("start"))
shutil.rmtree(os.path.join(root, [d_ for d_ in os.listdir(root) if d_ != dirs[0]][0]), ignore_errors=True)
check("E: the folder name cannot be guessed (16 characters, new every time)", len(dirs) == 1 and len(dirs[0]) >= 16, dirs)
new.set_user(UID, bidhaan2_on=False)
sent = run(new._place_open(FakeMsg("/logopos"), UID, None))
check("E: every logo switched off -> the studio still opens (they can be switched on there)",
      len(sent) == 1 and sent[0][2] is not None and len(os.listdir(root)) == 2, sent)
shutil.rmtree(os.path.join(root, [d_ for d_ in os.listdir(root) if d_ != dirs[0]][0]), ignore_errors=True)
keep_asset, keep_user = new._asset, new._user_logo
new._asset = lambda name: os.path.join(T, "missing_" + name)
new._user_logo = lambda c: os.path.join(T, "missing_logo.png")
sent = run(new._place_open(FakeMsg("/logopos"), UID, None))
new._asset, new._user_logo = keep_asset, keep_user
check("E: no logo image at all -> a plain message, no button, no folder left",
      len(sent) == 1 and sent[0][2] is None and "No logo image was found" in sent[0][1] and len(os.listdir(root)) == 1, sent)
new.set_user(UID, bidhaan2_on=True)
oldp = os.path.join(root, "old_one")
os.makedirs(oldp)
os.utime(oldp, (time.time() - 3 * 3600,) * 2)
new._place_sweep()
check("E: a folder older than 2 hours is swept, the fresh one kept", not os.path.exists(oldp) and os.path.isdir(os.path.join(root, dirs[0])))

# ---- F. /logoset --------------------------------------------------------------------------------------------
sent = run(new._cmd_logoset(None, FakeMsg("/logoset 12 8 15")))
c = new.user_cfg(UID)
check("F: /logoset 12 8 15 -> saved (left 12 %, top 8 %, size 15 %), answered",
      abs(c["bidhaan2_mx"] - 0.12) < 1e-9 and abs(c["bidhaan2_my"] - 0.08) < 1e-9 and abs(c["bidhaan2_frac"] - 0.15) < 1e-9
      and c["bidhaan2_corner"] == "TL" and sent and "left 12.0 %, top 8.0 %, size 15.0 %" in sent[0][1], (sent, c["bidhaan2_mx"]))
ph = [x for x in sent if x[0] == "photo"]
check("F: ... and a preview picture made by the real render filter (%s bytes)" % (ph[0][3] if ph else 0), len(ph) == 1 and ph[0][3] > 2000, sent)
sent = run(new._cmd_logoset(None, FakeMsg("/logoset left top")))
c2 = new.user_cfg(UID)
check("F: bad input -> the usage line, nothing changed", len(sent) == 1 and "Use: `/logoset" in sent[0][1] and c2 == c, sent)
sent = run(new._cmd_logoset(None, FakeMsg("/logoset streamnxt 5% 6% 10%")))
c3 = new.user_cfg(UID)
check("F: a named logo is placed and switched on; the first logo stays where it was",
      c3["streamnxt_on"] is True and abs(c3["streamnxt_mx"] - 0.05) < 1e-9 and abs(c3["streamnxt_frac"] - 0.10) < 1e-9
      and abs(c3["bidhaan2_mx"] - 0.12) < 1e-9, c3)
sent = run(new._cmd_logoset(None, FakeMsg("/logoset 50 50 50", uid=999)))
check("F: a user who is not allowed -> nothing sent, nothing stored", sent == [] and new._load().get("999") is None, sent)

# ---- G. the save coming from the page -----------------------------------------------------------------------
web = json.dumps({"k": "logo_place", "v": 2, "start": 45, "logos": [
    {"n": "bidhaan2", "on": True, "x": 0.4444, "y": 0.6, "w": 0.25}, {"n": "streamnxt", "on": False, "x": 0.05, "y": 0.06, "w": 0.1}]})
sent = run(new._on_web_app_data(None, FakeMsg("", web=web)))
c4 = new.user_cfg(UID)
check("G: the studio's Save -> stored (left 44.4 %, top 60 %, size 25 %), the keyboard taken away",
      abs(c4["bidhaan2_mx"] - 0.4444) < 1e-9 and abs(c4["bidhaan2_my"] - 0.6) < 1e-9 and abs(c4["bidhaan2_frac"] - 0.25) < 1e-9
      and sent and "Logo saved" in sent[0][1] and type(sent[0][2]).__name__ == "ReplyKeyboardRemove", sent[:1])
check("G: ... the other logo switched OFF as the studio said, the logo's start time 45 s -- both reach the renders",
      c4["streamnxt_on"] is False and c4["bidhaan2_on"] is True and abs(c4["logo_start_min"] * 60 - 45) < 1e-6
      and abs(new._brand_payload(UID)["logo_start"] - 45.0) < 1e-6 and len(new._brand_payload(UID)["logos"]) == 1
      and "switched off" in sent[0][1] and "appears from 45s" in sent[0][1], (sent[:1], new._brand_payload(UID)))
check("G: the logo switched off keeps its stored place (left 5 %, size 10 %)",
      abs(c4["streamnxt_mx"] - 0.05) < 1e-9 and abs(c4["streamnxt_frac"] - 0.10) < 1e-9, (c4["streamnxt_mx"], c4["streamnxt_frac"]))
webk = json.dumps({"k": "logo_place", "v": 2, "logos": [
    {"n": "bidhaan2", "on": True, "x": 0.4444, "y": 0.6, "w": 0.25}, {"n": "bidhaan", "on": False, "x": 0.7, "y": 0.7, "w": 0.3},
    {"n": "streamnxt", "on": False, "x": 0.9, "y": 0.9, "w": 0.5}]})
sent = run(new._on_web_app_data(None, FakeMsg("", web=webk)))
ck = new.user_cfg(UID)
check("G: logos that were off and stay off are not touched at all (corner, place, size as before; no line about them)",
      all(ck[k] == c4[k] for k in ck if k.startswith(("bidhaan_", "streamnxt_"))) and sent and "Bidhaan R" not in sent[0][1]
      and "StreamNxt" not in sent[0][1], ({k: (c4[k], ck[k]) for k in ck if ck[k] != c4[k]}, sent[:1]))
web1 = json.dumps({"k": "logo_place", "v": 1, "logos": [{"n": "bidhaan2", "x": 0.4444, "y": 0.6, "w": 0.25}]})
sent = run(new._on_web_app_data(None, FakeMsg("", web=web1)))
check("G: a save WITHOUT a start time leaves the start time alone",
      abs(new.user_cfg(UID)["logo_start_min"] * 60 - 45) < 1e-6 and sent and "appears from" not in sent[0][1], sent[:1])
for label, w in (("another kind of data", json.dumps({"k": "other", "logos": [{"n": "bidhaan2", "x": 0, "y": 0, "w": 0.5}]})),
                 ("broken JSON", "{not json"), ("a list", "[1,2]")):
    sent = run(new._on_web_app_data(None, FakeMsg("", web=w)))
    check("G: %s -> ignored" % label, sent == [] and new.user_cfg(UID) == c4, sent)
sent = run(new._on_web_app_data(None, FakeMsg("", uid=999, web=web)))
check("G: from a user who is not allowed -> ignored", sent == [], sent)

# ---- H. the page and the bot agree --------------------------------------------------------------------------
page = os.path.join(NEW, "web_public", "place.html")
txt = open(page, encoding="utf-8").read() if os.path.exists(page) else ""
check("H: web_public/place.html is there and speaks the bot's language (logo_place, n / on / x / y / w, start, sendData)",
      all(k in txt for k in ('k: "logo_place"', "n: it.n", "on: !!it.on", "x: +it.x", "y: +it.y", "w: +it.w", "start: startT",
                             "tg.sendData", "/logoset ", "/logoat ", "telegram-web-app.js", "L.mx", "L.my", "L.c", "L.img",
                             "L.on", "P.start")), len(txt))

shutil.rmtree(T, ignore_errors=True)
print("LOGOPLACE29_TESTS " + ("ALL PASS" if ok else "FAILED") + "  (LOGOSTUDIO v2)")
sys.exit(0 if ok else 1)
