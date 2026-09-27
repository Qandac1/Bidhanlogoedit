"""Bot self-handling (John 2026-09-27: "the bot must fix its own problems, not only report"):
  S1 _work_dir_for: never hash the engine's .det. detection scratch copy (Pushpa 2: the bot
     picked raw/..._hd_ORIG.det.mp4 -> work/4e3a03f699b8, a dir nothing ever wrote -> the audio
     step and the end credits found no provenance; the film shipped dub-only, no credits.
     Proved: hashing that file gives exactly 4e3a03f699b8). Same exclusion as the engine's.
  S2 the delivered file is always .mp4 (Pushpa 2 went out as "...Hindi.5.1.mkv")
  S3 after the audio step: the dialogue gate + self-repair (tools/restore_head.py): the dub's
     opening voice that the HD's own timeline has is put back automatically (Achcham: 16.4 s),
     adverts / channel intro stay cut; the result and every removed stretch go in the report.
Needs patch_bot_audit (the picture check) applied first.
Usage: python3 patch_bot_selfheal.py <dir with bot.py and dubsync_job.py>"""
import os
import sys

d = sys.argv[1]
J, B = os.path.join(d, "dubsync_job.py"), os.path.join(d, "bot.py")
sj, sb = open(J, encoding="utf-8").read(), open(B, encoding="utf-8").read()
if "RESTORE_HEAD" in sj:
    raise SystemExit("already patched")
assert "FRAME_AUDIT" in sj, "needs patch_bot_audit first"


def rep(s, old, new, what):
    assert s.count(old) == 1, "anchor not found exactly once: " + what
    return s.replace(old, new)


# S1 ------------------------------------------------------------------------------------------
sj = rep(sj, '''                for cand in sorted(p.parent.glob('%s_%s_ORIG.*' % (stem, who))):
                    return cand''', '''                for cand in sorted(p.parent.glob('%s_%s_ORIG.*' % (stem, who))):
                    if '.det.' in cand.name:
                        continue    # the engine's detection scratch copy, never the master
                                    # (Pushpa 2: hashing it sent the audio step to an empty dir)
                    return cand''', "S1 orig_of")

# S3 ------------------------------------------------------------------------------------------
sj = rep(sj, '''FRAME_AUDIT = "/opt/dubsync2/tools/frame_audit.py"''', '''FRAME_AUDIT = "/opt/dubsync2/tools/frame_audit.py"
RESTORE_HEAD = "/opt/dubsync2/tools/restore_head.py"''', "S3 constant")
sj = rep(sj, '''    # ---- GATE: jumps the dub did NOT make (skipped footage) ----------------''', '''    # ---- DIALOGUE GATE + SELF-REPAIR (John 2026-09-27) -----------------------
    # Every second of the dub's voice must be in the film. The dub's opening voice that the
    # HD's own timeline has (Achcham: 16.4 s cut with the channel logo) is put back here --
    # the HD's opening picture, the dub's sound -- and the provenance is rewritten, so the
    # gates below judge the repaired film. Adverts / channel intro stay cut and are listed.
    try:
        _rh_out = OUT_DIR / f"{title}_voice.mp4"
        _rh = await asyncio.create_subprocess_exec(
            DLG_PY, RESTORE_HEAD, title, str(out), str(_rh_out),
            f"{int(bitrate_k)}k" if bitrate_k else "2000k",
            "%.3f" % float(stats.get("hd_intro_s", 0.0) or 0.0),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        _rht = (await asyncio.wait_for(_rh.communicate(), timeout=5400))[0].decode("utf-8", "replace")
        await _rh.wait()
        _rl = [x.strip() for x in _rht.splitlines() if x.strip()]
        _fin = [x for x in _rl if x.startswith("RESTORE_HEAD")]
        if _fin and _fin[-1].startswith("RESTORE_HEAD DONE") and _rh_out.exists() \\
                and _rh_out.stat().st_size > 0:
            out.unlink(missing_ok=True)
            _rh_out.rename(out)
            stats["voice_restored_s"] = float(_fin[-1].split()[-1])
        elif _fin and "FAILED" in _fin[-1]:
            stats["voice_restore"] = _fin[-1][:200]
            _rh_out.unlink(missing_ok=True)
        _pct = [x for x in _rl if "in the output:" in x]
        if _pct:
            stats["dialogue_pct"] = _pct[-1].split("in the output:")[-1].strip()
            _after = _rl[_rl.index(_pct[-1]) + 1:]
            stats["dialogue_lines"] = [x for x in _after if x.startswith("voice dub")]
        _v = [x for x in _rl if x.startswith("DIALOGUE_AUDIT")]
        if _v:
            stats["dialogue_gate"] = _v[-1]
    except Exception as _rhx:
        stats["voice_restore"] = "not run (%s)" % type(_rhx).__name__

    # ---- GATE: jumps the dub did NOT make (skipped footage) ----------------''', "S3 step")
sj = rep(sj, '''        _pc = st.get("picture_check") or {}''', '''        if st.get("dialogue_gate"):
            _dg, _dp = st["dialogue_gate"], st.get("dialogue_pct", "")
            if st.get("voice_restored_s"):
                lines.append(f"🗣 dialogue: restored {st['voice_restored_s']:.0f}s of the dub's opening "
                             f"voice (on the HD's own opening) -- {_dp} of the dub's voice in the film")
            elif " RED" in _dg or _dg.endswith("RED"):
                lines.append(f"⚠️ dialogue: film voice was cut -- {_dp} of the dub's voice in the film:")
            else:
                lines.append(f"✅ dialogue: {_dp} of the dub's voice in the film")
            for _dl in (st.get("dialogue_lines") or [])[:6]:
                lines.append("   · " + _dl.replace("voice dub ", "dub "))
        elif st.get("voice_restore"):
            lines.append(f"⚠️ dialogue check: {st['voice_restore']}")
        _pc = st.get("picture_check") or {}''', "S3 caption")

# S2 ------------------------------------------------------------------------------------------
sb = rep(sb, '''        name = f"dubsync_{os.path.basename(hd_job['name'])}"''',
         '''        # always .mp4 (John): the render IS mp4; the source's .mkv/.webm name must not leak
        name = f"dubsync_{os.path.splitext(os.path.basename(hd_job['name']))[0]}.mp4"''', "S2 name")

open(J, "w", encoding="utf-8").write(sj)
open(B, "w", encoding="utf-8").write(sb)
print("patched", J, B)
