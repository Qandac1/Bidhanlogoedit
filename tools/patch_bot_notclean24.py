"""bot24: a delivery whose OWN measurements are bad is headed "NOT CLEAN -- do not publish", never "complete".

John 2026-10-04: Toxic 2026 was delivered "dub-sync complete / integrity gate passed / picture matched 100.0 %"
while the same report said 414 of 4711 shots do not match the Somali copy, 60.2 s of footage we added twice and
14.39 % of shots unconfirmed -- and from 1:19:23 the picture runs 31 s behind the sound for minutes. "I thought
the bot was honest ... I was going to post this on my VIP channel."

Calibrated on the 36 film reports in the bot chat (bot_quality_history.py): 30 good deliveries have picture check
95.2-99.3 %, repeats we added 0-5.5 s, unconfirmed 0-2.94 %; the three bad ones (Achcham HEVC 09-27, W.M.R. Saguni
10-02, Toxic 10-04) have <= 93.5 %, >= 22.6 s, >= 6.9 %. Rules (any one = NOT CLEAN):
  picture check ok < 94.5 %   |   repeated footage we added > 10 s   |   unconfirmed > 5 %
The film is still delivered (John decides), the headline and the first lines say plainly what is wrong.
A clean film: every line of the report exactly as before.
Usage: python patch_bot_notclean24.py <bot dir>     (patches <bot dir>/dubsync_job.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "dubsync_job.py"
s = P.read_text()
if "_quality_fail" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''def _contract_missing(st: dict, out) -> list:
''', '''# bot24 (John 2026-10-04, Toxic 2026 delivered "complete" with 414 of 4711 shots not matching the Somali copy,
# 60 s of repeats and the picture 31 s behind the sound for minutes): a delivery is NOT CLEAN when its own
# measurements say so. 30 good films: picture check 95.2-99.3 %, repeats we added 0-5.5 s, unconfirmed 0-2.94 %;
# the 3 bad ones: <= 93.5 %, >= 22.6 s, >= 6.9 %.
PIC_OK_MIN = 94.5            # % of checked shots whose picture is what the Somali copy shows
REPEAT_ADDED_MAX_S = 10.0    # seconds of footage we added a second time
UNCONF_MAX_PCT = 5.0         # % of shots the placement could not confirm by their picture


def _quality_fail(st: dict, title: str) -> list:
    """The measured rules a delivery breaks (plain lines for the top of the report); [] = clean. Never raises."""
    bad = []
    try:
        _pc = st.get("picture_check") or {}
        if _pc.get("ok_pct") is not None and float(_pc["ok_pct"]) < PIC_OK_MIN:
            _n = int(_pc.get("checked") or 0)
            bad.append("picture: only %.1f%% of %s shots show what the Somali copy shows (%d are wrong or unproven)"
                       % (float(_pc["ok_pct"]), _n or "the", max(0, _n - int(_pc.get("ok") or 0))))
    except Exception:
        pass
    try:
        q = _quality_report(title) or {}
    except Exception:
        q = {}
    try:
        if q.get("replay_s") is not None and float(q["replay_s"]) > REPEAT_ADDED_MAX_S:
            bad.append("repeats: %.1f s of footage plays twice (added by the sync, not by the Somali copy)"
                       % float(q["replay_s"]))
        if q.get("offset_unconf") is not None and float(q["offset_unconf"]) > UNCONF_MAX_PCT:
            bad.append("placement: %.1f%% of the shots could not be confirmed by their picture"
                       % float(q["offset_unconf"]))
    except Exception:
        pass
    return bad


def _contract_missing(st: dict, out) -> list:
''', "quality rules")

rep('''    stats["contract_missing"] = _contract_missing(stats, out)
''', '''    stats["contract_missing"] = _contract_missing(stats, out)
    stats["quality_fail"] = _quality_fail(stats, title)          # bot24: measured rules -> "NOT CLEAN"
''', "quality rules run after the contract")

rep('''    _miss = st.get("contract_missing") or []
    if _miss:
        _head = "⛔ dub-sync — INCOMPLETE (see the first lines)"
    lines = [f"🎬 **{title}** — {_head}",
             f"`{int(dur_s//3600)}h {int(dur_s%3600//60):02d}m` · {size_b/1e9:.2f} GB"]
    if _miss:
        lines.append(f"⛔ **{len(_miss)} step(s) did not finish** (each was tried twice):")
        for _x in _miss[:6]:
            lines.append("   · " + _x)
''', '''    _miss = st.get("contract_missing") or []
    _bad = st.get("quality_fail") or []                          # bot24
    if _bad:
        _head = "⛔ dub-sync — NOT CLEAN: do not publish (see the first lines)"
    if _miss:
        _head = "⛔ dub-sync — INCOMPLETE (see the first lines)"
    lines = [f"🎬 **{title}** — {_head}",
             f"`{int(dur_s//3600)}h {int(dur_s%3600//60):02d}m` · {size_b/1e9:.2f} GB"]
    if _miss:
        lines.append(f"⛔ **{len(_miss)} step(s) did not finish** (each was tried twice):")
        for _x in _miss[:6]:
            lines.append("   · " + _x)
    if _bad:
        lines.append(f"⛔ **NOT CLEAN — do not publish.** The film's own checks say ({len(_bad)}):")
        for _x in _bad[:4]:
            lines.append("   · " + _x)
        lines.append("   Most likely this HD is not the version the Somali copy was made from, or the copy is "
                     "reframed/zoomed. Watch the 🔁 spots below; tell Claude before posting.")
''', "headline + first lines")

rep('''                dst = PARKED_WORK / ("%s_%s" % (d.name, _t.strftime("%Y%m%d-%H%M%S")))
                shutil.move(str(d), str(dst))
''', '''                _stamp = _t.strftime("%Y%m%d-%H%M%S")
                dst, _k = PARKED_WORK / ("%s_%s" % (d.name, _stamp)), 0
                while dst.exists():                       # bot24: two moves in one second never collide
                    _k += 1
                    dst = PARKED_WORK / ("%s_%s_%d" % (d.name, _stamp, _k))
                shutil.move(str(d), str(dst))
''', "parked folders get a unique name")

P.write_text(s)
print("patched %s" % P)

# ---- part B (bot.py): a title's saved analyses are moved aside when its zoom window CHANGES -----------------------
# Toxic 2026, 2026-10-04: the re-run with the window would have reused the work dir of the unzoomed run (thumbs,
# CLIP embeds, speed.json are not keyed by the window) -- moved by hand that night.
P = Path(sys.argv[1]) / "bot.py"
s = P.read_text()
rep('''async def _same_film_check(hd: Path, dub: Path) -> dict:
''', '''def _hd_window_now(title: str):
    """The window the registry holds for the title ([zx, zy, cx, cy]) or None. Never raises."""
    try:
        with open(HD_WINDOWS) as f:
            e = json.load(f).get(title)
        w = e.get("window") if isinstance(e, dict) else None
        return [round(float(x), 4) for x in w] if w and len(w) == 4 else None
    except Exception:
        return None


def _sync_hd_window(title: str, window, hd, dub) -> list:
    """Save / clear the title's window (as _set_hd_window); when it CHANGED, the title's saved analyses -- made
    with the other framing -- are moved aside (bot24). Returns the work dirs moved. Never raises."""
    old = _hd_window_now(title)
    _set_hd_window(title, window)
    if old == _hd_window_now(title):
        return []
    try:
        import dubsync_job
        return dubsync_job._park_title_work(title, dubsync_job._work_dir_for(Path(hd), Path(dub)))
    except Exception as exc:
        log.warning("analyses of %s not moved aside after a window change: %s", title, exc)
        return []


async def _same_film_check(hd: Path, dub: Path) -> dict:
''', "bot.py: _sync_hd_window")
rep('''        _set_hd_window(title, pair.get("hd_window"))
''', '''        _sync_hd_window(title, pair.get("hd_window"), hd_src, dub_src)   # bot24: + old analyses aside on a change
''', "bot.py: the job uses it")
P.write_text(s)
print("patched %s" % P)
