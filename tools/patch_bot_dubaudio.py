"""bot12: the Somali track for the WHOLE film (John 2026-09-29: "I don't care music, I will okay the
way it is"). The render already lays the dub's sound under the whole film; the slow "Building audio
-- listening" step (switch_audio: demucs over the whole film to put the HD's music in the gaps) is
skipped -- about 1 hour per feature film -- and with it the switch jumps and any chance of HD (Hindi)
voice in a gap. One setting, AUDIO_MODE:
  "dub"    (default) the dub's sound everywhere; report "🎚 audio: dub audio -- the Somali track ..."
  "switch" the old way (dub talk + HD music), with its retry -- unchanged
The delivery contract accepts "dub audio" as a complete sound. Additive on bot11.
Usage: python3 patch_bot_dubaudio.py <bot dir>"""
import os
import sys

J = os.path.join(sys.argv[1], "dubsync_job.py")
s = open(J, encoding="utf-8").read()
if "AUDIO_MODE" in s:
    raise SystemExit("already patched")
assert "OPENING_RESTORE" in s and "opening_note" in s, "needs bot11 first"


def rep(old, new, what):
    global s
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    s = s.replace(old, new)


rep('''SWITCH_AUDIO = "/opt/dubsync2/switch_audio.py"''',
    '''SWITCH_AUDIO = "/opt/dubsync2/switch_audio.py"
# John 2026-09-29: "I don't care music" -- the dub's sound for the whole film (no ~1 h listening step,
# no switch jumps, no HD voice in a gap). "switch" = the old dub-talk / HD-music switch.
AUDIO_MODE = "dub"''', "constant")

START = "    # ---- AUDIO: the dub for talking, the HD master for music it really has --\n"
END = '''    if _cancelled():
        return DubResult(False, None, "cancelled", stats)
    # ---- CONTRACT: the audio step is never silently skipped -- one more try ----
'''
assert s.count(START) == 1 and s.count(END) == 1
i0 = s.index(START) + len(START)
i1 = s.index(END)
block = s[i0:i1]
lines = block.split("\n")
# the comment lines stay, the code (from "try:") goes under the switch branch
k = next(n for n, ln in enumerate(lines) if ln.startswith("    try:"))
head, body = lines[:k], lines[k:]
body = [("    " + ln) if ln.strip() else ln for ln in body]
new_block = "\n".join(head + [
    "    if AUDIO_MODE != \"switch\":",
    "        stats[\"audio\"] = \"dub audio -- the Somali track for the whole film (John: no HD music)\"",
    "    else:",
] + body)
s = s[:i0] + new_block + s[i1:]
rep('''    if not str(stats.get("audio", "")).startswith("dub dialogue"):
        stats["audio_first_try"] = stats.get("audio")''',
    '''    if AUDIO_MODE == "switch" and not str(stats.get("audio", "")).startswith("dub dialogue"):
        stats["audio_first_try"] = stats.get("audio")''', "retry")
rep('''    if not str(st.get("audio", "")).startswith("dub dialogue"):''',
    '''    if not str(st.get("audio", "")).startswith(("dub dialogue", "dub audio")):''', "contract")
open(J, "w", encoding="utf-8", newline="\n").write(s)
print("patched", J)
