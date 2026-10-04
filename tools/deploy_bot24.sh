#!/bin/sh
# Deploy bot24: (A) a delivery whose own measurements are bad is headed "NOT CLEAN: do not publish" (picture check
# < 94.5 %, repeats we added > 10 s, unconfirmed > 5 %) -- John 2026-10-04: Toxic 2026 was headed "complete" with
# 414 of 4711 shots unmatched; (B) when a title's zoom window changes, its saved analyses are moved aside (they
# were made with the other framing); parked folders get a unique name.
# Proven: test_bot_notclean24 39/39 (clean films: the SAME report text), bot22 + bot23 tests still pass on it,
# run_suites24.sh same verdict live vs patched.
set -e
Z=/opt/dubsync2/scratch/bot24
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cd /opt/Bidhanlogoedit
cmp -s bot.py $Z/live/bot.py || { echo "live bot.py changed since bot24 was tested -- refusing"; exit 1; }
cmp -s dubsync_job.py $Z/live/dubsync_job.py || { echo "live dubsync_job.py changed since bot24 was tested -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp bot.py dubsync_job.py $B/x/
cp $Z/patch_bot_notclean24.py $Z/test_bot_notclean24.py tools/
python3 tools/patch_bot_notclean24.py $B/x >/dev/null
cmp -s $B/x/bot.py $Z/new/bot.py && cmp -s $B/x/dubsync_job.py $Z/new/dubsync_job.py && echo "rebuilt files == tested bot24" \
  || { echo "rebuilt files differ from the tested bot24 -- refusing"; exit 1; }
python3 -m py_compile $B/x/bot.py $B/x/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot24-$TS
mkdir -p $K
cp -p bot.py dubsync_job.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $B/x/bot.py $B/x/dubsync_job.py .
docker cp bot.py bidhaan-logoedit:/app/bot.py
docker cp dubsync_job.py bidhaan-logoedit:/app/dubsync_job.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
for f in bot.py dubsync_job.py; do
  a=$(md5sum < $f); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/$f")
  [ "$a" = "$b" ] && echo "container $f == repo" || { echo "container $f differs"; exit 1; }
done
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "Traceback|Error" | grep -v "Task was destroyed\|AUTH_KEY\|CancelledError" | head -4
rm -rf $B
echo "backup of the previous files: $K"
echo DEPLOY_BOT24 DONE $TS
