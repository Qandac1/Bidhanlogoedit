#!/bin/sh
# Is the dub bot idle? (safe to restart / deploy). Prints BOT IDLE and exits 0 only when the
# container runs nothing but bot.py AND the queue worker has no running film. Any failure to
# look (docker error, unreadable queue) is BUSY -- never idle by default (2026-09-28: a
# `docker top -eo args` error once produced an empty list that read as "idle").
C=${1:-bidhaan-logoedit}
Q=/var/lib/docker/volumes/bidhanlogoedit_bot_data/_data/dub_queue.json
out=$(docker top "$C" 2>&1) || { echo "BOT BUSY (docker top failed: $out)"; exit 1; }
n=$(printf '%s\n' "$out" | tail -n +2 | wc -l)
others=$(printf '%s\n' "$out" | tail -n +2 | grep -v -c "python -u bot.py")
[ "$n" -ge 1 ] || { echo "BOT BUSY (no processes listed -- container down?)"; exit 1; }
[ "$others" -eq 0 ] || { echo "BOT BUSY ($others process(es) besides bot.py)"; printf '%s\n' "$out" | tail -n +2 | grep -v "python -u bot.py" | cut -c1-160; exit 1; }
run=$(python3 -c "import json,sys; q=json.load(open(sys.argv[1])); print(sum(1 for e in q if e.get('state') in ('running','waiting')))" "$Q" 2>&1) || { echo "BOT BUSY (queue unreadable: $run)"; exit 1; }
[ "$run" = "0" ] || { echo "BOT BUSY ($run film(s) running/waiting in the queue)"; exit 1; }
echo "BOT IDLE"
