"""bot22: a SHORT pair (trailer / clip) the placement refused is analysed ONCE more with the engine's short-clip
geometry (John 2026-10-03: the Toxic trailer refused "not the same edit" though it IS the same trailer -- a
screen-recorded player window, 2.37:1 against the HD's 1.90:1, 2.6 % faster).

The engine (head_scan, deployed 2026-10-04, md5 41d1e121) measures a short clip's picture inside the clip only for
titles listed in /opt/dubsync2/short_geom.json; every other film and clip is byte-identical (test_shortclip A, 34
files). This patch lists the title when -- and only when -- the normal analysis refused a pair whose two files are
both 20 s .. 5 min, moves that title's earlier analyses aside (they were made without the geometry; the engine
reuses work-dir caches), and runs the analysis again. The speed retry still comes first, exactly as before.
Usage: python patch_bot_shortgeom22.py <bot dir>     (patches <bot dir>/dubsync_job.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "dubsync_job.py"
s = P.read_text()
if "_geom_retry" in s:
    sys.exit("already patched: %s" % P)
nl = chr(10)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"' + nl,
    '''# bot22 (Toxic trailer 2026-10-03): a SHORT pair the placement refused is analysed once more with the engine's
# short-clip geometry -- the picture measured inside the clip (a screen-recorded player's frame, bars, a different
# shape). The engine applies it only to titles listed in SHORT_GEOM; every other film / clip is unchanged.
SHORT_GEOM = "/opt/dubsync2/short_geom.json"
SHORT_CLIP_S = 300.0                         # the engine's own bound (head_scan.SHORT_CLIP_S)
SHORT_MIN_S = 20.0                           # a real trailer / clip; shorter than this is not a job for it
PARKED_WORK = Path("/opt/dubsync2/scratch/parked_work")


def _media_s(p) -> float:
    """A file's duration in seconds (0.0 when it cannot be read)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(p)], capture_output=True, text=True, timeout=120).stdout
        return float(out.strip().splitlines()[0])
    except Exception:
        return 0.0


def _short_pair(hd, dub) -> bool:
    a, b = _media_s(hd), _media_s(dub)
    return SHORT_MIN_S <= a < SHORT_CLIP_S and SHORT_MIN_S <= b < SHORT_CLIP_S


def _list_short_geom(title: str) -> bool:
    """Add the title to SHORT_GEOM (other titles kept, atomic write). False when it could not be written."""
    import time as _t
    try:
        try:
            with open(SHORT_GEOM) as f:
                reg = json.load(f)
            if not isinstance(reg, dict):
                reg = {}
        except (OSError, ValueError):
            reg = {}
        reg[title] = {"set": _t.strftime("%Y-%m-%d %H:%M"), "why": "short pair refused by the normal analysis"}
        tmp = SHORT_GEOM + ".%d.tmp" % os.getpid()
        with open(tmp, "w") as f:
            json.dump(reg, f, indent=1)
        os.replace(tmp, SHORT_GEOM)
        return True
    except Exception:
        return False


def _park_title_work(title: str, work: Path) -> list:
    """Move this pair's work dir and every other work dir of the title aside (moved, never deleted): their
    thumbs / CLIP / speed caches were made without the geometry and the engine reuses work-dir caches."""
    import time as _t
    moved, dirs = [], {Path(work)}
    try:
        for sp in Path(work).parent.glob("*/speed.json"):
            try:
                if os.path.basename(json.loads(sp.read_text()).get("hd_original", "")).startswith(title + "_hd_"):
                    dirs.add(sp.parent)
            except Exception:
                pass
    except Exception:
        pass
    for d in sorted(dirs):
        if d.is_dir():
            try:
                PARKED_WORK.mkdir(parents=True, exist_ok=True)
                dst = PARKED_WORK / ("%s_%s" % (d.name, _t.strftime("%Y%m%d-%H%M%S")))
                shutil.move(str(d), str(dst))
                moved.append(d.name)
            except Exception:
                pass
    try:
        Path(work).mkdir(parents=True, exist_ok=True)      # the pair's work dir is there again, empty
    except Exception:
        pass
    return moved


RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"
''', "helpers before RESTORE_HEAD")

rep('    _speed_retry = False     # one re-analysis with the speed matched, at most' + nl,
    '    _speed_retry = False     # one re-analysis with the speed matched, at most' + nl
    + '    _geom_retry = False      # bot22: one re-analysis of a refused SHORT pair with its picture measured' + nl,
    "retry flag")

rep('''                    _job_env = dict(os.environ, DUBSYNC2_RETIME_MIN="%.4f" % SPEED_RETRY_MIN)
                    done_weight -= weight
                    i -= 1
                    continue
                _pct = _co.get("unconfirmed_pct")
''', '''                    _job_env = dict(os.environ, DUBSYNC2_RETIME_MIN="%.4f" % SPEED_RETRY_MIN)
                    done_weight -= weight
                    i -= 1
                    continue
                # SELF-REPAIR 2 (bot22): a SHORT pair (both files under 5 min) refused -> its picture was never
                # measured inside the clip (Toxic trailer: a player window, another shape). List the title for the
                # engine's short-clip geometry, move its old analyses aside, analyse once more.
                if not _geom_retry and _short_pair(hd, dub) and _list_short_geom(title):
                    _geom_retry = True
                    stats["short_geom_retry"] = _co.get("unconfirmed_pct")
                    stats["short_geom_parked"] = _park_title_work(title, _work_dir_for(hd, dub))
                    stats.setdefault("contract_healed", []).append(
                        "placement refused on a short clip (%s%% of shots unconfirmed) -- analysed again with its "
                        "picture measured inside the clip (player frame, bars, shape)" % _co.get("unconfirmed_pct"))
                    done_weight -= weight
                    i -= 1
                    continue
                _pct = _co.get("unconfirmed_pct")
''', "short-pair retry after the speed retry")

rep('''                       % (100 * (float(stats["speed_retry"]) - 1.0))
                       if stats.get("speed_retry") else "")
''', '''                       % (100 * (float(stats["speed_retry"]) - 1.0))
                       if stats.get("speed_retry") else "")
                    + ("(Short clip: analysed twice, the second time with its picture measured inside the clip "
                       "-- still refused.)\\n" if "short_geom_retry" in stats else "")
''', "refusal message names the second analysis")

P.write_text(s)
print("patched %s" % P)
