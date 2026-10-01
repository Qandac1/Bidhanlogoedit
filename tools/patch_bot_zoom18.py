"""bot18: a ZOOMED Somali copy is the same film (Sardar 2022, John 2026-10-01: "the movies are the same, why does
it say this"). The channel's copy shows only the middle 77 % x 80 % of the HD picture; the pair check compares
whole pictures, so it read "1 of 10 parts -- different films" and refused.
  * when the pair check says "different", /opt/dubsync2/pair_zoom.py tries windows of the HD picture; a window
    that lines the two up all through the film (>= 8 of 10 parts; wrong pairs stay 0-3 with every window, 7
    controls) makes the pair "same", with that window.
  * the window is saved for the title in /opt/dubsync2/hd_windows.json -- the engine compares the HD's pictures
    cut to it (head_scan._crop_of); every other job clears its title's entry, so a window never outlives its pair.
  * John is told: the copy is zoomed in; the film keeps the full HD picture.
Usage: python3 patch_bot_zoom18.py <bot.py>"""
import sys

P = sys.argv[1]
s = open(P, encoding="utf-8").read()
if "PAIR_ZOOM" in s:
    raise SystemExit("already patched")


def rep(old, new, what):
    global s
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


rep('''PAIR_MIN_STEPS = 40            # fewer steps (trailers, short clips) = not enough evidence
''', '''PAIR_MIN_STEPS = 40            # fewer steps (trailers, short clips) = not enough evidence
# A ZOOMED Somali copy (Sardar 2022: the middle 77 % x 80 % of the HD picture) reads as "different": the zoom
# search tries windows of the HD picture; only a window that lines the films up all through counts.
PAIR_ZOOM = ["/opt/dubsync2/.venv/bin/python", "/opt/dubsync2/pair_zoom.py"]
PAIR_ZOOM_TIMEOUT_S = 900
PAIR_ZOOM_MIN_PARTS = 8        # zoomed Sardar 10; wrong pairs 0-3 with every window tried (7 controls)
HD_WINDOWS = "/opt/dubsync2/hd_windows.json"


async def _zoom_check(hd: Path, dub: Path) -> dict:
    """pair_zoom.py's JSON (zoom_parts, zoom_window, ...); any failure = {"zoom_error": ...}, never raises."""
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *PAIR_ZOOM, "--hd", str(hd), "--dub", str(dub),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=PAIR_ZOOM_TIMEOUT_S)
        return json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except Exception as exc:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        return {"zoom_error": f"{type(exc).__name__}: {exc}"}


def _set_hd_window(title: str, window) -> None:
    """Save (window) or clear (None) the title's HD window for the engine. Never raises."""
    try:
        try:
            with open(HD_WINDOWS) as f:
                reg = json.load(f)
            if not isinstance(reg, dict):
                reg = {}
        except (OSError, ValueError):
            reg = {}
        if window:
            reg[title] = {"window": [round(float(x), 4) for x in window], "set": time.strftime("%Y-%m-%d %H:%M")}
        elif title in reg:
            reg.pop(title)
        else:
            return
        tmp = HD_WINDOWS + ".%d.tmp" % os.getpid()
        with open(tmp, "w") as f:
            json.dump(reg, f, indent=1)
        os.replace(tmp, HD_WINDOWS)
    except Exception as exc:
        log.warning("hd window not saved for %s: %s", title, exc)
''', "zoom constants + helpers")

rep('''    elif r["parts"] >= PAIR_SAME_MIN_PARTS:
        r["verdict"] = "same"
    else:
        r["verdict"] = "unknown"
    return r
''', '''    elif r["parts"] >= PAIR_SAME_MIN_PARTS:
        r["verdict"] = "same"
    else:
        r["verdict"] = "unknown"
    if r["verdict"] == "different":
        # the same film in a ZOOMED copy? (the real HD is the other file when they were swapped)
        z = await _zoom_check(dub if r["swap"] else hd, hd if r["swap"] else dub)
        r["zoom"] = {k: v for k, v in z.items() if k != "zoom_tried"}
        if z.get("zoom_parts", 0) >= PAIR_ZOOM_MIN_PARTS and z.get("zoom_window"):
            r["verdict"] = "same"
            r["hd_window"] = z["zoom_window"]
    return r
''', "zoom search on a 'different' verdict")

rep('''        hd_src, dub_src = Path(hd_job["src"]), Path(dub_job["src"])
        title = dubsync_job._slug(hd_job["name"])
''', '''        hd_src, dub_src = Path(hd_job["src"]), Path(dub_job["src"])
        title = dubsync_job._slug(hd_job["name"])
        # the engine compares the HD cut to a zoomed copy's window (bot18); any other pair clears it
        _set_hd_window(title, pair.get("hd_window"))
        if pair.get("hd_window"):
            try:
                await status.reply(
                    "🔍 The Somali copy is **zoomed in** — it shows only the middle %d %% × %d %% of the HD "
                    "picture. Same film: the pictures line up in %d of 10 parts with that framing. Your film "
                    "keeps the **full HD picture**." % (round(pair["hd_window"][0] * 100),
                                                         round(pair["hd_window"][1] * 100),
                                                         int(pair.get("zoom", {}).get("zoom_parts", 0))))
            except Exception:
                pass
''', "save the window + tell John")

open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patched", P)
