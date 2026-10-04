"""bot27 = live bot + BLACK CINEMA BARS (a frame wider than 16:9 becomes 16:9 at the same width). Run inside the
bot container:   python3 test_bot_letterbox27.py <live bot dir copy> <bot27 dir copy>
  A. NO BREAK: a 16:9 master, a 4:3 master and a vertical clip -> the engine gets the SAME frame as from the live
     bot, the same steps, the same film bytes, the same report, the same stats, the same brand settings.
  B. A wide master (2.39:1) at the 1920x1080 setting -> live bot: the master's own frame (no bars);
     bot27: the same width, 16:9 height.
  C. A wide master LARGER than the setting -> both bots already give the 16:9 setting (bars), unchanged.
  D. The frame rule on real sizes (CBI 5 1920x804, Ghost 1280x542, 4K 3840x1608, Achcham 1920x818 ...) and on
     garbage: never raises.
  E. The logo stays ON THE PICTURE: the brand settings the engine gets place it the same pixels from the picture's
     edge as before, the caption letters keep their size, the caller's settings are not changed.
  F. Kill switch BIDHAAN_LETTERBOX=0 -> the live bot's frame.
  H. The dialogue-layer mode (renders the HD's own frame, no bars added there) gets the brand settings unchanged.
  G. REAL ffmpeg with the engine's own filter and bot27's frame: 16:9 out, bars exactly where computed, and the
     picture between them is pixel for pixel the master's (nothing cropped, stretched or zoomed).
Prints LETTERBOX27_TESTS ALL PASS."""
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIVE, NEW = sys.argv[1], sys.argv[2]
T = Path(tempfile.mkdtemp(prefix="lb27_"))


def fixture(name, w, h):
    p = T / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=%dx%d:rate=25" % (w, h),
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", "-c:a", "aac", "-shortest", str(p)], check=True)
    return p


FIX = {"16x9": fixture("f169.mp4", 320, 180), "4x3": fixture("f43.mp4", 320, 240),
       "vertical": fixture("fvert.mp4", 180, 320), "wide": fixture("fwide.mp4", 640, 268)}
FAKES = {
    "engine": r'''
import json, os, shutil, sys
a = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write("engine_%s\n" % a[0])
w = os.environ["ENGINE_WORK"]
os.makedirs(w, exist_ok=True)
if a[0] == "analyze":
    json.dump({"conform_offset": {"accepted": True, "reason": "accepted"}, "edl": []}, open(os.path.join(w, "edl.json"), "w"))
if a[0] == "preview" and "--plan-only" not in a:
    rec = {"w": a[a.index("--width") + 1], "h": a[a.index("--height") + 1], "brand": None}
    if "--brand-config" in a:
        rec["brand"] = json.load(open(a[a.index("--brand-config") + 1]))
    json.dump(rec, open(os.environ["ARGS_OUT"], "w"))
    shutil.copy(os.environ["FIXTURE"], os.path.join(os.environ["FAKE_OUT"], a[a.index("--output-name") + 1]))
    open(os.path.join(w, "provenance.json"), "w").write("[]")
    print("Expected duration: 4.0s")
    print("Provenance: %s/provenance.json" % w)
if a[0] == "preview" and "--plan-only" in a:
    print("accidental: 0.0s")
if a[0] == "integrity":
    print("RELEASE APPROVED")
''',
    "switch_audio": 'import os,shutil,sys; a=sys.argv[1:]; open(os.environ["FAKE_LOG"],"a").write("switch_audio\\n"); '
                    'shutil.copy(a[a.index("--video")+1], a[a.index("--out")+1])',
    "opening_restore": 'import os; open(os.environ["FAKE_LOG"],"a").write("opening_restore\\n"); '
                       'print("OPENING_GATE OK"); print("OPENING_RESTORE NOT NEEDED")',
    "restore_head": 'import os; open(os.environ["FAKE_LOG"],"a").write("restore_head\\n"); '
                    'print("t: in the output: 100.0%"); print("DIALOGUE_AUDIT GREEN"); print("RESTORE_HEAD NOT NEEDED")',
    "auto_repair": 'import os; open(os.environ["FAKE_LOG"],"a").write("auto_repair\\n"); print("AUTO_REPAIR NOTHING 0")',
    "tail_restore": 'import os; open(os.environ["FAKE_LOG"],"a").write("tail_restore\\n"); print("TAIL_RESTORE NOT NEEDED")',
    "cut_audit": 'import os; open(os.environ["FAKE_LOG"],"a").write("cut_audit\\n"); print("UNJUSTIFIED CUTS: 0")',
    "frame_audit": r'''
import os
open(os.environ["FAKE_LOG"], "a").write("frame_audit\n")
print("t: 1 shots with HD checked, 0 show the dub's own picture")
print("  ok 1 (100.0%) | wrong clip (moved) 0 | HD the dub lacks (no_hd) 0 | unsure 0")
print("FRAME_AUDIT GREEN")
''',
    "append_credits": 'import os; open(os.environ["FAKE_LOG"],"a").write("append_credits\\n"); '
                      'print("CREDITS: appended 5.0s of the film\'s own end credits")',
    "space_guard": 'import os,sys; open(os.environ["FAKE_LOG"],"a").write("space_guard_%s\\n" % sys.argv[2])',
    "sync_faults": r'''
import json, os, sys
open(os.environ["FAKE_LOG"], "a").write("sync_faults\n")
open(sys.argv[sys.argv.index("--json") + 1], "w").write(json.dumps(
    {"lag": [], "lag_s": 0.0, "pinned": [], "pinned_s": 0.0, "total_s": 0.0}))
''',
}
for k, v in FAKES.items():
    (T / (k + ".py")).write_text(v)
