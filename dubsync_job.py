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
                     "released" if released else "finished, but the gate held it",
                     stats)


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
    lines = [f"🎬 **{title}** — dub-sync complete",
             f"`{int(dur_s//3600)}h {int(dur_s%3600//60):02d}m` · {size_b/1e9:.2f} GB"]
    if st.get("match_rate"):
        lines.append(f"✅ shot match: **{st['match_rate']}**")
    if st.get("intro_shots"):
        extra = " + closing promo" if st.get("promo_removed") else ""
        lines.append(f"✂️ dub intro removed ({st['intro_shots']} shots){extra}")
    if st.get("duplication"):
        lines.append(f"🧹 residual repeats: {st['duplication']}")
    lines.append("🛡 integrity gate: " +
                 ("**passed**" if st.get("gate") == "passed" else "**held**"))
    q = _quality_report(title)
    if q:
        lines.append("")
        lines.append("📊 **Quality report**")
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
        if q.get("accidental_s") is not None:
            lines.append(f"🧹 repeated footage: {q['accidental_s']:.1f}s "
                         f"(songs/montages count here — not always a fault)")
        if q.get("sync_collateral"):
            lines.append(f"⚠️ shots moved off their verified anchor: "
                         f"{q['sync_collateral']}")
    for n in (st.get("gate_notes") or [])[:2]:
        lines.append(f"   ⚠️ {n}")
    return "\n".join(lines)
