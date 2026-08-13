"""
The render engine. Takes a source video + cover timeline + branding config and
produces the final branded file in a SINGLE ffmpeg pass:

  * logos at chosen corners (StreamNxt / Bidhaan TV)
  * scrolling caption (name + number) — choose travel-seconds + how many times it
    appears across the whole video
  * red/black cover bar over every detected ad/number banner (per-interval)

Encoding matches the Wondershare export: MP4 / H.264 / 25fps / target bitrate /
Rec.709, so file size is predictable (and can be auto-targeted to ~2 GB).
"""
from __future__ import annotations

import os
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Callable

from detect import CoverEvent

log = logging.getLogger("branding")

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

CORNERS = {
    "TL": "top-left",
    "TR": "top-right",
    "BL": "bottom-left",
    "BR": "bottom-right",
}


@dataclass
class Logo:
    path: str
    corner: str = "TR"      # TL | TR | BL | BR
    frac: float = 0.13      # width as fraction of output width
    margin_x: float = 0.015  # gap from the corner, fraction of width
    margin_y: float = 0.015  # gap from the corner, fraction of height


@dataclass
class RenderConfig:
    logos: list[Logo] = field(default_factory=list)
    cover_png: str = ""
    scroll_text: str = ""
    scroll_seconds: float = 25.0   # time the caption takes to travel bottom->up
    scroll_count: int = 8          # how many times it appears (even spread)
    scroll_times: list[float] = field(default_factory=list)  # exact start secs;
    #                              if set, overrides scroll_count
    caption_scale: float = 0.023   # caption font height as fraction of output h
    # per-element start times (seconds) — appear only after these (skip an intro)
    logo_start: float = 0.0
    cover_start: float = 0.0
    text_start: float = 0.0

    # output / encode (Wondershare-style)
    width: int = 1920
    height: int = 1080
    fps: int = 25
    video_bitrate_k: int = 2000    # kbps; if 0 -> CRF mode
    crf: int = 21
    audio_bitrate_k: int = 128
    preset: str = "veryfast"


# ----------------------------------------------------------------- helpers
def probe(video: str) -> tuple[int, int, float]:
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


def has_audio_stream(video: str) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", video],
        capture_output=True, text=True, check=False,
    )
    return bool(r.stdout.strip())


def verify_decodable(video: str, timeout: int = 1800) -> tuple[bool, str]:
    """Decode the whole file start to finish, keeping nothing — the cheapest
    real proof a delivered render isn't broken. Catches a corrupted segment,
    a bad concat join, or a truncated file that still reports a plausible
    duration, none of which a "did the pipeline exit 0" check would notice.
    `-v error` means any output at all is a genuine decode problem, not
    routine logging.
    """
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", video, "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"decode check itself hung past {timeout}s"
    if r.returncode != 0 or r.stderr.strip():
        return False, (r.stderr or "").strip()[-500:]
    return True, ""


def estimate_size_bytes(duration: float, video_bitrate_k: int,
                        audio_bitrate_k: int = 128) -> int:
    """Predicted output size, the way Wondershare shows it before export."""
    total_kbps = video_bitrate_k + audio_bitrate_k
    return int(total_kbps * 1000 / 8 * duration)


def bitrate_for_target(duration: float, target_bytes: int,
                       audio_bitrate_k: int = 128) -> int:
    """kbps video bitrate needed to land on `target_bytes`."""
    total_kbps = target_bytes * 8 / 1000 / max(1.0, duration)
    return max(200, int(total_kbps - audio_bitrate_k))


def human_size(b: int) -> str:
    gb = b / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    return f"{b / (1024 ** 2):.0f} MB"


def _esc_text(t: str) -> str:
    return (t.replace("\\", "\\\\")
             .replace(":", "\\:")
             .replace("'", "’")
             .replace("%", "\\%"))


def _corner_xy(corner: str, mx: int, my: int) -> str:
    return {
        "TL": f"{mx}:{my}",
        "TR": f"W-w-{mx}:{my}",
        "BL": f"{mx}:H-h-{my}",
        "BR": f"W-w-{mx}:H-h-{my}",
    }.get(corner, f"W-w-{mx}:{my}")