eng = T / "fake_engine"
eng.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, T / "engine.py"))
eng.chmod(0o755)


def load(d, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, "dubsync_job.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    sys.path.insert(0, d)
    spec.loader.exec_module(m)
    sys.path.remove(d)
    m.DUBSYNC = str(eng)
    m.DLG_PY = sys.executable
    for k in ("switch_audio", "restore_head", "opening_restore", "auto_repair", "cut_audit", "frame_audit",
              "append_credits", "tail_restore", "space_guard", "sync_faults"):
        if hasattr(m, k.upper()) or k == "space_guard":
            setattr(m, k.upper(), str(T / (k + ".py")))
    m._quality_report = lambda title: {"locked_pct": 100.0, "shots": 1}
    if hasattr(m, "SHORT_GEOM"):
        m.SHORT_GEOM = str(T / "short_geom.json")
        m.PARKED_WORK = T / "parked"
    if hasattr(m, "HD_WINDOWS_FILE"):
        m.HD_WINDOWS_FILE = str(T / "hd_windows.json")
    return m


os.environ.pop("BIDHAAN_LETTERBOX", None)
old, new = load(LIVE, "job_live"), load(NEW, "job_27")
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:900]), flush=True)
    ok &= bool(cond)


def run(m, tag, fix, w, h, brand=None, mode="conform"):
    d = T / tag
    shutil.rmtree(d, ignore_errors=True)
    (d / "out").mkdir(parents=True)
    work = d / "work"
    work.mkdir()
    log = d / "log.txt"
    log.write_text("")
    args = d / "args.json"
    os.environ.update({"FAKE_LOG": str(log), "FIXTURE": str(fix), "FAKE_OUT": str(d / "out"),
                       "ENGINE_WORK": str(work), "ARGS_OUT": str(args)})
    m.OUT_DIR = d / "out"
    m._work_dir_for = lambda hd, dub: work
    res = asyncio.run(m.run_dubsync(fix, fix, "artest", brand, w, h, 23, lambda *a: None, bitrate_k=500, mode=mode))
    cap = m.summary_caption("artest", res, 4.0, 1000) if res.ok else ""
    rec = json.load(open(args)) if args.exists() else {}
    return res, cap, log.read_text().split(), rec


def film(res):
    return open(res.path, "rb").read() if res.ok and res.path and os.path.exists(res.path) else b""


LOGO = str(T / "logo.png")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:size=60x20", "-frames:v", "1", LOGO], check=True)
BRAND = {"logos": [{"path": LOGO, "corner": "TL", "frac": 0.132, "margin_x": 0.038, "margin_y": 0.1},
                   {"path": LOGO, "corner": "BR", "frac": 0.1, "margin_x": 0.02, "margin_y": 0.05}],
         "scroll_text": "", "caption_scale": 0.016, "logo_start": 45.0, "text_start": 300.0}

