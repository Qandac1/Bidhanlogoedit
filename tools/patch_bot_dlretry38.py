"""bot38: a download Telegram cut short is downloaded again before the bot reads it (10-16 Hope, 10-07 Harom Hara: the
file sat on another Telegram data centre, the login burst for it was refused - AUTH_BYTES_INVALID - the fast download
fell back to the normal one, which hit the same refusal, and an EMPTY src.mp4 went to ffprobe: "Dub-sync failed:
Command ffprobe ... returned non-zero exit status 1"; sent again minutes later, the same files worked).
Additive: a download that came out the size Telegram says it is goes on exactly as before (no new call, no wait).
    python3 patch_bot_dlretry38.py <bot dir>   -> PATCHED bot38 (refuses when bot.py is not the expected one)"""
import pathlib
import sys

d = pathlib.Path(sys.argv[1])
p = d / "bot.py"
s = p.read_text()

CALL_OLD = """        if not path:
            path = await m.download(file_name=dest, progress=_dlp)
        name = _derive_name(m)
"""
CALL_NEW = """        if not path:
            path = await m.download(file_name=dest, progress=_dlp)
        # bot38: a download Telegram cut short (another data centre refusing the login burst - AUTH_BYTES_INVALID,
        # 10-16 Hope / 10-07 Harom Hara: an empty src.mp4 reached ffprobe) is downloaded again before anything reads it
        path = await _complete_download(m, dest, path, _dlp)
        name = _derive_name(m)
"""
FUNC = '''async def _complete_download(m, dest, path, progress=None, waits=(5, 15, 30)):
    """bot38 (10-17): the file as Telegram has it, or a clear message - never a half file read as a film. A download
    that came out shorter than the file (or not at all) is downloaded again a few seconds later, up to three times,
    the partial file removed first. A file whose size Telegram does not give is taken as it came (as before)."""
    media = (getattr(m, "video", None) or getattr(m, "document", None) or getattr(m, "animation", None)
             or getattr(m, "audio", None))
    want = int(getattr(media, "file_size", 0) or 0)

    def size(x):
        try:
            return os.path.getsize(x) if x else -1
        except OSError:
            return -1

    def whole(x):
        n = size(x)
        return bool(x) and (n == want if want else n > 0)
    if whole(path):
        return path
    got = size(path)
    for k, wait in enumerate(waits):
        log.warning("download of %s came out at %s of %s bytes - downloading it again in %d s (try %d)",
                    dest, got, want, wait, k + 2)
        await asyncio.sleep(wait)
        try:
            os.remove(dest)
        except OSError:
            pass
        try:
            path = await m.download(file_name=dest, progress=progress)
        except Exception as e:  # noqa: BLE001 - any refusal: the next try, then the clear message
            log.warning("download try %d failed: %s", k + 2, str(e)[:160])
            path = None
        got = size(path)
        if whole(path):
            log.info("download complete on try %d: %s", k + 2, dest)
            return path
    raise RuntimeError("Telegram stopped the download of this file (%s of %s arrived, tried %d times) - nothing was "
                       "lost: send it again" % (human_size(max(0, got)), human_size(want), len(waits) + 1))


'''
ANCHOR = "async def _build_job("
if s.count(CALL_OLD) != 1 or s.count(ANCHOR) != 1 or "_complete_download" in s:
    sys.exit("bot.py is not the expected one (anchors %d/%d, already patched: %s) - nothing changed"
             % (s.count(CALL_OLD), s.count(ANCHOR), "_complete_download" in s))
s = s.replace(CALL_OLD, CALL_NEW).replace(ANCHOR, FUNC + ANCHOR)
p.write_text(s)
print("PATCHED bot38")
