#!/bin/sh
# Deploy bot18 + the engine's zoom window (John 2026-10-01, Sardar: a ZOOMED Somali copy was refused as "different
# films"). pair_zoom.py (engine root), patch_engine_zoom.py on the live engine (head_scan/speed/dense_align/cli),
# bot.py patched (zoom search on "different", window saved per title, John told).
# Proven: engine no-window identical (20 files: crops + 3 cache keys), window 8/8 vs 0/8; zoom controls 7 wrong
# pairs 0-3 parts, Sardar 10/10; test_bot_zoom18 10/10 in the container; Sardar engine stages with the window.
# Refuses unless the bot is idle and every file is the tested one.
set -e
Z=/opt/dubsync2/scratch
G=/opt/dubsync2_goat
SRC=/opt/dubsync2/src/dubsync2
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
[ "$(md5sum < $Z/zoom/pair_zoom.py | cut -c1-12)" = "8ca9af3239a4" ] || { echo "pair_zoom.py is not the tested file -- refusing"; exit 1; }
E=$(mktemp -d)
for f in head_scan speed dense_align cli; do cp $SRC/$f.py $E/; done
python3 $G/patch_engine_zoom.py $E >/dev/null
for f in head_scan speed dense_align cli; do
  cmp -s $E/$f.py $G/src_zoom/dubsync2/$f.py || { echo "engine $f.py rebuilt != tested src_zoom -- refusing"; exit 1; }
done
echo "engine files rebuilt == tested"
cd /opt/Bidhanlogoedit
B=$(mktemp -d)
cp bot.py $B/
cp $Z/bot18/patch_bot_zoom18.py $Z/bot18/test_bot_zoom18.py tools/
python3 tools/patch_bot_zoom18.py $B/bot.py >/dev/null
cmp -s $B/bot.py $Z/bot18/bot.py && echo "rebuilt bot.py == tested bot18" || { echo "bot.py differs from bot18 -- refusing"; exit 1; }
cmp -s dubsync_job.py $Z/bot18/dubsync_job.py || { echo "live dubsync_job.py changed since bot18 was tested -- refusing"; exit 1; }
python3 -m py_compile $B/bot.py
TS=$(date +%Y%m%d-%H%M)
K=$Z/pre-bot18-$TS
mkdir -p $K
cp -p bot.py $K/
for f in head_scan speed dense_align cli; do cp -p $SRC/$f.py $K/; done
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp $Z/zoom/pair_zoom.py /opt/dubsync2/pair_zoom.py
for f in head_scan speed dense_align cli; do cp $E/$f.py $SRC/$f.py; done
find $SRC -name "__pycache__" -prune -exec rm -rf {} +
cp $B/bot.py .
docker cp bot.py bidhaan-logoedit:/app/bot.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < bot.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/bot.py")
[ "$a" = "$b" ] && echo "container bot.py == repo" || { echo "container bot.py differs"; exit 1; }
docker exec bidhaan-logoedit sh -c "cd /opt/dubsync2 && .venv/bin/python -c 'import sys; sys.path.insert(0,\"/opt/dubsync2/src\"); from dubsync2 import head_scan; print(\"engine import OK, window registry:\", head_scan.HD_WINDOWS)'"
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error" | grep -v "Task was destroyed" | head -3
rm -rf $B $E
echo "backup of the previous files: $K"
echo DEPLOY_BOT18 DONE $TS
