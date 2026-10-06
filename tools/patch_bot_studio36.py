"""bot36: THE STUDIO -- the caption AS TYPED, more fonts, and the waiting video's OWN PICTURES in the preview.

John 2026-10-06 (two screenshots of the Studio): "I want the caption to appear the way I type, the way I give
space, my art ... [U GAAR AH on top, RASHKA BOY MUSALSAL TV under it] ... I need so good fonts, attractive, modern
... I want to see the actual video, just like a timeline: when you drop the video you can easily see where the
logo will be."

What was wrong: the page and the bot both squeezed the caption onto one line (every line break and run of spaces
became one space); the render itself draws line breaks and leading spaces correctly (measured in the bot's own
ffmpeg: lines left-aligned in a block, the block centred, the line pitch = the font's own line height). And the
Studio never got pictures of the video that waits in the panel.

  branding.py  CAPTION_FONTS: 12 more fonts (Debian's own packages: League Spartan, Sora, Manrope, Inter, Montserrat
               Black, Cabin, Yanone Kaffeesatz, Roboto Slab, Quicksand, Comfortaa, Lobster, Dancing Script).
               caption_lines(text): a caption as typed -- line breaks and spaces kept; only what cannot be seen
               goes (spaces at a line's end, empty first / last lines, the indent all lines share), at most 6
               lines, 300 characters. caption_line_height(font id): the line pitch the render uses.
               caption_text_arg: spaces at the very START of a caption get a backslash before the first one
               (ffmpeg drops white space at the start of an option's value: the first line of John's caption
               stood 59 px too far left in the real render). A text that does not start with a space gives the
               text of before, character for character -- and build_filter is not touched.
  bot.py       _cap_clean stores caption_lines(text) (was: one line); /text keeps the lines too; the panels show a
               caption on one line (" ⏎ " for a line break); the Studio's cfg.json gives every font its line
               pitch and, when a video waits in the banner flow, frames.json: one picture from the middle of
               each of 24 equal parts of that video (the first at once, the rest in the background), the first
               also as the preview's frame. In the dub-sync set: the HD film of the job that runs (or of the
               latest one still on the server); for a pair that only waits, the HD film's Telegram thumbnail.
               bot36b: a set that has no video of its own shows the other set's (after a restart everybody
               works in the banner set, and the Studio came up empty although the last film was on the server).
               The picture sent after a save draws the caption with its lines.
Usage: python patch_bot_studio36.py <bot dir>     (patches <bot dir>/bot.py and branding.py in place)"""
import sys
from pathlib import Path

D = Path(sys.argv[1])
PB, PR = D / "bot.py", D / "branding.py"
b, r = PB.read_text(), PR.read_text()
for need in ("_studio_apply", "_cap_clean", "_place_open", "_studio_waiting_dur"):
    assert need in b, "bot.py lacks %s -- apply bot29 .. bot31 first" % need
assert "CAPTION_FONTS" in r and "caption_text_arg" in r, "branding.py lacks the caption fonts of bot31"


def rep(src, old, new, what, has):
    if has in src:
        print("has " + what)
        return src
    n = src.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    print("ok  " + what)
    return src.replace(old, new)


# ------------------------------------------------------------------------------------------------ branding.py
r = rep(r, '''    "serif": ("Serif", "DejaVuSerif-Bold.ttf"),
}
''', '''    "serif": ("Serif", "DejaVuSerif-Bold.ttf"),
    # bot36 (John 2026-10-06: "so good fonts, attractive, modern"): again Debian's own font packages, unchanged
    "spartan": ("Spartan", "LeagueSpartan-Bold.otf"),
    "sora": ("Sora", "Sora-ExtraBold.otf"),
    "manrope": ("Manrope", "Manrope-ExtraBold.ttf"),
    "inter": ("Inter", "InterDisplay-Black.otf"),
    "black": ("Montserrat Black", "Montserrat-Black.otf"),
    "cabin": ("Cabin", "Cabin-Bold.otf"),
    "kaffeesatz": ("Kaffeesatz", "YanoneKaffeesatz-Bold.otf"),
    "slab": ("Slab", "RobotoSlab-Bold.otf"),
    "quicksand": ("Quicksand", "Quicksand-Bold.ttf"),
    "comfortaa": ("Comfortaa", "Comfortaa-Bold.ttf"),
    "lobster": ("Lobster", "lobster.otf"),
    "dancing": ("Dancing", "DancingScript-Bold.otf"),
}
''', "branding: 12 more caption fonts", '"spartan": ("Spartan"')

