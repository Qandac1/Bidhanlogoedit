"""
Bidhaan Logo-Edit bot.

Send it a video; it returns the same video branded exactly like John's Filmora
workflow — logos burned top-left/top-right, scrolling name+number caption, and
the broadcaster ad/phone-number banners auto-covered with the red/black bar.

One render at a time (encodes are heavy); progress is reported live.
"""
from __future__ import annotations

import os
import json
import time
import asyncio
import logging

import uvloop
from pyrogram import Client, filters
from pyrogram.types import Message

from config import settings
from branding import RenderConfig, render
from detect import detect_ad_banners

uvloop.install()
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
)
log = logging.getLogger("bot")

DATA_DIR = "/app/data"
SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")
_render_lock = asyncio.Lock()


# ------------------------------------------------------------------ settings
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
    return d.get(str(uid), {
        "scroll_text": settings.scroll_text,
        "cover_mode": "auto",          # auto | off
        "out_height": settings.out_height,
        "preset": settings.x264_preset,
    })


def set_user(uid: int, **kw) -> dict:
    d = _load()
    cur = d.get(str(uid), {})
    cur.update(kw)
    d[str(uid)] = cur
    _save(d)
    return cur


def _asset(name: str) -> str:
    return os.path.join(settings.assets_dir, name)


# ------------------------------------------------------------------ gate
def _allowed(uid: int) -> bool:
    return settings.owner_id == 0 or uid == settings.owner_id


# ------------------------------------------------------------------ app
app = Client(
    name="bidhaan_logoedit",
    api_id=settings.api_id,
    api_hash=settings.api_hash,
    bot_token=settings.bot_token,
    workdir=DATA_DIR,
    workers=20,
    sleep_threshold=60,
    max_concurrent_transmissions=8,
)

HELP = (
    "🎬 **Bidhaan Logo-Edit**\n\n"
    "Send me a **video** and I'll return it branded automatically:\n"
    "• StreamNxt logo top-right, Bidhaan TV top-left\n"
    "• Your scrolling caption (name + number) bottom→up\n"
    "• Ad / phone-number banners auto-covered with your red bar\n\n"
    "**Commands**\n"
    "/settings — show current settings\n"
    "/text `your caption` — set the scrolling caption\n"
    "/cover `auto`|`off` — toggle auto ad-covering\n"
    "/quality `source`|`720` — output size (720 = faster)\n"
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
    await m.reply(
        "⚙️ **Current settings**\n"
        f"• Caption: `{c['scroll_text']}`\n"
        f"• Auto-cover ads: `{c['cover_mode']}`\n"
        f"• Quality: `{'source' if not c['out_height'] else str(c['out_height'])+'p'}`\n"
        f"• Preset: `{c['preset']}`"
    )


@app.on_message(filters.command("text") & filters.private)
async def _text(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    if len(m.command) < 2:
        return await m.reply("Usage: `/text ugaar ah bidhaan tv 0619624090`")
    new = m.text.split(None, 1)[1].strip()
    set_user(m.from_user.id, scroll_text=new)
    await m.reply(f"✅ Caption set to:\n`{new}`")


@app.on_message(filters.command("cover") & filters.private)
async def _cover(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    arg = (m.command[1].lower() if len(m.command) > 1 else "")
    if arg not in ("auto", "off"):
        return await m.reply("Usage: `/cover auto` or `/cover off`")
    set_user(m.from_user.id, cover_mode=arg)
    await m.reply(f"✅ Auto-cover: `{arg}`")


@app.on_message(filters.command("quality") & filters.private)
async def _quality(_, m: Message):
    if not _allowed(m.from_user.id):
        return
    arg = (m.command[1].lower() if len(m.command) > 1 else "")
    if arg == "source":
        set_user(m.from_user.id, out_height=0)
    elif arg in ("720", "720p"):
        set_user(m.from_user.id, out_height=720)
    else:
        return await m.reply("Usage: `/quality source` or `/quality 720`")
    await m.reply(f"✅ Quality: `{arg}`")


@app.on_message((filters.video | filters.document) & filters.private)
async def _on_video(_, m: Message):
    uid = m.from_user.id
    if not _allowed(uid):
        return await m.reply("⛔ This bot is private.")

    # only treat documents that are actually video
    if m.document and not (m.document.mime_type or "").startswith("video"):
        return

    if _render_lock.locked():
        await m.reply("⏳ I'm rendering another video — yours is queued, hang on.")

    async with _render_lock:
        await _process(m)


async def _process(m: Message):
    uid = m.from_user.id
    c = user_cfg(uid)
    job = str(int(time.time()))
    work = os.path.join(settings.work_dir, job)
    os.makedirs(work, exist_ok=True)
    status = await m.reply("⬇️ Downloading…")

    try:
        src = await m.download(file_name=os.path.join(work, "src.mp4"))

        # 1) detect ad banners
        events = []
        if c["cover_mode"] == "auto":
            await status.edit("🔎 Scanning for ad / number banners…")
            events = await asyncio.to_thread(
                detect_ad_banners, src, work,
                settings.detect_fps, settings.merge_gap,
            )
            await status.edit(
                f"🔎 Found **{len(events)}** banner(s) to cover.\n🎨 Rendering… 0%"
            )
        else:
            await status.edit("🎨 Rendering… 0%")

        # 2) render (heavy) in a thread; progress polled via shared dict
        cfg = RenderConfig(
            logo_tr=_asset(settings.logo_tr),
            logo_tl=_asset(settings.logo_tl),
            cover_png=_asset(settings.cover_png),
            scroll_text=c["scroll_text"],
            x264_preset=c["preset"],
            x264_crf=settings.x264_crf,
            out_height=c["out_height"],
        )
        out = os.path.join(work, "branded.mp4")
        prog = {"pct": 0.0}

        def cb(p):
            prog["pct"] = p

        async def poller():
            last = -1
            while True:
                await asyncio.sleep(8)
                p = int(prog["pct"])
                if p != last and p < 100:
                    last = p
                    try:
                        await status.edit(
                            f"🎨 Rendering… {p}%  "
                            f"({len(events)} banner(s) covered)"
                        )
                    except Exception:
                        pass

        pt = asyncio.create_task(poller())
        try:
            await asyncio.to_thread(render, src, out, events, cfg, cb)
        finally:
            pt.cancel()

        # 3) upload
        await status.edit("⬆️ Uploading branded video…")
        await m.reply_video(
            out,
            caption=f"✅ Branded — {len(events)} banner(s) covered.",
        )
        await status.delete()

    except Exception as e:
        log.exception("job failed")
        await status.edit(f"❌ Failed: `{str(e)[:300]}`")
    finally:
        # cleanup work dir
        try:
            for root, _dirs, files in os.walk(work, topdown=False):
                for f in files:
                    os.remove(os.path.join(root, f))
                os.rmdir(root)
        except OSError:
            pass


if __name__ == "__main__":
    log.info("Bidhaan Logo-Edit bot starting…")
    app.run()
