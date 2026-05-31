"""
Bidhaan Logo-Edit bot.

Send a video -> a control panel appears (inline buttons) where you pick logo
positions, scroll-caption timing + how many times it shows, output resolution,
fps and bitrate (with a live file-size estimate, like Wondershare) -> Render.

The bot then covers broadcaster ad/number banners, burns the logos + caption,
and returns the finished file. One render at a time, with live progress.
"""
from __future__ import annotations

import os
import json
import time
import asyncio
import logging

import uvloop
from pyrogram import Client, filters
from pyrogram.errors import SessionPasswordNeeded
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB,
)

from config import settings
from branding import (
    Logo, RenderConfig, render, probe,
    estimate_size_bytes, bitrate_for_target, human_size,
)
from detect import detect_ad_banners
import delivery

uvloop.install()
logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("bot")

DATA_DIR = "/app/data"
SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")
PREMIUM_SESSION_FILE = os.path.join(DATA_DIR, "premium_session.txt")
TG_LIMIT = int(1.95 * 1024 ** 3)          # ~2 GB Telegram bot cap
PREMIUM_LIMIT = int(3.9 * 1024 ** 3)      # ~4 GB Telegram premium cap
os.environ.setdefault("RCLONE_CONFIG", delivery.RCLONE_CONF)
_render_lock = asyncio.Lock()
_pending: dict[int, dict] = {}            # uid -> active job (probe + src path)
_login: dict[int, dict] = {}              # uid -> premium-login flow state

CORNER_CYCLE = ["TL", "TR", "BR", "BL"]
SCALE_CYCLE = [0.8, 0.9, 1.0, 1.1, 1.25]
# horizontal offset presets for the left Bidhaan, to clear whatever logo the
# source already has top-left (far-left / after small logo / after wide logo)
MX_CYCLE = [0.012, 0.12, 0.22, 0.32]

# Defaults measured off John's "Ustaad trailer" output (exact layout):
#   StreamNxt -> top-LEFT, Bidhaan TV -> top-RIGHT, uppercase caption centered.
DEFAULTS = {
    "scroll_text": "UGAAR AH BIDHAAN TV 0619624090",
    "scroll_seconds": 25.0,
    "scroll_count": 8,           # 0 = continuous (every pass)
    "scroll_times": [],          # exact minute marks (overrides count when set)
    "caption_scale": 0.023,      # caption font size (fraction of height)
    # per-element start minutes (skip intro). 0 = from start.
    "logo_start_min": 0.0,
    "cover_start_min": 0.0,
    "text_start_min": 0.0,
    "cover_mode": "auto",        # auto | off
    "width": 1920, "height": 1080, "fps": 25,
    "bitrate": 2000,             # kbps (video)
    "size_target_gb": 0.0,       # >0 -> auto bitrate to hit this size
    "audio_k": 128,
    "streamnxt_on": False, "streamnxt_corner": "TL",
    "streamnxt_frac": 0.195, "streamnxt_mx": 0.032, "streamnxt_my": 0.095,
    "bidhaan_on": False, "bidhaan_corner": "TR",
    "bidhaan_frac": 0.134, "bidhaan_mx": 0.012, "bidhaan_my": 0.091,
    # second Bidhaan, top-left, offset right so it sits NEXT TO the channel's
    # own logo (e.g. 'a tv' on Kurulus) instead of overlapping it
    # measured exactly off John's reference pic: width 13.2%, left 3.8%, top 10.1%
    "bidhaan2_on": True, "bidhaan2_corner": "TL",
    "bidhaan2_frac": 0.132, "bidhaan2_mx": 0.038, "bidhaan2_my": 0.10,
    "logo_scale": 1.0,           # global multiplier on logo sizes
}


