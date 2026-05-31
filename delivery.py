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
import subprocess

RCLONE_CONF = "/app/data/rclone.conf"
REMOTE = "megabidhaan"
FOLDER = "BidhaanLogoEdit"


def _rclone(*args: str, timeout: int = 36000) -> subprocess.CompletedProcess:
    return subprocess.run(["rclone", "--config", RCLONE_CONF, *args],
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
        return False, "login failed: " + (chk.stderr or chk.stdout)[-200:]
    return True, "ok"


def mega_is_configured() -> bool:
    if not os.path.exists(RCLONE_CONF):
        return False
    r = _rclone("listremotes")
    return f"{REMOTE}:" in (r.stdout or "")


def mega_upload(path: str, name: str | None = None) -> str:
    """Upload a file to MEGA and return a public download link."""
    name = name or os.path.basename(path)
    dest = f"{REMOTE}:{FOLDER}/{name}"
    up = _rclone("copyto", path, dest)
    if up.returncode != 0:
        raise RuntimeError("MEGA upload failed: " + (up.stderr or up.stdout)[-300:])
    link = _rclone("link", dest, timeout=300)
    if link.returncode != 0:
        raise RuntimeError("MEGA link failed: " + (link.stderr or link.stdout)[-300:])
    return link.stdout.strip()
