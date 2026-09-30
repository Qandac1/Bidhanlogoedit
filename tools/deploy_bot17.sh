#!/bin/sh
# Deploy bot17 = bot16 + the report says only what is true of the delivered film (John 2026-09-30, Hebbuli):
#   stale "film starts at" line left out after the opening step; the expected length counts the opening and
#   ending put back (no false "duration" QA note); the spots list puts the repeats WE added first and names the
#   Somali copy's own (tools/repeat_split.py gains "pairs", its other output unchanged -- proven identical).
# test_bot_report17 10/10 on the real Hebbuli run (live bot16 fails it); the 16 other suites same as live.
set -e
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
Z=/opt/dubsync2/scratch/bot17
[ "$(md5sum < $Z/repeat_split.py | cut -c1-12)" = "d61adfffcce0" ] || { echo "repeat_split.py is not the tested file -- refusing"; exit 1; }
cd /opt/Bidhanlogoedit
B=$(mktemp -d)
cp dubsync_job.py $B/
cp $Z/patch_bot_report17.py $Z/test_bot_report17.py tools/
python3 tools/patch_bot_report17.py $B/dubsync_job.py >/dev/null
cmp -s $B/dubsync_job.py $Z/dubsync_job.py && echo "rebuilt dubsync_job.py == tested bot17"   || { echo "dubsync_job.py differs from bot17 -- refusing"; exit 1; }
cmp -s bot.py $Z/bot.py || { echo "live bot.py changed since bot17 was tested -- refusing"; exit 1; }
python3 -m py_compile $B/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot17-$TS
mkdir -p $K
cp -p dubsync_job.py /opt/dubsync2/tools/repeat_split.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $Z/repeat_split.py /opt/dubsync2/tools/repeat_split.py
cp $B/dubsync_job.py .
docker cp dubsync_job.py bidhaan-logoedit:/app/dubsync_job.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < dubsync_job.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/dubsync_job.py")
[ "$a" = "$b" ] && echo "container dubsync_job.py == repo" || { echo "container dubsync_job.py differs"; exit 1; }
/opt/dubsync2/.venv/bin/python tools/test_bot_report17.py /opt/Bidhanlogoedit /opt/dubsync2/tools/repeat_split.py | tail -1
python3 tools/test_bot_tail.py /opt/Bidhanlogoedit | tail -1
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error" | grep -v "Task was destroyed" | head -3
rm -rf $B
echo "backup of the previous files: $K"
echo DEPLOY_BOT17 DONE $TS
