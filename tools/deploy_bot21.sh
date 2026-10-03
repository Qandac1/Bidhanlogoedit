#!/bin/sh
# Deploy bot21: the disk-space guard (John 2026-10-03: Sardar 2 INCOMPLETE, "-28 No space left on device").
# Before a film and before each step that writes it again the bot makes sure the space is there
# (tools/space_guard.py clears regenerable data); a full disk stops the job at once with a plain message;
# the opening / opening-voice step that died on a full disk is run once more.
# Proven: test_bot_space21 33/33 (same steps, bytes, report and stats as the live bot when space is enough),
# 13 existing suites give the same verdict on the live and the patched copy.
set -e
Z=/opt/dubsync2/scratch/bot21
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
[ -f /opt/dubsync2/tools/space_guard.py ] || { echo "space_guard.py missing -- refusing"; exit 1; }
python3 /opt/dubsync2/tools/space_guard.py status >/dev/null || { echo "space_guard.py does not run -- refusing"; exit 1; }
docker exec bidhaan-logoedit /opt/dubsync2/.venv/bin/python /opt/dubsync2/tools/space_guard.py status >/dev/null \
  || { echo "space_guard.py does not run INSIDE the container -- refusing"; exit 1; }
cmp -s dubsync_job.py $Z/live/dubsync_job.py || { echo "live dubsync_job.py changed since bot21 was tested -- refusing"; exit 1; }
B=$(mktemp -d)
cp dubsync_job.py $B/
cp $Z/patch_bot_space21.py $Z/test_bot_space21.py tools/
python3 tools/patch_bot_space21.py $B/dubsync_job.py >/dev/null
cmp -s $B/dubsync_job.py $Z/new/dubsync_job.py && echo "rebuilt dubsync_job.py == tested bot21" || { echo "rebuilt file differs from the tested bot21 -- refusing"; exit 1; }
python3 -m py_compile $B/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot21-$TS
mkdir -p $K
cp -p dubsync_job.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $B/dubsync_job.py .
docker cp dubsync_job.py bidhaan-logoedit:/app/dubsync_job.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < dubsync_job.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/dubsync_job.py")
[ "$a" = "$b" ] && echo "container dubsync_job.py == repo" || { echo "container dubsync_job.py differs"; exit 1; }
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error|not available" | grep -v "Task was destroyed" | head -4
rm -rf $B
echo "backup of the previous dubsync_job.py: $K"
echo DEPLOY_BOT21 DONE $TS
