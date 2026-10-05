"""bot30 = live bot + TWO INDEPENDENT SETS OF SETTINGS (banner jobs / dub-sync films).
Run inside the bot container:   python3 test_bot_profiles30.py <live bot dir copy> <bot30 dir copy>
Nothing is sent anywhere (fake messages); settings and presets go to TEMPORARY files, never the bot's own.
  A. NO BREAK: a user who only ever does one kind of job sees the settings, the brand settings for the render and
     every settings menu of the live bot; the stored record keeps every value it had.
  B. Independence: a banner change does not reach the dub-sync set, a dub-sync change does not reach the banner
     set; the uploaded logo image is shared.
  C. Today's settings are frozen into the dub-sync set at the bot's start (migration): every value as it was;
     running it again changes nothing; without it, the FIRST later banner change still cannot reach dub-sync.
  D. Typed commands follow the flow the user is in (/text in a dub-sync flow vs after sending a video for the logo).
  E. A button changes the set of ITS panel (a dub-sync panel / a banner panel), whatever was touched before.
  F. A time typed after "set ... time" goes to the set of the panel that asked, even if the other flow was
     touched in between.
  G. Renders never follow the "working in" state: dub-sync brand settings come from the dub-sync set, the batch
     panel from the banner set.
  H. Presets: saved from the set the user is in, applied to the set the user is in.
Prints PROFILES30_TESTS ALL PASS."""
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

LIVE, NEW = sys.argv[1], sys.argv[2]
T = tempfile.mkdtemp(prefix="pf30_")


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
    m.SETTINGS_FILE = os.path.join(T, name + "_settings.json")
    m.TEMPLATES_FILE = os.path.join(T, name + "_templates.json")
    m._allowed = lambda uid: True
    return m


old, new = load(LIVE, "bot_live"), load(NEW, "bot_30")
UID = 424244
ok = True
SENT = []


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


class FakeMsg:
    n = [800000]

    def __init__(self, text="", uid=UID):
        FakeMsg.n[0] += 1
        self.id = FakeMsg.n[0]
        self.text, self.caption, self.video, self.document, self.photo = text, None, None, None, None
        self.command = text.split() and [text.split()[0].lstrip("/")] + text.split()[1:] if text.startswith("/") else None
        self.from_user = SimpleNamespace(id=uid)
        self.chat = SimpleNamespace(id=uid)
        self.reply_markup = None
        self.reply_to_message = None

    async def reply(self, text, reply_markup=None, **kw):
        SENT.append(text)
        return FakeMsg(text)

    async def edit(self, text, reply_markup=None, **kw):
        self.text = text
        return self

    async def edit_text(self, *a, **k):
        return await self.edit(*a, **k)

    async def edit_reply_markup(self, reply_markup=None, **k):
        self.reply_markup = reply_markup
        return self


class FakeCQ:
    def __init__(self, data, msg, uid=UID):
        self.data, self.message, self.from_user = data, msg, SimpleNamespace(id=uid)

    async def answer(self, *a, **k):
        return None


def run(coro):
    SENT.clear()
    asyncio.run(coro)
    return list(SENT)


def kb_dump(km):
    return [[(b.text, getattr(b, "callback_data", None)) for b in row] for row in km.inline_keyboard]


def stored(m, uid=UID):
    return m._load().get(str(uid), {})


DUBP = "🎬 Ready to dub-sync\n\n📺 HD master x.mkv"
BANP = "🎬 Ready to render\n\nx.mp4"

# ---- A. no break ------------------------------------------------------------------------------------------
for m in (old, new):
    m.set_user(UID, scroll_text="HELLO", logo_start_min=0.5, bitrate=2700, bidhaan2_mx=0.2)
vo, vn = old.user_cfg(UID), new.user_cfg(UID)
check("A: the settings a user sees are the live bot's (%d values; no dub-sync part showing)" % len(vo),
      {k: vn.get(k) for k in vo} == vo and "_dub" not in vn, {k: (vo.get(k), vn.get(k)) for k in vo if vo.get(k) != vn.get(k)})
check("A: the brand settings for a render are the live bot's",
      old._brand_payload(UID) == new._brand_payload(UID) == new._brand_payload(UID, "banner"),
      (old._brand_payload(UID), new._brand_payload(UID)))
def kb_same(km):
    """A menu without the LABEL of the Studio button (bot31 renamed it; the button and what it does are the same)."""
    return [[("<studio>" if cb == "lg:place:open" else t, cb) for t, cb in row] for row in kb_dump(km)]


