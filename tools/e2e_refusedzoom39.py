"""End-to-end proof of bot39b on a REAL refused pair, the bot's own code path, nothing sent to Telegram:
  1. the bot's pair check (pair_check.py --voice, and pair_zoom.py when the bot would run it) -- what the bot saw
  2. the zoom window registry handled as the bot does for this title (a pair-check window saved, else none)
  3. prepare_inputs + run_dubsync(mode="conform") from the PATCHED copy, no logo, 1920x1080, 2000k (John's setting)
Run INSIDE the bot container:  python3 e2e_refusedzoom39.py <patched bot dir> <hd file> <dub file> <hd name>
Prints the steps, then E2E_RESULT ok=<bool> path=<file> and the job's stats (refused_zoom, contract_healed, ...)."""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

NEW, HD_SRC, DUB_SRC, HD_NAME = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
sys.path.insert(0, NEW)
import dubsync_job  # noqa: E402

assert str(Path(dubsync_job.__file__).resolve().parent) == str(Path(NEW).resolve()), dubsync_job.__file__
PY = "/opt/dubsync2/.venv/bin/python"
T0 = time.time()


def say(*a):
    print("[%6.0fs]" % (time.time() - T0), *a, flush=True)


title = dubsync_job._slug(HD_NAME)
say("title", title, "| window saved now:", dubsync_job._hd_window_of(title))
pc = subprocess.run([PY, "/opt/dubsync2/pair_check.py", "--voice", "--hd", str(HD_SRC), "--dub", str(DUB_SRC)],
                    capture_output=True, text=True, timeout=600)
pair = json.loads(pc.stdout.strip().splitlines()[-1]) if pc.stdout.strip() else {"error": pc.stderr[-300:]}
say("pair check:", json.dumps({k: v for k, v in pair.items() if not isinstance(v, (list, dict))})[:600])
weak = "parts" in pair and pair.get("chain_steps", 0) >= 40 and pair["parts"] < 8
if pair.get("parts", 0) <= 3 or weak:
    zc = subprocess.run([PY, "/opt/dubsync2/pair_zoom.py", "--hd", str(HD_SRC), "--dub", str(DUB_SRC)],
                        capture_output=True, text=True, timeout=1500)
    say("the bot's zoom check (it runs one here):", zc.stdout.strip().splitlines()[-1][:600] if zc.stdout.strip() else zc.stderr[-300:])
else:
    say("the bot runs NO zoom check here (pair check %s parts >= 8) -- no window for this title" % pair.get("parts"))


async def on_progress(label, pct):
    if not hasattr(on_progress, "last") or label != on_progress.last:
        on_progress.last = label
        say("%5.1f%% %s" % (pct, label))


async def main():
    hd, dub = await dubsync_job.prepare_inputs(HD_SRC, DUB_SRC, title, 1080, lambda *a: None, on_progress)
    say("inputs:", hd.name, dub.name)
    res = await dubsync_job.run_dubsync(hd, dub, title, None, mode="conform", width=1920, height=1080, crf=21,
                                        bitrate_k=2000, on_progress=on_progress)
    say("E2E_RESULT ok=%s path=%s" % (res.ok, res.path))
    say("message:", (res.message or "")[:900])
    st = res.stats or {}
    for k in ("refused_zoom", "refused_parked", "contract_healed", "placement", "weak_analysis", "weak_zoom",
              "lip_sync", "opening_restore", "opening_restored_s"):
        if k in st:
            say("stats.%s = %s" % (k, json.dumps(st[k], default=str)[:700]))
    json.dump(st, open("/opt/dubsync2/scratch/bot39/e2e_stats.json", "w"), default=str, indent=1)


asyncio.run(main())
