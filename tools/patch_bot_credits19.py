"""bot19: the end-credits line says what is true when the film already ends on its own end (John 2026-10-01,
Sardar): the ending step (tail_restore) now follows the Somali copy to the HD's last second when its sound bed is
the HD's own music on the film line -- the credits roll is then IN the film, with the Somali copy's sound, and the
credits step has nothing to add ("SKIP: HD continues only 0.9s past the film -- the dub kept its ending").
bot16 showed every SKIP as "⚠️ end credits not added"; this one is not a problem:
  "🎬 end credits kept: the Somali copy runs to the film's own end (its credits are in the film)".
Usage: python3 patch_bot_credits19.py <dubsync_job.py>"""
import sys

P = sys.argv[1]
s = open(P, encoding="utf-8").read()
if "the dub kept its ending" in s:
    raise SystemExit("already patched")
old = '''        elif str(st.get("credits", "")).startswith("SKIP"):
            lines.append("⚠️ end credits not added — %s" % st["credits"][5:150].strip())'''
new = '''        elif str(st.get("credits", "")).startswith("SKIP") and "the dub kept its ending" in str(st["credits"]):
            lines.append("🎬 end credits kept: the Somali copy runs to the film's own end (its credits are in the "
                         "film)")
        elif str(st.get("credits", "")).startswith("SKIP"):
            lines.append("⚠️ end credits not added — %s" % st["credits"][5:150].strip())'''
assert s.count(old) == 1, "anchor found %d times" % s.count(old)
s = s.replace(old, new)
open(P, "w", encoding="utf-8", newline="\n").write(s)
print("patched", P)
