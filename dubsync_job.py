"""dubsync job runner for the Telegram bot.

Bridges @BidhaanLogoEdit_bot to the dubsync2 engine. The bot already owns
downloading, the progress bar, MEGA/premium delivery, presets and auth; this
module only runs the conform pipeline and reports where it is, so none of that
existing machinery is duplicated or disturbed.

Design notes:

  * The bot's branding settings are passed straight through to the render, so
    logos and the caption are burned in during the conform's own encode. One
    encode, not two.

  * Cover-banner detection is never used here. It exists to hide broadcaster
    banners baked into a StreamNxt-style source; a clean HD master has none.

  * Progress is parsed from the engine's stdout rather than guessed, and
    weighted by how long each stage actually takes, so the bar moves at a
    believable rate instead of sitting at 40% for twenty minutes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

DUBSYNC = "/opt/dubsync2/.venv/bin/dubsync2"
RAW_DIR = Path("/opt/dubsync2/raw")
OUT_DIR = Path("/opt/dubsync2/out")

# A hard backstop, not a normal-case limit. A real stage can legitimately go
# quiet for many minutes (stage3 in particular), so this only trips on total
# silence — no output at all — for this long, which is what "hung" actually
# looks like. The Demon City proxy sat silent for 4.5+ hours before this
# existed; nothing should ever again be allowed to do that unnoticed.
STALL_TIMEOUT_S = 1800

# Stage weights measured on real runs (2h09 episode, 8 cores). They only need
# to be roughly right — their job is to keep the bar honest, not exact.
STAGES: list[tuple[str, str, float]] = [
    ("analyze",   "🔍 Analysing shots",      0.30),
    ("stage1",    "✂️ Finding editorial cuts", 0.02),
    ("calibrate", "🎯 Calibrating to this master", 0.06),
    ("stage2",    "✅ Verifying every shot",  0.22),
    ("stage3",    "🩹 Healing mismatches",    0.08),
    ("stage3-5",  "🔎 Global search",         0.04),
    ("plan",      "🧩 Building the cut",      0.02),
    ("repair",    "🧹 Removing repeats",      0.08),   # expands into cycles
    ("render",    "🎬 Rendering",             0.18),
]

# How hard to chase duplication before accepting what is left.
REPAIR_PASSES = 4        # convergence measured at 4 on a 2h27m feature
REPAIR_TARGET_S = 5.0    # clean enough — stop
REPAIR_MIN_GAIN_S = 1.0  # a pass that buys less than this is not worth another



@dataclass
class DubResult:
    ok: bool
    path: Optional[Path]
    message: str
    stats: dict


def _slug(name: str) -> str:
    """Turn a filename into the title used for raw/{title}_hd_ORIG.* and,
    transitively, the whole per-title cache.

    2026-08-14 incident: two DIFFERENT movies uploaded from the same channel
    ("[ @BT_MOVIES_HD ][ @FILMSCLUB04 ] <title>...") both slugified to the
    identical "btmovieshdfilmsclub04aak" -- the bracketed channel tag alone
    ate the whole 24-char budget, leaving only 3 characters of the real
    title to tell them apart. Since prepare_inputs() unconditionally
    overwrites raw/{title}_hd_ORIG.* on every submission, the second
    movie's raw source silently destroyed the first's, and its cached
    shots/embeddings got reused against the wrong video entirely.

    Fix: strip bracketed uploader/channel tags before slugifying (so the
    real title drives the slug instead of being crowded out), then append a
    short hash of the FULL original name as a disambiguator. Two different
    movies now can't collide even if their titles also happen to share a
    long common prefix; the identical filename resubmitted (a legitimate
    retry) still hashes to the identical slug and correctly reuses cached
    work instead of redownloading and reprocessing from scratch.
    """
    stem = Path(name).stem
    detagged = re.sub(r"\[[^\]]*\]", "", stem)
    core = re.sub(r"[^A-Za-z0-9]+", "", detagged).lower()[:18]
    h = hashlib.sha1(name.encode("utf-8", "replace")).hexdigest()[:6]
    return f"{core or 'job'}_{h}"


SLOW_CODECS = {"hevc", "vp9", "av1"}


async def _needs_proxy(src: Path) -> tuple[bool, str]:
    """True when decoding this file repeatedly would dominate the job.

    HEVC/VP9/AV1, and any 10-bit pixel format, are far slower to seek and decode
    on CPU than H.264 8-bit. Demon City (HEVC Main 10, 1080p) spent 8+ hours in
    a stage that takes 3 minutes on an H.264 master.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,pix_fmt",
        "-of", "default=noprint_wrappers=1:nokey=1", str(src),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    parts = [x.strip() for x in out.decode("utf-8", "replace").split() if x.strip()]
    codec = parts[0] if parts else ""
    pix = parts[1] if len(parts) > 1 else ""
    if codec in SLOW_CODECS:
        return True, f"{codec}"
    if "10le" in pix or "10be" in pix or "12le" in pix:
        return True, f"{codec} {pix}"
    return False, codec


