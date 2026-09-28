# Bidhaan Logo-Edit — Changelog

## 2026-09-28 (evening) — bot9 LIVE (6f5a10a)

- **patch_bot_brandrepair:** the self-repair hands the job's brand JSON to auto_repair (`--brand`),
  so a re-made shot keeps the channel logo; the cut summary gets the delivered film
  (`make_cut_summary(..., film=res.path)` → `cut_list --film`) for the end-credits accounting.
  Additive: unbranded jobs and old calls unchanged. 7 suites pass (brandrepair, restorefix,
  autorepair, contract, cutsummary, samecontent, speedretry); container == tested bot9.

## 2026-09-28

### Added (John: "the bot must fix its own problems, not only report them")
- **Dialogue gate + self-repair after the audio step:**
  - If the dub's opening voice that the HD's timeline has was cut (Achcham: 16.4 s inside the
    channel-logo shot), the bot puts it back: the HD's opening picture with the dub's sound,
    aligned by waveform.
  - The report shows the share of the dub's voice in the film, and every stretch that was cut
    on purpose (adverts, channel intro).
- **Picture check in the report:** wrong clips, repeats and spots (`frame_audit.py`).

### Fixed
- **Pushpa 2 shipped "dub only", with no end credits.** The work-dir hash picked the engine's
  `.det.` scratch copy, so the audio step looked in an empty directory. `.det.` files are
  now skipped.
- The delivered file is always `.mp4`. Before, the source's `.mkv` name leaked into it.
- `tools/bot_idle.sh`: a strict idle check before any restart. Any failure to look counts as
  BUSY.

## 2026-09-27

### Changed (John: no premium account now; quality first; real thumbnails)
- **No more squeezing to 2 GB.** When MEGA is set up, a film over Telegram's limit keeps its
  full bitrate and is delivered as a MEGA link (Pushpa 2 had been cut from 2000k to 1039k to
  fit 2.07 GB; at 2000k it is ~3.6 GiB). Without MEGA the old fit-to-Telegram behaviour stays.
  The "premium expired" notice now says the film goes by MEGA at full quality.
- **Real thumbnail.** Deliveries showed Telegram's black first frame. The bot now picks the
  most detailed, well-exposed frame from 15-75 % of the film (320 px JPEG) for the Telegram
  video, the premium upload and the MEGA-link message (sent as a photo with the link).

### Fixed
- **A cancelled dub job left its proxy encoder running**; the next job's encoder wrote the same
  file and the engine read it as 0 frames. `_make_proxy` now kills the encoder and deletes the
  half-written proxy on cancel.
- **"dub only" audio without a reason.** When switch_audio produces no file, its output is kept
  in `out/<title>_switch_audio.log` and the caption says why.
- Tests: `tools/test_bot_patch.py` (run inside the container, against /app) -- all pass.

## 2026-09-12

### Added
- **Branded dialogue-layer — you no longer choose between the two modes.**
  Dialogue-layer used to be a trade: it kept the HD master's own music/SFX/
  action audio, but carried no logos and no caption. It now burns the branding
  in as well, so picking a mode is about AUDIO and TIMELINE only, never about
  giving up the branding.
  - The branding rides inside the video re-encode the dialogue-layer mux was
    already doing, so it costs **no second encode** and no extra generation
    loss.
  - Reuses dubsync2's OWN brand module (`dubsync2.brand.segment_filters`), the
    same code conform renders with, so logos and caption land identically in
    both modes instead of drifting apart as two implementations.
  - Logo size/margins come from the HD's REAL pixel size (new `probe_wh`), not
    the panel's ow/oh. This mux never scales, and real masters are not
    1920x1080 — Tammal is 1920x808, The Comeback 1920x720.
  - Branding can never cost a render: if the brand module or its config fails
    to load, the engine logs UNBRANDED and renders anyway. A movie without
    logos is usable; a crashed 70-minute render is not.
  - Verified on a real 120s Tammal window (1920x808, 2 logos + caption):
    PSNR branded vs unbranded is 20.60 dB in the bidhaan corner and 27.99 dB in
    the streamnxt corner (both heavily changed) against 37.54 dB in the centre
    (unchanged bar re-encode noise). Duration identical to 6 decimal places
    (120.958333 = 120.958333), so INV-3 holds. The unbranded path renders
    exactly as before.
  (backups: dialogue_layer.py.pre-brand-*, dubsync_job.py.pre-brand-*)

### Fixed
- **The panel no longer lies about dialogue-layer.** The mode button and its
  confirmation toast both read "Dialogue-layer (HD audio, no branding)", which
  stopped being true the moment branding was added. Both now read
  "Dialogue-layer (HD audio + branding)". (backup: bot.py.pre-dlgbrand)

## 2026-09-11

### Changed
- **MEGA upload now shows a live progress bar.** rclone was run with -P, whose
  in-place (carriage-return) progress display is invisible to a line-based
  reader, so the bar sat frozen at "2.00 GB — uploading to MEGA…". Switched to
  --stats 1s --stats-one-line --stats-log-level NOTICE (newline-terminated
  lines) so the percentage updates live. (backup: delivery.py.pre-megaprogress)
- **Delivered files keep the ORIGINAL movie name.** The caption used to show
  only "✅ Branded — N banner(s) • size", which Telegram displays as the video
  name — hiding the real title. Now the caption leads with the original file
  name, with the status on a small second line, and the real filename is
  stamped onto the uploaded video (file_name) so saves/forwards keep it. Applies
  to render and /trim. (backup: bot.py.pre-keepname)
### Fixed
- **Render crash "maximum recursion depth exceeded"**: `_user_logo()` called
  itself instead of returning the default Bidhaan logo when no custom logo was
  set. Hit every render without a custom logo. (backup: bot.py.pre-logorecursion)

### Added
- **Download-once source cache** (bot.py): a forwarded/sent file is downloaded
  only ONCE, keyed by Telegram file_unique_id. Cancel a render and re-forward
  the same movie -> reused instantly, no re-download. Cached copy is a HARD LINK
  to the work-dir source (zero extra disk, survives the post-render wipe).
  Auto-capped: SRC_CACHE_MAX_GB=25, SRC_CACHE_MAX_AGE_H=24 (LRU eviction);
  orphaned work dirs older than WORK_STALE_H=6 are swept. (backup: bot.py.pre-srccache)
- **Video trimmer** (new trim.py + bot.py): fast stream-copy, NO re-encode,
  keyframe-accurate, works on all videos.
  - Standalone `/trim` command: reply /trim to a video (button panel) or type
    `/trim first 60s` | `last 30s` | `keep 1:00 5:00` | `cut 2:00 2:30`.
  - "Trim" button in the render panel: cut first/last/keep-range/cut-section
    applied BEFORE render, so covers/caption/logo stay aligned.
  (backups: bot.py.pre-trim, bot.py.pre-trim2)
