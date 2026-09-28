"""A re-made shot keeps the channel logo; the cut summary knows the delivered film.
(Bheemaa 2026-09-28: 9 shots re-made by the self-repair had NO Bidhaan TV logo -- it blinked off
for 27 s -- because repair_shots never got the branding; and the cut summary could not account for
the kept end credits without the film.)
  * auto_repair gets --brand <the job's brand JSON> when the job is branded (it hands it to
    repair_shots, which burns the logo in exactly as the render did)
  * make_cut_summary(..., film=path) passes --film to cut_list; bot.py passes the delivered file
Additive: an unbranded job and a call without film= behave exactly as before.
Needs patch_bot_autorepair + patch_bot_cutsummary.
Usage: python3 patch_bot_brandrepair.py <dir with dubsync_job.py and bot.py>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
B = os.path.join(sys.argv[1], "bot.py")
s = open(J, encoding="utf-8").read()
b = open(B, encoding="utf-8").read()
if "a re-made shot keeps the channel logo" in s:
    raise SystemExit("already patched")
assert "AUTO_REPAIR" in s and "make_cut_summary" in s, "needs autorepair + cutsummary first"


def rep(t, old, new, what):
    assert t.count(old) == 1, "anchor %s found %d times" % (what, t.count(old))
    return t.replace(old, new)


s = rep(s, '''            DLG_PY, AUTO_REPAIR, title, str(out), str(_ar_out),
            "%.3f" % float(stats.get("hd_intro_s", 0.0) or 0.0),
            "--bitrate", f"{int(bitrate_k)}k" if bitrate_k else "2000k",''',
        '''            DLG_PY, AUTO_REPAIR, title, str(out), str(_ar_out),
            "%.3f" % float(stats.get("hd_intro_s", 0.0) or 0.0),
            "--bitrate", f"{int(bitrate_k)}k" if bitrate_k else "2000k",
            # a re-made shot keeps the channel logo (Bheemaa 2026-09-28: 9 shots lost it)
            *(["--brand", str(brand_path)] if brand_path else []),''', "auto_repair call")
s = rep(s, '''async def make_cut_summary(title: str, name: str, stats: dict):''',
        '''async def make_cut_summary(title: str, name: str, stats: dict, film: str | None = None):''', "summary def")
s = rep(s, '''            DLG_PY, CUT_LIST, title, "--intro", "%.3f" % intro, "--json", str(cj),''',
        '''            DLG_PY, CUT_LIST, title, "--intro", "%.3f" % intro, "--json", str(cj),
            *(["--film", str(film)] if film and os.path.exists(str(film)) else []),''', "cut_list call")
b = rep(b, '''_ct, _ci = await dubsync_job.make_cut_summary(title, _nm, res.stats)''',
        '''_ct, _ci = await dubsync_job.make_cut_summary(title, _nm, res.stats, film=res.path)''', "bot call")
open(J, "w", encoding="utf-8").write(s)
open(B, "w", encoding="utf-8").write(b)
print("patched", J, B)
