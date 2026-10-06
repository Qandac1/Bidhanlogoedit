#!/bin/sh
# Deploy bot36: THE STUDIO -- the caption as typed, 12 more fonts, the waiting video's own pictures.
#   patch_bot_studio36.py   bot.py + branding.py (the render's build_filter is not touched)
#   place.html              the Studio page
#   12 font files           assets/fonts (Debian's own packages) + FONTS.md
# Proven on copies: test_bot_studio36 43/43 in the bot's container, run_suites36.sh (every earlier suite the same
# on the live and the patched copy), the page driven in a browser on a real staged opening.
# Only when the bot is idle; backups first; every rebuilt file must equal its tested copy; if the bot does not
# come up with the new files, the old ones are put back and it is started again.
set -e
Z=/opt/dubsync2/scratch/bot36
R=/opt/Bidhanlogoedit
idle() { sh $R/tools/bot_idle.sh | grep -q "BOT IDLE"; }
idle || { echo "BOT BUSY - nothing installed"; exit 2; }
grep -q "SUITES36 SAME ON LIVE AND NEW" $Z/suites36.log || { echo "the suites did not pass - nothing installed"; exit 3; }
cd $R
cmp -s bot.py $Z/live/bot.py || { echo "live bot.py changed since the tests -- refusing"; exit 1; }
cmp -s branding.py $Z/live/branding.py || { echo "live branding.py changed since the tests -- refusing"; exit 1; }
cmp -s $Z/page/place.html $Z/place.html || { echo "the tested page is not the staged page -- refusing"; exit 1; }
B=$(mktemp -d)
mkdir -p $B/x
cp bot.py branding.py $B/x/
python3 $Z/patch_bot_studio36.py $B/x >/dev/null
for f in bot.py branding.py; do
  cmp -s $B/x/$f $Z/new/$f && echo "rebuilt $f == tested" || { echo "rebuilt $f differs from the tested copy -- refusing"; exit 1; }
  python3 -m py_compile $B/x/$f
done
TS=$(date +%Y%m%d-%H%M)
K=/opt/dubsync2/scratch/pre-bot36-$TS
mkdir -p $K
cp -p bot.py branding.py web_public/place.html assets/fonts/FONTS.md $K/
cp -p /var/lib/docker/volumes/bidhanlogoedit_bot_data/_data/user_settings.json $K/user_settings.json
# 1. the fonts (new files only; nothing that is there is replaced)
n=0
for f in /opt/dubsync2/scratch/fonts36/files/*; do
  b=$(basename "$f")
  if [ ! -e "assets/fonts/$b" ]; then cp -p "$f" "assets/fonts/$b"; n=$((n + 1)); fi
done
echo "fonts added: $n (now $(ls assets/fonts | grep -c -i '\.[ot]tf$') font files)"
grep -q "LeagueSpartan-Bold.otf" assets/fonts/FONTS.md || cat $Z/FONTS_add36.md >> assets/fonts/FONTS.md
# 2. the page, the tools
cp $Z/page/place.html web_public/place.html
cp $Z/patch_bot_studio36.py $Z/test_bot_studio36.py $Z/caption_cases36.json $Z/make_caption_cases36.py $Z/run_suites36.sh $Z/stage_site36.py $Z/e2e_studio36.py $Z/deploy_bot36.sh $Z/check_dub_video36.py $Z/wait_quiet.py tools/
idle || { echo "BOT BUSY now - the page and the fonts are in (they change nothing for the running bot), the bot files are NOT: run again"; exit 2; }
# 3. the bot
cp $B/x/bot.py bot.py
cp $B/x/branding.py branding.py
docker cp bot.py bidhaan-logoedit:/app/bot.py
docker cp branding.py bidhaan-logoedit:/app/branding.py
docker restart bidhaan-logoedit >/dev/null
sleep 14
up=$(docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit || true)
echo "$up"
okk=1
case "$up" in *"Up "*) ;; *) okk=0 ;; esac
for f in bot.py branding.py; do
  a=$(md5sum < $f); b=$(docker exec bidhaan-logoedit sh -c "md5sum < /app/$f" 2>/dev/null || echo none)
  [ "$a" = "$b" ] && echo "container $f == repo" || { echo "container $f differs"; okk=0; }
done
docker logs --since 40s bidhaan-logoedit 2>&1 | grep -E "Traceback|SyntaxError|ImportError|NameError" | head -3 > $B/err.txt || true
[ -s $B/err.txt ] && { echo "the bot's start shows an error:"; cat $B/err.txt | cut -c1-200; okk=0; }
if [ $okk = 0 ]; then
  echo "ROLLING BACK to the files of before"
  cp -p $K/bot.py bot.py; cp -p $K/branding.py branding.py; cp -p $K/place.html web_public/place.html
  docker cp bot.py bidhaan-logoedit:/app/bot.py; docker cp branding.py bidhaan-logoedit:/app/branding.py
  docker restart bidhaan-logoedit >/dev/null; sleep 12
  docker ps --format "{{.Names}} {{.Status}}" | grep bidhaan-logoedit
  echo "DEPLOY_BOT36 ROLLED BACK (backup $K)"; exit 4
fi
docker exec bidhaan-logoedit python3 -c "
import branding as b
print('fonts known', len(b.CAPTION_FONTS), '| every file there:', all(b.caption_font_file(k) != b.FONT or k == 'classic' for k in b.CAPTION_FONTS))
print('caption as typed:', repr(b.caption_lines('     U GAAR AH\nRASHKA BOY MUSALSAL TV')), '->', b.caption_text_arg(b.caption_lines('     U GAAR AH\nRASHKA BOY'))[1][:12].encode())
"
W=https://159-195-136-50.sslip.io/logo
echo "page $(curl -s -o /dev/null -w '%{http_code}' $W/place.html) $(curl -s $W/place.html | grep -c 'function capNorm') | new font $(curl -s -o /dev/null -w '%{http_code}' $W/fonts/LeagueSpartan-Bold.otf) | old font $(curl -s -o /dev/null -w '%{http_code}' $W/fonts/Montserrat-ExtraBold.ttf)"
rm -rf web_public/s36
rm -rf $B
echo "backup of the previous files: $K"
echo DEPLOY_BOT36 DONE $TS
