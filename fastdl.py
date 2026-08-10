"""Parallel chunked download from Telegram.

Pyrogram downloads a file over a single MTProto connection, which on this VPS
means a 3 GB master crawls. Telegram does not rate-limit the file itself — it
limits one connection — so opening several sessions to the media DC and pulling
different byte ranges at once multiplies throughput. Same principle as
`aria2c -x16` on an HTTP link, which is the method that already proved fast
here.

Written against pyrofork's own `Client.get_file` so the DC auth handling is
identical: a session on a foreign DC needs an exported auth imported into it,
otherwise every request comes back AUTH_KEY_UNREGISTERED.

Falls back to the ordinary download on any failure. A slow file is a nuisance;
a failed job after twenty minutes is worse, so this never becomes the only path.
"""
from __future__ import annotations

import asyncio
import os
from typing import Callable, Optional

from pyrogram import raw, utils
from pyrogram.file_id import FileId, FileType, ThumbnailSource
from pyrogram.session import Auth, Session

CHUNK = 1024 * 1024          # Telegram's max per request
DEFAULT_WORKERS = 8
MIN_PARALLEL_SIZE = 32 * 1024 * 1024   # below this the setup cost dominates


def _location(file_id: FileId):
    ft = file_id.file_type
    if ft == FileType.CHAT_PHOTO:
        if file_id.chat_id > 0:
            peer = raw.types.InputPeerUser(
                user_id=file_id.chat_id, access_hash=file_id.chat_access_hash)
        elif file_id.chat_access_hash == 0:
            peer = raw.types.InputPeerChat(chat_id=-file_id.chat_id)
        else:
            peer = raw.types.InputPeerChannel(
                channel_id=utils.get_channel_id(file_id.chat_id),
                access_hash=file_id.chat_access_hash)
        return raw.types.InputPeerPhotoFileLocation(
            peer=peer, photo_id=file_id.media_id,
            big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG)
    if ft == FileType.PHOTO:
        return raw.types.InputPhotoFileLocation(
            id=file_id.media_id, access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
            thumb_size=file_id.thumbnail_size)
    return raw.types.InputDocumentFileLocation(
        id=file_id.media_id, access_hash=file_id.access_hash,
        file_reference=file_id.file_reference,
        thumb_size=file_id.thumbnail_size)


async def _new_session(client, dc_id: int) -> Session:
    """A media session on `dc_id`, authorised the way pyrofork does it."""
    home_dc = await client.storage.dc_id()
    test_mode = await client.storage.test_mode()
    auth = (await Auth(client, dc_id, test_mode).create()
            if dc_id != home_dc else await client.storage.auth_key())
    session = Session(client, dc_id, auth, test_mode, is_media=True)
    await session.start()
    if dc_id != home_dc:
        # A freshly created key on a foreign DC is anonymous until an exported
        # auth from the home DC is imported into it.
        exported = await client.invoke(
            raw.functions.auth.ExportAuthorization(dc_id=dc_id))
        await session.invoke(
            raw.functions.auth.ImportAuthorization(
                id=exported.id, bytes=exported.bytes))
    return session


async def fast_download(
    client, message, dest: str,
    workers: int = DEFAULT_WORKERS,
    progress: Optional[Callable] = None,
) -> str:
    """Download `message`'s media to `dest` using `workers` connections.

    `progress(current, total)` may be a coroutine function. Returns the path.
    Raises on failure so the caller can fall back.
    """
    media = message.video or message.document or message.audio
    if media is None:
        raise ValueError("message carries no downloadable media")
    total = int(getattr(media, "file_size", 0) or 0)
    file_id = FileId.decode(media.file_id)
    location = _location(file_id)

    if total < MIN_PARALLEL_SIZE or workers <= 1:
        raise ValueError("too small to be worth parallelising")

    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    # Pre-size the file so every worker can seek straight to its own offset.
    with open(dest, "wb") as f:
        f.truncate(total)

    n = max(1, min(workers, (total + CHUNK - 1) // CHUNK))
    per = ((total + n - 1) // n + CHUNK - 1) // CHUNK * CHUNK   # 1 MB aligned
    done = 0
    lock = asyncio.Lock()
    sessions: list[Session] = []

    async def bump(k: int):
        nonlocal done
        async with lock:
            done += k
            if progress:
                r = progress(done, total)
                if asyncio.iscoroutine(r):
                    await r

    async def worker(idx: int, session: Session):
        start = idx * per
        end = min(start + per, total)
        if start >= end:
            return
        # Each worker owns its slice of the file and never touches another's.
        with open(dest, "r+b") as f:
            off = start
            while off < end:
                limit = min(CHUNK, end - off)
                # Telegram wants offset and limit 4 KB aligned; the last chunk
                # may exceed `end`, which is fine — we simply write less.
                req = raw.functions.upload.GetFile(
                    location=location, offset=off, limit=CHUNK)
                for attempt in range(4):
                    try:
                        chunk = await session.invoke(req, sleep_threshold=30)
                        break
                    except Exception:
                        if attempt == 3:
                            raise
                        await asyncio.sleep(1 + attempt)
                data = getattr(chunk, "bytes", b"")
                if not data:
                    break
                data = data[:limit]
                f.seek(off)
                f.write(data)
                off += len(data)
                await bump(len(data))
                if len(data) < limit:
                    break

    try:
        sessions = await asyncio.gather(
            *[_new_session(client, file_id.dc_id) for _ in range(n)])
        await asyncio.gather(*[worker(i, s) for i, s in enumerate(sessions)])
    finally:
        for s in sessions:
            try:
                await s.stop()
            except Exception:
                pass

    got = os.path.getsize(dest)
    if got < total:
        raise IOError(f"incomplete download: {got}/{total}")
    return dest
