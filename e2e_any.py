# -*- coding: utf-8 -*-
"""Run ANY title end-to-end through the bot's own run_dubsync(mode="dlg").

Second-movie proof. John's standing rule is that a fix is not proven until it
works on at least two movies, and the bot path had only been proven on The
Comeback. Tammal is the harder case: its HD audio is 5.1 surround (eac3, 6ch)
where The Comeback is stereo, so this also exercises the downmix path.

This run uses the DEPLOYED code, so it should also produce, on its own:
  out/<title>_dlg.log     raw engine stdout (added so a report is never data-less)
  out/<title>_report.md   the human-review report, with a real per-chunk table

NOT calling prepare_inputs on purpose: it does dst.unlink() then
os.link(src, dst), so if src and dst are the same path (inputs already in raw/)
it deletes the file and then fails to link it. The bot never hits that because
it passes freshly downloaded temp files.

Usage: e2e_any.py <hd_path> <dub_path> <title>
"""
import asyncio, sys, time
from pathlib import Path

sys.path.insert(0, "/opt/Bidhanlogoedit")
import dubsync_job

HD = Path(sys.argv[1])
DUB = Path(sys.argv[2])
TITLE = sys.argv[3]

_t0 = time.time()
_last = [""]


async def on_progress(label, pct):
    if label != _last[0] or int(pct) % 5 == 0:
        _last[0] = label
        print("[%7.1fs] %5.1f%%  %s" % (time.time() - _t0, pct, label), flush=True)


async def main():
    for f in (HD, DUB):
        if not f.exists():
            print("MISSING:", f)
            return 1
    print("TITLE:", TITLE, flush=True)
    print("HD  :", HD.name, "%.2f GB" % (HD.stat().st_size / 1024**3), flush=True)
    print("DUB :", DUB.name, "%.2f GB" % (DUB.stat().st_size / 1024**3), flush=True)
    print("mode=dlg via the bot code path", flush=True)

    res = await dubsync_job.run_dubsync(
        HD, DUB, TITLE, None,
        width=1920, height=1080, crf=21,
        on_progress=on_progress, bitrate_k=2000, mode="dlg")

    dt = time.time() - _t0
    print()
    print("=== RESULT after %.0f min ===" % (dt / 60))
    print("ok      :", res.ok)
    print("path    :", res.path)
    print("message :", res.message)
    print("stats   :", res.stats)
    if res.ok and res.path and Path(res.path).exists():
        print("size    : %.2f GB" % (Path(res.path).stat().st_size / 1024**3))
    return 0 if res.ok else 1


sys.exit(asyncio.run(main()))
