"""Proves patch_bot_all on the staged bot WITHOUT importing bot.py (its import wires the dub
queue). The functions under test are lifted out with ast and run against real files.
  T1 _fit_bitrate: 3h40 film @2000k, no premium, MEGA set up -> 2000k kept (MEGA note);
     MEGA not set up -> the old squeeze; a film that fits -> untouched
  T2 _make_thumb: a real delivered film -> a bright, detailed JPEG <= 320 px, < 200 KB, and not
     the (black) first frame
  T3 _make_proxy cancelled mid-encode -> no ffmpeg left, no half-written proxy
Usage (inside the bot container): python3 test_bot_patch.py <staged dir> <film.mp4> <hevc src>"""
import ast
import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path

d, film, src = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, "/app")
ok = True


def lift(path, names, ns):
    tree = ast.parse(open(path, encoding="utf-8").read())
    got = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name in names]
    assert {n.name for n in got} == set(names), "missing: %s" % (set(names) - {n.name for n in got})
    exec(compile(ast.Module(body=got, type_ignores=[]), path, "exec"), ns)


# ---- T1 ------------------------------------------------------------------------------------
import branding  # noqa: E402

class _D:
    mega = True
    def mega_is_configured(self):
        return self.mega

ns = {"os": os, "json": __import__("json"), "asyncio": asyncio, "log": logging.getLogger("t"),
      "TG_LIMIT": int(1.95 * 1024 ** 3), "PREMIUM_LIMIT": int(3.9 * 1024 ** 3),
      "_premium_session": lambda: None, "delivery": _D()}
for k in ("estimate_size_bytes", "bitrate_for_target"):
    if hasattr(branding, k):
        ns[k] = getattr(branding, k)
lift(os.path.join(d, "bot.py"), ["_fit_bitrate", "_run_quiet", "_make_thumb"], ns)
if "estimate_size_bytes" not in ns:
    lift(os.path.join(d, "bot.py"), ["estimate_size_bytes"], ns)

vk, note = ns["_fit_bitrate"](2000, 13202.6, 320)
r = vk == 2000 and "MEGA" in note
print("T1a 3h40 @2000k, MEGA on  ->", vk, repr(note), "PASS" if r else "FAIL")
ok &= r
ns["delivery"].mega = False
vk2, note2 = ns["_fit_bitrate"](2000, 13202.6, 320)
r = vk2 < 2000 and "Telegram" in note2
print("T1b 3h40 @2000k, MEGA off ->", vk2, repr(note2), "PASS (old squeeze kept)" if r else "FAIL")
ok &= r
ns["delivery"].mega = True
vk3, note3 = ns["_fit_bitrate"](2000, 5400.0, 320)
r = vk3 == 2000 and note3 == ""
print("T1c 1h30 @2000k (fits)    ->", vk3, repr(note3), "PASS" if r else "FAIL")
ok &= r
size_gb = ns["estimate_size_bytes"](13202.6, 2000, 320) / 1024 ** 3
print("    Pushpa 2 at the full 2000k: about %.2f GiB (was squeezed to 1039k / 2.07 GB)" % size_gb)

# ---- T2 ------------------------------------------------------------------------------------
from PIL import Image, ImageStat  # noqa: E402
import subprocess  # noqa: E402

dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                            "csv=p=0", film], capture_output=True, text=True).stdout.strip())
t0 = time.time()
th = asyncio.run(ns["_make_thumb"](film, dur))
el = time.time() - t0
if not th:
    print("T2  thumbnail: none made FAIL")
    ok = False
else:
    im = Image.open(th)
    st = ImageStat.Stat(im.convert("L"))
    kb = os.path.getsize(th) / 1024
    first = "/tmp/bt_first.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", film, "-frames:v", "1", "-vf",
                    "scale=320:-2", first])
    f0 = ImageStat.Stat(Image.open(first).convert("L"))
    r = (max(im.size) <= 320 and kb < 200 and 40 <= st.mean[0] <= 210 and st.stddev[0] >= 30)
    print("T2  thumbnail %s %dx%d %.0f KB  mean %.0f  detail %.0f  (first frame: mean %.0f detail %.0f)"
          "  %.1fs  %s" % (th, im.size[0], im.size[1], kb, st.mean[0], st.stddev[0], f0.mean[0],
                          f0.stddev[0], el, "PASS" if r else "FAIL"))
    ok &= r
    os.system("cp %s /tmp/bt_thumb.jpg" % th)

# ---- T3 ------------------------------------------------------------------------------------
ns3 = {"asyncio": asyncio, "re": re, "Path": Path, "os": os, "STALL_TIMEOUT_S": 1800,
       "log": logging.getLogger("t3")}
lift(os.path.join(d, "dubsync_job.py"), ["_make_proxy"], ns3)
dst = Path("/tmp/bt_proxy_test.mp4")
dst.unlink(missing_ok=True)


async def _t3():
    task = asyncio.ensure_future(ns3["_make_proxy"](Path(src), dst, 816))
    await asyncio.sleep(8)
    grew = dst.exists() and dst.stat().st_size > 0
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(1)
    left = []                                   # no pgrep in the bot image: read /proc
    for pid in os.listdir("/proc"):
        if pid.isdigit() and int(pid) != os.getpid():
            try:
                cl = open("/proc/%s/cmdline" % pid, "rb").read().replace(bytes([0]), b" ")
            except OSError:
                continue
            if b"bt_proxy_test.mp4" in cl and b"ffmpeg" in cl:
                left.append(pid)
    return grew, left, dst.exists()

grew, left, exists = asyncio.run(_t3())
r = grew and not left and not exists
print("T3  cancel mid-proxy: was encoding=%s  ffmpeg left=%r  partial file left=%s  %s"
      % (grew, left, exists, "PASS" if r else "FAIL"))
ok &= r
print("BOT_PATCH_TESTS", "ALL PASS" if ok else "FAILED")
