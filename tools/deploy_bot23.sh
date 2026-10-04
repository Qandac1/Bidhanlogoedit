#!/bin/sh
# Deploy bot23: the ZOOM is measured whenever a film pair's "same film" evidence is weak (< 8 of 10 parts), not
# only on "different" (John 2026-10-04: Toxic 2026 delivered with 60 s of repeats and 414 of 4711 shots unmatched --
# the Somali copy shows the middle 77.5 % x 81 % of the HD picture; the plain check gave 6 parts = "same").
# Proven: test_bot_zoomweak23 27/27 (logic with fake checks + REAL Toxic 2026: 10 of 10 parts with the window
# [0.775, 0.8112, 0, -0.08]; REAL Highway unzoomed: no zoom search), run_suites23.sh same verdict live vs patched.
set -e
Z=/opt/dubsync2/scratch/bot23
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
cmp -s bot.py $Z/live/bot.py || { echo "live bot.py changed since bot23 was tested -- refusing"; exit 1; }
cmp -s dubsync_job.py $Z/live/dubsync_job.py || { echo "live dubsync_job.py changed since bot23 was tested -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp bot.py $B/x/
cp $Z/patch_bot_zoomweak23.py $Z/test_bot_zoomweak23.py tools/
python3 tools/patch_bot_zoomweak23.py $B/x >/dev/null
cmp -s $B/x/bot.py $Z/new/bot.py && echo "rebuilt bot.py == tested bot23" || { echo "rebuilt file differs from the tested bot23 -- refusing"; exit 1; }
python3 -m py_compile $B/x/bot.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot23-$TS
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
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "Traceback|Error" | grep -v "Task was destroyed\|AUTH_KEY\|CancelledError" | head -4
rm -rf $B
echo "backup of the previous bot.py: $K"
echo DEPLOY_BOT23 DONE $TS
