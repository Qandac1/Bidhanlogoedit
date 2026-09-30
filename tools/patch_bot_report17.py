"""bot17: the report says only what is true of the delivered film (John 2026-09-30, Hebbuli bot16 report):
  * "✂️ film starts at 1:09" was the engine's start in the Somali copy's time, from BEFORE the opening step put
    the HD intro back -- the opening line says where the film starts; the stale line is left out when it ran.
  * "QA note: duration 7017.3s vs expected 6942.7s" -- the expected length counted the credits but not the
    opening and the ending put back (6942.7 + 59.1 + 15.5 = 7017.3 = the file): both are added now.
  * "🔎 Check these spots" listed the Somali copy's OWN repeats (it shows those frames twice itself, dub vs dub
    0.2-8 bits) like mistakes: the repeats WE added come first, the copy's own are named (tools/repeat_split.py
    "pairs"; matched line by line with the checker's list, any mismatch leaves the list as it was).
Usage: python3 patch_bot_report17.py <dubsync_job.py>"""
import sys

P = sys.argv[1]
s = open(P, encoding="utf-8").read()
if "_label_own_repeats" in s:
    raise SystemExit("already patched")


def rep(old, new, what):
    global s
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


rep('''            stats["opening_restored_s"] = float(_of[-1].split()[-1])
''', '''            stats["opening_restored_s"] = float(_of[-1].split()[-1])
            if stats.get("expected_duration_s"):      # the film is longer by the opening put back (bot17)
                stats["expected_duration_s"] = float(stats["expected_duration_s"]) + stats["opening_restored_s"]
''', "opening -> expected length")

rep('''            stats["tail_restored_s"] = float(_tlf[-1].split()[-1])
''', '''            stats["tail_restored_s"] = float(_tlf[-1].split()[-1])
            if stats.get("expected_duration_s"):      # ... and by the ending put back (bot17)
                stats["expected_duration_s"] = float(stats["expected_duration_s"]) + stats["tail_restored_s"]
''', "tail -> expected length")

rep('''    # ---- END CREDITS: every film ends on its own credits (John 2026-09-25) --
''', '''    # ---- the spots list names the Somali copy's OWN repeats (bot17, John 2026-09-30) ----
    try:
        if stats.get("dup_regions"):
            stats["dup_regions"] = await asyncio.to_thread(_label_own_repeats, stats["dup_regions"], _post_work)
    except Exception:
        pass

    # ---- END CREDITS: every film ends on its own credits (John 2026-09-25) --
''', "label step after the gate")

rep('''APPEND_CREDITS = "/opt/dubsync2/append_credits.py"
''', '''APPEND_CREDITS = "/opt/dubsync2/append_credits.py"
REPEAT_SPLIT = "/opt/dubsync2/tools/repeat_split.py"


def _label_own_repeats(lines, work):
    """The integrity checker's "🔁 a ↔ b (Ns)" spots, the repeats WE added first, then the ones the Somali copy
    shows twice itself (tools/repeat_split.py "pairs": more of the pair's seconds the copy has twice than we
    added), named so. The lines are the checker's own (human_repeat_lines: accidental regions, longest first);
    each is matched to its region by that order AND its seconds -- any mismatch returns the list unchanged."""
    rep_ = json.load(open(Path(work) / "integrity_report.json"))
    acc = [r for r in rep_.get("regions") or []
           if r.get("classification") == "accidental" and (r.get("seconds") or 0) > 0]
    acc.sort(key=lambda r: -r["seconds"])
    if len(acc) < len(lines):
        return lines
    rs = subprocess.run([DLG_PY, REPEAT_SPLIT, str(work)], capture_output=True, text=True, timeout=180)
    rj = json.loads((rs.stdout.strip().splitlines() or ["{}"])[-1])
    own = {(int(a), int(b)) for a, b, o, x in (rj.get("pairs") or []) if o > x}
    if not rj.get("ok") or not own:
        return lines
    ours, theirs = [], []
    for ln, r in zip(lines, acc):
        m = re.search(r"\\(([0-9.]+)s\\)", ln)
        if not m or abs(float(m.group(1)) - round(float(r["seconds"]), 1)) > 0.051:
            return lines
        if tuple(sorted((int(r.get("dub_a", -1)), int(r.get("dub_b", -1))))) in own:
            theirs.append(ln + " · the Somali copy shows it twice too (kept as it has it)")
        else:
            ours.append(ln)
    return ours + theirs
''', "REPEAT_SPLIT + _label_own_repeats")

rep('''        if st.get("film_start"):
            lines.append("✂️ film starts at %s — intro/bumpers cut automatically"''',
    '''        if st.get("film_start") and not st.get("opening_restored_s"):   # bot17: the opening line says it
            lines.append("✂️ film starts at %s — intro/bumpers cut automatically"''', "stale film-start line")

open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patched", P)