async def _make_proxy(src: Path, dst: Path, height: int,
                      on_line=None, on_progress=None) -> bool:
    """One sequential transcode to H.264 8-bit. Returns True on success.

    Spawned with asyncio's own subprocess machinery, like every other stage
    in this file — never the blocking `subprocess` module. Mixing the two in
    one asyncio process is a known way to end up with a permanently zombied
    ffmpeg: the blocking call's own wait() can lose the race for the child's
    exit status and simply never come back, silently freezing the job for
    hours (this is exactly what happened to the Demon City run).
    """
    # Resolve the target height in Python rather than with an ffmpeg min()
    # expression — the comma inside it has to be escaped for the filtergraph
    # parser, which is easy to get subtly wrong. Duration is fetched here too
    # so progress below can be reported as a real percentage.
    r0 = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=height", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(src),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out0, _ = await r0.communicate()
    vals = [x.strip() for x in out0.decode("utf-8", "replace").split() if x.strip()]
    try:
        src_h = int(float(vals[0])) if vals else 0
    except (ValueError, IndexError):
        src_h = 0
    try:
        dur = float(vals[1]) if len(vals) > 1 else 0.0
    except (ValueError, IndexError):
        dur = 0.0
    tgt = min(height, src_h) if src_h else height
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
        "-i", str(src),
        "-map", "0:v:0", "-map", "0:a?",
        "-vf", f"scale=-2:{tgt}:flags=bicubic,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-movflags", "+faststart",
        str(dst),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)

    # ffmpeg's -stats writes "time=HH:MM:SS.xx" updates with \r, not \n, so
    # this reads raw chunks rather than lines and regexes the rolling buffer
    # — line-based iteration would just sit there buffering until EOF.
    pat_time = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
    buf = ""
    last_pct = -1.0
    stalled = False
    assert proc.stdout is not None
    while True:
        try:
            chunk = await asyncio.wait_for(proc.stdout.read(4096),
                                           timeout=STALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            stalled = True
            break
        if not chunk:
            break
        buf += chunk.decode("utf-8", "replace")
        buf = buf[-4000:]
        if on_progress and dur > 0:
            matches = pat_time.findall(buf)
            if matches:
                h, mnt, s = matches[-1]
                cur = int(h) * 3600 + int(mnt) * 60 + float(s)
                pct = min(1.0, cur / dur)
                if pct - last_pct >= 0.01:
                    last_pct = pct
                    res = on_progress(pct)
                    if asyncio.iscoroutine(res):
                        await res
    if stalled:
        try:
            proc.kill()
        except Exception:
            pass
        await proc.wait()
        if on_line:
            on_line(f"proxy stalled — no output for {STALL_TIMEOUT_S // 60} min, "
                    "killed; using the original")
        dst.unlink(missing_ok=True)
        return False
    rc = await proc.wait()
    if rc != 0 or not dst.exists() or dst.stat().st_size == 0:
        if on_line:
            tail = buf.strip().replace("\r", " ").splitlines()
            snippet = tail[-1][-300:] if tail else ""
            on_line(f"proxy failed (exit {rc}); using the original" +
                    (f" — {snippet}" if snippet else ""))
        dst.unlink(missing_ok=True)
        return False
    return True


async def prepare_inputs(hd_src: Path, dub_src: Path, title: str,
                         out_height: int = 1080, on_line=None,
                         on_progress=None) -> tuple[Path, Path]:
    """Place the two files where the engine expects them.

    Hardlinked when possible so a 2 GB pair is not copied twice on a disk that
    has been near-full before.

    A master in a slow codec (HEVC/VP9/AV1 or any 10-bit format) is transcoded
    once to H.264 8-bit first — see `_needs_proxy`. Every later stage seeks and
    decodes this file many times over, so paying once here is far cheaper than
    paying per shot, per keyframe and per rendered segment.

    `on_progress(label, pct_0_100)` mirrors `run_dubsync`'s callback so the
    caller can drive the same panel through the proxy build instead of it
    sitting silent — a multi-hour transcode with no feedback reads as "stuck"
    even when it is working fine.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    hd = RAW_DIR / f"{title}_hd_ORIG{hd_src.suffix}"
    dub = RAW_DIR / f"{title}_dub_ORIG{dub_src.suffix}"
    for src, dst in ((hd_src, hd), (dub_src, dub)):
        # SAME-FILE GUARD. This used to be an unconditional dst.unlink() followed
        # by os.link(src, dst). When src and dst are the SAME file -- a re-run on
        # inputs already sitting in raw/, or two submissions resolving to the
        # same title -- the unlink DELETES THE ONLY COPY and the link then fails
        # with FileNotFoundError, leaving nothing behind.
        #
        # This is not hypothetical: the 2026-08-14 incident (see _slug's note)
        # lost a movie's raw source exactly this way when two different films
        # slugified identically. The slug collision was fixed; the destructive
        # unlink that actually did the damage was not. Nothing to do when the
        # source is already in place.
        try:
            if dst.exists() and src.exists() and os.path.samefile(src, dst):
                continue
        except OSError:
            pass
        if dst.exists():
            dst.unlink()
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)

    for who, path in (("HD", hd), ("dub", dub)):
        slow, what = await _needs_proxy(path)
        if not slow:
            continue
        prox = RAW_DIR / f"{title}_{'hd' if who == 'HD' else 'dub'}_PROXY.mp4"
        if on_line:
            on_line(f"{who} is {what} — building a fast proxy once")

        async def _report(pct: float, who=who):
            res = on_progress(f"🧬 Building {who} proxy", pct * 100.0)
            if asyncio.iscoroutine(res):
                await res

        if await _make_proxy(path, prox, out_height, on_line,
                             _report if on_progress else None):
            if who == "HD":
                hd = prox
            else:
                dub = prox
    return hd, dub


def identify_pair(a: Path, b: Path) -> tuple[Path, Path]:
    """Decide which file is the HD master and which is the dub.

    Resolution first, duration as the tie-break: the dub is the lower-res one,
    and it is also shorter because the dub source cuts scenes. File size is NOT
    used — it misleads. On the Turkish episode the dub was the LARGER file
    (1079 MB at 480p vs 972 MB at 720p) purely because of bitrate.
    """
    def probe(p: Path) -> tuple[int, float]:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", str(p)],
            capture_output=True, text=True)
        vals = [x for x in r.stdout.split() if x]
        w = int(float(vals[0])) if vals else 0
        d = float(vals[1]) if len(vals) > 1 else 0.0
        return w, d

    wa, da = probe(a)
    wb, db = probe(b)
    if wa != wb:
        return (a, b) if wa > wb else (b, a)
    return (a, b) if da >= db else (b, a)


async def run_dubsync(
    hd: Path, dub: Path, title: str,
    brand_cfg: dict | None,
    width: int, height: int, crf: int,
    on_progress: Callable[[str, float], "asyncio.Future | None"],
    bitrate_k: int = 0,
    # 20.0s was arbitrary and too strict for a feature. John watched the
    # flagged spots on Cocktail 2 (41:47, 52:55, 63:05) and confirmed they are
    # the FILM ITSELF - songs and montages legitimately replay footage, which
    # is exactly the pattern the detector calls duplication. The dedupe stage
    # had already tried 4 repair passes and correctly refused to touch them,
    # because repairing them would break lip sync. Holding a 142-min release
    # over 47.7s of the movie's own repeated shots is a false positive, not a
    # safety net. Raised to 90s; genuine accidental duplication of the kind
    # this gate exists to catch (a 300s promo replayed onto used HD) is far
    # larger than that and still blocks.
    max_accidental: float = 90.0,
    register: Optional[Callable[[object], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    mode: str = "conform",
) -> DubResult:
    """Run the pipeline, reporting (stage label, overall 0..100) as it goes."""
    out_name = f"{title}_final.mp4"
    brand_path = None
    if brand_cfg:
        brand_path = Path(f"/tmp/brand_{title}.json")
        brand_path.write_text(json.dumps(brand_cfg))

    base = [DUBSYNC]
    render = [*base, "preview", "--title", title,
              "--width", str(width), "--height", str(height),
              # STANDING RULE (John, repeated many times): THE DUB IS THE
              # EDITORIAL REFERENCE. The output starts EXACTLY where the dub's
              # film starts and adds back NOTHING the dub cut. The dub removed
              # the head material (channel bumpers AND the HD master's own
              # distributor slate / censor card / studio logos), so none of it
              # goes back in. A prior session flipped this to keep the HD intro
              # ("--hd-intro" default on), which prepended ~3 min of the HD
              # head -- censor cards, studio logos, with Hindi audio -- onto
              # every render. That is exactly the long/Hindi intro John keeps
              # reporting. --no-hd-intro restores the rule: start at the film.
              "--no-hd-intro",
              "--output-name", out_name]
    # A target bitrate keeps the delivered size close to what the panel quoted.
    # CRF with -preset ultrafast does not: it pins quality and lets the bitrate
    # run, which is how a 1.6 GB estimate came back as a 5.35 GB file.
    if bitrate_k:
        render += ["--bitrate", f"{int(bitrate_k)}k"]
    else:
        render += ["--crf", str(crf)]
    if brand_path:
        render += ["--brand-config", str(brand_path)]

    cmds = {
        "analyze":   [*base, "analyze", "--title", title],
        "stage1":    [*base, "stage1", "--title", title],
        "calibrate": [*base, "stage2-calibrate", "--title", title],
        "stage2":    [*base, "stage2", "--title", title],
        "stage3":    [*base, "stage3", "--title", title],
        "stage3-5":  [*base, "stage3-5", "--title", title],
        # Same render invocation twice: once to lay out the cut and write
        # provenance.json (no encoding), then -- after dedupe has used that
        # provenance to verify its repairs -- once for real. The repairs are
        # read back from dedupe_fixes.json during the second call.
        "plan":      [*render, "--plan-only"],
        "dedupe":    [*base, "dedupe", "--title", title],
        "render":    render,
    }

    stats: dict = {}
    done_weight = 0.0
    total_weight = sum(w for _, _, w in STAGES)   # "repair" counted once

    # progress markers inside a stage's own output
    pat_frac = re.compile(r"\[\s*(\d+)\s*/\s*(\d+)\s*\]")
    pat_pass = re.compile(r"PASS:\s*(\d+)\s*/\s*(\d+)")
    pat_total = re.compile(r"Total pass after Stage 3(?:\.5)?:\s*(\d+)/(\d+)\s*\(([\d.]+)%\)")
    pat_dup = re.compile(r"accidental:\s*([\d.]+)s")
    pat_intro = re.compile(r"Dub intro removed:\s*(\d+) shots")
    pat_promo = re.compile(r"trailing promo")
    # The render's own planned duration, so the caller can catch a delivered
    # file whose real length silently drifted from what was actually cut —
    # the cheapest possible smoke test for "did this ship intact."
    pat_expected_dur = re.compile(r"Expected duration:\s*([\d.]+)s")

    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    # Expand "repair" into alternating dedupe / re-plan cycles. Each cycle is
    # weighted evenly so the bar keeps moving through them; unused cycles hand
    # their weight back when the loop exits early.
    queue: list[tuple[str, str, float]] = []
    # "auto" takes the conform queue because STAGES already begins with analyze;
    # the early exit below turns it into a dlg job the moment measurement says so.
    # No queue surgery, and the dlg/conform paths stay byte-identical.
    if mode == "dlg":
        # dialogue-layer needs ONLY the anchor map. edl.json has a single
        # writer -- save_edl() inside `analyze` -- and no later stage
        # rewrites it, so stage1..stage3-5/plan/dedupe/render add nothing
        # dialogue_layer can read. Running just `analyze` is both correct
        # and far cheaper than the full conform.
        queue.append(("analyze", "\U0001F50D Analysing shots", 1.0))
    else:
      for k, l, w in STAGES:
        if k != "repair":
            queue.append((k, l, w))
            continue
        each = w / (REPAIR_PASSES * 2)
        for i in range(REPAIR_PASSES):
            queue.append(("dedupe", f"{l} ({i + 1}/{REPAIR_PASSES})", each))
            queue.append(("plan", f"🧩 Rebuilding the cut ({i + 1})", each))

    prev_acc: float | None = None

    i = -1
    while True:
        i += 1
        if i >= len(queue):
            break
        key, label, weight = queue[i]
        if _cancelled():
            return DubResult(False, None, "cancelled", stats)
        cmd = cmds[key]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        # Hand the process to the caller so /cancel and the Cancel button can
        # actually kill it — without this the job runs on after "cancelled".
        if register:
            register(proc)
        assert proc.stdout is not None
        # Announce the stage immediately. Some stages (stage3 in particular)
        # run for minutes before printing anything parseable, so the panel
        # kept showing the PREVIOUS stage's label the whole time — which is
        # exactly what reads as a frozen job even though the process is busy.
        res = on_progress(label, done_weight / total_weight * 100.0)
        if asyncio.iscoroutine(res):
            await res
        inner = 0.0
        last_emit = 0.0
        tail: list[str] = []
        stalled = False
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(),
                                             timeout=STALL_TIMEOUT_S)
            except asyncio.TimeoutError:
                stalled = True
                break
            if not raw:
                break
            if _cancelled():
                try:
                    proc.kill()
                except Exception:
                    pass
                return DubResult(False, None, "cancelled", stats)
            line = raw.decode("utf-8", "replace")
            stripped = line.strip()
            if stripped:
                tail.append(stripped)
                if len(tail) > 12:
                    tail.pop(0)
            m = pat_frac.search(line)
            if m:
                cur, tot = int(m.group(1)), int(m.group(2))
                if tot:
                    inner = min(1.0, cur / tot)
            if (m := pat_pass.search(line)):
                stats["verified"] = f"{m.group(1)}/{m.group(2)}"
            if (m := pat_total.search(line)):
                stats["match_rate"] = f"{m.group(3)}%"
            if (m := pat_dup.search(line)):
                stats["duplication"] = f"{m.group(1)}s"
            if (m := pat_intro.search(line)):
                stats["intro_shots"] = m.group(1)
            if pat_promo.search(line):
                stats["promo_removed"] = "yes"
            if (m := pat_expected_dur.search(line)):
                stats["expected_duration_s"] = float(m.group(1))

            pct = (done_weight + weight * inner) / total_weight * 100.0
            if pct - last_emit >= 1.0:
                last_emit = pct
                res = on_progress(label, pct)
                if asyncio.iscoroutine(res):
                    await res
        if stalled:
            try:
                proc.kill()
            except Exception:
                pass
            await proc.wait()
            if register:
                register(None)
            return DubResult(
                False, None,
                f"{label} produced no output for {STALL_TIMEOUT_S // 60} min "
                "— killed as hung", stats)
        rc = await proc.wait()
        if register:
            register(None)
        if _cancelled():
            return DubResult(False, None, "cancelled", stats)
        if rc != 0:
            # Previously this discarded the engine's own output entirely, so
            # every failure showed up in Telegram as a bare "(exit 1)" with
            # no way to tell what actually went wrong without SSHing in.
            detail = " › ".join(tail[-4:])
            msg = f"{label} failed (exit {rc})"
            if detail:
                msg += f"\n{detail[:500]}"
            return DubResult(False, None, msg, stats)
        done_weight += weight
        res = on_progress(label, done_weight / total_weight * 100.0)
        if asyncio.iscoroutine(res):
            await res

        # A re-plan just told us how much duplication survives. Stop cycling
        # once the cut is clean enough, or once a pass stops paying for itself
        # (the residue is repairs that failed verification and were rolled
        # back to protect lip sync — more passes will not move them).
        if key == "plan" and "duplication" in stats:
            try:
                acc = float(str(stats["duplication"]).rstrip("s"))
            except ValueError:
                acc = None
            if acc is not None:
                gain = None if prev_acc is None else prev_acc - acc
                prev_acc = acc
                if acc <= REPAIR_TARGET_S or (gain is not None
                                              and gain < REPAIR_MIN_GAIN_S):
                    # Hand the skipped cycles their weight back so the bar
                    # still reaches 100% rather than jumping.
                    for j in range(i + 1, len(queue)):
                        if queue[j][0] not in ("dedupe", "plan"):
                            break
                        done_weight += queue[j][2]
                        i = j

        # --- AUTO MODE: decide as soon as the evidence exists ----------------
        # analyze has just written edl.json, so this is the earliest honest point
        # to choose. Picking dlg here skips every remaining conform stage, which
        # is also why auto costs nothing extra on a film that wants dlg.
        if mode == "auto" and key == "analyze":
            picked, why = _pick_mode(hd, dub)
            stats["auto_mode"] = picked
            stats["auto_why"] = why
            if picked == "dlg":
                mode = "dlg"
                break

    if mode == "dlg":
        return await _render_dialogue_layer(hd, dub, title, on_progress,
                                            register, _cancelled, stats,
                                            brand_path)

    out = OUT_DIR / out_name
    if not out.exists():
        return DubResult(False, None, "render produced no file", stats)

    # Release gate. A failure here is not a crash — the movie exists, it just
    # could not be proven clean, and the caller should say so rather than
    # silently presenting it as finished.
    gate = await asyncio.create_subprocess_exec(
        *base, "integrity", "--title", title, "--file", str(out),
        "--scan-step", "5", "--max-accidental", str(max_accidental),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    gate_out = (await gate.communicate())[0].decode("utf-8", "replace")
    await gate.wait()
    released = "RELEASE APPROVED" in gate_out
    stats["gate"] = "passed" if released else "held"
    for ln in gate_out.splitlines():
        s = ln.strip()
        if s.startswith("✗"):
            stats.setdefault("gate_notes", []).append(s[1:].strip())
        elif s.startswith("🔁"):
            # "where to check" lines from the integrity checker — surfaced to
            # John so he can jump straight to each suspected repeat.
            stats.setdefault("dup_regions", []).append(s)

    return DubResult(True, out,
                     "released" if released else "delivered for review — integrity gate FAILED (NOT final)",
                     stats)


DLG_SCRIPT = "/opt/dubsync2/dialogue_layer.py"
DLG_PY = "/opt/dubsync2/.venv/bin/python"


def _work_dir_for(hd: Path, dub: Path) -> Path:
    """The engine's own work dir for this pair.

    Mirrors dubsync2 paths.project_hash() and dialogue_layer._proj_hash():
    sha256 of both file SIZES plus the sha256 of each file's first 100 000
    bytes, truncated to 12 chars. Resolved by identity, never by name or
    order -- picking by order is what produced the wrong-movie render.
    """
    import hashlib

    def head_sha(f: Path) -> str:
        with open(f, "rb") as fh:
            return hashlib.sha256(fh.read(100000)).hexdigest()

    parts = [str(hd.stat().st_size), str(dub.stat().st_size),
             head_sha(hd), head_sha(dub)]
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
    return Path("/opt/dubsync2/work") / h


def _pick_mode(hd: Path, dub: Path) -> tuple[str, str]:
    """Choose conform vs dialogue-layer by MEASURING this pair. Returns (mode, why).

    Must run AFTER `analyze`: the evidence is edl.json, which analyze writes.

    dialogue_layer renders the HD master end to end -- its --full loop walks
    H = 0 -> hd_total with no skip logic -- so footage the Somali release CUT is put
    back by a dlg render. conform follows the dub's editorial timeline and excludes it
    by construction. dub_cut_check.py measures interior HD that no dub time maps into,
    which is the footprint a removed scene leaves behind (FM-042).

    Falls back to dlg on any failure: that is the mode every approved film used, so an
    unmeasurable pair behaves exactly as it did before this function existed.
    """
    work = _work_dir_for(hd, dub)
    try:
        r = subprocess.run(
            [DLG_PY, "/opt/dubsync2/dub_cut_check.py", "--caption", str(work)],
            capture_output=True, text=True, timeout=120)
        line = (r.stdout or "").strip().splitlines()[0]
        picked, worst, total, n = line.split("|")
    except Exception as exc:
        return "dlg", "coverage unmeasurable (%s); using dialogue-layer" % type(exc).__name__
    if picked == "conform":
        return "conform", (
            "the dub is a CUT version: %ss of HD across %s stretches (worst %ss) is "
            "footage it never covers, so the HD timeline would put it back" % (total, n, worst))
    if picked == "ask":
        return "conform", (
            "%ss of HD across %s stretches (worst %ss) is uncovered -- borderline, so "
            "the dub's own timeline is the safer choice" % (total, n, worst))
    return "dlg", "the dub follows its HD master (no uncovered interior footage)"


def _probe(path, sel, entries):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel,
                        "-show_entries", entries, "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return r.stdout.strip()


def _write_render_report(title, hd, dub, work, out, chunk_rows, anomalies,
                         vdur, adur, placed, chunks, branding="unknown"):
    """Human-readable evidence file for one dialogue-layer render.

    Deliberately records the RAW per-chunk numbers, not just a summary: the
    13.27s drift that caused the 'whole movie mismatch' was invisible in any
    summary and obvious in the per-chunk durations.
    """
    import datetime, glob, json as _json

    rp = OUT_DIR / f"{title}_report.md"
    L = []
    A = L.append
    A("# Render report — %s" % title)
    A("")
    A("- generated: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    A("- mode: **dialogue-layer** (HD master + Somali dialogue overlay)")
    A("- output: `%s`" % out)
    try:
        A("- output size: %.2f GB" % (out.stat().st_size / 1024 ** 3))
    except OSError:
        pass
    A("")
    A("## Inputs")
    for tag, f in (("HD ", hd), ("DUB", dub)):
        try:
            sz = "%.2f GB" % (Path(f).stat().st_size / 1024 ** 3)
        except OSError:
            sz = "?"
        A("- %s `%s` — %s, %ss, audio %s" % (
            tag, Path(f).name, sz,
            _probe(f, "v:0", "format=duration") or "?",
            _probe(f, "a:0", "stream=sample_rate,channels").replace("\n", " ") or "?"))
    A("")
    A("## Anchor map (edl.json — written by `analyze`, single writer)")
    try:
        edl = _json.load(open(Path(work) / "edl.json"))["edl"]
        body = [e for e in edl if not e["is_intro_cluster"] and e["hd_idx"] is not None]
        ds = [e["dub_start_s"] for e in body]
        A("- work dir: `%s`" % work)
        A("- total shots: %d · intro cluster: %d · matched anchors: %d · unmatched: %d"
          % (len(edl), sum(1 for e in edl if e.get("is_intro_cluster")), len(body),
             sum(1 for e in edl if not e.get("is_intro_cluster") and e.get("hd_idx") is None)))
        if ds:
            A("- dub range covered: %.0fs .. %.0fs" % (min(ds), max(ds)))
    except Exception as e:
        A("- could not read edl.json: %s" % e)
    A("")
    A("## Per-chunk detail")
    A("")
    A("| chunk | HD range | segments | placed | mixed WAV |")
    A("|---|---|---|---|---|")
    tmpdirs = sorted(glob.glob("/opt/dubsync2/_scratch/dlg_*"), key=os.path.getmtime)
    tmp = tmpdirs[-1] if tmpdirs else None
    total_audio = 0.0
    for r in chunk_rows:
        wav = os.path.join(tmp, "mix_%d.wav" % r["idx"]) if tmp else ""
        d = _probe(wav, "a:0", "format=duration") if wav and os.path.exists(wav) else ""
        if d:
            try:
                total_audio += float(d)
            except ValueError:
                pass
        A("| %d | %.0f–%.0fs | %d | %d | %s |"
          % (r["idx"], r["hd_start"], r["hd_end"], r["segs"], r["placed"], d or "(cleaned up)"))
    A("")
    A("- chunks: **%d** · dialogue segments placed: **%d**" % (chunks, placed))
    miss = sum(r["segs"] - r["placed"] for r in chunk_rows)
    A("- segments found but not placed: %d%s" % (
        miss, " (normal at window edges)" if miss else ""))
    measured = sum(1 for r in chunk_rows
                   if tmp and os.path.exists(os.path.join(tmp, "mix_%d.wav" % r["idx"])))
    if chunk_rows and measured == len(chunk_rows) and total_audio:
        hd_total = 0.0
        try:
            hd_total = float(_probe(hd, "", "format=duration") or 0)
        except ValueError:
            pass
        if hd_total:
            A("- summed chunk audio: %.3fs vs HD %.3fs → drift **%+.3fs**"
              % (total_audio, hd_total, total_audio - hd_total))
        else:
            A("- summed chunk audio: %.3fs" % total_audio)
        A("  (compared against the HD duration, never against chunks*300 — the")
        A("   last chunk is short by design and that formula invents a phantom deficit)")
    else:
        # Partial sums lie. Two consecutive reports on the SAME finished
        # render printed -1389.614s then -1089.614s, because the render
        # deletes chunk WAVs as it goes. The value tracked cleanup, not
        # drift. Never compare a partial sum against a full duration.
        A("- per-chunk drift: not computed — %d of %d chunk WAVs still exist "
          "(the render deletes them as it goes). A partial sum compared against "
          "the full HD duration fabricates a large false deficit, so it is omitted. "
          "**INV-3 below is the authoritative check** — it is computed from the "
          "delivered file and is unaffected by cleanup."
          % (measured, len(chunk_rows)))
    A("")
    A("## Delivered file checks")
    if vdur and adur:
        skew = adur - vdur
        A("- video %.3fs · audio %.3fs · **INV-3 skew %+.3fs** (tolerance 0.50s) → %s"
          % (vdur, adur, skew, "PASS" if abs(skew) <= 0.5 else "FAIL"))
        A("- for reference, the pre-fix drift bug measured **-13.270s** here")
    else:
        A("- could not read stream durations")
    A("")
    A("## Anomalies")
    if anomalies:
        A("The engine reported these during the render:")
        A("")
        for a_ in anomalies[:40]:
            A("- `%s`" % a_)
    else:
        A("None. No bed-only fallbacks, separation failures or tracebacks.")
    A("")
    A("## What this mode does (and does not) do")
    A("- Keeps the HD's OWN music, effects and action audio — correct by construction.")
    A("- Lays only the dub's isolated Somali speech over it.")
    # This line used to read "Does NOT burn in branding" unconditionally. Once
    # branding shipped, the report stated the OPPOSITE of what the render did:
    # it told John a film carrying 2 logos and 8 caption passes was unbranded.
    # A report that contradicts the file is worse than no report, so it now
    # states the branding state it was actually given.
    if branding == "on":
        # Say what was ACTUALLY burned in, not a fixed phrase. The first version
        # of this line read "logos + scrolling caption" unconditionally, so a
        # render with a logo and NO caption (John's scroll_text is empty) was
        # reported as having one. That is the same over-claiming this block was
        # written to stop, one level finer. The engine already logs the truth:
        #   [dlg] branding ON 1920x804: 1 logo(s), 2 filters, ...
        #         caption passes at [...]
        # so parse it rather than guess.
        _logos, _caps = None, None
        try:
            import re as _re
            _raw = Path(str(out)).with_name(Path(str(out)).stem + ".log")
            if _raw.exists():
                for _ln in _raw.read_text(errors="replace").splitlines():
                    if "branding ON" not in _ln:
                        continue
                    _m = _re.search(r"(\d+)\s+logo\(s\)", _ln)
                    if _m:
                        _logos = int(_m.group(1))
                    _c = _re.search(r"caption passes at \[([^\]]*)\]", _ln)
                    if _c:
                        _items = [x for x in _c.group(1).split(",") if x.strip()]
                        _caps = len(_items)
                    break
        except Exception:
            pass
        if _logos is None:
            A("- Branding IS burned in, in the same video pass that attaches")
            A("  the audio — no second encode.")
        else:
            _bits = "%d logo(s)" % _logos
            _bits += (" + %d caption pass(es)" % _caps) if _caps else " (no caption)"
            A("- Branding IS burned in: %s, in the same video pass that" % _bits)
            A("  attaches the audio — no second encode.")
    elif branding == "off":
        A("- No branding burned in (none was configured for this job).")
    else:
        A("- Branding state not recorded for this render.")
    A("- Renders the HD timeline, not the dub editorial cut.")
    A("- Lip-to-word sync is not achievable for any dub: the picture is an actor")
    A("  speaking another language. What is achievable is shot/event placement.")
    A("")
    rp.write_text("\n".join(L), encoding="utf-8")
    return rp


async def _render_dialogue_layer(hd: Path, dub: Path, title: str,
                                 on_progress, register, cancelled, stats,
                                 brand_path: Path | None = None) -> DubResult:
    """HD master + Somali-dialogue overlay (dubsync2 dialogue_layer, --full).

    Keeps the HD's own music/SFX/action audio and lays ONLY the dub's isolated
    speech over it, so the fight/impact matching that has no reliable automatic
    signal never arises. Renders the HD timeline, not the dub editorial
    timeline -- the caller states that plainly.

    Branding is now OPTIONAL here rather than absent: given brand_path, the
    logos and caption are burned in during the mux's EXISTING video re-encode,
    so this mode no longer trades John's branding away to get HD audio.
    """
    work = _work_dir_for(hd, dub)
    # Real denominator for the progress bar. Without this the first chunk
    # reports 100% (clamped to 99) and the panel sits there for the rest of
    # the render -- measured on the first end-to-end run.
    if not stats.get("hd_duration_s"):
        try:
            _r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(hd)], capture_output=True, text=True)
            stats["hd_duration_s"] = float(_r.stdout.strip())
        except (ValueError, OSError):
            pass
    if not (work / "edl.json").exists():
        return DubResult(False, None,
                         f"dialogue-layer needs the anchor map; edl.json missing in {work}",
                         stats)
    out = OUT_DIR / f"{title}_dlg.mp4"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [DLG_PY, "-u", DLG_SCRIPT, "--work", str(work),
           "--full", "--chunk", "300", "--out", str(out)]
    # Brand only when the panel actually produced a config. Passing a missing
    # path would make the engine log UNBRANDED on every render and hide a real
    # misconfiguration behind a warning nobody reads.
    if brand_path and Path(brand_path).exists():
        cmd += ["--brand-json", str(brand_path)]
        stats["branding"] = "on"
    else:
        stats["branding"] = "off"

    # Cut what the HD does not contain -- John standing rule, so an intro or outro
    # spliced into the dub never reaches a delivered film again. nohd_spans finds
    # runs where the film stops advancing while the dub keeps going (an intro, an
    # outro, or an advert), and a tail run is extended to the end of the dub.
    # Validated across 23 work dirs: the approved films (WTTJ, Badla, The Comeback,
    # Tammal, Jumper, Dial) all come back clean, and it refuses any film whose edl
    # claims more dub than the dub file holds.
    # FAILS OPEN: any error, or no spans, and the render proceeds exactly as before.
    try:
        import subprocess as _sp
        import json as _json
        # A STALE active set must never survive (FM-079). If this run's union refuses --
        # say the spans would exceed 10% of the dub -- an old file left in place would be
        # used instead, and yesterday's verdict would cut today's film. Remove it first so
        # a refusal fails open to NO exclusions rather than to the previous answer.
        try:
            (work / "spans_active.json").unlink()
        except OSError:
            pass

        # 1. Collapse spans: intros and outros the HD does not contain.
        #    HEAD/TAIL ONLY -- mid-film is refused, because a collapse there can be a
        #    matcher failure over REAL dialogue. Ghost's would have cut 81s of John's
        #    speech: its vocals measured -17.4 dB against dialogue at -16.4 dB (FM-069).
        _sp.run([DLG_PY, "/opt/dubsync2/nohd_spans.py", work.name, "--write"],
                capture_output=True, text=True, timeout=600)

        # 2. Adverts: card-likeness AND positive OCR promotional text, BOTH required.
        #    Catches the SHORT promos that sit under nohd_spans' 30s floor (Ghost's
        #    22s/25s/6s). Tested across 7 approved films: 12 stage-1 candidates, ALL
        #    rejected by the text stage, 0 false positives (FM-078). Costs 6-17s against
        #    a ~2.5h render.
        _sp.run([DLG_PY, "/opt/dubsync2/promo_detect.py", str(work), "--write"],
                capture_output=True, text=True, timeout=900)

        # 3. One active set: sorted union, overlaps kept, NEVER merged and re-judged
        #    (FM-068b -- merging averaged two criteria together and refused both).
        _sp.run([DLG_PY, "/opt/dubsync2/spans_union.py", work.name],
                capture_output=True, text=True, timeout=300)

        _spans = work / "spans_active.json"
        if _spans.exists():
            _n = len((_json.load(open(_spans)) or {}).get("promos") or [])
            if _n:
                cmd += ["--promo-json", str(_spans)]
                stats["exclusion_spans"] = _n
    except Exception as _exc:
        stats["exclusion_spans"] = "skipped (%s)" % type(_exc).__name__
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    if register:
        register(proc)
    placed = 0
    chunks = 0
    chunk_rows: list[dict] = []
    anomalies: list[str] = []
    tail: list[str] = []
    # Keep the engine's RAW stdout. A report rebuilt from a log that lacks the
    # chunk lines shows an empty table and "0 placed" on a render that actually
    # placed 1254 segments -- misleading evidence is worse than none.
    raw_log = OUT_DIR / f"{title}_dlg.log"
    try:
        raw_fh = open(raw_log, "w", encoding="utf-8")
    except OSError:
        raw_fh = None
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        line = raw.decode("utf-8", "replace").rstrip()
        if raw_fh:
            try:
                raw_fh.write(line + "\n")
                raw_fh.flush()
            except OSError:
                pass
        tail.append(line)
        del tail[:-25]
        low = line.lower()
        if ("bed-only" in low or "separation failed" in low
                or "traceback" in low or "no space" in low):
            anomalies.append(line)
        if cancelled():
            try:
                proc.kill()
            except Exception:
                pass
            return DubResult(False, None, "cancelled", stats)
        m = re.search(r"chunk (\d+) HD\[([\d.]+),([\d.]+)\] (\d+) segs, (\d+) placed", line)
        if m:
            chunks += 1
            placed += int(m.group(5))
            chunk_rows.append({
                "idx": int(m.group(1)),
                "hd_start": float(m.group(2)),
                "hd_end": float(m.group(3)),
                "segs": int(m.group(4)),
                "placed": int(m.group(5)),
            })
            # HD seconds completed / total -> a real percentage for the panel
            try:
                done_s = float(m.group(3))
                total_s = float(stats.get("hd_duration_s") or 0) or done_s
                pct = max(0.0, min(99.0, done_s / total_s * 100.0)) if total_s else 0.0
            except (ValueError, ZeroDivisionError):
                pct = 0.0
            res = on_progress("\U0001F5E3 Laying Somali dialogue", pct)
            if asyncio.iscoroutine(res):
                await res
    await proc.wait()
    if raw_fh:
        try:
            raw_fh.close()
        except OSError:
            pass
    if proc.returncode != 0:
        return DubResult(False, None,
                         "dialogue-layer failed (exit %d)\n%s"
                         % (proc.returncode, " > ".join(tail[-4:])[:500]), stats)
    if not out.exists() or out.stat().st_size == 0:
        return DubResult(False, None, "dialogue-layer produced no file", stats)

    # INV-3: the audio must not slide against the picture. A concat bug once
    # shipped a film whose audio ran 13.27 s short of its video.
    def _dur(sel: str) -> float:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", sel,
                            "-show_entries", "stream=duration", "-of", "csv=p=0",
                            str(out)], capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except ValueError:
            return 0.0

    v, a = _dur("v:0"), _dur("a:0")
    try:
        rp = _write_render_report(title, hd, dub, work, out, chunk_rows,
                                  anomalies, v, a, placed, chunks,
                                  stats.get("branding", "unknown"))
        stats["report"] = str(rp)
    except Exception as _e:            # a report must never fail the render
        stats["report_error"] = str(_e)[:200]
    stats["raw_log"] = str(raw_log)
    stats["mode"] = "dialogue-layer"
    stats["segments_placed"] = placed
    stats["chunks"] = chunks
    if v and a:
        skew = a - v
        stats["av_skew_s"] = round(skew, 3)
        if abs(skew) > 0.5:
            return DubResult(True, out,
                             "delivered for review — audio/video skew %+.3fs (INV-3)" % skew,
                             stats)

    # PLAYABILITY GATE (FM-015). A render used to be called "released" on sync
    # alone, and that is exactly how a film that no Android decoder could open
    # was reported as finished with a +0.001s skew. Sync being perfect is
    # worthless if the file will not play. libx264 inherits the SOURCE pixel
    # format, so a 10-bit master yields High 10 (and, with a logo in the graph,
    # High 4:4:4 Predictive) unless the mux pins yuv420p.
    try:
        _pf = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=pix_fmt,profile", "-of", "csv=p=0",
             str(out)], capture_output=True, text=True).stdout.strip()
    except OSError:
        _pf = ""
    stats["pix_fmt"] = _pf or "unknown"
    if _pf and "yuv420p" not in _pf.split(",")[-1]:
        return DubResult(True, out,
                         "delivered for review — NOT PLAYABLE on Android "
                         "(%s); needs yuv420p (FM-015)" % _pf,
                         stats)

    return DubResult(True, out, "released", stats)


def _quality_report(title: str) -> dict:
    """Mine the real per-shot numbers for the delivery caption.

    Everything here already exists in the work dir after a render - it was
    just never surfaced. John asked to see lip-sync quality on every delivery,
    not only when the gate holds.
    """
    import glob, json as _json, os as _os
    try:
        cands = sorted(glob.glob('/opt/dubsync2/work/*/edl.json'),
                       key=_os.path.getmtime, reverse=True)
        if not cands:
            return {}
        wd = _os.path.dirname(cands[0])
        edl = _json.load(open(_os.path.join(wd, 'edl.json')))
        shots = [e for e in edl['edl'] if e.get('hd_idx') is not None]
        body = [e for e in shots if not e.get('is_intro_cluster')]
        if not body:
            return {}
        confs = [e['visual_conf'] for e in body if e.get('visual_conf') is not None]
        out = {}
        if confs:
            confs_sorted = sorted(confs)
            out['visual_mean'] = sum(confs) / len(confs)
            out['visual_median'] = confs_sorted[len(confs_sorted) // 2]
            # a shot is "locked" when the picture matched HD strongly enough
            # that no audio-envelope rescue was needed
            out['locked_pct'] = 100.0 * sum(1 for e in body
                                            if not e.get('needs_resync')) / len(body)
        resynced = [e for e in body if e.get('needs_resync')]
        out['resynced'] = len(resynced)
        out['shots'] = len(body)
        deltas = [abs(e['audio_resync_delta_s']) for e in body
                  if e.get('audio_resync_delta_s') is not None]
        if deltas:
            out['max_drift'] = max(deltas)
            out['mean_drift'] = sum(deltas) / len(deltas)
        ip = _os.path.join(wd, 'integrity_report.json')
        if _os.path.exists(ip):
            r = _json.load(open(ip))
            out['accidental_s'] = r.get('accidental_seconds')
            out['visible_s'] = r.get('visible_accidental_seconds')
            out['benign_s'] = r.get('benign_reuse_seconds')
            out['unknown_s'] = r.get('unknown_seconds')
            out['sync_collateral'] = r.get('sync_collateral')
        cut = [e for e in shots if e.get('is_intro_cluster')]
        if cut:
            out['cut_s'] = sum((e.get('dub_end_s') or 0) - (e.get('dub_start_s') or 0)
                               for e in cut)
        return out
    except Exception:
        return {}


def summary_caption(title: str, res: DubResult, dur_s: float, size_b: int) -> str:
    st = res.stats
    _passed = st.get("gate") == "passed"
    _nblock = len(st.get("gate_notes") or [])
    _head = "dub-sync complete" if _passed else "⚠️ dub-sync — NEEDS REVIEW (NOT final)"
    lines = [f"🎬 **{title}** — {_head}",
             f"`{int(dur_s//3600)}h {int(dur_s%3600//60):02d}m` · {size_b/1e9:.2f} GB"]
    if not _passed:
        _bs = "s" if _nblock != 1 else ""
        lines.append(f"⛔ **Integrity gate FAILED** — {_nblock} blocker{_bs}. Delivered "
                     f"for manual review; this is NOT a finished master. Check the "
                     f"🔁 spots below by eye (esp. the first ~90s and last ~90s).")
    if st.get("match_rate"):
        lines.append(f"✅ shot match: **{st['match_rate']}**")
    if st.get("intro_shots"):
        extra = " + closing promo" if st.get("promo_removed") else ""
        lines.append(f"✂️ dub intro removed ({st['intro_shots']} shots){extra}")
    if st.get("duplication"):
        lines.append(f"🧹 residual repeats: {st['duplication']}")
    lines.append("🛡 integrity gate: " +
                 ("✅ **passed**" if _passed
                  else f"❌ **FAILED — release held** ({_nblock} blocker" + ("s" if _nblock != 1 else "") + ")"))
    q = _quality_report(title)
    if q:
        lines.append("")
        lines.append("📊 **Quality report**" + ("" if _passed else " _(measured on a NOT-final cut)_"))
        if q.get("locked_pct") is not None:
            lines.append(f"🎯 lip-sync locked: **{q['locked_pct']:.1f}%** "
                         f"({q['shots'] - q.get('resynced', 0)}/{q['shots']} shots "
                         f"matched picture-to-picture)")
        if q.get("resynced"):
            lines.append(f"🎧 audio-resynced: {q['resynced']} shots "
                         f"(rescued by sound when the picture was unclear)")
        if q.get("visual_mean") is not None:
            lines.append(f"👁 picture match: mean **{q['visual_mean']:.3f}** "
                         f"/ median {q.get('visual_median', 0):.3f}")
        if q.get("max_drift") is not None:
            lines.append(f"⏱ sync drift: avg {q.get('mean_drift', 0):.2f}s, "
                         f"worst {q['max_drift']:.2f}s")
        if q.get("cut_s"):
            lines.append(f"✂️ channel material cut: {q['cut_s']:.0f}s")
        if q.get("visible_s") is not None:
            _bn = q.get("benign_s") or 0.0
            lines.append(f"👁 visible repeats: {q['visible_s']:.1f}s"
                         + (f"  ·  {_bn:.1f}s static reuse (invisible)" if _bn else ""))
        elif q.get("accidental_s") is not None:
            lines.append(f"🧹 repeated footage: {q['accidental_s']:.1f}s "
                         f"(songs/montages count here — not always a fault)")
        if q.get("sync_collateral"):
            lines.append(f"⚠️ shots moved off their verified anchor: "
                         f"{q['sync_collateral']}")
    for n in (st.get("gate_notes") or [])[:2]:
        lines.append(f"   ⚠️ {n}")
    return "\n".join(lines)