# ---- A. no break: 16:9, 4:3, vertical ---------------------------------------------------------------------
for tag, (w, h) in (("16x9", (1920, 1080)), ("16x9", (320, 180)), ("4x3", (1920, 1080)), ("vertical", (1920, 1080)),
                    ("16x9", (0, 0))):
    name = "%s@%dx%d" % (tag, w, h)
    ro, co, lo, ao = run(old, "A_old", FIX[tag], w, h, json.loads(json.dumps(BRAND)))
    rn, cn, ln, an = run(new, "A_new", FIX[tag], w, h, json.loads(json.dumps(BRAND)))
    check("A[%s]: the engine gets the same frame (%sx%s) and the same brand settings" % (name, an.get("w"), an.get("h")),
          ao == an and an.get("w"), (ao, an))
    check("A[%s]: same steps, same film bytes, same report" % name,
          lo == ln and film(ro) == film(rn) and len(film(rn)) > 1000 and co == cn, (lo, ln))
    so = {k: str(v).replace("A_old", "A_") for k, v in ro.stats.items()}
    sn = {k: str(v).replace("A_new", "A_") for k, v in rn.stats.items()}
    check("A[%s]: the same stats (%d values)" % (name, len(sn)), so == sn,
          {k: (so.get(k), sn.get(k)) for k in set(so) | set(sn) if so.get(k) != sn.get(k)})

# ---- B. a wide master at the 1920x1080 setting ---------------------------------------------------------------
ro, co, lo, ao = run(old, "B_old", FIX["wide"], 1920, 1080)
rn, cn, ln, an = run(new, "B_new", FIX["wide"], 1920, 1080)
check("B (control): the live bot renders the master's own frame, no bars (640x268)", (ao["w"], ao["h"]) == ("640", "268"), ao)
check("B: bot27 renders the same width in a 16:9 frame (640x360)", (an["w"], an["h"]) == ("640", "360"), an)
check("B: same steps, the film delivered, the same report", lo == ln and rn.ok and len(film(rn)) > 1000 and co == cn, (lo, ln))
ro, co, lo, ao = run(old, "B2_old", FIX["wide"], 0, 0)
rn, cn, ln, an = run(new, "B2_new", FIX["wide"], 0, 0)
check("B: the 'Source' setting too (live 640x268 -> bot27 640x360)",
      (ao["w"], ao["h"]) == ("640", "268") and (an["w"], an["h"]) == ("640", "360"), (ao, an))

# ---- C. a wide master larger than the setting ---------------------------------------------------------------
ro, co, lo, ao = run(old, "C_old", FIX["wide"], 320, 180)
rn, cn, ln, an = run(new, "C_new", FIX["wide"], 320, 180)
check("C: setting smaller than the master: 320x180 from both (bars were already there)",
      (ao["w"], ao["h"]) == ("320", "180") and ao == an, (ao, an))

# ---- D. the frame rule ----------------------------------------------------------------------------------------
TABLE = [((1920, 804), (1920, 1080, 138)), ((1280, 542), (1280, 720, 89)), ((3840, 1608), (3840, 2160, 276)),
         ((1920, 818), (1920, 1080, 131)), ((1920, 800), (1920, 1080, 140)), ((1920, 1036), (1920, 1080, 22)),
         ((1280, 536), (1280, 720, 92)), ((1920, 1080), (1920, 1080, 0)), ((1280, 720), (1280, 720, 0)),
         ((3840, 2160), (3840, 2160, 0)), ((1440, 1080), (1440, 1080, 0)), ((1080, 1920), (1080, 1920, 0)),
         ((640, 360), (640, 360, 0)), ((854, 356), (854, 480, 62)), ((0, 0), (0, 0, 0)), ((-1, 1080), (-1, 1080, 0))]
bad = [(i, new._frame_169(*i), o) for i, o in TABLE if tuple(new._frame_169(*i)) != o]
check("D: %d real frame sizes -> the right frame and bar" % len(TABLE), not bad, bad)
check("D: every frame with bars is even, 16:9 at the same width, and the bars add up",
      all(o[0] % 2 == 0 and o[1] % 2 == 0 and abs(o[0] * 9 - o[1] * 16) <= 16 and o[1] - i[1] in (2 * o[2], 2 * o[2] + 1)
          for i, o in TABLE if o[2]), TABLE)
try:
    g = [new._frame_169(None, None), new._frame_169("x", 3), new._frame_169(1920.0, 804.0), new._frame_169(1e9, 1)]
    check("D: garbage never raises; unusable input comes back unchanged", g[0] == (None, None, 0) and g[1] == ("x", 3, 0), g)
except Exception as e:
    check("D: garbage never raises", False, repr(e))

# ---- E. the logo stays on the picture ---------------------------------------------------------------------
mine = json.loads(json.dumps(BRAND))
rn, cn, ln, an = run(new, "E_new", FIX["wide"], 1920, 1080, mine)
ro, co, lo, ao = run(old, "E_old", FIX["wide"], 1920, 1080, json.loads(json.dumps(BRAND)))
pic_h, frame_h, bar = 268, 360, 46
px_old = [int(lg["margin_y"] * pic_h) for lg in ao["brand"]["logos"]]
px_new = [int(lg["margin_y"] * frame_h) for lg in an["brand"]["logos"]]
check("E: each logo sits the same pixels from the picture's edge (%s px + the %d px bar)" % (px_old, bar),
      px_new == [bar + p for p in px_old], (px_old, px_new))
