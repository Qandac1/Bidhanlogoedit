"""bot20: higher quality than 1080p (John 2026-10-02: "src 3840x2160 but the bot sets 1920x1080 -- add an option
with more quality, with logic for the dub and for trailers and short videos"; "do it without breaking anything").
  * Resolution menu: "4K" (width -1 in the settings) = the source's own size up to 3840x2160; a source at or below
    1080p renders exactly as with 1920x1080 (never upscaled further).
  * Short videos / trailers (<= 20 min) whose source is above 1080p keep it automatically (up to 4K) -- toggle in
    the Resolution menu ("hq_short", default on). Full films stay at the setting unless 4K is chosen (a 4K film is
    ~9 GB via MEGA and 3-4x the render time).
  * Above 1080p the bitrate grows with the picture: the setting stays the 1080p value (2300k -> 9200k at 4K, the
    same bits per pixel); a size target is still a ceiling.
  * At or below 1080p NOTHING changes: same size, same bitrate, same panel text (test_bot_hq20 proves it on a grid).
Usage: python3 patch_bot_hq20.py <bot.py>"""
import sys

P = sys.argv[1]
s = open(P, encoding="utf-8").read()
if "_out_size" in s:
    raise SystemExit("already patched")


def rep(old, new, what, count=1):
    global s
    assert s.count(old) == count, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


# ---- helpers, right after _effective_bitrate ----
rep('''async def _run_quiet(*cmd, timeout: float = 90.0) -> bytes:''', '''# ---- above 1080p (bot20, John 2026-10-02: a 3840x2160 source came out 1920x1080) ----------------------------
UHD_W, UHD_H = 3840, 2160
HQ_SHORT_S = 20 * 60            # short videos / trailers: a source above 1080p keeps its size (hq_short)
BASE_PIX = 1920 * 1080          # the bitrate setting is the 1080p value


def _fit_box(w: int, h: int, bw: int, bh: int) -> tuple[int, int]:
    """w x h scaled DOWN (never up) to fit inside bw x bh, even sizes."""
    if w <= 0 or h <= 0:
        return bw, bh
    k = min(1.0, bw / w, bh / h)
    return int(w * k) // 2 * 2, int(h * k) // 2 * 2


def _out_size(c: dict, src_w: int, src_h: int, dur: float) -> tuple[int, int, str]:
    """(width, height, note) of the render. A source at or below 1080p: exactly the old rule."""
    big = src_w > 1920 or src_h > 1080
    if c["width"] == 0:
        return src_w, src_h, ""
    if c["width"] == -1:                                      # "4K": the source's own size up to 3840x2160
        if big:
            w, h = _fit_box(src_w, src_h, UHD_W, UHD_H)
            return w, h, " (4K: the source's own size)"
        return 1920, 1080, ""
    if big and c.get("hq_short", True) and 0 < dur <= HQ_SHORT_S:
        w, h = _fit_box(src_w, src_h, UHD_W, UHD_H)
        return w, h, " (short video: kept at its source size)"
    return c["width"], c["height"], ""


def _effective_bitrate_wh(c: dict, dur: float, w: int, h: int) -> tuple[int, str]:
    """_effective_bitrate for a w x h render: above 1080p the bitrate setting (a 1080p value) grows with the
    picture, the size target stays a ceiling. At or below 1080p: exactly _effective_bitrate."""
    if w * h <= BASE_PIX or int(c["bitrate"]) <= 0:
        return _effective_bitrate(c, dur)
    base = int(round(int(c["bitrate"]) * (w * h) / BASE_PIX / 100.0)) * 100
    if c["size_target_gb"] > 0 and dur > 0:
        cap = bitrate_for_target(dur, int(c["size_target_gb"] * 1024 ** 3), c["audio_k"])
        if cap < base:
            return cap, f"{cap}k (capped → {c['size_target_gb']:g} GB)"
    return base, f"{base}k ({int(c['bitrate'])}k at 1080p, scaled for {w}×{h})"


def _res_label(c: dict) -> str:
    """The resolution setting as shown before bot20, plus "4K" for the new choice."""
    if c["width"] == -1:
        return "4K"
    return "Source" if c["width"] == 0 else f"{c['width']}×{c['height']}"


async def _run_quiet(*cmd, timeout: float = 90.0) -> bytes:''', "helpers")

# ---- branding panel: the size, bitrate and size estimate of THIS render ----
rep('''def panel(uid: int, job: dict) -> tuple[str, IKM]:
    c = user_cfg(uid)
    dur = job["duration"]
    vk, br_label = _effective_bitrate(c, dur)''', '''def panel(uid: int, job: dict) -> tuple[str, IKM]:
    c = user_cfg(uid)
    dur = job["duration"]
    _ow, _oh, _onote = _out_size(c, int(job.get("w") or 0), int(job.get("h") or 0), dur)
    vk, br_label = _effective_bitrate_wh(c, dur, _ow, _oh)''', "branding panel bitrate")
rep('''    res = "Source" if c["width"] == 0 else f"{c['width']}×{c['height']}"
    if c.get("scroll_times"):''', '''    res = _res_label(c)
    if _onote or c["width"] == -1:
        res = f"{_ow}×{_oh}{_onote}"
    if c.get("scroll_times"):''', "branding panel res")

