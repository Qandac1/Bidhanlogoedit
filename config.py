"""
Central configuration, loaded from environment (.env).

Secrets (API_ID/API_HASH/BOT_TOKEN) NEVER live in code — only in .env on the
server. Everything else has a sane default so the bot runs out of the box.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int | None = None, required: bool = False) -> int:
    val = os.getenv(name)
    if val is None or val == "":
        if required:
            raise RuntimeError(f"Missing required env var: {name}")
        return default  # type: ignore[return-value]
    return int(val)


def _str(name: str, default: str = "", required: bool = False) -> str:
    val = os.getenv(name)
    if (val is None or val == "") and required:
        raise RuntimeError(f"Missing required env var: {name}")
    return val if val else default


@dataclass(frozen=True)
class Settings:
    # ---- Telegram credentials ----
    api_id:    int = field(default_factory=lambda: _int("API_ID", required=True))
    api_hash:  str = field(default_factory=lambda: _str("API_HASH", required=True))
    bot_token: str = field(default_factory=lambda: _str("BOT_TOKEN", required=True))

    # Only this user id may use the bot (John). 0 = open to anyone.
    owner_id:  int = field(default_factory=lambda: _int("OWNER_ID", default=0))

    # ---- Paths ----
    work_dir:   str = field(default_factory=lambda: _str("WORK_DIR", default="/app/work"))
    assets_dir: str = field(default_factory=lambda: _str("ASSETS_DIR", default="/app/assets"))

    # ---- Branding defaults (overridable per-user with /settings) ----
    scroll_text: str = field(default_factory=lambda: _str(
        "SCROLL_TEXT", default="ugaar ah bidhaan tv 0619624090"))

    # Logo files inside assets_dir
    logo_tr: str = field(default_factory=lambda: _str("LOGO_TR", default="streamnxt.png"))
    logo_tl: str = field(default_factory=lambda: _str("LOGO_TL", default="bidhaan.png"))
    cover_png: str = field(default_factory=lambda: _str("COVER_PNG", default="coverbar.png"))

    # ---- Encode tuning ----
    # x264 preset: ultrafast..veryslow. faster = quicker render, slightly bigger file.
    x264_preset: str = field(default_factory=lambda: _str("X264_PRESET", default="ultrafast"))
    x264_crf:    int = field(default_factory=lambda: _int("X264_CRF", default=21))
    # downscale output to this height (0 = keep source). 720 ~ halves render time.
    out_height:  int = field(default_factory=lambda: _int("OUT_HEIGHT", default=0))

    # ---- Detection tuning ----
    detect_fps: float = field(default_factory=lambda: float(_str("DETECT_FPS", default="1")))
    # merge cover events closer than this many seconds into one
    merge_gap:  float = field(default_factory=lambda: float(_str("MERGE_GAP", default="2.5")))


settings = Settings()
