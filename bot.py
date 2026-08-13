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
import re
import json
import time
import shutil
import asyncio
from pathlib import Path
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
# Concurrency: up to MAX_RENDERS jobs render AT THE SAME TIME, so different
# users' videos process simultaneously instead of waiting in one line. The VPS
# cpu_shares/cpus caps keep the box (and the other bots) safe under load.
_render_sem = asyncio.Semaphore(int(os.environ.get("MAX_RENDERS", "3")))
_pending: dict[int, dict] = {}            # uid -> active job (probe + src path)
_login: dict[int, dict] = {}              # uid -> premium-login flow state
# PER-UID in-flight download/render so concurrent jobs don't clobber each other
# and /cancel can stop the right one: uid -> {proc, cancelled, phase}
_active: dict[int, dict] = {}


def _act(uid: int) -> dict:
    return _active.setdefault(uid, {"proc": None, "cancelled": False, "phase": ""})


# ---- OUTBOX: finished files are kept here so a delivery failure (MEGA full,
# over 2GB with no method, etc.) never loses the render. /deliver re-sends them.
OUTBOX = os.path.join(DATA_DIR, "outbox")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")


def _load_pending() -> dict:
    try:
        with open(PENDING_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_pending(d: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PENDING_FILE, "w") as f:
        json.dump(d, f, indent=2)


def _add_pending(uid: int, entry: dict) -> None:
    d = _load_pending()
    d.setdefault(str(uid), []).append(entry)
    _save_pending(d)


def _remove_pending(uid: int, path: str) -> None:
    d = _load_pending()
    lst = [e for e in d.get(str(uid), []) if e.get("path") != path]
    if lst:
        d[str(uid)] = lst
    else:
        d.pop(str(uid), None)
    _save_pending(d)
# ---- batch queue: send many files at once -> processed one-by-one ----
_queue: dict[int, list] = {}              # uid -> incoming msgs being collected
_qtimer: dict[int, asyncio.Task] = {}     # uid -> debounce task
_batch: dict[int, list] = {}              # uid -> msgs confirmed, awaiting "go"
_batch_panel: dict[int, Message] = {}     # uid -> the batch panel message
_batch_cancel: dict[int, bool] = {}       # uid -> stop-the-whole-batch flag
_dubsel: dict[int, dict] = {}             # uid -> pending dub-sync selection
_dubflow: dict[int, dict] = {}            # uid -> guided dub-sync intake
_work_seq = 0


def _new_work() -> str:
    """A UNIQUE work dir per job — never share (two renders in one dir corrupt
    each other's frames/output)."""
    global _work_seq
    _work_seq += 1
    w = os.path.join(settings.work_dir, f"{int(time.time())}_{_work_seq}")
    os.makedirs(w, exist_ok=True)
    return w

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
    "caption_scale": 0.016,      # caption font size (fraction of height) — small, Wondershare-style
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


# ---- named presets/templates (e.g. "movie", "series") ----
TEMPLATES_FILE = os.path.join(DATA_DIR, "templates.json")


def _load_tpls() -> dict:
    try:
        with open(TEMPLATES_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def get_templates(uid: int) -> dict:
    return _load_tpls().get(str(uid), {})


def save_template(uid: int, name: str) -> None:
    """Snapshot the user's current brandable settings under `name`."""
    d = _load_tpls()
    c = user_cfg(uid)
    d.setdefault(str(uid), {})[name] = {k: c[k] for k in DEFAULTS}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TEMPLATES_FILE, "w") as f:
        json.dump(d, f, indent=2)


def delete_template(uid: int, name: str) -> bool:
    d = _load_tpls()
    if str(uid) in d and name in d[str(uid)]:
        del d[str(uid)][name]
        with open(TEMPLATES_FILE, "w") as f:
            json.dump(d, f, indent=2)
        return True
    return False


def apply_template(uid: int, name: str) -> bool:
    tpls = get_templates(uid)
    if name not in tpls:
        return False
    set_user(uid, **tpls[name])
    return True


def _asset(name: str) -> str:
    return os.path.join(settings.assets_dir, name)


# ---- access control: owner + an owner-managed allowlist of authorized ids ----
ALLOWED_FILE = os.path.join(DATA_DIR, "allowed_users.json")


def _load_allowed() -> set:
    try:
        with open(ALLOWED_FILE) as f:
            return {int(x) for x in json.load(f)}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return set()


def _save_allowed(s: set) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ALLOWED_FILE, "w") as f:
        json.dump(sorted(s), f)


def _is_owner(uid: int) -> bool:
    return settings.owner_id != 0 and uid == settings.owner_id


def _allowed(uid: int) -> bool:
    if settings.owner_id == 0:           # not configured -> open (avoids lockout)
        return True
    return uid == settings.owner_id or uid in _load_allowed()


def _parse_ids(m: Message) -> list[int]:
    """User ids from the command text, or from a replied-to / forwarded message."""
    ids = [int(x) for x in re.findall(r"\d{5,}", m.text or "")]
    if m.reply_to_message and m.reply_to_message.from_user:
        ids.append(m.reply_to_message.from_user.id)
    fo = getattr(m, "forward_from", None)
    if fo:
        ids.append(fo.id)
    return list(dict.fromkeys(ids))      # unique, keep order


# ----------------------------------------------------------------- premium
def _premium_session() -> str | None:
    try:
        s = open(PREMIUM_SESSION_FILE).read().strip()
        return s or None
    except OSError:
        return None


async def _premium_send(out_path: str, caption: str, duration: int,
                        w: int, h: int, target_uid: int | None = None,
                        progress=None) -> str:
    """Upload via the logged-in PREMIUM account (up to 4GB) and hand the result
    to `target_uid`.

    The bot cannot upload >2GB itself, and the premium USER account cannot
    message an arbitrary user id it has never spoken to — that raises
    PEER_ID_INVALID, which is why this used to dead-end in the premium
    account's own Saved Messages.

    A bot, however, is always resolvable by username, and `copy_message`
    re-sends an EXISTING file rather than uploading a new one, so the bot's
    upload ceiling does not apply. The premium account therefore uploads into
    the bot's DM, and the bot copies it to whoever asked for the job.

    Returns a short description of where it ended up, for the status message.
    """
    sess = _premium_session()
    pu = Client("premium_up", api_id=settings.api_id, api_hash=settings.api_hash,
                session_string=sess, in_memory=True, no_updates=True)
    await pu.start()
    try:
        me_bot = await app.get_me()
        dest = me_bot.username or "me"
        sent = await pu.send_video(dest, out_path, caption=caption,
                                   duration=duration, width=w, height=h,
                                   supports_streaming=True, progress=progress)
        prem_me = await pu.get_me()
    finally:
        await pu.stop()

    if target_uid and sent is not None:
        try:
            # Copy, not forward: no "forwarded from" header on the user's copy.
            await app.copy_message(chat_id=target_uid,
                                   from_chat_id=prem_me.id,
                                   message_id=sent.id)
            return "your chat"
        except Exception as e:
            log.warning("premium->user copy failed: %s", e)
            return f"the premium account's Saved Messages (copy failed: {str(e)[:60]})"
    return "the premium account's Saved Messages"


# ----------------------------------------------------------------- estimate
def _effective_bitrate(c: dict, dur: float) -> tuple[int, str]:
    if c["size_target_gb"] > 0 and dur > 0:
        vk = bitrate_for_target(dur, int(c["size_target_gb"] * 1024 ** 3), c["audio_k"])
        return vk, f"{vk}k (auto → {c['size_target_gb']:g} GB)"
    return c["bitrate"], f"{c['bitrate']}k"


