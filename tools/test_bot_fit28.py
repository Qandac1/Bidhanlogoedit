"""bot28 = live bot + the logo-only path FITS a video into the frame (black bars) instead of stretching it.
Run inside the bot container:   python3 test_bot_fit28.py <live bot dir copy> <bot28 dir copy>
  A. NO BREAK: sources of the frame's shape (16:9 into 16:9, near misses like 1280x718, the "Source" setting,
     upscales and downscales) -> the filter is character for character the live bot's, with banner covers, logos
     and every caption variant.
  B. (control) the live bot STRETCHES a 2.39:1 picture: a circle comes out taller than wide, no bars.
     bot28: the frame asked for, black bars above and below, the circle round, and at the same size the picture
     between the bars is pixel for pixel the source.
  C. A small wide source scaled up, a tall (vertical) source, a 4:3 source: fitted, bars on the right sides,
     the circle round.
  D. A banner cover lands on the picture where the banner is (its fractions are of the source picture).
  E. A logo sits on the picture's own corner with its usual margins, at its usual share of the picture's width.
  F. Kill switch BIDHAAN_FIT=0 -> the live bot's filter.
  G. _fit_rect on real sizes and on garbage: never raises.
  H. The bot's own render(): a wide source at a 16:9 setting -> a file of that frame with the bars.
Prints FIT28_TESTS ALL PASS."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIVE, NEW = sys.argv[1], sys.argv[2]
T = Path(tempfile.mkdtemp(prefix="fit28_"))


def load(d, name):
    sys.path.insert(0, d)
    try:
        for k in ("detect",):
            sys.modules.pop(k, None)
        spec = importlib.util.spec_from_file_location(name, os.path.join(d, "branding.py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
    finally:
        sys.path.remove(d)
    return m


os.environ.pop("BIDHAAN_FIT", None)
old, new = load(LIVE, "br_live"), load(NEW, "br_28")
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


def circle(name, w, h, r):
    """a white circle of radius r on dark grey, w x h"""
    p = T / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=gray:s=%dx%d:r=25,format=gray,geq=lum='if(lte(hypot(X-%d,Y-%d),%d),255,60)'"
                    % (w, h, w // 2, h // 2, r), "-f", "lavfi", "-i", "sine=frequency=440",
                    "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p)], check=True)
    return p


def png(name, w, h, color):
    p = T / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=%s:size=%dx%d" % (color, w, h),
                    "-frames:v", "1", str(p)], check=True)
    return str(p)


COVER, LOGO = png("cover.png", 64, 16, "red"), png("logo.png", 60, 20, "white")


def frame(m, src, sw, sh, cfg, events=()):
    """the first output frame as (rgb bytes, W, H), through m.build_filter and real ffmpeg"""
    fc = m.build_filter(sw, sh, 1.0, list(events), cfg)
    W, H = cfg.width or sw, cfg.height or sh
    ins = ["-i", str(src), "-i", COVER]
    for lg in cfg.logos:
        ins += ["-i", lg.path]
    raw = subprocess.run(["ffmpeg", "-v", "error", *ins, "-filter_complex", fc + ";[outv]format=rgb24[g]",
                          "-map", "[g]", "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True).stdout
    assert len(raw) == W * H * 3, (len(raw), W, H, fc)
    return raw, W, H, fc


def lum(raw, W, H):
    return [[raw[(y * W + x) * 3 + 1] for x in range(W)] for y in range(H)]


def shape(raw, W, H):
    """(bar top, bar bottom, bar left, bar right, circle width, circle height) -- black < 30, circle > 200"""
    g = lum(raw, W, H)
    rows = [max(r) for r in g]
    cols = [max(g[y][x] for y in range(H)) for x in range(W)]
    top = next((i for i, v in enumerate(rows) if v > 30), H)
    bot = next((i for i, v in enumerate(reversed(rows)) if v > 30), H)
    left = next((i for i, v in enumerate(cols) if v > 30), W)
    right = next((i for i, v in enumerate(reversed(cols)) if v > 30), W)
    cw = max(sum(1 for v in r if v > 200) for r in g)
    ch = sum(1 for r in g if max(r) > 200)
    return top, bot, left, right, cw, ch


def bbox(raw, W, H, pred):
    xs, ys = [], []
    for y in range(H):
        for x in range(W):
            i = (y * W + x) * 3
            if pred(raw[i], raw[i + 1], raw[i + 2]):
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1) if xs else None


def cfg_of(m, w, h, **kw):
    return m.RenderConfig(logos=kw.pop("logos", []), cover_png=COVER, scroll_text=kw.pop("scroll_text", ""),
                          width=w, height=h, **kw)


WIDE = circle("wide.mp4", 640, 268, 100)
SMALLWIDE = circle("smallwide.mp4", 320, 134, 50)
TALL = circle("tall.mp4", 180, 320, 60)
FOUR3 = circle("four3.mp4", 320, 240, 80)

# ---- A. no break ------------------------------------------------------------------------------------------
same = []
for (sw, sh), (ow, oh) in (((1280, 720), (1920, 1080)), ((640, 360), (1920, 1080)), ((1920, 1080), (1920, 1080)),
                           ((1280, 718), (1280, 720)), ((1920, 1072), (1920, 1080)), ((3840, 2160), (1920, 1080)),
                           ((1280, 720), (0, 0)), ((1920, 804), (0, 0)), ((640, 268), (640, 268)),
                           ((854, 480), (1280, 720)), ((1916, 1080), (1920, 1080))):
    for variant in range(4):
        def mk(m):
            ev = [m.CoverEvent(10.0, 20.0, 0.1, 0.8, 0.5, 0.1), m.CoverEvent(30.0, 40.0, 0.2, 0.7, 0.4, 0.08)] if variant in (1, 3) else []
            lg = [m.Logo(path=LOGO, corner="TL", frac=0.132, margin_x=0.038, margin_y=0.1),
                  m.Logo(path=LOGO, corner="BR", frac=0.1, margin_x=0.02, margin_y=0.05)] if variant in (2, 3) else []
            c = cfg_of(m, ow, oh, logos=lg, scroll_text="Bidhaan 123" if variant == 3 else "",
                       scroll_times=[60.0, 120.0] if variant == 3 else [], logo_start=45.0)
            return m.build_filter(sw, sh, 600.0, ev, c)
        a, b = mk(old), mk(new)
        same.append((a == b, (sw, sh, ow, oh, variant), a, b))
bad = [x for x in same if not x[0]]
check("A: %d filters for sources of the frame's shape are character for character the live bot's" % len(same), not bad, bad[:2])

# ---- B. the wide picture ------------------------------------------------------------------------------------
raw, W, H, fc = frame(old, WIDE, 640, 268, cfg_of(old, 640, 360))
t, b, l, r, cw, ch = shape(raw, W, H)
check("B (control): the live bot stretches it -- no bars, the circle %d wide x %d high" % (cw, ch),
      t == 0 and b == 0 and ch > cw * 1.25, (t, b, cw, ch, fc))
raw, W, H, fc = frame(new, WIDE, 640, 268, cfg_of(new, 640, 360))
t, b, l, r, cw, ch = shape(raw, W, H)
check("B: bot28 gives the 640x360 frame with black bars of 46 px above and below", (W, H, t, b, l, r) == (640, 360, 46, 46, 0, 0), (t, b, l, r, fc))
check("B: the circle is round (%d wide x %d high)" % (cw, ch), abs(cw - ch) <= 4, (cw, ch))
src = subprocess.run(["ffmpeg", "-v", "error", "-i", str(WIDE), "-frames:v", "1", "-vf", "setsar=1,format=rgb24",
                      "-f", "rawvideo", "-"], capture_output=True).stdout
mid = b"".join(raw[(y * W) * 3:(y * W + W) * 3] for y in range(46, 46 + 268))
check("B: the picture between the bars is pixel for pixel the source",
      len(mid) == len(src) and max(abs(x - y) for x, y in zip(mid, src)) == 0,
      (len(mid), len(src), max(abs(x - y) for x, y in zip(mid, src)) if len(mid) == len(src) else -1))

# ---- C. other shapes ----------------------------------------------------------------------------------------
raw, W, H, fc = frame(new, SMALLWIDE, 320, 134, cfg_of(new, 640, 360))
t, b, l, r, cw, ch = shape(raw, W, H)
check("C: a small wide source scaled up: bars 46 px above and below, the circle round (%dx%d)" % (cw, ch),
      (t, b, l, r) == (46, 46, 0, 0) and abs(cw - ch) <= 6, (t, b, l, r, cw, ch, fc))
raw, W, H, fc = frame(new, TALL, 180, 320, cfg_of(new, 640, 360))
t, b, l, r, cw, ch = shape(raw, W, H)
check("C: a vertical source: bars left and right (%d / %d px), none above or below, the circle round (%dx%d)" % (l, r, cw, ch),
      (t, b) == (0, 0) and l == r == (640 - 202) // 2 and abs(cw - ch) <= 6, (t, b, l, r, cw, ch, fc))
raw, W, H, fc = frame(new, FOUR3, 320, 240, cfg_of(new, 640, 360))
t, b, l, r, cw, ch = shape(raw, W, H)
check("C: a 4:3 source: bars left and right (80 px), the circle round (%dx%d)" % (cw, ch),
      (t, b, l, r) == (0, 0, 80, 80) and abs(cw - ch) <= 6, (t, b, l, r, cw, ch, fc))

# ---- D. a banner cover ----------------------------------------------------------------------------------------
ev = [new.CoverEvent(0.0, 5.0, 0.1, 0.8, 0.5, 0.1)]
raw, W, H, fc = frame(new, WIDE, 640, 268, cfg_of(new, 640, 360), ev)
bb = bbox(raw, W, H, lambda R, G, B: R > 180 and G < 90 and B < 90)
exp = (int(0.1 * 640), 46 + int(0.8 * 268), int(0.5 * 640), int(0.1 * 268))
check("D: the cover is on the picture where the banner is %s" % (exp,),
      bb is not None and all(abs(a - e) <= 2 for a, e in zip(bb, exp)), (bb, exp, fc))
rawo, W, H, fco = frame(old, WIDE, 640, 268, cfg_of(old, 640, 360), [old.CoverEvent(0.0, 5.0, 0.1, 0.8, 0.5, 0.1)])
bbo = bbox(rawo, W, H, lambda R, G, B: R > 180 and G < 90 and B < 90)
check("D (control): in the live bot's stretched frame the same banner cover sits at %s" % (bbo,),
      bbo is not None and abs(bbo[1] - int(0.8 * 360)) <= 2, bbo)

# ---- E. a logo ------------------------------------------------------------------------------------------------
def blue(R, G, B):
    return B > 180 and R < 90 and G < 90


BLUE = png("blue.png", 60, 20, "blue")
for corner, exp in (("TL", (int(0.05 * 640), 46 + int(0.1 * 268))),
                    ("BR", (640 - int(0.05 * 640) - 128, 360 - 46 - int(0.1 * 268) - 42))):
    lg = [new.Logo(path=BLUE, corner=corner, frac=0.2, margin_x=0.05, margin_y=0.1)]
    raw, W, H, fc = frame(new, WIDE, 640, 268, cfg_of(new, 640, 360, logos=lg))
    bb = bbox(raw, W, H, blue)
    check("E: a %s logo sits on the picture's corner at %s, 128 px wide" % (corner, exp),
          bb is not None and abs(bb[0] - exp[0]) <= 2 and abs(bb[1] - exp[1]) <= 2 and abs(bb[2] - 128) <= 2, (bb, exp, fc))
lg = [new.Logo(path=BLUE, corner="TL", frac=0.2, margin_x=0.05, margin_y=0.1)]
raw, W, H, fc = frame(new, TALL, 180, 320, cfg_of(new, 640, 360, logos=lg))
bb = bbox(raw, W, H, blue)
check("E: on a vertical picture the logo is on the picture (x from %d), not out on the black" % ((640 - 202) // 2),
      bb is not None and bb[0] >= (640 - 202) // 2 and bb[0] + bb[2] <= (640 + 202) // 2 + 1, (bb, fc))

# ---- F. kill switch -------------------------------------------------------------------------------------------
os.environ["BIDHAAN_FIT"] = "0"
off = load(NEW, "br_28_off")
os.environ.pop("BIDHAAN_FIT", None)
check("F: BIDHAAN_FIT=0 -> the live bot's filter for the wide source",
      off.build_filter(640, 268, 600.0, [off.CoverEvent(1.0, 2.0, 0.1, 0.8, 0.5, 0.1)], cfg_of(off, 640, 360))
      == old.build_filter(640, 268, 600.0, [old.CoverEvent(1.0, 2.0, 0.1, 0.8, 0.5, 0.1)], cfg_of(old, 640, 360)))

# ---- G. _fit_rect ---------------------------------------------------------------------------------------------
TABLE = [((1920, 804, 1920, 1080), (0, 138, 1920, 804)), ((1280, 536, 1920, 1080), (0, 138, 1920, 804)),
         ((640, 268, 1280, 720), (0, 92, 1280, 536)), ((1080, 1920, 1920, 1080), (656, 0, 608, 1080)),
         ((1440, 1080, 1920, 1080), (240, 0, 1440, 1080)), ((1920, 1080, 1920, 1080), None),
         ((1280, 720, 1920, 1080), None), ((1280, 718, 1280, 720), None), ((1916, 1080, 1920, 1080), None),
         ((0, 0, 1920, 1080), None), ((1920, 804, 0, 0), None)]
bad = [(i, new._fit_rect(*i), o) for i, o in TABLE if new._fit_rect(*i) != o]
check("G: %d real sizes -> the right place for the picture (None = the scale of before)" % len(TABLE), not bad, bad)
try:
    g = [new._fit_rect(None, None, 1920, 1080), new._fit_rect("a", 2, 3, 4), new._fit_rect(1e9, 1, 1920, 1080)]
    check("G: garbage never raises", g[0] is None and g[1] is None, g)
except Exception as e:
    check("G: garbage never raises", False, repr(e))

# ---- H. the bot's own render() --------------------------------------------------------------------------------
out = T / "out.mp4"
c = cfg_of(new, 640, 360, logos=[new.Logo(path=BLUE, corner="TL", frac=0.2, margin_x=0.05, margin_y=0.1)])
c.video_bitrate_k = 800
try:
    new.render(str(WIDE), str(out), [], c)
    wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                         "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    cd = subprocess.run(["ffmpeg", "-v", "info", "-i", str(out), "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    crops = [x.split("crop=")[1].split()[0] for x in cd.splitlines() if "crop=" in x]
    check("H: render() of the wide source at 640x360 -> a 640x360 file, the picture 640x268 from y=46 (%s)" % (crops[-1] if crops else "?"),
          wh == "640,360" and crops and crops[-1] == "640:268:0:46", (wh, crops[-3:]))
except Exception as e:
    check("H: render() of the wide source", False, repr(e)[:400])

shutil.rmtree(T, ignore_errors=True)
print("FIT28_TESTS " + ("ALL PASS" if ok else "FAILED"))
sys.exit(0 if ok else 1)
