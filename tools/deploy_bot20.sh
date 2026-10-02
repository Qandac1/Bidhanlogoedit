#!/bin/sh
# Deploy bot20: higher quality than 1080p (John 2026-10-02). Resolution menu "4K"; short videos / trailers above
# 1080p keep their size (toggle); above 1080p the bitrate grows with the picture. At or below 1080p nothing changes
# (test_bot_hq20: 1728 combinations + panel texts identical to the live bot; panels 18/18 on both).
set -e
Z=/opt/dubsync2/scratch/bot20
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
B=$(mktemp -d)
cp bot.py $B/
cp $Z/patch_bot_hq20.py $Z/test_bot_hq20.py tools/
python3 tools/patch_bot_hq20.py $B/bot.py >/dev/null
cmp -s $B/bot.py $Z/bot.py && echo "rebuilt bot.py == tested bot20" || { echo "bot.py differs from bot20 -- refusing"; exit 1; }
cmp -s dubsync_job.py $Z/dubsync_job.py || { echo "live dubsync_job.py changed since bot20 was tested -- refusing"; exit 1; }
python3 -m py_compile $B/bot.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot20-$TS
mkdir -p $K
cp -p bot.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $B/bot.py .
docker cp bot.py bidhaan-logoedit:/app/bot.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < bot.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/bot.py")
[ "$a" = "$b" ] && echo "container bot.py == repo" || { echo "container bot.py differs"; exit 1; }
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error" | grep -v "Task was destroyed" | head -3
rm -rf $B
echo "backup of the previous bot.py: $K"
echo DEPLOY_BOT20 DONE $TS
