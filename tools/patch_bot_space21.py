"""bot21: a film never runs into a full disk (John 2026-10-03: Sardar 2 delivered INCOMPLETE --
"RESTORE_HEAD FAILED ... error code: -28 (No space left on device)" and "OPENING_RESTORE FAILED ... -28";
the disk had sat at 0 GB free for 10 hours and Kondal before it ended at 1 GB).
  * Before the first engine stage: the space this film needs (5 x its two source files + 10 GB, 15..90 GB)
    must be free. Old regenerable caches are cleared first (/opt/dubsync2/tools/space_guard.py: temp folders
    of dead runs, engine caches, caches of films whose sources are gone, old source copies -- never a film in
    the queue, never a protected title). Still short -> the job stops at once with a plain disk message
    instead of rendering for hours into a failure.
  * Before each step that writes the film again (sound mix, opening, ending, opening voice, wrong-clip
    repair): the same clearing for 3 x the film + 3 GB. Fail-open: the step always runs.
  * The opening step and the opening-voice step are run ONCE MORE when they died on a full disk and space
    could be cleared ("each was tried twice" is then true for exactly this failure). If the disk is still
    full the report says so in plain words.
  * With enough free space nothing changes: no extra process, same steps, same order, same report
    (test_bot_space21 + the existing suites).
Usage: python3 patch_bot_space21.py <dubsync_job.py>"""
import sys

P = sys.argv[1]
s = open(P, encoding="utf-8").read()
if "SPACE_GUARD" in s:
    raise SystemExit("already patched")


def rep(old, new, what, count=1):
    global s
    assert s.count(old) == count, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


# ---- 1. helpers ---------------------------------------------------------------------------------------------
rep('''RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"
''', '''# ---- DISK SPACE (bot21, 2026-10-03: Sardar 2 "RESTORE_HEAD FAILED ... -28 No space left on device") --------
SPACE_GUARD = "/opt/dubsync2/tools/space_guard.py"
_ENOSPC_MARKS = ("No space left on device", "error code: -28", "Errno 28", "ENOSPC")


def _free_gb() -> float:
    return shutil.disk_usage(str(OUT_DIR)).free / 1e9


def _job_need_gb(hd, dub) -> float:
    """Free space a whole film needs: sources are copied, proxied, analysed, rendered and re-written by the
    opening / sound / credits steps. Measured 2026-10-02: Kondal (5.1 GB of sources) took the disk from 20 GB
    free to 1."""
    try:
        src = (Path(hd).stat().st_size + Path(dub).stat().st_size) / 1e9
    except OSError:
        src = 4.0
    return max(15.0, min(90.0, 5.0 * src + 10.0))


def _step_need_gb(film) -> float:
    """A step that writes the film again: the new copy, its pieces and the old one side by side."""
    try:
        return 3.0 * Path(film).stat().st_size / 1e9 + 3.0
    except OSError:
        return 8.0


def _is_enospc(text) -> bool:
    return any(k in str(text or "") for k in _ENOSPC_MARKS)


async def _ensure_space(need_gb: float) -> tuple[bool, str]:
    """(enough, note). With enough free space: nothing runs. Otherwise the space guard clears regenerable
    data (never a queued or protected film) and the answer is measured again on the disk."""
    free = _free_gb()
    if free >= need_gb:
        return True, ""
    try:
        _p = await asyncio.create_subprocess_exec(
            DLG_PY, SPACE_GUARD, "ensure", "%d" % int(need_gb + 0.999),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        await asyncio.wait_for(_p.communicate(), timeout=900)
    except Exception:
        pass
    free2 = _free_gb()
    if free2 >= need_gb:
        return True, "disk: %.0f GB was free, old caches cleared -> %.0f GB" % (free, free2)
    return False, ("the server's disk is full: %.0f GB free, about %.0f GB needed (old caches were "
                   "cleared first)" % (free2, need_gb))


RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"
''', "helpers")

# ---- 2. before the first engine stage -----------------------------------------------------------------------
rep('''    stats: dict = {}
    done_weight = 0.0
''', '''    stats: dict = {}
    # bot21: never start a film into a full disk (it would render for hours and fail in the last steps)
    _sp_ok, _sp_note = await _ensure_space(_job_need_gb(hd, dub))
    if not _sp_ok:
        return DubResult(False, None, "💽 " + _sp_note + ". Nothing was rendered -- the film is not lost: "
                         "send it again when space is back (tell Claude: the disk is full).", stats)
    if _sp_note:
        stats["space_note"] = _sp_note
    done_weight = 0.0
''', "job start")

# ---- 3. space before the steps that write the film again (fail-open) ----------------------------------------
rep('''            _sa_out = OUT_DIR / f"{title}_v8.mp4"
            _sa = await asyncio.create_subprocess_exec(
''', '''            await _ensure_space(_step_need_gb(out))                    # bot21
            _sa_out = OUT_DIR / f"{title}_v8.mp4"
            _sa = await asyncio.create_subprocess_exec(
''', "audio step")
rep('''        _tl_out = OUT_DIR / f"{title}_tail.mp4"
''', '''        await _ensure_space(_step_need_gb(out))                        # bot21
        _tl_out = OUT_DIR / f"{title}_tail.mp4"
''', "tail step")
rep('''        _ar_out = OUT_DIR / f"{title}_repaired.mp4"
''', '''        await _ensure_space(_step_need_gb(out))                        # bot21
        _ar_out = OUT_DIR / f"{title}_repaired.mp4"
''', "repair step")


# ---- 4. opening + opening voice: once more when they died on a full disk ------------------------------------
def wrap_retry(start, end, var, key, what):
    """Indent the step's try-block into `for <var> in (1, 2):`; a second pass only when the step's failure
    text says the disk was full AND space could be cleared."""
    global s
    assert s.count(start) == 1, "start anchor %s found %d times" % (what, s.count(start))
    i = s.index(start)
    assert s.count(end, i) >= 1, "end anchor %s missing" % what
    j = s.index(end, i)
    nl = chr(10)
    block = s[i:j].rstrip(nl) + nl
    body = "".join(("    " + ln if ln.strip() else ln) for ln in block.splitlines(True))
    tail = nl.join([
        "        # bot21: died on a full disk -> clear space and run this step once more",
        "        if %(var)s == 1 and _is_enospc(stats.get(%(key)r)):",
        "            if (await _ensure_space(_step_need_gb(out)))[0]:",
        "                stats.pop(%(key)r, None)",
        "                continue",
        "            stats[%(key)r] = 'disk full, %%.0f GB free -- %%s' %% (_free_gb(), stats[%(key)r])",
        "        break", ""]) % {"var": var, "key": key}
    head = nl.join(["    for %s in (1, 2):" % var,
                    "        await _ensure_space(_step_need_gb(out))                    # bot21", ""])
    s = s[:i] + head + body + tail + nl + s[j:]


wrap_retry('''    try:
        if _cancelled():
            return DubResult(False, None, "cancelled", stats)
        _og_out = OUT_DIR / f"{title}_opening.mp4"
''', '''    # ---- THE END: the film's last scene with its Somali voice''', "_og_try", "opening_restore", "opening")
wrap_retry('''    try:
        _rh_out = OUT_DIR / f"{title}_voice.mp4"
''', '''    # ---- SELF-REPAIR: wrong clips the cut check proves''', "_rh_try", "voice_restore", "voice")

open(P, "w", encoding="utf-8", newline=chr(10)).write(s)
print("patched: space guard at job start, before 5 steps, retry of opening + voice on a full disk")
