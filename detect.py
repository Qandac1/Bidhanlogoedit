"""
Ad / phone-number banner detection.

The broadcaster banners John covers by hand (TRT red bar, Fanproj strip, the
red WhatsApp-number bars) share one strong signal: a saturated RED block, often
in the lower third, often wider than tall. We sample the video at a low fps,
find those red blocks per frame, optionally confirm with OCR digits, then merge
the per-frame hits into time intervals -> a "cover timeline".

Output coords are NORMALISED (0..1) so they're resolution-independent; the
branding pipeline scales them back to the output resolution.
"""
from __future__ import annotations

import os
import glob
import logging
import subprocess
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger("detect")

try:
    import pytesseract  # noqa
    _HAS_OCR = True
except Exception:  # pragma: no cover
    _HAS_OCR = False


@dataclass
class CoverEvent:
    start: float   # seconds
    end: float     # seconds
    x: float       # normalised 0..1 (left)
    y: float       # normalised 0..1 (top)
    w: float       # normalised 0..1 width
    h: float       # normalised 0..1 height

    def padded(self, px: float = 0.022, py: float = 0.02) -> "CoverEvent":
        """Grow the box a touch so the bar fully hides the banner edges."""
        x = max(0.0, self.x - px)
        y = max(0.0, self.y - py)
        w = min(1.0 - x, self.w + 2 * px)
        h = min(1.0 - y, self.h + 2 * py)
        return CoverEvent(self.start, self.end, x, y, w, h)


def _keyframe_times(video: str) -> list[float]:
    """Keyframe timestamps via ffprobe — fast, no decoding."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-skip_frame", "nokey",
         "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0", video],
        capture_output=True, text=True,
    ).stdout
    ts = []
    for line in out.splitlines():
        line = line.strip().rstrip(",")
        try:
            ts.append(float(line))
        except ValueError:
            pass
    return sorted(ts)


def _extract_keyframes(video: str, out_dir: str, width: int = 640) -> int:
    """Decode ONLY keyframes (decode-light) -> scaled JPEGs. Returns count."""
    os.makedirs(out_dir, exist_ok=True)
    for f in glob.glob(os.path.join(out_dir, "*.jpg")):
        os.remove(f)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-skip_frame", "nokey",
        "-i", video, "-vsync", "0", "-vf", f"scale={width}:-1",
        os.path.join(out_dir, "f_%06d.jpg"),
    ]
    subprocess.run(cmd, check=True)
    return len(glob.glob(os.path.join(out_dir, "*.jpg")))


def _find_red_banners(img: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Return normalised (x,y,w,h) boxes of saturated-red rectangular blocks."""
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # red wraps around hue 0/180 -> two ranges
    lower1 = cv2.inRange(hsv, (0, 90, 70), (10, 255, 255))
    lower2 = cv2.inRange(hsv, (170, 90, 70), (180, 255, 255))
    mask = cv2.bitwise_or(lower1, lower2)
    # close gaps so text/icons inside the bar don't split it
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    boxes: list[tuple[float, float, float, float]] = []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        nx, ny, nw, nh = x / W, y / H, w / W, h / H
        area_frac = nw * nh
        # --- shape: an ad bar is WIDE and SHORT, not a tall blob ---
        wide = nw >= 0.12
        short = 0.02 <= nh <= 0.28
        banner_aspect = (nw / nh) >= 2.2 if nh > 0 else False
        reasonable_area = 0.006 <= area_frac <= 0.22
        # --- zone: bottom strip (phone bars) or a top corner (channel bug) ---
        in_bottom = (ny + nh) >= 0.66
        in_top = ny <= 0.16
        in_zone = in_bottom or in_top
        # red fill density inside the box (reject sparse red speckle)
        sub = mask[y:y + h, x:x + w]
        dense = sub.size > 0 and (cv2.countNonZero(sub) / sub.size) >= 0.45
        if wide and short and banner_aspect and reasonable_area and in_zone and dense:
            boxes.append((nx, ny, nw, nh))
    return boxes


def _find_number_banners(img: np.ndarray) -> list[tuple[float, float, float, float]]:
    """OCR the lower half for phone-number-like digit runs (catches ad numbers
    even when the banner isn't strongly red). Returns normalised boxes covering
    the number, widened a little so the whole number is hidden."""
    if not _HAS_OCR:
        return []
    H, W = img.shape[:2]
    y0 = int(0.52 * H)
    region = img[y0:, :]
    boxes: list[tuple[float, float, float, float]] = []
    try:
        from pytesseract import Output
        data = pytesseract.image_to_data(region, config="--psm 11",
                                         output_type=Output.DICT)
    except Exception:
        return []
    for i, txt in enumerate(data["text"]):
        digits = sum(c.isdigit() for c in txt)
        if digits >= 4:                      # phone-number-ish
            x, y = data["left"][i], data["top"][i]
            w, h = data["width"][i], data["height"][i]
            # widen horizontally (numbers sit inside a wider bar)
            nx = max(0.0, (x - w * 0.4) / W)
            ny = max(0.0, (y + y0 - h * 0.4) / H)
            nw = min(1.0 - nx, (w * 1.8) / W)
            nh = min(1.0 - ny, (h * 1.8) / H)
            boxes.append((nx, ny, nw, nh))
    return boxes


def _has_digits(img: np.ndarray, box: tuple[float, float, float, float]) -> bool:
    """OCR a crop; True if it looks like it contains a phone-ish digit run."""
    if not _HAS_OCR:
        return True  # can't check -> don't veto
    H, W = img.shape[:2]
    x, y, w, h = box
    crop = img[int(y * H):int((y + h) * H), int(x * W):int((x + w) * W)]
    if crop.size == 0:
        return True
    try:
        txt = pytesseract.image_to_string(crop, config="--psm 6")
        digits = sum(ch.isdigit() for ch in txt)
        return digits >= 4
    except Exception:
        return True


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    return inter / (aw * ah + bw * bh - inter)


