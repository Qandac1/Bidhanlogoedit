#!/bin/sh
# Deploy bot29b: the Logo studio's per-opening folders go to /opt/dubsync2/web_logo (the bot container cannot
# write under /opt/Bidhanlogoedit: "[Errno 30] Read-only file system" on the first real /logopos). One line of
# bot.py (patch_bot_logoplace29b.py) + the /logo/t/* route (caddy_logo_route_b.sh, already applied when this runs).
set -e
Z=/opt/dubsync2/scratch/bot29
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
cmp -s bot.py $Z/new/bot.py || { echo "live bot.py is not the tested bot29 -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp bot.py $B/x/
cp $Z/patch_bot_logoplace29.py $Z/patch_bot_logoplace29b.py $Z/caddy_logo_route_b.sh tools/
python3 tools/patch_bot_logoplace29b.py $B/x
python3 -m py_compile $B/x/bot.py
[ "$(diff bot.py $B/x/bot.py | grep -c '^[<>]')" = "2" ] || { echo "more than the one line changed -- refusing"; exit 1; }
grep -q "^web_logo/" /opt/dubsync2/.gitignore 2>/dev/null || echo "web_logo/" >> /opt/dubsync2/.gitignore
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot29b-$TS
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
docker exec bidhaan-logoedit sh -c "grep -n '^WEB_PUBLIC' /app/bot.py | cut -c1-120"
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "Traceback|Error" | grep -v "Task was destroyed\|AUTH_KEY\|CancelledError" | head -4
rm -rf $B
echo "backup of the previous file: $K"
echo DEPLOY_BOT29B DONE $TS
