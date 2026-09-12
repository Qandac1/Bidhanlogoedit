"""
Fast, lossless video trimming — stream copy (NO re-encode).

Cuts land on the nearest keyframe (typically well under a second off, and often
frame-exact at a scene cut), which is the standard trade for "instant, works on
every codec, never re-encodes". A 2 GB movie trims in a couple of seconds.

Modes (all times in SECONDS):
  head  : drop the first N seconds        -> keep [N, end]
  tail  : drop the last  N seconds        -> keep [0, dur-N]
  range : keep only [A, B]
  cut   : remove the middle [A, B], join the two remaining parts

Everything here is pure ffmpeg/ffprobe with no bot dependencies, so it is unit
testable on its own.
"""
from __future__ import annotations

import os
import json
import shutil
import tempfile
import subprocess


def duration(path: str) -> float:
    """Total seconds, or 0.0 if unknown."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, check=False,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _run(cmd: list, register=None) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True)
    if register:
        register(proc)
    _out, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("trim failed: " + (err or "")[-800:])


def fast_trim(src: str, out: str, start: float = 0.0, end: float | None = None,
              register=None) -> str:
    """Keep [start, end] by stream copy. start<=0 => from the beginning;
    end None/<=0 => to the very end."""
    cmd = ["ffmpeg", "-hide_banner", "-y"]
    if start and start > 0:
        cmd += ["-ss", f"{start:.3f}"]          # input seek: fast, keyframe snap
    cmd += ["-i", src]
    if end is not None and end > 0:
        length = end - (start if start and start > 0 else 0.0)
        if length <= 0:
            raise RuntimeError("trim range is empty")
        cmd += ["-t", f"{length:.3f}"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
            "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", out]
    _run(cmd, register)
    return out


def cut_middle(src: str, out: str, cut_start: float, cut_end: float,
               register=None) -> str:
    """Remove [cut_start, cut_end] and concat the surrounding parts (copy)."""
    dur = duration(src)
    cut_start = max(0.0, cut_start)
    cut_end = min(cut_end, dur) if dur else cut_end
    if cut_end <= cut_start:
        raise RuntimeError("cut section is empty")
    tmp = tempfile.mkdtemp(prefix="cut_")
    try:
        segs = []
        if cut_start > 0.1:
            a = os.path.join(tmp, "a.mp4")
            fast_trim(src, a, 0.0, cut_start, register)
            segs.append(a)
        if not dur or cut_end < dur - 0.1:
            b = os.path.join(tmp, "b.mp4")
            fast_trim(src, b, cut_end, None, register)
            segs.append(b)
        if not segs:
            raise RuntimeError("nothing left after the cut")
        if len(segs) == 1:
            shutil.move(segs[0], out)
            return out
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            for s in segs:
                f.write("file '%s'\n" % s.replace("'", "'\\''"))
        _run(["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0",
              "-i", lst, "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
              "-movflags", "+faststart", out], register)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def apply(src: str, out: str, mode: str, a: float, b: float,
          dur: float = 0.0, register=None) -> str:
    """Dispatch a trim spec (seconds) to the right operation. Returns out.
    Raises ValueError if the spec leaves nothing / is nonsensical."""
    if not dur:
        dur = duration(src)
    if mode == "head":
        if a <= 0:
            raise ValueError("nothing to cut")
        if dur and a >= dur:
            raise ValueError("that would remove the whole video")
        return fast_trim(src, out, start=a, end=None, register=register)
    if mode == "tail":
        if a <= 0:
            raise ValueError("nothing to cut")
        keep_to = (dur - a) if dur else 0
        if keep_to <= 0:
            raise ValueError("that would remove the whole video")
        return fast_trim(src, out, start=0.0, end=keep_to, register=register)
    if mode == "range":
        if b <= a:
            raise ValueError("end must be after start")
        if dur:
            b = min(b, dur)
        return fast_trim(src, out, start=a, end=b, register=register)
    if mode == "cut":
        if b <= a:
            raise ValueError("end must be after start")
        return cut_middle(src, out, a, b, register=register)
    raise ValueError("unknown trim mode: %r" % mode)
