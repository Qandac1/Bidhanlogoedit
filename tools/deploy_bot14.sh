#!/bin/sh
# Deploy bot14 = bot13 + the banner and dub-sync flows kept apart: the Next-movie intake asks, a leftover dub selection never draws a banner panel, /cancel stops the banner scan (test_bot_panels 18/18; the 9 other suites pass).
# Refuses unless the bot is idle and the rebuilt files equal the tested bot14.
set -e
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
B=$(mktemp -d)
cp bot.py dubsync_job.py $B/
for p in patch_bot_panels; do  # live = bot13 already
  python3 tools/$p.py $B >/dev/null
done
for f in bot.py dubsync_job.py; do
  cmp -s $B/$f /opt/dubsync2/scratch/bot14/$f && echo "rebuilt $f == tested bot14" || { echo "$f differs from bot14 -- refusing"; exit 1; }
done
python3 -m py_compile $B/bot.py $B/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
cp -p bot.py /opt/dubsync2/scratch/bot.py.pre-bot14-$TS
cp -p dubsync_job.py /opt/dubsync2/scratch/dubsync_job.py.pre-bot14-$TS
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $B/bot.py $B/dubsync_job.py .
docker cp bot.py bidhaan-logoedit:/app/bot.py
docker cp dubsync_job.py bidhaan-logoedit:/app/dubsync_job.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
for f in bot.py dubsync_job.py; do
  a=$(md5sum < $f); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/$f")
  [ "$a" = "$b" ] && echo "container $f == repo" || { echo "container $f differs"; exit 1; }
done
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error" | grep -v "Task was destroyed" | head -3
rm -rf $B
echo DEPLOY_BOT14 DONE $TS
