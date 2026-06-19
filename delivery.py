"""
Large-file delivery: when a branded video is over Telegram's bot limit (~2GB),
deliver it another way.

  * MEGA  — upload via rclone, return a public download link (any size, no
            premium needed). Configured with the owner's MEGA login.
  * Premium — handled in bot.py via a logged-in premium USER session (up to 4GB
              native Telegram upload).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

RCLONE_CONF = "/app/data/rclone.conf"
REMOTE = "megabidhaan"
FOLDER = "BidhaanLogoEdit"
RCLONE = shutil.which("rclone") or "/usr/local/bin/rclone"


def _rclone(*args: str, timeout: int = 36000) -> subprocess.CompletedProcess:
    return subprocess.run([RCLONE, "--config", RCLONE_CONF, *args],
                          capture_output=True, text=True, timeout=timeout)


def mega_configure(email: str, password: str) -> tuple[bool, str]:
    """Set up the MEGA remote with the owner's login. Returns (ok, message)."""
    obs = subprocess.run(["rclone", "obscure", password],
                         capture_output=True, text=True)
    if obs.returncode != 0:
        return False, "rclone obscure failed"
    pw = obs.stdout.strip()
    # recreate the remote
    _rclone("config", "delete", REMOTE)
    r = _rclone("config", "create", REMOTE, "mega", "user", email, "pass", pw)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[-300:]
    # verify the login works
    chk = _rclone("lsd", f"{REMOTE}:", timeout=120)
    if chk.returncode != 0:
        # DON'T leave a poisoned remote behind: a remote with bad creds makes
        # mega_is_configured() return True, so later uploads fail with the
        # confusing "rclone exit 1". Remove it so the bot stays cleanly "not set
        # up" until a valid login succeeds.
        _rclone("config", "delete", REMOTE)
        return False, "login failed: " + (chk.stderr or chk.stdout)[-200:]
    return True, "ok"


def mega_is_configured() -> bool:
    if not os.path.exists(RCLONE_CONF):
        return False
    r = _rclone("listremotes")
    return f"{REMOTE}:" in (r.stdout or "")


def mega_download(link: str, dest: str, progress_cb=None, register=None) -> tuple[str, str]:
    """Download a MEGA public link straight to the server with megatools (megadl)
    — full bandwidth (~200+ MB/s), far faster than pulling the file through
    Telegram. Saves to `dest`; returns (path, original_filename).

    progress_cb(pct 0..100) is called as it downloads (parsed from megadl).
    register(proc) is called with the process so the caller can cancel it."""
    proc = subprocess.Popen(
        ["megadl", "--path", dest, link],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    if register:
        register(proc)
    assert proc.stdout is not None
    name = None
    for line in proc.stdout:
        # lines look like: "Movie.mp4: 10.93% - 243 MiB of 2.2 GiB (242 MiB/s)"
        if name is None and ": " in line and "%" in line:
            name = line.split(": ", 1)[0].strip()
        mo = re.search(r"(\d+(?:\.\d+)?)%", line)
        if mo and progress_cb:
            try:
                progress_cb(float(mo.group(1)))
            except Exception:
                pass
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("MEGA download failed (megadl exit %d)" % proc.returncode)
    if not os.path.exists(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError("MEGA download produced no file")
    return dest, (name or os.path.basename(dest))


def mega_upload(path: str, name: str | None = None, progress_cb=None) -> str:
    """Upload a file to MEGA and return a public download link.

    If progress_cb is given, it's called with a 0..100 float as the upload
    proceeds (parsed from rclone's live progress output)."""
    import re

    def _friendly(text: str) -> str:
        # surface the common, actionable cause instead of "rclone exit 1"
        if "over quota" in text.lower() or "quota" in text.lower():
            return ("your MEGA account is OUT OF SPACE / over quota — free up "
                    "storage in MEGA (or wait for the transfer limit to reset), "
                    "or use /loginpremium to send up to 4GB via your own account")
        return (text or "unknown error").strip()[-300:]

    name = name or os.path.basename(path)
    dest = f"{REMOTE}:{FOLDER}/{name}"
    if progress_cb is None:
        up = _rclone("copyto", path, dest)
        if up.returncode != 0:
            raise RuntimeError("MEGA upload failed: " + _friendly(up.stderr or up.stdout))
    else:
        proc = subprocess.Popen(
            [RCLONE, "--config", RCLONE_CONF, "copyto", path, dest,
             "-P", "--stats", "2s", "--stats-one-line"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert proc.stdout is not None
        tail = []
        for line in proc.stdout:
            tail.append(line)
            del tail[:-25]                       # keep only the last lines
            mobj = re.search(r"(\d+)%", line)
            if mobj:
                try:
                    progress_cb(float(mobj.group(1)))
                except Exception:
                    pass
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError("MEGA upload failed: " + _friendly("".join(tail)))
    link = _rclone("link", dest, timeout=300)
    if link.returncode != 0:
        raise RuntimeError("MEGA link failed: " + (link.stderr or link.stdout)[-300:])
    return link.stdout.strip()
