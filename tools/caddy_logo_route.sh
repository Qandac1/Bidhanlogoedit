#!/bin/sh
# The web address of the logo page (bot29): https://<host>/logo/* -> the static folder /opt/Bidhanlogoedit/web_public
# (place.html + one unguessable folder per opening with the logo images). Static files only, no listing.
# Adds ONE handle_path block to the shared (watch) snippet of /etc/caddy/Caddyfile, before its catch-all 404;
# backup first, `caddy validate` before the reload, the old file put back if anything fails. Idempotent.
set -u
C=/etc/caddy/Caddyfile
grep -q "handle_path /logo/\*" $C && { echo "CADDY_LOGO already there"; exit 0; }
TS=$(date +%Y%m%d-%H%M%S)
cp -p $C $C.pre-logo-$TS
python3 - "$C" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
old = '\thandle {\n\t\trespond "Not found" 404\n\t}\n'
new = ('\thandle_path /logo/* {\n\t\troot * /opt/Bidhanlogoedit/web_public\n\t\theader Cache-Control "no-cache"\n'
       '\t\tfile_server\n\t}\n' + old)
assert s.count(old) == 1, "the catch-all block was found %d times" % s.count(old)
open(p, "w").write(s.replace(old, new))
PY
[ $? = 0 ] || { cp -p $C.pre-logo-$TS $C; echo "CADDY_LOGO FAILED: edit"; exit 1; }
caddy validate --config $C --adapter caddyfile >/dev/null 2>&1 || { cp -p $C.pre-logo-$TS $C; echo "CADDY_LOGO FAILED: validate (old file put back)"; exit 1; }
systemctl reload caddy || { cp -p $C.pre-logo-$TS $C; systemctl reload caddy; echo "CADDY_LOGO FAILED: reload (old file put back)"; exit 1; }
sleep 2
echo "CADDY_LOGO OK (backup $C.pre-logo-$TS) | page: $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/logo/place.html) | other path: $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/nothing-here) | listing: $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/logo/t/)"
