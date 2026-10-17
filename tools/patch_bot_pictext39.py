"""bot39c, dubsync_job.py (words only): a NOT CLEAN picture line says WHAT the unproven shots are, and the advice under
it no longer says "another version / zoomed" when no shot is placed wrong.

Why (John 10-17 pasted the Matchbox trailer report: "only 91.1% of 146 shots show what the Somali copy shows (13 are
wrong or unproven) ... Most likely this HD is not the version the Somali copy was made from, or the copy is
reframed/zoomed"): measured, 0 of the 13 were placed wrong -- 11 are 0.52 s flash shots the picture check cannot judge
(all correct, looked at), 2 are pictures the HD does not have (the real fault: the last 8 s show the HD's YouTube end
screen where the copy has its own dark ending). The headline and the NOT CLEAN decision stay exactly as they are; the
line gains the split, and with no shot placed wrong the advice points at the spots instead of "another version".
    python3 patch_bot_pictext39.py <bot dir>   -> PATCHED dubsync_job (refuses when the file is not the expected one)"""
import sys

p = sys.argv[1].rstrip("/") + "/dubsync_job.py"
s = open(p, newline="").read()
if "\r\n" in s or "placed wrong" in s:
    sys.exit("dubsync_job.py is not the expected one (CRLF or already patched) - nothing changed")
A_OLD = """            bad.append("picture: only %.1f%% of %s shots show what the Somali copy shows (%d are wrong or unproven)"
                       % (float(_pc["ok_pct"]), _n or "the", max(0, _n - int(_pc.get("ok") or 0))))
"""
A_NEW = """            bad.append("picture: only %.1f%% of %s shots show what the Somali copy shows (%d are wrong or unproven%s)"
                       % (float(_pc["ok_pct"]), _n or "the", max(0, _n - int(_pc.get("ok") or 0)), _pic_split(_pc)))
"""
B_OLD = """        if all(str(_x).startswith("lips:") for _x in _bad):
            lines.append("   Watch the ⚠️ lips spots below (film times) before posting; tell Claude.")
        else:
"""
B_NEW = """        if all(str(_x).startswith("lips:") for _x in _bad):
            lines.append("   Watch the ⚠️ lips spots below (film times) before posting; tell Claude.")
        elif _only_unproven(_bad, st):
            lines.append("   No shot is placed wrong. At the 🔁 spots below the film shows HD picture the Somali copy "
                         "does not have (an end card, a logo?) -- watch them before posting; tell Claude.")
        else:
"""
C_OLD = """def _quality_fail(st: dict, title: str) -> list:
"""
C_NEW = '''def _pic_split(pc: dict) -> str:
    """': 0 placed wrong, 2 pictures the HD does not have, 11 too short / dark to check' -- the picture check's own
    counts (bot39c); '' when they are not all there. Never raises."""
    try:
        n, ok, wrong, nohd = (int(pc[k]) for k in ("checked", "ok", "wrong", "no_hd"))
        unsure = n - ok - wrong - nohd
        if unsure < 0:
            return ""
        return ": %d placed wrong, %d HD picture the copy does not have, %d too short / dark to check" % (wrong, nohd, unsure)
    except Exception:
        return ""


def _only_unproven(bad: list, st: dict) -> bool:
    """True when the picture line is the only NOT CLEAN reason and the picture check placed NO shot wrong."""
    try:
        pc = st.get("picture_check") or {}
        return (len(bad) == 1 and str(bad[0]).startswith("picture:") and "wrong" in pc
                and int(pc["wrong"]) == 0)
    except Exception:
        return False


def _quality_fail(st: dict, title: str) -> list:
'''
for old, new in ((A_OLD, A_NEW), (B_OLD, B_NEW), (C_OLD, C_NEW)):
    if s.count(old) != 1:
        sys.exit("dubsync_job.py is not the expected one (%r found %d times) - nothing changed" % (old[:50], s.count(old)))
    s = s.replace(old, new)
open(p, "w", newline="").write(s)
print("PATCHED dubsync_job (picture words)")
