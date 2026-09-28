"""The bot never silently forgets a step (John 2026-09-28: "sometimes it gets errors or forgets").
Every step after the render used to be fail-open: a failure became a quiet stats note and the
film shipped anyway (Pushpa 2: no HD sound mix, no end credits, found only by hand). Now:
  K1 the work dir every later step reads is the ENGINE'S OWN (its "Provenance: .../provenance.json"
     line), never re-derived by a second hash; a disagreement is healed and reported.
  K2 a cancel during the audio step stops the job there (no further steps start).
  K3 the audio step failed -> one more try (only when the work dir really has the provenance).
  K4 the end credits failed / did not run -> one more try.
  K5 the DELIVERY CONTRACT: audio mixed, dialogue gate ran, cut gate ran, picture check ran,
     credits handled, picture and sound the same length. Whatever is still missing after the
     retries goes at the TOP of the report ("INCOMPLETE") -- never buried in a stats line.
Additive: the tested steps are unchanged; the new blocks act only when a step reports failure.
Needs patch_bot_audit + patch_bot_selfheal first.
Usage: python3 patch_bot_contract.py <dir with dubsync_job.py>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "_contract_missing" in s:
    raise SystemExit("already patched")
assert "RESTORE_HEAD" in s, "needs patch_bot_selfheal first"


def rep(s, old, new, what, count=1):
    assert s.count(old) == count, "anchor %s found %d times, expected %d" % (what, s.count(old), count)
    return s.replace(old, new)


# K1 -------------------------------------------------------------------------------------------
s = rep(s, '''            if (m := pat_hd_intro.search(line)):
                stats["hd_intro_s"] = float(m.group(1))
''', '''            if (m := pat_hd_intro.search(line)):
                stats["hd_intro_s"] = float(m.group(1))
            # the engine's OWN work dir: every step after the render reads its provenance
            # (Pushpa 2: a re-derived hash pointed at an empty dir -> no sound mix, no credits)
            _m_pv = re.search(r"Provenance:\\s*(\\S+)/provenance\\.json", line)
            if _m_pv:
                stats["engine_work"] = _m_pv.group(1)
''', "K1 parse")

s = rep(s, '''    if not out.exists():
        return DubResult(False, None, "render produced no file", stats)
''', '''    if not out.exists():
        return DubResult(False, None, "render produced no file", stats)

    # ---- CONTRACT: every step after the render uses the engine's own work dir ----
    _bot_work = Path(_work_dir_for(hd, dub))
    _post_work = Path(stats["engine_work"]) if stats.get("engine_work") else _bot_work
    if _post_work != _bot_work:
        stats.setdefault("contract_healed", []).append(
            "work dir: the bot's hash said %s, the engine wrote %s -- used the engine's"
            % (_bot_work.name, _post_work.name))
''', "K1 post work")
for old, new, what in (
        ('DLG_PY, "-u", SWITCH_AUDIO, "--work", str(_work_dir_for(hd, dub)),',
         'DLG_PY, "-u", SWITCH_AUDIO, "--work", str(_post_work),', "K1 audio"),
        ('DLG_PY, CUT_AUDIT, str(_work_dir_for(hd, dub)), str(out), str(dub),',
         'DLG_PY, CUT_AUDIT, str(_post_work), str(out), str(dub),', "K1 cut gate"),
        ('"--json", str(Path(_work_dir_for(hd, dub)) / "frame_audit.json"),',
         '"--json", str(_post_work / "frame_audit.json"),', "K1 picture"),
        ('DLG_PY, APPEND_CREDITS, "--work", str(_work_dir_for(hd, dub)),',
         'DLG_PY, APPEND_CREDITS, "--work", str(_post_work),', "K1 credits")):
    s = rep(s, old, new, what)

# K2 + K3 --------------------------------------------------------------------------------------
s = rep(s, '''    # ---- DIALOGUE GATE + SELF-REPAIR (John 2026-09-27) -----------------------
''', '''    if _cancelled():
        return DubResult(False, None, "cancelled", stats)
    # ---- CONTRACT: the audio step is never silently skipped -- one more try ----
    if not str(stats.get("audio", "")).startswith("dub dialogue"):
        stats["audio_first_try"] = stats.get("audio")
        if not (_post_work / "provenance.json").exists():
            stats["audio_retry"] = "not retried: no provenance.json in work/%s" % _post_work.name
        else:
            try:
                _sa_out2 = OUT_DIR / f"{title}_v8.mp4"
                _sa_out2.unlink(missing_ok=True)
                _sa2 = await asyncio.create_subprocess_exec(
                    DLG_PY, "-u", SWITCH_AUDIO, "--work", str(_post_work),
                    "--video", str(out), "--out", str(_sa_out2), "--abitrate", "320k",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
                if register:
                    register(_sa2)
                _t2 = (await _sa2.communicate())[0].decode("utf-8", "replace")
                await _sa2.wait()
                if _cancelled():
                    return DubResult(False, None, "cancelled", stats)
                if _sa_out2.exists() and _sa_out2.stat().st_size > 0:
                    out = _sa_out2
                    stats["audio"] = "dub dialogue + HD master music"
                    stats.setdefault("contract_healed", []).append(
                        "sound mix: failed once (%s), built on the second try"
                        % str(stats.get("audio_first_try"))[:80])
                else:
                    _tl2 = [x.strip() for x in _t2.splitlines() if x.strip()]
                    stats["audio_retry"] = "failed again: " + (_tl2[-1][:160] if _tl2 else "no output")
            except Exception as _ax2:
                stats["audio_retry"] = "failed again (%s)" % type(_ax2).__name__

    # ---- DIALOGUE GATE + SELF-REPAIR (John 2026-09-27) -----------------------
''', "K2/K3")

# K4 + K5 --------------------------------------------------------------------------------------
s = rep(s, '''    except Exception as _crx:
        stats["credits"] = "not run (%s)" % type(_crx).__name__

    return DubResult(True, out,
''', '''    except Exception as _crx:
        stats["credits"] = "not run (%s)" % type(_crx).__name__

    # ---- CONTRACT: end credits are never silently lost -- one more try ----
    _cr1 = str(stats.get("credits", ""))
    if not _cr1 or _cr1.startswith(("not run", "CREDITS FAILED")):
        try:
            _crb = await asyncio.create_subprocess_exec(
                DLG_PY, APPEND_CREDITS, "--work", str(_post_work),
                "--video", str(out), "--out", str(out),
                "--keep-under", str(TG_FIT_BYTES),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            _crt2 = (await _crb.communicate())[0].decode("utf-8", "replace")
            await _crb.wait()
            for _ln in _crt2.splitlines():
                if _ln.startswith("CREDITS:"):
                    _m = re.search(r"appended ([0-9.]+)s", _ln)
                    if _m:
                        stats["credits_s"] = float(_m.group(1))
                        if stats.get("expected_duration_s"):
                            stats["expected_duration_s"] = (
                                float(stats["expected_duration_s"]) + float(_m.group(1)))
                    stats["credits"] = _ln[len("CREDITS:"):].strip()
                    stats.setdefault("contract_healed", []).append(
                        "end credits: failed once (%s), added on the second try" % _cr1[:80])
                elif _ln.startswith(("SKIP:", "CREDITS FAILED:")):
                    stats["credits"] = _ln.strip()
        except Exception as _crx2:
            stats["credits"] = "not run twice (%s)" % type(_crx2).__name__

    stats["contract_missing"] = _contract_missing(stats, out)

    return DubResult(True, out,
''', "K4/K5")

s = rep(s, '''def _audio_len_s(video) -> float:
''', '''def _contract_missing(st: dict, out) -> list:
    """What a finished conform delivery must have, checked after the retries. Each missing
    item is one short line for the top of the report. Facts about the FILE come from the file."""
    miss = []
    if not str(st.get("audio", "")).startswith("dub dialogue"):
        miss.append("sound mix (dub talk + HD music): " + str(st.get("audio_retry") or st.get("audio")
                                                            or "did not run")[:140])
    if not st.get("dialogue_gate"):
        miss.append("dialogue check: " + str(st.get("voice_restore") or "did not run")[:140])
    if not str(st.get("cut_gate", "")).startswith("UNJUSTIFIED CUTS"):
        miss.append("cut check: " + str(st.get("cut_gate") or "did not run")[:140])
    _pc = st.get("picture_check") or {}
    if not _pc.get("verdict"):
        miss.append("picture check: " + str(_pc.get("error") or "did not run")[:140])
    _cr = str(st.get("credits", ""))
    if not _cr or _cr.startswith(("not run", "CREDITS FAILED")):
        miss.append("end credits: " + (_cr or "did not run")[:140])
    try:
        def _d(sel):
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel, "-show_entries",
                                "stream=duration", "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True, timeout=120)
            return float((r.stdout.strip().splitlines() or ["0"])[0] or 0)
        _dv, _da = _d("v:0"), _d("a:0")
        if _dv <= 0 or _da <= 0:
            miss.append("file: no %s stream" % ("picture" if _dv <= 0 else "sound"))
        elif abs(_dv - _da) > 1.0:
            miss.append("file: picture %.1f s but sound %.1f s" % (_dv, _da))
    except Exception as _fx:
        miss.append("file: could not be measured (%s)" % type(_fx).__name__)
    return miss


def _audio_len_s(video) -> float:
''', "K5 function")

s = rep(s, '''    _head = "dub-sync complete" if _passed else "⚠️ dub-sync — NEEDS REVIEW (NOT final)"
''', '''    _head = "dub-sync complete" if _passed else "⚠️ dub-sync — NEEDS REVIEW (NOT final)"
    _miss = st.get("contract_missing") or []
    if _miss:
        _head = "⛔ dub-sync — INCOMPLETE (see the first lines)"
''', "K5 head")
s = rep(s, '''    lines = [f"🎬 **{title}** — {_head}",
             f"`{int(dur_s//3600)}h {int(dur_s%3600//60):02d}m` · {size_b/1e9:.2f} GB"]
''', '''    lines = [f"🎬 **{title}** — {_head}",
             f"`{int(dur_s//3600)}h {int(dur_s%3600//60):02d}m` · {size_b/1e9:.2f} GB"]
    if _miss:
        lines.append(f"⛔ **{len(_miss)} step(s) did not finish** (each was tried twice):")
        for _x in _miss[:6]:
            lines.append("   · " + _x)
    for _h in (st.get("contract_healed") or [])[:4]:
        lines.append("🩹 self-repaired: " + _h)
''', "K5 caption")

open(J, "w", encoding="utf-8").write(s)
print("patched", J)
