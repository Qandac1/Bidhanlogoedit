#!/bin/sh
# Deploy bot30 + bot31 together: TWO SETS OF SETTINGS (banner jobs / dub-sync films) and THE STUDIO (logo,
# caption with fonts and colours, timeline, trim).
#   bot30  patch_bot_profiles30.py   bot.py: user_cfg / set_user with two sets; today's settings are frozen into
#                                    the dub-sync set at the bot's start
#   bot31  patch_bot_capfont31.py    branding.py + bot.py: the caption's font (by id) and colour (by name); a
#                                    caption with a % in it is drawn at last
#          patch_bot_studio31.py     bot.py: the Studio (cfg.json with both sets, cleaned saves per set)
#          place.html                the Studio page; web_public/fonts -> ../assets/fonts for its font previews
#          patch_engine_capfont.py   engine brand.py: the dub-sync render draws the chosen font and colour
# Proven on copies: test_bot_profiles30 25/25, test_bot_capfont31 20/20, test_bot_studio31 34/34,
# test_engine_capfont 8/8, run_suites31.sh, the page driven in a browser.
# Only when the bot is idle; backups first; every rebuilt file must equal its tested copy.
set -e
Z=/opt/dubsync2/scratch/bot31
E=/opt/dubsync2/scratch/eng_capfont/src/dubsync2/brand.py
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
cmp -s bot.py /opt/dubsync2/scratch/bot30/live/bot.py || { echo "live bot.py changed since the tests -- refusing"; exit 1; }
cmp -s branding.py /opt/dubsync2/scratch/bot30/live/branding.py || { echo "live branding.py changed since the tests -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x $B/e/dubsync2
cp bot.py branding.py $B/x/
cp /opt/dubsync2/scratch/bot30/patch_bot_profiles30.py $Z/patch_bot_capfont31.py $Z/patch_bot_studio31.py tools/
cp /opt/dubsync2/scratch/bot30/test_bot_profiles30.py $Z/test_bot_capfont31.py $Z/test_bot_studio31.py tools/
python3 tools/patch_bot_profiles30.py $B/x >/dev/null
python3 tools/patch_bot_capfont31.py $B/x >/dev/null
python3 tools/patch_bot_studio31.py $B/x >/dev/null
for f in bot.py branding.py; do
  cmp -s $B/x/$f $Z/new/$f && echo "rebuilt $f == tested" || { echo "rebuilt $f differs from the tested copy -- refusing"; exit 1; }
  python3 -m py_compile $B/x/$f
done
cp /opt/dubsync2/src/dubsync2/brand.py $B/e/dubsync2/
/opt/dubsync2/.venv/bin/python $Z/patch_engine_capfont.py $B/e >/dev/null
cmp -s $B/e/dubsync2/brand.py $E && echo "rebuilt engine brand.py == tested" || { echo "rebuilt engine brand.py differs from the tested copy -- refusing"; exit 1; }
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot31-$TS
mkdir -p $K
cp -p bot.py branding.py web_public/place.html /opt/dubsync2/src/dubsync2/brand.py $K/
cp -p /var/lib/docker/volumes/bidhanlogoedit_bot_data/_data/user_settings.json $K/user_settings.json
# the page and its fonts
cp $Z/page/place.html web_public/place.html
[ -e web_public/fonts ] || ln -s ../assets/fonts web_public/fonts
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
# the bot
cp $B/x/bot.py bot.py
cp $B/x/branding.py branding.py
docker cp bot.py bidhaan-logoedit:/app/bot.py
docker cp branding.py bidhaan-logoedit:/app/branding.py
# the engine (bind-mounted: no restart needed, done while the bot is down for its own restart)
cp $B/e/dubsync2/brand.py /opt/dubsync2/src/dubsync2/brand.py
cp $Z/patch_engine_capfont.py $Z/test_engine_capfont.py /opt/dubsync2/tools/
docker restart bidhaan-logoedit >/dev/null
sleep 14
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
for f in bot.py branding.py; do
  a=$(md5sum < $f); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/$f")
  [ "$a" = "$b" ] && echo "container $f == repo" || { echo "container $f differs"; exit 1; }
done
echo "engine brand.py host $(md5sum < /opt/dubsync2/src/dubsync2/brand.py | cut -c1-12) container $(docker exec bidhaan-logoedit sh -c 'md5sum < /opt/dubsync2/src/dubsync2/brand.py' | cut -c1-12) tested $(md5sum < $E | cut -c1-12)"
docker exec bidhaan-logoedit python3 -c "
import json
d = json.load(open('/app/data/user_settings.json'))
print('users', len(d), '| with their own dub-sync set', sum(1 for r in d.values() if isinstance(r, dict) and isinstance(r.get('_dub'), dict)))
"
docker logs --since 30s bidhaan-logoedit 2>&1 | grep -i "dub-sync set" | tail -2 | cut -c1-160
docker logs --since 30s bidhaan-logoedit 2>&1 | grep -E "Traceback|Error" | grep -v "Task was destroyed\|AUTH_KEY\|CancelledError" | head -4
echo "page $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/logo/place.html) | font $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/logo/fonts/Montserrat-ExtraBold.ttf) | font listing $(curl -s -o /dev/null -w '%{http_code}' https://159-195-136-50.sslip.io/logo/fonts/)"
rm -rf $B
echo "backup of the previous files: $K"
echo DEPLOY_BOT31 DONE $TS
