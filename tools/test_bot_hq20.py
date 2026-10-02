"""bot20 = live bot + higher quality above 1080p. Run INSIDE the bot container on two full copies of the bot:
    python3 test_bot_hq20.py <live bot dir copy> <bot20 dir copy>
  A. NO BREAK: every source at or below 1080p (and long 4K films with a fixed resolution), every resolution /
     bitrate / size target / toggle / length: the size and bitrate the render gets == the live bot's rule, and
     the branding panel text == the live bot's text (John's real settings and every combination).
  B. NEW: a 4K short video keeps 3840x2160 at 4x the bitrate; "4K" chosen does it for films; the toggle off
     restores 1080p; a 4096x2160 source fits 3840 wide; a size target stays a ceiling; the menu has 4K + toggle."""
import importlib.util
import itertools
import os
import sys

LIVE, NEW = sys.argv[1], sys.argv[2]


def load(d, name):
    sys.path.insert(0, d)
    os.chdir(d)
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, "bot.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    sys.path.remove(d)
    return m


old = load(LIVE, "bot_live")
new = load(NEW, "bot_20")
fails = 0


def check(ok, what, extra=""):
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what + (("  " + str(extra)[:400]) if extra and not ok else ""), flush=True)


def old_render(c, w, h, dur):
    ow = w if c["width"] == 0 else c["width"]
    oh = h if c["height"] == 0 else c["height"]
    return ow, oh, old._effective_bitrate(c, dur)[0]


def new_render(c, w, h, dur):
    ow, oh, _ = new._out_size(c, w, h, dur)
    return ow, oh, new._effective_bitrate_wh(c, dur, ow, oh)[0]


base = dict(old.DEFAULTS)
small = [(1280, 720), (1920, 1080), (1920, 800), (1920, 1040), (1440, 1080), (854, 480)]
durs = [60.0, 178.0, 600.0, 1500.0, 3000.0, 9000.0]
res_opts = [(1920, 1080), (1280, 720), (0, 0)]
mism, n = [], 0
for (w, h), dur, (rw, rh), br, tgt, hq in itertools.product(small, durs, res_opts, (1500, 2000, 2300, 3500),
                                                             (0.0, 1.9), (True, False)):
    c = dict(base, width=rw, height=rh, bitrate=br, size_target_gb=tgt, hq_short=hq)
    n += 1
    if old_render(c, w, h, dur) != new_render(c, w, h, dur):
        mism.append(((w, h), dur, (rw, rh), br, tgt, hq, old_render(c, w, h, dur), new_render(c, w, h, dur)))
check(not mism, "A: %d combinations at or below 1080p: render size + bitrate identical to the live bot" % n, mism[:3])
mism = []
for (w, h), dur, (rw, rh), br, tgt, hq in itertools.product([(3840, 2160), (3840, 1600)], [1500.0, 3000.0, 9000.0],
                                                             [(1920, 1080), (1280, 720)], (2000, 2300), (0.0, 1.9),
                                                             (True, False)):
    if dur <= new.HQ_SHORT_S:
        continue
    c = dict(base, width=rw, height=rh, bitrate=br, size_target_gb=tgt, hq_short=hq)
    if old_render(c, w, h, dur) != new_render(c, w, h, dur):
        mism.append(((w, h), dur, (rw, rh), old_render(c, w, h, dur), new_render(c, w, h, dur)))
check(not mism, "A: long 4K films with 1080p/720p chosen: identical to the live bot (stay at the setting)", mism[:3])

# the real panel text, John's own settings and the grid
uid = 8000904269
diff = []
for (w, h), dur in itertools.product(small, durs):
    job = {"name": "t.mp4", "duration": dur, "w": w, "h": h, "src": "", "work": ""}
    a, b = old.panel(uid, job)[0], new.panel(uid, job)[0]
    if a != b:
        diff.append(((w, h), dur))
check(not diff, "A: branding panel text identical for every source at or below 1080p (John's settings)", diff[:3])
c0 = old.user_cfg(uid)
print("   John's settings: %s, %dk, size target %s, fps %s" % (old._res_label(c0) if hasattr(old, "_res_label")
      else ("Source" if c0["width"] == 0 else "%dx%d" % (c0["width"], c0["height"])), c0["bitrate"],
      c0["size_target_gb"], c0["fps"]))

