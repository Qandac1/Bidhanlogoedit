"""bot11: the film's start by John's full rule (2026-09-28). On top of patch_bot_opening (bot10):
  * the opening step runs BEFORE the voice restore: it decides where the Somali copy's film starts
    (first shared pictures / dialogue matching the HD) and writes <work>/opening.json, so the dialogue
    gate counts the copy's own intro voice (a dubber's narrator) as cut correctly, never "restore";
  * the report shows the step's plain sentence (OPENING_NOTE): where the film starts now, how much film
    was added, what was cut (the Somali copy's own intro, and what only the HD has).
Additive on bot10. Usage: python3 patch_bot_opening2.py <bot dir>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "opening_note" in s:
    raise SystemExit("already patched")
assert "OPENING_RESTORE" in s, "needs patch_bot_opening (bot10) first"

OPEN_START = "    # ---- OPENING GATE + SELF-REPAIR (John 2026-09-28: \"never again\") -------\n"
OPEN_END = '''    except Exception as _ogx:
        stats["opening_restore"] = "not run (%s)" % type(_ogx).__name__
'''
VOICE_START = "    # ---- DIALOGUE GATE + SELF-REPAIR (John 2026-09-27) -----------------------\n"
assert s.count(OPEN_START) == 1 and s.count(OPEN_END) == 1 and s.count(VOICE_START) == 1
i0 = s.index(OPEN_START)
i1 = s.index(OPEN_END) + len(OPEN_END)
block = s[i0:i1]
s = s[:i0] + s[i1:]
# the note line
a = '''        _ogg = [x for x in _ol if x.startswith("OPENING_GATE")]'''
b = '''        _ogg = [x for x in _ol if x.startswith("OPENING_GATE")]
        _ogn = [x for x in _ol if x.startswith("OPENING_NOTE ")]
        if _ogn:
            stats["opening_note"] = _ogn[-1][len("OPENING_NOTE "):][:260]'''
assert block.count(a) == 1
block = block.replace(a, b)
block = block.replace("    # ---- OPENING GATE + SELF-REPAIR (John 2026-09-28: \"never again\") -------\n",
                      "    # ---- OPENING: where the Somali copy's film starts (John 2026-09-28) ------\n"
                      "    # Runs BEFORE the voice restore: the HD's logo intro, then the film from the first\n"
                      "    # moment BOTH copies share; the copy's own intro and what only the HD has are cut.\n")
v = s.index(VOICE_START)
s = s[:v] + block + "\n" + s[v:]
# the report line
a = '''        if st.get("opening_restored_s"):
            lines.append(f"🎬 opening: put back {st['opening_restored_s']:.0f}s of the film's start "
                         "(proven by its frames / voice)")'''
b = '''        if st.get("opening_restored_s"):
            lines.append("🎬 opening: " + str(st.get("opening_note") or
                                              "put back %.0fs of the film's start" % st["opening_restored_s"]))'''
assert s.count(a) == 1
s = s.replace(a, b)
a = '''        elif st.get("opening_report"):'''
b = '''        elif st.get("opening_note"):
            lines.append("ℹ️ opening: " + str(st["opening_note"]))
        elif st.get("opening_report"):'''
assert s.count(a) == 1
s = s.replace(a, b)
open(J, "w", encoding="utf-8", newline="\n").write(s)
print("patched", J)
