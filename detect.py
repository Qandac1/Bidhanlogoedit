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

    def padded(self, px: float = 0.015, py_top: float = 0.022,
               py_bot: float = 0.012) -> "CoverEvent":
        """Grow the box to fully cover the banner with NO edge showing. The red
        detection only sees the red bar, but the banner (set-top-box graphic,
        icons) is taller — so extend more on TOP to reach the banner's real top,
        plus a little each side; not a big block, just enough to hide all edges."""
        x = max(0.0, self.x - px)
        y = max(0.0, self.y - py_top)
        w = min(1.0 - x, self.w + 2 * px)
        h = min(1.0 - y, self.h + py_top + py_bot)
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


def _duration(video: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def _extract_frames(video: str, out_dir: str, fps: float, width: int = 640) -> int:
    """Sample frames at a fixed rate (decode pass) -> scaled JPEGs."""
    os.makedirs(out_dir, exist_ok=True)
    for f in glob.glob(os.path.join(out_dir, "*.jpg")):
        os.remove(f)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video,
         "-vf", f"fps={fps},scale={width}:-1", "-q:v", "3",
         os.path.join(out_dir, "f_%06d.jpg")], check=True)
    return len(glob.glob(os.path.join(out_dir, "*.jpg")))


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
        # --- zone: bottom strip only (Fanproj promos sit at the bottom). NOT the
        # top, where the channel/StreamNxt watermark logos live (those aren't
        # ad banners and were causing false covers). ---
        in_zone = (ny + nh) >= 0.66
        # red fill density inside the box (reject sparse red speckle)
        sub = mask[y:y + h, x:x + w]
        dense = sub.size > 0 and (cv2.countNonZero(sub) / sub.size) >= 0.45
        # a banner has WHITE text/icons on the red (phone number, channel icons);
        # red clothing/objects don't -> require some white content to reject them
        sv = hsv[y:y + h, x:x + w]
        white_frac = (((sv[:, :, 2] > 195) & (sv[:, :, 1] < 60)).mean()
                      if sv.size else 0.0)
        has_text = white_frac >= 0.02
        if (wide and short and banner_aspect and reasonable_area
                and in_zone and dense and has_text):
            boxes.append((nx, ny, nw, nh))
    return boxes


def _bottom_candidate(img: np.ndarray) -> bool:
    """Cheap gate: is there anything banner-like (saturated RED, or a bright
    horizontal strip) in the bottom third? Lets us skip the expensive OCR +
    template match on the ~99% of frames that have no banner — the big speedup."""
    H = img.shape[0]
    reg = img[int(0.60 * H):, :]
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    red = (((h < 10) | (h > 170)) & (s > 90) & (v > 70)).mean()
    bright = ((v > 195) & (s < 60)).mean()
    return red > 0.008 or bright > 0.05


def _max_digit_run(s: str) -> int:
    best = run = 0
    for ch in s:
        run = run + 1 if ch.isdigit() else 0
        best = max(best, run)
    return best


def _find_phone_boxes(img: np.ndarray) -> list[tuple[float, float, float, float]]:
    """OCR the WHOLE frame for phone numbers (>=6 consecutive digits, e.g.
    0612001600 / 0619624090). The number is the universal signal of an ad
    banner — any size, any location. Returns normalised boxes around each
    number, widened to the banner strip so the whole banner gets covered."""
    if not _HAS_OCR:
        return []
    H, W = img.shape[:2]
    # only the BOTTOM strip — banners live there; scanning the whole frame
    # caught scene text/numbers (clocks, signs, dialogue) -> false covers.
    y0 = int(0.58 * H)
    region = img[y0:, :]
    # The numbers are WHITE text on a RED/coloured bar — raw OCR reads that badly
    # (it failed on a perfectly clear "3636 0612001600"). Isolate the bright text
    # into a clean binary + upscale 2x; tesseract reads it reliably this way.
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    white = (((hsv[:, :, 2] > 170) & (hsv[:, :, 1] < 90)).astype(np.uint8)) * 255
    white = cv2.resize(white, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_LINEAR)
    boxes: list[tuple[float, float, float, float]] = []
    try:
        from pytesseract import Output
        data = pytesseract.image_to_data(white, config="--psm 11",
                                         output_type=Output.DICT)
    except Exception:
        return []
    for i, txt in enumerate(data["text"]):
        if _max_digit_run(txt) >= 6:
            # coords are in the 2x-upscaled strip -> divide back by 2
            x, y = data["left"][i] / 2.0, data["top"][i] / 2.0
            w, h = data["width"][i] / 2.0, data["height"][i] / 2.0
            nx = max(0.0, (x - w * 0.6) / W)
            ny = max(0.0, (y + y0 - h * 0.8) / H)
            nw = min(1.0 - nx, (w * 2.2) / W)
            nh = min(1.0 - ny, (h * 2.6) / H)
            boxes.append((nx, ny, nw, nh))
    return boxes


_TEMPLATES = None


