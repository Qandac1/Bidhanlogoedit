"""bot36, before it is installed: WOULD THE STUDIO SHOW THE FILM THAT RUNS NOW?  (John opened it on "Dub-sync films"
while Stumped was running and saw an empty picture.)
Run in a container of the bot's image:  python3 check_dub_video36.py <patched bot dir> <out dir> [uid]
Loads the patched bot.py (nothing is started or sent), gives it the REAL dub queue as the running bot has it in
memory (read from the queue's file, read only), asks _studio_dub_video(uid) which film it would show, and cuts its 24
pictures into <out dir>/t/<token>/ exactly as /studio would.
Prints  DUB_VIDEO file=<name> seconds=<n> | pictures <n> done=<bool> | sizes <min>..<max> bytes | <w>x<h>"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys

NEW, OUT = sys.argv[1], sys.argv[2]
os.environ["BIDHAAN_WEB_PUBLIC"] = OUT
sys.path.insert(0, NEW)
os.chdir(NEW)
spec = importlib.util.spec_from_file_location("bot_dubcheck36", os.path.join(NEW, "bot.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["bot_dubcheck36"] = m
spec.loader.exec_module(m)
import dub_queue as dq  # noqa: E402

q = json.load(open("/app/data/dub_queue.json"))
dq._q[:] = q
uid = int(sys.argv[3]) if len(sys.argv) > 3 else int(next((e["uid"] for e in reversed(q) if e.get("state") == "running"), q[-1]["uid"]))
m._ui_profile[uid] = "dub"                     # in THIS process only
src, dur = m._studio_dub_video(uid)
if not src:
    print("DUB_VIDEO none: no HD film of this user's jobs is on the server")
    sys.exit(0)
token = "dubcheck36" + os.urandom(5).hex()
d = os.path.join(OUT, "t", token)
os.makedirs(d, exist_ok=True)


async def go():
    ok = await m._studio_frames_start(uid, src, dur, d, token)
    tk = m._studio_tasks.get(uid)
    if tk is not None:
        await tk
    return ok


ok = asyncio.run(go())
fj = json.load(open(os.path.join(d, "frames.json"))) if os.path.exists(os.path.join(d, "frames.json")) else {}
sizes = [os.path.getsize(os.path.join(OUT, x["img"])) for x in fj.get("frames", [])]
wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                     os.path.join(d, "frame.jpg")], capture_output=True, text=True).stdout.strip()
print("DUB_VIDEO file=%s seconds=%.0f | first picture %s | pictures %d done=%s | sizes %s..%s bytes | %s | folder %s"
      % (os.path.basename(src), dur, ok, len(sizes), fj.get("done"), min(sizes or [0]), max(sizes or [0]), wh, d))
