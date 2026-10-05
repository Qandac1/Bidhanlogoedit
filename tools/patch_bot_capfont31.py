"""bot31 (part 1): THE CAPTION'S FONT AND COLOUR -- render support in the bot (branding.py + bot.py).

John 2026-10-05: "caption in there ... different fonts ... more like studio". The caption was always DejaVu Sans
Bold in white. Now a setting names a font BY ID (never a path) and a colour from a fixed list:
  branding.py  CAPTION_FONTS (8 ids -> files in assets/fonts), caption_font_file(id), CAPTION_COLORS,
               caption_color(v); RenderConfig.caption_font / .caption_color; build_filter draws with them.
  bot.py       DEFAULTS caption_font "" / caption_color "white"; the banner render and the brand settings handed
               to the dub-sync engine carry both.
A caption with a % or a backslash in it is drawn at last (it used to make drawtext stop: "Stray %", no caption).
With the defaults ("" / "white") every other filter is the live bot's, character for character. An unknown id, a missing
font file or a colour that is not on the list falls back to the default -- a render never fails over a font.
Usage: python patch_bot_capfont31.py <bot dir>     (patches <bot dir>/branding.py and bot.py in place)"""
import sys
from pathlib import Path

D = Path(sys.argv[1])
B, O = D / "branding.py", D / "bot.py"
b, o = B.read_text(), O.read_text()
if "CAPTION_FONTS" in b or "caption_font" in o:
    sys.exit("already patched: %s" % D)


def rep(src, old, new, what):
    n = src.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    print("ok  " + what)
    return src.replace(old, new)


b = rep(b, '''CORNERS = {
''', '''# bot31 (John 2026-10-05: "different fonts"): the caption's font is chosen BY ID, its colour from a list. The files
# live in assets/fonts (Debian's own font packages: Montserrat, Roboto, Open Sans, Lato, Bebas Neue; DejaVu is
# the system's). "" / an unknown id / a missing file = the font of before.
FONT_DIRS = ("/app/assets/fonts", "/opt/Bidhanlogoedit/assets/fonts")
CAPTION_FONTS = {
    "classic": ("Classic", ""),
    "montserrat": ("Montserrat", "Montserrat-ExtraBold.ttf"),
    "roboto": ("Roboto", "Roboto-Bold.ttf"),
    "condensed": ("Condensed", "RobotoCondensed-Bold.ttf"),
    "opensans": ("Open Sans", "OpenSans-Bold.ttf"),
    "lato": ("Lato", "Lato-Black.ttf"),
    "bebas": ("Bebas", "BebasNeue-Bold.otf"),
    "serif": ("Serif", "DejaVuSerif-Bold.ttf"),
}
CAPTION_COLORS = {"white": "white", "yellow": "0xFFD60A", "gold": "0xFFC107", "cyan": "0x4DD0E1",
                  "green": "0x69F0AE", "pink": "0xFF4F9A", "red": "0xFF5252", "orange": "0xFF9F0A"}


def caption_font_file(font_id) -> str:
    """The font file for an id of CAPTION_FONTS; the default font for anything else or a file that is not there."""
    try:
        name = CAPTION_FONTS.get(str(font_id or "").strip().lower(), ("", ""))[1]
        if name:
            for d in FONT_DIRS:
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    return p
    except Exception:
        pass
    return FONT


def caption_color(v) -> str:
    """The ffmpeg colour for a name of CAPTION_COLORS; white for anything else."""
    try:
        return CAPTION_COLORS.get(str(v or "").strip().lower(), "white")
    except Exception:
        return "white"


def caption_text_arg(text) -> tuple:
    """(extra drawtext option, the escaped text) for a caption. A text with a % or a backslash in it made drawtext
    stop with "Stray %" and draw NOTHING ("50% OFF" never showed): such a text is drawn with expansion=none --
    letter for letter. Every other text: the option and the escaping of before, character for character."""
    t = str(text or "")
    if "%" in t or "\\\\" in t:
        return "expansion=none:", t.replace("\\\\", "\\\\\\\\").replace(":", "\\\\:").replace("'", "\\u2019")
    return "", _esc_text(t)


CORNERS = {
''', "branding: the font / colour lists and their look-ups")

b = rep(b, '''    caption_scale: float = 0.023   # caption font height as fraction of output h
''', '''    caption_scale: float = 0.023   # caption font height as fraction of output h
    caption_font: str = ""         # an id of CAPTION_FONTS ("" = the classic font)
    caption_color: str = "white"   # a name of CAPTION_COLORS
''', "branding: RenderConfig.caption_font / caption_color")

b = rep(b, '''    base = (f"drawtext=fontfile={FONT}:text='{txt}':fontcolor=white:"
''', '''    _cap_xp, _cap_txt = caption_text_arg(cfg.scroll_text)
    base = (f"drawtext=fontfile={caption_font_file(cfg.caption_font)}:{_cap_xp}text='{_cap_txt}':"
            f"fontcolor={caption_color(cfg.caption_color)}:"
''', "branding: the caption is drawn with them")

o = rep(o, '''    "caption_scale": 0.016,      # caption font size (fraction of height) — small, Wondershare-style
''', '''    "caption_scale": 0.016,      # caption font size (fraction of height) — small, Wondershare-style
    "caption_font": "",          # an id of branding.CAPTION_FONTS ("" = the classic font)
    "caption_color": "white",    # a name of branding.CAPTION_COLORS
''', "bot: the two settings")

o = rep(o, '''        "caption_scale": c.get("caption_scale", 0.016),
        "logo_start": c.get("logo_start_min", 0.0) * 60,
''', '''        "caption_scale": c.get("caption_scale", 0.016),
        # only when chosen: with the classic font in white the settings are the ones of before, key for key
        **({"caption_font": c["caption_font"]} if c.get("caption_font") else {}),
        **({"caption_color": c["caption_color"]} if c.get("caption_color", "white") not in ("", "white") else {}),
        "logo_start": c.get("logo_start_min", 0.0) * 60,
''', "bot: the dub-sync engine gets them")

o = rep(o, '''                caption_scale=c.get("caption_scale", 0.016),
                logo_start=_ls,
''', '''                caption_scale=c.get("caption_scale", 0.016),
                caption_font=c.get("caption_font", ""),
                caption_color=c.get("caption_color", "white"),
                logo_start=_ls,
''', "bot: the banner render gets them")

B.write_text(b)
O.write_text(o)
print("patched %s" % D)
