"""WAIT UNTIL THE BOT CAN BE RESTARTED WITHOUT TAKING ANYTHING FROM JOHN (before a deploy).
All of these, three checks in a row (one a minute):
  the bot is idle            /opt/Bidhanlogoedit/tools/bot_idle.sh prints BOT IDLE (no render, no engine, no download)
  no film waits in the queue  dub_queue.json holds no item that is waiting or running
  the chat is quiet          the last message between John and the bot is --quiet minutes old or more (default 10)
  no panel waits for a tap   the bot's last message is not a "Ready to render" / "videos queued" / dub-sync panel
                              (a restart forgets a video that waits in a panel)
Usage (host, system python): python3 wait_quiet.py [--quiet 10] [--max-hours 6]
Prints a line when something changes and  WAIT_QUIET OK <time>  |  WAIT_QUIET TIMEOUT. Reads only; sends nothing."""
import datetime
import json
import subprocess
import sys
import time

a = sys.argv[1:]
QUIET = float(a[a.index("--quiet") + 1]) if "--quiet" in a else 10.0
MAXH = float(a[a.index("--max-hours") + 1]) if "--max-hours" in a else 6.0
QUEUE = "/var/lib/docker/volumes/bidhanlogoedit_bot_data/_data/dub_queue.json"
PANELS = ("Ready to render", "videos queued", "Send its HD master", "Send the Somali", "Which one is the HD", "Open Studio")


def idle():
    r = subprocess.run(["sh", "/opt/Bidhanlogoedit/tools/bot_idle.sh"], capture_output=True, text=True)
    return "BOT IDLE" in r.stdout


def queue_busy():
    try:
        d = json.load(open(QUEUE))
        items = d.get("items", d) if isinstance(d, dict) else d
        items = list(items.values()) if isinstance(items, dict) else list(items or [])
        return sum(1 for x in items if isinstance(x, dict) and str(x.get("state") or x.get("status") or "") in ("waiting", "running", "queued", "downloading", "active"))
    except Exception:
        return 0


def chat():
    """(minutes since the last message, the last BOT message's text) from read_bot_chat.py."""
    r = subprocess.run(["/opt/media-os/venv/bin/python", "/opt/Bidhanlogoedit/read_bot_chat.py", "6"], capture_output=True, text=True, cwd="/opt/Bidhanlogoedit")
    rows = [ln.split(None, 4) for ln in r.stdout.splitlines() if ln[:1].isdigit()]
    rows = [x for x in rows if len(x) >= 4]
    if not rows:
        return 1e9, ""
    rows.sort(key=lambda x: int(x[0]))
    now = datetime.datetime.now()
    hh, mm, ss = (int(v) for v in rows[-1][1].split(":"))
    t = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
    if t > now + datetime.timedelta(minutes=2):
        t -= datetime.timedelta(days=1)
    bot = [x for x in rows if x[2] == "bot"]
    return (now - t).total_seconds() / 60.0, (bot[-1][4] if bot and len(bot[-1]) > 4 else "")


t_end, good, last = time.time() + MAXH * 3600, 0, ""
while time.time() < t_end:
    why = ""
    if not idle():
        why = "the bot is working"
    elif queue_busy():
        why = "%d film(s) in the queue" % queue_busy()
    else:
        age, btxt = chat()
        if age < QUIET:
            why = "the chat was used %.0f min ago" % age
        elif any(p in btxt for p in PANELS):
            why = "a panel waits for a tap (%s)" % btxt[:40].replace("\n", " ")
    if why:
        good = 0
        if why.split(" ")[0:3] != last.split(" ")[0:3]:
            print("%s not yet: %s" % (time.strftime("%H:%M"), why), flush=True)
        last = why
    else:
        good += 1
        if good >= 3:
            print("WAIT_QUIET OK %s" % time.strftime("%H:%M"), flush=True)
            sys.exit(0)
    time.sleep(60)
print("WAIT_QUIET TIMEOUT", flush=True)
sys.exit(1)
