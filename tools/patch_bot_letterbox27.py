"""bot27: BLACK CINEMA BARS -- a picture wider than 16:9 is delivered in a 16:9 frame (1920x1080), not as a
1920x804 file.

John 2026-10-04 (two screenshots: "Pooja Meri Jaan" with black bars vs the bot's CBI 5 without; his Premiere
sequence 1920x1080 square pixels): "I want the black cinematic bars. I do NOT want the video cropped, stretched or
zoomed ... preserve its original cinematic aspect ratio and framing."

Measured on the files: nothing was cropped or stretched -- CBI 5's master IS 1920x804 and the bot delivered
1920x804; the example is 1920x1080 with the bars inside the file. The rule responsible is run_dubsync's
"never render above the master's own size" (Ghost's 1280x542 master once went out upscaled to 1920x1080): when the
setting (1920x1080) is larger than the master it shrank the FRAME to the master's own size, bars gone. A setting
SMALLER than the master (1280x720 for a 1920x804 master) already came out with bars -- the engine's filter is
  scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2:black
and only needs a 16:9 W x H.

bot27, right after that rule: a frame WIDER than 16:9 gets its height raised to 16:9 at the same width
(1920x804 -> 1920x1080, 1280x542 -> 1280x720, 3840x1608 -> 3840x2160). The picture keeps its size (never scaled
up: the Ghost rule stays), its shape and every pixel; the bitrate is the one the panel quoted (bars cost nothing).
A master at 16:9 or narrower (also a vertical clip): the frame of before, byte for byte the same arguments.
The LOGO keeps its place ON THE PICTURE: its margin is re-expressed for the taller frame so that it sits the
same number of pixels from the picture's own edge as before (it does not move up onto the bar); the caption's
letter size is kept the same way. Every later step reads the frame from the film itself (restore_head,
opening_restore, tail_restore, repair_shots, logo_check: the same scale+pad / the same brand file).
NOT covered: the dialogue-layer mode (dlg: picked when the conform aligner refuses a pair, or by hand) renders the
HD's own frame through its own encoder -- it stays as it was, with its brand settings as they were.
Kill switch: BIDHAAN_LETTERBOX=0 in the bot's environment.
Usage: python patch_bot_letterbox27.py <bot dir>     (patches <bot dir>/dubsync_job.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "dubsync_job.py"
s = P.read_text()
if "LETTERBOX_169" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''async def run_dubsync(
    hd: Path, dub: Path, title: str,
''', '''# bot27 (John 2026-10-04: "I want the black cinematic bars ... not cropped, stretched or zoomed", like his
# 1920x1080 Premiere sequence): a frame WIDER than 16:9 -- CBI 5's master is 1920x804 and went out as a 1920x804
# file -- becomes 16:9 at the same width (1920x1080); the engine's own scale+pad puts the picture in the middle,
# untouched, with black bars above and below. 16:9 or narrower: the frame of before.
LETTERBOX_169 = os.environ.get("BIDHAAN_LETTERBOX", "1") != "0"


def _frame_169(width: int, height: int) -> tuple:
    """(frame width, frame height, bar height in pixels) for the render frame the old rules chose. Never raises."""
    try:
        w, h = int(width), int(height)
        if not LETTERBOX_169 or w <= 0 or h <= 0 or w * 9 <= h * 16:
            return width, height, 0
        full = int(round(w * 9 / 16.0 / 2)) * 2
        bar = (full - h) // 2
        if bar < 1:
            return width, height, 0
        return w, full, bar
    except Exception:
        return width, height, 0


def _brand_on_picture(cfg: dict, pic_h: int, frame_h: int, bar: int) -> dict:
    """The brand settings for a frame with bars: every logo the same pixels from the PICTURE's edge as in the
    frame without bars, the caption's letters the same size. A copy; the caller's settings are not touched."""
    try:
        if not cfg or bar <= 0 or pic_h <= 0 or frame_h <= 0:
            return cfg
        out = json.loads(json.dumps(cfg))
        for lg in out.get("logos") or []:
            my = int(float(lg.get("margin_y", 0.015)) * pic_h)
            lg["margin_y"] = (bar + my + 0.5) / float(frame_h)
        if out.get("caption_scale"):
            out["caption_scale"] = float(out["caption_scale"]) * pic_h / float(frame_h)
        return out
    except Exception:
        return cfg


async def run_dubsync(
    hd: Path, dub: Path, title: str,
''', "helpers _frame_169 / _brand_on_picture")

rep('''            width, height = _mw - (_mw % 2), _mh - (_mh % 2)
    except Exception:
        pass
    out_name = f"{title}_final.mp4"
''', '''            width, height = _mw - (_mw % 2), _mh - (_mh % 2)
    except Exception:
        pass
    # bot27: black cinema bars -- a frame wider than 16:9 becomes 16:9 at the same width
    _pic_h = height
    width, height, _bar = _frame_169(width, height)
    _brand_dlg = brand_cfg          # the dialogue-layer mode renders the HD's own frame: its settings as they are
    if _bar and brand_cfg:
        brand_cfg = _brand_on_picture(brand_cfg, _pic_h, height, _bar)
    out_name = f"{title}_final.mp4"
''', "the frame in run_dubsync")

rep('''    if mode == "dlg":
        return await _render_dialogue_layer(hd, dub, title, on_progress,
''', '''    if mode == "dlg":
        # bot27: this mode renders the HD's own frame (no bars added there): the brand settings as they were
        if _bar and _brand_dlg and brand_path:
            try:
                brand_path.write_text(json.dumps(_brand_dlg))
            except Exception:
                pass
        return await _render_dialogue_layer(hd, dub, title, on_progress,
''', "the dialogue-layer mode keeps its own brand settings")

assert "\nimport os\n" in s.split("def ", 1)[0], "dubsync_job.py does not import os at the top"
P.write_text(s)
print("patched %s" % P)
