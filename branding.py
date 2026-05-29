"""
The render engine. Takes a source video + cover timeline + branding config and
produces the final branded file in a SINGLE ffmpeg pass:

  * top-right logo   (StreamNxt)
  * top-left  logo   (Bidhaan TV)
  * scrolling caption (name + number) moving bottom -> up
  * red/black cover bar over every detected ad/number banner (per-interval)

Everything is one filter_complex so the video is decoded/encoded only once.
"""
from __future__ import annotations

import os
import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Callable

from detect import CoverEvent

log = logging.getLogger("branding")


@dataclass
class RenderConfig:
    logo_tr: str          # absolute path, top-right png
    logo_tl: str          # absolute path, top-left png
    cover_png: str        # absolute path, red/black bar png
    scroll_text: str
    x264_preset: str = "veryfast"
    x264_crf: int = 21
    out_height: int = 0   # 0 = keep source height
    scroll_speed: int = 70  # px / second
    logo_frac: float = 0.13  # logo width as fraction of output width


def probe(video: str) -> tuple[int, int, float]:
    """Return (width, height, duration_seconds)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", video],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    vs = next(s for s in data["streams"] if s.get("codec_type") == "video")
    w, h = int(vs["width"]), int(vs["height"])
    dur = float(data["format"].get("duration") or vs.get("duration") or 0)
    return w, h, dur


def _esc_text(t: str) -> str:
    """Escape a string for ffmpeg drawtext."""
    return (t.replace("\\", "\\\\")
             .replace(":", "\\:")
             .replace("'", "’")   # curly apostrophe — dodges quoting hell
             .replace("%", "\\%"))


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def build_filter(src_w: int, src_h: int, events: list[CoverEvent],
                 cfg: RenderConfig) -> str:
    """Construct the filter_complex string. Inputs are assumed to be:
       [0]=video [1]=logo_tr [2]=logo_tl [3]=cover_png"""
    if cfg.out_height and cfg.out_height < src_h:
        out_h = cfg.out_height
        out_w = int(round(src_w * out_h / src_h / 2) * 2)
    else:
        out_w, out_h = src_w, src_h

    logo_w = max(40, int(out_w * cfg.logo_frac))
    margin = max(8, int(out_w * 0.015))
    fontsize = max(18, int(out_h * 0.030))

    parts: list[str] = []

    # 0) base scale (forces a known output size; no-op if unchanged)
    parts.append(f"[0:v]scale={out_w}:{out_h}[base]")

    # 1) cover bars — split the cover png into one stream per event, scale each
    #    to its box, overlay with a time gate.
    cur = "base"
    if events:
        n = len(events)
        labels = "".join(f"[c{i}]" for i in range(n))
        parts.append(f"[3:v]split={n}{labels}" if n > 1 else "[3:v]null[c0]")
        for i, e in enumerate(events):
            bw = max(2, int(e.w * out_w))
            bh = max(2, int(e.h * out_h))
            bx = int(e.x * out_w)
            by = int(e.y * out_h)
            parts.append(f"[c{i}]scale={bw}:{bh}[cs{i}]")
            nxt = f"ov{i}"
            parts.append(
                f"[{cur}][cs{i}]overlay={bx}:{by}:"
                f"enable='between(t,{e.start:.2f},{e.end:.2f})'[{nxt}]"
            )
            cur = nxt

    # 2) logos: scale then overlay (top-left, top-right)
    parts.append(f"[1:v]scale={logo_w}:-1[ltr]")
    parts.append(f"[2:v]scale={logo_w}:-1[ltl]")
    parts.append(f"[{cur}][ltr]overlay=W-w-{margin}:{margin}[wtr]")
    parts.append(f"[wtr][ltl]overlay={margin}:{margin}[wtl]")

    # 3) scrolling caption bottom -> up (loops continuously)
    txt = _esc_text(cfg.scroll_text)
    parts.append(
        f"[wtl]drawtext=fontfile={FONT}:text='{txt}':"
        f"fontcolor=white:fontsize={fontsize}:borderw=2:bordercolor=black@0.9:"
        f"x=(w-text_w)/2:"
        f"y=h-mod(t*{cfg.scroll_speed}\\,h+text_h)[outv]"
    )
    return ";".join(parts)


def render(video: str, out_path: str, events: list[CoverEvent],
           cfg: RenderConfig,
           progress_cb: Callable[[float], None] | None = None) -> str:
    """Run the single-pass render. Calls progress_cb(percent 0..100)."""
    src_w, src_h, dur = probe(video)
    fc = build_filter(src_w, src_h, events, cfg)
    log.info("render: %dx%d %.0fs, %d cover events", src_w, src_h, dur, len(events))

    cmd = [
        "ffmpeg", "-hide_banner", "-y",
        "-i", video,
        "-i", cfg.logo_tr,
        "-i", cfg.logo_tl,
        "-i", cfg.cover_png,
        "-filter_complex", fc,
        "-map", "[outv]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", cfg.x264_preset, "-crf", str(cfg.x264_crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        out_path,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1)
    last = -5.0
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("out_time_ms=") and dur > 0:
            try:
                ms = int(line.split("=", 1)[1])
                pct = min(99.0, (ms / 1_000_000) / dur * 100)
                if progress_cb and pct - last >= 5:
                    progress_cb(pct)
                    last = pct
            except ValueError:
                pass
    proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err[-1500:]}")
    if progress_cb:
        progress_cb(100.0)
    return out_path
