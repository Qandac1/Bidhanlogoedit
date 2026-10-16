"""bot38 inside the bot container:  python3 test_dlretry38.py <live bot dir copy> <bot38 dir copy>
  A. a whole download (the size Telegram gives): the same path back, no second download, no wait   (the usual case)
  B. an EMPTY file (10-16 Hope, 10-07 Harom Hara) -> downloaded again after a wait, the whole file back
  C. the download raises (AUTH_BYTES_INVALID) and returns nothing, then works -> the whole file
  D. never whole -> three more tries, then a clear "send it again" message (never a half file read as a film)
  E. Telegram gives no size + a non-empty file -> taken as it came, no download (as before)
  F. bot.py: the only change is ADDED lines (the new function + the call), and it compiles
Prints DLRETRY38_TESTS ALL PASS."""
import json
import os
import py_compile
import subprocess
import sys
import tempfile

LIVE, NEW = sys.argv[1], sys.argv[2]
T = tempfile.mkdtemp(prefix="dl38_")
RUNNER = r'''
import asyncio, json, os, sys
d = sys.argv[1]
sys.path.insert(0, d); os.chdir(d)
import bot
waits = []
async def fast_sleep(s):
    waits.append(s)
bot.asyncio.sleep = fast_sleep
case = json.loads(sys.argv[2])
calls = []
class Media:
    file_size = case["want"]
class M:
    video = Media() if case["want"] is not None else None
    document = None
    async def download(self, file_name=None, progress=None):
        k = len(calls)
        calls.append(os.path.exists(file_name))  # (was the partial file still there when downloaded again?)
        r = case["tries"][min(k, len(case["tries"]) - 1)]
        if r == "raise":
            raise RuntimeError("Telegram says: [400 AUTH_BYTES_INVALID]")
        if r == "none":
            return None
        open(file_name, "wb").write(b"x" * r)
        return file_name
dest = case["dest"]
path = None
if case["first"] is not None:
    open(dest, "wb").write(b"x" * case["first"])
    path = dest
try:
    out = asyncio.run(bot._complete_download(M(), dest, path, None))
    print("RESULT " + json.dumps({"path": out, "size": os.path.getsize(out), "calls": len(calls), "left": calls, "waits": waits}))
except Exception as e:
    print("RESULT " + json.dumps({"error": str(e), "calls": len(calls), "left": calls, "waits": waits}))
'''
open(T + "/runner.py", "w").write(RUNNER)
fails = 0


def check(ok, what, extra=""):
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + what + (("  | " + str(extra)[:400]) if extra and not ok else ""), flush=True)


def run(want, first, tries):
    dest = os.path.join(T, "src.mp4")
    if os.path.exists(dest):
        os.remove(dest)
    case = {"want": want, "first": first, "tries": tries, "dest": dest}
    p = subprocess.run([sys.executable, T + "/runner.py", NEW, json.dumps(case)], capture_output=True, text=True, timeout=300)
    line = [x for x in p.stdout.splitlines() if x.startswith("RESULT ")]
    return json.loads(line[-1][7:]) if line else {"crash": (p.stderr or p.stdout)[-400:]}


r = run(1000, 1000, [1000])
check(r.get("size") == 1000 and r.get("calls") == 0 and r.get("waits") == [], "A. a whole download goes on as before: no second download, no wait", r)
r = run(1000, 0, [1000])
check(r.get("size") == 1000 and r.get("calls") == 1 and r.get("waits") == [5] and r.get("left") == [False],
      "B. an empty file (the Hope case) is downloaded again after 5 s, the empty file removed first", r)
r = run(1000, None, ["raise", 1000])
check(r.get("size") == 1000 and r.get("calls") == 2 and r.get("waits") == [5, 15], "C. AUTH_BYTES_INVALID, then a good try -> the whole file", r)
r = run(1000, 10, [10])
check("send it again" in (r.get("error") or "") and "tried 4 times" in (r.get("error") or "") and r.get("calls") == 3
      and r.get("waits") == [5, 15, 30], "D. never whole -> three more tries, then the clear message", r)
r = run(1000, None, ["none", "none", "none"])
check("send it again" in (r.get("error") or "") and r.get("calls") == 3, "D2. downloads that return nothing -> the clear message", r)
r = run(None, 500, [500])
check(r.get("size") == 500 and r.get("calls") == 0, "E. no size from Telegram + a non-empty file -> as it came", r)
d = subprocess.run(["diff", os.path.join(LIVE, "bot.py"), os.path.join(NEW, "bot.py")], capture_output=True, text=True).stdout.splitlines()
removed = [x for x in d if x.startswith("< ")]
added = [x for x in d if x.startswith("> ")]
check(not removed and 30 < len(added) < 70 and any("_complete_download(m, dest, path, _dlp)" in x for x in added),
      "F. bot.py only GAINS lines (the function + the call): %d added, %d removed" % (len(added), len(removed)), removed[:3])
try:
    py_compile.compile(os.path.join(NEW, "bot.py"), doraise=True)
    check(True, "F2. bot.py compiles")
except py_compile.PyCompileError as e:
    check(False, "F2. bot.py compiles", e)
print("DLRETRY38_TESTS ALL PASS" if not fails else "DLRETRY38_TESTS %d FAILED" % fails)
sys.exit(1 if fails else 0)
