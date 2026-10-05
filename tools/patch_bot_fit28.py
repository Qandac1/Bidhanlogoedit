"""bot28: the LOGO-ONLY path never stretches a video -- a source whose shape is not the frame's is FITTED into the
frame with black bars (what Filmora / Premiere do with a 1920x1080 project).

John 2026-10-04: "I do NOT want the video cropped, stretched, or zoomed to fill the 16:9 frame." bot27 gave the
dub-sync path its black bars. Reading the other path (a video sent only for the logo / banner cover) showed
  branding.build_filter:  [0:v]scale=<out_w>:<out_h>,setsar=1
-- a plain scale to the setting (1920x1080). Proven on a file (tools/probe_batch_stretch.py): a 2.39:1 picture
comes out filling 16:9, a circle 201 px wide x 269 px high (stretched x1.34), no bars.

bot28, in build_filter: when the source's shape differs from the frame's by more than FIT_TOL (2 %), the picture
is scaled to FIT (shape kept) and padded with black to the frame; the banner covers are placed on the picture
(their fractions are of the source picture), and each logo sits on the picture's own corner with its usual
margins. A source of the frame's shape (16:9 into 1920x1080, also 1280x718-like near misses) and the "Source"
setting: the filter of before, character for character. Kill switch: BIDHAAN_FIT=0.
Usage: python patch_bot_fit28.py <bot dir>     (patches <bot dir>/branding.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "branding.py"
s = P.read_text()
if "FIT_TOL" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''# ----------------------------------------------------------------- filter
def build_filter(src_w: int, src_h: int, duration: float,
                 events: list[CoverEvent], cfg: RenderConfig) -> str:
    out_w = cfg.width or src_w
    out_h = cfg.height or src_h
''', '''# bot28 (John 2026-10-04: "NOT cropped, stretched, or zoomed to fill the 16:9 frame"): a source whose shape is not
# the frame's is fitted into the frame with black bars -- the plain scale below stretched a 2.39:1 picture x1.34.
FIT_ON = os.environ.get("BIDHAAN_FIT", "1") != "0"
FIT_TOL = 0.02          # shapes within 2 % of each other: the scale of before (1280x718 into 1280x720)


def _fit_rect(src_w: int, src_h: int, out_w: int, out_h: int):
    """(x, y, w, h) of the picture fitted inside the out frame (even sizes, centred), or None when the plain
    scale of before applies: the same shape (within FIT_TOL), unusable sizes, the switch off. Never raises."""
    try:
        if not FIT_ON or min(src_w, src_h, out_w, out_h) <= 0:
            return None
        if abs((src_w * out_h) / float(src_h * out_w) - 1.0) <= FIT_TOL:
            return None
        k = min(out_w / float(src_w), out_h / float(src_h))
        w = min(out_w, max(2, int(round(src_w * k / 2.0)) * 2))
        h = min(out_h, max(2, int(round(src_h * k / 2.0)) * 2))
        return (out_w - w) // 2, (out_h - h) // 2, w, h
    except Exception:
        return None


# ----------------------------------------------------------------- filter
def build_filter(src_w: int, src_h: int, duration: float,
                 events: list[CoverEvent], cfg: RenderConfig) -> str:
    out_w = cfg.width or src_w
    out_h = cfg.height or src_h
    _fit = _fit_rect(src_w, src_h, out_w, out_h)
    # the picture's own place inside the frame: covers and logos are put on IT (the whole frame when not fitted)
    _px, _py, _pw, _ph = _fit if _fit else (0, 0, out_w, out_h)
''', "helper _fit_rect + the picture's place")

rep('''    if out_w == src_w and out_h == src_h:
        parts: list[str] = ["[0:v]setsar=1[base]"]
    else:
        parts = ["[0:v]scale=%d:%d,setsar=1[base]" % (out_w, out_h)]
''', '''    if out_w == src_w and out_h == src_h:
        parts: list[str] = ["[0:v]setsar=1[base]"]
    elif _fit:
        parts = ["[0:v]scale=%d:%d,pad=%d:%d:%d:%d:black,setsar=1[base]" % (_pw, _ph, out_w, out_h, _px, _py)]
    else:
        parts = ["[0:v]scale=%d:%d,setsar=1[base]" % (out_w, out_h)]
''', "fit + pad instead of the plain scale")

rep('''            bw = max(2, int(e.w * out_w))
            bh = max(2, int(e.h * out_h))
            bx, by = int(e.x * out_w), int(e.y * out_h)
''', '''            bw = max(2, int(e.w * _pw))
            bh = max(2, int(e.h * _ph))
            bx, by = _px + int(e.x * _pw), _py + int(e.y * _ph)
''', "banner covers on the picture")

rep('''        lw = max(40, int(out_w * lg.frac))
        mx, my = int(lg.margin_x * out_w), int(lg.margin_y * out_h)
        # format=rgba BEFORE scale keeps the alpha channel (else transparent
''', '''        lw = max(40, int(_pw * lg.frac))
        mx, my = _px + int(lg.margin_x * _pw), _py + int(lg.margin_y * _ph)
        # format=rgba BEFORE scale keeps the alpha channel (else transparent
''', "logos on the picture")

assert "\nimport os\n" in s.split("def ", 1)[0], "branding.py does not import os at the top"
P.write_text(s)
print("patched %s" % P)
