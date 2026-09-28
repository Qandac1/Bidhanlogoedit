"""Give every existing bot test suite a fake opening_restore ("nothing needed"), so the new bot step
is exercised as a no-op there and each suite keeps testing what it tested. Idempotent.
Usage: python3 add_opening_fake.py <tools dir>"""
import os
import re
import sys

FAKE = '    "opening_restore": \'print("OPENING_GATE OK"); print("OPENING_RESTORE NOT NEEDED")\',\n'
LOOP = re.compile(r'for k in \(([^)]*)"restore_head",')
for f in ("test_bot_autorepair.py", "test_bot_brandrepair.py", "test_bot_contract.py", "test_bot_restorefix.py",
          "test_bot_speedretry.py"):
    p = os.path.join(sys.argv[1], f)
    s = open(p, encoding="utf-8").read()
    if '"opening_restore"' in s:
        print("already", f)
        continue
    i = s.index('    "restore_head":')
    s = s[:i] + FAKE + s[i:]
    if "for k in TOOLS" not in s:         # speedretry installs every entry of its TOOLS dict
        assert LOOP.search(s), f
        s = LOOP.sub(r'for k in (\1"restore_head", "opening_restore",', s)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("fake added", f)
