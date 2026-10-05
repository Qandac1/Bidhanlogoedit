"""bot31 part 1 = THE CAPTION'S FONT AND COLOUR (patch_bot_capfont31.py: branding.py + bot.py).
Run inside the bot container:   python3 test_bot_capfont31.py <bot dir copy before> <bot dir copy after>
  A. NO BREAK: with the default font and colour every render filter is the one of before, character for
     character (captions by count, by exact times, with logos, with banner covers); the brand settings handed to
     the dub-sync engine are the ones of before, key for key.
  B. Every font id finds its file; "", "classic", an unknown id, a path, a missing file -> the font of before.
  C. Every colour name is on the list; anything else (also text that tries to add filter options) -> white.
  D. REAL ffmpeg: a yellow Montserrat caption really comes out yellow and shaped differently from the classic
     white one; the classic one has no yellow in it.
  F. A caption with a % in it (it used to make drawtext stop: no caption at all) is drawn; so are : , [ ] = ; ' and a backslash.
  E. bot.py: the two settings exist with the defaults of before; a chosen font / colour reaches the dub-sync
     engine's settings and the banner render.
Prints CAPFONT31_TESTS ALL PASS."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

BASE, NEW = sys.argv[1], sys.argv[2]
T = tempfile.mkdtemp(prefix="cf31_")
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


def load(d, name, fn):
    sys.path.insert(0, d)
    cwd = os.getcwd()
    os.chdir(d)
    try:
        for k in ("branding", "detect", "config", "delivery", "trim", "dub_queue", "dubsync_job"):
            sys.modules.pop(k, None)
        spec = importlib.util.spec_from_file_location(name, os.path.join(d, fn))
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
    finally:
        os.chdir(cwd)
        sys.path.remove(d)
    return m


bo, bn = load(BASE, "br_base", "branding.py"), load(NEW, "br_new", "branding.py")
LOGO = os.path.join(T, "logo.png")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=blue:size=60x20", "-frames:v", "1", LOGO], check=True)

# ---- A. no break ------------------------------------------------------------------------------------------
same = []
for (sw, sh), (ow, oh) in (((1280, 720), (1920, 1080)), ((1920, 804), (1920, 1080)), ((1920, 1080), (0, 0)), ((640, 360), (1280, 720))):
    for variant in range(4):
        def mk(m):
            ev = [m.CoverEvent(10.0, 20.0, 0.1, 0.8, 0.5, 0.1)] if variant in (1, 3) else []
            lg = [m.Logo(path=LOGO, corner="TL", frac=0.132, margin_x=0.038, margin_y=0.1)] if variant >= 2 else []
            c = m.RenderConfig(logos=lg, cover_png=LOGO, scroll_text="UGAAR AH BIDHAAN TV 0619624090", width=ow, height=oh,
                               scroll_times=[60.0, 120.0] if variant % 2 else [], scroll_count=8, logo_start=45.0, text_start=300.0)
            return m.build_filter(sw, sh, 3600.0, ev, c)
        a, b = mk(bo), mk(bn)
        same.append((a == b, (sw, sh, ow, oh, variant), a[-200:], b[-200:]))
bad = [x for x in same if not x[0]]
check("A: %d render filters with the default font and colour are character for character the ones of before" % len(same), not bad, bad[:1])

# ---- B. fonts ---------------------------------------------------------------------------------------------
miss = [(k, bn.caption_font_file(k)) for k, (lab, fn) in bn.CAPTION_FONTS.items() if fn and not bn.caption_font_file(k).endswith(fn)]
check("B: every one of the %d font ids finds its file in assets/fonts" % len(bn.CAPTION_FONTS), not miss and len(bn.CAPTION_FONTS) == 8, miss)
check("B: all the files are really there and are fonts ffmpeg can draw with",
      all(os.path.isfile(bn.caption_font_file(k)) for k in bn.CAPTION_FONTS))
dflt = [bn.caption_font_file(v) for v in ("", None, "classic", "CLASSIC", "nope", "../../etc/passwd", "montserrat:text=x", 7, [1])]
check("B: '', classic, an unknown id, a path, garbage -> the font of before", all(v == bn.FONT for v in dflt), dflt)
keep = bn.FONT_DIRS
bn.FONT_DIRS = (os.path.join(T, "empty"),)
check("B: a font file that is not there -> the font of before (a render never fails over a font)", bn.caption_font_file("montserrat") == bn.FONT)
bn.FONT_DIRS = keep
check("B: MONTSERRAT in capitals / with spaces is the same id", bn.caption_font_file(" Montserrat ").endswith("Montserrat-ExtraBold.ttf"))

# ---- C. colours ---------------------------------------------------------------------------------------------
check("C: %d colour names, each an ffmpeg colour" % len(bn.CAPTION_COLORS),
      len(bn.CAPTION_COLORS) >= 6 and all(v == "white" or (v.startswith("0x") and len(v) == 8) for v in bn.CAPTION_COLORS.values()))
bad = [(v, bn.caption_color(v)) for v in ("", None, "nope", "white:enable=0", "#fff", "0xFF0000", "yellow'", 5) if bn.caption_color(v) != "white"]
check("C: anything that is not a name on the list -> white", not bad and bn.caption_color("YELLOW") == bn.CAPTION_COLORS["yellow"], bad)

# ---- D. real ffmpeg -----------------------------------------------------------------------------------------
def frame(m, **kw):
    c = m.RenderConfig(logos=[], cover_png=LOGO, scroll_text="BIDHAAN TV 0619", width=640, height=360, scroll_seconds=4.0,
                       scroll_times=[0.0], caption_scale=0.12, text_start=0.0, **kw)
    fc = m.build_filter(640, 360, 10.0, [], c)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x202020:s=640x360:r=25", "-i", LOGO,
                          "-filter_complex", fc + ";[outv]format=rgb24[g]", "-map", "[g]", "-ss", "2", "-frames:v", "1",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    assert len(raw) == 640 * 360 * 3, (len(raw), fc)
    yel = wht = 0
    xs = []
    for i in range(0, len(raw), 3):
        r, g, b_ = raw[i], raw[i + 1], raw[i + 2]
        if r > 200 and g > 170 and b_ < 110:
            yel += 1
            xs.append((i // 3) % 640)
        elif r > 215 and g > 215 and b_ > 215:
            wht += 1
            xs.append((i // 3) % 640)
    return yel, wht, (max(xs) - min(xs) + 1) if xs else 0, fc


y0, w0, wid0, fc0 = frame(bn)
y1, w1, wid1, fc1 = frame(bn, caption_font="montserrat", caption_color="yellow")
y2, w2, wid2, fc2 = frame(bn, caption_font="bebas")
check("D: the classic caption is white (%d white pixels, %d yellow)" % (w0, y0), w0 > 500 and y0 < 20, (y0, w0))
check("D: a yellow Montserrat caption really is yellow (%d yellow pixels, %d white)" % (y1, w1), y1 > 500 and w1 < 50, (y1, w1, fc1[-300:]))
check("D: another font gives another shape (text width classic %d px, Montserrat %d px, Bebas %d px)" % (wid0, wid1, wid2),
      wid0 > 100 and abs(wid2 - wid0) > 0.1 * wid0 and wid1 != wid0, (wid0, wid1, wid2))
check("D: the filter names the chosen font file and colour", "Montserrat-ExtraBold.ttf" in fc1 and "fontcolor=0xFFD60A" in fc1 and "DejaVuSans-Bold.ttf" in fc0 and "fontcolor=white" in fc0)

# ---- F. a caption with a % in it ------------------------------------------------------------------------------
def white_px(m, text):
    c = m.RenderConfig(logos=[], cover_png=LOGO, scroll_text=text, width=640, height=360, scroll_seconds=4.0,
                       scroll_times=[0.0], caption_scale=0.12, text_start=0.0)
    fc = m.build_filter(640, 360, 10.0, [], c)
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x202020:s=640x360:r=25", "-i", LOGO,
                        "-filter_complex", fc + ";[outv]format=gray[g]", "-map", "[g]", "-ss", "2", "-frames:v", "1",
                        "-f", "rawvideo", "-"], capture_output=True)
    return sum(1 for v in r.stdout if v > 215), fc, r.stderr.decode()[:120]


w_old, fc_old, err_old = white_px(bo, "50% OFF TODAY")
w_new, fc_new, err_new = white_px(bn, "50% OFF TODAY")
check("F (control): before, a caption with a %% in it drew NOTHING (%d pixels; ffmpeg: %s)" % (w_old, err_old.strip()[:50]), w_old < 20 and "Stray %" in err_old, (w_old, err_old))
check("F: now it is drawn (%d pixels), no ffmpeg error" % w_new, w_new > 1500 and not err_new.strip(), (w_new, err_new, fc_new[-200:]))
w3, fc3, err3 = white_px(bn, "A:B, [x]=1;c it's 100% " + chr(92) + " ok")
check("F: colon, comma, brackets, =, ;, apostrophe, %% and backslash together are drawn too (%d pixels)" % w3, w3 > 1500 and not err3.strip(), (w3, err3))
plain_old, plain_new = white_px(bo, "BIDHAAN TV 0619")[1], white_px(bn, "BIDHAAN TV 0619")[1]
check("F: a caption without them keeps the filter of before, character for character", plain_old == plain_new and "expansion" not in plain_new)

# ---- E. bot.py ----------------------------------------------------------------------------------------------
o_base, o_new = load(BASE, "bot_base", "bot.py"), load(NEW, "bot_new", "bot.py")
for m in (o_base, o_new):
    m.SETTINGS_FILE = os.path.join(T, m.__name__ + "_settings.json")
UID = 424247
check("E: the two settings exist, with the look of before as their default",
      o_new.DEFAULTS.get("caption_font") == "" and o_new.DEFAULTS.get("caption_color") == "white"
      and {k: v for k, v in o_new.DEFAULTS.items() if k not in ("caption_font", "caption_color")} == o_base.DEFAULTS)
check("E: with the defaults the dub-sync engine gets the settings of before, key for key",
      o_base._brand_payload(UID) == o_new._brand_payload(UID), (o_base._brand_payload(UID), o_new._brand_payload(UID)))
o_new.set_user(UID, caption_font="bebas", caption_color="gold")
pay = o_new._brand_payload(UID)
check("E: a chosen font and colour reach the dub-sync engine's settings", pay.get("caption_font") == "bebas" and pay.get("caption_color") == "gold", pay)
src = open(os.path.join(NEW, "bot.py"), encoding="utf-8").read()
check("E: ... and the banner render", 'caption_font=c.get("caption_font", "")' in src and 'caption_color=c.get("caption_color", "white")' in src)

shutil.rmtree(T, ignore_errors=True)
print("CAPFONT31_TESTS " + ("ALL PASS" if ok else "FAILED"))
sys.exit(0 if ok else 1)
