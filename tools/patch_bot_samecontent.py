"""A re-sent IDENTICAL file keeps the copy already in raw/, so the finished analysis is reused.
Bheemaa 2026-09-28: John re-sent the same HD + dub; prepare_inputs replaced raw/ with the new
download, its mtime changed, the engine's speed cache key (path|size|mtime) no longer matched,
the speed was re-measured and every HD-derived cache cleared -- 1.5 h of analysis redone. Same
content = same size and the same first and last 8 MB (sha256); anything else is replaced exactly
as before. Additive: a new guard next to the existing same-file guard.
Usage: python3 patch_bot_samecontent.py <dir with dubsync_job.py>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "_same_content" in s:
    raise SystemExit("already patched")


def rep(s, old, new, what):
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    return s.replace(old, new)


s = rep(s, '''        try:
            if dst.exists() and src.exists() and os.path.samefile(src, dst):
                continue
        except OSError:
            pass
        if dst.exists():
            dst.unlink()''', '''        try:
            if dst.exists() and src.exists() and os.path.samefile(src, dst):
                continue
        except OSError:
            pass
        # SAME-CONTENT GUARD: a re-sent identical file keeps the copy already in raw/ -- its
        # mtime is part of the engine's cache keys, so replacing it redid the whole analysis
        # (Bheemaa re-sent 2026-09-28: 1.5 h). Different content is replaced as before.
        try:
            if dst.exists() and src.exists() and _same_content(src, dst):
                continue
        except OSError:
            pass
        if dst.exists():
            dst.unlink()''', "guard")
s = rep(s, '''async def prepare_inputs(''', '''def _same_content(a: Path, b: Path, chunk: int = 8 * 1024 * 1024) -> bool:
    """Same size and the same first and last `chunk` bytes (sha256)."""
    sa, sb = os.path.getsize(a), os.path.getsize(b)
    if sa != sb:
        return False
    for off in (0, max(0, sa - chunk)):
        ha, hb = hashlib.sha256(), hashlib.sha256()
        with open(a, "rb") as fa, open(b, "rb") as fb:
            fa.seek(off)
            fb.seek(off)
            ha.update(fa.read(chunk))
            hb.update(fb.read(chunk))
        if ha.digest() != hb.digest():
            return False
    return True


async def prepare_inputs(''', "helper")
open(J, "w", encoding="utf-8").write(s)
print("patched", J)