def detect_ad_banners(
    video: str,
    work_dir: str,
    fps: float = 1.0,
    merge_gap: float = 2.5,
    use_ocr: bool = True,
    min_duration: float = 3.0,
    min_coverage: float = 0.3,
) -> list[CoverEvent]:
    """Full pipeline: keyframe-sample -> detect -> merge into cover events.

    Scans only KEYFRAMES (decode-light) instead of decoding the whole video —
    ad banners persist for seconds so keyframe density is plenty, and this is
    dramatically faster on long (2h+) movies. `fps` is kept for signature compat
    but ignored; timing comes from the real keyframe timestamps.
    """
    frames_dir = os.path.join(work_dir, "frames")
    times = _keyframe_times(video)
    n = _extract_keyframes(video, frames_dir)
    files = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    m = min(len(files), len(times))
    files, times = files[:m], times[:m]
    if m < 2:
        log.info("detect: too few keyframes (%d)", m)
        return []
    spacing = max(0.5, (times[-1] - times[0]) / max(1, m - 1))
    # A recurring banner sits in the SAME spot but the sparse keyframe scan can
    # miss it between hits. Merge same-location detections across a generous gap
    # so the cover is CONTINUOUS over its active span — over-covering a fixed
    # bottom strip briefly is fine; leaking a phone number is not.
    merge_gap = max(merge_gap, 4.0 * spacing, 15.0)
    log.info("detect: %d keyframes, ~%.1fs apart, merge_gap=%.0fs", m, spacing, merge_gap)

    # per-timestamp detections; remember which boxes had digits (phone signal)
    dets: list[tuple[float, tuple[float, float, float, float], bool]] = []
    for idx, fp in enumerate(files):
        t = times[idx]
        img = cv2.imread(fp)
        if img is None:
            continue
        for box in _find_red_banners(img):
            has_dig = _has_digits(img, box) if use_ocr else True
            dets.append((t, box, has_dig))
        # OCR phone-number banners (non-red ad numbers) — always digit-backed
        if use_ocr:
            for box in _find_number_banners(img):
                dets.append((t, box, True))

    # cleanup frames to save disk
    for fp in files:
        try:
            os.remove(fp)
        except OSError:
            pass

    if not dets:
        log.info("detect: no ad banners found")
        return []

    # cluster into tracks by spatial overlap + temporal continuity
    tracks: list[dict] = []
    for t, box, has_dig in dets:
        placed = False
        for tr in tracks:
            if t - tr["last_t"] <= merge_gap and _iou(tr["box"], box) >= 0.4:
                tr["end"] = t
                tr["last_t"] = t
                tr["hits"] += 1
                tr["digits"] += int(has_dig)
                bx = min(tr["box"][0], box[0])
                by = min(tr["box"][1], box[1])
                bw = max(tr["box"][0] + tr["box"][2], box[0] + box[2]) - bx
                bh = max(tr["box"][1] + tr["box"][3], box[1] + box[3]) - by
                tr["box"] = (bx, by, bw, bh)
                placed = True
                break
        if not placed:
            tracks.append({"start": t, "end": t, "last_t": t, "box": box,
                           "hits": 1, "digits": int(has_dig)})

    events: list[CoverEvent] = []
    step = spacing
    for tr in tracks:
        dur = tr["end"] - tr["start"] + step
        span_frames = max(1, round((tr["end"] - tr["start"]) / spacing) + 1)
        coverage = tr["hits"] / span_frames
        # A real banner: lasts a while, is present in most frames of its span,
        # and (if OCR available) shows digits at least once.
        if dur < min_duration:
            continue
        if coverage < min_coverage:
            continue
        if _HAS_OCR and tr["digits"] == 0 and (tr["box"][2] * tr["box"][3]) < 0.05:
            continue
        x, y, w, h = tr["box"]
        events.append(CoverEvent(
            start=max(0.0, tr["start"] - step / 2),
            end=tr["end"] + step,
            x=x, y=y, w=w, h=h,
        ).padded())

    # --- Post-merge by horizontal band ---------------------------------
    # These broadcaster banners SLIDE in/out, so a single banner fragments into
    # several boxes at different x. Merge everything sharing a vertical band into
    # ONE continuous cover with the UNION box, spanning first->last appearance.
    # This is how John covers manually (one bar over the whole active segment)
    # and guarantees a sliding phone number can't leak between samples.
    LINK_GAP = 60.0

    def _voverlap(a: CoverEvent, b: CoverEvent) -> bool:
        top, bot = max(a.y, b.y), min(a.y + a.h, b.y + b.h)
        inter = max(0.0, bot - top)
        return inter / max(1e-6, min(a.h, b.h)) > 0.5

    events.sort(key=lambda e: e.start)
    bands: list[CoverEvent] = []
    for e in events:
        hit = next((b for b in bands
                    if _voverlap(e, b) and e.start <= b.end + LINK_GAP), None)
        if hit:
            nx, ny = min(hit.x, e.x), min(hit.y, e.y)
            nx2 = max(hit.x + hit.w, e.x + e.w)
            ny2 = max(hit.y + hit.h, e.y + e.h)
            hit.x, hit.y, hit.w, hit.h = nx, ny, nx2 - nx, ny2 - ny
            hit.start, hit.end = min(hit.start, e.start), max(hit.end, e.end)
        else:
            bands.append(CoverEvent(e.start, e.end, e.x, e.y, e.w, e.h))

    bands.sort(key=lambda e: e.start)
    log.info("detect: %d cover bands (from %d raw)", len(bands), len(events))
    return bands