diff = [w for w in ("logos", "scroll", "starts", "trim", "output", "size") if kb_same(old.submenu(w, UID, None)) != kb_same(new.submenu(w, UID, None))]
check("A: every settings menu is the same (the Studio button may carry its new name)", not diff, diff)
so, sn = stored(old), stored(new)
check("A: the stored record keeps every value it had; one new part beside it (the dub-sync set)",
      {k: sn.get(k) for k in so} == so and isinstance(sn.get("_dub"), dict), set(sn) ^ set(so))
r = new.set_user(UID, fps=30)
check("A: set_user still answers with the settings as the user sees them", r == new.user_cfg(UID) and r["fps"] == 30 and "_dub" not in r)

# ---- B. independence ----------------------------------------------------------------------------------------
new._set_ui_profile(UID, "banner")
before_dub = new.user_cfg(UID, "dub")
new.set_user(UID, logo_start_min=2.0, scroll_text="BANNER TEXT", bidhaan2_on=False, bitrate=1234, trim_mode="head", trim_a=30.0)
check("B: banner changes (logo time, caption, logo switch, bitrate, trim) do not reach the dub-sync set",
      new.user_cfg(UID, "dub") == before_dub and new.user_cfg(UID, "banner")["scroll_text"] == "BANNER TEXT",
      {k: (before_dub[k], new.user_cfg(UID, "dub")[k]) for k in before_dub if before_dub[k] != new.user_cfg(UID, "dub")[k]})
before_ban = new.user_cfg(UID, "banner")
new.set_user(UID, _profile="dub", logo_start_min=0.3333, scroll_text="DUB TEXT", width=1280, height=720)
check("B: dub-sync changes do not reach the banner set",
      new.user_cfg(UID, "banner") == before_ban and new.user_cfg(UID, "dub")["scroll_text"] == "DUB TEXT"
      and new.user_cfg(UID, "dub")["width"] == 1280 and new.user_cfg(UID, "banner")["width"] == before_ban["width"])
new.set_user(UID, _profile="dub", custom_logo="/tmp/x.png")
check("B: the uploaded logo image is one for both", new.user_cfg(UID, "dub")["custom_logo"] == new.user_cfg(UID, "banner")["custom_logo"] == "/tmp/x.png")
new.set_user(UID, custom_logo="")

# ---- C. migration ---------------------------------------------------------------------------------------------
U2, U3 = 424245, 424246
d = new._load()
rec2 = dict(new.DEFAULTS)
rec2.update(logo_start_min=0.3333, scroll_text="AS IT WAS", bidhaan2_mx=0.038, bitrate=2000)
d[str(U2)] = dict(rec2)
d[str(U3)] = dict(rec2)
new._save(d)
n = new._migrate_profiles()
check("C: at the bot's start the users without a dub-sync set get one (%d made)" % n, n == 2 and isinstance(stored(new, U2).get("_dub"), dict))
check("C: it is the settings exactly as they were", all(new.user_cfg(U2, "dub")[k] == rec2[k] for k in rec2) and new.user_cfg(U2, "banner") == rec2)
check("C: ... so the dub-sync render gets the brand settings it got before",
      new._brand_payload(U2, "dub") == new._brand_payload(U2, "banner") and abs(new._brand_payload(U2, "dub")["logo_start"] - 20.0) < 0.01)
snap = json.dumps(new._load(), sort_keys=True)
check("C: running it again changes nothing", new._migrate_profiles() == 0 and json.dumps(new._load(), sort_keys=True) == snap)
new.set_user(U2, _profile="banner", logo_start_min=5.0, scroll_text="NEW BANNER")
check("C: after it a banner change cannot reach the dub-sync films (logo time stays 20 s, caption stays)",
      abs(new.user_cfg(U2, "dub")["logo_start_min"] - 0.3333) < 1e-9 and new.user_cfg(U2, "dub")["scroll_text"] == "AS IT WAS")
d = new._load()
d[str(U3)] = dict(rec2)                                   # a record that somehow missed the migration
new._save(d)
new.set_user(U3, _profile="banner", logo_start_min=7.0)
check("C: without the migration the FIRST banner change still leaves the dub-sync set as it was",
      abs(new.user_cfg(U3, "dub")["logo_start_min"] - 0.3333) < 1e-9 and new.user_cfg(U3, "banner")["logo_start_min"] == 7.0)

# ---- D. typed commands follow the flow ------------------------------------------------------------------------
new._set_ui_profile(UID, "dub")
run(new._text(None, FakeMsg("/text SOMALI FILM")))
check("D: /text inside a dub-sync flow changes the dub-sync caption only",
      new.user_cfg(UID, "dub")["scroll_text"] == "SOMALI FILM" and new.user_cfg(UID, "banner")["scroll_text"] == "BANNER TEXT")
