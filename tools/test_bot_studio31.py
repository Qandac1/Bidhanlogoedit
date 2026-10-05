"""bot31 part 2 = THE STUDIO (patch_bot_studio31.py) on top of bot30 (two sets of settings) and bot31 part 1
(caption font / colour).  Run inside the bot container:
    python3 test_bot_studio31.py <bot dir copy before (bot30 + part 1)> <bot dir copy after> <dir with place.html>
Nothing is sent anywhere (fake messages); settings go to a TEMPORARY file, the web folder to a temp folder.
  A. NO BREAK: untouched settings -> the brand settings for the renders and every settings menu as before (one
     button renamed).
  B. What the page sends is cleaned: caption (text on one line and cut, a font ID and a colour NAME from the
     lists, clamped numbers, at most 40 times) and trim (only what makes sense).
  C. Opening: cfg.json holds BOTH sets as they are (logos, logo start, caption, trim), 8 fonts, the colours, the
     set the user is working in, the waiting video's length; the logo images are copied; the link carries only
     the folder's name.
  D. Saving: only the parts sent are stored, each in its own set -- a dub-sync save does not touch the banner set
     and the other way round; trim sent for dub-sync is ignored.
  E. Text that tries to break the render filter (quotes, colons, %, new lines) is stored as plain text and REAL
     ffmpeg still renders the caption.
  F. The save arriving through Telegram: answered per set, the keyboard taken away, a preview picture; the first
     logo page's answers still work; other data is ignored; a user who is not allowed -> nothing.
  G. The page file speaks the bot's language.
Prints STUDIO31_TESTS ALL PASS."""
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

BASE, NEW, PAGE_DIR = sys.argv[1], sys.argv[2], sys.argv[3]
T = tempfile.mkdtemp(prefix="st31_")
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
        m._branding = sys.modules.get("branding")
    finally:
        os.chdir(cwd)
        sys.path.remove(d)
    m.SETTINGS_FILE = os.path.join(T, name + "_settings.json")
    m._allowed = lambda uid: uid != 999
    return m


old, new = load(BASE, "bot_base"), load(NEW, "bot_31")
br = new._branding
UID = 424248
ok = True
SENT = []


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


class FakeMsg:
    def __init__(self, text="", uid=UID, web=None):
        self.text, self.caption, self.video, self.document, self.photo = text, None, None, None, None
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
check("A: untouched settings -> the brand settings for both kinds of render are the ones of before",
      old._brand_payload(UID, "dub") == new._brand_payload(UID, "dub") and old._brand_payload(UID, "banner") == new._brand_payload(UID, "banner"))
diff = []
for w in ("logos", "scroll", "starts", "trim", "output", "size"):
    a, b = kb_dump(old.submenu(w, UID, None)), kb_dump(new.submenu(w, UID, None))
    if w == "logos":
        check("A: Settings -> Logos: the same rows, the Studio button renamed",
              [r for r in a if r[0][1] != "lg:place:open"] == [r for r in b if r[0][1] != "lg:place:open"]
              and [r for r in b if r[0][1] == "lg:place:open"] == [[("🎨 Studio — logo, caption, timeline, trim", "lg:place:open")]], (a, b))
    elif a != b:
        diff.append(w)
check("A: the other settings menus are the same", not diff, diff)