# ---- resolution menu: 4K + the short-video toggle ----
rep('''    if which == "res":
        opts = [("1920×1080", "1920x1080"), ("1280×720", "1280x720"), ("Source", "source")]
        cur = "source" if c["width"] == 0 else f"{c['width']}x{c['height']}"
        rows = [[IKB(f"{'✅' if cur==v else ''}{lbl}", f"s:res:{v}") for lbl, v in opts]]
        return IKM(rows + [_back_row()])''', '''    if which == "res":
        opts = [("4K", "4k"), ("1920×1080", "1920x1080"), ("1280×720", "1280x720"), ("Source", "source")]
        cur = "4k" if c["width"] == -1 else ("source" if c["width"] == 0 else f"{c['width']}x{c['height']}")
        rows = [[IKB(f"{'✅' if cur==v else ''}{lbl}", f"s:res:{v}") for lbl, v in opts]]
        hq = c.get("hq_short", True)
        rows.append([IKB(("✅ " if hq else "❌ ") + "Short videos & trailers above 1080p keep 4K",
                         f"s:hq_short:{0 if hq else 1}")])
        return IKM(rows + [_back_row()])''', "resolution menu")
rep('''        elif key == "res":
            if val == "source":
                set_user(uid, width=0, height=0)
            else:''', '''        elif key == "hq_short":
            set_user(uid, hq_short=bool(int(val)))
            await cq.message.edit_reply_markup(submenu("res", uid, job))
            return await cq.answer("✓")
        elif key == "res":
            if val == "source":
                set_user(uid, width=0, height=0)
            elif val == "4k":
                set_user(uid, width=-1, height=-1)
            else:''', "settings handler")

# ---- other places that show the setting ----
rep('''        f"(cover {c['cover_mode']}, {c['width']}×{c['height']}, logo start "''',
    '''        f"(cover {c['cover_mode']}, {_res_label(c)}, logo start "''', "/save message")
rep('''def _batch_panel_text(uid: int, n: int) -> str:
    c = user_cfg(uid)
    res = "Source" if c["width"] == 0 else f"{c['width']}×{c['height']}"''', '''def _batch_panel_text(uid: int, n: int) -> str:
    c = user_cfg(uid)
    res = _res_label(c)''', "batch panel")

# ---- dub-sync panel ----
rep('''    res = "source" if c["width"] == 0 else f"{c['width']}×{c['height']}"

    # ---- what comes out -------------------------------------------------''', '''    res = "source" if c["width"] == 0 else ("4K" if c["width"] == -1 else f"{c['width']}×{c['height']}")

    # ---- what comes out -------------------------------------------------''', "dub panel res")
rep('''    out_dur = ddur or hdur or 0.0
    vk, br_label = _effective_bitrate(c, out_dur) if out_dur else (0, "—")''', '''    out_dur = ddur or hdur or 0.0
    _dw, _dh, _dnote = _out_size(c, int(hw or 0), int(hh or 0), out_dur)
    if c["width"] not in (0, -1) and not _dnote:
        _dw, _dh = c["width"], c["height"]
    vk, br_label = _effective_bitrate_wh(c, out_dur, _dw, _dh) if out_dur else (0, "—")''', "dub panel bitrate")
rep('''    out_res = f"{hw}×{hh}" if c["width"] == 0 and hw else res''', '''    out_res = f"{hw}×{hh}" if c["width"] == 0 and hw else res
    if (_dnote or c["width"] == -1) and hw:
        res = out_res = f"{_dw}×{_dh}{_dnote}"''', "dub panel out_res")

# ---- dub-sync render: the same size + bitrate the panel showed ----
rep('''        ow = hd_job["w"] if c["width"] == 0 else c["width"]
        oh = hd_job["h"] if c["height"] == 0 else c["height"]''', '''        ow = hd_job["w"] if c["width"] == 0 else c["width"]
        oh = hd_job["h"] if c["height"] == 0 else c["height"]
        # above 1080p (bot20): "4K", or a short dub (trailer) whose HD is above 1080p
        _hq = _out_size(c, int(hd_job.get("w") or 0), int(hd_job.get("h") or 0),
                        float(dub_job.get("duration") or 0.0))
        if c["width"] == -1 or _hq[2]:
            ow, oh = _hq[0], _hq[1]''', "dub render size")
rep('''        _vk, _ = _effective_bitrate(c, _dur)
        _vk, _ = _fit_bitrate(_vk, _dur, c["audio_k"])''', '''        _vk, _ = _effective_bitrate_wh(c, _dur, ow, oh)
        _vk, _ = _fit_bitrate(_vk, _dur, c["audio_k"])''', "dub render bitrate")

# ---- branding render ----
rep('''            vk, _ = _effective_bitrate(c, dur)
            logos = []''', '''            _bw, _bh, _ = _out_size(c, int(job.get("w") or 0), int(job.get("h") or 0), dur)
            vk, _ = _effective_bitrate_wh(c, dur, _bw, _bh)
            logos = []''', "branding render bitrate")
rep('''                width=(job["w"] if c["width"] == 0 else c["width"]),
                height=(job["h"] if c["height"] == 0 else c["height"]),''', '''                width=_bw,
                height=_bh,''', "branding render size")

open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patched", P)
