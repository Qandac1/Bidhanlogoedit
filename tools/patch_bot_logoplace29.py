"""bot29: THE LOGO ANYWHERE -- a page inside Telegram where the logo is dragged to any place on the picture and made
smaller or larger; Save stores it for every next render.

John 2026-10-05: "is there a way, like a browser, that allows me to put my logo any position I want, anywhere -- not
like top left / top right / top center -- also I can make it small, large".

No render code changes: a logo is already stored as a corner + two margins + a width share. A free place is
corner TL with margin_x = left and margin_y = top (shares of the PICTURE), width = size. The menu only offered
corners; the page offers every place.
  /logopos (also /logoplace, /place, /logoanywhere, /studio; button in Settings -> Logos)
      -> a keyboard button that opens web_public/place.html, the "Logo studio" (static, served over HTTPS by
         Caddy at WEB_BASE): every logo drawn on a frame (reply to a photo / video with /logopos to use ITS
         picture as the frame); drag on the picture, quick places, slider / + - for the size, arrows for fine
         steps, a switch per logo, the second the logo appears (John 10-05: "about the logo time ... modern,
         well designed, easy"), Save.
      -> the page hands the numbers back through Telegram (web_app_data); the bot clamps them, stores them, takes
         the keyboard away and answers with the numbers and a preview picture made by the real render filter.
  /logoset [name] <left %> <top %> <size %>   the same without the page (name: bidhaan2 | bidhaan | streamnxt).
Only allowed users; only known logo names; numbers clamped (size 3-70 % of the picture's width, the logo kept
inside the picture). Nothing else in the settings is touched. The page has no secrets; each opening gets its own
unguessable folder (web_public/t/<token>) with the logo images, removed after 2 hours.
Usage: python patch_bot_logoplace29.py <bot dir>     (patches <bot dir>/bot.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "bot.py"
s = P.read_text()
if "_place_open" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''            [IKB(f"Size: {int(c['logo_scale']*100)}%  (tap to change)", "lg:scale:cycle")],
            _back_row(),
''', '''            [IKB(f"Size: {int(c['logo_scale']*100)}%  (tap to change)", "lg:scale:cycle")],
            [IKB("🎨 Logo studio — move, size, time", "lg:place:open")],
            _back_row(),
''', "the button in Settings -> Logos")

rep('''        _, who, act = data.split(":", 2)
        c = user_cfg(uid)
        if act == "toggle":
''', '''        _, who, act = data.split(":", 2)
        c = user_cfg(uid)
        if who == "place" and act == "open":          # bot29: the logo anywhere
            await _place_open(cq.message, uid)
            return await cq.answer("Tap the button below 👇")
        if act == "toggle":
''', "the button's action")

rep('''# ---- crash/restart-safe batch journal + /resume ----------------------------
JOURNAL_FILE = ''', r'''# ---- bot29: THE LOGO ANYWHERE (John 2026-10-05: "put my logo any position I want ... make it small, large") ----
# A logo is stored as corner + margins + width share; a free place is corner TL with margin_x = left and
# margin_y = top (shares of the picture). web_public/place.html (static, HTTPS through Caddy) is the page where
# it is dragged; it hands the numbers back through Telegram (web_app_data). /logoset does the same by hand.
WEB_PUBLIC = os.environ.get("BIDHAAN_WEB_PUBLIC", "/opt/dubsync2/web_logo")   # writable from the bot container
WEB_BASE = os.environ.get("BIDHAAN_WEB_BASE", "https://159-195-136-50.sslip.io/logo")
PLACE_LOGOS = (("bidhaan2", "Bidhaan L"), ("bidhaan", "Bidhaan R"), ("streamnxt", "StreamNxt"))
PLACE_MIN_W, PLACE_MAX_W = 0.03, 0.70
PLACE_MAX_START_S = 3 * 3600
PLACE_KEEP_S = 2 * 3600


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


def _place_apply(uid: int, items: list, start=None) -> list:
    """Store the places (corner TL + margins + size, the logo's switch) and, when given, the second the logo
    appears. One plain line per thing stored."""
    c = user_cfg(uid)
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
        set_user(uid, **kw)
    return lines


def _place_payload(uid: int, token: str, has_bg: bool) -> dict:
    """What the page needs: every logo that has an image (corner, margins, size, its switch), the second the
    logo appears, the frame. Copies the images into WEB_PUBLIC/t/<token>."""
    c = user_cfg(uid)
    sc = float(c.get("logo_scale") or 1.0) or 1.0
    d = os.path.join(WEB_PUBLIC, "t", token)
    os.makedirs(d, exist_ok=True)
    logos = []
    for n, label in PLACE_LOGOS:
        src = _place_file(c, n)
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(src)[1].lower() or ".png"
        shutil.copyfile(src, os.path.join(d, n + ext))
        logos.append({"n": n, "label": label, "img": "t/%s/%s%s" % (token, n, ext), "c": c[n + "_corner"],
                      "mx": float(c[n + "_mx"]), "my": float(c[n + "_my"]), "w": float(c[n + "_frac"]) * sc,
                      "on": bool(c.get(n + "_on"))})
    return {"logos": logos, "bg": ("t/%s/frame.jpg" % token) if has_bg else "", "ar": 16 / 9,
            "start": int(round(float(c.get("logo_start_min") or 0.0) * 60))}


def _place_url(payload: dict) -> str:
    import base64
    b = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return "%s/place.html?d=%s" % (WEB_BASE.rstrip("/"), b)


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


async def _place_open(m: Message, uid: int, src: Message | None = None) -> None:
    """Send the keyboard button that opens the page. `src`: a photo / video whose picture becomes the frame."""
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
        log.exception("logo place: the frame could not be fetched")
    has_bg = has_bg and os.path.exists(os.path.join(d, "frame.jpg"))
    payload = _place_payload(uid, token, has_bg)
    if not payload["logos"]:
        shutil.rmtree(d, ignore_errors=True)
        await m.reply("No logo image was found. Upload yours first: /logo")
        return
    _place_last[uid] = d
    kb = ReplyKeyboardMarkup([[KeyboardButton("🎨 Open Logo studio", web_app=WebAppInfo(url=_place_url(payload)))]],
                             resize_keyboard=True, one_time_keyboard=True)
    await m.reply(
        "🎨 **Logo studio**\n\n"
        "Tap **Open Logo studio** below. Drag on the picture to move the logo, set its size, switch each logo "
        "on or off, choose the second it appears, then **Save**.\n\n"
        "_Tip: reply to one of your photos or videos with /logopos to see the logo on that picture._\n"
        "Without the page: `/logoset 12 8 15` = left 12 %, top 8 %, size 15 %.",
        reply_markup=kb)


async def _place_preview(m: Message, uid: int) -> None:
    """A picture of the result made by the REAL render filter (best effort; never breaks the save)."""
    try:
        import tempfile
        c = user_cfg(uid)
        pay = _brand_payload(uid)
        logos = [Logo(**lg) for lg in pay["logos"] if os.path.exists(lg["path"])]
        if not logos:
            return
        bg = os.path.join(_place_last.get(uid) or "", "frame.jpg")
        W, H = 1280, 720
        if os.path.exists(bg):
            try:
                bw, bh, _ = await asyncio.to_thread(probe, bg)
                if bw > 0 and bh > 0:
                    W = 1280
                    H = max(2, int(round(1280.0 * bh / bw / 2)) * 2)
            except Exception:
                pass
            src = ["-loop", "1", "-i", bg]
        else:
            src = ["-f", "lavfi", "-i", "color=c=0x33475b:s=%dx%d:r=25" % (W, H)]
        cfg = RenderConfig(logos=logos, cover_png=logos[0].path, scroll_text="", width=W, height=H, logo_start=0.0)
        from branding import build_filter
        fc = build_filter(0, 0, 1.0, [], cfg)
        out = os.path.join(tempfile.gettempdir(), "logo_place_%d.jpg" % uid)
        cmd = ["ffmpeg", "-v", "error", "-y", *src, "-i", logos[0].path]
        for lg in logos:
            cmd += ["-i", lg.path]
        cmd += ["-filter_complex", fc, "-map", "[outv]", "-frames:v", "1", "-q:v", "4", out]
        pr = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL,
                                                  stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(pr.wait(), timeout=40)
        if pr.returncode == 0 and os.path.exists(out):
            await m.reply_photo(out, caption="This is how it will sit on the picture.")
    except Exception:
        log.exception("logo place: preview failed")


async def _place_done(m: Message, uid: int, items: list, start=None) -> None:
    from pyrogram.types import ReplyKeyboardRemove
    if not items and start is None:
        await m.reply("Nothing was changed.", reply_markup=ReplyKeyboardRemove())
        return
    lines = _place_apply(uid, items, start)
    await m.reply("✅ **Logo saved**\n" + "\n".join(lines)
                  + "\n\nIt applies to your next renders. /logopos opens the studio again.",
                  reply_markup=ReplyKeyboardRemove())
    await _place_preview(m, uid)


@app.on_message(filters.command(["logopos", "logoplace", "place", "logoanywhere", "studio", "logostudio"]) & filters.private)
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
    if not isinstance(data, dict) or data.get("k") != "logo_place":
        return
    await _place_done(m, uid, _place_clean(data.get("logos")),
                      _place_start(data.get("start")) if "start" in data else None)


# ---- crash/restart-safe batch journal + /resume ----------------------------
JOURNAL_FILE = ''', "the page opener, /logopos, /logoset, the save")

P.write_text(s)
print("patched %s" % P)