r = rep(r, '''def caption_text_arg(text) -> tuple:
''', '''# bot36 (John 2026-10-06: "the way I type, the way I give space, my art"): a caption keeps its line breaks and its
# spaces. drawtext draws them as they are -- the lines left-aligned in a block, the block centred by
# x=(w-text_w)/2, the next line one font line height lower (measured on all 20 fonts in the bot's ffmpeg).
CAPTION_MAX_LEN, CAPTION_MAX_LINES = 300, 6


def caption_lines(text) -> str:
    """A caption AS TYPED. Kept: every line break, every space inside a line and before it. Changed only what
    cannot be seen or drawn: Windows line ends, a tab (4 spaces), control characters, spaces at the END of a line
    (they would push the block off centre), empty lines at the start and the end, the indent ALL lines share (in
    a centred block only the difference between the lines shows); cut to CAPTION_MAX_LINES lines and
    CAPTION_MAX_LEN characters. A text on one line with single spaces comes back as it is. Never raises."""
    try:
        t = str(text or "").replace("\\r\\n", "\\n").replace("\\r", "\\n").replace("\\t", "    ")
        t = "".join(ch for ch in t if ch == "\\n" or (ord(ch) >= 32 and ord(ch) != 127))
        ls = [ln.rstrip() for ln in t.split("\\n")]
        while ls and not ls[0]:
            ls.pop(0)
        while ls and not ls[-1]:
            ls.pop()
        ls = ls[:CAPTION_MAX_LINES]
        while ls and not ls[-1]:
            ls.pop()
        ind = min((len(ln) - len(ln.lstrip(" ")) for ln in ls if ln), default=0)
        if ind > 0:
            ls = [ln[ind:] if ln else "" for ln in ls]
        out = "\\n".join(ls)
        if len(out) > CAPTION_MAX_LEN:
            out = out[:CAPTION_MAX_LEN].rstrip()
        return out
    except Exception:
        return ""


_LINE_H: dict = {}


def caption_line_height(font_id) -> float:
    """From one line of a caption to the next, as a share of the letter size, for a font of CAPTION_FONTS: the
    font's own line height, which is what drawtext uses (the Studio's preview spaces its lines by it). 1.17 when
    the font cannot be read."""
    k = str(font_id or "")
    if k not in _LINE_H:
        v = 1.17
        try:
            from PIL import ImageFont
            f = ImageFont.truetype(caption_font_file(font_id), 200)
            h = f.font.height / 200.0
            if 0.5 <= h <= 2.5:
                v = round(h, 4)
        except Exception:
            pass
        _LINE_H[k] = v
    return _LINE_H[k]


def caption_text_arg(text) -> tuple:
''', "branding: caption_lines + caption_line_height", "def caption_lines(")

# spaces at the very start of a caption: ffmpeg drops white space at the start of an option's value
r = rep(r, r'''    t = str(text or "")
    if "%" in t or "\\" in t:
        return "expansion=none:", t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
    return "", _esc_text(t)
''', r'''    t = str(text or "")
    if "%" in t or "\\" in t:
        return "expansion=none:", _lead_space(t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019"))
    return "", _lead_space(_esc_text(t))


def _lead_space(esc: str) -> str:
    """bot36: a caption whose FIRST line starts with spaces (typed that way to move it right). ffmpeg drops white
    space at the start of an option's value -- the first line stood 59 px too far left in the real render, the
    spaces of the later lines were drawn. A backslash before the first space keeps them all. A text that does not
    start with a space comes back as it is: every caption of before."""
    return ("\\" + esc) if esc[:1] == " " else esc
''', "branding: spaces at the start of a caption are kept", "def _lead_space(")

# ------------------------------------------------------------------------------------------------ bot.py
# the panels show a caption on one line
b = rep(b, '''        f"📝 Caption: `{c['scroll_text']}`\\n"
''', '''        f"📝 Caption: `{_cap_flat(c['scroll_text'])}`\\n"
''', "bot: the render panel shows the caption on one line", "Caption: `{_cap_flat(c['scroll_text'])}`")
b = rep(b, '''            f"📝 `{c['scroll_text']}`\\n\\n"
''', '''            f"📝 `{_cap_flat(c['scroll_text'])}`\\n\\n"
''', "bot: the batch panel shows the caption on one line", "📝 `{_cap_flat(c['scroll_text'])}`")

