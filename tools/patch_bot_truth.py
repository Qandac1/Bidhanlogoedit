"""bot13: two hard rules the film must pass to be called complete (John 2026-09-29: "you need real
mathematics / code logic so we never see these problems again"):
  1. NO SOMALI-VOICED FILM CUT: the dialogue check's RED (Somali voice lost whose frames ARE in the
     HD -- Srinivasa Kalyanam's last scene) used to be one warning line under a "complete" film. Now
     it is a step that did not finish: INCOMPLETE at the top, with the exact missing seconds.
  2. VOICE ON THE LIPS, MEASURED: tools/av_sync.py on the finished film at 5 places (10-90 %); the
     median error > 0.10 s = INCOMPLETE ("the Somali voice is 0.34 s BEFORE the lips"). A place with no
     clear voice is skipped; a measurement that cannot run is reported, never blocks.
     (2026-09-29: two engine bugs put the voice 0.3-1.4 s off in 7 delivered films; no check looked.)
Report line: "👄 lip sync: ..." / "⛔ lip sync: ..." / "ℹ️ lip sync: not measured (...)". Additive on bot12.
Usage: python3 patch_bot_truth.py <bot dir>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "AV_SYNC" in s:
    raise SystemExit("already patched")
assert "AUDIO_MODE" in s, "needs bot12 first"


def rep(old, new, what):
    global s
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


rep('FRAME_AUDIT = "/opt/dubsync2/tools/frame_audit.py"\n',
    'FRAME_AUDIT = "/opt/dubsync2/tools/frame_audit.py"\n'
    '# the Somali voice vs the lips, measured on the finished film (bot13, 2026-09-29)\n'
    'AV_SYNC = "/opt/dubsync2/tools/av_sync.py"\n', "constant")

rep('''    # Release gate. A failure here is not a crash''',
    '''    # ---- LIP SYNC: the Somali voice on the lips, MEASURED on the film (2026-09-29: two engine bugs
    # put it 0.3-1.4 s off in 7 films and no check looked at voice vs lips). Read-only, fail-open:
    # five places spread over the film; a place without a clear voice (music, silence) is skipped.
    try:
        _ld = _audio_len_s(out)
        _at = ",".join("%.0f" % (_ld * _f) for _f in (0.1, 0.3, 0.5, 0.7, 0.9))
        _av = await asyncio.create_subprocess_exec(
            DLG_PY, AV_SYNC, title, str(out), "%.3f" % float(stats.get("hd_intro_s", 0.0) or 0.0),
            "--at", _at, "--search", "3",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        _avt = (await asyncio.wait_for(_av.communicate(), timeout=1200))[0].decode("utf-8", "replace")
        await _av.wait()
        _m = re.search(r"AV_SYNC ([+-]?[0-9.]+|none) (\\d+)", _avt)
        if _m:
            stats["lip_sync"] = {"median": None if _m.group(1) == "none" else float(_m.group(1)),
                                 "points": int(_m.group(2))}
        else:
            stats["lip_sync"] = {"error": (_avt.strip().splitlines() or ["no output"])[-1][:120]}
    except Exception as _avx:
        stats["lip_sync"] = {"error": type(_avx).__name__}

    # Release gate. A failure here is not a crash''', "lip sync step")

rep('''    if not _pc.get("verdict"):
        miss.append("picture check: " + str(_pc.get("error") or "did not run")[:140])
''',
    '''    if not _pc.get("verdict"):
        miss.append("picture check: " + str(_pc.get("error") or "did not run")[:140])
    # hard rules (John 2026-09-29): not complete when Somali-voiced FILM was cut (its frames are in the
    # HD) or when the voice is MEASURED off the lips
    _dg = str(st.get("dialogue_gate", ""))
    if _dg.endswith("RED") or " RED " in _dg:
        _red = [x for x in (st.get("dialogue_lines") or []) if "cut by mistake" in x]
        miss.append("dialogue: film with Somali voice was cut by mistake -- "
                    + (_red[0].replace("voice dub ", "dub ")[:140] if _red else "see the dialogue lines"))
    _ls = st.get("lip_sync") or {}
    if _ls.get("median") is not None and _ls.get("points", 0) >= 2 and abs(_ls["median"]) > 0.10:
        miss.append("lip sync: the Somali voice is %.2f s %s the lips (measured at %d places)"
                    % (abs(_ls["median"]), "BEFORE" if _ls["median"] > 0 else "AFTER", _ls["points"]))
''', "contract")

rep('''            lines.append(f"⚠️ picture check not run ({_pc['error']})")
''',
    '''            lines.append(f"⚠️ picture check not run ({_pc['error']})")
        _ls = st.get("lip_sync") or {}
        if _ls.get("median") is not None and _ls.get("points", 0) >= 2:
            if abs(_ls["median"]) <= 0.10:
                lines.append("👄 lip sync: the Somali voice is on the lips (measured at %d places, %+.2f s)"
                             % (_ls["points"], _ls["median"]))
            else:
                lines.append("⛔ lip sync: the Somali voice is %.2f s %s the lips (measured at %d places)"
                             % (abs(_ls["median"]), "BEFORE" if _ls["median"] > 0 else "AFTER", _ls["points"]))
        elif _ls:
            lines.append("ℹ️ lip sync: not measured (%s)" % (_ls.get("error") or "no clear voice at the places checked"))
''', "report")
open(J, "w", encoding="utf-8", newline="\n").write(s)
print("patched", J)
