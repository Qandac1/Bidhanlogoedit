"""bot25: the WEAK-ANALYSIS gate -- a bad plan is caught BEFORE the render, not after it.

John 2026-10-04: "that's wasting time ... keep rendering and the next film is wrong again ... I thought you were
preparing the bot". Every bad delivery so far showed its problem in the FIRST stage: the share of shots the
placement could not confirm by their picture -- Toxic 2026 14.39 %, Achcham HEVC 7.8 %, W.M.R. Saguni 6.9 %; the 30
good films 0-2.94 %. The bot read that number only for the final report, after ~2 hours of render.

Right after `analyze` (accepted placement, unconfirmed > WEAK_UNCONF_PCT):
  1. no zoom window known for the title -> measure the zoom now (pair_zoom); a window that lines the films up in
     >= 8 parts AND >= 3 parts more than the plain framing is saved, the title's analyses are moved aside and the
     analysis runs again with that framing (once).
  2. still above STOP_UNCONF_PCT -> NOT rendered: a plain message, nothing wasted.
  3. between the two bounds -> rendered as before; bot24 heads the report NOT CLEAN.
A pair at or below WEAK_UNCONF_PCT (every good film): exactly as before.
Usage: python patch_bot_weakgate25.py <bot dir>     (patches <bot dir>/dubsync_job.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "dubsync_job.py"
s = P.read_text()
if "WEAK_UNCONF_PCT" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''def _media_s(p) -> float:
''', '''# bot25 (John 2026-10-04): a weak analysis is acted on BEFORE the render. Unconfirmed shots after `analyze`:
# 30 good films 0-2.94 %; W.M.R. Saguni 6.9, Achcham HEVC 7.8, Toxic 2026 14.39 (delivered, unusable).
WEAK_UNCONF_PCT = 5.0        # above this the bot first tries its remedy (measure the zoom, analyse again)
STOP_UNCONF_PCT = 10.0       # still above this -> nothing is rendered
ENGINE_ACCEPT_MAX_PCT = 20.0 # the engine itself refuses above 15 %: an "accepted" record above this is not its own
HD_WINDOWS_FILE = "/opt/dubsync2/hd_windows.json"            # the engine's zoom windows (bot.py HD_WINDOWS)
PAIR_ZOOM_CMD = ["/opt/dubsync2/.venv/bin/python", "/opt/dubsync2/pair_zoom.py"]
PAIR_ZOOM_GATE_TIMEOUT_S = 1500
ZOOM_GATE_MIN_PARTS = 8      # as the pair check's PAIR_ZOOM_MIN_PARTS
ZOOM_GATE_MIN_GAIN = 3       # ...and this many parts more than the plain framing (Toxic 10 vs 3; Saguni 10 vs 10)


def _hd_window_of(title: str):
    """The zoom window saved for the title, or None. Never raises."""
    try:
        with open(HD_WINDOWS_FILE) as f:
            e = json.load(f).get(title)
        w = e.get("window") if isinstance(e, dict) else None
        return [float(x) for x in w] if w and len(w) == 4 else None
    except Exception:
        return None


def _save_hd_window(title: str, window) -> bool:
    """Save the title's zoom window in the engine's registry (other titles kept, atomic). False on failure."""
    import time as _t
    try:
        try:
            with open(HD_WINDOWS_FILE) as f:
                reg = json.load(f)
            if not isinstance(reg, dict):
                reg = {}
        except (OSError, ValueError):
            reg = {}
        reg[title] = {"window": [round(float(x), 4) for x in window], "set": _t.strftime("%Y-%m-%d %H:%M"),
                      "by": "weak-analysis gate"}
        tmp = HD_WINDOWS_FILE + ".%d.tmp" % os.getpid()
        with open(tmp, "w") as f:
            json.dump(reg, f, indent=1)
        os.replace(tmp, HD_WINDOWS_FILE)
        return True
    except Exception:
        return False


async def _zoom_search(hd, dub) -> dict:
    """pair_zoom.py's JSON for the pair; any failure = {"zoom_error": ...}. Never raises."""
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *PAIR_ZOOM_CMD, "--hd", str(hd), "--dub", str(dub),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=PAIR_ZOOM_GATE_TIMEOUT_S)
        return json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except Exception as exc:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        return {"zoom_error": "%s: %s" % (type(exc).__name__, exc)}