# /text keeps the lines
b = rep(b, '''    new = m.text.split(None, 1)[1].strip()
    if new.lower() in ("off", "none", "clear", "no", "remove", "-"):
        set_user(m.from_user.id, scroll_text="")
        return await m.reply("✅ Caption removed — no scrolling text on your renders.\\n"
                             "Set one again with /text <your text>.")
    set_user(m.from_user.id, scroll_text=new)
    await m.reply(f"✅ Caption set:\\n`{new}`")
''', '''    from branding import caption_lines as _cl
    new = _cl(m.text.split(None, 1)[1])                # bot36: its line breaks and spaces stay as typed
    if new.lower() in ("off", "none", "clear", "no", "remove", "-"):
        set_user(m.from_user.id, scroll_text="")
        return await m.reply("✅ Caption removed — no scrolling text on your renders.\\n"
                             "Set one again with /text <your text>.")
    set_user(m.from_user.id, scroll_text=new)
    if "\\n" in new:
        return await m.reply("✅ Caption set, as you typed it:\\n```\\n%s\\n```" % new)
    await m.reply(f"✅ Caption set:\\n`{new}`")
''', "bot: /text keeps the lines", "bot36: its line breaks and spaces stay as typed")

# the Studio's cleaning stores the caption as typed
b = rep(b, '''    """The caption part of a Studio save -> settings. A font ID and a colour NAME from branding's lists (anything
    else: the classic font, white), the text on one line and cut, numbers clamped, at most STUDIO_MAX_TIMES
    times. {} when nothing usable was sent. Never raises."""
    out = {}
    try:
        from branding import CAPTION_FONTS, CAPTION_COLORS
        if not isinstance(d, dict):
            return {}
        if "text" in d:
            out["scroll_text"] = " ".join(str(d.get("text") or "").split())[:STUDIO_TEXT_MAX]
''', '''    """The caption part of a Studio save -> settings. A font ID and a colour NAME from branding's lists (anything
    else: the classic font, white), the text AS TYPED (bot36: its line breaks and spaces kept, branding.caption_lines)
    and cut, numbers clamped, at most STUDIO_MAX_TIMES times. {} when nothing usable was sent. Never raises."""
    out = {}
    try:
        from branding import CAPTION_FONTS, CAPTION_COLORS, caption_lines
        if not isinstance(d, dict):
            return {}
        if "text" in d:
            out["scroll_text"] = caption_lines(d.get("text"))
''', "bot: _cap_clean stores the caption as typed", 'out["scroll_text"] = caption_lines(d.get("text"))')

b = rep(b, '''def _cap_line(c: dict) -> str:
    """One plain line saying what the caption of a set is."""
    try:
        from branding import CAPTION_FONTS
        txt = (c.get("scroll_text") or "").strip()
''', '''def _cap_flat(t) -> str:
    """A caption on ONE line, for a panel or an answer: a line break shown as " ⏎ ", a run of spaces as one."""
    try:
        return " ⏎ ".join(" ".join(ln.split()) for ln in str(t or "").split("\\n") if ln.strip())
    except Exception:
        return ""


def _cap_line(c: dict) -> str:
    """One plain line saying what the caption of a set is."""
    try:
        from branding import CAPTION_FONTS
        txt = _cap_flat(c.get("scroll_text"))
''', "bot: _cap_flat", "def _cap_flat(")

# cfg.json: every font's line pitch, the film strip's list
b = rep(b, '''def _studio_cfg(uid: int, token: str, has_bg: bool, dur: float = 0.0) -> dict:
    """Everything the Studio page needs, written to WEB_PUBLIC/t/<token>/cfg.json: both sets, the font and
    colour lists, the set the user is working in, the frame, the length of the waiting video."""
    from branding import CAPTION_FONTS, CAPTION_COLORS
    cfg = {"v": 3, "active": _profile_of(uid), "bg": ("t/%s/frame.jpg" % token) if has_bg else "",
           "dur": float(dur or 0.0),
           "fonts": [{"id": "" if k == "classic" else k, "label": lab, "file": "fonts/" + (fn or "DejaVuSans-Bold.ttf")}
                     for k, (lab, fn) in CAPTION_FONTS.items()],
''', '''def _studio_cfg(uid: int, token: str, has_bg: bool, dur: float = 0.0, frames: bool = False) -> dict:
    """Everything the Studio page needs, written to WEB_PUBLIC/t/<token>/cfg.json: both sets, the font and
    colour lists (bot36: each font with its line pitch), the set the user is working in, the frame, the length of
    the waiting video and (bot36) where the list of that video's own pictures is."""
    from branding import CAPTION_FONTS, CAPTION_COLORS, caption_line_height
    cfg = {"v": 3, "active": _profile_of(uid), "bg": ("t/%s/frame.jpg" % token) if has_bg else "",
           "dur": float(dur or 0.0),
           "frames": ("t/%s/frames.json" % token) if frames else "",
           "fonts": [{"id": "" if k == "classic" else k, "label": lab, "file": "fonts/" + (fn or "DejaVuSans-Bold.ttf"),
                      "lh": caption_line_height(k)}
                     for k, (lab, fn) in CAPTION_FONTS.items()],
''', "bot: cfg.json with line pitches and the film strip", '"frames": ("t/%s/frames.json" % token) if frames else ""')

