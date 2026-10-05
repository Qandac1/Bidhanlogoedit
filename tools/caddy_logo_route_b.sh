#!/bin/sh
# bot29b: the Logo studio's per-opening folders (logo images, frame) are written by the bot into
# /opt/dubsync2/web_logo/t/<token> (the bot container cannot write under /opt/Bidhanlogoedit). Adds ONE
# handle_path /logo/t/* block before the /logo/* block of /etc/caddy/Caddyfile. Backup, validate, reload; the old
# file is put back if anything fails. Idempotent.
set -u
C=/etc/caddy/Caddyfile
grep -q "handle_path /logo/t/\*" $C && { echo "CADDY_LOGO_T already there"; exit 0; }
grep -q "handle_path /logo/\*" $C || { echo "CADDY_LOGO_T FAILED: the /logo/* block is missing (run caddy_logo_route.sh first)"; exit 1; }
mkdir -p /opt/dubsync2/web_logo/t
TS=$(date +%Y%m%d-%H%M%S)
cp -p $C $C.pre-logo-t-$TS
python3 - "$C" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
old = '\thandle_path /logo/* {\n'
new = ('\thandle_path /logo/t/* {\n\t\troot * /opt/dubsync2/web_logo/t\n\t\theader Cache-Control "no-cache"\n'
       '\t\tfile_server\n\t}\n' + old)
assert s.count(old) == 1, "the /logo/* block was found %d times" % s.count(old)
open(p, "w").write(s.replace(old, new))
PY
[ $? = 0 ] || { cp -p $C.pre-logo-t-$TS $C; echo "CADDY_LOGO_T FAILED: edit"; exit 1; }
caddy validate --config $C --adapter caddyfile >/dev/null 2>&1 || { cp -p $C.pre-logo-t-$TS $C; echo "CADDY_LOGO_T FAILED: validate (old file put back)"; exit 1; }
systemctl reload caddy || { cp -p $C.pre-logo-t-$TS $C; systemctl reload caddy; echo "CADDY_LOGO_T FAILED: reload (old file put back)"; exit 1; }
sleep 2
echo probe > /opt/dubsync2/web_logo/t/_probe.txt
echo "CADDY_LOGO_T OK (backup $C.pre-logo-t-$TS) | page: $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/logo/place.html) | a file in t/: $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/logo/t/_probe.txt) | listing: $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/logo/t/)"
rm -f /opt/dubsync2/web_logo/t/_probe.txt
