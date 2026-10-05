#!/bin/sh
# bot28 staging: a copy of the live bot (scratch/bot28/live) and the same with the patch (scratch/bot28/new).
set -e
Z=/opt/dubsync2/scratch/bot28
rm -rf $Z/live $Z/new
mkdir -p $Z/live $Z/new
cp /opt/Bidhanlogoedit/*.py $Z/live/
cp /opt/Bidhanlogoedit/*.py $Z/new/
python3 $Z/patch_bot_fit28.py $Z/new
python3 -m py_compile $Z/new/branding.py
diff $Z/live/branding.py $Z/new/branding.py | grep -c "^[<>]" || true
echo STAGE_BOT28 DONE
