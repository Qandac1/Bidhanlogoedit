"""bot36 = the Studio's caption AS TYPED, 12 more fonts, the waiting video's own pictures (patch_bot_studio36.py).
Run inside the bot container:
    python3 test_bot_studio36.py <bot dir copy before (live)> <bot dir copy after> <dir with place.html> <dir with ALL font files>
Nothing is sent anywhere (fake messages); settings go to a TEMPORARY file, the web folder to a temp folder.
  A. NO BREAK: untouched settings -> the brand settings, every settings menu, the render panel, the batch panel and
     the render filter are the ones of before, character for character; a caption on one line is stored as before.
  B. The caption AS TYPED: cleaned the same way as the page does (shared cases), stored with its line breaks and
     spaces, given back to the page unchanged, drawn by REAL ffmpeg as typed (two lines, the first moved right by
     its own spaces, the block centred), also with a % in it and with text that tries to break the filter; /text;
     the panels show it on one line; the picture after a save.
  C. Fonts: 20, every file there, every one drawn by real ffmpeg, the line pitch ffmpeg uses = the one the page gets.
  D. The waiting video's own pictures: the first at once (it is the frame), 24 in the list, each from its own
     moment of the video, in the picture's true shape; nothing waits / the file is gone / a photo is replied to /
     the dub-sync set -> as before; a waiting dub-sync pair gives the HD film's thumbnail.
  E. The dub-sync ENGINE draws the same caption as typed (its own filter, real ffmpeg).
  F. The page file speaks the bot's language.
Prints STUDIO36_TESTS ALL PASS."""
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import numpy as np

BASE, NEW, PAGE_DIR, FONT_DIR = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
T = tempfile.mkdtemp(prefix="st36_")
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


old, new = load(BASE, "bot_base"), load(NEW, "bot_36")
bo, br = old._branding, new._branding
br.FONT_DIRS = (FONT_DIR,) + tuple(br.FONT_DIRS)          # the staged fonts (old + new), as they will be installed
UID = 424249
ok = True
SENT = []


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


class FakeMsg:
    def __init__(self, text="", uid=UID, web=None):
        self.text, self.caption, self.video, self.document, self.photo = text, None, None, None, None
        self.command = text.split() if text.startswith("/") else None
        if self.command:
            self.command[0] = self.command[0].lstrip("/")
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

    async def download(self, file_name=None, **kw):
        shutil.copyfile(self._file, file_name)
        return file_name


def run(coro):
    SENT.clear()
    asyncio.run(coro)
    return list(SENT)


def kb_dump(km):
    return [[(b.text, getattr(b, "callback_data", None)) for b in row] for row in km.inline_keyboard]


