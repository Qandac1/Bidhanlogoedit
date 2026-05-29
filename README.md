# Bidhaan Logo-Edit Bot

Replaces the manual Filmora workflow. Send the bot a video; it returns the same
video branded automatically:

- **StreamNxt** logo top-right, **Bidhaan TV** logo top-left
- Scrolling caption (name + number) moving bottom → up
- Broadcaster **ad / phone-number banners auto-covered** with the red/black bar,
  even when they move position between scenes

All effects are burned in a **single ffmpeg pass** (decode/encode once).

## How it works

1. **Detect** (`detect.py`) — samples the video at 1 fps, finds saturated-red
   banner blocks (TRT/Fanproj/WhatsApp number bars), optionally confirms with
   OCR digits, and merges per-frame hits into a *cover timeline* of
   `(start, end, x, y, w, h)` intervals. Positions are normalised so they track
   the banner as it moves.
2. **Render** (`branding.py`) — one `filter_complex`: scales the cover bar to
   each interval and overlays it with a time gate, then the two logos, then the
   scrolling caption.
3. **Bot** (`bot.py`) — pyrofork bot, owner-gated, one render at a time with
   live progress.

## Commands

| Command | Effect |
|---|---|
| `/start`, `/help` | quick guide |
| `/settings` | show current settings |
| `/text <caption>` | set the scrolling caption |
| `/cover auto`\|`off` | toggle auto ad-covering |
| `/quality source`\|`720` | output size (720 renders faster) |

Then just **send a video**.

## Assets (`assets/`)

| File | What |
|---|---|
| `streamnxt.png` | top-right logo (needs transparency) |
| `bidhaan.png` | top-left logo (needs transparency) |
| `coverbar.png` | the red/black cover bar |

## Deploy

```bash
cp .env.example .env      # fill API_ID / API_HASH / BOT_TOKEN / OWNER_ID
docker compose up -d --build
docker logs -f bidhaan-logoedit
```

## Notes

- Handles files up to ~2 GB (direct MTProto, no Bot-API server needed).
- Encoding is CPU `libx264`. A full 2h+ episode is an overnight-batch job on a
  CPU box; use `/quality 720` or a faster preset to speed it up.
- Detection targets red banners well; tune `DETECT_FPS` / HSV thresholds in
  `detect.py` for other banner styles.
