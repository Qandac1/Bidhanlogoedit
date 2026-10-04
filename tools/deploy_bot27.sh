#!/bin/sh
# Deploy bot27: BLACK CINEMA BARS. A render frame wider than 16:9 (CBI 5's master is 1920x804 and went out as a
# 1920x804 file) becomes 16:9 at the same width (1920x1080): the picture in the middle, untouched, black bars above
# and below -- the engine's own scale+pad. The logo keeps its place on the picture. 16:9 or narrower masters: the
# frame of before. Kill switch: BIDHAAN_LETTERBOX=0.
# Proven: test_bot_letterbox27 33/33 (incl. real ffmpeg: the picture between the bars is pixel for pixel the
# master's), run_suites27.sh (13 suites same verdict live vs patched, the bot22-26 tests pass on the patched copy),
# a real 75-s CBI 5 render through the engine at 1920x1080 watched (bars 138 px, logo on the picture).
set -e
Z=/opt/dubsync2/scratch/bot27
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
cmp -s dubsync_job.py $Z/live/dubsync_job.py || { echo "live dubsync_job.py changed since bot27 was tested -- refusing"; exit 1; }
cmp -s bot.py $Z/live/bot.py || { echo "live bot.py changed since bot27 was tested -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp dubsync_job.py $B/x/
cp $Z/patch_bot_letterbox27.py $Z/test_bot_letterbox27.py tools/
python3 tools/patch_bot_letterbox27.py $B/x >/dev/null
cmp -s $B/x/dubsync_job.py $Z/new/dubsync_job.py && echo "rebuilt file == tested bot27" \
  || { echo "rebuilt file differs from the tested bot27 -- refusing"; exit 1; }
python3 -m py_compile $B/x/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot27-$TS
mkdir -p $K
cp -p dubsync_job.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $B/x/dubsync_job.py .
docker cp dubsync_job.py bidhaan-logoedit:/app/dubsync_job.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < dubsync_job.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/dubsync_job.py")
[ "$a" = "$b" ] && echo "container dubsync_job.py == repo" || { echo "container dubsync_job.py differs"; exit 1; }
docker exec bidhaan-logoedit python3 -c "import dubsync_job as d; print('LETTERBOX_169', d.LETTERBOX_169, '| 1920x804 ->', d._frame_169(1920, 804), '| 1920x1080 ->', d._frame_169(1920, 1080))"
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "Traceback|Error" | grep -v "Task was destroyed\|AUTH_KEY\|CancelledError" | head -4
rm -rf $B
echo "backup of the previous file: $K"
echo DEPLOY_BOT27 DONE $TS
