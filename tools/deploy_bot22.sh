#!/bin/sh
# Deploy bot22: a SHORT pair (trailer / clip, both files < 5 min) the placement refused is analysed once more with
# the engine's short-clip geometry (John 2026-10-03: the Toxic trailer refused "not the same edit" though it IS the
# same trailer -- a screen-recorded player window, another shape, 2.6 % faster).
# Proven: test_bot_shortgeom22 23/23 (accepted pairs: same steps, bytes, report, stats as the live bot; refused
# short pair -> listed -> delivered; wrong short pair still refused; long pair unchanged; speed retry first),
# run_suites22.sh: the existing suites give the same verdict on the live and the patched copy.
set -e
Z=/opt/dubsync2/scratch/bot22
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
grep -q "SHORT_GEOM" /opt/dubsync2/src/dubsync2/head_scan.py || { echo "engine has no short-clip geometry -- refusing"; exit 1; }
cmp -s dubsync_job.py $Z/live/dubsync_job.py || { echo "live dubsync_job.py changed since bot22 was tested -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp dubsync_job.py $B/x/
cp $Z/patch_bot_shortgeom22.py $Z/test_bot_shortgeom22.py tools/
python3 tools/patch_bot_shortgeom22.py $B/x >/dev/null
cmp -s $B/x/dubsync_job.py $Z/new/dubsync_job.py && echo "rebuilt dubsync_job.py == tested bot22" || { echo "rebuilt file differs from the tested bot22 -- refusing"; exit 1; }
python3 -m py_compile $B/x/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot22-$TS
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
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error|not available" | grep -v "Task was destroyed" | head -4
rm -rf $B
echo "backup of the previous dubsync_job.py: $K"
echo DEPLOY_BOT22 DONE $TS
