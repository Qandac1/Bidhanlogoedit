"""bot39b, dubsync_job.py: a pair REFUSED by the engine's frame check while the picture search FOUND its shots gets the
zoom remedy the weak-analysis gate already has (bot25) -- measure the zoom; a window that lines the films up in time
and that ORB features measure as a real zoom -> saved, the old analyses moved aside, analysed once more (the engine's
own frame check judges again). Anything else: the refusal exactly as before (+ one line saying the zoom was measured).

Why (John 10-17, "some movie bot was refuse"): Aegan 2008 was refused twice (10-12, 10-14) "84% of the dub's shots
could not be found in this HD's picture" -- yet the picture search had matched 96% of its shots strongly, and its kept
thumbnails show the Fanproj copy is a ZOOMED window of the HD: the middle 77.5% x 75%, 7% up (54 shot pairs, spread
0.01; Sardar 77 x 80, Toxic 77.5 x 81, Mandaadi 80 x 82 -- the windows the engine already uses for those). No window
was saved for Aegan, so the frame check compared the whole HD picture with a zoomed copy. The bot measures the zoom
only when the pair check is weak (< 8 parts) and the weak-analysis remedy only for ACCEPTED analyses; a refusal
returned before either. And the remedy's rule "the zoom lines up 3 parts MORE than the plain framing" cannot pass a
zoomed copy the plain check already scored high -- for a refused pair the frame check has already shown the plain
framing does not place the shots, so a window counts there when it lines up all through (>= 8 parts) and ORB measures
a real zoom (the copy shows at most 92% of the HD's width; grid and ORB within 0.05).
Only pairs whose shots were found this well (>= 90%: Aegan 96; the right refusals measured lower -- Alias Janaki 73,
a different trailer cut 60, old tapes Patth 77 / Stumped 84) and not short clips (they have their own retry).
v2: on Aegan itself the zoom search found the right window but only 5 of 10 parts lined up (a poor 848x464 MPEG-4
copy, watermarks: 11 % of keyframes). Then the window is measured on the ANALYSIS's own matched shots
(tools/edl_zoom.py: ORB on frame pairs the analysis matched, pair_zoom._orb_window) and counts when ORB measured it on
>= 6 pairs, it is a real zoom of the copy's own shape, and the zoom search's best grid window agrees (Aegan: 10 pairs,
77.8 % x 88.5 %, shape off by 0.000, grid 75 %; a clean unzoomed film: 1.00 -> no).
    python3 patch_bot_refusedzoom39.py <bot dir>   -> PATCHED dubsync_job (refuses when the file is not the expected one)"""
import sys

p = sys.argv[1].rstrip("/") + "/dubsync_job.py"
s = open(p, newline="").read()
if "\r\n" in s or "_refused_zoom_ok" in s:
    sys.exit("dubsync_job.py is not the expected one (CRLF or already patched) - nothing changed")

