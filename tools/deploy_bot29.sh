#!/bin/sh
# Deploy bot29: THE LOGO ANYWHERE. /logopos (button in Settings -> Logos) opens a page inside Telegram where the
# logo is dragged to any place on the picture and resized; Save stores it (corner TL + margins + size -- no render
# code changes). /logoset <left %> <top %> <size %> does the same by hand.
# Proven: test_bot_logoplace29 24/24 (settings to a temp file; real ffmpeg: the logo lands at the chosen place),
# run_suites29.sh, the page driven in a browser (drag, tap, size, nudge, clamp, save).
# Steps: the page into /opt/Bidhanlogoedit/web_public, the /logo/* route in Caddy (caddy_logo_route.sh), bot.py.
set -e
Z=/opt/dubsync2/scratch/bot29
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
cmp -s bot.py $Z/live/bot.py || { echo "live bot.py changed since bot29 was tested -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp bot.py $B/x/
cp $Z/patch_bot_logoplace29.py $Z/test_bot_logoplace29.py $Z/caddy_logo_route.sh tools/
python3 tools/patch_bot_logoplace29.py $B/x >/dev/null
cmp -s $B/x/bot.py $Z/new/bot.py && echo "rebuilt file == tested bot29" \
  || { echo "rebuilt file differs from the tested bot29 -- refusing"; exit 1; }
python3 -m py_compile $B/x/bot.py
mkdir -p web_public/t
cp $Z/place.html web_public/place.html
grep -q "^web_public/t/" .gitignore 2>/dev/null || echo "web_public/t/" >> .gitignore
sh tools/caddy_logo_route.sh
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot29-$TS
mkdir -p $K
cp -p bot.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $B/x/bot.py .
docker cp bot.py bidhaan-logoedit:/app/bot.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < bot.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/bot.py")
[ "$a" = "$b" ] && echo "container bot.py == repo" || { echo "container bot.py differs"; exit 1; }
docker exec bidhaan-logoedit sh -c "grep -c '_place_open\|_cmd_logoset\|_on_web_app_data' /app/bot.py; ls /opt/Bidhanlogoedit/web_public"
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "Traceback|Error" | grep -v "Task was destroyed\|AUTH_KEY\|CancelledError" | head -4
rm -rf $B
echo "backup of the previous file: $K"
echo DEPLOY_BOT29 DONE $TS
