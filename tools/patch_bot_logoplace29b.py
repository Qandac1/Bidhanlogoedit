"""bot29b: the Logo studio's per-opening folders go to a place the bot can WRITE.
bot29 wrote them under /opt/Bidhanlogoedit/web_public -- that folder is mounted READ-ONLY in the bot container
("[Errno 30] Read-only file system" on the first real /logopos, found by the end-to-end test e2e_logostudio.py;
the unit tests used a temp folder). /opt/dubsync2 is writable there: the folders now live in
/opt/dubsync2/web_logo/t/<token>, served by Caddy at /logo/t/* (caddy_logo_route.sh); the static page stays in
/opt/Bidhanlogoedit/web_public.
Usage: python patch_bot_logoplace29b.py <bot dir>     (patches <bot dir>/bot.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "bot.py"
s = P.read_text()
old = 'WEB_PUBLIC = os.environ.get("BIDHAAN_WEB_PUBLIC", "/opt/Bidhanlogoedit/web_public")'
new = 'WEB_PUBLIC = os.environ.get("BIDHAAN_WEB_PUBLIC", "/opt/dubsync2/web_logo")   # writable from the bot container'
if new in s:
    sys.exit("already patched: %s" % P)
assert s.count(old) == 1, "anchor found %d times" % s.count(old)
P.write_text(s.replace(old, new))
print("patched %s" % P)