A_OLD = """                _pct = _co.get("unconfirmed_pct")
                stats["placement"] = str(_co.get("reason", ""))
"""
A_NEW = """                # SELF-REPAIR 3 (bot39, Aegan 10-12 / 10-14): refused by the FRAME check while the picture search FOUND
                # the shots (Aegan: 96% strong, 84% unconfirmed by frames) = a ZOOMED Somali copy no window described.
                # The weak-analysis remedy (bot25) for a refused pair: measure the zoom; a real zoom that lines the films
                # up -> saved, old analyses moved aside, analysed once more (the engine's frame check judges again).
                if not _zoom_gate and _hd_window_of(title) is None and not _short_pair(hd, dub):
                    _sh = _strong_share(_work_dir_for(hd, dub))
                    if _sh is not None and _sh >= REFUSED_ZOOM_MIN_STRONG:
                        _zoom_gate = True
                        _z = await _zoom_search(hd, dub)
                        stats["refused_zoom"] = {k: _z.get(k) for k in ("zoom_parts", "plain_small_parts", "zoom_window",
                                                                        "zoom_orb_window", "zoom_orb_parts", "zoom_error")
                                                 if k in _z}
                        stats["refused_zoom"]["found_share"] = round(_sh, 3)
                        _win = _z.get("zoom_window") if _refused_zoom_ok(_z) else None
                        if _win is None:
                            # the zoom search's own evidence is too weak on a poor copy (Aegan: the right window, 5 of
                            # 10 parts): the window measured on the ANALYSIS's matched shots (tools/edl_zoom.py)
                            _e = await _edl_zoom(_work_dir_for(hd, dub), hd, dub)
                            stats["refused_zoom"]["edl"] = {k: _e.get(k) for k in ("orb_window", "orb_pairs", "pairs_tried",
                                                                                   "shape_dev", "window", "error") if k in _e}
                            if _edl_zoom_ok(_e, _z):
                                _win = _e["window"]
                        if _win and _save_hd_window(title, _win):
                            stats["refused_zoom"]["used_window"] = [round(float(x), 4) for x in _win]
                            stats["refused_parked"] = _park_title_work(title, _work_dir_for(hd, dub))
                            stats.setdefault("contract_healed", []).append(
                                "placement refused (%s%% of shots unconfirmed by their frames) although the picture "
                                "search found %d%% of the shots: the Somali copy is ZOOMED -- it shows the middle %d%% x "
                                "%d%% of the HD picture; analysed again with that framing"
                                % (_co.get("unconfirmed_pct"), round(100 * _sh), round(float(_win[0]) * 100),
                                   round(float(_win[1]) * 100)))
                            done_weight -= weight
                            i -= 1
                            continue
                _pct = _co.get("unconfirmed_pct")
                stats["placement"] = str(_co.get("reason", ""))
"""
B_OLD = """                    + ("(Short clip: analysed twice, the second time with its picture measured inside the clip "
                       "-- still refused.)\\n" if "short_geom_retry" in stats else "")
"""
B_NEW = """                    + ("(Short clip: analysed twice, the second time with its picture measured inside the clip "
                       "-- still refused.)\\n" if "short_geom_retry" in stats else "")
                    + ("(%s)\\n" % _refused_zoom_note(stats) if "refused_zoom" in stats else "")
"""
C_OLD = """def _media_s(p) -> float:
"""
C_NEW = '''REFUSED_ZOOM_MIN_STRONG = 0.90  # bot39: a REFUSED pair whose shots the picture search found this well (Aegan 0.96;
                                # the right refusals: Alias Janaki 0.73, a different trailer cut 0.60, Patth 0.77, Stumped 0.84)
REFUSED_ZOOM_MAX_SHARE = 0.92   # ...gets a window only when the copy shows at most this share of the HD's width


def _strong_share(work) -> "float | None":
    """Share of the body shots the picture search matched strongly (visual_conf >= 0.70) in the work dir's edl.json;
    None when there is no such record or fewer than 50 body shots. Never raises."""
    try:
        edl = json.loads((Path(work) / "edl.json").read_text()).get("edl") or []
        body = [e for e in edl if not e.get("is_intro_cluster") and e.get("hd_idx") is not None]
        if len(body) < 50:
            return None
        return sum(1 for e in body if (e.get("visual_conf") or 0) >= 0.70) / float(len(body))
    except Exception:
        return None


def _refused_zoom_ok(z: dict) -> bool:
    """For a pair the frame check REFUSED while its shots were found: the zoom search's window counts when it clearly
    beats the plain framing (_zoom_gain), or when it lines the films up all through (>= ZOOM_GATE_MIN_PARTS, grid and
    ORB) and ORB features measure a REAL zoom (at most REFUSED_ZOOM_MAX_SHARE of the HD's width, grid within 0.05)."""
    try:
        if _zoom_gain(z):
            return True
        w, o = z.get("zoom_window"), z.get("zoom_orb_window")
        return (bool(w) and len(w) == 4 and bool(o) and len(o) == 4
                and int(z.get("zoom_parts", 0)) >= ZOOM_GATE_MIN_PARTS
                and int(z.get("zoom_orb_parts", 0)) >= ZOOM_GATE_MIN_PARTS
                and float(o[0]) <= REFUSED_ZOOM_MAX_SHARE and abs(float(o[0]) - float(w[0])) <= 0.05)
    except Exception:
        return False


EDL_ZOOM_CMD = ["/opt/dubsync2/.venv/bin/python", "/opt/dubsync2/tools/edl_zoom.py"]
EDL_ZOOM_TIMEOUT_S = 900
EDL_ZOOM_MIN_PAIRS = 6        # frame pairs ORB measured (Aegan 10 of 60; a clean unzoomed film 54 of 60, window 1.0)
EDL_ZOOM_MAX_SHAPE_DEV = 0.03 # a zoom keeps the copy's shape: |zy - zx * HD aspect / dub aspect| (Aegan 0.000)
EDL_ZOOM_GRID_AGREE = 0.06    # ...and the zoom search's own best grid window says the same width (Aegan 0.75 vs 0.778)


async def _edl_zoom(work, hd, dub) -> dict:
    """tools/edl_zoom.py's JSON for the pair (the window ORB measures on the analysis's matched shots); any failure =
    {"error": ...}. Never raises."""
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *EDL_ZOOM_CMD, str(work), str(hd), str(dub),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=EDL_ZOOM_TIMEOUT_S)
        return json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except Exception as exc:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _edl_zoom_ok(e: dict, z: dict) -> bool:
    """The analysis-measured window counts when ORB measured it on enough frame pairs, it is a real zoom (at most
    REFUSED_ZOOM_MAX_SHARE of the HD's width) of the copy's own shape, and the zoom search's best grid window agrees."""
    try:
        o, w, g = e.get("orb_window"), e.get("window"), z.get("zoom_grid_window")
        return (bool(o) and len(o) == 4 and bool(w) and len(w) == 4 and bool(g) and len(g) == 4
                and int(e.get("orb_pairs", 0)) >= EDL_ZOOM_MIN_PAIRS
                and float(o[0]) <= REFUSED_ZOOM_MAX_SHARE
                and float(e.get("shape_dev", 9.0)) <= EDL_ZOOM_MAX_SHAPE_DEV
                and abs(float(g[0]) - float(o[0])) <= EDL_ZOOM_GRID_AGREE)
    except Exception:
        return False


def _refused_zoom_note(stats: dict) -> str:
    """One line for the refusal message: what the zoom remedy did."""
    z = stats.get("refused_zoom") or {}
    w = z.get("used_window")
    if stats.get("refused_parked") is not None and w:
        return ("Analysed twice: the second time with the Somali copy's zoom (the middle %d%% x %d%% of the HD "
                "picture) -- still refused." % (round(w[0] * 100), round(w[1] * 100)))
    return "The zoom was measured too: no zoomed framing explains it."


def _media_s(p) -> float:
'''
for old, new in ((A_OLD, A_NEW), (B_OLD, B_NEW), (C_OLD, C_NEW)):
    if s.count(old) != 1:
        sys.exit("dubsync_job.py is not the expected one (%r found %d times) - nothing changed" % (old[:50], s.count(old)))
    s = s.replace(old, new)
open(p, "w", newline="").write(s)
print("PATCHED dubsync_job")
