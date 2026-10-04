#!/bin/sh
# Deploy bot25: the weak-analysis gate (John 2026-10-04: "wasting time ... keep rendering and the next film is wrong
# again"). After analyze, unconfirmed > 5 %: measure the zoom, analyse again with it; still > 10 %: NOT rendered.
# Proven: test_bot_weakgate25 25/25, bot23 + bot24 tests pass on it, run_suites25.sh same verdict live vs patched.
# run_suites22.sh: the existing suites give the same verdict on the live and the patched copy.
set -e
Z=/opt/dubsync2/scratch/bot25
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
[ -f /opt/dubsync2/pair_zoom.py ] || { echo "pair_zoom.py missing -- refusing"; exit 1; }
cmp -s dubsync_job.py $Z/live/dubsync_job.py || { echo "live dubsync_job.py changed since bot25 was tested -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp dubsync_job.py $B/x/
cp $Z/patch_bot_weakgate25.py $Z/test_bot_weakgate25.py tools/
python3 tools/patch_bot_weakgate25.py $B/x >/dev/null
cmp -s $B/x/dubsync_job.py $Z/new/dubsync_job.py && echo "rebuilt dubsync_job.py == tested bot25" || { echo "rebuilt file differs from the tested bot25 -- refusing"; exit 1; }
python3 -m py_compile $B/x/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot25-$TS
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
echo DEPLOY_BOT25 DONE $TS