def frame(fc, t=2.5, w=640, h=360, extra=()):
    """One frame (h x w x 3) of real ffmpeg through a filter_complex that ends in [outv]."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x202020:s=%dx%d:r=25" % (w, h), "-f", "lavfi", "-i", "color=c=red:s=16x16",
                        *extra, "-filter_complex", fc + ";[outv]format=rgb24[g]", "-map", "[g]", "-ss", str(t), "-frames:v", "1", "-f", "rawvideo", "-"],
                       capture_output=True)
    if len(r.stdout) != w * h * 3:
        return None, r.stderr.decode()[-300:]
    return np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3), r.stderr.decode().strip()


def text_lines(img, thr=170):
    """[(top row, bottom row, left edge, right edge)] of every line of bright (white or yellow) text in a frame."""
    g = (img[:, :, 0] > thr) & (img[:, :, 1] > thr - 20)
    rows = np.where(g.any(1))[0]
    if not len(rows):
        return []
    runs, s = [], rows[0]
    for a, b in zip(rows, rows[1:]):
        if b - a > 3:
            runs.append((s, a))
            s = b
    runs.append((s, rows[-1]))
    out = []
    for a, b in runs:
        cols = np.where(g[a:b + 1].any(0))[0]
        out.append((int(a), int(b), int(cols[0]), int(cols[-1])))
    return out


def rc(text, **kw):
    d = dict(logos=[], cover_png="", scroll_text=text, width=640, height=360, scroll_seconds=5.0, scroll_times=[0.0], caption_scale=0.125, text_start=0.0)   # 45 px
    d.update(kw)
    return d


# ---- A. no break ------------------------------------------------------------------------------------------------
check("A: untouched settings -> the brand settings for both kinds of render are the ones of before",
      old._brand_payload(UID, "dub") == new._brand_payload(UID, "dub") and old._brand_payload(UID, "banner") == new._brand_payload(UID, "banner"))
diff = [w for w in ("logos", "scroll", "starts", "trim", "output", "size") if kb_dump(old.submenu(w, UID, None)) != kb_dump(new.submenu(w, UID, None))]
check("A: every settings menu is the same", not diff, diff)
job = {"name": "film.mp4", "w": 1280, "h": 720, "duration": 5400.0, "src": "", "work": "", "msg": None, "size": 1500000000}
try:
    pa, pb = old.panel(UID, dict(job)), new.panel(UID, dict(job))
    check("A: the render panel of a waiting video (text and buttons) is the same", pa[0] == pb[0] and kb_dump(pa[1]) == kb_dump(pb[1]), (pa[0][-300:], pb[0][-300:]))
except Exception as e:
    check("A: the render panel of a waiting video is the same", False, repr(e))
check("A: the batch panel's text is the same", old._batch_panel_text(UID, 3) == new._batch_panel_text(UID, 3))
same = []
for kw in (rc("UGAAR AH BIDHAAN TV 0619624090"), rc("BIDHAAN TV", scroll_times=[], scroll_count=4), rc("50% OFF", caption_font="montserrat", caption_color="yellow"),
           rc("A B", caption_font="bebas"), rc("", scroll_times=[]), rc("X", caption_font="no-such-font", caption_color="nope")):
    a = bo.build_filter(640, 360, 600.0, [], bo.RenderConfig(**kw))
    b = br.build_filter(640, 360, 600.0, [], br.RenderConfig(**kw)).replace(FONT_DIR, "/app/assets/fonts")   # the test's font folder
    same.append(a == b)
check("A: the render filter for 6 one-line captions (times, count, a %%, fonts of before, none, unknown font) is the one of before, "
      "character for character", all(same), same)
check("A: the 8 fonts of before keep their ids, names and files (in the same order, first)",
      list(br.CAPTION_FONTS.items())[:8] == list(bo.CAPTION_FONTS.items()), list(br.CAPTION_FONTS)[:8])
one = [{"text": "UGAAR AH BIDHAAN TV 0619624090"}, {"text": "Bidhaan TV"}, {"text": ""}, {"font": "Montserrat"}, {"font": "classic"}, {"font": "../../etc/passwd"},
       {"color": "YELLOW"}, {"color": "red:enable=0"}, {"size": 0.5}, {"size": 0.0172}, {"seconds": 3}, {"seconds": 9999}, {"times": [720, 60, 60, "x", -5, 1e9, 1140.4]},
       {"count": 99}, {"count": -3}, {}, None, "garbage", [1, 2]]
bad = [(i, old._cap_clean(i), new._cap_clean(i)) for i in one if old._cap_clean(i) != new._cap_clean(i)]
check("A: %d Studio answers (a caption on one line, fonts, colours, numbers, times, rubbish) are cleaned as before" % len(one), not bad, bad[:3])

# ---- B. the caption as typed --------------------------------------------------------------------------------------
CASES = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "caption_cases36.json"), encoding="utf-8"))
bad = [(i, br.caption_lines(i), o) for i, o in CASES if br.caption_lines(i) != o]
check("B: %d typed captions are cleaned as the shared list says (the page is tested with the same list)" % len(CASES), not bad, bad[:3])
check("B: cleaning a cleaned caption changes nothing (what is saved is what is shown again)",
      all(br.caption_lines(o) == o for _i, o in CASES))
JOHN = "     U GAAR AH\nRASHKA BOY MUSALSAL TV"
check("B: John's own caption is kept as typed: two lines, five spaces before the first",
      new._cap_clean({"text": JOHN}) == {"scroll_text": JOHN} and old._cap_clean({"text": JOHN}) == {"scroll_text": "U GAAR AH RASHKA BOY MUSALSAL TV"})
new.set_user(UID, _profile="dub", scroll_text="DUB CAPTION", caption_font="lato")
new._studio_apply(UID, {"k": "studio", "sets": {"banner": {"cap": {"text": JOHN, "font": "spartan", "color": "yellow", "size": 0.1, "seconds": 5, "times": [0]}}}})
cb, cd = new.user_cfg(UID, "banner"), new.user_cfg(UID, "dub")
check("B: a Studio save stores it in the banner set (font Spartan) and does not touch the dub-sync set",
      cb["scroll_text"] == JOHN and cb["caption_font"] == "spartan" and cd["scroll_text"] == "DUB CAPTION" and cd["caption_font"] == "lato", (cb["scroll_text"], cd["scroll_text"]))
tok = "tok36aaaaaaaaaaaa"
os.makedirs(os.path.join(T, "web", "t", tok), exist_ok=True)
check("B: ... and the page gets it back unchanged the next time it opens", new._studio_set(UID, "banner", tok)["cap"]["text"] == JOHN)
pay = new._brand_payload(UID, "banner")
cfg = br.RenderConfig(**rc(pay["scroll_text"], caption_font=pay.get("caption_font", ""), caption_color=pay.get("caption_color", "white")))
fc = br.build_filter(640, 360, 10.0, [], cfg)
img, err = frame(fc)
ls = text_lines(img) if img is not None else []
from PIL import ImageFont  # noqa: E402
fnt = ImageFont.truetype(br.caption_font_file("spartan"), 45)
sp5 = fnt.getlength("     U") - fnt.getlength("U")
w1, w2 = fnt.getlength("U GAAR AH"), fnt.getlength("RASHKA BOY MUSALSAL TV")
check("B: REAL ffmpeg draws it as typed: 2 lines (%s), yellow, one drawtext" % (ls,),
      img is not None and len(ls) == 2 and fc.count("]drawtext=") == 1 and not err
      and int(((img[:, :, 0] > 200) & (img[:, :, 1] > 170) & (img[:, :, 2] < 110)).sum()) > 300 and "LeagueSpartan-Bold.otf" in fc, (err, fc[-200:]))
if len(ls) == 2:
    check("B: ... the first line starts %d px right of the second = its five spaces (%.0f px in this font)" % (ls[0][2] - ls[1][2], sp5),
          abs((ls[0][2] - ls[1][2]) - sp5) <= 3, (ls, sp5))
    check("B: ... the lines stand left-aligned in a block, the block in the middle of the picture (centre %.0f of 320)" % ((ls[1][2] + ls[1][3]) / 2.0),
          abs((ls[1][2] + ls[1][3]) / 2.0 - 320) <= 4 and abs((ls[1][3] - ls[1][2]) - w2) <= 8 and abs((ls[0][3] - ls[0][2]) - w1) <= 8, (ls, w1, w2))
    check("B: ... one line pitch apart (%d px; the font's own line height at 45 px = %.1f)" % (ls[1][0] - ls[0][0], br.caption_line_height("spartan") * 45),
          abs((ls[1][0] - ls[0][0]) - br.caption_line_height("spartan") * 45) <= 2)
nasty = "A'B:C%D\\E, [x]=1;drawtext=text=HACK \n second line"
new._studio_apply(UID, {"k": "studio", "sets": {"banner": {"cap": {"text": nasty, "font": "montserrat", "color": "yellow", "size": 0.1, "seconds": 5, "times": [0]}}}})
c = new.user_cfg(UID, "banner")
check("B: text that tries to break the filter is stored as plain text, with its line break", c["scroll_text"] == "A'B:C%D\\E, [x]=1;drawtext=text=HACK\n second line", c["scroll_text"])
fc = br.build_filter(640, 360, 10.0, [], br.RenderConfig(**rc(c["scroll_text"], caption_font=c["caption_font"], caption_color=c["caption_color"])))
img, err = frame(fc)
ls = text_lines(img) if img is not None else []
check("B: ... and REAL ffmpeg draws it in two lines -- one drawtext, no injected filter, a %% letter for letter",
      img is not None and len(ls) == 2 and fc.count("]drawtext=") == 1 and "expansion=none" in fc and not err, (err, len(ls)))
run(new._text(None, FakeMsg("/text LINE ONE\n   LINE TWO  ")))
check("B: /text keeps the lines too (\"LINE ONE / three spaces LINE TWO\"), and says so in a block",
      new.user_cfg(UID)["scroll_text"] == "LINE ONE\n   LINE TWO" and SENT and "```\nLINE ONE\n   LINE TWO\n```" in SENT[0][1], (new.user_cfg(UID)["scroll_text"], SENT[:1]))
a = run(old._text(None, FakeMsg("/text bidhaan tv 0619")))
b = run(new._text(None, FakeMsg("/text bidhaan tv 0619")))
check("B: /text with one line: stored and answered as before", a and b and a[0][1] == b[0][1] and new.user_cfg(UID)["scroll_text"] == "bidhaan tv 0619", (a[:1], b[:1]))
new.set_user(UID, _profile="banner", scroll_text=JOHN)
new._set_ui_profile(UID, "banner")
ptxt = new.panel(UID, dict(job))[0]
check("B: the render panel shows the caption on ONE line (\"U GAAR AH ⏎ RASHKA BOY MUSALSAL TV\")",
      "`U GAAR AH ⏎ RASHKA BOY MUSALSAL TV`" in ptxt and "`U GAAR AH ⏎ RASHKA BOY MUSALSAL TV`" in new._batch_panel_text(UID, 2), ptxt[:300])
check("B: ... and the Studio's answer names it on one line", "U GAAR AH ⏎ RASHKA BOY MUSALSAL TV" in new._cap_line(new.user_cfg(UID, "banner")))
sent = run(new._place_preview(FakeMsg(""), UID, "banner"))
ph = [x for x in sent if x[0] == "photo"]
ok_ph = False
if ph:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", ph[0][1], "-vf", "format=rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
    pim = np.frombuffer(raw, np.uint8).reshape(-1, 1280, 3) if len(raw) % (1280 * 3) == 0 and raw else None
    pl = text_lines(pim[int(pim.shape[0] * 0.6):], 200) if pim is not None else []
    ok_ph = len(pl) == 2 and pl[0][2] > pl[1][2]
    check("B: the picture sent after a save shows the caption in its two lines, the first moved right (%s)" % (pl,), ok_ph, pl)
else:
    check("B: the picture sent after a save shows the caption in its two lines", False, sent)

# ---- C. fonts -----------------------------------------------------------------------------------------------------
F = br.CAPTION_FONTS
check("C: 20 caption fonts (8 of before + 12), every file is in the font folder",
      len(F) == 20 and all(os.path.isfile(os.path.join(FONT_DIR, fn or "DejaVuSans-Bold.ttf")) for _l, fn in F.values()),
      [k for k, (_l, fn) in F.items() if not os.path.isfile(os.path.join(FONT_DIR, fn or "DejaVuSans-Bold.ttf"))])
check("C: an id finds its own file; an unknown id the classic font, as before",
      all(br.caption_font_file(k).endswith(fn) for k, (_l, fn) in F.items() if fn) and br.caption_font_file("no-such") == br.FONT and br.caption_font_file("") == br.FONT)
badf = []
for k in F:
    fc = br.build_filter(640, 360, 10.0, [], br.RenderConfig(**rc("AB\nAB", caption_font=k)))
    img, err = frame(fc)
    ls = text_lines(img) if img is not None else []
    want = br.caption_line_height(k) * 45
    if img is None or err or len(ls) != 2 or abs((ls[1][0] - ls[0][0]) - want) > 2.5:
        badf.append((k, len(ls), (ls[1][0] - ls[0][0]) if len(ls) == 2 else None, round(want, 1), err[-80:]))
check("C: real ffmpeg draws two lines in every one of the 20 fonts, the second one font line height under the first "
      "(the number the page spaces its lines by)", not badf, badf)

# ---- D. the waiting video's own pictures ----------------------------------------------------------------------------
VID = os.path.join(T, "film.mp4")            # 96 s, 2.39:1, the picture gets brighter second by second
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x28:r=25:d=96", "-vf", "geq=lum='16+200*T/96':cb=128:cr=128,scale=1280:536,setsar=1",
                "-c:v", "libx264", "-preset", "ultrafast", "-g", "50", "-pix_fmt", "yuv420p", VID], check=True)
PAL = os.path.join(T, "pal.mp4")             # 720x576 stored, shown 4:3 (its points are not square)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=720x576:r=25:d=8", "-vf", "setsar=16/15",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", PAL], check=True)
root = os.path.join(T, "web", "t")
os.makedirs(root, exist_ok=True)


async def open_and_fill(uid, reply=None):
    new._studio_tasks.pop(uid, None)
    os.makedirs(root, exist_ok=True)
    for n in os.listdir(root):
        shutil.rmtree(os.path.join(root, n), ignore_errors=True)
    await new._place_open(FakeMsg("/studio"), uid, reply)
    tk = new._studio_tasks.get(uid)
    if tk is not None:
        await tk


def opened():
    ds = [n for n in os.listdir(root)]
    d = os.path.join(root, ds[0]) if len(ds) == 1 else ""
    return d, (json.load(open(os.path.join(d, "cfg.json"))) if d else {})


new._set_ui_profile(UID, "banner")
new._pending[UID] = dict(job, src=VID, duration=96.0, w=1280, h=536)
new._studio_tasks.pop(UID, None)
sent = run(open_and_fill(UID))
d, cfg = opened()
fj = json.load(open(os.path.join(d, "frames.json"))) if d and os.path.exists(os.path.join(d, "frames.json")) else {}
tok = os.path.basename(d)
check("D: a video waits in the panel -> the Studio opens with its own picture as the frame and a list of pictures",
      cfg.get("bg") == "t/%s/frame.jpg" % tok and cfg.get("frames") == "t/%s/frames.json" % tok and os.path.getsize(os.path.join(d, "frame.jpg")) > 400
      and abs(cfg.get("dur", 0) - 96.0) < 0.01 and len(sent) == 1 and sent[0][2].keyboard[0][0].text == "🎨 Open Studio", (cfg.get("bg"), cfg.get("frames"), sent[:1]))
fr = fj.get("frames", [])
check("D: 24 pictures, one from the middle of each of 24 equal parts (2 s, 6 s ... 94 s), the list closed",
      fj.get("done") is True and fj.get("n") == 24 and abs(fj.get("dur", 0) - 96.0) < 0.01 and [x["i"] for x in fr] == list(range(24))
      and all(abs(x["t"] - (4.0 * x["i"] + 2.0)) < 0.01 for x in fr), (fj.get("done"), len(fr), fr[:2]))
lum, shape = [], set()
for x in fr:
    p = os.path.join(T, "web", x["img"])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-vf", "format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    shape.add(pr)
    lum.append(float(np.frombuffer(raw, np.uint8).mean()) if raw else -1.0)
want = [200.0 * (4.0 * i + 2.0) / 96.0 * 255.0 / 219.0 for i in range(24)]      # video levels 16..216 -> a JPEG's 0..233
worst = max(abs(a - b) for a, b in zip(lum, want)) if len(lum) == 24 else 999
check("D: every picture is from ITS moment of the video (the test film gets brighter second by second: each picture has its "
      "moment's brightness, worst miss %.1f of 255; step to step always brighter)" % worst,
      len(lum) == 24 and worst < 10 and all(b > a + 4 for a, b in zip(lum, lum[1:])), list(zip(lum, want))[:4])
check("D: ... 640 px wide in the picture's true shape (2.39:1 -> %s)" % sorted(shape), shape == {"640,268"}, shape)
check("D: the frame behind the logo is the picture of part 3 (14 s into the 96 s)",
      open(os.path.join(d, "frame.jpg"), "rb").read() == open(os.path.join(d, "f_03.jpg"), "rb").read())
check("D: the fonts in cfg.json: 20, each with its line pitch; the classic one first with the empty id",
      len(cfg.get("fonts", [])) == 20 and cfg["fonts"][0] == {"id": "", "label": "Classic", "file": "fonts/DejaVuSans-Bold.ttf", "lh": br.caption_line_height("classic")}
      and all(0.8 < f["lh"] < 1.5 for f in cfg["fonts"]) and cfg["fonts"][8]["id"] == "spartan", cfg.get("fonts", [])[:1])
new._pending.pop(UID, None)
sent = run(open_and_fill(UID))
d, cfg = opened()
check("D: nothing waits -> the Studio opens as before: no frame, no list", cfg.get("bg") == "" and cfg.get("frames") == "" and cfg.get("dur") == 0.0
      and not os.path.exists(os.path.join(d, "frames.json")) and len(sent) == 1, (cfg.get("bg"), cfg.get("frames")))
new._pending[UID] = dict(job, src=os.path.join(T, "gone.mp4"), duration=96.0)
sent = run(open_and_fill(UID))
d, cfg = opened()
check("D: the waiting video's file is gone -> as before, and the timeline still gets its length", cfg.get("bg") == "" and cfg.get("frames") == "" and abs(cfg.get("dur", 0) - 96.0) < 0.01
      and len(sent) == 1, cfg.get("frames"))
BROKEN = os.path.join(T, "broken.mp4")
open(BROKEN, "wb").write(b"not a video at all" * 200)
new._pending[UID] = dict(job, src=BROKEN, duration=96.0)
sent = run(open_and_fill(UID))
d, cfg = opened()
check("D: a file no picture can be cut from -> as before, no error", cfg.get("bg") == "" and cfg.get("frames") == "" and len(sent) == 1, cfg.get("frames"))
PHOTO = os.path.join(T, "photo.jpg")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=green:s=320x180", "-frames:v", "1", PHOTO], check=True)
rep = FakeMsg("")
rep.photo, rep._file = SimpleNamespace(file_id="x"), PHOTO
new._pending[UID] = dict(job, src=VID, duration=96.0)
sent = run(open_and_fill(UID, rep))
d, cfg = opened()
check("D: a reply to a photo still wins: that picture is the frame, no list of the video", cfg.get("bg", "").endswith("frame.jpg") and cfg.get("frames") == ""
      and open(os.path.join(d, "frame.jpg"), "rb").read() == open(PHOTO, "rb").read(), cfg.get("frames"))
new._set_ui_profile(UID, "dub")
sent = run(open_and_fill(UID))
d, cfg = opened()
check("D: working in the dub-sync set with no film of its own: the video that waits in the banner flow is shown (better than an empty picture)",
      cfg.get("frames", "").endswith("frames.json") and cfg.get("bg", "").endswith("frame.jpg") and cfg.get("active") == "dub", (cfg.get("frames"), cfg.get("bg")))
new._pending.pop(UID, None)
sent = run(open_and_fill(UID))
d, cfg = opened()
check("D: ... and with nothing anywhere: as before, no frame, no list", cfg.get("frames") == "" and cfg.get("bg") == "" and cfg.get("active") == "dub", (cfg.get("frames"), cfg.get("bg")))
hd = FakeMsg("")
hd.video = SimpleNamespace(thumbs=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id="big")], duration=5400, file_name="hd.mp4", width=1920, height=1080, file_size=1)
dub = FakeMsg("")
dub.video = SimpleNamespace(thumbs=None, duration=5400, file_name="dub.mp4", width=640, height=360, file_size=1)
new._dubsel[UID] = {"msgs": [dub, hd], "hd_i": 1}
got = []


async def fake_dl(file_id, file_name=None, **kw):
    got.append(file_id)
    shutil.copyfile(PHOTO, file_name)
    return file_name


real_dl = new.app.download_media
new.app.download_media = fake_dl
try:
    sent = run(open_and_fill(UID))
finally:
    new.app.download_media = real_dl
d, cfg = opened()
check("D: a dub-sync pair waits -> the HD film's Telegram thumbnail (its largest) is the frame", got == ["big"] and cfg.get("bg", "").endswith("frame.jpg") and cfg.get("frames") == "", (got, cfg.get("bg")))
new._dubsel.pop(UID, None)
# the dub-sync set shows the real film: the job that runs, else the latest one still on the server
import time as _time  # noqa: E402
from pathlib import Path  # noqa: E402
sys.path.insert(0, NEW)                      # the bot imports these two where it needs them (it runs in its own folder)
import dub_queue as dq  # noqa: E402
import dubsync_job as dj  # noqa: E402
sys.path.remove(NEW)
RAW = os.path.join(T, "raw")
os.makedirs(RAW, exist_ok=True)
real_raw, real_q = dj.RAW_DIR, list(dq._q)
dj.RAW_DIR = Path(RAW)
now = _time.time()
NAME = "My Film (2026) 1080p.mp4"
LONG = "A Very Long Film Name That Goes On And On (2026) 1080p 10bit x265 HEVC [Somali] - GROUP.mp4"
try:
    dq._q[:] = [{"uid": str(UID), "title": NAME, "state": "running", "started": now - 300, "added": now - 300, "ended": None}]
    sent = run(open_and_fill(UID))
    d, cfg = opened()
    check("D: dub-sync set, a film runs but its HD is not on the server (yet) -> as before, no error", cfg.get("frames") == "" and cfg.get("bg") == "" and len(sent) == 1, cfg.get("frames"))
    shutil.copyfile(VID, os.path.join(RAW, dj._slug(NAME) + "_hd_ORIG.mp4"))
    open(os.path.join(RAW, dj._slug(NAME) + "_hd_ORIG.det.mp4"), "wb").write(b"x" * 900)        # the engine's helper copies are not the film
    shutil.copyfile(PAL, os.path.join(RAW, dj._slug(NAME) + "_dub_ORIG.mp4"))
    sent = run(open_and_fill(UID))
    d, cfg = opened()
    fj = json.load(open(os.path.join(d, "frames.json"))) if os.path.exists(os.path.join(d, "frames.json")) else {}
    check("D: dub-sync set, a film RUNS -> the Studio shows that HD film's own pictures (24, the frame, its length 96 s)",
          cfg.get("frames", "").endswith("frames.json") and cfg.get("bg", "").endswith("frame.jpg") and len(fj.get("frames", [])) == 24 and fj.get("done") is True
          and abs(fj.get("dur", 0) - 96.0) < 0.1 and cfg.get("active") == "dub", (cfg.get("frames"), len(fj.get("frames", []))))
    new._pending[UID] = dict(job, src=PAL, duration=8.0)
    sent = run(open_and_fill(UID))
    d, cfg = opened()
    fj = json.load(open(os.path.join(d, "frames.json"))) if os.path.exists(os.path.join(d, "frames.json")) else {}
    check("D: dub-sync set, a film runs AND a banner video waits: the dub-sync film is shown (the set he works in comes first)",
          abs(fj.get("dur", 0) - 96.0) < 0.1, fj.get("dur"))
    new._set_ui_profile(UID, "banner")
    sent = run(open_and_fill(UID))
    d, cfg = opened()
    fj = json.load(open(os.path.join(d, "frames.json"))) if os.path.exists(os.path.join(d, "frames.json")) else {}
    check("D: banner set, both there: the video that waits in the panel is shown (8 s)", abs(fj.get("dur", 0) - 8.0) < 0.1 and cfg.get("active") == "banner", fj.get("dur"))
    new._pending.pop(UID, None)
    sent = run(open_and_fill(UID))
    d, cfg = opened()
    fj = json.load(open(os.path.join(d, "frames.json"))) if os.path.exists(os.path.join(d, "frames.json")) else {}
    check("D: banner set, NOTHING waits there (everybody's state after a restart) but his dub-sync film is on the server -> its "
          "pictures, not an empty picture", cfg.get("frames", "").endswith("frames.json") and abs(fj.get("dur", 0) - 96.0) < 0.1 and len(fj.get("frames", [])) == 24
          and cfg.get("active") == "banner", (cfg.get("frames"), fj.get("dur")))
    new._set_ui_profile(UID, "dub")
    dq._q[:] = [{"uid": "777", "title": NAME, "state": "running", "started": now - 300, "added": now - 300, "ended": None}]
    sent = run(open_and_fill(UID))
    d, cfg = opened()
    check("D: ... another user's film is never shown", cfg.get("frames") == "" and cfg.get("bg") == "", cfg.get("frames"))
    for n in os.listdir(RAW):
        os.remove(os.path.join(RAW, n))
    long_file = os.path.join(RAW, dj._slug(LONG) + "_hd_ORIG.mkv")
    shutil.copyfile(VID, long_file)
    os.utime(long_file, (now - 3000, now - 3000))
    dq._q[:] = [{"uid": str(UID), "title": NAME, "state": "finished", "started": now - 9000, "added": now - 9000, "ended": now - 8000},
                {"uid": str(UID), "title": LONG[:60], "state": "finished", "started": now - 3100, "added": now - 3100, "ended": now - 1000}]
    check("(the queue keeps 60 letters of a title: the slug of the cut title is not the file's)", dj._slug(LONG[:60]) != dj._slug(LONG))
    sent = run(open_and_fill(UID))
    d, cfg = opened()
    check("D: dub-sync set, nothing runs -> the LATEST film whose HD is still there, found by the time its job ran when the "
          "queue's cut title does not name the file", cfg.get("frames", "").endswith("frames.json") and cfg.get("bg", "").endswith("frame.jpg"), cfg.get("frames"))
    new._dubsel[UID] = {"msgs": [dub, hd], "hd_i": 1}
    got.clear()
    new.app.download_media = fake_dl
    try:
        sent = run(open_and_fill(UID))
    finally:
        new.app.download_media = real_dl
    d, cfg = opened()
    check("D: ... but a pair that WAITS is the film he is setting up: its thumbnail, not the last film's pictures",
          got == ["big"] and cfg.get("bg", "").endswith("frame.jpg") and cfg.get("frames") == "", (got, cfg.get("frames")))
    new._dubsel.pop(UID, None)
finally:
    dj.RAW_DIR = real_raw
    dq._q[:] = real_q
new._set_ui_profile(UID, "banner")
pj = os.path.join(T, "pal.jpg")
okp = asyncio.run(new._studio_grab(PAL, 4.0, pj))
shp = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", pj], capture_output=True, text=True).stdout.strip()
check("D: a video whose points are not square (720x576 shown 4:3) gives a picture in the shape it is SHOWN in (%s)" % shp, okp and shp == "640,480", shp)
check("D: one picture of a moment past the end / of rubbish: False, no error",
      asyncio.run(new._studio_grab(VID, 500.0, os.path.join(T, "x.jpg"))) is False and asyncio.run(new._studio_grab(BROKEN, 1.0, os.path.join(T, "y.jpg"))) is False)

# ---- E. the dub-sync engine ------------------------------------------------------------------------------------------
ENG = "/opt/dubsync2/src"
code = ("import json, sys; sys.path.insert(0, %r); from dubsync2 import brand; cfg = brand.config_from_json(json.loads(sys.argv[1])); "
        "i, p, l = brand.segment_filters(cfg, 640, 360, seg_offset=0.0, seg_duration=10.0, total_duration=600.0); print(json.dumps([i, p, l]))" % ENG)
data = {"logos": [], "scroll_text": JOHN, "scroll_seconds": 5.0, "scroll_count": 1, "scroll_times": [0.0], "caption_scale": 0.1, "logo_start": 0.0,
        "text_start": 0.0, "caption_font": "spartan", "caption_color": "yellow"}
e_ok, e_det = False, ""
for py in (sys.executable, "/opt/dubsync2/.venv/bin/python"):
    r = subprocess.run([py, "-c", code, json.dumps(data)], capture_output=True, text=True, env=dict(os.environ, BIDHAAN_DIR=NEW, PYTHONPATH=NEW),
                       cwd=NEW)                          # the engine takes the bot's branding.py from where it runs: the copy under test
    if r.returncode == 0:
        ins, parts, lab = json.loads(r.stdout.strip().splitlines()[-1])
        fc = "[0:v]null[v];" + ";".join(parts).replace("/app/assets/fonts", FONT_DIR) + ";[%s]null[outv]" % lab
        img, err = frame(fc)
        ls = text_lines(img) if img is not None else []
        e_ok = len(ls) == 2 and ls[0][2] > ls[1][2] and not err
        e_det = (ls, err, fc[-260:])
        break
    e_det = r.stderr[-300:]
check("E: the dub-sync engine's own filter draws the same caption as typed: two lines, the first moved right (%s)" % (e_det[0] if e_ok else "",), e_ok, e_det)

# ---- F. the page ---------------------------------------------------------------------------------------------------
page = os.path.join(PAGE_DIR, "place.html")
txt = open(page, encoding="utf-8").read() if os.path.exists(page) else ""
need = ('k: "studio"', "sets: sets", "cfg.json", "tg.sendData", "telegram-web-app.js", "out.logos", "out.start", "out.cap", "out.trim",
        "cfg.fonts", "cfg.colors", "cfg.active", "cfg.dur", "cfg.bg", "L.mx", "L.my", "L.c", "L.img", "n: L.n", "on: !!L.on",
        "function capNorm", "white-space: pre", "cfg.frames", "f.lh", 'id="film"', "d.frames", "d.done", "x.img", "x.t", "x.i", 'wrap="off"', 'maxlength="300"')
miss = [k for k in need if k not in txt]
check("F: place.html speaks the bot's language (%d markers: the save, the caption as typed, the font's line pitch, the film strip)" % len(need), txt and not miss, miss)
check("F: the page no longer squeezes the caption onto one line", 'replace(/\\s+/g, " ")' not in txt)

shutil.rmtree(T, ignore_errors=True)
print("STUDIO36_TESTS " + ("ALL PASS" if ok else "FAILED"))
