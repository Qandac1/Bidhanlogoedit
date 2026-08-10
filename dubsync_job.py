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

# Stage weights measured on real runs (2h09 episode, 8 cores). They only need
# to be roughly right — their job is to keep the bar honest, not exact.
STAGES: list[tuple[str, str, float]] = [
    ("analyze",   "🔍 Analysing shots",      0.30),
    ("stage1",    "✂️ Finding editorial cuts", 0.02),
    ("calibrate", "🎯 Calibrating to this master", 0.06),
    ("stage2",    "✅ Verifying every shot",  0.22),
    ("stage3",    "🩹 Healing mismatches",    0.08),
    ("stage3-5",  "🔎 Global search",         0.04),
    ("render",    "🎬 Rendering",             0.24),
    ("dedupe",    "🧹 Removing repeats",      0.04),
]


@dataclass
class DubResult:
    ok: bool
    path: Optional[Path]
    message: str
    stats: dict


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "", Path(name).stem).lower()
    return (s or "job")[:24]


def prepare_inputs(hd_src: Path, dub_src: Path, title: str) -> tuple[Path, Path]:
    """Place the two files where the engine expects them.

    Hardlinked when possible so a 2 GB pair is not copied twice on a disk that
    has been near-full before.
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
    max_accidental: float = 20.0,
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
              "--crf", str(crf), "--output-name", out_name]
    if brand_path:
        render += ["--brand-config", str(brand_path)]

    cmds = {
        "analyze":   [*base, "analyze", "--title", title],
        "stage1":    [*base, "stage1", "--title", title],
        "calibrate": [*base, "stage2-calibrate", "--title", title],
        "stage2":    [*base, "stage2", "--title", title],
        "stage3":    [*base, "stage3", "--title", title],
        "stage3-5":  [*base, "stage3-5", "--title", title],
        "render":    render,
        "dedupe":    [*base, "dedupe", "--title", title],
    }

    stats: dict = {}
    done_weight = 0.0
    total_weight = sum(w for _, _, w in STAGES)

    # progress markers inside a stage's own output
    pat_frac = re.compile(r"\[\s*(\d+)\s*/\s*(\d+)\s*\]")
    pat_pass = re.compile(r"PASS:\s*(\d+)\s*/\s*(\d+)")
    pat_total = re.compile(r"Total pass after Stage 3(?:\.5)?:\s*(\d+)/(\d+)\s*\(([\d.]+)%\)")
    pat_dup = re.compile(r"accidental:\s*([\d.]+)s")
    pat_intro = re.compile(r"Dub intro removed:\s*(\d+) shots")
    pat_promo = re.compile(r"trailing promo")

    for key, label, weight in STAGES:
        cmd = cmds[key]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        assert proc.stdout is not None
        inner = 0.0
        last_emit = 0.0
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace")
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

            pct = (done_weight + weight * inner) / total_weight * 100.0
            if pct - last_emit >= 1.0:
                last_emit = pct
                res = on_progress(label, pct)
                if asyncio.iscoroutine(res):
                    await res
        rc = await proc.wait()
        if rc != 0:
            return DubResult(False, None, f"{label} failed (exit {rc})", stats)
        done_weight += weight
        res = on_progress(label, done_weight / total_weight * 100.0)
        if asyncio.iscoroutine(res):
            await res

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
        if ln.strip().startswith("✗"):
            stats.setdefault("gate_notes", []).append(ln.strip()[1:].strip())

    return DubResult(True, out,
                     "released" if released else "finished, but the gate held it",
                     stats)


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
    for n in (st.get("gate_notes") or [])[:2]:
        lines.append(f"   ⚠️ {n}")
    return "\n".join(lines)
