"""Which escaping gets a caption with %, backslash, colon, comma, brackets, = and ; through ffmpeg's drawtext?
Run anywhere with ffmpeg + DejaVu:  python3 probe_caption_escape.py
For each text and each candidate: does ffmpeg draw it without an error? (white pixels > 0, stderr clean)"""
import subprocess

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TEXTS = ["BIDHAAN TV 0619", "50% OFF", "A\B", "A:B, [x]=1;c", "100%% sure", "it's 5% \ ok: yes"]


def old(t):
    return "", t.replace("\\", "\\\\").replace(":", "\:").replace("'", "’").replace("%", "\%")


def none(t):
    return "expansion=none:", t.replace("\\", "\\\\").replace(":", "\:").replace("'", "’")


for t in TEXTS:
    for name, fn in (("old", old), ("expansion=none", none)):
        xp, e = fn(t)
        fc = "[0:v]drawtext=fontfile=%s:%stext='%s':fontcolor=white:fontsize=30:x=10:y=20[o];[o]format=gray[g]" % (FONT, xp, e)
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=640x80:r=25", "-filter_complex", fc,
                            "-map", "[g]", "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True)
        white = sum(1 for v in r.stdout if v > 200)
        cols = [x for x in range(640) if any(r.stdout[y * 640 + x] > 200 for y in range(80))] if len(r.stdout) == 640 * 80 else []
        print("%-22r %-15s drawn %5d px, width %3d | %s" % (t, name, white, (max(cols) - min(cols) + 1) if cols else 0,
                                                           (r.stderr.decode()[:70].replace("\n", " ") or "no error")))
