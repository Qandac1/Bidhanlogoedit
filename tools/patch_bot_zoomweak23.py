"""bot23: measure the ZOOM whenever a film pair's "same film" evidence is weak (below 8 parts of 10), not only when
the check says "different".

Toxic 2026 (John 2026-10-04, delivered "complete" with 60.2 s of repeats we added, 414 of 4711 shots unmatched,
14.4 % unconfirmed): the Somali copy shows only the middle 77.5 % x 81 % of the HD picture (pair_zoom: 10 of 10 parts
with that window, matched share 0.091 -> 0.305) -- the same channel zoom as Sardar 2022. The plain check gave 6 of
10 parts = "same", so the zoom search (bot18: only on "different") never ran and every picture comparison was made
with the wrong framing. All 44 real unzoomed films in the bot log scored 8-10 parts.

Change (bot.py _same_film_check): the zoom search also runs for a pair with enough keyframe evidence
(chain_steps >= PAIR_MIN_STEPS) and fewer than PAIR_ZOOM_TRY_BELOW parts; its window is used only when the zoomed
framing lines up in >= PAIR_ZOOM_MIN_PARTS parts AND in more parts than the plain check. A pair at 8-10 parts,
a short clip, and a "different" pair: exactly as before.
Usage: python patch_bot_zoomweak23.py <bot dir>     (patches <bot dir>/bot.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "bot.py"
s = P.read_text()
if "PAIR_ZOOM_TRY_BELOW" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what):
    global s
    n = s.count(old)
    assert n == 1, "%s: anchor found %d times" % (what, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''PAIR_ZOOM_MIN_PARTS = 8        # zoomed Sardar 10; wrong pairs 0-3 with every window tried (7 controls)
''', '''PAIR_ZOOM_MIN_PARTS = 8        # zoomed Sardar 10; wrong pairs 0-3 with every window tried (7 controls)
# bot23 (Toxic 2026): a zoomed copy can still read as a WEAK "same" -- 6 of 10 parts, the zoom never measured, 414
# of 4711 shots unmatched and 60 s of repeats delivered. Every real unzoomed film in the log scored 8-10 parts:
# below that the zoom is measured too; its window counts only when it lines the films up in MORE parts.
PAIR_ZOOM_TRY_BELOW = 8
''', "constant")

rep('''    if r["verdict"] == "different":
        # the same film in a ZOOMED copy? (the real HD is the other file when they were swapped)
        z = await _zoom_check(dub if r["swap"] else hd, hd if r["swap"] else dub)
        r["zoom"] = {k: v for k, v in z.items() if k != "zoom_tried"}
        if z.get("zoom_parts", 0) >= PAIR_ZOOM_MIN_PARTS and z.get("zoom_window"):
            r["verdict"] = "same"
            r["hd_window"] = z["zoom_window"]
''', '''    _weak = ("parts" in r and r.get("chain_steps", 0) >= PAIR_MIN_STEPS
             and r["parts"] < PAIR_ZOOM_TRY_BELOW)                      # bot23: weak evidence -> measure the zoom
    if r["verdict"] == "different" or _weak:
        # the same film in a ZOOMED copy? (the real HD is the other file when they were swapped)
        z = await _zoom_check(dub if r["swap"] else hd, hd if r["swap"] else dub)
        r["zoom"] = {k: v for k, v in z.items() if k != "zoom_tried"}
        if (z.get("zoom_parts", 0) >= PAIR_ZOOM_MIN_PARTS and z.get("zoom_window")
                and z.get("zoom_parts", 0) > r.get("parts", 0)):
            r["verdict"] = "same"
            r["hd_window"] = z["zoom_window"]
''', "zoom search on weak evidence")

P.write_text(s)
print("patched %s" % P)
