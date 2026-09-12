# Bidhaan Logo-Edit — Changelog

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