def _load_templates():
    """Load banner templates (cropped from full-res 1920-wide frames) once."""
    global _TEMPLATES
    if _TEMPLATES is not None:
        return _TEMPLATES
    _TEMPLATES = []
    for base in (os.path.join(os.path.dirname(__file__), "assets", "templates"),
                 "/app/assets/templates"):
        if os.path.isdir(base):
            for f in sorted(glob.glob(os.path.join(base, "*.png"))):
                t = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
                if t is not None and t.size:
                    _TEMPLATES.append((os.path.basename(f), t))
            break
    if _TEMPLATES:
        log.info("detect: %d banner template(s) loaded", len(_TEMPLATES))
    return _TEMPLATES


_BANNER_TMPLS = None


def _load_banner_templates():
    """The FULL Fanproj banner in each phase: the CHANNELS strip and the
    phone-NUMBER bar. Matching these whole graphics gives the banner's EXACT box
    (so the cover fits with no edge) AND its exact appear/disappear time."""
    global _BANNER_TMPLS
    if _BANNER_TMPLS is not None:
        return _BANNER_TMPLS
    _BANNER_TMPLS = []
    for base in (os.path.join(os.path.dirname(__file__), "assets", "templates"),
                 "/app/assets/templates"):
        # NOTE: no fanproj_number_k.png — the Kurulus number bar is the same
        # "3636 0612001600" graphic as Mr X's and its template out-scored Mr X's
        # own, hijacking Mr X's box to full width. The red/OCR detector already
        # covers number bars for both; only Kurulus's distinct full-frame CHANNELS
        # strip needed its own template.
        for fn in ("fanproj_channels.png", "fanproj_number.png",
                   "fanproj_channels_k.png"):
            t = cv2.imread(os.path.join(base, fn), cv2.IMREAD_GRAYSCALE)
            if t is not None and t.size:
                _BANNER_TMPLS.append((fn, t))
        if _BANNER_TMPLS:
            break
    return _BANNER_TMPLS