def _fit_bitrate(vk: int, dur: float, audio_k: int) -> tuple[int, str]:
    """Reduce `vk` only as far as needed for the file to fit the delivery cap.

    Never raises the bitrate: the user setting is the ceiling. Returns the
    bitrate to use plus a short note when it had to be trimmed.
    """
    if dur <= 0 or vk <= 0:
        return vk, ""
    cap = PREMIUM_LIMIT if _premium_session() else TG_LIMIT
    if estimate_size_bytes(dur, vk, audio_k) <= cap:
        return vk, ""
    # 7% headroom, not a guess: x264 with -maxrate/-bufsize overshoots the
    # nominal bitrate slightly and the HD intro adds seconds the estimate does
    # not model. Measured on Lenin, a 1714k target landed at 1.942 GiB against
    # a 1.95 GiB cap -- inside, but by 8 MB. 0.93 puts it near 1.85 GiB.
    fit = bitrate_for_target(dur, int(cap * 0.93), audio_k)
    if fit >= vk:
        return vk, ""
    return fit, f" → {fit}k to fit Telegram"


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
    rows = []
    # one-tap presets at the top: applies the saved settings AND renders
    tpls = list(get_templates(uid))
    if tpls:
        rows.append([IKB(f"🎬 {n}", f"tpl:{n}") for n in tpls[:3]])
    rows += [
        [IKB("⏱ Scroll time", "m:scroll"), IKB("🔁 Times", "m:times")],
        [IKB("📐 Bitrate", "m:br"), IKB("🎯 Target size", "m:size")],
        [IKB("🖼 Resolution", "m:res"), IKB("🎞 FPS", "m:fps")],
        [IKB("🏷 Logo positions", "m:logos")],
        [IKB("▶️ Start times (skip intro)", "m:starts")],
        [IKB(f"🟥 Cover: {c['cover_mode']}", "cover:toggle")],
        [IKB("✅ Render now", "go"), IKB("❌ Cancel", "cancel")],
    ]
    return text, IKM(rows)


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
    if which == "starts":
        # let John pick the minute each element starts (so an intro stays clean
        # until then). 0 = from the very start.
        mins = [0, 1, 2, 3, 5]

        def _lbl(m):
            return "Off" if m == 0 else f"{m}m"

        def _row(key):
            return [IKB(("✅ " if abs(c.get(key, 0.0) - m) < 0.01 else "") + _lbl(m),
                        f"s:{key}:{m}") for m in mins]
        rows = [
            [IKB("🏷 Bidhaan logo starts at:", "noop")], _row("logo_start_min"),
            [IKB("🟥 Banner cover starts at:", "noop")], _row("cover_start_min"),
            [IKB("📝 Caption starts at:", "noop")], _row("text_start_min"),
            _back_row(),
        ]
        return IKM(rows)
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
    "Send me a **video**, or **paste a MEGA link** — pasting a link is far "
    "faster for big movies (the server pulls it at ~200 MB/s instead of the slow "
    "Telegram download). A panel then opens where you choose logo positions, "
    "scroll timing, resolution, fps and bitrate (with a live size estimate). Tap "
    "**Render** and I cover the ad/number banners, add your logos + caption, and "
    "send it back.\n\n"
    "⚡ **Fastest for big movies:** paste the **MEGA link** instead of forwarding.\n"
    "⏭ No banners? Turn **Cover off** in the panel to skip scanning.\n\n"
    "/settings — show your saved defaults\n"
    "/text `caption` — set the scrolling caption\n"
    "/at `1 3 12 24` — show the caption at exact minute marks "
    "(send `/at` alone to clear)\n"
    "/begin `2` — start logo/caption/cover at minute 2 (skip an intro)\n"
    "/logoat · /coverat · /textat `2.5` — start each element separately\n"
    "/capsize `small`|`normal`|`big` — caption size\n"
    "/cancel — stop the current download / render\n\n"
    "🎬 **One-tap presets** (e.g. for movies)\n"
    "Set the panel how you like, then `/save movie`. Next time: paste a link → "
    "tap **🎬 movie** → it applies those settings and renders in one tap.\n"
    "`/presets` list · `/delpreset <name>` remove\n\n"
    "📦 **Batch (whole series at once)**\n"
    "Send ALL the episodes/files together (or paste several MEGA links). The bot "
    "queues them and shows a 📦 panel — tap a preset (or **Render all**) and it "
    "brands them **one-by-one automatically**. `/cancel` stops the batch.\n\n"
    "**Big files (2GB+)**\n"
    "/loginpremium — connect your premium account → send up to 4GB\n"
    "/megalogin `email pass` — send 2GB+ videos as a MEGA link\n"
    "💾 If delivery fails (MEGA full etc.) the finished file is **kept on the "
    "server** — `/files` to see them, `/deliver` to send them once you've freed "
    "space. No re-rendering.\n\n"
    "🎬 **/dub** — dub-sync: conform an HD master to a Somali dub. The bot asks "
    "for each file, then brands the result in the same encode.\n\n"
    "👤 `/myid` — show your Telegram ID (to request access)\n"
    "👑 **Owner only:** `/allow <id>` · `/deny <id>` · `/users` — manage who can "
    "use the bot.\n"
)


@app.on_message(filters.command(["start", "help"]) & filters.private)
async def _start(_, m: Message):
    if not _allowed(m.from_user.id):
        return await m.reply(f"⛔ This bot is private.\nYour ID is `{m.from_user.id}` — "
                             "send it to the owner to request access.")
    await m.reply(HELP, reply_markup=IKM([
        [IKB("🎬 Dub-sync (HD + Somali dub)", "dubflow:begin")],
        [IKB("⚙️ Settings", "open:settings")],
    ]))