# ---- B. cleaning ------------------------------------------------------------------------------------------
CC, TC = new._cap_clean, new._trim_clean
cases = [
    ({"text": "  Bidhaan   TV \n 0619  "}, {"scroll_text": "Bidhaan TV 0619"}),
    ({"text": "x" * 500}, {"scroll_text": "x" * 200}),
    ({"font": "Montserrat"}, {"caption_font": "montserrat"}),
    ({"font": "classic"}, {"caption_font": ""}), ({"font": ""}, {"caption_font": ""}),
    ({"font": "../../etc/passwd"}, {"caption_font": ""}), ({"font": "bebas:text=x"}, {"caption_font": ""}),
    ({"color": "YELLOW"}, {"caption_color": "yellow"}), ({"color": "red:enable=0"}, {"caption_color": "white"}),
    ({"size": 0.5}, {"caption_scale": 0.06}), ({"size": 0.0001}, {"caption_scale": 0.008}), ({"size": 0.0172}, {"caption_scale": 0.0172}),
    ({"seconds": 3}, {"scroll_seconds": 5.0}), ({"seconds": 9999}, {"scroll_seconds": 120.0}),
    ({"times": [720, 60, 60, "x", -5, 1e9, 1140.4]}, {"scroll_times": [1.0, 12.0, 19.0]}),
    ({"times": list(range(0, 6000, 60))}, {"scroll_times": [float(i) for i in range(40)]}),
    ({"count": 99}, {"scroll_count": 40}), ({"count": -3}, {"scroll_count": 0}),
    ({}, {}), (None, {}), ("garbage", {}), ([1, 2], {}),
]
bad = [(i, CC(i), o) for i, o in cases if CC(i) != o]
check("B: %d caption answers -> cleaned (text, font id, colour name, size, speed, times, count)" % len(cases), not bad, bad[:3])
tcases = [({"mode": "off", "a": 5, "b": 9}, {"trim_mode": "off", "trim_a": 0.0, "trim_b": 0.0}),
          ({"mode": "head", "a": 90}, {"trim_mode": "head", "trim_a": 90.0, "trim_b": 0.0}),
          ({"mode": "tail", "a": 0}, {"trim_mode": "off", "trim_a": 0.0, "trim_b": 0.0}),
          ({"mode": "range", "a": 60, "b": 300}, {"trim_mode": "range", "trim_a": 60.0, "trim_b": 300.0}),
          ({"mode": "cut", "a": 300, "b": 60}, {}), ({"mode": "rm -rf", "a": 1, "b": 2}, {}),
          ({"mode": "head", "a": "x"}, {}), ({"mode": "head", "a": -10}, {"trim_mode": "off", "trim_a": 0.0, "trim_b": 0.0}),
          (None, {}), ({}, {})]
bad = [(i, TC(i), o) for i, o in tcases if TC(i) != o]
check("B: %d trim answers -> only what makes sense" % len(tcases), not bad, bad[:3])

# ---- C. opening -------------------------------------------------------------------------------------------
new.set_user(UID, _profile="banner", scroll_text="UGAAR AH BIDHAAN TV", scroll_count=8, scroll_times=[], logo_start_min=0.0, bidhaan2_mx=0.038)
new.set_user(UID, _profile="dub", scroll_text="", scroll_times=[12, 19, 29], logo_start_min=20 / 60.0, caption_font="lato", caption_color="gold",
             bidhaan2_mx=0.25, trim_mode="off")
new.set_user(UID, _profile="banner", trim_mode="head", trim_a=30.0)
new._set_ui_profile(UID, "dub")
new._pending[UID] = {"duration": 5400.0}
sent = run(new._place_open(FakeMsg("/studio"), UID, None))
root = os.path.join(T, "web", "t")
dirs = os.listdir(root) if os.path.isdir(root) else []
kb = sent[0][2] if sent else None
url = kb.keyboard[0][0].web_app.url if kb is not None and hasattr(kb, "keyboard") else ""
check("C: one message with a keyboard button; the link carries only the folder's name",
      len(sent) == 1 and len(dirs) == 1 and url == "https://example.test/logo/place.html?t=" + dirs[0] and len(dirs[0]) >= 16
      and kb.keyboard[0][0].text == "🎨 Open Studio", (url, dirs))
cfg = json.load(open(os.path.join(root, dirs[0], "cfg.json"))) if dirs else {}
sb, sd = cfg.get("sets", {}).get("banner", {}), cfg.get("sets", {}).get("dub", {})
check("C: cfg.json holds the BANNER set as it is (caption text, 8 times spread, logo from the start, trim 30 s off the start)",
      sb.get("cap", {}).get("text") == "UGAAR AH BIDHAAN TV" and sb["cap"]["count"] == 8 and sb["cap"]["times"] == [] and sb["start"] == 0
      and sb["trim"] == {"mode": "head", "a": 30.0, "b": 0.0} and abs([x for x in sb["logos"] if x["n"] == "bidhaan2"][0]["mx"] - 0.038) < 1e-9, sb)