# ----------------------------------------------------------------- settings io
def _load() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save(d: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(d, f, indent=2)


def user_cfg(uid: int) -> dict:
    d = _load()
    c = dict(DEFAULTS)
    c.update(d.get(str(uid), {}))
    return c


def set_user(uid: int, **kw) -> dict:
    d = _load()
    cur = dict(DEFAULTS)
    cur.update(d.get(str(uid), {}))
    cur.update(kw)
    d[str(uid)] = cur
    _save(d)
    return cur


def _asset(name: str) -> str:
    return os.path.join(settings.assets_dir, name)


def _allowed(uid: int) -> bool:
    return settings.owner_id == 0 or uid == settings.owner_id


# ----------------------------------------------------------------- premium
def _premium_session() -> str | None:
    try:
        s = open(PREMIUM_SESSION_FILE).read().strip()
        return s or None
    except OSError:
        return None


async def _premium_send(out_path: str, caption: str, duration: int,
                        w: int, h: int) -> None:
    """Upload via the owner's logged-in PREMIUM account (up to 4GB) -> the
    owner's Saved Messages (the bot itself can't send >2GB)."""
    sess = _premium_session()
    pu = Client("premium_up", api_id=settings.api_id, api_hash=settings.api_hash,
                session_string=sess, in_memory=True, no_updates=True)
    await pu.start()
    try:
        await pu.send_video("me", out_path, caption=caption, duration=duration,
                            width=w, height=h, supports_streaming=True)
    finally:
        await pu.stop()


# ----------------------------------------------------------------- estimate
def _effective_bitrate(c: dict, dur: float) -> tuple[int, str]:
    if c["size_target_gb"] > 0 and dur > 0:
        vk = bitrate_for_target(dur, int(c["size_target_gb"] * 1024 ** 3), c["audio_k"])
        return vk, f"{vk}k (auto → {c['size_target_gb']:g} GB)"
    return c["bitrate"], f"{c['bitrate']}k"


def _fmt_hms(s: float) -> str:
    s = int(s)
    return f"{s//3600}:{(s%3600)//60:02d}:{s%60:02d}"


# ----------------------------------------------------------------- panel
def panel(uid: int, job: dict) -> tuple[str, IKM]:
    c = user_cfg(uid)
    dur = job["duration"]
    vk, br_label = _effective_bitrate(c, dur)
    size = estimate_size_bytes(dur, vk, c["audio_k"])
    if size > TG_LIMIT:
        if _premium_session() and size <= PREMIUM_LIMIT:
            warn = "  → via premium (4GB)"
        elif delivery.mega_is_configured():
            warn = "  → via MEGA link"
        else:
            warn = "  ⚠️ over 2GB (set /loginpremium or /megalogin)"
    else:
        warn = ""
    res = "Source" if c["width"] == 0 else f"{c['width']}×{c['height']}"
    if c.get("scroll_times"):
        times = "@ " + ", ".join(f"{x:g}m" for x in c["scroll_times"])
    else:
        times = "every pass" if c["scroll_count"] == 0 else f"{c['scroll_count']}×"
    logos = []
    if c["streamnxt_on"]:
        logos.append(f"StreamNxt[{c['streamnxt_corner']}]")
    if c["bidhaan_on"]:
        logos.append(f"Bidhaan[{c['bidhaan_corner']}]")
    if c["bidhaan2_on"]:
        logos.append(f"Bidhaan[{c['bidhaan2_corner']}]")

    text = (
        f"🎬 **Ready to render**\n"
        f"`{job['name']}`\n"
        f"⏳ {_fmt_hms(dur)}  •  src {job['w']}×{job['h']}\n\n"
        f"📝 Caption: `{c['scroll_text']}`\n"
        f"⏱ Scroll: {c['scroll_seconds']:g}s  •  🔁 {times}\n"
        f"🖼 {res}  •  🎞 {c['fps']}fps  •  📐 {br_label}\n"
        f"🏷 Logos: {', '.join(logos) or 'none'} (size {int(c['logo_scale']*100)}%)\n"
        f"🟥 Cover ads: {c['cover_mode']}\n"
        + (f"▶️ Start — logo:{c.get('logo_start_min',0):g}m "
           f"cover:{c.get('cover_start_min',0):g}m text:{c.get('text_start_min',0):g}m\n"
           if (c.get('logo_start_min') or c.get('cover_start_min') or c.get('text_start_min'))
           else "")
        + "\n"
        f"💾 **Estimated size: {human_size(size)}**{warn}"
    )
    kb = IKM([
        [IKB("⏱ Scroll time", "m:scroll"), IKB("🔁 Times", "m:times")],
        [IKB("📐 Bitrate", "m:br"), IKB("🎯 Target size", "m:size")],
        [IKB("🖼 Resolution", "m:res"), IKB("🎞 FPS", "m:fps")],
        [IKB("🏷 Logo positions", "m:logos")],
        [IKB(f"🟥 Cover: {c['cover_mode']}", "cover:toggle")],
        [IKB("✅ Render now", "go"), IKB("❌ Cancel", "cancel")],
    ])
    return text, kb


def _back_row():
    return [IKB("⬅ Back", "m:main")]


def submenu(which: str, uid: int, job: dict) -> IKM:
    c = user_cfg(uid)
    if which == "scroll":
        rows = [[IKB(f"{'✅' if c['scroll_seconds']==s else ''}{s}s",
                     f"s:scroll_seconds:{s}") for s in (5, 10, 15)],
                [IKB(f"{'✅' if c['scroll_seconds']==s else ''}{s}s",
                     f"s:scroll_seconds:{s}") for s in (20, 25, 30)]]
        return IKM(rows + [_back_row()])
    if which == "times":
        opts = [1, 3, 5, 8, 10, 12, 20]
        rows = [[IKB(f"{'✅' if c['scroll_count']==n else ''}{n}×",
                     f"s:scroll_count:{n}") for n in opts[i:i+4]] for i in (0, 4)]
        rows.append([IKB(("✅ " if c['scroll_count'] == 0 else "") + "Every pass (max)",
                         "s:scroll_count:0")])
        rows.append([IKB("✏️ Exact minutes → type  /at 1 3 12 24", "noop")])
        return IKM(rows + [_back_row()])
    if which == "br":
        opts = [1500, 2000, 2300, 2700, 3000, 3500]
        rows = [[IKB(f"{'✅' if (c['size_target_gb']==0 and c['bitrate']==b) else ''}{b}",
                     f"s:bitrate:{b}") for b in opts[i:i+3]] for i in (0, 3)]
        return IKM(rows + [_back_row()])
    if which == "size":
        opts = [("Off", 0.0), ("1.5 GB", 1.5), ("1.9 GB", 1.9), ("2.0 GB", 2.0)]
        rows = [[IKB(f"{'✅' if c['size_target_gb']==v else ''}{lbl}",
                     f"s:size_target_gb:{v}") for lbl, v in opts]]
        return IKM(rows + [_back_row()])
    if which == "res":
        opts = [("1920×1080", "1920x1080"), ("1280×720", "1280x720"), ("Source", "source")]
        cur = "source" if c["width"] == 0 else f"{c['width']}x{c['height']}"
        rows = [[IKB(f"{'✅' if cur==v else ''}{lbl}", f"s:res:{v}") for lbl, v in opts]]
        return IKM(rows + [_back_row()])
    if which == "fps":
        rows = [[IKB(f"{'✅' if c['fps']==f else ''}{f}", f"s:fps:{f}")
                 for f in (24, 25, 30)]]
        return IKM(rows + [_back_row()])
    if which == "logos":
        sn = f"StreamNxt: {c['streamnxt_corner']} {'on' if c['streamnxt_on'] else 'OFF'}"
        bd = f"Bidhaan R: {c['bidhaan_corner']} {'on' if c['bidhaan_on'] else 'OFF'}"
        b2 = f"Bidhaan L: {c['bidhaan2_corner']} {'on' if c['bidhaan2_on'] else 'OFF'}"
        rows = [
            [IKB(f"↻ {sn}", "lg:streamnxt:corner"), IKB("⏻", "lg:streamnxt:toggle")],
            [IKB(f"↻ {bd}", "lg:bidhaan:corner"), IKB("⏻", "lg:bidhaan:toggle")],
            [IKB(f"↻ {b2}", "lg:bidhaan2:corner"), IKB("⏻", "lg:bidhaan2:toggle")],
            [IKB(f"Bidhaan-L slide →  {int(c['bidhaan2_mx']*100)}%", "lg:bidhaan2:offset")],
            [IKB(f"Size: {int(c['logo_scale']*100)}%  (tap to change)", "lg:scale:cycle")],
            _back_row(),
        ]
        return IKM(rows)
    return IKM([_back_row()])


# ----------------------------------------------------------------- app
app = Client(
    name="bidhaan_logoedit",
    api_id=settings.api_id, api_hash=settings.api_hash, bot_token=settings.bot_token,
    workdir=DATA_DIR, workers=20, sleep_threshold=60, max_concurrent_transmissions=8,
)

HELP = (
    "🎬 **Bidhaan Logo-Edit**\n\n"
    "Send me a **video**. A panel opens where you choose logo positions, scroll "
    "timing, resolution, fps and bitrate (with a live size estimate). Tap "
    "**Render** and I cover the ad/number banners, add your logos + caption, and "
    "send it back.\n\n"
    "/settings — show your saved defaults\n"
    "/text `caption` — set the scrolling caption\n"
    "/at `1 3 12 24` — show the caption at exact minute marks "
    "(send `/at` alone to clear)\n"
    "/begin `2` — start logo/caption/cover at minute 2 (skip an intro)\n"
    "/logoat · /coverat · /textat `2.5` — start each element separately\n"
    "/capsize `small`|`normal`|`big` — caption size\n\n"
    "**Big files (2GB+)**\n"
    "/loginpremium — connect your premium account → send up to 4GB\n"
    "/megalogin `email pass` — send 2GB+ videos as a MEGA link\n"
)


@app.on_message(filters.command(["start", "help"]) & filters.private)
async def _start(_, m: Message):
    if not _allowed(m.from_user.id):
        return await m.reply("⛔ This bot is private.")
    await m.reply(HELP)


@app.on_message(filters.command("settings") & filters.private)
async def _settings(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    c = user_cfg(m.from_user.id)
    await m.reply("⚙️ **Saved defaults**\n```\n" +
                  json.dumps({k: c[k] for k in (
                      "scroll_text", "scroll_seconds", "scroll_count", "width",
                      "height", "fps", "bitrate", "size_target_gb",
                      "streamnxt_corner", "bidhaan_corner", "logo_frac",
                      "cover_mode")}, indent=2) + "\n```")


@app.on_message(filters.command("text") & filters.private)
async def _text(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    if len(m.command) < 2:
        return await m.reply("Usage: `/text ugaar ah bidhaan tv 0619624090`")
    new = m.text.split(None, 1)[1].strip()
    set_user(m.from_user.id, scroll_text=new)
    await m.reply(f"✅ Caption set:\n`{new}`")


@app.on_message(filters.command("begin") & filters.private)
async def _begin(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    if len(m.command) < 2:
        return await m.reply("Usage: `/begin 2`  → logo, caption and banner-cover "
                             "start at minute 2 (skips a 2-min intro). `/begin 0` = from start.")
    try:
        mins = float(m.command[1].replace(",", "."))
    except ValueError:
        return await m.reply("Give a number of minutes, e.g. `/begin 2`")
    mins = max(0.0, mins)
    set_user(m.from_user.id, logo_start_min=mins, cover_start_min=mins, text_start_min=mins)
    if mins <= 0:
        await m.reply("✅ Everything starts from the very beginning.")
    else:
        await m.reply(f"✅ Logo, caption & banner-cover all start at **{mins:g} min** "
                      f"(first {mins:g} min / intro stays clean).\n"
                      f"To set them separately: `/logoat 2`, `/coverat 2.5`, `/textat 3`")


async def _set_start(m: Message, key: str, label: str):
    if not _allowed(m.from_user.id):
        return
    if len(m.command) < 2:
        return await m.reply(f"Usage: `/{m.command[0]} 2.5`  → {label} starts at minute 2.5")
    try:
        mins = max(0.0, float(m.command[1].replace(",", ".")))
    except ValueError:
        return await m.reply("Give minutes, e.g. `2` or `2.5`")
    set_user(m.from_user.id, **{key: mins})
    await m.reply(f"✅ {label} starts at **{mins:g} min**.")


@app.on_message(filters.command("logoat") & filters.private)
async def _logoat(_, m: Message):
    await _set_start(m, "logo_start_min", "Logo")


@app.on_message(filters.command("coverat") & filters.private)
async def _coverat(_, m: Message):
    await _set_start(m, "cover_start_min", "Banner-cover")


@app.on_message(filters.command("textat") & filters.private)
async def _textat(_, m: Message):
    await _set_start(m, "text_start_min", "Caption")


@app.on_message(filters.command("capsize") & filters.private)
async def _capsize(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    arg = (m.command[1].lower() if len(m.command) > 1 else "")
    sizes = {"small": 0.018, "normal": 0.023, "big": 0.030}
    if arg not in sizes:
        return await m.reply("Usage: `/capsize small|normal|big`")
    set_user(m.from_user.id, caption_scale=sizes[arg])
    await m.reply(f"✅ Caption size: `{arg}`")


@app.on_message(filters.command("megalogin") & filters.private)
async def _megalogin(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    if len(m.command) < 3:
        return await m.reply("Usage: `/megalogin your@email.com yourpassword`\n"
                             "Then videos over 2GB are uploaded to MEGA and I send you the link.")
    email = m.command[1]
    pw = m.text.split(None, 2)[2]
    await m.reply("⏳ Connecting to MEGA…")
    ok, msg = await asyncio.to_thread(delivery.mega_configure, email, pw)
    await m.reply("✅ MEGA connected. Big videos (2GB+) will be sent as a MEGA link."
                  if ok else f"❌ MEGA login failed: `{msg}`")


@app.on_message(filters.command("loginpremium") & filters.private)
async def _loginpremium(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    _login[m.from_user.id] = {"step": "phone"}
    await m.reply("🔐 **Premium account login** (for up to 4GB uploads).\n\n"
                  "Send your phone number with country code, e.g. `+252612345678`.\n"
                  "(Send /cancel to stop.)")


@app.on_message(filters.command("cancel") & filters.private)
async def _cancel(_, m: Message):
    st = _login.pop(m.from_user.id, None)
    if st and st.get("client"):
        try:
            await st["client"].disconnect()
        except Exception:
            pass
    await m.reply("✖️ Cancelled." if st else "Nothing to cancel.")


@app.on_message(filters.command("logoutpremium") & filters.private)
async def _logoutpremium(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    try:
        os.remove(PREMIUM_SESSION_FILE)
    except OSError:
        pass
    await m.reply("✅ Premium account removed.")


@app.on_message(filters.text & filters.private & ~filters.regex(r"^/"))
async def _login_text(_, m: Message):
    uid = m.from_user.id
    if not _allowed(uid) or uid not in _login:
        return
    st = _login[uid]
    try:
        if st["step"] == "phone":
            phone = m.text.strip().replace(" ", "")
            cli = Client("premium_login", api_id=settings.api_id,
                         api_hash=settings.api_hash, in_memory=True, no_updates=True)
            await cli.connect()
            sent = await cli.send_code(phone)
            st.update(step="otp", client=cli, phone=phone, hash=sent.phone_code_hash)
            await m.reply("📲 A code was sent to your Telegram. Send it **with spaces** "
                          "so Telegram doesn't block it, e.g. `1 2 3 4 5`.")
        elif st["step"] == "otp":
            code = m.text.replace(" ", "").strip()
            cli = st["client"]
            try:
                await cli.sign_in(st["phone"], st["hash"], code)
            except SessionPasswordNeeded:
                st["step"] = "2fa"
                return await m.reply("🔒 Your account has 2FA. Send your password.")
            sess = await cli.export_session_string()
            with open(PREMIUM_SESSION_FILE, "w") as f:
                f.write(sess)
            await cli.disconnect()
            _login.pop(uid, None)
            await m.reply("✅ Premium account connected — videos up to **4GB** are now "
                          "delivered straight to your Saved Messages.")
        elif st["step"] == "2fa":
            cli = st["client"]
            await cli.check_password(m.text.strip())
            sess = await cli.export_session_string()
            with open(PREMIUM_SESSION_FILE, "w") as f:
                f.write(sess)
            await cli.disconnect()
            _login.pop(uid, None)
            await m.reply("✅ Premium account connected — up to **4GB** uploads.")
    except Exception as e:
        await m.reply(f"❌ Login error: `{str(e)[:200]}`\nTry /loginpremium again.")
        st2 = _login.pop(uid, None)
        if st2 and st2.get("client"):
            try:
                await st2["client"].disconnect()
            except Exception:
                pass


@app.on_message(filters.command("at") & filters.private)
async def _at(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    args = m.command[1:]
    if not args:
        set_user(m.from_user.id, scroll_times=[])
        return await m.reply("✅ Cleared exact times — caption now uses the "
                             "**Times** (even spread) setting again.")
    mins = []
    for a in args:
        try:
            mins.append(float(a.replace(",", ".")))
        except ValueError:
            return await m.reply(f"`{a}` isn't a number. Example:\n"
                                 "`/at 1 3 12 24 52 119`  (minutes)")
    mins = sorted(set(mins))
    set_user(m.from_user.id, scroll_times=mins)
    await m.reply("✅ Caption will appear at: " +
                  ", ".join(f"{x:g}min" for x in mins) +
                  "\n(Send `/at` with no numbers to go back to even spread.)")


@app.on_message((filters.video | filters.document) & filters.private)
async def _on_video(_, m: Message):
    uid = m.from_user.id
    if not _allowed(uid):
        return await m.reply("⛔ This bot is private.")
    if m.document and not (m.document.mime_type or "").startswith("video"):
        return

    work = os.path.join(settings.work_dir, str(int(time.time())))
    os.makedirs(work, exist_ok=True)
    status = await m.reply("⬇️ Downloading…")
    try:
        src = await m.download(file_name=os.path.join(work, "src.mp4"))
        w, h, dur = await asyncio.to_thread(probe, src)
        name = (getattr(m.video, "file_name", None)
                or getattr(m.document, "file_name", None) or "video.mp4")
        _pending[uid] = {"src": src, "work": work, "w": w, "h": h,
                         "duration": dur, "name": name, "msg": m}
        text, kb = panel(uid, _pending[uid])
        await status.edit(text, reply_markup=kb)
    except Exception as e:
        log.exception("probe/download failed")
        await status.edit(f"❌ Failed: `{str(e)[:300]}`")


@app.on_callback_query()
async def _cb(_, cq: CallbackQuery):
    uid = cq.from_user.id
    if not _allowed(uid):
        return await cq.answer("private", show_alert=True)
    job = _pending.get(uid)
    data = cq.data

    if data == "noop":
        return await cq.answer("Type:  /at 1 3 12 24 52   (minutes you want it shown)",
                               show_alert=True)

    if data == "cancel":
        _pending.pop(uid, None)
        await cq.message.edit("❌ Cancelled.")
        return await cq.answer()

    if job is None:
        return await cq.answer("Session expired — send the video again.", show_alert=True)

    # navigation
    if data == "m:main":
        text, kb = panel(uid, job)
        await cq.message.edit(text, reply_markup=kb)
        return await cq.answer()
    if data.startswith("m:"):
        await cq.message.edit_reply_markup(submenu(data[2:], uid, job))
        return await cq.answer()

    # setting changes
    if data.startswith("s:"):
        _, key, val = data.split(":", 2)
        if key == "scroll_seconds":
            set_user(uid, scroll_seconds=float(val))
        elif key == "scroll_count":
            set_user(uid, scroll_count=int(val), scroll_times=[])  # exact-times off
        elif key == "bitrate":
            set_user(uid, bitrate=int(val), size_target_gb=0.0)
        elif key == "size_target_gb":
            set_user(uid, size_target_gb=float(val))
        elif key == "fps":
            set_user(uid, fps=int(val))
        elif key == "res":
            if val == "source":
                set_user(uid, width=0, height=0)
            else:
                w, h = val.split("x")
                set_user(uid, width=int(w), height=int(h))
        text, kb = panel(uid, job)
        await cq.message.edit(text, reply_markup=kb)
        return await cq.answer("✓")

    if data.startswith("lg:"):
        _, who, act = data.split(":", 2)
        c = user_cfg(uid)
        if act == "toggle":
            set_user(uid, **{f"{who}_on": not c[f"{who}_on"]})
        elif act == "corner":
            nxt = CORNER_CYCLE[(CORNER_CYCLE.index(c[f"{who}_corner"]) + 1) % 4]
            set_user(uid, **{f"{who}_corner": nxt})
        elif act == "cycle" and who == "scale":
            i = SCALE_CYCLE.index(c["logo_scale"]) if c["logo_scale"] in SCALE_CYCLE else 2
            set_user(uid, logo_scale=SCALE_CYCLE[(i + 1) % len(SCALE_CYCLE)])
        elif act == "offset" and who == "bidhaan2":
            cur = min(MX_CYCLE, key=lambda v: abs(v - c["bidhaan2_mx"]))
            i = MX_CYCLE.index(cur)
            set_user(uid, bidhaan2_mx=MX_CYCLE[(i + 1) % len(MX_CYCLE)])
        await cq.message.edit_reply_markup(submenu("logos", uid, job))
        return await cq.answer("✓")

    if data == "cover:toggle":
        c = user_cfg(uid)
        set_user(uid, cover_mode=("off" if c["cover_mode"] == "auto" else "auto"))
        text, kb = panel(uid, job)
        await cq.message.edit(text, reply_markup=kb)
        return await cq.answer("✓")

    if data == "go":
        await cq.answer("Starting…")
        await _do_render(cq, uid, job)
        return


# ----------------------------------------------------------------- render
async def _do_render(cq: CallbackQuery, uid: int, job: dict):
    if _render_lock.locked():
        await cq.message.edit("⏳ Another render is running — try again when it's done.")
        return
    async with _render_lock:
        c = user_cfg(uid)
        src, work, dur = job["src"], job["work"], job["duration"]
        status = cq.message
        try:
            # detection at render time (adaptive fps for long videos)
            events = []
            if c["cover_mode"] == "auto":
                await status.edit("🔎 Scanning for ad / number banners…")
                dfps = max(0.15, min(1.0, 1800.0 / dur)) if dur > 0 else 1.0
                events = await asyncio.to_thread(
                    detect_ad_banners, src, work, dfps, settings.merge_gap)

            vk, _ = _effective_bitrate(c, dur)
            logos = []
            sc = c["logo_scale"]
            if c["streamnxt_on"]:
                logos.append(Logo(_asset(settings.logo_tr), c["streamnxt_corner"],
                                  c["streamnxt_frac"] * sc, c["streamnxt_mx"], c["streamnxt_my"]))
            if c["bidhaan_on"]:
                logos.append(Logo(_asset(settings.logo_tl), c["bidhaan_corner"],
                                  c["bidhaan_frac"] * sc, c["bidhaan_mx"], c["bidhaan_my"]))
            if c["bidhaan2_on"]:
                logos.append(Logo(_asset(settings.logo_tl), c["bidhaan2_corner"],
                                  c["bidhaan2_frac"] * sc, c["bidhaan2_mx"], c["bidhaan2_my"]))

            cfg = RenderConfig(
                logos=logos, cover_png=_asset(settings.cover_png),
                scroll_text=c["scroll_text"], scroll_seconds=c["scroll_seconds"],
                scroll_count=(c["scroll_count"] or max(1, int(dur / max(2.0, c["scroll_seconds"])))),
                scroll_times=[mn * 60 for mn in c.get("scroll_times", []) if mn * 60 < dur],
                caption_scale=c.get("caption_scale", 0.023),
                logo_start=c.get("logo_start_min", 0.0) * 60,
                cover_start=c.get("cover_start_min", 0.0) * 60,
                text_start=c.get("text_start_min", 0.0) * 60,
                width=(job["w"] if c["width"] == 0 else c["width"]),
                height=(job["h"] if c["height"] == 0 else c["height"]),
                fps=c["fps"], video_bitrate_k=vk, audio_bitrate_k=c["audio_k"],
                preset=settings.x264_preset,
            )
            out = os.path.join(work, "branded.mp4")
            prog = {"pct": 0.0}

            async def poller():
                last = -1
                while True:
                    await asyncio.sleep(8)
                    p = int(prog["pct"])
                    if p != last and p < 100:
                        last = p
                        try:
                            await status.edit(
                                f"🎨 Rendering… {p}%  ({len(events)} banner(s) covered)")
                        except Exception:
                            pass

            pt = asyncio.create_task(poller())
            try:
                await asyncio.to_thread(render, src, out, events, cfg,
                                        lambda p: prog.__setitem__("pct", p))
            finally:
                pt.cancel()

            ow, oh, odur = await asyncio.to_thread(probe, out)
            sz = os.path.getsize(out)
            cap = f"✅ Branded — {len(events)} banner(s) covered • {human_size(sz)}"
            name = f"branded_{os.path.basename(job['name'])}"

            if sz <= TG_LIMIT:
                # fits Telegram's 2GB bot limit -> send normally
                await status.edit(f"⬆️ Uploading… ({human_size(sz)})")
                await job["msg"].reply_video(
                    out, duration=int(odur), width=ow, height=oh,
                    supports_streaming=True, caption=cap)
            elif _premium_session() and sz <= PREMIUM_LIMIT:
                # use the owner's premium account (up to 4GB) -> Saved Messages
                await status.edit(f"⬆️ {human_size(sz)} — uploading via your premium "
                                  f"account (up to 4GB)…")
                await _premium_send(out, cap, int(odur), ow, oh)
                await job["msg"].reply(
                    f"{cap}\n📥 Too big for the bot — sent to your **Saved Messages** "
                    f"via your premium account.")
            elif delivery.mega_is_configured():
                await status.edit(f"☁️ {human_size(sz)} — uploading to MEGA…")
                link = await asyncio.to_thread(delivery.mega_upload, out, name)
                await job["msg"].reply(f"{cap}\n📥 Too big for Telegram — **MEGA link:**\n{link}")
            else:
                await job["msg"].reply(
                    f"⚠️ Output is {human_size(sz)} — over Telegram's 2GB bot limit.\n"
                    f"Options:\n• `/loginpremium` to send up to 4GB via your account\n"
                    f"• `/megalogin email pass` to get a MEGA link\n"
                    f"• or lower the bitrate / set Target size 1.9GB and re-render")
            await status.delete()
        except Exception as e:
            log.exception("render failed")
            await status.edit(f"❌ Failed: `{str(e)[:300]}`")
        finally:
            _pending.pop(uid, None)
            try:
                for root, _d, files in os.walk(work, topdown=False):
                    for f in files:
                        os.remove(os.path.join(root, f))
                    os.rmdir(root)
            except OSError:
                pass


if __name__ == "__main__":
    log.info("Bidhaan Logo-Edit bot starting…")
    app.run()
