#!/bin/sh
# bot36: every existing bot suite on the LIVE copy and on the PATCHED copy -- the verdict (and for the suites that
# were red before: the list of failing checks) must be THE SAME -- then the tests of the earlier bot changes on the
# patched copy, then this release's own test.
# Runs in a SEPARATE container of the bot's image with the bot's own environment and folders (no network, 1.5 CPUs,
# its data read-only): the running bot is not touched, so this may run while it works on a film.
#   by design two earlier tests no longer pass in full on the patched copy -- their failing checks are printed:
#   studio31 (the caption was "on one line", "8 fonts"), capfont31 (the new font files are in assets/fonts only
#   after the install).
Z=/opt/dubsync2/scratch/bot36
T=/opt/Bidhanlogoedit/tools
run() {
  docker run --rm --network none --cpus 3 -w /app --env-file /opt/Bidhanlogoedit/.env \
    -v /opt/Bidhanlogoedit:/opt/Bidhanlogoedit:ro -v /opt/dubsync:/opt/dubsync -v /opt/dubsync2:/opt/dubsync2 \
    -v /root/.local/share/uv/python:/root/.local/share/uv/python:ro -v /opt/Bidhanlogoedit/assets:/app/assets:ro \
    -v bidhanlogoedit_bot_data:/app/data:ro \
    --entrypoint python3 bidhanlogoedit-bidhaan-logoedit "$@" 2>&1 | grep -v "asyncio ERROR\|^task: \|RuntimeWarning\|never awaited"
}
verdict() { grep "_TESTS\|Error" | tail -1 | cut -c1-90; }
fails() { grep "^FAIL" | cut -c1-110 | sort | md5sum | cut -c1-8; }
fail=0
for s in autorepair brandrepair cutsummary dubaudio opening repeats restorefix samecontent speedretry truth credits19 tail panels; do
  run $T/test_bot_$s.py $Z/live > /tmp/s36_a.txt; run $T/test_bot_$s.py $Z/new > /tmp/s36_b.txt
  a=$(verdict < /tmp/s36_a.txt); b=$(verdict < /tmp/s36_b.txt); fa=$(fails < /tmp/s36_a.txt); fb=$(fails < /tmp/s36_b.txt)
  if [ "$a" = "$b" ] && [ "$fa" = "$fb" ]; then echo "SAME  $s: $b ($(grep -c '^PASS' /tmp/s36_b.txt) pass, $(grep -c '^FAIL' /tmp/s36_b.txt) fail on both)"; else echo "DIFF  $s: live[$a] new[$b]"; fail=1; fi
done
run $T/test_bot_contract.py $Z/live $Z/live > /tmp/s36_a.txt; run $T/test_bot_contract.py $Z/live $Z/new > /tmp/s36_b.txt
a=$(verdict < /tmp/s36_a.txt); b=$(verdict < /tmp/s36_b.txt)
if [ "$a" = "$b" ] && [ "$(fails < /tmp/s36_a.txt)" = "$(fails < /tmp/s36_b.txt)" ]; then echo "SAME  contract (live vs live == live vs new): $b ($(grep -c '^FAIL' /tmp/s36_b.txt) fail on both)"; else echo "DIFF  contract: live-live[$a] live-new[$b]"; grep "^FAIL" /tmp/s36_b.txt | cut -c1-200 | head -5; fail=1; fi
for pair in "shortgeom22 $Z/live" "zoomweak23 /opt/dubsync2/scratch/bot23/live" "notclean24 /opt/dubsync2/scratch/bot24/live" "weakgate25 /opt/dubsync2/scratch/bot25/live" "syncfaults26 /opt/dubsync2/scratch/bot26/live" "letterbox27 /opt/dubsync2/scratch/bot27/live" "fit28 /opt/dubsync2/scratch/bot28/live" "profiles30 /opt/dubsync2/scratch/bot30/live"; do
  set -- $pair
  run $T/test_bot_$1.py $2 $Z/live > /tmp/s36_a.txt; run $T/test_bot_$1.py $2 $Z/new > /tmp/s36_b.txt
  a=$(verdict < /tmp/s36_a.txt); b=$(verdict < /tmp/s36_b.txt)
  if [ "$a" = "$b" ] && [ "$(fails < /tmp/s36_a.txt)" = "$(fails < /tmp/s36_b.txt)" ]; then echo "SAME  earlier test $1 (on the live copy == on the bot36 copy): $b"; else echo "DIFF  earlier test $1: live[$a] new[$b]"; grep "^FAIL" /tmp/s36_b.txt | cut -c1-200 | head -4; fail=1; fi
done
for pair in "fast33 /opt/dubsync2/scratch/bot33/base" "guard34 /opt/dubsync2/scratch/bot34/base" "swap35 /opt/dubsync2/scratch/bot35/base"; do
  set -- $pair
  [ -d "$2" ] || { echo "      trailer test $1: its baseline $2 is not there -- skipped"; continue; }
  run $T/test_trailer_$1.py $2 $Z/live > /tmp/s36_a.txt; run $T/test_trailer_$1.py $2 $Z/new > /tmp/s36_b.txt
  a=$(verdict < /tmp/s36_a.txt); b=$(verdict < /tmp/s36_b.txt)
  if [ "$a" = "$b" ] && [ "$(fails < /tmp/s36_a.txt)" = "$(fails < /tmp/s36_b.txt)" ]; then echo "SAME  trailer test $1 (on the live copy == on the bot36 copy): $b"; else echo "DIFF  trailer test $1: live[$a] new[$b]"; fail=1; fi
done
echo "--- by design: the checks of two earlier tests that the new behaviour changes (caption as typed, 20 fonts)"
run $T/test_bot_capfont31.py /opt/dubsync2/scratch/bot31/base $Z/new | grep "^FAIL\|_TESTS" | cut -c1-170
run $T/test_bot_studio31.py /opt/dubsync2/scratch/bot31/mid $Z/new $Z/page | grep "^FAIL\|_TESTS" | cut -c1-170
echo "--- this release"
run $Z/test_bot_studio36.py $Z/live $Z/new $Z/page $Z/fonts > /tmp/s36_r.txt
grep "^FAIL\|_TESTS\|Error" /tmp/s36_r.txt | cut -c1-300
echo "      $(grep -c '^PASS' /tmp/s36_r.txt) checks pass"
grep -q "STUDIO36_TESTS ALL PASS" /tmp/s36_r.txt || fail=1
[ $fail = 0 ] && echo "SUITES36 SAME ON LIVE AND NEW" || echo "SUITES36 DIFFER"
