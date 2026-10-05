"""bot31 (part 2): THE STUDIO -- logo, caption (text, font, colour, size, speed), timeline (logo start, caption
times), trim -- for BOTH sets of settings (banner jobs / dub-sync films), each on its own.

John 2026-10-05: "not only the logo, I also want caption in there ... different fonts, more like studio, timeline
... the cut trim, caption, everything ... banner and dub sync totally different, independent".

Needs bot30 (two sets: user_cfg(uid, profile), set_user(uid, _profile=...)) and bot31 part 1 (caption font /
colour). Replaces the whole bot29 block of bot.py (the logo page's functions) with the Studio's:
  open      /studio (also /logopos, /place ...; the button in Settings -> Logos): a fresh unguessable folder
            WEB_PUBLIC/t/<token> gets the user's logo images and cfg.json -- BOTH sets (logos, logo start,
            caption, trim), the font and colour lists, the set the user is working in, the length of the video
            that is waiting (for the timeline) -- and a keyboard button opens place.html?t=<token>. The page
            reads the file; nothing personal is in the link.
  save      the page answers through Telegram (web_app_data) with ONLY what changed, per set:
            {"k": "studio", "v": 3, "sets": {"banner": {...}, "dub": {...}}}. Everything is cleaned before it is
            stored: known logo names, clamped numbers, a font ID and a colour NAME from the lists (never a path,
            never free text into a filter), caption text cut to 200 characters on one line, at most 40 caption
            times, trim only for banner jobs and only when it makes sense. Each set is written with
            set_user(_profile=...): a change of one never reaches the other.
  answer    what was saved, per set, in plain lines + a preview picture made by the real render filter.
The older answers ("logo_place" v1 / v2) and /logoset keep working (they change the set the user is working in).
Usage: python patch_bot_studio31.py <bot dir>     (patches <bot dir>/bot.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "bot.py"
s = P.read_text()
if "_studio_apply" in s:
    sys.exit("already patched: %s" % P)
for need in ("_ui_profile", "caption_font", "_place_open"):
    assert need in s, "bot.py lacks %s -- apply bot29, bot30 and bot31 part 1 first" % need

A = s.index("# ---- bot29: THE LOGO ANYWHERE")
B = s.index("# ---- crash/restart-safe batch journal + /resume")
assert 0 < A < B

NEW = r'''# ---- THE STUDIO (bot29: the logo anywhere; bot31: caption, fonts, timeline, trim, two sets of settings) ---------
# A logo is stored as corner + margins + width share; a free place is corner TL with margin_x = left and
# margin_y = top (shares of the picture). web_public/place.html (static, HTTPS through Caddy) is the Studio: it
# reads t/<token>/cfg.json (both sets of settings) and hands back ONLY what changed through Telegram
# (web_app_data). Everything that comes back is cleaned here before it is stored.
WEB_PUBLIC = os.environ.get("BIDHAAN_WEB_PUBLIC", "/opt/dubsync2/web_logo")   # writable from the bot container
WEB_BASE = os.environ.get("BIDHAAN_WEB_BASE", "https://159-195-136-50.sslip.io/logo")
PLACE_LOGOS = (("bidhaan2", "Bidhaan L"), ("bidhaan", "Bidhaan R"), ("streamnxt", "StreamNxt"))
PLACE_MIN_W, PLACE_MAX_W = 0.03, 0.70
PLACE_MAX_START_S = 3 * 3600
PLACE_KEEP_S = 2 * 3600
STUDIO_MAX_TIMES = 40
STUDIO_MAX_T = 6 * 3600.0
STUDIO_TEXT_MAX = 200


def _place_file(c: dict, name: str) -> str:
    return _asset(settings.logo_tr) if name == "streamnxt" else _user_logo(c)


def _place_clean(items) -> list:
    """[(name, left, top, width, on)] from what the page or /logoset sent: known names once each, numbers as
    shares of the picture, clamped so the logo starts inside it; `on` (default True) = the logo's switch.
    Anything else is dropped. Never raises."""
    out, seen = [], set()
    names = {n for n, _ in PLACE_LOGOS}
    try:
        for it in (items or [])[:8]:
            try:
                n = str(it.get("n"))
                x, y, w = float(it.get("x")), float(it.get("y")), float(it.get("w"))
            except Exception:
                continue
            if n not in names or n in seen or not all(v == v and abs(v) < 1e6 for v in (x, y, w)):
                continue
            w = min(PLACE_MAX_W, max(PLACE_MIN_W, w))
            x = min(1.0 - w, max(0.0, x))
            y = min(0.98, max(0.0, y))
            seen.add(n)
            out.append((n, round(x, 4), round(y, 4), round(w, 4), it.get("on") is not False))
    except Exception:
        return []
    return out


def _place_start(v):
    """The second the logo appears (0 .. PLACE_MAX_START_S), or None when nothing usable was sent."""
    try:
        t = float(v)
        if t != t or abs(t) > 1e9:
            return None
        return float(min(PLACE_MAX_START_S, max(0.0, round(t))))
    except Exception:
        return None


def _place_apply(uid: int, items: list, start=None, profile=None) -> list:
    """Store the places (corner TL + margins + size, the logo's switch) and, when given, the second the logo
    appears -- in the given set of settings (None: the one the user is working in). One plain line per thing."""
    c = user_cfg(uid, profile)
    sc = float(c.get("logo_scale") or 1.0) or 1.0
    label = dict(PLACE_LOGOS)
    kw, lines = {}, []
    for n, x, y, w, on in items:
        if not on:
            if c.get(n + "_on"):                      # switched off now: only its switch, its place is kept
                kw[n + "_on"] = False
                lines.append("• %s: switched off" % label.get(n, n))
            continue                                  # was off and stays off: not touched at all
        kw.update({n + "_on": True, n + "_corner": "TL", n + "_mx": x, n + "_my": y, n + "_frac": round(w / sc, 5)})
        lines.append("• %s: left %.1f %%, top %.1f %%, size %.1f %% of the picture's width"
                     % (label.get(n, n), x * 100, y * 100, w * 100))
    if start is not None:
        kw["logo_start_min"] = start / 60.0
        lines.append("• The logo appears from %s" % _fmt_time(start / 60.0))
    if kw:
        set_user(uid, _profile=profile, **kw)
    return lines


def _cap_clean(d) -> dict:
    """The caption part of a Studio save -> settings. A font ID and a colour NAME from branding's lists (anything
    else: the classic font, white), the text on one line and cut, numbers clamped, at most STUDIO_MAX_TIMES
    times. {} when nothing usable was sent. Never raises."""
    out = {}
    try:
        from branding import CAPTION_FONTS, CAPTION_COLORS
        if not isinstance(d, dict):
            return {}
        if "text" in d:
            out["scroll_text"] = " ".join(str(d.get("text") or "").split())[:STUDIO_TEXT_MAX]
        if "font" in d:
            f = str(d.get("font") or "").strip().lower()
            out["caption_font"] = f if (f in CAPTION_FONTS and f != "classic") else ""
        if "color" in d:
            col = str(d.get("color") or "").strip().lower()
            out["caption_color"] = col if col in CAPTION_COLORS else "white"
        if "size" in d:
            v = float(d.get("size"))
            if v == v:
                out["caption_scale"] = round(min(0.06, max(0.008, v)), 4)
        if "seconds" in d:
            v = float(d.get("seconds"))
            if v == v:
                out["scroll_seconds"] = float(min(120.0, max(5.0, round(v))))
        if "times" in d:
            ts = set()
            for t in list(d.get("times") or [])[:200]:
                try:
                    t = float(t)
                except Exception:
                    continue
                if t == t and 0.0 <= t <= STUDIO_MAX_T:
                    ts.add(round(t))
            out["scroll_times"] = [round(t / 60.0, 4) for t in sorted(ts)[:STUDIO_MAX_TIMES]]     # stored in minutes
        if "count" in d:
            v = float(d.get("count"))
            if v == v:
                out["scroll_count"] = int(min(40, max(0, round(v))))
    except Exception:
        return {}
    return out


def _trim_clean(d) -> dict:
    """The trim part of a Studio save -> settings; {} when it makes no sense (a part that ends before it starts)."""
    try:
        if not isinstance(d, dict):
            return {}
        mode = str(d.get("mode") or "")
        if mode not in ("off", "head", "tail", "range", "cut"):
            return {}
        a = min(STUDIO_MAX_T, max(0.0, float(d.get("a") or 0.0)))
        b = min(STUDIO_MAX_T, max(0.0, float(d.get("b") or 0.0)))
        if a != a or b != b:
            return {}
        if mode == "off":
            return {"trim_mode": "off", "trim_a": 0.0, "trim_b": 0.0}
        if mode in ("head", "tail"):
            return {"trim_mode": mode, "trim_a": a, "trim_b": 0.0} if a > 0 else {"trim_mode": "off", "trim_a": 0.0, "trim_b": 0.0}
        return {"trim_mode": mode, "trim_a": a, "trim_b": b} if b > a else {}
    except Exception:
        return {}


def _cap_line(c: dict) -> str:
    """One plain line saying what the caption of a set is."""
    try:
        from branding import CAPTION_FONTS
        txt = (c.get("scroll_text") or "").strip()
        if not txt:
            return "• Caption: off"
        font = CAPTION_FONTS.get(c.get("caption_font") or "classic", ("Classic", ""))[0]
        ts = [round(float(mn) * 60) for mn in (c.get("scroll_times") or [])]
        when = ("at " + ", ".join(_fmt_hms(t) for t in ts[:6]) + (" … (%d times)" % len(ts) if len(ts) > 6 else "")) if ts \
            else ("%d times spread over the film" % int(c.get("scroll_count") or 0) if c.get("scroll_count") else "all through the film")
        return "• Caption: “%s” · %s · %s · %.1f %% · crosses in %d s · %s" % (
            txt[:60] + ("…" if len(txt) > 60 else ""), font, c.get("caption_color") or "white",
            float(c.get("caption_scale") or 0.016) * 100, int(c.get("scroll_seconds") or 25), when)
    except Exception:
        return "• Caption saved"


def _studio_apply(uid: int, data: dict) -> tuple:
    """Store a Studio save: per set, only the parts that were sent. Returns (plain lines, the first set changed)."""
    lines, first = [], None
    sets = data.get("sets") if isinstance(data.get("sets"), dict) else {}
    for prof in ("banner", "dub"):
        part = sets.get(prof)
        if not isinstance(part, dict):
            continue
        sub = []
        items = _place_clean(part.get("logos")) if "logos" in part else []
        start = _place_start(part.get("start")) if "start" in part else None
        if items or start is not None:
            sub += _place_apply(uid, items, start, profile=prof)
        kw = _cap_clean(part.get("cap")) if "cap" in part else {}
        tr = _trim_clean(part.get("trim")) if (prof == "banner" and "trim" in part) else {}
        kw.update(tr)
        if kw:
            c = set_user(uid, _profile=prof, **kw)
            if any(k.startswith(("scroll_", "caption_")) for k in kw):
                sub.append(_cap_line(c))
            if tr:
                sub.append("• Trim: %s" % _trim_label(c["trim_mode"], c["trim_a"], c["trim_b"]))
        if sub:
            lines.append("**%s**" % PROFILE_LABEL[prof])
            lines += sub
            first = first or prof
    return lines, first


def _studio_set(uid: int, profile: str, token: str) -> dict:
    """One set of settings as the Studio page reads it. Copies the logo images into WEB_PUBLIC/t/<token>."""
    c = user_cfg(uid, profile)
    sc = float(c.get("logo_scale") or 1.0) or 1.0
    d = os.path.join(WEB_PUBLIC, "t", token)
    os.makedirs(d, exist_ok=True)
    logos = []
    for n, label in PLACE_LOGOS:
        src = _place_file(c, n)
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(src)[1].lower() or ".png"
        dst = os.path.join(d, n + ext)
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
        logos.append({"n": n, "label": label, "img": "t/%s/%s%s" % (token, n, ext), "c": c[n + "_corner"],
                      "mx": float(c[n + "_mx"]), "my": float(c[n + "_my"]), "w": float(c[n + "_frac"]) * sc,
                      "on": bool(c.get(n + "_on"))})
    return {"logos": logos,
            "start": int(round(float(c.get("logo_start_min") or 0.0) * 60)),
            "cap": {"text": c.get("scroll_text") or "", "font": c.get("caption_font") or "",
                    "color": c.get("caption_color") or "white", "size": float(c.get("caption_scale") or 0.016),
                    "seconds": float(c.get("scroll_seconds") or 25.0), "count": int(c.get("scroll_count") or 0),
                    "times": [int(round(float(mn) * 60)) for mn in (c.get("scroll_times") or [])]},
            "trim": {"mode": c.get("trim_mode") or "off", "a": float(c.get("trim_a") or 0.0), "b": float(c.get("trim_b") or 0.0)}}


def _studio_cfg(uid: int, token: str, has_bg: bool, dur: float = 0.0) -> dict:
    """Everything the Studio page needs, written to WEB_PUBLIC/t/<token>/cfg.json: both sets, the font and
    colour lists, the set the user is working in, the frame, the length of the waiting video."""
    from branding import CAPTION_FONTS, CAPTION_COLORS
    cfg = {"v": 3, "active": _profile_of(uid), "bg": ("t/%s/frame.jpg" % token) if has_bg else "",
           "dur": float(dur or 0.0),
           "fonts": [{"id": "" if k == "classic" else k, "label": lab, "file": "fonts/" + (fn or "DejaVuSans-Bold.ttf")}
                     for k, (lab, fn) in CAPTION_FONTS.items()],
           "colors": [{"id": k, "css": "#ffffff" if v == "white" else "#" + v[2:]} for k, v in CAPTION_COLORS.items()],
           "sets": {"banner": _studio_set(uid, "banner", token), "dub": _studio_set(uid, "dub", token)}}
    with open(os.path.join(WEB_PUBLIC, "t", token, "cfg.json"), "w") as f:
        json.dump(cfg, f)
    return cfg


def _place_url(token: str) -> str:
    return "%s/place.html?t=%s" % (WEB_BASE.rstrip("/"), token)


def _place_sweep() -> None:
    """Folders of earlier openings older than PLACE_KEEP_S are removed."""
    try:
        root = os.path.join(WEB_PUBLIC, "t")
        for n in os.listdir(root):
            p = os.path.join(root, n)
            if os.path.isdir(p) and time.time() - os.path.getmtime(p) > PLACE_KEEP_S:
                shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


_place_last: dict = {}          # uid -> the folder of the page he has open (its frame is the preview's background)


def _studio_waiting_dur(uid: int) -> float:
    """The length of the video that is waiting in the flow the user is in (for the Studio's timeline); 0 = none."""
    try:
        if _profile_of(uid) == "dub":
            sel = _dubsel.get(uid) or {}
            msgs = sel.get("msgs") or []
            if len(msgs) == 2:
                return float(_vmeta(msgs[sel.get("hd_i", 0)])[3] or 0.0)
            return 0.0
        return float((_pending.get(uid) or {}).get("duration") or 0.0)
    except Exception:
        return 0.0


async def _place_open(m: Message, uid: int, src: Message | None = None) -> None:
    """Send the keyboard button that opens the Studio. `src`: a photo / video whose picture becomes the frame."""
    import secrets
    from pyrogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
    _place_sweep()
    token = secrets.token_urlsafe(12)
    d = os.path.join(WEB_PUBLIC, "t", token)
    os.makedirs(d, exist_ok=True)
    has_bg = False
    try:
        if src is not None and src.photo:
            await src.download(file_name=os.path.join(d, "frame.jpg"))
            has_bg = True
        elif src is not None and (src.video or src.document) and getattr(src.video or src.document, "thumbs", None):
            await app.download_media((src.video or src.document).thumbs[-1].file_id,
                                     file_name=os.path.join(d, "frame.jpg"))
            has_bg = True
    except Exception:
        log.exception("studio: the frame could not be fetched")
    has_bg = has_bg and os.path.exists(os.path.join(d, "frame.jpg"))
    cfg = _studio_cfg(uid, token, has_bg, _studio_waiting_dur(uid))
    if not cfg["sets"]["banner"]["logos"] and not cfg["sets"]["dub"]["logos"]:
        shutil.rmtree(d, ignore_errors=True)
        await m.reply("No logo image was found. Upload yours first: /logo")
        return
    _place_last[uid] = d
    kb = ReplyKeyboardMarkup([[KeyboardButton("🎨 Open Studio", web_app=WebAppInfo(url=_place_url(token)))]],
                             resize_keyboard=True, one_time_keyboard=True)
    await m.reply(
        "🎨 **Studio**\n\n"
        "Tap **Open Studio** below.\n"
        "• **Logo** — drag it anywhere, size it, switch each logo on or off\n"
        "• **Caption** — text, font, colour, size, speed\n"
        "• **Timeline** — when the logo appears, when the caption crosses\n"
        "• **Trim** — cut the start, the end or a part (banner jobs)\n\n"
        "At the top you choose **Banner jobs** or **Dub-sync films**: each keeps its own settings "
        "(it opens on **%s**).\n"
        "_Tip: reply to one of your photos or videos with /studio to see the logo on that picture._"
        % PROFILE_LABEL[_profile_of(uid)],
        reply_markup=kb)


async def _place_preview(m: Message, uid: int, profile=None) -> None:
    """A picture of the result made by the REAL render filter (best effort; never breaks the save)."""
    try:
        import tempfile
        from branding import build_filter, caption_font_file, caption_color, _esc_text
        pay = _brand_payload(uid, profile)
        logos = [Logo(**lg) for lg in pay["logos"] if os.path.exists(lg["path"])]
        txt = (pay.get("scroll_text") or "").strip()
        if not logos and not txt:
            return
        bg = os.path.join(_place_last.get(uid) or "", "frame.jpg")
        W, H = 1280, 720
        if os.path.exists(bg):
            try:
                bw, bh, _ = await asyncio.to_thread(probe, bg)
                if bw > 0 and bh > 0:
                    H = max(2, int(round(1280.0 * bh / bw / 2)) * 2)
            except Exception:
                pass
            src = ["-loop", "1", "-i", bg]
        else:
            src = ["-f", "lavfi", "-i", "color=c=0x33475b:s=%dx%d:r=25" % (W, H)]
        cfg = RenderConfig(logos=logos, cover_png="", scroll_text="", width=W, height=H, logo_start=0.0)
        fc = build_filter(0, 0, 1.0, [], cfg)
        last = "outv"
        if txt:                                        # the caption as it looks, standing near the bottom
            fs = max(14, int(H * float(pay.get("caption_scale") or 0.016)))
            fc += (";[outv]drawtext=fontfile=%s:text='%s':fontcolor=%s:fontsize=%d:borderw=2:bordercolor=black@0.9:"
                   "x=(w-text_w)/2:y=h*0.86-text_h/2[pv]" % (caption_font_file(pay.get("caption_font", "")), _esc_text(txt),
                                                              caption_color(pay.get("caption_color", "white")), fs))
            last = "pv"
        out = os.path.join(tempfile.gettempdir(), "studio_%d.jpg" % uid)
        dummy = logos[0].path if logos else _asset(settings.cover_png)
        cmd = ["ffmpeg", "-v", "error", "-y", *src, "-i", dummy]
        for lg in logos:
            cmd += ["-i", lg.path]
        cmd += ["-filter_complex", fc, "-map", "[%s]" % last, "-frames:v", "1", "-q:v", "4", out]
        pr = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL,
                                                  stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(pr.wait(), timeout=40)
        if pr.returncode == 0 and os.path.exists(out):
            await m.reply_photo(out, caption="This is how it will look (%s)." % PROFILE_LABEL[_profile_of(uid, profile)])
    except Exception:
        log.exception("studio: preview failed")


async def _place_done(m: Message, uid: int, items: list, start=None) -> None:
    from pyrogram.types import ReplyKeyboardRemove
    if not items and start is None:
        await m.reply("Nothing was changed.", reply_markup=ReplyKeyboardRemove())
        return
    lines = _place_apply(uid, items, start)
    await m.reply("✅ **Logo saved** (%s)\n" % PROFILE_LABEL[_profile_of(uid)] + "\n".join(lines)
                  + "\n\nIt applies to your next renders. /studio opens the Studio again.",
                  reply_markup=ReplyKeyboardRemove())
    await _place_preview(m, uid)


@app.on_message(filters.command(["studio", "logopos", "logoplace", "place", "logoanywhere", "logostudio"]) & filters.private)
async def _cmd_logopos(_, m: Message):
    uid = m.from_user.id
    if not _allowed(uid):
        return
    await _place_open(m, uid, m.reply_to_message)


@app.on_message(filters.command("logoset") & filters.private)
async def _cmd_logoset(_, m: Message):
    uid = m.from_user.id
    if not _allowed(uid):
        return
    a = (m.text or "").split()[1:]
    names = [n for n, _ in PLACE_LOGOS]
    c = user_cfg(uid)
    name = a.pop(0) if a and a[0] in names else next((n for n in names if c.get(n + "_on")), names[0])
    try:
        x, y, w = (float(v.rstrip("%")) / 100.0 for v in a[:3])
        if len(a) < 3:
            raise ValueError
    except Exception:
        await m.reply("Use: `/logoset [bidhaan2|bidhaan|streamnxt] <left %> <top %> <size %>`\n"
                      "Example: `/logoset 12 8 15` = left 12 %, top 8 %, size 15 % of the picture's width.")
        return
    await _place_done(m, uid, _place_clean([{"n": name, "x": x, "y": y, "w": w}]))


@app.on_message(filters.private & filters.create(lambda _, __, m: bool(getattr(m, "web_app_data", None))))
async def _on_web_app_data(_, m: Message):
    uid = m.from_user.id if m.from_user else 0
    if not _allowed(uid):
        return
    try:
        data = json.loads(m.web_app_data.data)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    if data.get("k") == "logo_place":                  # the first logo page (v1 / v2)
        await _place_done(m, uid, _place_clean(data.get("logos")),
                          _place_start(data.get("start")) if "start" in data else None)
        return
    if data.get("k") != "studio":
        return
    from pyrogram.types import ReplyKeyboardRemove
    lines, first = _studio_apply(uid, data)
    if not lines:
        await m.reply("Nothing was changed.", reply_markup=ReplyKeyboardRemove())
        return
    await m.reply("✅ **Studio saved**\n" + "\n".join(lines)
                  + "\n\nIt applies to your next renders. /studio opens the Studio again.",
                  reply_markup=ReplyKeyboardRemove())
    await _place_preview(m, uid, first)


'''
s = s[:A] + NEW + s[B:]
old = '''            [IKB("🎨 Logo studio — move, size, time", "lg:place:open")],'''
assert s.count(old) == 1
s = s.replace(old, '''            [IKB("🎨 Studio — logo, caption, timeline, trim", "lg:place:open")],''')
P.write_text(s)
print("ok  the Studio block replaces the logo page's block\nok  the button in Settings -> Logos\npatched %s" % P)