@app.on_message(filters.command("settings") & filters.private)
async def _settings(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    c = user_cfg(m.from_user.id)
    await m.reply("⚙️ **Saved defaults**\n```\n" +
                  json.dumps({k: c[k] for k in (
                      "scroll_text", "scroll_seconds", "scroll_count", "width",
                      "height", "fps", "bitrate", "size_target_gb",
                      "streamnxt_corner", "bidhaan_corner", "logo_scale",
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


@app.on_message(filters.command("save") & filters.private)
async def _save_preset(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    if len(m.command) < 2:
        return await m.reply(
            "Save your current settings as a one-tap preset:\n"
            "`/save movie` — then next time, after you paste a link, tap "
            "**🎬 movie** to apply it and render in one tap.\n"
            "You can keep several (e.g. `movie`, `series`, `trailer`).")
    name = " ".join(m.command[1:]).strip().lower()[:20]
    save_template(m.from_user.id, name)
    c = user_cfg(m.from_user.id)
    await m.reply(
        f"✅ Saved preset **{name}** with your current settings "
        f"(cover {c['cover_mode']}, {c['width']}×{c['height']}, logo start "
        f"{c.get('logo_start_min',0):g}m).\n\n"
        f"Now for any movie: **paste the link → tap 🎬 {name}** → done.")


@app.on_message(filters.command(["presets", "templates"]) & filters.private)
async def _list_presets(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    t = get_templates(m.from_user.id)
    if not t:
        return await m.reply("No presets yet. Set the panel how you like, then "
                             "`/save movie`.")
    await m.reply("🎬 **Your presets:**\n" + "\n".join(f"• {n}" for n in t) +
                  "\n\n`/save <name>` add/update · `/delpreset <name>` remove")


@app.on_message(filters.command("delpreset") & filters.private)
async def _del_preset(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    if len(m.command) < 2:
        return await m.reply("Usage: `/delpreset movie`")
    name = " ".join(m.command[1:]).strip().lower()
    await m.reply("🗑 Removed." if delete_template(m.from_user.id, name)
                  else "No such preset.")


@app.on_message(filters.command("capsize") & filters.private)
async def _capsize(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    arg = (m.command[1].lower() if len(m.command) > 1 else "")
    sizes = {"small": 0.013, "normal": 0.016, "big": 0.022}
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


async def _cancel_everything(uid: int) -> list:
    """Stop whatever this user has running. Shared by /cancel and the button,
    so the button can no longer claim to cancel while the job keeps going."""
    done = []
    # 0) a batch: stop the whole queue (and the current item below)
    if _dubflow.pop(uid, None) is not None:
        done.append("🎬 dub-sync intake cancelled")

    if _batch_cancel.get(uid) is not None or _batch.get(uid) or _queue.get(uid):
        _batch_cancel[uid] = True
        tm = _qtimer.pop(uid, None)
        if tm:
            tm.cancel()
        n = len(_queue.pop(uid, [])) + len(_batch.pop(uid, []))
        _batch_panel.pop(uid, None)
        done.append("🛑 batch stopped" + (f" ({n} queued cleared)" if n else ""))
    # 1) a running download or render.
    #    A subprocess (ffmpeg, megadl, the dubsync stages) gets killed. A
    #    Telegram download has NO subprocess — it is an asyncio task — so the
    #    task is cancelled too, otherwise the bot reports "cancelled" while the
    #    download carries happily on, which is exactly what John saw.
    a = _active.get(uid)
    if a:
        a["cancelled"] = True
        killed = False
        if a.get("proc"):
            try:
                a["proc"].kill()
                killed = True
            except Exception:
                pass
        task = a.get("task")
        if task is not None and not task.done():
            try:
                task.cancel()
                killed = True
            except Exception:
                pass
        if killed:
            done.append(f"🛑 {a.get('phase') or 'job'} cancelled")
    # 2) a pending job waiting in the panel (not started yet)
    pend = _pending.pop(uid, None)
    if pend and not done:
        done.append("✖️ Pending video cleared")
    # 3) a premium-login flow
    st = _login.pop(uid, None)
    if st:
        if st.get("client"):
            try:
                await st["client"].disconnect()
            except Exception:
                pass
        if not done:
            done.append("✖️ Login cancelled")
    return done


@app.on_message(filters.command("cancel") & filters.private)
async def _cancel(_, m: Message):
    done = await _cancel_everything(m.from_user.id)
    await m.reply("\n".join(done) if done else "Nothing to cancel.")



@app.on_message(filters.command(["dub", "dubsync"]) & filters.private)
async def _dub_cmd(_, m: Message):
    if not _allowed(m.from_user.id):
        return await m.reply(f"⛔ This bot is private.\nYour ID is "
                             f"`{m.from_user.id}` — send it to the owner.")
    await _dubflow_start(m.from_user.id, m)


@app.on_message(filters.command(["myid", "id"]) & filters.private)
async def _myid(_, m: Message):
    await m.reply(f"Your Telegram ID: `{m.from_user.id}`\n"
                  "Send this to the owner to be granted access.")


@app.on_message(filters.command(["allow", "adduser", "authorize"]) & filters.private)
async def _allow_user(_, m: Message):
    if not _is_owner(m.from_user.id):
        return await m.reply("⛔ Owner only.")
    ids = _parse_ids(m)
    ids = [i for i in ids if i != settings.owner_id]
    if not ids:
        return await m.reply("Usage: `/allow 123456789`\n"
                             "(or reply to / forward a message from the user, then `/allow`)")
    s = _load_allowed()
    s.update(ids)
    _save_allowed(s)
    await m.reply("✅ Authorized: " + ", ".join(f"`{i}`" for i in ids) +
                  f"\n👥 Total authorized users: {len(s)}")


@app.on_message(filters.command(["deny", "remove", "revoke", "block"]) & filters.private)
async def _deny_user(_, m: Message):
    if not _is_owner(m.from_user.id):
        return await m.reply("⛔ Owner only.")
    ids = _parse_ids(m)
    if not ids:
        return await m.reply("Usage: `/deny 123456789`")
    s = _load_allowed()
    removed = [i for i in ids if i in s]
    s.difference_update(ids)
    _save_allowed(s)
    await m.reply(("🚫 Removed: " + ", ".join(f"`{i}`" for i in removed)
                   if removed else "None of those were on the list.") +
                  f"\n👥 Total authorized users: {len(s)}")


@app.on_message(filters.command(["users", "allowed", "authorized"]) & filters.private)
async def _list_users(_, m: Message):
    if not _is_owner(m.from_user.id):
        return await m.reply("⛔ Owner only.")
    s = _load_allowed()
    lst = "\n".join(f"• `{i}`" for i in sorted(s)) or "_(none yet)_"
    await m.reply(f"👥 **Authorized users** (plus you, the owner `{settings.owner_id}`):\n"
                  f"{lst}\n\n`/allow <id>` add · `/deny <id>` remove\n"
                  "Tell a new user to send `/myid` to get their ID.")


@app.on_message(filters.command(["files", "pending", "outbox"]) & filters.private)
async def _files_cmd(_, m: Message):
    uid = m.from_user.id
    if not _allowed(uid):
        return
    lst = [e for e in _load_pending().get(str(uid), []) if os.path.exists(e.get("path", ""))]
    if not lst:
        return await m.reply("✅ No files waiting — everything's been delivered.")
    total = sum(e.get("size", 0) for e in lst)
    body = "\n".join(f"• {e['name']} — {human_size(e.get('size', 0))}" for e in lst)
    await m.reply(f"💾 **{len(lst)} file(s) saved on the server** ({human_size(total)} total):\n"
                  f"{body}\n\nSend /deliver to send them (after freeing MEGA or /loginpremium).")


@app.on_message(filters.command(["deliver", "getfiles", "resend"]) & filters.private)
async def _deliver_cmd(_, m: Message):
    uid = m.from_user.id
    if not _allowed(uid):
        return
    lst = [e for e in _load_pending().get(str(uid), []) if os.path.exists(e.get("path", ""))]
    if not lst:
        return await m.reply("No files waiting to deliver.")
    await m.reply(f"📤 Delivering {len(lst)} saved file(s)…")
    for e in lst:
        status = await m.reply(f"📦 {e['name']} ({human_size(e.get('size', 0))})…")
        if await _deliver_file(uid, e, status, m):
            _remove_pending(uid, e["path"])
            try:
                os.remove(e["path"])
            except OSError:
                pass
            try:
                await status.delete()
            except Exception:
                pass
    left = len([e for e in _load_pending().get(str(uid), []) if os.path.exists(e.get("path", ""))])
    await m.reply("✅ All delivered." if left == 0
                  else f"⚠️ {left} still couldn't send — free MEGA space or /loginpremium, then /deliver again.")


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


def _bar(pct: float, width: int = 12) -> str:
    """A text progress bar: ▰▰▰▰▱▱▱▱  42%"""
    pct = max(0.0, min(100.0, pct))
    filled = int(round(pct / 100 * width))
    return "▰" * filled + "▱" * (width - filled) + f"  {pct:3.0f}%"


class _Throttle:
    """Limit how often we edit the status message (Telegram rate-limits edits)."""
    def __init__(self, min_pct: float = 5.0, min_sec: float = 3.0):
        self.min_pct, self.min_sec = min_pct, min_sec
        self.last_pct, self.last_t = -100.0, 0.0

    def ok(self, pct: float) -> bool:
        now = time.time()
        if pct >= 100 or (pct - self.last_pct >= self.min_pct
                          and now - self.last_t >= self.min_sec):
            self.last_pct, self.last_t = pct, now
            return True
        return False


def _enqueue(uid: int, m: Message) -> None:
    """Collect an incoming file/link. Becomes a BATCH if more than one arrives —
    whether in a quick burst (debounce) OR slowly one-after-another (a 2nd file
    landing while the 1st's panel is still waiting converts both to a batch).
    This is what makes 'send the whole series at once' work even though Telegram
    uploads the files one at a time, seconds apart."""
    if _batch.get(uid) is not None:           # batch panel already up -> add to it
        _batch[uid].append(m)
        asyncio.create_task(_refresh_batch_panel(uid))
        return
    pend = _pending.get(uid)                  # a single is waiting -> convert to batch
    if pend is not None:
        _pending.pop(uid, None)
        _batch[uid] = [pend["msg"], m]
        asyncio.create_task(_show_batch_panel(uid, m))
        return
    _queue.setdefault(uid, []).append(m)
    tm = _qtimer.get(uid)
    if tm:
        tm.cancel()
    _qtimer[uid] = asyncio.create_task(_flush_after(uid))


async def _flush_after(uid: int) -> None:
    try:
        await asyncio.sleep(4.0)              # wait for the whole burst to arrive
    except asyncio.CancelledError:
        return
    _qtimer.pop(uid, None)
    msgs = _queue.pop(uid, [])
    if not msgs:
        return
    if len(msgs) == 1:
        await _intake_single(uid, msgs[0])
    else:
        _batch[uid] = msgs
        await _show_batch_panel(uid, msgs[0])


async def _intake_single(uid: int, m: Message) -> None:
    """One file -> download + show the normal render panel. A placeholder marks
    the slot immediately so a 2nd file arriving mid-download still converts us to
    a batch (see _enqueue)."""
    _pending[uid] = {"msg": m, "collecting": True}
    status = await m.reply("⬇️ Downloading…")
    try:
        job = await _build_job(uid, m, status)
    except Exception as e:
        _pending.pop(uid, None)
        if _active.get(uid, {}).get("cancelled"):
            await status.edit("🛑 Download cancelled.")
        else:
            log.exception("download/probe failed")
            await status.edit(f"❌ Failed: `{str(e)[:300]}`")
        return
    # a 2nd file may have converted us to a batch while downloading
    if not (_pending.get(uid) or {}).get("collecting"):
        try:
            await status.delete()
        except Exception:
            pass
        return
    _pending[uid] = job
    text, kb = panel(uid, job)
    await status.edit(text, reply_markup=kb)


def _batch_panel_text(uid: int, n: int) -> str:
    c = user_cfg(uid)
    res = "Source" if c["width"] == 0 else f"{c['width']}×{c['height']}"
    return (f"📦 **{n} videos queued**\n"
            f"🟥 Cover: {c['cover_mode']}  •  🖼 {res}  •  🎞 {c['fps']}fps\n"
            f"📝 `{c['scroll_text']}`\n\n"
            f"They'll be branded **one-by-one automatically**. Pick a preset to "
            f"apply to ALL + start, or render all with current settings.\n"
            f"Send more files to add them. `/cancel` stops the batch.")


def _batch_panel_kb(uid: int, n: int) -> IKM:
    rows = []
    tpls = list(get_templates(uid))
    if tpls:
        rows.append([IKB(f"🎬 {x}", f"btpl:{x}") for x in tpls[:3]])
    if n == 2:
        # Exactly two files is the shape of an HD + Somali-dub pair. Offered as
        # a choice rather than assumed — two files to brand is still valid.
        rows.append([IKB("🎬 Dub-sync these two", "bdub")])
    rows += [[IKB(f"✅ Render all ({n})", "bgo")], [IKB("❌ Clear queue", "bclear")]]
    return IKM(rows)


# Not a cap — downloads go over MTProto, which has no 2 GB ceiling (that is
# the HTTP Bot API's limit). Purely the size past which the panel warns the
# user the download will be slow.
FASTDL_WORKERS = int(os.getenv("FASTDL_WORKERS", "8"))
BOT_DL_LIMIT = int(1.95 * 1024 ** 3)


class _DubProgress:
    """The whole job in one message: phase checklist + overall + ETA."""

    PHASES = [
        ("dl_hd",   "Download HD"),
        ("dl_dub",  "Download dub"),
        ("engine",  "Conforming"),
        ("upload",  "Delivering"),
    ]
    WEIGHT = {"dl_hd": 0.14, "dl_dub": 0.14, "engine": 0.62, "upload": 0.10}

    def __init__(self, status: Message, title: str):
        self.status = status
        self.title = title
        self.pct = {k: 0.0 for k, _ in self.PHASES}
        self.note = {k: "" for k, _ in self.PHASES}
        self.stage_label = ""
        self.active = ""        # phase currently running, even at 0%
        self.started = time.time()
        # Trailing samples of (timestamp, overall%) for a windowed rate. A
        # single average since start cannot survive stages whose real cost
        # varies with what is cached.
        self._samples: list[tuple[float, float]] = []
        self._thr = _Throttle()
        self._last = ""

    def overall(self) -> float:
        return sum(self.pct[k] * self.WEIGHT[k] for k, _ in self.PHASES)

    def _elapsed(self) -> str:
        el = int(time.time() - self.started)
        return f"{el // 60}m {el % 60:02d}s" if el >= 60 else f"{el}s"

    def _eta(self) -> str:
        """Elapsed always; a projection only once the bar means something.

        Below 10% the sample is too short to extrapolate from — that is what
        produced "~8 min left" on a job with 40 minutes to run.
        """
        now = time.time()
        done = self.overall()
        base = f"⏱ {self._elapsed()} elapsed"

        # Keep ~6 minutes of history, sampled sparsely.
        if not self._samples or now - self._samples[-1][0] >= 20:
            self._samples.append((now, done))
            cutoff = now - 360
            while len(self._samples) > 2 and self._samples[0][0] < cutoff:
                self._samples.pop(0)

        # No rate for the thing currently running means no honest projection:
        # with both downloads done the bar reads 28% before the engine has
        # emitted a single number, and extrapolating that is how "~8 min left"
        # appeared on a job with forty minutes to run.
        if done < 10 or (self.active and self.pct.get(self.active, 0.0) <= 0.0):
            return base

        t0, p0 = self._samples[0]
        span, gained = now - t0, done - p0
        if span < 45 or gained <= 0.05:
            # Either too little history, or the bar has stalled — a stalled bar
            # cannot produce a number, and guessing is what caused the "~2 min
            # left" that sat there for twenty minutes.
            return base
        left = (100 - done) * span / gained
        if left < 90:
            return f"{base} · ~{int(left)}s left"
        return f"{base} · ~{int(left // 60)} min left"

    def _render(self) -> str:
        rows = []
        for key, label in self.PHASES:
            v = self.pct[key]
            extra = f"  {self.note[key]}" if self.note[key] else ""
            if v >= 100:
                rows.append(f"✅ {label}{extra}")
            elif v > 0 or key == self.active:
                # A started phase reads ⏳ even at 0% — `analyze` reports no
                # numbers for its first ten minutes and must not look idle.
                lbl = self.stage_label if key == "engine" and self.stage_label else label
                rows.append(f"⏳ {lbl}\n`{_bar(v)}`{extra}")
            else:
                rows.append(f"⬜ {label}")
        return (f"🎬 **Dub-sync** · `{self.title}`\n"
                + "\n".join(rows)
                + f"\n\n**Overall** `{_bar(self.overall())}`\n{self._eta()}")

    async def set(self, key: str, pct: float, note: str = "",
                  label: str = "", force: bool = False):
        self.pct[key] = max(0.0, min(100.0, pct))
        if self.pct[key] < 100:
            self.active = key
        elif self.active == key:
            self.active = ""
        if note:
            self.note[key] = note
        if label:
            self.stage_label = label
        if not force and not self._thr.ok(self.overall()):
            return
        txt = self._render()
        if txt == self._last:
            return
        self._last = txt
        try:
            await self.status.edit(txt, reply_markup=IKM([[IKB("🛑 Cancel", "cancel")]]))
        except Exception:
            pass


def _vmeta(m: Message) -> tuple[str, int, int, float]:
    """Name/size/duration straight from Telegram — no download needed."""
    v = m.video or m.document
    name = (getattr(v, "file_name", None) or "video.mp4")
    w = int(getattr(v, "width", 0) or 0)
    h = int(getattr(v, "height", 0) or 0)
    dur = float(getattr(v, "duration", 0) or 0)
    return name, w, h, dur


DUB_ASK_HD = (
    "🎬 **Dub-sync**\n\n"
    "Step 1 of 2 — send the **HD master** (the clean high-quality video).\n\n"
    "_Forward it here, or paste a MEGA link._"
)
DUB_ASK_DUB = (
    "✅ HD received: `{name}`  ·  {res}\n\n"
    "Step 2 of 2 — now send the **Somali dub** (the StreamNxt/FANPROJ version).\n\n"
    "_Forward it here, or paste a MEGA link._"
)


def _dubflow_kb() -> IKM:
    return IKM([[IKB("❌ Cancel", "dubflow:cancel")]])


async def _dubflow_start(uid: int, m: Message) -> None:
    _dubflow[uid] = {"step": "hd", "hd": None, "dub": None}
    _dubflow[uid]["prompt"] = await m.reply(DUB_ASK_HD, reply_markup=_dubflow_kb())


async def _dubflow_take(uid: int, m: Message) -> bool:
    """Consume a file for the guided flow. True if it was taken."""
    fl = _dubflow.get(uid)
    if not fl:
        return False
    name, w, h, _d = _vmeta(m)
    res = f"{w}×{h}" if w and h else "resolution unknown"
    if fl["step"] == "hd":
        fl["hd"] = m
        fl["step"] = "dub"
        try:
            await fl["prompt"].edit(DUB_ASK_DUB.format(name=name[:40], res=res),
                                    reply_markup=_dubflow_kb())
        except Exception:
            fl["prompt"] = await m.reply(
                DUB_ASK_DUB.format(name=name[:40], res=res),
                reply_markup=_dubflow_kb())
        return True

    fl["dub"] = m
    _dubflow.pop(uid, None)
    msgs = [fl["hd"], fl["dub"]]
    # The user told us which is which, so trust that ordering rather than
    # guessing from resolution — Swap on the confirm panel is still there if
    # they sent them the wrong way round.
    _dubsel[uid] = {"msgs": msgs, "hd_i": 0, "brand": True, "panel": None}
    try:
        panel = await fl["prompt"].edit(_dub_panel_text(uid),
                                        reply_markup=_dub_panel_kb(uid))
        _dubsel[uid]["panel"] = panel if hasattr(panel, "edit") else fl["prompt"]
    except Exception:
        _dubsel[uid]["panel"] = await m.reply(_dub_panel_text(uid),
                                              reply_markup=_dub_panel_kb(uid))
    return True


def _dub_size_warning(msgs: list) -> str:
    """Tell the user what a large input means for the wait — not a blocker.

    These files are already in Telegram, and downloads here go over MTProto,
    which has no 2 GB ceiling (that limit belongs to the HTTP Bot API). So a
    3 GB master downloads fine; it just takes a while, and the panel should say
    so rather than leaving someone staring at a bar. A MEGA link is the faster
    route when the file happens to be there too.
    """
    total = 0
    biggest = 0
    for m in msgs:
        v = m.video or m.document
        sz = int(getattr(v, "file_size", 0) or 0)
        total += sz
        biggest = max(biggest, sz)
    if total <= 0:
        return ""
    line = f"\n📥 To download: **{human_size(total)}**"
    if biggest > BOT_DL_LIMIT:
        line += ("\n   _Large file — this part can take a while. A MEGA link "
                 "downloads faster if you have one._")
    return line + "\n"


def _dub_panel_text(uid: int) -> str:
    sel = _dubsel.get(uid) or {}
    msgs = sel.get("msgs") or []
    if len(msgs) != 2:
        return "🎬 **Dub-sync** — send exactly 2 files."
    hi = sel.get("hd_i", 0)
    hd_n, hw, hh, hdur = _vmeta(msgs[hi])
    du_n, dw, dh, ddur = _vmeta(msgs[1 - hi])

    def line(tag, n, w, h, d):
        res = f"{w}×{h}" if w and h else "?"
        dur = f" · {int(d)//60}:{int(d)%60:02d}" if d else ""
        return f"{tag} `{n[:38]}`\n     {res}{dur}"

    c = user_cfg(uid)
    logos = []
    if c["bidhaan_on"]:
        logos.append(f"Bidhaan[{c['bidhaan_corner']}]")
    if c["bidhaan2_on"]:
        logos.append(f"Bidhaan[{c['bidhaan2_corner']}]")
    if c["streamnxt_on"]:
        logos.append(f"StreamNxt[{c['streamnxt_corner']}]")
    brand_on = sel.get("brand", True)
    if brand_on and (logos or c["scroll_text"]):
        bits = ", ".join(logos) or "no logo"
        cap = " + caption" if c["scroll_text"] else ""
        brand_line = f"🏷 Branding: {bits}{cap}  _(same encode)_"
    else:
        brand_line = "🏷 Branding: **off** — conform only"
    res = "source" if c["width"] == 0 else f"{c['width']}×{c['height']}"

    # ---- what comes out -------------------------------------------------
    # Output length tracks the DUB (that is the edit being conformed to), less
    # its own intro/promo, which is only measurable after analysis.
    out_dur = ddur or hdur or 0.0
    vk, br_label = _effective_bitrate(c, out_dur) if out_dur else (0, "—")
    vk, fit_note = _fit_bitrate(vk, out_dur, c["audio_k"])
    br_label += fit_note
    est = estimate_size_bytes(out_dur, vk, c["audio_k"]) if out_dur else 0
    if est > TG_LIMIT:
        if _premium_session() and est <= PREMIUM_LIMIT:
            deliver = "→ premium upload → **Saved Messages of the premium account**"
        elif delivery.mega_is_configured():
            deliver = "→ sent as a MEGA link"
        else:
            deliver = "⚠️ over 2GB — set /loginpremium or /megalogin first"
    else:
        deliver = "→ sent straight to Telegram"
    out_res = f"{hw}×{hh}" if c["width"] == 0 and hw else res
    result = (
        f"\n🎞 **After editing** _(estimate)_\n"
        f"     ~{_fmt_hms(out_dur)} · {out_res} · ~{human_size(est)}\n"
        f"     {deliver}\n"
    ) if out_dur else ""

    return (
        "🎬 **Ready to dub-sync**\n\n"
        + line("📺 **HD master**", hd_n, hw, hh, hdur) + "\n"
        + line("🗣 **Somali dub**", du_n, dw, dh, ddur) + "\n\n"
        + brand_line + "\n"
        + f"📐 Output: {res} · {br_label}\n"
        + _dub_size_warning(msgs)
        + result
        + "\n_The dub's own intro and closing promo are removed automatically, so "
        "the film starts exactly where the dub's film starts — nothing the dub "
        "cut is added back._\n"
        "⚠️ Wrong way round? Tap **Swap**."
    )


def _dub_panel_kb(uid: int) -> IKM:
    """Same edit controls as the branding panel — they all edit user settings,
    so they apply to a dub render exactly as they do to a branding one.
    Cover is omitted: a clean HD master has no broadcaster banner to hide."""
    sel = _dubsel.get(uid) or {}
    brand_on = sel.get("brand", True)
    rows = [
        [IKB("⏱ Scroll time", "m:scroll"), IKB("🔁 Times", "m:times")],
        [IKB("📐 Bitrate", "m:br"), IKB("🎯 Target size", "m:size")],
        [IKB("🖼 Resolution", "m:res"), IKB("🎞 FPS", "m:fps")],
        [IKB("🏷 Logo positions", "m:logos")],
        [IKB("▶️ Start times (skip intro)", "m:starts")],
        [IKB("🔄 Swap HD ⇄ Dub", "dub:swap"),
         IKB(("🏷 Branding: ON" if brand_on else "🏷 Branding: OFF"), "dub:brand")],
        [IKB("✅ Start dub-sync", "dub:start"), IKB("❌ Cancel", "dub:cancel")],
    ]
    return IKM(rows)


def _dub_job_stub(uid: int) -> dict | None:
    """A job-shaped dict for the shared settings UI.

    `submenu()` never reads it; `panel()` only wants name/duration/w/h. Built
    from Telegram metadata so no download is needed to open a submenu.
    """
    sel = _dubsel.get(uid)
    if not sel or len(sel.get("msgs") or []) != 2:
        return None
    name, w, h, dur = _vmeta(sel["msgs"][sel.get("hd_i", 0)])
    return {"name": name, "w": w or 1280, "h": h or 720,
            "duration": dur or 0.0, "src": "", "work": "", "msg": sel["msgs"][0]}


async def _refresh_active_panel(cq, uid: int, job: dict) -> None:
    """Redraw whichever panel is open — dub or branding."""
    if _dubsel.get(uid):
        await cq.message.edit(_dub_panel_text(uid), reply_markup=_dub_panel_kb(uid))
    else:
        text, kb = panel(uid, job)
        await cq.message.edit(text, reply_markup=kb)


async def _refresh_dub_panel(uid: int) -> None:
    sel = _dubsel.get(uid) or {}
    msg = sel.get("panel")
    if msg:
        try:
            await msg.edit(_dub_panel_text(uid), reply_markup=_dub_panel_kb(uid))
        except Exception:
            pass


async def _show_batch_panel(uid: int, m: Message) -> None:
    n = len(_batch.get(uid, []))
    _batch_panel[uid] = await m.reply(_batch_panel_text(uid, n),
                                      reply_markup=_batch_panel_kb(uid, n))


async def _refresh_batch_panel(uid: int) -> None:
    msg = _batch_panel.get(uid)
    n = len(_batch.get(uid, []))
    if msg and n:
        try:
            await msg.edit(_batch_panel_text(uid, n), reply_markup=_batch_panel_kb(uid, n))
        except Exception:
            pass


async def _run_batch(uid: int) -> None:
    msgs = _batch.pop(uid, [])
    _batch_panel.pop(uid, None)
    if not msgs:
        return
    _batch_cancel[uid] = False
    total = len(msgs)
    done = 0
    head = await msgs[0].reply(f"📦 **Batch started** — 0/{total} done.")
    for i, m in enumerate(msgs, 1):
        if _batch_cancel.get(uid):
            break
        status = await m.reply(f"📦 **{i}/{total}** — preparing…")
        try:
            job = await _build_job(uid, m, status)
            await _render_job(uid, job, status)
            if not _batch_cancel.get(uid):
                done += 1
        except Exception as e:
            if _act(uid).get("cancelled") or _batch_cancel.get(uid):
                pass
            else:
                log.exception("batch item failed")
                try:
                    await status.edit(f"❌ {i}/{total} failed: `{str(e)[:200]}`")
                except Exception:
                    pass
        try:
            tail = " — stopping…" if _batch_cancel.get(uid) else "…"
            await head.edit(f"📦 **Batch** — {done}/{total} done{tail}")
        except Exception:
            pass
    final = (f"🛑 Batch stopped — {done}/{total} done."
             if _batch_cancel.get(uid) else f"✅ **Batch finished** — {done}/{total} branded.")
    try:
        await head.edit(final)
    except Exception:
        pass
    _batch_cancel.pop(uid, None)


@app.on_message(filters.private & filters.text
                & filters.regex(r"mega(?:\.co)?\.nz/"), group=-1)
async def _on_mega_link(_, m: Message):
    """Paste a MEGA link (or several) -> queued; downloaded server-side at full
    speed (~200 MB/s) when processed."""
    uid = m.from_user.id
    if not _allowed(uid) or uid in _login:
        return
    if not re.search(r"https?://mega(?:\.co)?\.nz/\S+", m.text):
        return
    if await _dubflow_take(uid, m):
        return
    _enqueue(uid, m)


@app.on_message((filters.video | filters.document) & filters.private)
async def _on_video(_, m: Message):
    uid = m.from_user.id
    if not _allowed(uid):
        return await m.reply(f"⛔ This bot is private.\nYour ID is `{uid}` — "
                             "send it to the owner to request access.")
    if m.document and not (m.document.mime_type or "").startswith("video"):
        return
    # A guided dub-sync takes priority; otherwise behave exactly as before.
    if await _dubflow_take(uid, m):
        return
    _enqueue(uid, m)


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
        done = await _cancel_everything(uid)
        try:
            await cq.message.edit("🛑 " + ("\n".join(done) if done
                                           else "Cancelled."))
        except Exception:
            pass
        return await cq.answer("Cancelled")

    # ---- batch queue controls (no _pending job needed) ----
    if data == "bclear":
        _batch.pop(uid, None)
        _batch_panel.pop(uid, None)
        await cq.message.edit("📦 Queue cleared.")
        return await cq.answer()

    if data == "bdub":
        msgs = _batch.get(uid) or []
        if len(msgs) != 2:
            return await cq.answer("Send exactly 2 files: the HD and the dub.",
                                   show_alert=True)
        _batch.pop(uid, None)
        _batch_panel.pop(uid, None)
        # Guess the HD by resolution from Telegram's own metadata — no download
        # needed to show the user what was picked. Size is NOT used: a 480p dub
        # can easily be the larger file.
        a, b = _vmeta(msgs[0]), _vmeta(msgs[1])
        hd_i = 0 if (a[1] * a[2]) >= (b[1] * b[2]) else 1
        _dubsel[uid] = {"msgs": msgs, "hd_i": hd_i, "brand": True, "panel": None}
        await cq.answer()
        panel = await cq.message.edit(_dub_panel_text(uid),
                                      reply_markup=_dub_panel_kb(uid))
        _dubsel[uid]["panel"] = panel if hasattr(panel, "edit") else cq.message
        return

    if data == "dubflow:begin":
        await cq.answer()
        return await _dubflow_start(uid, cq.message)

    if data == "open:settings":
        await cq.answer()
        return await cq.message.reply(
            "⚙️ Send **/settings** to view and change logos, caption and quality.")

    if data == "dubflow:cancel":
        _dubflow.pop(uid, None)
        await cq.message.edit("❌ Dub-sync cancelled.")
        return await cq.answer()

    if data.startswith("dub:"):
        act = data[4:]
        sel = _dubsel.get(uid)
        if not sel and act != "cancel":
            return await cq.answer("Session expired — send the two files again.",
                                   show_alert=True)
        if act == "cancel":
            _dubsel.pop(uid, None)
            await cq.message.edit("❌ Dub-sync cancelled.")
            return await cq.answer()
        if act == "swap":
            sel["hd_i"] = 1 - sel["hd_i"]
            await _refresh_dub_panel(uid)
            return await cq.answer("Swapped.")
        if act == "brand":
            sel["brand"] = not sel.get("brand", True)
            await _refresh_dub_panel(uid)
            return await cq.answer("Branding " + ("on" if sel["brand"] else "off"))
        if act == "start":
            msgs = sel["msgs"]
            hd_i = sel["hd_i"]
            brand = sel.get("brand", True)
            _dubsel.pop(uid, None)
            await cq.answer("Starting…")
            try:
                await cq.message.edit("🎬 **Dub-sync starting…**")
            except Exception:
                pass
            asyncio.create_task(_run_dubsync(uid, msgs, hd_i, brand))
            return
        return await cq.answer()

    if data == "bgo" or data.startswith("btpl:"):
        if not _batch.get(uid):
            return await cq.answer("Queue is empty.", show_alert=True)
        if data.startswith("btpl:"):
            name = data[5:]
            if not apply_template(uid, name):
                return await cq.answer("Preset not found.", show_alert=True)
        await cq.answer("Starting batch…")
        try:
            await cq.message.edit(f"📦 Processing {len(_batch.get(uid, []))} videos one-by-one…")
        except Exception:
            pass
        asyncio.create_task(_run_batch(uid))
        return

    if job is None and _dubsel.get(uid):
        # Dub mode has no _pending job, but the shared settings UI expects one.
        job = _dub_job_stub(uid)
    if job is None:
        return await cq.answer("Session expired — send the video again.", show_alert=True)

    # navigation
    if data == "m:main":
        await _refresh_active_panel(cq, uid, job)
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
        elif key in ("logo_start_min", "cover_start_min", "text_start_min"):
            set_user(uid, **{key: float(val)})
            await cq.message.edit_reply_markup(submenu("starts", uid, job))
            return await cq.answer("✓")
        elif key == "res":
            if val == "source":
                set_user(uid, width=0, height=0)
            else:
                w, h = val.split("x")
                set_user(uid, width=int(w), height=int(h))
        await _refresh_active_panel(cq, uid, job)
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

    if data.startswith("tpl:"):
        name = data[4:]
        if not apply_template(uid, name):
            return await cq.answer("Preset not found.", show_alert=True)
        await cq.answer(f"Applied '{name}' — starting…")
        await _do_render(cq, uid, job)
        return

    if data == "go":
        await cq.answer("Starting…")
        await _do_render(cq, uid, job)
        return


# ------------------------------------------------------------- dub-sync
def _brand_payload(uid: int) -> dict:
    """The user's CURRENT branding settings, in the shape dubsync expects.

    Deliberately the same fields the branding path builds its RenderConfig
    from, so whatever is configured with /settings is what the conform render
    burns in. Cover bars are omitted on purpose: they hide broadcaster banners
    burned into a StreamNxt-style source, and a clean HD master has none.
    """
    c = user_cfg(uid)
    sc = c["logo_scale"]
    logos = []
    if c["streamnxt_on"]:
        logos.append({"path": _asset(settings.logo_tr), "corner": c["streamnxt_corner"],
                      "frac": c["streamnxt_frac"] * sc,
                      "margin_x": c["streamnxt_mx"], "margin_y": c["streamnxt_my"]})
    if c["bidhaan_on"]:
        logos.append({"path": _asset(settings.logo_tl), "corner": c["bidhaan_corner"],
                      "frac": c["bidhaan_frac"] * sc,
                      "margin_x": c["bidhaan_mx"], "margin_y": c["bidhaan_my"]})
    if c["bidhaan2_on"]:
        logos.append({"path": _asset(settings.logo_tl), "corner": c["bidhaan2_corner"],
                      "frac": c["bidhaan2_frac"] * sc,
                      "margin_x": c["bidhaan2_mx"], "margin_y": c["bidhaan2_my"]})
    return {
        "logos": logos,
        "scroll_text": c["scroll_text"],
        "scroll_seconds": c["scroll_seconds"],
        "scroll_count": c["scroll_count"],
        "scroll_times": [mn * 60 for mn in c.get("scroll_times", [])],
        "caption_scale": c.get("caption_scale", 0.016),
        "logo_start": c.get("logo_start_min", 0.0) * 60,
        "text_start": c.get("text_start_min", 0.0) * 60,
    }


async def _run_dubsync(uid: int, msgs: list, hd_i: int = 0,
                       brand: bool = True) -> None:
    """Conform an HD master to a Somali dub, branded in the same single pass."""
    import dubsync_job

    status = await msgs[0].reply("🎬 **Dub-sync** — preparing…")
    _active[uid] = {"proc": None, "cancelled": False, "phase": "Dub-sync",
                    "task": asyncio.current_task()}
    prog = _DubProgress(status, dubsync_job._slug(_vmeta(msgs[hd_i])[0]))
    await prog.set("dl_hd", 0, force=True)
    jobs = []
    try:
        for i, m in enumerate(msgs):
            key = "dl_hd" if i == hd_i else "dl_dub"
            jobs.append(await _build_job(uid, m, status, prog=prog, key=key))
            await prog.set(key, 100, note=human_size(os.path.getsize(jobs[-1]["src"])),
                           force=True)

        # The user confirmed (and could correct) the pairing on the panel, so
        # honour that rather than re-guessing from the downloaded files.
        hd_job, dub_job = jobs[hd_i], jobs[1 - hd_i]
        hd_src, dub_src = Path(hd_job["src"]), Path(dub_job["src"])
        title = dubsync_job._slug(hd_job["name"])
        # Settings first: the proxy is capped at the render height, so there is
        # no point transcoding 1080p only to hand it to a 720p render.
        c = user_cfg(uid)
        ow = hd_job["w"] if c["width"] == 0 else c["width"]
        oh = hd_job["h"] if c["height"] == 0 else c["height"]

        await prog.set("engine", 0, label="🎞 Preparing master", force=True)

        async def on_prog(label: str, pct: float):
            await prog.set("engine", pct, label=label)

        # prepare_inputs now spawns ffmpeg/ffprobe with asyncio's own
        # subprocess machinery (like every stage below already does) instead
        # of the blocking `subprocess` module, so it runs directly here
        # rather than via to_thread — mixing the two subprocess styles in one
        # process is what left an HEVC proxy build permanently zombied.
        hd, dub = await dubsync_job.prepare_inputs(
            hd_src, dub_src, title, oh or 1080, log.info, on_prog)

        # The same bitrate the confirm panel quoted, so the delivered size
        # matches the estimate instead of ballooning under CRF + ultrafast.
        # Output length tracks the dub, which is what the panel measured.
        _dur = dub_job.get("duration") or 0.0
        _vk, _ = _effective_bitrate(c, _dur)
        _vk, _ = _fit_bitrate(_vk, _dur, c["audio_k"])
        res = await dubsync_job.run_dubsync(
            hd, dub, title, (_brand_payload(uid) if brand else None),
            width=ow, height=oh, crf=settings.x264_crf,
            bitrate_k=_vk,
            on_progress=on_prog,
            register=lambda pr: _act(uid).__setitem__("proc", pr),
            should_cancel=lambda: bool(_act(uid).get("cancelled")))

        if not res.ok or not res.path:
            if res.message == "cancelled" or _act(uid).get("cancelled"):
                return await status.edit("🛑 Dub-sync cancelled.")
            return await status.edit(f"❌ Dub-sync failed: `{res.message}`")

        sz = os.path.getsize(res.path)
        ow2, oh2, odur = await asyncio.to_thread(probe, str(res.path))
        cap = dubsync_job.summary_caption(title, res, odur, sz)
        name = f"dubsync_{os.path.basename(hd_job['name'])}"

        # Same protection the branding path gets: keep the finished file in the
        # outbox BEFORE attempting delivery, so a 2h render is never lost to a
        # full MEGA account or a missing premium session.
        os.makedirs(OUTBOX, exist_ok=True)
        saved = os.path.join(OUTBOX, f"{int(time.time())}_{uid}_{name}")
        await asyncio.to_thread(shutil.move, str(res.path), saved)
        entry = {"path": saved, "name": name, "cap": cap, "w": ow2, "h": oh2,
                 "dur": odur, "size": sz, "ts": time.time()}
        _add_pending(uid, entry)

        await prog.set("engine", 100, force=True)
        await prog.set("upload", 1, force=True)
        if await _deliver_file(uid, entry, status, msgs[0]):
            _remove_pending(uid, saved)
            try:
                os.remove(saved)
            except OSError:
                pass
            await status.delete()
        else:
            await status.edit(
                f"💾 **Saved on the server** ({human_size(sz)}) — nothing is lost.\n"
                f"Couldn't deliver now (over 2GB / MEGA full / no delivery set up). "
                f"Free space or /loginpremium, then **/deliver**. No re-render.")
    except asyncio.CancelledError:
        try:
            await status.edit("🛑 Dub-sync cancelled.")
        except Exception:
            pass
        raise
    except Exception as e:
        if _act(uid).get("cancelled"):
            try:
                await status.edit("🛑 Dub-sync cancelled.")
            except Exception:
                pass
        else:
            log.exception("dubsync failed")
            try:
                await status.edit(f"❌ Dub-sync failed: `{str(e)[:300]}`")
            except Exception:
                pass
    finally:
        _active.pop(uid, None)
        for j in jobs:
            try:
                shutil.rmtree(j["work"], ignore_errors=True)
            except Exception:
                pass


async def _build_job(uid: int, m: Message, status: Message,
                     prog=None, key: str = "") -> dict:
    """Download the file (Telegram video/doc OR a MEGA link in the message) to a
    FRESH work dir, probe it, return a job dict. Raises on failure/cancel."""
    work = _new_work()
    dest = os.path.join(work, "src.mp4")
    mo = re.search(r"https?://mega(?:\.co)?\.nz/\S+", (m.text or m.caption or ""))
    if mo:
        dlt = _Throttle()
        loop = asyncio.get_event_loop()

        def _cb(pct):
            if prog is not None and key:
                asyncio.run_coroutine_threadsafe(prog.set(key, pct, note="MEGA"), loop)
            elif dlt.ok(pct):
                asyncio.run_coroutine_threadsafe(
                    status.edit(f"⬇️ **Downloading from MEGA** (fast)\n`{_bar(pct)}`"), loop)
        _act(uid).update(proc=None, cancelled=False, phase="Download",
                     task=asyncio.current_task())
        try:
            path, name = await asyncio.to_thread(
                delivery.mega_download, mo.group(0), dest, _cb,
                lambda p: _act(uid).__setitem__("proc", p))
        finally:
            _act(uid).update(proc=None, phase="")
    else:
        dlt = _Throttle()

        async def _dlp(cur, tot):
            if not tot:
                return
            pct = cur / tot * 100
            if prog is not None and key:
                await prog.set(key, pct, note=f"{human_size(cur)}/{human_size(tot)}")
            elif dlt.ok(pct):
                try:
                    await status.edit(f"⬇️ **Downloading**\n`{_bar(pct)}`\n"
                                      f"{human_size(cur)} / {human_size(tot)}")
                except Exception:
                    pass
        # Parallel chunked download first: pyrogram uses one connection, and
        # Telegram throttles the connection rather than the file, so several
        # sessions pulling different byte ranges is several times faster. Falls
        # back to the ordinary download on anything unexpected — a slow file is
        # a nuisance, a failed job after twenty minutes is worse.
        path = None
        try:
            import fastdl
            _act(uid).update(phase="Download")
            path = await fastdl.fast_download(
                app, m, dest, workers=FASTDL_WORKERS, progress=_dlp)
            log.info("fast download OK: %s", dest)
        except Exception as e:
            log.info("fast download unavailable (%s) — using normal download",
                     str(e)[:120])
            path = None
        if not path:
            path = await m.download(file_name=dest, progress=_dlp)
        name = (getattr(m.video, "file_name", None)
                or getattr(m.document, "file_name", None) or "video.mp4")
    w, h, dur = await asyncio.to_thread(probe, path)
    return {"src": path, "work": work, "w": w, "h": h, "duration": dur,
            "name": name, "msg": m}


# ----------------------------------------------------------------- render
async def _deliver_file(uid: int, entry: dict, status: Message, reply_to: Message) -> bool:
    """Send one finished file (Telegram / premium / MEGA). Returns True on
    success. On failure it leaves the file in the outbox so it can be retried."""
    out = entry["path"]
    if not os.path.exists(out):
        _remove_pending(uid, out)
        try:
            await status.edit("⚠️ That file is no longer on the server.")
        except Exception:
            pass
        return False
    sz = os.path.getsize(out)
    cap, name = entry["cap"], entry["name"]
    ow, oh, odur = int(entry.get("w", 0)), int(entry.get("h", 0)), entry.get("dur", 0)
    try:
        if sz <= TG_LIMIT:
            ult = _Throttle()

            async def _ulp(cur, tot):
                if tot and ult.ok(cur / tot * 100):
                    try:
                        await status.edit(f"⬆️ **Uploading to Telegram**\n`{_bar(cur / tot * 100)}`")
                    except Exception:
                        pass
            await status.edit(f"⬆️ Uploading… ({human_size(sz)})")
            await reply_to.reply_video(out, duration=int(odur), width=ow, height=oh,
                                       supports_streaming=True, caption=cap, progress=_ulp)
            return True
        elif _premium_session() and sz <= PREMIUM_LIMIT:
            put = _Throttle()

            async def _pp(cur, tot):
                if tot and put.ok(cur / tot * 100):
                    try:
                        await status.edit("⬆️ **Uploading via premium**\n"
                                          f"`{_bar(cur / tot * 100)}`")
                    except Exception:
                        pass

            await status.edit(f"⬆️ {human_size(sz)} — uploading via premium…")
            where = await _premium_send(out, cap, int(odur), ow, oh,
                                        target_uid=uid, progress=_pp)
            if where != "your chat":
                await reply_to.reply(f"{cap}\n📥 Sent to {where}.")
            return True
        elif delivery.mega_is_configured():
            await status.edit(f"☁️ {human_size(sz)} — uploading to MEGA…")
            loop = asyncio.get_event_loop()
            megt = _Throttle(min_sec=3.0)

            def _mcb(pct):
                if megt.ok(pct):
                    asyncio.run_coroutine_threadsafe(
                        status.edit(f"☁️ **Uploading to MEGA**\n`{_bar(pct)}`"), loop)
            link = await asyncio.to_thread(delivery.mega_upload, out, name, _mcb)
            await reply_to.reply(f"{cap}\n📥 Too big for Telegram — **MEGA link:**\n{link}")
            return True
        else:
            return False    # no delivery method available right now
    except Exception as e:
        log.exception("delivery failed")
        try:
            await status.edit(f"⚠️ Delivery failed: `{str(e)[:200]}`")
        except Exception:
            pass
        return False


async def _do_render(cq: CallbackQuery, uid: int, job: dict):
    await _render_job(uid, job, cq.message)


async def _render_job(uid: int, job: dict, status: Message):
    """Scan + render + deliver ONE job. Up to MAX_RENDERS of these run at once
    (a semaphore), so different users' videos process simultaneously instead of
    waiting in a single line. Each job holds one slot for its scan+render."""
    if _render_sem.locked():
        try:
            await status.edit("⏳ In queue — other renders are running; yours starts shortly…")
        except Exception:
            pass
    async with _render_sem:
        c = user_cfg(uid)
        src, work, dur = job["src"], job["work"], job["duration"]
        try:
            # detection at render time (adaptive fps for long videos)
            events = []
            if c["cover_mode"] == "auto":
                dfps = max(0.15, min(1.0, 1800.0 / dur)) if dur > 0 else 1.0
                _scan = {"on": True}

                async def scan_poll():
                    t0 = time.time()
                    while _scan["on"]:
                        try:
                            await status.edit(
                                f"🔎 **Scanning for banners…**  ({int(time.time()-t0)}s)")
                        except Exception:
                            pass
                        await asyncio.sleep(5)
                sp = asyncio.create_task(scan_poll())
                try:
                    events = await asyncio.to_thread(
                        detect_ad_banners, src, work, dfps, settings.merge_gap)
                finally:
                    _scan["on"] = False
                    sp.cancel()
            else:
                await status.edit("⏭ Cover off — skipping scan, going straight to render.")

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
                caption_scale=c.get("caption_scale", 0.016),
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

            cov = f"  • {len(events)} banner(s)" if events else "  • logo + caption"

            async def poller():
                last = -1
                while True:
                    await asyncio.sleep(7)
                    p = int(prog["pct"])
                    if p != last and p < 100:
                        last = p
                        try:
                            await status.edit(f"🎬 **Rendering**{cov}\n`{_bar(p)}`")
                        except Exception:
                            pass

            pt = asyncio.create_task(poller())
            _act(uid).update(proc=None, cancelled=False, phase="Render",
                         task=asyncio.current_task())
            try:
                await asyncio.to_thread(
                    render, src, out, events, cfg,
                    lambda p: prog.__setitem__("pct", p),
                    lambda p: _act(uid).__setitem__("proc", p))
            finally:
                pt.cancel()

            ow, oh, odur = await asyncio.to_thread(probe, out)
            sz = os.path.getsize(out)
            cap = f"✅ Branded — {len(events)} banner(s) covered • {human_size(sz)}"
            name = f"branded_{os.path.basename(job['name'])}"

            # PRESERVE the finished file in a persistent outbox BEFORE trying to
            # deliver it — so it's NEVER lost if delivery fails (MEGA full, over
            # 2GB with no method set up, a crash, etc.). The user can free space /
            # set up delivery and run /deliver to get it, with no re-render.
            os.makedirs(OUTBOX, exist_ok=True)
            saved = os.path.join(OUTBOX, f"{int(time.time())}_{uid}_{name}")
            await asyncio.to_thread(shutil.move, out, saved)
            entry = {"path": saved, "name": name, "cap": cap, "w": ow, "h": oh,
                     "dur": odur, "size": sz, "ts": time.time()}
            _add_pending(uid, entry)

            if await _deliver_file(uid, entry, status, job["msg"]):
                _remove_pending(uid, saved)
                try:
                    os.remove(saved)
                except OSError:
                    pass
                await status.delete()
            else:
                await status.edit(
                    f"💾 **Saved on the server** ({human_size(sz)}) — your file is NOT "
                    f"lost.\nCouldn't deliver now (over 2GB / MEGA full / no delivery set "
                    f"up). Free MEGA space or run /loginpremium, then send **/deliver** to "
                    f"get it — no re-render needed.  (/files to see what's waiting.)")
        except Exception as e:
            if _act(uid).get("cancelled"):
                try:
                    await status.edit("🛑 Render cancelled.")
                except Exception:
                    pass
            else:
                log.exception("render failed")
                await status.edit(f"❌ Failed: `{str(e)[:300]}`")
        finally:
            _active.pop(uid, None)
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