# ----------------------------------------------------------------- filter
def build_filter(src_w: int, src_h: int, duration: float,
                 events: list[CoverEvent], cfg: RenderConfig) -> str:
    out_w = cfg.width or src_w
    out_h = cfg.height or src_h
    margin = max(8, int(out_w * 0.015))
    fontsize = max(14, int(out_h * cfg.caption_scale))
    S_logo = max(0.0, cfg.logo_start)
    S_text = max(0.0, cfg.text_start)   # per-element start (skip intro)

    # skip the scale entirely when output == source (saves a full rescale pass)
    if out_w == src_w and out_h == src_h:
        parts: list[str] = ["[0:v]setsar=1[base]"]
    else:
        parts = ["[0:v]scale=%d:%d,setsar=1[base]" % (out_w, out_h)]

    # cover bars  ([1]=cover png)
    cur = "base"
    if events:
        n = len(events)
        labels = "".join(f"[c{i}]" for i in range(n))
        parts.append(f"[1:v]split={n}{labels}" if n > 1 else "[1:v]null[c0]")
        for i, e in enumerate(events):
            bw = max(2, int(e.w * out_w))
            bh = max(2, int(e.h * out_h))
            bx, by = int(e.x * out_w), int(e.y * out_h)
            parts.append(f"[c{i}]scale={bw}:{bh}[cs{i}]")
            parts.append(
                f"[{cur}][cs{i}]overlay={bx}:{by}:"
                f"enable='between(t,{e.start:.2f},{e.end:.2f})'[ov{i}]")
            cur = f"ov{i}"

    # logos — each scaled + placed at its corner with its own margins.
    for idx, lg in enumerate(cfg.logos):
        in_i = 2 + idx
        lw = max(40, int(out_w * lg.frac))
        mx, my = int(lg.margin_x * out_w), int(lg.margin_y * out_h)
        # format=rgba BEFORE scale keeps the alpha channel (else transparent
        # areas render as a black box).
        parts.append(f"[{in_i}:v]format=rgba,scale={lw}:-1[lg{idx}]")
        nxt = f"wl{idx}"
        parts.append(f"[{cur}][lg{idx}]overlay={_corner_xy(lg.corner, mx, my)}"
                     f":format=auto:enable='gte(t,{S_logo:.2f})'[{nxt}]")
        cur = nxt

    # scrolling caption (bottom -> up over scroll_seconds).
    txt = _esc_text(cfg.scroll_text)
    T = max(2.0, cfg.scroll_seconds)
    base = (f"drawtext=fontfile={FONT}:text='{txt}':fontcolor=white:"
            f"fontsize={fontsize}:borderw=2:bordercolor=black@0.9:x=(w-text_w)/2")
    if cfg.scroll_times:
        # EXACT minute marks the user chose: one pass at each time.
        ts = sorted(cfg.scroll_times)
        for i, start in enumerate(ts):
            lbl = "outv" if i == len(ts) - 1 else f"cap{i}"
            parts.append(
                f"[{cur}]{base}:"
                f"y='h-((t-{start:.2f})/{T:.3f})*(h+text_h)':"
                f"enable='between(t,{start:.2f},{start + T:.2f})'[{lbl}]")
            cur = lbl
    else:
        # N appearances evenly spread across the video AFTER the intro (S_text).
        n = max(1, cfg.scroll_count)
        span = max(T, (duration - S_text)) if duration > 0 else T
        period = max(T, span / n)
        parts.append(
            f"[{cur}]{base}:"
            f"y='h-(mod(t-{S_text:.2f},{period:.3f})/{T:.3f})*(h+text_h)':"
            f"enable='gte(t,{S_text:.2f})*lt(mod(t-{S_text:.2f},{period:.3f}),{T:.3f})'[outv]")
    return ";".join(parts)


# ----------------------------------------------------------------- render
def render(video: str, out_path: str, events: list[CoverEvent],
           cfg: RenderConfig,
           progress_cb: Callable[[float], None] | None = None,
           register: Callable[[object], None] | None = None) -> str:
    src_w, src_h, dur = probe(video)
    # gate cover bars by cover_start (skip the intro): drop banners that end
    # before it, clip the start of any that straddle it.
    if cfg.cover_start > 0:
        gated = []
        for e in events:
            if e.end <= cfg.cover_start:
                continue
            gated.append(CoverEvent(max(e.start, cfg.cover_start), e.end,
                                    e.x, e.y, e.w, e.h, e.digits))
        events = gated
    fc = build_filter(src_w, src_h, dur, events, cfg)
    log.info("render: %dx%d %.0fs -> %dx%d @%dfps, %dk, %d covers",
             src_w, src_h, dur, cfg.width, cfg.height, cfg.fps,
             cfg.video_bitrate_k, len(events))

    # [0]=video  [1]=cover png  [2..]=logos
    inputs = ["-i", video, "-i", cfg.cover_png]
    for lg in cfg.logos:
        inputs += ["-i", lg.path]

    cmd = ["ffmpeg", "-hide_banner", "-y", *inputs,
           "-filter_complex", fc,
           "-map", "[outv]", "-map", "0:a?",
           "-r", str(cfg.fps),
           "-c:v", "libx264", "-preset", cfg.preset,
           "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]

    if cfg.video_bitrate_k > 0:
        vk = cfg.video_bitrate_k
        cmd += ["-b:v", f"{vk}k", "-maxrate", f"{int(vk*1.5)}k",
                "-bufsize", f"{vk*2}k"]
    else:
        cmd += ["-crf", str(cfg.crf)]

    cmd += ["-c:a", "aac", "-b:a", f"{cfg.audio_bitrate_k}k",
            "-movflags", "+faststart",
            "-progress", "pipe:1", "-nostats", out_path]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1)
    if register:
        register(proc)   # let the caller hold the process so it can cancel it
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
