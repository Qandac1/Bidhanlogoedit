#!/bin/sh
# bot29: every existing bot suite on the LIVE copy and on the PATCHED copy -- the verdict line must be the same
# (and a pass) -- then the tests of bot22-28 on the patched copy. Runs inside the bot container; only when idle.
Z=/opt/dubsync2/scratch/bot29
T=/opt/Bidhanlogoedit/tools
sh $T/bot_idle.sh || exit 1
fail=0
for s in autorepair brandrepair cutsummary dubaudio opening repeats restorefix samecontent speedretry truth credits19 tail panels; do
  a=$(docker exec bidhaan-logoedit python3 $T/test_bot_$s.py $Z/live 2>&1 | tail -1 | cut -c1-90)
  b=$(docker exec bidhaan-logoedit python3 $T/test_bot_$s.py $Z/new 2>&1 | tail -1 | cut -c1-90)
  if [ "$a" = "$b" ]; then echo "SAME  $s: $b"; else echo "DIFF  $s: live[$a] new[$b]"; fail=1; fi
done
c=$(docker exec bidhaan-logoedit python3 $T/test_bot_contract.py $Z/live $Z/new 2>&1 | tail -1 | cut -c1-90)
echo "      contract (live vs new): $c"
# the tests of the earlier bot changes, each against the baseline it was written for (its control needs the bot
# from BEFORE that change); shortgeom22 against today's live bot
for pair in "shortgeom22 $Z/live" "zoomweak23 /opt/dubsync2/scratch/bot23/live" "notclean24 /opt/dubsync2/scratch/bot24/live" "weakgate25 /opt/dubsync2/scratch/bot25/live" "syncfaults26 /opt/dubsync2/scratch/bot26/live" "letterbox27 /opt/dubsync2/scratch/bot27/live" "fit28 /opt/dubsync2/scratch/bot28/live"; do
  set -- $pair
  r=$(docker exec bidhaan-logoedit python3 $T/test_bot_$1.py $2 $Z/new 2>&1 | tail -1 | cut -c1-90)
  echo "      earlier test $1 on the bot29 copy: $r"
  case "$r" in *"ALL PASS"*) ;; *) fail=1 ;; esac
done
[ $fail = 0 ] && echo "SUITES29 SAME ON LIVE AND NEW" || echo "SUITES29 DIFFER"
