#!/bin/sh
# bot27 staging: a copy of the live bot (scratch/bot27/live) and the same with the patch (scratch/bot27/new).
set -e
Z=/opt/dubsync2/scratch/bot27
rm -rf $Z/live $Z/new
mkdir -p $Z/live $Z/new
cp /opt/Bidhanlogoedit/*.py $Z/live/
cp /opt/Bidhanlogoedit/*.py $Z/new/
python3 $Z/patch_bot_letterbox27.py $Z/new
python3 -m py_compile $Z/new/dubsync_job.py
diff $Z/live/dubsync_job.py $Z/new/dubsync_job.py | grep -c "^[<>]" || true
echo STAGE_BOT27 DONE
