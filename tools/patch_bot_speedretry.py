"""Bot side of "a refused pair gets one more try with its speed matched" (Bheemaa 2008, 2026-09-28).
The engine refused Bheemaa as "not the same edit": it IS the same edit, its dub runs 2.28 %
slower (measured in all 14 speed windows), under RETIME_MIN 2.5 %, so it was never retimed.
  R1 every engine stage runs with the job's own environment (None = inherited, as before)
  R2 at the placement gate: refused + speed.json says "same speed" although it measured a
     CONSISTENT difference (>= SPEED_RETRY_MIN, < 2.5 %, >= 90 % of >= 10 windows on one side,
     score gain >= 0.010) -> ONE more analysis with DUBSYNC2_RETIME_MIN lowered (speed.json
     removed so the engine re-measures, retimes the HD stream-copied and clears its own
     HD-derived caches). Refused again -> the refusal, saying it was retried. A pair accepted
     the first time never reaches this (it is additive).
Needs patch_bot_contract (the report's self-repaired lines) and the engine's
patch_speed_retry_engine (DUBSYNC2_RETIME_MIN).
Usage: python3 patch_bot_speedretry.py <dir with dubsync_job.py>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "SPEED_RETRY_MIN" in s:
    raise SystemExit("already patched")
assert "_contract_missing" in s, "needs patch_bot_contract first"


def rep(s, old, new, what):
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    return s.replace(old, new)


s = rep(s, '''    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())
''', '''    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    _job_env = None          # every engine stage's environment (None = the bot's own)
    _speed_retry = False     # one re-analysis with the speed matched, at most
''', "R1 state")
s = rep(s, '''        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)''', '''        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, env=_job_env)''', "R1 env")
s = rep(s, '''            if _co.get("accepted") is False:
                _pct = _co.get("unconfirmed_pct")''', '''            if _co.get("accepted") is False:
                # SELF-REPAIR: refused while the speed check measured a consistent speed
                # difference it did not correct -> one more analysis with the speed matched
                _spd = {}
                try:
                    _spd = json.loads((_work_dir_for(hd, dub) / "speed.json").read_text())
                except Exception:
                    pass
                _rr = float(_spd.get("ratio", 1.0) or 1.0)
                _nw = int(_spd.get("windows", 0) or 0)
                _ss = float(_spd.get("same_side", 0) or 0)
                if (not _speed_retry and _spd.get("decision") == "same speed"
                        and SPEED_RETRY_MIN <= abs(_rr - 1.0) < 0.025 and _nw >= 10
                        and _ss >= 0.9 and float(_spd.get("gain", 0) or 0) >= 0.010):
                    _speed_retry = True
                    stats["speed_retry"] = round(_rr, 5)
                    stats.setdefault("contract_healed", []).append(
                        "placement refused; the dub runs %+.2f%% against the HD (%d of %d speed "
                        "windows agree) -- analysed again with the speed matched"
                        % (100 * (_rr - 1.0), int(round(_ss * _nw)), _nw))
                    (_work_dir_for(hd, dub) / "speed.json").unlink(missing_ok=True)
                    _job_env = dict(os.environ, DUBSYNC2_RETIME_MIN="%.4f" % SPEED_RETRY_MIN)
                    done_weight -= weight
                    i -= 1
                    continue
                _pct = _co.get("unconfirmed_pct")''', "R2 retry")
s = rep(s, '''                    "Send an HD of the SAME version the dub was made from "''', '''                    + ("(Analysed twice: the second time with the dub's %+.2f%% speed "
                       "difference matched -- still refused.)\\n"
                       % (100 * (float(stats["speed_retry"]) - 1.0))
                       if stats.get("speed_retry") else "")
                    + "Send an HD of the SAME version the dub was made from "''', "R2 message")
s = rep(s, '''TG_FIT_BYTES = int(1.95 * 1024 ** 3)''', '''SPEED_RETRY_MIN = 0.010   # a consistent speed difference this big is worth a re-analysis
TG_FIT_BYTES = int(1.95 * 1024 ** 3)''', "R2 constant")
open(J, "w", encoding="utf-8").write(s)
print("patched", J)