check("C: ... and the DUB-SYNC set as it is (no caption text, times 12 / 19 / 29 min, Lato in gold, logo from 20 s, its own logo place)",
      sd.get("cap", {}).get("text") == "" and sd["cap"]["times"] == [720, 1140, 1740] and sd["cap"]["font"] == "lato" and sd["cap"]["color"] == "gold"
      and sd["start"] == 20 and sd["trim"]["mode"] == "off" and abs([x for x in sd["logos"] if x["n"] == "bidhaan2"][0]["mx"] - 0.25) < 1e-9, sd)
check("C: 8 fonts (the classic one has the empty id), the colours as web colours, the set he is in, no frame",
      len(cfg.get("fonts", [])) == 8 and cfg["fonts"][0] == {"id": "", "label": "Classic", "file": "fonts/DejaVuSans-Bold.ttf"}
      and {"id": "yellow", "css": "#FFD60A"} in cfg["colors"] and {"id": "white", "css": "#ffffff"} in cfg["colors"]
      and cfg["active"] == "dub" and cfg["bg"] == "", (cfg.get("fonts", [])[:1], cfg.get("colors", [])[:2], cfg.get("active")))
check("C: every font file named in cfg.json exists in the bot's assets", all(os.path.isfile(os.path.join("/app/assets", f["file"])) for f in cfg.get("fonts", [])))
check("C: the logo images are in the folder", all(os.path.exists(os.path.join(T, "web", x["img"])) for x in sb.get("logos", []) + sd.get("logos", [])) and len(sb.get("logos", [])) == 3)
check("C: in a dub-sync flow with no film chosen the timeline gets no length; in a banner flow the waiting video's (90 min)", cfg["dur"] == 0.0, cfg.get("dur"))
new._set_ui_profile(UID, "banner")
run(new._place_open(FakeMsg("/studio"), UID, None))
d2 = [x for x in os.listdir(root) if x != dirs[0]][0]
cfg2 = json.load(open(os.path.join(root, d2, "cfg.json")))
check("C: ... banner flow: the waiting video's length (5400 s) and the banner set as the one he is in", cfg2["dur"] == 5400.0 and cfg2["active"] == "banner", (cfg2["dur"], cfg2["active"]))
new._pending.pop(UID, None)

# ---- D. saving ----------------------------------------------------------------------------------------------
ban0, dub0 = new.user_cfg(UID, "banner"), new.user_cfg(UID, "dub")
lines, first = new._studio_apply(UID, {"k": "studio", "v": 3, "sets": {"dub": {
    "start": 45, "cap": {"text": "FILIM CUSUB", "font": "bebas", "color": "yellow", "size": 0.02, "seconds": 20, "count": 1, "times": [600, 1800]},
    "logos": [{"n": "bidhaan2", "on": True, "x": 0.4, "y": 0.5, "w": 0.2}], "trim": {"mode": "head", "a": 99}}}})
dub1, ban1 = new.user_cfg(UID, "dub"), new.user_cfg(UID, "banner")
check("D: a dub-sync save is stored in the dub-sync set (logo place, logo from 45 s, caption text / Bebas / yellow / 2 % / 20 s / 10 and 30 min)",
      dub1["scroll_text"] == "FILIM CUSUB" and dub1["caption_font"] == "bebas" and dub1["caption_color"] == "yellow" and dub1["caption_scale"] == 0.02
      and dub1["scroll_seconds"] == 20.0 and dub1["scroll_times"] == [10.0, 30.0] and abs(dub1["logo_start_min"] * 60 - 45) < 1e-6
      and dub1["bidhaan2_mx"] == 0.4 and dub1["bidhaan2_my"] == 0.5 and dub1["bidhaan2_corner"] == "TL", {k: dub1[k] for k in ("scroll_text", "caption_font", "scroll_times", "logo_start_min", "bidhaan2_mx")})
check("D: ... the banner set is untouched by it", ban1 == ban0, {k: (ban0[k], ban1[k]) for k in ban0 if ban0[k] != ban1[k]})
check("D: ... trim sent for dub-sync is ignored", dub1["trim_mode"] == dub0["trim_mode"] == "off")
check("D: the answer names the set and says what was stored", first == "dub" and lines[0] == "**Dub-sync films**" and any("FILIM CUSUB" in x and "Bebas" in x and "yellow" in x and "10:00" in x for x in lines)
      and any("appears from 45s" in x for x in lines), lines)