def _find_template_banners(gray: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Match the exact Fanproj banner (channels strip OR number bar) in the
    bottom strip, multi-scale. The match rectangle IS the banner, so the box is
    exact. High threshold -> scenes are rejected."""
    out = []
    H, W = gray.shape[:2]
    # region top at 0.74 (not 0.78): full-frame banners (e.g. Kurulus) sit lower,
    # so a 0.78 cut clipped the channels-strip top and the template couldn't align
    # (score 0.69 vs 1.00). 0.74 gives room; high threshold still rejects scenes.
    y0 = int(0.74 * H)
    region = gray[y0:, :]
    rH = region.shape[0]
    base = W / 960.0
    # Keep only the SINGLE best-fitting template for this frame, across ALL
    # templates that clear THEIR OWN threshold. The banner shows ONE phase at a
    # time; different formats have their own templates. The full-frame Kurulus
    # CHANNELS template cross-scores ~0.92 on the letterboxed Mr X/Bou channels
    # strip (vs 0.97-1.0 on real Kurulus), so it needs a HIGHER bar (0.95) or it
    # hijacks their box. Native templates keep 0.86. Best qualifier wins -> each
    # video stays on its own template and the box stays exact.
    cands = []  # (score, lx, ly, tw, th)
    for name, tmpl in _load_banner_templates():
        thr = 0.95 if name.endswith("_k.png") else 0.86
        best = None
        for s in (0.78, 0.88, 1.0, 1.12, 1.28):
            tw, th = int(tmpl.shape[1] * base * s), int(tmpl.shape[0] * base * s)
            if tw < 30 or th < 12 or tw >= W or th >= rH:
                continue
            res = cv2.matchTemplate(region, cv2.resize(tmpl, (tw, th)),
                                    cv2.TM_CCOEFF_NORMED)
            _mn, mv, _ml, ml = cv2.minMaxLoc(res)
            if best is None or mv > best[0]:
                best = (mv, ml[0], ml[1], tw, th)
        if best and best[0] >= thr:
            cands.append(best)
    if cands:
        _, lx, ly, tw, th = max(cands, key=lambda c: c[0])
        out.append((lx / W, (ly + y0) / H, tw / W, th / H))
    return out


def _find_channel_grid(img: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Detect the Fanproj CHANNELS strip by its giveaway: a horizontal ROW of
    many small, distinctly-coloured channel icons in the bottom strip. This is
    the phase of the banner that has NO phone number, so OCR misses it — but it
    appears first, so catching it makes the cover start with the banner."""
    H, W = img.shape[:2]
    y0 = int(0.80 * H)
    reg = img[y0:, :]
    hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    sat = (((s > 110) & (v > 90)).astype(np.uint8)) * 255
    sat = cv2.morphologyEx(sat, cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    cnts, _ = cv2.findContours(sat, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rh = reg.shape[0]
    icons = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if (0.008 * W < w < 0.06 * W and 0.18 * rh < h < 0.95 * rh
                and 0.4 < (w / max(1, h)) < 2.6):
            icons.append((x, y, w, h))
    if len(icons) < 4:
        return []
    # icons must line up in a row (the grid), not be scattered around the scene
    ys = sorted((iy + ih / 2) for _, iy, _, ih in icons)
    ymed = ys[len(ys) // 2]
    row = [ic for ic in icons if abs((ic[1] + ic[3] / 2) - ymed) < 0.35 * rh]
    if len(row) < 4:
        return []
    # UNIFORMITY: a real channel-icon grid is a run of similarly-sized, evenly
    # spaced tiles. Scene clutter (flags, market stalls, crowds) makes a ragged
    # row -> reject it. Keeps the grid usable as a PRIMARY detector, not just a
    # location-locked confirmer.
    row.sort(key=lambda ic: ic[0])
    ws = [iw for _, _, iw, _ in row]
    wmean = sum(ws) / len(ws)
    if wmean <= 0 or (max(ws) - min(ws)) / wmean > 1.1:
        return []
    gaps = [row[i + 1][0] - row[i][0] for i in range(len(row) - 1)]
    if gaps:
        gmean = sum(gaps) / len(gaps)
        if gmean <= 0 or (max(gaps) - min(gaps)) / gmean > 1.6:
            return []
    xs0 = min(ix for ix, _, _, _ in row)
    xs1 = max(ix + iw for ix, _, iw, _ in row)
    ys0 = min(iy for _, iy, _, _ in row)
    ys1 = max(iy + ih for _, iy, _, ih in row)
    # CORROBORATION: the Fanproj CHANNELS strip ALWAYS has a saturated-RED logo
    # block immediately LEFT of the icon row. Require it, so a merely-colourful
    # scene (no red logo) can't create a false cover.
    lx0 = max(0, int(xs0 - 0.16 * W))
    lx1 = max(0, int(xs0 - 0.005 * W))
    lstrip = reg[max(0, ys0 - 4):min(rh, ys1 + 4), lx0:lx1]
    if lstrip.size:
        lh = cv2.cvtColor(lstrip, cv2.COLOR_BGR2HSV)
        lred = ((((lh[:, :, 0] < 10) | (lh[:, :, 0] > 170)) &
                 (lh[:, :, 1] > 90) & (lh[:, :, 2] > 70)).mean())
        if lred < 0.12:
            return []
    else:
        return []
    # the icons sit between the red "Fanproj CHANNELS" logo (left) and the set-top
    # box (right) — extend to include both so the whole strip is covered.
    nx = max(0.0, (xs0 - 0.14 * W) / W)
    nx2 = min(1.0, (xs1 + 0.11 * W) / W)
    ny = max(0.0, (ys0 + y0) / H - 0.015)
    ny2 = min(1.0, (ys1 + y0) / H + 0.015)
    return [(nx, ny, nx2 - nx, ny2 - ny)]


def _match_gray_templates(gray: np.ndarray, tmpls: list, thr: float = 0.85
                          ) -> list[tuple[float, float, float, float]]:
    """Match a list of grayscale template arrays (e.g. SELF-LEARNED banner crops
    taken from this very video) in the bottom strip and return the single best
    box >= thr. Scales are tight (the crop came from a same-resolution frame, so
    the banner is ~the same size) plus a little slack."""
    if not tmpls:
        return []
    H, W = gray.shape[:2]
    y0 = int(0.74 * H)
    region = gray[y0:, :]
    rH = region.shape[0]
    best = None
    for tmpl in tmpls:
        for s in (0.92, 1.0, 1.08):
            tw, th = int(tmpl.shape[1] * s), int(tmpl.shape[0] * s)
            if tw < 30 or th < 12 or tw >= W or th >= rH:
                continue
            res = cv2.matchTemplate(region, cv2.resize(tmpl, (tw, th)),
                                    cv2.TM_CCOEFF_NORMED)
            _mn, mv, _ml, ml = cv2.minMaxLoc(res)
            if best is None or mv > best[0]:
                best = (mv, ml[0], ml[1], tw, th)
    if best and best[0] >= thr:
        _, lx, ly, tw, th = best
        return [(lx / W, (ly + y0) / H, tw / W, th / H)]
    return []


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


def _refine_box_temporal(video: str, start: float, end: float,
                         box: tuple[float, float, float, float],
                         work_dir: str):
    """Measure a banner's EXACT extent so the cover fits it with no edge showing.

    A broadcaster banner is STATIC (it doesn't move) while the scene plays
    behind it. So inside the band we sample several frames in a generous window
    around the rough box, keep the pixels that barely change across frames AND
    look like an overlay graphic (saturated / very bright / very dark text), and
    take their tight bounding box. Location/size/series-independent.

    Returns a tight normalised (x,y,w,h) or None if it couldn't measure cleanly.
    """
    N = 9
    # Window centred on the rough detection, with a MINIMUM span so a narrow
    # detection (e.g. OCR found only the phone number) still captures the whole
    # banner. Bounded so we don't grab the show's own static corner logos.
    midx = box[0] + box[2] / 2
    midy = box[1] + box[3] / 2
    halfw = max(box[2] / 2 + 0.14, 0.32)
    halfh = max(box[3] / 2 + 0.06, 0.11)
    cx0 = max(0.0, midx - halfw)
    cx1 = min(1.0, midx + halfw)
    cy0 = max(0.0, midy - halfh)
    cy1 = min(1.0, midy + halfh)
    if cx1 - cx0 < 0.05 or cy1 - cy0 < 0.03:
        return None
    if end > start:
        m0 = start + 0.25 * (end - start)
        m1 = end - 0.25 * (end - start)
        times = [m0 + (m1 - m0) * i / (N - 1) for i in range(N)]
    else:
        times = [start]
    rdir = os.path.join(work_dir, "rfn")
    os.makedirs(rdir, exist_ok=True)
    Wt = 960
    grays, hsvs = [], []
    for i, t in enumerate(times):
        fp = os.path.join(rdir, f"r{i}.jpg")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{max(0.0, t):.2f}", "-i", video, "-frames:v", "1",
                        "-vf", f"scale={Wt}:-1", fp], check=False)
        im = cv2.imread(fp)
        if im is None:
            continue
        H, Wi = im.shape[:2]
        x0, y0 = int(cx0 * Wi), int(cy0 * H)
        x1, y1 = int(cx1 * Wi), int(cy1 * H)
        crop = im[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        grays.append(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32))
        hsvs.append(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV))
    for f in glob.glob(os.path.join(rdir, "*.jpg")):
        try:
            os.remove(f)
        except OSError:
            pass
    _dbg = os.environ.get("RDBG")
    if len(grays) < 3:
        if _dbg:
            log.warning("refine None: only %d frames (times=%s)", len(grays), times)
        return None
    hmin = min(g.shape[0] for g in grays)
    wmin = min(g.shape[1] for g in grays)
    if hmin < 8 or wmin < 8:
        return None
    grays = [g[:hmin, :wmin] for g in grays]
    hsvs = [h[:hmin, :wmin] for h in hsvs]
    std = np.stack(grays).std(axis=0)               # low = static across band
    hsv_med = np.median(np.stack(hsvs), axis=0).astype(np.uint8)
    sat, val = hsv_med[:, :, 1], hsv_med[:, :, 2]
    static = std < 18.0
    # overlay graphic = saturated (logo/icons) OR bright (white strip). NOT dark
    # (that caught static night scenes / dark walls and over-grew the box).
    distinct = (sat > 70) | (val > 200)
    mask = (static & distinct).astype(np.uint8) * 255
    # drop tiny speckle first, then bridge the strip's gaps (logo | icons |
    # set-top box) into ONE blob with a wide horizontal close.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3)), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (45, 7)), iterations=2)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_min = 0.0015 * hmin * wmin
    cand = [cv2.boundingRect(c) for c in cnts if cv2.contourArea(c) > area_min]
    if _dbg:
        log.warning("refine: window x[%.2f-%.2f] y[%.2f-%.2f] blobs=%s",
                    cx0, cx1, cy0, cy1, cand)
    if not cand:
        return None
    # the moving scene means ONLY the banner is static, so the union of the
    # static blobs (logo | icon-grid | set-top box) is the banner. Static
    # BACKGROUND (a still wall/sky) would extend the union up to the window's top
    # edge — which the top-touch check below rejects.
    bx0 = min(b[0] for b in cand)
    by0 = min(b[1] for b in cand)
    bx1 = max(b[0] + b[2] for b in cand)
    by1 = max(b[1] + b[3] for b in cand)
    nx = cx0 + (bx0 / wmin) * (cx1 - cx0)
    ny = cy0 + (by0 / hmin) * (cy1 - cy0)
    nw = (bx1 - bx0) / wmin * (cx1 - cx0)
    nh = (by1 - by0) / hmin * (cy1 - cy0)
    # sanity: a real banner, not a sliver and not the whole window (unreliable)
    if nw < 0.06 or nh < 0.025:
        return None
    # if the measured blob reaches the window's TOP edge, static background is
    # bleeding upward into it (a still wall/sky fused with the banner) — the
    # measurement is unreliable, fall back to the rough box. (Bottom-touch is
    # fine — banners sit near the frame bottom; left/right can graze the window
    # when the rough box is off-centre, which is OK.)
    if cy0 > 0.001 and ny - cy0 < 0.012:
        if _dbg:
            log.warning("refine None: top-touch ny=%.3f cy0=%.3f", ny, cy0)
        return None
    if _dbg:
        log.warning("refine: cand=%s pick=%s merged=(%d,%d,%d,%d) wmin=%d hmin=%d",
                    cand, pick, bx0, by0, bx1, by1, wmin, hmin)
        log.warning("refine OK: box=(%.3f,%.3f,%.3f,%.3f)", nx, ny, nw, nh)
    return (nx, ny, nw, nh)


def _refine_extent(video: str, start: float, end: float,
                   box: tuple[float, float, float, float], work_dir: str):
    """Grow the cover box sideways to the banner's TRUE width. The detected box
    comes from the red bar / phone number, but the banner also has a set-top-box
    icon and channel-grid that aren't red — so the cover misses them. The whole
    banner strip is STATIC while the scene moves, so on the banner's row we keep
    the columns that (a) barely change across the band AND (b) look like overlay
    (saturated or bright) — then take the contiguous span around the detection.
    Returns a box with the corrected x-extent (keeps y/h)."""
    N = 7
    # sample the MIDDLE of the banner window — the edges include its fade in/out
    # where the banner is absent, which inflates the per-column variance and made
    # the static test fail.
    if end > start:
        m0 = start + 0.25 * (end - start)
        m1 = end - 0.25 * (end - start)
        times = [m0 + (m1 - m0) * i / (N - 1) for i in range(N)]
    else:
        times = [start]
    # sample the banner's own row (lower part of the padded box) — the top of the
    # box is padding/scene and would drown out the column scores.
    ry0 = max(0.0, box[1] + 0.30 * box[3])
    ry1 = min(1.0, box[1] + box[3] + 0.005)
    rdir = os.path.join(work_dir, "ext")
    os.makedirs(rdir, exist_ok=True)
    grays, sats = [], []
    for i, t in enumerate(times):
        fp = os.path.join(rdir, f"e{i}.jpg")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{max(0.0, t):.2f}", "-i", video, "-frames:v", "1",
                        "-vf", "scale=960:-1", fp], check=False)
        im = cv2.imread(fp)
        if im is None:
            continue
        H, Wi = im.shape[:2]
        strip = im[int(ry0 * H):int(ry1 * H), :]
        if strip.size == 0:
            continue
        grays.append(cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY).astype(np.float32))
        sats.append(cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)[:, :, 1].astype(np.float32))
    for f in glob.glob(os.path.join(rdir, "*.jpg")):
        try:
            os.remove(f)
        except OSError:
            pass
    if len(grays) < 3:
        return box
    hmin = min(g.shape[0] for g in grays)
    grays = [g[:hmin, :] for g in grays]
    sats = [s[:hmin, :] for s in sats]
    stk = np.stack(grays)
    Wi = stk.shape[2]
    # per-PIXEL: static across the band AND overlay-like (coloured or bright).
    # Then a column is "banner" if enough of its rows are banner-like — this
    # ignores the moving scene that sits above the bar in the sampled strip.
    std2d = stk.std(axis=0)
    val2d = np.median(stk, axis=0)
    sat2d = np.median(np.stack(sats), axis=0)
    banner2d = (std2d < 18.0) & ((sat2d > 80) | (val2d > 200))
    col_score = banner2d.mean(axis=0)
    colok = col_score > 0.25
    sx0 = max(0, int(box[0] * Wi))
    sx1 = min(Wi - 1, int((box[0] + box[2]) * Wi))
    gaptol = int(0.012 * Wi)        # only bridge tiny gaps (inside the strip)
    cap = int(0.13 * Wi)            # don't grow more than this beyond the box

    def grow(c, step, limit):
        best, gap = c, 0
        while 0 <= c < Wi and abs(c - (sx0 if step < 0 else sx1)) <= limit:
            if colok[c]:
                best, gap = c, 0
            else:
                gap += 1
                if gap > gaptol:
                    break
            c += step
        return best
    L, R = grow(sx0, -1, cap), grow(sx1, +1, cap)
    # never run the cover into the frame edge — that means it grabbed scene/logo
    if (R + 1) / Wi > 0.97:
        R = sx1
    if L / Wi < 0.03:
        L = sx0
    nx = max(0.0, L / Wi)
    nx2 = min(1.0, (R + 1) / Wi)
    nw = nx2 - nx
    # sanity: a banner strip, not a sliver and not (almost) the whole width
    if nw < 0.1 or nw > 0.92:
        return box
    return (nx, box[1], nw, box[3])


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
    dur = _duration(video)
    # Fixed-interval sampling (~every 2s) so a banner can't hide between
    # keyframes; capped at ~2200 frames so very long movies stay reasonable.
    sample_fps = max(0.30, min(0.6, 2200.0 / max(1.0, dur)))
    n = _extract_frames(video, frames_dir, sample_fps, width=960)
    files = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    m = len(files)
    if m < 2:
        log.info("detect: too few frames (%d)", m)
        return []
    times = [i / sample_fps for i in range(m)]
    spacing = 1.0 / sample_fps
    # bridge only short gaps (a sliding banner missed for 1-2 samples), NOT long
    # absences — otherwise an intermittent banner becomes one long over-cover.
    merge_gap = max(merge_gap, 4.0 * spacing, 12.0)
    log.info("detect: %d frames @%.2ffps (~%.1fs apart), merge_gap=%.0fs",
             m, sample_fps, spacing, merge_gap)

    # per-timestamp detections: (t, box, has_phone, is_red).
    # NUMBER-CENTRIC: a phone number (>=6 digits) anywhere = an ad banner, any
    # size/location. Cover it, expanded to any red bar around it. Plus known
    # banner templates. Red WITHOUT a number is NOT covered (avoids roses/
    # clothing false positives).
    def _samerow(b, pb):
        return b[1] - 0.05 <= pb[1] + pb[3] * 0.5 <= b[1] + b[3] + 0.05

    def _crop_gray(gray, box, W, H):
        x0, y0p = int(box[0] * W), int(box[1] * H)
        x1, y1p = int((box[0] + box[2]) * W), int((box[1] + box[3]) * H)
        if x1 - x0 < 40 or y1p - y0p < 10:
            return None
        c = gray[max(0, y0p):y1p, max(0, x0):x1]
        return c.copy() if c.size else None

    dets: list = []
    tmpl_times: set = set()        # times a PRE-MADE template matched
    exemplars: dict = {}           # phase -> (score, gray_crop) for self-learning
    for idx, fp in enumerate(files):
        t = times[idx]
        img = cv2.imread(fp)
        if img is None:
            continue
        red_boxes = _find_red_banners(img)
        # gate the SLOW checks (OCR, template match) to frames that actually have
        # a banner-like region — ~99% of frames are skipped -> much faster scan,
        # and fewer false positives from OCR'ing random scene text.
        cand = bool(red_boxes) or _bottom_candidate(img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if cand else None
        phone_boxes = _find_phone_boxes(img) if (use_ocr and cand) else []
        tmpl_boxes = _find_template_banners(gray) if cand else []
        grid_boxes = _find_channel_grid(img) if cand else []
        H, W = img.shape[:2]

        # red bars (reliable for red phone bars); union any number on the same
        # row for full width; flag whether a number was confirmed this frame
        for rb in red_boxes:
            # the RED BAR itself is the banner geometry; a phone number on it only
            # CONFIRMS it (don't union the widened OCR box — that over-extended the
            # cover to near full-width on some videos).
            phone = any(_iou(rb, pb) > 0.005 or _samerow(rb, pb) for pb in phone_boxes)
            dets.append((t, rb, phone, True, False))
            # SELF-LEARN: a red bar WITH a phone number is a rock-solid banner;
            # keep the cleanest (largest) crop as a template for THIS video.
            if phone and 0.2 <= rb[2] <= 0.95:
                c = _crop_gray(gray, rb, W, H)
                if c is not None and (exemplars.get("num") is None
                                      or c.size > exemplars["num"][0]):
                    exemplars["num"] = (c.size, c)
        # numbers NOT on a red bar = non-red banner (any size/location)
        for pb in phone_boxes:
            if not any(_iou(pb, rb) > 0.005 or _samerow(rb, pb) for rb in red_boxes):
                dets.append((t, pb, True, True, False))
        # exact full-banner template matches (channels strip / number bar)
        for tb in tmpl_boxes:
            dets.append((t, tb, True, True, True))
            tmpl_times.add(t)
        # UNIVERSAL channels-strip detection (no template needed): a uniform row
        # of channel icons WITH the Fanproj red logo beside it. This is what makes
        # a NEW banner format's channels phase coverable on its own. Marked
        # has_dig=True (a confirmed banner signature, like a number) so the FP
        # filter keeps it.
        for gb in grid_boxes:
            if not any(_iou(gb, e[1]) > 0.2 for e in dets if e[0] == t):
                dets.append((t, gb, True, False, False))
            if 0.2 <= gb[2] <= 0.95:
                c = _crop_gray(gray, gb, W, H)
                if c is not None and (exemplars.get("ch") is None
                                      or c.size > exemplars["ch"][0]):
                    exemplars["ch"] = (c.size, c)

    # --- SELF-LEARNING pass: for an UNSEEN banner format (no pre-made template
    # matched), match the banner crops we just learned FROM THIS VIDEO back
    # across every frame. This recovers the banner at moments the heuristics
    # missed (faint channels phase, slide frames) and pins an exact, stable box
    # + timing — template-quality results on a format we've never seen. Only
    # fills frames a pre-made template did NOT already claim, so it can't fight
    # the tuned templates on known formats.
    # SPEED gate: skip this extra full pass when a pre-made template already
    # matched the banner on plenty of frames (a KNOWN format — the common case,
    # and every episode of a series). Only an UNSEEN format (few/no pre-made
    # matches) needs the self-learned crops, so the cost is paid only when it
    # actually buys coverage. Big win for batch/long videos.
    autos = [c for (_s, c) in exemplars.values()]
    if autos and len(tmpl_times) < 8:
        for idx, fp in enumerate(files):
            t = times[idx]
            if t in tmpl_times:
                continue
            img = cv2.imread(fp)
            if img is None or not _bottom_candidate(img):
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            for ab in _match_gray_templates(gray, autos, thr=0.85):
                if not any(_iou(ab, e[1]) > 0.3 for e in dets if e[0] == t):
                    dets.append((t, ab, True, True, True))

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

    def _edges(use: list) -> tuple[float, float, float, float]:
        """Horizontal + vertical extent of a set of boxes, scroll-aware. A STATIC
        banner (Mr X/Bou) clusters tightly -> trim outliers for an exact fit. A
        MOVING banner (Kurulus Orhan travels left<->centre across the bottom)
        spreads wide -> its detections are all real, so cover the full travel."""
        lefts = [b[0] for b in use]
        rights = [b[0] + b[2] for b in use]
        centers = sorted(b[0] + b[2] / 2.0 for b in use)
        cspread = (centers[-1] - centers[0]) if len(centers) > 1 else 0.0
        if cspread > 0.20:
            x = float(np.percentile(lefts, 2))
            x2 = float(np.percentile(rights, 98))
        else:
            x = float(np.percentile(lefts, 15))
            x2 = float(np.percentile(rights, 85))
        y = float(np.percentile([b[1] for b in use], 10))
        y2 = float(np.percentile([b[1] + b[3] for b in use], 90))
        return (x, y, x2 - x, y2 - y)

    def _box_from(boxes: list) -> tuple[float, float, float, float]:
        """The cover box. Prefer exact full-banner TEMPLATE matches (that rectangle
        IS the banner). Both branches are scroll-aware via _edges()."""
        tmpls = [b for b, _is_red, is_tmpl in boxes if is_tmpl]
        if tmpls:
            return _edges(tmpls)
        reds = [b for b, is_red, _ in boxes if is_red]
        use = reds if reds else [b for b, _, _ in boxes]
        return _edges(use)

    # cluster into tracks by SAME-BAND continuity + time. NOT strict IoU: the
    # banner cycles number-bar <-> channels-strip, whose boxes differ in height
    # (IoU ~0.39, just under a 0.4 cut) and so fragmented into separate tracks —
    # which then chopped a whole-clip banner into a tiny band. Same-band = they
    # share the bottom strip (vertical overlap) AND overlap horizontally; a det
    # at a different spot still starts its own track.
    def _sameband(a, b) -> bool:
        vov = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
        hov = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
        return (vov / max(1e-6, min(a[3], b[3])) > 0.3
                and hov / max(1e-6, min(a[2], b[2])) > 0.3)

    # MUST be time-sorted: clustering advances each track's end by processing
    # order, and the self-learning pass appends its dets out of order (it re-walks
    # the frames), which otherwise reset a track's end back to an early time.
    dets.sort(key=lambda d: d[0])
    tracks: list[dict] = []
    for t, box, has_dig, is_red, is_tmpl in dets:
        placed = False
        for tr in tracks:
            if t - tr["last_t"] <= merge_gap and _sameband(tr["rep"], box):
                tr["end"] = t
                tr["last_t"] = t
                tr["hits"] += 1
                tr["digits"] += int(has_dig)
                tr["boxes"].append((box, is_red, is_tmpl))
                tr["rep"] = box
                placed = True
                break
        if not placed:
            tracks.append({"start": t, "end": t, "last_t": t, "rep": box,
                           "boxes": [(box, is_red, is_tmpl)], "hits": 1,
                           "digits": int(has_dig)})

    LINK_GAP = 12.0   # join same-location events with short gaps, not long absences

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

    # Every detection here is already a confirmed banner: a red bar WITH white
    # text, a phone number, or a template match. min_duration/coverage (in the
    # track stage) drops transient one-offs. So keep them all.

    # --- Refine each band's start/end so the cover matches the banner exactly --
    # The coarse interval scan only knows the banner is present at sampled times;
    # fine-scan (0.4s) around the edges to find the true appear/disappear moment.
    refdir = os.path.join(work_dir, "ref")
    os.makedirs(refdir, exist_ok=True)

    def _present_at(t: float, box) -> bool:
        tmp = os.path.join(refdir, "r.jpg")
        # 960px (same as the main scan) + the white-mask OCR so the edge check is
        # as sensitive as detection itself — a 640px frame missed faint edges and
        # made the cover end before the banner did.
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{max(0.0, t):.2f}", "-i", video, "-frames:v", "1",
                        "-vf", "scale=960:-1", tmp], check=False)
        img = cv2.imread(tmp)
        if img is None:
            return False
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cand = list(_find_red_banners(img))
        cand += _find_template_banners(g)
        # SELF-LEARNED crops from this video — catch slide/transition frames where
        # red/OCR/grid/pre-made templates all momentarily miss (that gap was ending
        # the cover ~13s before the banner actually left).
        cand += _match_gray_templates(g, autos, thr=0.82)
        if use_ocr:
            cand += _find_phone_boxes(img)
        # the channels-grid phase (no number) at THIS banner's spot — used only to
        # extend a band already confirmed by the number, so a colourful scene can
        # never create a false cover.
        cand += _find_channel_grid(img)
        for c in cand:
            vov = max(0.0, min(c[1] + c[3], box[1] + box[3]) - max(c[1], box[1]))
            hov = max(0.0, min(c[0] + c[2], box[0] + box[2]) - max(c[0], box[0]))
            if vov > 0 and hov > 0.15 * box[2]:
                return True
        # The banner cycles: phone-number bar (red) <-> channels grid (white bg).
        # OCR/red only catch the number phase, so the channels phase looked
        # "absent" and the cover started late. Here — ONLY at the banner's known
        # location (so it can't false-trigger on the scene) — also treat the box
        # as present if it's still a solid banner bar: mostly WHITE (channels bg)
        # or mostly RED (phone bar).
        Hh, Ww = img.shape[:2]
        # check only the banner's ROW (bottom 45% of the box) so the scene above
        # it in the box doesn't dilute the measure; require a HIGH fill so a
        # scene that merely has some white/red doesn't trigger.
        by0 = int((box[1] + 0.55 * box[3]) * Hh)
        cx0 = int(box[0] * Ww)
        cx1 = int((box[0] + box[2]) * Ww)
        cy1 = int((box[1] + box[3]) * Hh)
        crop = img[max(0, by0):cy1, max(0, cx0):cx1]
        if crop.size:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            h_, s_, v_ = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
            white = ((v_ > 180) & (s_ < 55)).mean()
            red = (((h_ < 10) | (h_ > 170)) & (s_ > 95) & (v_ > 70)).mean()
            if white > 0.32 or red > 0.40:
                return True
        return False

    out: list[CoverEvent] = []
    for b in bands:
        x, y, w, h = b["rep"]
        box = (x, y, w, h)
        # Re-derive the banner's TRUE on-screen window by fine-scanning the whole
        # band region (0.5s steps) with the accurate detector. min/max of the
        # moments it's actually present = exact window. This fixes both a cover
        # that started too early (coarse merge) and one that ended before the
        # banner was gone (lost edge) -> cover now lines up with the banner.
        # TRUST the coarse band [start,end] (the main scan is frame-accurate and
        # found the banner continuously across it) and only fine-scan a SMALL
        # window at each EDGE to pin the exact appear/disappear moment between
        # samples. Crucial: the walk can only EXTEND outward from the coarse
        # edges (rs only shrinks, re only grows), so the middle of a long banner
        # can never be chopped — earlier a mid-anchored walk + flaky `-ss` seeks
        # truncated Kurulus to a fraction of its true span. Edge window is bounded
        # (~6s) so a flaky seek can over-extend by at most that, never under-cover.
        rs, re = b["start"], b["end"]
        t, gap = b["start"], 0.0
        while t > b["start"] - 6.0 and t > 0:
            t -= 0.5
            if _present_at(t, box):
                rs, gap = t, 0.0
            else:
                gap += 0.5
                if gap > 2.0:
                    break
        t, gap = b["end"], 0.0
        while t < b["end"] + 6.0 and t < dur:
            t += 0.5
            if _present_at(t, box):
                re, gap = t, 0.0
            else:
                gap += 0.5
                if gap > 2.0:
                    break
        # Small sync lead/lag so the cover is never a frame late and stays till the
        # banner is fully gone. Modest now (-0.5/+0.6): the channels-grid detector
        # in the main scan catches the banner's onset ~2s earlier than before, so a
        # large lead would pop the bar up well before the banner appears.
        rs -= 0.5
        re += 0.6
        if rs < 0.8:
            rs = 0.0
        if re <= rs:
            re = rs + 1.0
        # cover the detected banner box, padded enough that no edge peeks.
        out.append(CoverEvent(rs, re, x, y, w, h, b["digits"]).padded(
            px=0.026, py_top=0.012, py_bot=0.016))

    for f in glob.glob(os.path.join(refdir, "*.jpg")):
        try:
            os.remove(f)
        except OSError:
            pass

    # --- Smart cleanup -------------------------------------------------------
    # (1) Drop false positives: a real ad banner is confirmed by a phone number
    # OR a known-banner template match (both set digits>=1). Bands with digits=0
    # are bare red blobs — opening-credit name-plates, night city-lights, a phone
    # screen — which were the spurious covers. Drop them.
    real = [e for e in out if e.digits >= 1]
    if not real:                       # nothing confirmed -> keep originals
        real = out

    # (2) Consensus fit: the same promo banner sits in the SAME place every time,
    # but a single detection can come out shifted/narrow (e.g. only the phone-
    # number half). Widen each box to the consensus (median) of the bands sharing
    # its row, so every banner is covered fully with no edge.
    if len(real) >= 3:
        import statistics as st
        cl = st.median([e.x for e in real])
        cr = st.median([e.x + e.w for e in real])
        ct = st.median([e.y for e in real])
        cb = st.median([e.y + e.h for e in real])
        fixed = []
        for e in real:
            vo = min(e.y + e.h, cb) - max(e.y, ct)
            if vo > 0.3 * min(e.h, cb - ct):     # on the consensus row
                nx, nx2 = min(e.x, cl), max(e.x + e.w, cr)
                ny, ny2 = min(e.y, ct), max(e.y + e.h, cb)
                fixed.append(CoverEvent(e.start, e.end, nx, ny,
                                        nx2 - nx, ny2 - ny, e.digits))
            else:
                fixed.append(e)
        real = fixed

    out = real
    out.sort(key=lambda e: e.start)
    log.info("detect: %d cover bands (edges refined, consensus-fit)", len(out))
    return out