# the waiting video's own pictures
b = rep(b, '''async def _place_open(m: Message, uid: int, src: Message | None = None) -> None:
''', '''# ---- bot36: THE WAITING VIDEO'S OWN PICTURES in the Studio (John 2026-10-06: "I want to see the actual video,
# just like a timeline ... easily see where the logo will be"). A banner job's video is on disk as soon as its
# panel shows: one picture from the middle of each of STUDIO_FRAMES equal parts of it goes into the opening's
# folder, listed in frames.json as they come; the page shows them as a film strip and behind the logo.
STUDIO_FRAMES = 24
STUDIO_FRAME_W = 640            # px wide: about 40 KB a picture
_studio_tasks: dict = {}        # uid -> the task that is filling his film strip


def _studio_frame_times(dur: float, n: int = STUDIO_FRAMES) -> list:
    """The middle of each of n equal parts of a video of dur seconds."""
    try:
        return [round(float(dur) * (i + 0.5) / n, 2) for i in range(n)] if float(dur) > 0 else []
    except Exception:
        return []


def _studio_dub_video(uid: int) -> tuple:
    """(file, seconds) of the HD film of the user's dub-sync job -- the one that runs now, else his latest one whose
    HD is still on the server (the engine keeps a film's sources for about a day) -- or ("", 0.0).
    John 2026-10-06 02:38: he opened the Studio on "Dub-sync films" while a film was running and the picture was
    empty. The film is found by its title's slug (raw/<slug>_hd_ORIG.*), else by the time its job ran (the queue
    keeps only the first 60 letters of a title, and the slug's last part is made from the whole name)."""
    try:
        import glob as _glob
        import dub_queue as _dq
        import dubsync_job as _dj
        hds = [p for p in _glob.glob(os.path.join(str(_dj.RAW_DIR), "*_hd_ORIG.*"))
               if ".det." not in os.path.basename(p) and os.path.isfile(p)]
        if not hds:
            return "", 0.0
        mine = [e for e in list(getattr(_dq, "_q", None) or []) if str(e.get("uid")) == str(uid) and e.get("title")]
        mine.sort(key=lambda e: (e.get("state") == "running", float(e.get("started") or e.get("added") or 0.0)), reverse=True)
        now = time.time()
        for e in mine[:6]:
            slug = _dj._slug(str(e["title"]))
            pick = [p for p in hds if os.path.basename(p).startswith(slug + "_hd_ORIG.")]
            t0 = float(e.get("started") or 0.0)
            if not pick and t0 > 0:
                t1 = float(e.get("ended") or now)
                pick = [p for p in hds if t0 - 5 <= os.path.getmtime(p) <= t1 + 5]
            for p in sorted(pick, key=os.path.getmtime, reverse=True):
                dur = float(probe(p)[2] or 0.0)
                if dur > 1.0:
                    return p, dur
    except Exception:
        pass
    return "", 0.0


def _studio_waiting_video(uid: int) -> tuple:
    """(file, seconds) of the video whose own pictures the Studio shows, or ("", 0.0). Working in the BANNER set:
    the video that waits in the panel (downloaded already). Working in the DUB-SYNC set: the HD film of the job
    that runs, or of the latest one still on the server (_studio_dub_video)."""
    try:
        if _profile_of(uid) == "dub":
            return _studio_dub_video(uid)
        job = _pending.get(uid) or {}
        src, dur = str(job.get("src") or ""), float(job.get("duration") or 0.0)
        if src and dur > 1.0 and os.path.isfile(src):
            return src, dur
    except Exception:
        pass
    return "", 0.0


def _studio_waiting_msg(uid: int):
    """The HD film's message of a dub-sync pair that waits (its Telegram thumbnail becomes the Studio's picture:
    the film itself is not downloaded yet); None otherwise."""
    try:
        if _profile_of(uid) == "dub":
            sel = _dubsel.get(uid) or {}
            msgs = sel.get("msgs") or []
            if len(msgs) == 2:
                return msgs[sel.get("hd_i", 0)]
    except Exception:
        pass
    return None


async def _studio_grab(src: str, t: float, out: str, timeout: float = 25.0) -> bool:
    """One picture of the video at second t: a JPEG STUDIO_FRAME_W wide in the picture's true shape. ffmpeg jumps
    to the key frame before t, so it is quick on a long film. Best effort: False on any failure; never raises
    (a cancel goes through), never leaves ffmpeg running."""
    pr = None
    try:
        pr = await asyncio.create_subprocess_exec(
            "ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % max(0.0, float(t)), "-i", src, "-map", "0:v:0", "-frames:v", "1",
            "-vf", "scale=iw*sar:ih,scale=%d:-2,setsar=1" % STUDIO_FRAME_W, "-q:v", "6", out,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(pr.wait(), timeout=timeout)
        return pr.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 400
    except asyncio.CancelledError:
        raise
    except Exception:
        return False
    finally:
        try:
            if pr is not None and pr.returncode is None:
                pr.kill()
        except Exception:
            pass


def _studio_frames_write(d: str, token: str, dur: float, got: dict, done: bool) -> None:
    """frames.json of an opening: the pictures there are so far (written whole, then moved into place)."""
    tmp = os.path.join(d, "frames.json.tmp")
    with open(tmp, "w") as f:
        json.dump({"v": 1, "dur": float(dur), "n": STUDIO_FRAMES, "done": bool(done),
                   "frames": [{"i": i, "t": got[i], "img": "t/%s/f_%02d.jpg" % (token, i)} for i in sorted(got)]}, f)
    os.replace(tmp, os.path.join(d, "frames.json"))


async def _studio_frames_fill(src: str, dur: float, d: str, token: str, got: dict) -> None:
    """The rest of the film strip, in the background: spread first (every 4th part, then the gaps), the list
    rewritten after each picture so the open page shows them as they come. Stops when the folder is gone."""
    try:
        times = _studio_frame_times(dur)
        n = len(times)
        for i in list(range(0, n, 4)) + list(range(2, n, 4)) + list(range(1, n, 2)):
            if i in got:
                continue
            if not os.path.isdir(d):
                return
            if await _studio_grab(src, times[i], os.path.join(d, "f_%02d.jpg" % i)):
                got[i] = times[i]
                _studio_frames_write(d, token, dur, got, False)
        if os.path.isdir(d):
            _studio_frames_write(d, token, dur, got, True)
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("studio: the film strip could not be finished")


async def _studio_frames_start(uid: int, src: str, dur: float, d: str, token: str) -> bool:
    """The first picture now (it is also the preview's frame), the others in the background. False: no picture
    could be cut from the video -- the Studio opens as before."""
    try:
        times = _studio_frame_times(dur)
        if not times:
            return False
        i0 = len(times) // 8
        first = os.path.join(d, "f_%02d.jpg" % i0)
        if not await _studio_grab(src, times[i0], first):
            return False
        shutil.copyfile(first, os.path.join(d, "frame.jpg"))
        got = {i0: times[i0]}
        _studio_frames_write(d, token, dur, got, False)
        old = _studio_tasks.pop(uid, None)
        if old is not None and not old.done():
            old.cancel()
        _studio_tasks[uid] = asyncio.create_task(_studio_frames_fill(src, dur, d, token, got))
        return True
    except Exception:
        log.exception("studio: the video's pictures could not be started")
        return False


async def _place_open(m: Message, uid: int, src: Message | None = None) -> None:
''', "bot: the waiting video's own pictures", "def _studio_frames_start(")