# B. the new cases
c = dict(base, width=1920, height=1080, bitrate=2300, size_target_gb=0.0, hq_short=True)
check(new_render(c, 3840, 2160, 178.0) == (3840, 2160, 9200), "B: 4K short video (2:58) keeps 3840x2160 at 9200k",
      new_render(c, 3840, 2160, 178.0))
check(new_render(dict(c, hq_short=False), 3840, 2160, 178.0) == (1920, 1080, 2300),
      "B: toggle off -> 1920x1080 at 2300k as before")
check(new_render(c, 3840, 2160, 9000.0) == (1920, 1080, 2300), "B: 4K film with 1080p chosen stays 1920x1080 2300k")
c4 = dict(c, width=-1, height=-1)
check(new_render(c4, 3840, 2160, 9000.0) == (3840, 2160, 9200), "B: '4K' chosen: a 4K film renders 3840x2160 9200k")
check(new_render(c4, 1920, 1080, 9000.0) == (1920, 1080, 2300), "B: '4K' chosen, 1080p source: 1920x1080 2300k")
check(new_render(c4, 1280, 720, 600.0) == (1920, 1080, 2300), "B: '4K' chosen, 720p source: as 1080p chosen today")
check(new_render(c, 4096, 2160, 178.0)[:2] == (3840, 2024), "B: 4096x2160 fits 3840 wide (3840x2024)",
      new_render(c, 4096, 2160, 178.0))
ct = dict(c4, size_target_gb=1.9)
r = new_render(ct, 3840, 2160, 9000.0)
check(r[2] < 9200 and new._effective_bitrate_wh(ct, 9000.0, 3840, 2160)[1].endswith("GB)"),
      "B: a size target is still a ceiling at 4K (%dk)" % r[2])
job4 = {"name": "video.mp4", "duration": 178.0, "w": 3840, "h": 2160, "src": "", "work": ""}
t = new.panel(uid, job4)[0]
check("3840×2160 (short video: kept at its source size)" in t and "9200k" in t,
      "B: the panel shows the 4K render of John's 4K video", [x for x in t.splitlines() if "🖼" in x or "💾" in x])
kb = new.submenu("res", uid, job4)
labels = [b.text for row in kb.inline_keyboard for b in row]
check(any("4K" == l.replace("✅", "") for l in labels) and any("keep 4K" in l for l in labels)
      and any("1920×1080" in l for l in labels) and any("Source" in l for l in labels),
      "B: Resolution menu: 4K, 1920x1080, 1280x720, Source + the short-video toggle", labels)
# the dub-sync panel: same text for every pair at or below 1080p and for 4K films; a 4K HD with a short dub
# (a trailer dub) shows the 4K render
def dub_text(m, hd, du):
    meta = {"HD": ("hd.mkv",) + hd, "DU": ("dub.mp4",) + du}
    m._vmeta = lambda msg: meta[msg]
    m._dub_size_warning = lambda msgs: ""
    m._dubsel[uid] = {"msgs": ["HD", "DU"], "hd_i": 0, "brand": False}
    return m._dub_panel_text(uid)


ddiff = []
pairs = [((1920, 1080, 9000.0), (1280, 720, 8800.0)), ((1920, 800, 7200.0), (854, 480, 7000.0)),
         ((1280, 720, 6000.0), (1280, 720, 5900.0)), ((3840, 2160, 9847.0), (854, 480, 9645.0)),
         ((1920, 1080, 180.0), (1280, 720, 175.0)), ((3840, 1600, 9000.0), (1280, 536, 8800.0))]
for hd, du in pairs:
    a_, b_ = dub_text(old, hd, du), dub_text(new, hd, du)
    if a_ != b_:
        ddiff.append((hd, du, [x for x in b_.splitlines() if "Output" in x or "·" in x][:3]))
check(not ddiff, "A: dub-sync panel identical for every pair at or below 1080p and 4K films (John's settings)", ddiff)
t = dub_text(new, (3840, 2160, 180.0), (1280, 720, 176.0))
check("3840×2160 (short video: kept at its source size)" in t and "9200k" in t,
      "B: a 4K HD with a short dub (trailer) shows the 4K render", [x for x in t.splitlines() if "Output" in x])
print("HQ20_TESTS", "ALL PASS" if not fails else "%d FAILED" % fails)
