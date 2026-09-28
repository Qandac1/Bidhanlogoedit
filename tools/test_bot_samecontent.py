"""Proves patch_bot_samecontent on the real prepare_inputs (bot container):
  identical re-send  -> raw/ file kept (same inode, same mtime) -> the engine's caches stay valid
  same size, different content -> replaced
  different size -> replaced
Usage: python3 test_bot_samecontent.py <patched bot dir>      prints SAMECONTENT_TESTS ALL PASS"""
import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

d = sys.argv[1]
spec = importlib.util.spec_from_file_location("jsc", os.path.join(d, "dubsync_job.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["jsc"] = m
sys.path.insert(0, d)
spec.loader.exec_module(m)
T = Path(tempfile.mkdtemp(prefix="sctest_"))
m.RAW_DIR = T / "raw"


def clip(p, freq, secs=3):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=%d" % freq, "-t", str(secs), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p)], check=True)


ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)))
    ok &= bool(cond)


d1 = T / "dl1"
d1.mkdir()
clip(d1 / "hd.mp4", 440)
clip(d1 / "dub.mp4", 660)
hd, dub = asyncio.run(m.prepare_inputs(d1 / "hd.mp4", d1 / "dub.mp4", "sctest"))
ino, mt = os.stat(hd).st_ino, os.stat(hd).st_mtime
time.sleep(1.2)
d2 = T / "dl2"                        # the re-send: a NEW download of the same bytes
d2.mkdir()
shutil.copy(d1 / "hd.mp4", d2 / "hd.mp4")
shutil.copy(d1 / "dub.mp4", d2 / "dub.mp4")
os.utime(d2 / "hd.mp4")
hd2, _ = asyncio.run(m.prepare_inputs(d2 / "hd.mp4", d2 / "dub.mp4", "sctest"))
check("identical re-send keeps raw/ (inode + mtime)", os.stat(hd2).st_ino == ino and os.stat(hd2).st_mtime == mt,
      (os.stat(hd2).st_ino, ino))
d3 = T / "dl3"                        # same size, different bytes
d3.mkdir()
b = bytearray(open(d1 / "hd.mp4", "rb").read())
b[len(b) // 2 + 1000] ^= 0xFF
b[-100] ^= 0xFF
open(d3 / "hd.mp4", "wb").write(bytes(b))
shutil.copy(d1 / "dub.mp4", d3 / "dub.mp4")
hd3, _ = asyncio.run(m.prepare_inputs(d3 / "hd.mp4", d3 / "dub.mp4", "sctest"))
check("same size, different content -> replaced", open(hd3, "rb").read() == bytes(b))
d4 = T / "dl4"                        # a different film (different size)
d4.mkdir()
clip(d4 / "hd.mp4", 880, secs=4)
shutil.copy(d1 / "dub.mp4", d4 / "dub.mp4")
hd4, _ = asyncio.run(m.prepare_inputs(d4 / "hd.mp4", d4 / "dub.mp4", "sctest"))
check("different film -> replaced", os.path.getsize(hd4) == os.path.getsize(d4 / "hd.mp4"))
shutil.rmtree(T, ignore_errors=True)
print("SAMECONTENT_TESTS", "ALL PASS" if ok else "FAILED")
