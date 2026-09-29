#!/bin/sh
# Deploy bot13 = bot12 + two hard rules: Somali-voiced film cut by mistake and a voice measured off the lips are INCOMPLETE; lip sync measured on every film (test_bot_truth 13/13, all suites same as bot12).
# Refuses unless the bot is idle and the rebuilt files equal the tested bot13.
set -e
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
B=$(mktemp -d)
cp bot.py dubsync_job.py $B/
for p in patch_bot_truth; do  # live = bot12 already
  python3 tools/$p.py $B >/dev/null
done
for f in bot.py dubsync_job.py; do
  cmp -s $B/$f /opt/dubsync2_goat/bot13/$f && echo "rebuilt $f == tested bot13" || { echo "$f differs from bot13 -- refusing"; exit 1; }
done
python3 -m py_compile $B/bot.py $B/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
cp -p bot.py /opt/dubsync2/scratch/bot.py.pre-bot13-$TS
cp -p dubsync_job.py /opt/dubsync2/scratch/dubsync_job.py.pre-bot13-$TS
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
echo DEPLOY_BOT13 DONE $TS