lines, first = new._studio_apply(UID, {"k": "studio", "v": 3, "sets": {"banner": {"trim": {"mode": "range", "a": 60, "b": 600}, "cap": {"color": "cyan"}}}})
ban2 = new.user_cfg(UID, "banner")
check("D: a banner save: only the parts sent change (trim keep 1:00-10:00, caption colour); its text, font, times, logos stay",
      ban2["trim_mode"] == "range" and ban2["trim_a"] == 60.0 and ban2["trim_b"] == 600.0 and ban2["caption_color"] == "cyan"
      and {k: ban2[k] for k in ban2 if k not in ("trim_mode", "trim_a", "trim_b", "caption_color")} == {k: ban1[k] for k in ban1 if k not in ("trim_mode", "trim_a", "trim_b", "caption_color")},
      {k: (ban1[k], ban2[k]) for k in ban1 if ban1[k] != ban2[k]})
check("D: ... the dub-sync set is untouched by it", new.user_cfg(UID, "dub") == dub1 and first == "banner" and lines[0] == "**Banner jobs**")
check("D: the dub-sync render gets ITS caption (Bebas, yellow, at 10 and 30 min) and logo time; the banner one does not",
      new._brand_payload(UID, "dub").get("caption_font") == "bebas" and new._brand_payload(UID, "dub")["scroll_times"] == [600.0, 1800.0]
      and abs(new._brand_payload(UID, "dub")["logo_start"] - 45) < 1e-6 and "caption_font" not in new._brand_payload(UID, "banner"))
lines, first = new._studio_apply(UID, {"k": "studio", "v": 3, "sets": {"dub": {"cap": {"font": "x:y", "color": "#fff"}}, "evil": {"start": 1}, "banner": "nope"}})
check("D: an unknown font / colour falls back to the classic white; unknown sets are ignored",
      new.user_cfg(UID, "dub")["caption_font"] == "" and new.user_cfg(UID, "dub")["caption_color"] == "white" and new.user_cfg(UID, "banner") == ban2)
check("D: nothing usable -> nothing stored, nothing said", new._studio_apply(UID, {"k": "studio", "sets": {"dub": {}}}) == ([], None)
      and new._studio_apply(UID, {"k": "studio"}) == ([], None))

# ---- E. text that tries to break the filter -------------------------------------------------------------------
nasty = "A'B:C%D\\E, [x]=1;drawtext=text=HACK \n second line"
new._studio_apply(UID, {"k": "studio", "sets": {"banner": {"cap": {"text": nasty, "font": "montserrat", "color": "yellow", "size": 0.1, "seconds": 5, "times": [0]}}}})
c = new.user_cfg(UID, "banner")
check("E: stored as plain text on one line", c["scroll_text"] == "A'B:C%D\\E, [x]=1;drawtext=text=HACK second line", c["scroll_text"])
rc = br.RenderConfig(logos=[], cover_png="", scroll_text=c["scroll_text"], width=640, height=360, scroll_seconds=5.0, scroll_times=[0.0],
                     caption_scale=0.1, text_start=0.0, caption_font=c["caption_font"], caption_color=c["caption_color"])
fc = br.build_filter(640, 360, 10.0, [], rc)
r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x202020:s=640x360:r=25", "-f", "lavfi", "-i", "color=c=red:s=16x16",
                    "-filter_complex", fc + ";[outv]format=rgb24[g]", "-map", "[g]", "-ss", "2.5", "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True)
yel = sum(1 for i in range(0, len(r.stdout), 3) if r.stdout[i] > 200 and r.stdout[i + 1] > 170 and r.stdout[i + 2] < 110)
check("E: REAL ffmpeg renders that caption (%d yellow pixels) -- one drawtext, no injected filter" % yel,
      len(r.stdout) == 640 * 360 * 3 and yel > 300 and fc.count("]drawtext=") == 1 and not r.stderr.strip(), (len(r.stdout), r.stderr[-300:], fc[-300:]))

