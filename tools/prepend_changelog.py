"""Put a new entry at the top of a CHANGELOG.md (under its title line, before the first "## ").
Usage: python3 prepend_changelog.py <CHANGELOG.md> <entry.md>"""
import sys

p, e = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8").read()
entry = open(e, encoding="utf-8").read().strip() + "\n\n"
first = entry.splitlines()[0]
if first in s:
    sys.exit("already there: " + first[:60])
i = s.index("\n## ")
open(p, "w", encoding="utf-8").write(s[:i + 1] + entry + s[i + 1:])
print("CHANGELOG entry added: " + first[:80])
