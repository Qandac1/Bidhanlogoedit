"""The report may never show a missing opening voice as ✅ (Bheemaa 2026-09-28: the dialogue gate
said RESTORE -- 38 s of the film's opening Somali voice -- the restore was refused, and the report
said "✅ dialogue: 99.4%"). Now a RESTORE verdict that is still standing after the repair step:
  * the report line is ⚠️ "the film's opening voice was NOT put back (<why>)"
  * the delivery contract lists it, so the report's first lines say INCOMPLETE.
Additive. Needs patch_bot_selfheal + patch_bot_contract.
Usage: python3 patch_bot_restorefix.py <dir with dubsync_job.py>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "opening voice was NOT put back" in s:
    raise SystemExit("already patched")
assert "_contract_missing" in s and "RESTORE_HEAD" in s, "needs selfheal + contract first"


def rep(s, old, new, what):
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    return s.replace(old, new)


s = rep(s, '''            elif " RED" in _dg or _dg.endswith("RED"):''', '''            elif "RESTORE" in _dg:
                lines.append("⚠️ dialogue: the film's opening voice was NOT put back (%s) -- %s of the "
                             "dub's voice in the film:" % (str(st.get("voice_restore") or "the repair "
                                                               "did not run")[:120], _dp))
            elif " RED" in _dg or _dg.endswith("RED"):''', "caption")
s = rep(s, '''    if not st.get("dialogue_gate"):
        miss.append("dialogue check: " + str(st.get("voice_restore") or "did not run")[:140])''',
        '''    if not st.get("dialogue_gate"):
        miss.append("dialogue check: " + str(st.get("voice_restore") or "did not run")[:140])
    elif "RESTORE" in str(st.get("dialogue_gate")) and not st.get("voice_restored_s"):
        miss.append("opening voice: the film's opening Somali voice is not in the film -- "
                    + str(st.get("voice_restore") or "the repair did not run")[:120])''', "contract")
open(J, "w", encoding="utf-8").write(s)
print("patched", J)