new._set_ui_profile(UID, "banner")
run(new._text(None, FakeMsg("/text SERIES 0619")))
check("D: /text after a video for the logo changes the banner caption only",
      new.user_cfg(UID, "banner")["scroll_text"] == "SERIES 0619" and new.user_cfg(UID, "dub")["scroll_text"] == "SOMALI FILM")
sent = run(new._settings(None, FakeMsg("/settings")))
check("D: /settings says which set it shows", sent and "Banner jobs" in sent[0], sent[:1])

# ---- E. a button changes the set of its panel -----------------------------------------------------------------
new.set_user(UID, _profile="dub", logo_start_min=0.3333)
new.set_user(UID, _profile="banner", logo_start_min=0.75)
new._set_ui_profile(UID, "banner")
run(new._cb(None, FakeCQ("tfull:logo_start_min", FakeMsg(DUBP))))
check("E: a button on a DUB-SYNC panel changes the dub-sync set (logo start -> the film's start), banner untouched",
      new.user_cfg(UID, "dub")["logo_start_min"] == 0.0 and new.user_cfg(UID, "banner")["logo_start_min"] == 0.75,
      (new.user_cfg(UID, "dub")["logo_start_min"], new.user_cfg(UID, "banner")["logo_start_min"]))
new.set_user(UID, _profile="dub", logo_start_min=0.3333)
run(new._cb(None, FakeCQ("tfull:logo_start_min", FakeMsg(BANP))))
check("E: the same button on a BANNER panel changes the banner set, dub-sync untouched",
      new.user_cfg(UID, "banner")["logo_start_min"] == 0.0 and abs(new.user_cfg(UID, "dub")["logo_start_min"] - 0.3333) < 1e-9)
check("E: the panel test: a dub-sync panel / a banner panel / nothing",
      new._is_dub_msg(UID, FakeMsg(DUBP)) and not new._is_dub_msg(UID, FakeMsg(BANP)) and not new._is_dub_msg(UID, None))

# ---- F. a typed time goes to the set of the panel that asked ---------------------------------------------------
run(new._cb(None, FakeCQ("tset:logo_start_min", FakeMsg(DUBP))))
new._set_ui_profile(UID, "banner")                           # he touches the other flow in between
run(new._handle_time_input(FakeMsg("45s"), UID))
check("F: 'set logo start' on a dub-sync panel, then 45s typed -> the dub-sync set gets 45 s, the banner set stays",
      abs(new.user_cfg(UID, "dub")["logo_start_min"] - 0.75) < 1e-9 and new.user_cfg(UID, "banner")["logo_start_min"] == 0.0,
      (new.user_cfg(UID, "dub")["logo_start_min"], new.user_cfg(UID, "banner")["logo_start_min"]))

# ---- G. renders read their own set ------------------------------------------------------------------------------
new._set_ui_profile(UID, "banner")
check("G: the dub-sync render's brand settings: logo from 45 s (its own set), whatever flow was touched last",
      abs(new._brand_payload(UID, "dub")["logo_start"] - 45.0) < 1e-6 and new._brand_payload(UID, "dub")["scroll_text"] == "SOMALI FILM")
new._set_ui_profile(UID, "dub")
new.set_user(UID, _profile="banner", fps=30, scroll_text="SERIES 0619")
new.set_user(UID, _profile="dub", fps=25)
txt = new._batch_panel_text(UID, 2)
check("G: the batch (banner) panel shows the banner set (30 fps, its caption) while he is in a dub-sync flow",
      "30fps" in txt and "SERIES 0619" in txt and "SOMALI FILM" not in txt, " | ".join(txt[:400].splitlines()))

# ---- H. presets ---------------------------------------------------------------------------------------------------
new._set_ui_profile(UID, "dub")
new.save_template(UID, "film")
new._set_ui_profile(UID, "banner")
ban_before = new.user_cfg(UID, "banner")
check("H: a preset saved in a dub-sync flow holds the dub-sync values", new.get_templates(UID)["film"]["scroll_text"] == "SOMALI FILM")
new.apply_template(UID, "film")
check("H: applied in a banner flow it changes the banner set only",
      new.user_cfg(UID, "banner")["scroll_text"] == "SOMALI FILM" and ban_before["scroll_text"] == "SERIES 0619"
      and new.user_cfg(UID, "dub")["scroll_text"] == "SOMALI FILM")

shutil.rmtree(T, ignore_errors=True)
print("PROFILES30_TESTS " + ("ALL PASS" if ok else "FAILED"))
sys.exit(0 if ok else 1)
