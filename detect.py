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
    digits: int = 0  # how many keyframes confirmed a phone number in this band

    def padded(self, px: float = 0.018, py: float = 0.012) -> "CoverEvent":
        """Grow the box just a touch so the bar matches the banner (covers the
        non-red edge) without over-covering — like a Wondershare bar placed on
        the number, not a big block."""
        x = max(0.0, self.x - px)
        y = max(0.0, self.y - py)
        w = min(1.0 - x, self.w + 2 * px)
        h = min(1.0 - y, self.h + 2 * py)
        return CoverEvent(self.start, self.end, x, y, w, h, self.digits)


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


def _max_digit_run(s: str) -> int:
    best = run = 0
    for ch in s:
        run = run + 1 if ch.isdigit() else 0
        best = max(best, run)
    return best


def _find_phone_boxes(img: np.ndarray) -> list[tuple[float, float, float, float]]:
    """OCR the lower half for REAL phone numbers (>=6 consecutive digits, e.g.
    0612001600). Strict on purpose — random OCR noise rarely yields a clean
    6-digit run, so this confirms 'there is a number here' without firing on
    promos/textures. Returns normalised boxes around the number."""
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
        if _max_digit_run(txt) >= 6:
            x, y = data["left"][i], data["top"][i]
            w, h = data["width"][i], data["height"][i]
            nx = max(0.0, (x - w * 0.4) / W)
            ny = max(0.0, (y + y0 - h * 0.5) / H)
            nw = min(1.0 - nx, (w * 1.8) / W)
            nh = min(1.0 - ny, (h * 2.0) / H)
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

    # per-timestamp detections: (t, box, has_phone, is_red). is_red boxes give
    # the TIGHT banner geometry; phone-only boxes are confirmation/fallback.
    dets: list = []
    for idx, fp in enumerate(files):
        t = times[idx]
        img = cv2.imread(fp)
        if img is None:
            continue
        red_boxes = _find_red_banners(img)
        phone_boxes = _find_phone_boxes(img) if use_ocr else []

        def _phone_here(b):
            for pb in phone_boxes:
                same_row = b[1] <= pb[1] + pb[3] * 0.5 <= b[1] + b[3]
                if _iou(b, pb) > 0.01 or same_row:
                    return True
            return False

        for rb in red_boxes:
            dets.append((t, rb, _phone_here(rb), True))
        for pb in phone_boxes:
            if not any(_iou(pb, rb) > 0.01 for rb in red_boxes):
                dets.append((t, pb, True, False))

    # cleanup frames to save disk
    for fp in files:
        try:
            os.remove(fp)
        except OSError:
            pass

    if not dets:
        log.info("detect: no ad banners found")
        return []

    import statistics as st

    def _box_from(boxes: list) -> tuple[float, float, float, float]:
        """Tight cover box that fits the actual banner: use only the RED banner
        boxes (phone-only boxes are confirmation, not geometry). UNION
        horizontally (covers the slide), MEDIAN vertically (banner row is
        constant -> ignores outliers). No bottom-snap, so it matches the bar."""
        reds = [b for b, is_red in boxes if is_red]
        use = reds if reds else [b for b, _ in boxes]
        x = min(b[0] for b in use)
        x2 = max(b[0] + b[2] for b in use)
        y = st.median([b[1] for b in use])
        y2 = st.median([b[1] + b[3] for b in use])
        return (x, y, x2 - x, y2 - y)

    # cluster into tracks by spatial overlap + temporal continuity; keep member
    # boxes (with red flag) so we can size the cover tightly later.
    tracks: list[dict] = []
    for t, box, has_dig, is_red in dets:
        placed = False
        for tr in tracks:
            if t - tr["last_t"] <= merge_gap and _iou(tr["rep"], box) >= 0.4:
                tr["end"] = t
                tr["last_t"] = t
                tr["hits"] += 1
                tr["digits"] += int(has_dig)
                tr["boxes"].append((box, is_red))
                tr["rep"] = box
                placed = True
                break
        if not placed:
            tracks.append({"start": t, "end": t, "last_t": t, "rep": box,
                           "boxes": [(box, is_red)], "hits": 1, "digits": int(has_dig)})

    LINK_GAP = 60.0

    # tracks -> events (filtered), carrying member boxes
    step = spacing
    raw: list[dict] = []
    for tr in tracks:
        dur = tr["end"] - tr["start"] + step
        span_frames = max(1, round((tr["end"] - tr["start"]) / spacing) + 1)
        if dur < min_duration or tr["hits"] / span_frames < min_coverage:
            continue
        raw.append({"start": max(0.0, tr["start"] - step / 2),
                    "end": tr["end"] + step, "digits": tr["digits"],
                    "boxes": tr["boxes"], "rep": _box_from(tr["boxes"])})

    # --- Post-merge by horizontal band (continuous cover over active span) ---
    def _voverlap(a, b) -> bool:
        top, bot = max(a[1], b[1]), min(a[1] + a[3], b[1] + b[3])
        return max(0.0, bot - top) / max(1e-6, min(a[3], b[3])) > 0.4

    raw.sort(key=lambda e: e["start"])
    bands: list[dict] = []
    for e in raw:
        hit = next((b for b in bands
                    if _voverlap(e["rep"], b["rep"]) and e["start"] <= b["end"] + LINK_GAP),
                   None)
        if hit:
            hit["boxes"] += e["boxes"]
            hit["start"] = min(hit["start"], e["start"])
            hit["end"] = max(hit["end"], e["end"])
            hit["digits"] += e["digits"]
            hit["rep"] = _box_from(hit["boxes"])
        else:
            bands.append(dict(e))

    # keep only bands with a confirmed phone number (drops red scene colour)
    if _HAS_OCR:
        kept = [b for b in bands if b["digits"] > 0]
        bands = kept if kept else bands

    out: list[CoverEvent] = []
    for b in bands:
        x, y, w, h = b["rep"]
        # Cover from the moment it arrives: extend the start back a little, and
        # snap to 0 if the banner shows up in the first few seconds (keyframe
        # sampling can miss the very start).
        start = max(0.0, b["start"] - 1.5 * spacing)
        if start < 6.0:
            start = 0.0
        out.append(CoverEvent(start, b["end"], x, y, w, h, b["digits"]).padded())
    out.sort(key=lambda e: e.start)
    log.info("detect: %d cover bands", len(out))
    return out
