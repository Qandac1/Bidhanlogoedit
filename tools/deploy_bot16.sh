#!/bin/sh
# Deploy bot16 + the opening/ending tools TOGETHER (John 2026-09-30: "wait and ship both together").
#   * the opening: the HD intro with the Somali voice, from the end of the channel's bumper (FANPROJ / StreamNxt =
#     the clip the copy shares with other films' copies -- tools/shared_bumper.py); opening_regress 10/10.
#   * the ending: the film's last scene the channel covered with its credits box goes on with its Somali voice on
#     the HD's own picture (tools/tail_restore.py, insert_head.py --append).
#   * end credits: the HD's own roll found by its upward scroll (credits_scroll.py) -- a dim roll with music no
#     longer reads as "a scene".
#   * bot16 report: "🎬 ending: ...", "⚠️ ending: ...", and an end-credits SKIP is shown.
# Refuses unless the bot is idle, every staged tool is the tested one (md5), and the rebuilt bot file == bot16.
set -e
S=/opt/dubsync2_goat/tools_fix
L=/opt/dubsync2/tools
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
chk() { [ "$(md5sum < "$1" | cut -c1-12)" = "$2" ] || { echo "$1 is not the tested file -- refusing"; exit 1; }; }
chk $S/insert_head.py      a6dc676b5214
chk $S/opening_restore.py  73f739c9eeab
chk $S/opening_regress.py  fc7f0eaafa63
chk $S/tail_restore.py     4f0b60f62b2a
chk $S/shared_bumper.py    173b13a19894
chk $S/root/append_credits.py c560d1babd04
[ -f $L/credits_scroll.py ] || { echo "tools/credits_scroll.py missing -- refusing"; exit 1; }
[ -f $L/frame_audit.py ] || { echo "tools/frame_audit.py missing -- refusing"; exit 1; }
cd /opt/Bidhanlogoedit
B=$(mktemp -d)
cp dubsync_job.py $B/
cp /opt/dubsync2/scratch/bot16/patch_bot_tail.py /opt/dubsync2/scratch/bot16/test_bot_tail.py tools/
python3 tools/patch_bot_tail.py $B/dubsync_job.py >/dev/null
cmp -s $B/dubsync_job.py /opt/dubsync2/scratch/bot16/dubsync_job.py && echo "rebuilt dubsync_job.py == tested bot16" \
  || { echo "dubsync_job.py differs from bot16 -- refusing"; exit 1; }
cmp -s bot.py /opt/dubsync2/scratch/bot16/bot.py || { echo "live bot.py changed since bot16 was tested -- refusing"; exit 1; }
python3 -m py_compile $B/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot16-$TS
mkdir -p $K
cp -p dubsync_job.py $K/
for f in insert_head opening_restore opening_regress shared_bumper; do cp -p $L/$f.py $K/; done
cp -p /opt/dubsync2/append_credits.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
for f in insert_head opening_restore opening_regress tail_restore shared_bumper; do cp $S/$f.py $L/$f.py; done
cp $S/root/append_credits.py /opt/dubsync2/append_credits.py
cp $B/dubsync_job.py .
docker cp dubsync_job.py bidhaan-logoedit:/app/dubsync_job.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < dubsync_job.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/dubsync_job.py")
[ "$a" = "$b" ] && echo "container dubsync_job.py == repo" || { echo "container dubsync_job.py differs"; exit 1; }
docker exec bidhaan-logoedit sh -c "cd /opt/dubsync2 && .venv/bin/python -c 'import sys; sys.path.insert(0,\"tools\"); import shared_bumper, credits_scroll; print(\"tools import OK in the container\")'"
python3 tools/test_bot_tail.py /opt/Bidhanlogoedit | tail -1
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error" | grep -v "Task was destroyed" | head -3
rm -rf $B
echo "backup of the previous files: $K"
echo DEPLOY_BOT16 DONE $TS
