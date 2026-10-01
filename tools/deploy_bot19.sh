#!/bin/sh
# Deploy the ending fix + bot19 (John 2026-10-01, Sardar: 28 s of TAMIL voice at the end -- the Somali copy's
# mid-credits dialogue was cut by the 60 s cap, the credits step then played the HD's sound there).
#   tools/tail_restore.py: looks 300 s ahead; voice / picture / SOUND-BED proofs per second on the film line
#   (wrong-offset controls both ways), one run (20 s bridge), kept only up to its last Somali line.
#   bot19: "end credits kept: the Somali copy runs to the film's own end" instead of a false warning.
# Proven: Sardar 58 -> 82 s (Somali to 9593.6, then the HD credits); regression on 13 titles: unchanged except
# Sardar and Bheemaa (+5 s = the film's last shots, eye-checked); Hebbuli unchanged (15.5 s).
set -e
Z=/opt/dubsync2/scratch
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
[ "$(md5sum < /opt/dubsync2_goat/tools_fix/tail_restore.py | cut -c1-12)" = "24b025ba24a5" ] || { echo "tail_restore.py is not the tested file -- refusing"; exit 1; }
cd /opt/Bidhanlogoedit
B=$(mktemp -d)
cp dubsync_job.py $B/
cp $Z/bot19/patch_bot_credits19.py $Z/bot19/test_bot_credits19.py tools/
python3 tools/patch_bot_credits19.py $B/dubsync_job.py >/dev/null
cmp -s $B/dubsync_job.py $Z/bot19/dubsync_job.py && echo "rebuilt dubsync_job.py == tested bot19" || { echo "dubsync_job.py differs from bot19 -- refusing"; exit 1; }
cmp -s bot.py $Z/bot19/bot.py || { echo "live bot.py changed since bot19 was tested -- refusing"; exit 1; }
python3 -m py_compile $B/dubsync_job.py
TS=$(date +%Y%m%d-%H%M)
K=$Z/pre-bot19-$TS
mkdir -p $K
cp -p dubsync_job.py /opt/dubsync2/tools/tail_restore.py $K/
sh /opt/Bidhanlogoedit/tools/bot_idle.sh
cp /opt/dubsync2_goat/tools_fix/tail_restore.py /opt/dubsync2/tools/tail_restore.py
cp $B/dubsync_job.py .
docker cp dubsync_job.py bidhaan-logoedit:/app/dubsync_job.py
docker restart bidhaan-logoedit >/dev/null
sleep 12
docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
a=$(md5sum < dubsync_job.py); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/dubsync_job.py")
[ "$a" = "$b" ] && echo "container dubsync_job.py == repo" || { echo "container dubsync_job.py differs"; exit 1; }
python3 tools/test_bot_credits19.py /opt/Bidhanlogoedit | tail -1
python3 tools/test_bot_tail.py /opt/Bidhanlogoedit | tail -1
docker logs --since 20s bidhaan-logoedit 2>&1 | grep -E "started|Traceback|Error" | grep -v "Task was destroyed" | head -3
rm -rf $B
echo "backup of the previous files: $K"
echo DEPLOY_BOT19 DONE $TS
