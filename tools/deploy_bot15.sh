#!/bin/sh
# Deploy bot15 = bot14 + the report's "repeated footage" counts only repeats WE added; the Somali copy's own
# repeats are named, shown as it has them (tools/repeat_split.py; test_bot_repeats 4/4, truth 13/13, panels 18/18).
# Refuses unless the bot is idle and the rebuilt file equals the tested bot15.
set -e
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
B=$(mktemp -d)
cp dubsync_job.py $B/
python3 tools/patch_bot_repeats.py $B/dubsync_job.py >/dev/null
cmp -s $B/dubsync_job.py /opt/dubsync2/scratch/bot15/dubsync_job.py && echo "rebuilt dubsync_job.py == tested bot15" \
  || { echo "dubsync_job.py differs from bot15 -- refusing"; exit 1; }
cmp -s bot.py /opt/dubsync2/scratch/bot15/bot.py || { echo "live bot.py changed since bot15 was tested -- refusing"; exit 1; }
python3 -m py_compile $B/dubsync_job.py
[ -f /opt/dubsync2/tools/repeat_split.py ] || { echo "tools/repeat_split.py missing -- refusing"; exit 1; }
TS=$(date +%Y%m%d-%H%M)
cp -p dubsync_job.py /opt/dubsync2/scratch/dubsync_job.py.pre-bot15-$TS
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $B/dubsync_job.py .
docker cp dubsync_job.py bidhaan-logoedit:/app/dubsync_job.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < dubsync_job.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/dubsync_job.py")
[ "$a" = "$b" ] && echo "container dubsync_job.py == repo" || { echo "container dubsync_job.py differs"; exit 1; }
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error" | grep -v "Task was destroyed" | head -3
rm -rf $B
echo DEPLOY_BOT15 DONE $TS