b = rep(b, '''def _studio_waiting_video(uid: int) -> tuple:
    """(file, seconds) of the video whose own pictures the Studio shows, or ("", 0.0). Working in the BANNER set:
    the video that waits in the panel (downloaded already). Working in the DUB-SYNC set: the HD film of the job
    that runs, or of the latest one still on the server (_studio_dub_video)."""
    try:
        if _profile_of(uid) == "dub":
            return _studio_dub_video(uid)
        job = _pending.get(uid) or {}
        src, dur = str(job.get("src") or ""), float(job.get("duration") or 0.0)
        if src and dur > 1.0 and os.path.isfile(src):
            return src, dur
    except Exception:
        pass
    return "", 0.0
''', '''def _studio_waiting_video(uid: int) -> tuple:
    """(file, seconds) of the video whose own pictures the Studio shows, or ("", 0.0). The set the user works in
    comes first -- BANNER: the video that waits in the panel (downloaded already); DUB-SYNC: the HD film of the job
    that runs, or of the latest one still on the server (_studio_dub_video) -- and when that set has no video, the
    OTHER set's is shown (bot36b: after a restart everybody works in the banner set again, and the Studio came up
    empty although his last film was on the server; a real picture of his is better than none)."""
    def _banner(_uid):
        job = _pending.get(_uid) or {}
        src, dur = str(job.get("src") or ""), float(job.get("duration") or 0.0)
        return (src, dur) if (src and dur > 1.0 and os.path.isfile(src)) else ("", 0.0)
    order = (_studio_dub_video, _banner) if _profile_of(uid) == "dub" else (_banner, _studio_dub_video)
    for f in order:
        try:
            got = f(uid)
            if got and got[0]:
                return got
        except Exception:
            pass
    return "", 0.0
''', "bot36b: the Studio falls back to the other set's video", "def _banner(_uid):")