# ---- F. through Telegram ----------------------------------------------------------------------------------------
new._set_ui_profile(UID, "banner")
run(new._place_open(FakeMsg("/studio"), UID, None))
web = json.dumps({"k": "studio", "v": 3, "sets": {"dub": {"cap": {"text": "BIDHAAN TV", "font": "lato", "color": "gold", "size": 0.03, "seconds": 25, "count": 4, "times": []}},
                                                 "banner": {"start": 20}}})
sent = run(new._on_web_app_data(None, FakeMsg("", web=web)))
check("F: the Studio's Save: one answer naming both sets, the keyboard taken away",
      sent and sent[0][0] == "text" and "Studio saved" in sent[0][1] and "**Banner jobs**" in sent[0][1] and "**Dub-sync films**" in sent[0][1]
      and type(sent[0][2]).__name__ == "ReplyKeyboardRemove", sent[:1])
ph = [x for x in sent if x[0] == "photo"]
check("F: ... and a preview picture made by the real render filter (%s bytes)" % (ph[0][3] if ph else 0), len(ph) == 1 and ph[0][3] > 3000, sent)
check("F: ... stored: dub-sync caption 4 times spread (exact times off), banner logo from 20 s",
      new.user_cfg(UID, "dub")["scroll_times"] == [] and new.user_cfg(UID, "dub")["scroll_count"] == 4 and new.user_cfg(UID, "dub")["scroll_text"] == "BIDHAAN TV"
      and abs(new.user_cfg(UID, "banner")["logo_start_min"] * 60 - 20) < 1e-6)
before = (new.user_cfg(UID, "banner"), new.user_cfg(UID, "dub"))
old_web = json.dumps({"k": "logo_place", "v": 2, "start": 30, "logos": [{"n": "bidhaan2", "on": True, "x": 0.1, "y": 0.1, "w": 0.15}]})
sent = run(new._on_web_app_data(None, FakeMsg("", web=old_web)))
check("F: an answer of the first logo page still works (the set he is in: banner)",
      sent and "Logo saved" in sent[0][1] and new.user_cfg(UID, "banner")["bidhaan2_mx"] == 0.1 and new.user_cfg(UID, "dub") == before[1], sent[:1])
snap = (new.user_cfg(UID, "banner"), new.user_cfg(UID, "dub"))
for label, w in (("another kind of data", json.dumps({"k": "other", "sets": {"dub": {"start": 5}}})), ("broken JSON", "{nope"), ("a list", "[1]")):
    sent = run(new._on_web_app_data(None, FakeMsg("", web=w)))
    check("F: %s -> ignored" % label, sent == [] and (new.user_cfg(UID, "banner"), new.user_cfg(UID, "dub")) == snap, sent)
sent = run(new._on_web_app_data(None, FakeMsg("", uid=999, web=web)))
check("F: a user who is not allowed -> nothing", sent == [])
sent = run(new._on_web_app_data(None, FakeMsg("", web=json.dumps({"k": "studio", "sets": {}}))))
check("F: a save with nothing in it -> 'Nothing was changed', the keyboard taken away", sent and "Nothing was changed" in sent[0][1] and type(sent[0][2]).__name__ == "ReplyKeyboardRemove", sent)

# ---- G. the page -------------------------------------------------------------------------------------------------
page = os.path.join(PAGE_DIR, "place.html")
txt = open(page, encoding="utf-8").read() if os.path.exists(page) else ""
need = ('k: "studio"', "sets: sets", "cfg.json", "tg.sendData", "telegram-web-app.js", "out.logos", "out.start", "out.cap", "out.trim",
        "cfg.fonts", "cfg.colors", "cfg.active", "cfg.dur", "cfg.bg", "L.mx", "L.my", "L.c", "L.img", "n: L.n", "on: !!L.on")
miss = [k for k in need if k not in txt]
check("G: place.html is there and speaks the bot's language (%d markers)" % len(need), txt and not miss, miss)

shutil.rmtree(T, ignore_errors=True)
print("STUDIO31_TESTS " + ("ALL PASS" if ok else "FAILED"))
sys.exit(0 if ok else 1)
