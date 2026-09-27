"""Read-only: list the newest N Saved Messages (id, date, kind, file, duration, size, text/links)."""
import asyncio
import sys

from pyrogram import Client


def env(k):
    for line in open("/opt/Streamnxt/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip("\"")


async def main(n):
    app = Client("john_ie", api_id=int(env("API_ID")), api_hash=env("API_HASH"), workdir="/opt/media-os/data")
    async with app:
        async for m in app.get_chat_history("me", limit=n):
            v = m.video or m.document or m.audio or m.voice or m.animation
            kind = ("video" if m.video else "doc" if m.document else "audio" if m.audio
                    else "voice" if m.voice else "anim" if m.animation else "photo" if m.photo else "text")
            name = getattr(v, "file_name", None) if v else None
            dur = int(getattr(v, "duration", 0) or 0) if v else 0
            size = round((getattr(v, "file_size", 0) or 0) / 1e6, 1) if v else 0
            txt = (m.caption or m.text or "").replace("\n", " | ")
            links = []
            for ent in (m.entities or []) + (m.caption_entities or []):
                if getattr(ent, "url", None):
                    links.append(ent.url)
            print(m.id, m.date.strftime("%m-%d %H:%M"), kind, name or "", (str(dur) + "s") if dur else "",
                  (str(size) + "MB") if size else "", txt[:300], ("LINKS:" + " ".join(links)) if links else "")


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 30))