b = rep(b, '''    has_bg = False
    try:
        if src is not None and src.photo:
            await src.download(file_name=os.path.join(d, "frame.jpg"))
''', '''    has_bg = False
    if src is None:
        src = _studio_waiting_msg(uid)                 # bot36: a waiting dub-sync pair -> the HD film's thumbnail
    try:
        if src is not None and src.photo:
            await src.download(file_name=os.path.join(d, "frame.jpg"))
''', "bot: a waiting dub-sync pair gives its thumbnail", "src = _studio_waiting_msg(uid)")

b = rep(b, '''    has_bg = has_bg and os.path.exists(os.path.join(d, "frame.jpg"))
    cfg = _studio_cfg(uid, token, has_bg, _studio_waiting_dur(uid))
''', '''    has_bg = has_bg and os.path.exists(os.path.join(d, "frame.jpg"))
    frames = False
    if not has_bg:                                     # bot36: the video that waits in the panel -> its own pictures
        vsrc, vdur = await asyncio.to_thread(_studio_waiting_video, uid)
        if vsrc:
            frames = has_bg = await _studio_frames_start(uid, vsrc, vdur, d, token)
    cfg = _studio_cfg(uid, token, has_bg, _studio_waiting_dur(uid), frames)
''', "bot: the Studio opens with the waiting video's pictures", "frames = has_bg = await _studio_frames_start(")

# the picture after a save draws the caption with its lines
b = rep(b, '''        from branding import build_filter, caption_font_file, caption_color, _esc_text
        pay = _brand_payload(uid, profile)
        logos = [Logo(**lg) for lg in pay["logos"] if os.path.exists(lg["path"])]
        txt = (pay.get("scroll_text") or "").strip()
''', '''        from branding import build_filter, caption_font_file, caption_color, _esc_text, caption_text_arg, caption_lines
        pay = _brand_payload(uid, profile)
        logos = [Logo(**lg) for lg in pay["logos"] if os.path.exists(lg["path"])]
        txt = caption_lines(pay.get("scroll_text"))    # bot36: as typed (a strip() took the first line's own spaces)
''', "bot: the preview picture keeps the caption's lines", 'txt = caption_lines(pay.get("scroll_text"))')
b = rep(b, '''            fc += (";[outv]drawtext=fontfile=%s:text='%s':fontcolor=%s:fontsize=%d:borderw=2:bordercolor=black@0.9:"
                   "x=(w-text_w)/2:y=h*0.86-text_h/2[pv]" % (caption_font_file(pay.get("caption_font", "")), _esc_text(txt),
                                                              caption_color(pay.get("caption_color", "white")), fs))
''', '''            _xp, _tx = caption_text_arg(txt)           # the render's own escaping: lines, spaces, a % letter for letter
            fc += (";[outv]drawtext=fontfile=%s:%stext='%s':fontcolor=%s:fontsize=%d:borderw=2:bordercolor=black@0.9:"
                   "x=(w-text_w)/2:y='min(h*0.86-text_h/2,h-text_h-6)'[pv]" % (caption_font_file(pay.get("caption_font", "")), _xp, _tx,
                                                                              caption_color(pay.get("caption_color", "white")), fs))
''', "bot: the preview picture draws the caption as the render does", "_xp, _tx = caption_text_arg(txt)           # the render's own escaping")

PB.write_text(b)
PR.write_text(r)
print("patched %s" % D)
