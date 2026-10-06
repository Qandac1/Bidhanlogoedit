#!/bin/sh
# Deploy bot36b on top of the installed bot36: the Studio falls back to the other set's video (one function of
# bot.py; patch_bot_studio36.py applies only its last step to an installed bot36).
# Gates: the bot is idle; the suites passed on the final copy; the installed bot.py is the one the upgrade was
# tested on; the rebuilt file equals the tested one. Backup; restart; if the bot does not come up, the file of
# before is put back.
set -e
Z=/opt/dubsync2/scratch/bot36
R=/opt/Bidhanlogoedit
idle() { sh $R/tools/bot_idle.sh | grep -q "BOT IDLE"; }
idle || { echo "BOT BUSY - nothing installed"; exit 2; }
grep -q "SUITES36 SAME ON LIVE AND NEW" $Z/suites36.log || { echo "the suites did not pass - nothing installed"; exit 3; }
cd $R
cmp -s bot.py $Z/b/live/bot.py || { echo "the installed bot.py is not the one the upgrade was tested on -- refusing"; exit 1; }
cmp -s $Z/new/bot.py $Z/b/new/bot.py || { echo "the suites ran on another copy than the upgrade -- refusing"; exit 1; }
B=$(mktemp -d)
cp bot.py branding.py $B/
python3 $Z/patch_bot_studio36.py $B >/dev/null
cmp -s $B/bot.py $Z/b/new/bot.py && cmp -s $B/branding.py branding.py && echo "rebuilt bot.py == tested; branding.py untouched" || { echo "the rebuilt files differ from the tested ones -- refusing"; exit 1; }
python3 -m py_compile $B/bot.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot36b-$TS
mkdir -p $K
cp -p bot.py $K/
cp $Z/patch_bot_studio36.py $Z/test_bot_studio36.py $Z/run_suites36.sh $Z/deploy_bot36b.sh tools/
idle || { echo "BOT BUSY now - nothing installed"; exit 2; }
cp $B/bot.py bot.py
docker cp bot.py bidhaan-logoedit:/app/bot.py
docker restart bidhaan-logoedit >/dev/null
sleep 14
up=$(docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit || true)
echo "$up"
okk=1
case "$up" in *"Up "*) ;; *) okk=0 ;; esac
a=$(md5sum < bot.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/bot.py" 2>/dev/null || echo none)
[ "$a" = "$b" ] && echo "container bot.py == repo" || { echo "container bot.py differs"; okk=0; }
docker logs --since 40s bidhaan-logoedit 2>&1 | grep -E "Traceback|SyntaxError|ImportError|NameError" | head -3 > $B/err.txt || true
[ -s $B/err.txt ] && { echo "the bot's start shows an error:"; cut -c1-200 $B/err.txt; okk=0; }
if [ $okk = 0 ]; then
  echo "ROLLING BACK to the bot.py of before"
  cp -p $K/bot.py bot.py; docker cp bot.py bidhaan-logoedit:/app/bot.py; docker restart bidhaan-logoedit >/dev/null; sleep 12
  docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
  echo "DEPLOY_BOT36B ROLLED BACK (backup $K)"; exit 4
fi
rm -rf $B
echo "backup of the previous file: $K"
echo DEPLOY_BOT36B DONE $TS