def _zoom_gain(z: dict) -> bool:
    """A zoomed framing that clearly explains the pair: enough parts, and clearly more than the plain framing."""
    try:
        w = z.get("zoom_window")
        return bool(w) and len(w) == 4 and int(z.get("zoom_parts", 0)) >= ZOOM_GATE_MIN_PARTS \\
            and int(z.get("zoom_parts", 0)) >= int(z.get("plain_small_parts", 99)) + ZOOM_GATE_MIN_GAIN
    except Exception:
        return False


def _media_s(p) -> float:
''', "helpers")

rep('''    _geom_retry = False      # bot22: one re-analysis of a refused SHORT pair with its picture measured
''', '''    _geom_retry = False      # bot22: one re-analysis of a refused SHORT pair with its picture measured
    _zoom_gate = False       # bot25: one zoom search + re-analysis of a WEAK (accepted) analysis
''', "retry flag")

rep('''                    + "Send an HD of the SAME version the dub was made from "
                    "(e.g. the WEB-DL / OTT release, not a PreDVD/cam copy), "
                    "then run /dub again.", stats)

    if mode == "dlg":
''', '''                    + "Send an HD of the SAME version the dub was made from "
                    "(e.g. the WEB-DL / OTT release, not a PreDVD/cam copy), "
                    "then run /dub again.", stats)
            # --- WEAK ANALYSIS GATE (bot25): act on a bad plan BEFORE the render ----------------
            _unc = _co.get("unconfirmed_pct")
            if (_co.get("accepted") and isinstance(_unc, (int, float))
                    and WEAK_UNCONF_PCT < _unc <= ENGINE_ACCEPT_MAX_PCT):
                stats["weak_analysis"] = round(float(_unc), 2)
                if not _zoom_gate and _hd_window_of(title) is None:
                    _zoom_gate = True
                    _z = await _zoom_search(hd, dub)
                    stats["weak_zoom"] = {k: _z.get(k) for k in ("zoom_parts", "plain_small_parts",
                                                                 "zoom_window", "zoom_error") if k in _z}
                    if _zoom_gain(_z) and _save_hd_window(title, _z["zoom_window"]):
                        stats["weak_parked"] = _park_title_work(title, _work_dir_for(hd, dub))
                        stats.setdefault("contract_healed", []).append(
                            "weak analysis (%.1f%% of shots unconfirmed): the Somali copy is ZOOMED -- it shows "
                            "the middle %d%% x %d%% of the HD picture; analysed again with that framing, before "
                            "any render" % (_unc, round(_z["zoom_window"][0] * 100),
                                            round(_z["zoom_window"][1] * 100)))
                        done_weight -= weight
                        i -= 1
                        continue
                if _unc > STOP_UNCONF_PCT:
                    stats["placement"] = "weak analysis: %.2f%% unconfirmed" % _unc
                    return DubResult(
                        False, None,
                        "⛔ NOT rendered — the analysis of this pair is too weak to trust.\\n"
                        "%.1f%% of the Somali copy's shots could not be confirmed in this HD's picture "
                        "(every clean film so far: under 3%%; a film at 14%% came out with the picture half a "
                        "minute behind the sound).\\n" % _unc
                        + ("The zoom was measured too: no zoomed framing explains it.\\n"
                           if "weak_zoom" in stats else "")
                        + "Nothing was rendered, so no time was lost on a film you could not post.\\n"
                        "Most likely this HD is another version / cut than the one the Somali copy was made "
                        "from: send another HD of this film, then run /dub again.", stats)

    if mode == "dlg":
''', "weak-analysis gate after analyze")

P.write_text(s)
print("patched %s" % P)
