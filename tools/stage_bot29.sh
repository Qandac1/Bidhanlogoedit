#!/bin/sh
# bot29 staging: a copy of the live bot (scratch/bot29/live) and the same with the patch + the page (scratch/bot29/new).
set -e
Z=/opt/dubsync2/scratch/bot29
rm -rf $Z/live $Z/new
mkdir -p $Z/live $Z/new/web_public
cp /opt/Bidhanlogoedit/*.py $Z/live/
cp /opt/Bidhanlogoedit/*.py $Z/new/
cp $Z/place.html $Z/new/web_public/place.html
python3 $Z/patch_bot_logoplace29.py $Z/new
python3 -m py_compile $Z/new/bot.py
diff $Z/live/bot.py $Z/new/bot.py | grep -c "^[<>]" || true
echo STAGE_BOT29 DONE
