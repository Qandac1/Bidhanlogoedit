"""bot15: the report's "repeated footage" counts only repeats WE added -- not the ones the Somali copy itself
has (John's rule: each moment as often as the dub shows it; Hebbuli 2026-09-30: 10.3 s the copy repeats
itself, 49:36 = 49:53, 65:33 = 65:45). tools/repeat_split.py decides by the dub's own frames (fingerprints
saved by analyze); without them it returns the old measure, so older films read exactly as before.
Usage: python3 patch_bot_repeats.py <dubsync_job.py>"""
import sys

P = sys.argv[1]
s = open(P, encoding="utf-8").read()
if "repeat_split.py" in s:
    raise SystemExit("already patched")


def rep(old, new, what):
    global s
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


rep('''                out['backward'] = sum(1 for i in range(1, len(hs))
                                      if hs[i][0] < hs[i - 1][1] - 0.04)
''', '''                out['backward'] = sum(1 for i in range(1, len(hs))
                                      if hs[i][0] < hs[i - 1][1] - 0.04)
                # split by the DUB's own frames: repeats the Somali copy has too vs repeats we added (bot15)
                try:
                    import subprocess as _sp_rs
                    _rs = _sp_rs.run([DLG_PY, "/opt/dubsync2/tools/repeat_split.py", wd],
                                     capture_output=True, text=True, timeout=180)
                    _rj = _json.loads((_rs.stdout.strip().splitlines() or ["{}"])[-1])
                    if _rj.get("ok"):
                        out['replay_s'] = float(_rj["accidental_s"])
                        out['replay_dub_s'] = float(_rj["faithful_s"])
                except Exception:
                    pass
''', "replay split")

rep('''            lines.append(("♻️ repeated footage: **none** (each HD frame used once)"
                          if _r < 0.05 and _v < 0.05 else''', '''            _own = q.get('replay_dub_s') or 0.0
            _own_txt = (f" · {_own:.1f}s the Somali copy itself shows twice -- shown as it has them"
                        if _own >= 0.05 else "")
            lines.append(("♻️ repeated footage: **none** (each HD frame used once)"
                          if _r < 0.05 and _v < 0.05 and _own < 0.05 else
                          "♻️ repeated footage we added: **none**" + _own_txt
                          if _r < 0.05 and _v < 0.05 else''', "report line")

rep('''                          f"⚠️ repeated footage: {_r:.1f}s (worst {q.get('replay_worst', 0)}x)"
                          if _r >= 0.05 else''', '''                          f"⚠️ repeated footage we added: {_r:.1f}s (worst {q.get('replay_worst', 0)}x)" + _own_txt
                          if _r >= 0.05 else''', "warning line")

open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patched", P)