check("E: logo width, corner, side margin, start time untouched",
      all(a[k] == b[k] for a, b in zip(ao["brand"]["logos"], an["brand"]["logos"]) for k in ("path", "corner", "frac", "margin_x"))
      and an["brand"]["logo_start"] == 45.0, an["brand"])
check("E: caption letters keep their size (%d px)" % int(pic_h * 0.016),
      int(frame_h * an["brand"]["caption_scale"] + 1e-9) == int(pic_h * 0.016), an["brand"]["caption_scale"])
check("E: the caller's own settings are not changed", mine == BRAND, mine)
check("E (control): the live bot passes the settings as they are", ao["brand"] == BRAND, ao["brand"])
try:
    g = [new._brand_on_picture(None, 804, 1080, 138), new._brand_on_picture({}, 804, 1080, 138),
         new._brand_on_picture({"logos": None}, 804, 1080, 138), new._brand_on_picture({"logos": [{"margin_y": "x"}]}, 804, 1080, 138),
         new._brand_on_picture(BRAND, 804, 1080, 0)]
    check("E: broken brand settings never raise; without bars the settings come back as they are", g[4] == BRAND, g)
except Exception as e:
    check("E: broken brand settings never raise", False, repr(e))

# ---- F. kill switch -----------------------------------------------------------------------------------------
os.environ["BIDHAAN_LETTERBOX"] = "0"
off = load(NEW, "job_27_off")
os.environ.pop("BIDHAAN_LETTERBOX", None)
rf, cf, lf, af = run(off, "F_off", FIX["wide"], 1920, 1080, json.loads(json.dumps(BRAND)))
check("F: BIDHAAN_LETTERBOX=0 -> the live bot's frame (640x268) and brand settings",
      (af["w"], af["h"]) == ("640", "268") and af["brand"] == BRAND, af)

# ---- H. the dialogue-layer mode is left as it was ----------------------------------------------------------
seen = {}
for m_, tag in ((old, "H_old"), (new, "H_new")):
    async def fake_dlg(hd, dub, title, on_progress, register, cancelled, stats, brand_path=None, _tag=tag, _m=m_):
        seen[_tag] = json.load(open(brand_path)) if brand_path else None
        return _m.DubResult(False, None, "dlg fake", stats)
    m_._render_dialogue_layer = fake_dlg
    run(m_, tag, FIX["wide"], 1920, 1080, json.loads(json.dumps(BRAND)), mode="dlg")
check("H: dialogue-layer mode on a wide master: the brand settings it gets are the caller's own, as from the live bot",
      seen.get("H_new") == BRAND and seen.get("H_old") == BRAND, seen)

# ---- G. real ffmpeg, the engine's filter, bot27's frame -----------------------------------------------------
W, H, bar = new._frame_169(640, 268)
vf = "scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:black" % (W, H, W, H)


def gray(extra_vf):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(FIX["wide"]), "-frames:v", "10",
                           "-vf", (extra_vf + "," if extra_vf else "") + "format=gray", "-f", "rawvideo", "-"],
                          capture_output=True).stdout


src, out = gray(""), gray(vf)
n = len(out) // (W * H) if W * H else 0
check("G: real ffmpeg gives a %dx%d frame (16:9) for the 640x268 master, %d frames" % (W, H, n),
      (W, H) == (640, 360) and n >= 5 and len(out) == n * W * H and len(src) == n * 640 * 268, (W, H, len(out), len(src)))
if n:
    top = max(max(out[f * W * H:f * W * H + bar * W]) for f in range(n))
    bot = max(max(out[f * W * H + (H - bar) * W:(f + 1) * W * H]) for f in range(n))
    check("G: black bars of %d px above and below" % bar, top <= 20 and bot <= 20, (top, bot))
    mid = b"".join(out[f * W * H + bar * W:f * W * H + (bar + 268) * W] for f in range(n))
    diff = max(abs(a - b) for a, b in zip(mid, src)) if len(mid) == len(src) else -1
    check("G: the picture between the bars is pixel for pixel the master's (not cropped, stretched or zoomed)",
          diff == 0, diff)

shutil.rmtree(T, ignore_errors=True)
print("LETTERBOX27_TESTS " + ("ALL PASS" if ok else "FAILED"))
sys.exit(0 if ok else 1)
