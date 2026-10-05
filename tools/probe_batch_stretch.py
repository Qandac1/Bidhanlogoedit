"""Does the bot's logo-only path (branding.build_filter) STRETCH a video that is not 16:9? Real ffmpeg, the bot's own
filter, a 640x268 test picture with a circle (a circle stays round only when nothing is stretched).
Run inside the bot container:  python3 probe_batch_stretch.py [<bot dir=/app>]
Prints the filter's first part, the output frame, the bars found and the circle's width / height."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/app")
import branding  # noqa: E402

T = Path(tempfile.mkdtemp(prefix="stretch_"))
src = T / "wide.mp4"
# white circle (radius 100) on grey, 640x268
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=c=gray:s=640x268:r=25,format=gray,geq=lum='if(lte(hypot(X-320,Y-134),100),255,60)'",
                "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
cfg = branding.RenderConfig(logos=[], scroll_text="", width=640, height=360)
fc = branding.build_filter(640, 268, 1.0, [], cfg)
print("FILTER", fc.split(";")[0])
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-filter_complex", fc + ";[outv]format=gray[g]",
                      "-map", "[g]", "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True).stdout
W, H = 640, 360
assert len(raw) == W * H, len(raw)
rows = [raw[y * W:(y + 1) * W] for y in range(H)]
bars_top = next(y for y in range(H) if max(rows[y]) > 30)
bars_bot = next(y for y in range(H) if max(rows[H - 1 - y]) > 30)
white_rows = [y for y in range(H) if max(rows[y]) > 200]
cw = max(sum(1 for v in r if v > 200) for r in rows)
ch = len(white_rows)
print("OUT %dx%d | black bar top %d px, bottom %d px | circle %d wide x %d high -> %s"
      % (W, H, bars_top, bars_bot, cw, ch, "ROUND (not stretched)" if abs(cw - ch) <= 6 else
         "STRETCHED x%.2f vertically" % (ch / float(cw))))
