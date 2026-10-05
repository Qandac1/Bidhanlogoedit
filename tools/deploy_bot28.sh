#!/bin/sh
# Deploy bot28: the LOGO-ONLY path fits a video into the frame (black bars) instead of stretching it.
# branding.build_filter used a plain scale=W:H to the setting: a 2.39:1 picture came out stretched x1.34 into 16:9
# (tools/probe_batch_stretch.py). Now a source whose shape differs from the frame's by more than 2 % is scaled to
# fit and padded with black; banner covers and logos are placed on the picture. A source of the frame's shape and
# the "Source" setting: the filter of before, character for character. Kill switch: BIDHAAN_FIT=0.
# Proven: test_bot_fit28 17/17 (real ffmpeg: circle round, picture pixel for pixel, covers / logos in place,
# render() end to end), run_suites28.sh (13 suites same verdict live vs patched, bot22-27 tests pass).
set -e
Z=/opt/dubsync2/scratch/bot28
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
cmp -s branding.py $Z/live/branding.py || { echo "live branding.py changed since bot28 was tested -- refusing"; exit 1; }
cmp -s bot.py $Z/live/bot.py || { echo "live bot.py changed since bot28 was tested -- refusing"; exit 1; }
cmp -s dubsync_job.py $Z/live/dubsync_job.py || { echo "live dubsync_job.py changed since bot28 was tested -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp branding.py $B/x/
cp $Z/patch_bot_fit28.py $Z/test_bot_fit28.py tools/
python3 tools/patch_bot_fit28.py $B/x >/dev/null
cmp -s $B/x/branding.py $Z/new/branding.py && echo "rebuilt file == tested bot28" \
  || { echo "rebuilt file differs from the tested bot28 -- refusing"; exit 1; }
python3 -m py_compile $B/x/branding.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot28-$TS
mkdir -p $K
cp -p branding.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $B/x/branding.py .
docker cp branding.py bidhaan-logoedit:/app/branding.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < branding.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/branding.py")
[ "$a" = "$b" ] && echo "container branding.py == repo" || { echo "container branding.py differs"; exit 1; }
docker exec bidhaan-logoedit python3 -c "import branding as b; print('FIT_ON', b.FIT_ON, '| 1920x804 in 1920x1080 ->', b._fit_rect(1920, 804, 1920, 1080), '| 1280x720 in 1920x1080 ->', b._fit_rect(1280, 720, 1920, 1080))"
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "Traceback|Error" | grep -v "Task was destroyed\|AUTH_KEY\|CancelledError" | head -4
rm -rf $B
echo "backup of the previous file: $K"
echo DEPLOY_BOT28 DONE $TS
