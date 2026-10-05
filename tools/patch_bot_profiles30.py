"""bot30: TWO INDEPENDENT SETS OF SETTINGS per user -- BANNER jobs and DUB-SYNC films.

John 2026-10-05: "I want banner and dub sync totally different, independent, so my dub-sync settings stay the way
they are." Until now one record served both: the logo place / size / start time, the caption, the output size and
bitrate, the trim -- a change made for a banner job changed the next dub-sync film too.

  storage     the user's record stays as it is and IS the banner set; the dub-sync set lives beside it under
              "_dub". It is born as a copy of the banner set at that moment (at the bot's start for every
              user who has none -- so today's dub-sync settings are frozen exactly as they are -- and before the
              first later change of either set), and from then on nothing written to one reaches the other.
              Shared on purpose: the uploaded logo IMAGE (custom_logo).
  user_cfg(uid, profile=None) / set_user(uid, _profile=None, **kw)
              profile "dub" | "banner"; None = the set the user is working in right now (_ui_profile): "dub"
              from /dub, a dub-sync panel or its buttons, "banner" from a video sent for the logo, a banner
              panel or its buttons. Typed commands (/text, /logoat, /at ...) follow it; a time typed after
              "set ... time" goes to the set of the panel that asked.
  renders     never read the "working in" state: dub-sync reads "dub" (_run_dubsync, the dub panel, the brand
              settings handed to the engine), banner jobs read "banner" (_render_job, the batch panel).
A user who never touches the other flow sees no change at all.
Usage: python patch_bot_profiles30.py <bot dir>     (patches <bot dir>/bot.py in place)"""
import sys
from pathlib import Path

P = Path(sys.argv[1]) / "bot.py"
s = P.read_text()
if "_ui_profile" in s:
    sys.exit("already patched: %s" % P)


def rep(old, new, what, n=1):
    global s
    k = s.count(old)
    assert k == n, "%s: anchor found %d times (wanted %d)" % (what, k, n)
    s = s.replace(old, new)
    print("ok  " + what)


rep('''def user_cfg(uid: int) -> dict:
    d = _load()
    c = dict(DEFAULTS)
    c.update(d.get(str(uid), {}))
    return c


def set_user(uid: int, **kw) -> dict:
    d = _load()
    cur = dict(DEFAULTS)
    cur.update(d.get(str(uid), {}))
    cur.update(kw)
    d[str(uid)] = cur
    _save(d)
    return cur
''', '''# bot30 (John 2026-10-05: "banner and dub sync totally different, independent -- my dub-sync settings stay the way
# they are"): two sets of settings per user. The record itself is the BANNER set; "_dub" beside it is the DUB-SYNC
# set, born as a copy of the banner set and independent from then on. The uploaded logo image is shared.
PROFILE_DUB_KEY = "_dub"
PROFILE_SHARED = ("custom_logo",)
PROFILE_LABEL = {"banner": "Banner jobs", "dub": "Dub-sync films"}
_ui_profile: dict = {}          # uid -> "dub" | "banner": the set the user is working in right now


def _set_ui_profile(uid: int, name: str) -> None:
    _ui_profile[uid] = "dub" if name == "dub" else "banner"


def _profile_of(uid: int, profile=None) -> str:
    p = profile or _ui_profile.get(uid) or "banner"
    return "dub" if p == "dub" else "banner"


def _split_record(rec: dict) -> tuple:
    """(banner set, dub-sync set) of a stored record; the dub-sync set is a copy of the banner set when the
    record has none yet."""
    flat = dict(DEFAULTS)
    flat.update({k: v for k, v in (rec or {}).items() if k != PROFILE_DUB_KEY})
    dub = (rec or {}).get(PROFILE_DUB_KEY)
    if not isinstance(dub, dict):
        dub = {k: flat[k] for k in DEFAULTS if k not in PROFILE_SHARED}
    return flat, dict(dub)


def user_cfg(uid: int, profile=None) -> dict:
    flat, dub = _split_record(_load().get(str(uid), {}))
    if _profile_of(uid, profile) == "dub":
        flat.update({k: v for k, v in dub.items() if k not in PROFILE_SHARED})
    return flat


def set_user(uid: int, *, _profile=None, **kw) -> dict:
    d = _load()
    flat, dub = _split_record(d.get(str(uid), {}))
    if _profile_of(uid, _profile) == "dub":
        for k, v in kw.items():
            if k in PROFILE_SHARED or k not in DEFAULTS:
                flat[k] = v
            else:
                dub[k] = v
    else:
        flat.update(kw)
    rec = dict(flat)
    rec[PROFILE_DUB_KEY] = dub
    d[str(uid)] = rec
    _save(d)
    return user_cfg(uid, _profile_of(uid, _profile))


def _migrate_profiles() -> int:
    """Every user who has no dub-sync set yet gets one NOW, a copy of the settings as they are -- so a later
    banner change cannot reach the dub-sync films. Returns how many were made."""
    d = _load()
    n = 0
    for k, rec in list(d.items()):
        if isinstance(rec, dict) and not isinstance(rec.get(PROFILE_DUB_KEY), dict):
            flat, dub = _split_record(rec)
            new = dict(rec)
            new[PROFILE_DUB_KEY] = dub
            d[k] = new
            n += 1
    if n:
        _save(d)
    return n
''', "user_cfg / set_user with two sets")

rep('''def _batch_panel_text(uid: int, n: int) -> str:
    c = user_cfg(uid)
''', '''def _batch_panel_text(uid: int, n: int) -> str:
    c = user_cfg(uid, "banner")
''', "the batch panel reads the banner set")

rep('''        return f"{tag} `{n[:38]}`\\n     {res}{dur}"

    c = user_cfg(uid)
''', '''        return f"{tag} `{n[:38]}`\\n     {res}{dur}"

    c = user_cfg(uid, "dub")
''', "the dub panel reads the dub-sync set")

rep('''def _brand_payload(uid: int) -> dict:
''', '''def _brand_payload(uid: int, profile=None) -> dict:
''', "_brand_payload takes the set")
rep('''    burned into a StreamNxt-style source, and a clean HD master has none.
    """
    c = user_cfg(uid)
    sc = c["logo_scale"]
''', '''    burned into a StreamNxt-style source, and a clean HD master has none.
    """
    c = user_cfg(uid, profile)
    sc = c["logo_scale"]
''', "_brand_payload reads it")
rep('''(_brand_payload(uid) if brand else None)''', '''(_brand_payload(uid, "dub") if brand else None)''', "the dub-sync render gets the dub-sync brand settings")

rep('''        # no point transcoding 1080p only to hand it to a 720p render.
        c = user_cfg(uid)
''', '''        # no point transcoding 1080p only to hand it to a 720p render.
        c = user_cfg(uid, "dub")
''', "_run_dubsync reads the dub-sync set")

rep('''    async with _render_sem:
        c = user_cfg(uid)
''', '''    async with _render_sem:
        c = user_cfg(uid, "banner")
''', "_render_job reads the banner set")

# ---- which set the user is working in
rep('''async def _dubflow_start(uid: int, m: Message, text: str = DUB_ASK_HD,
                         kb: IKM | None = None) -> None:
    _dubflow[uid] = {"step": "hd", "hd": None, "dub": None}
''', '''async def _dubflow_start(uid: int, m: Message, text: str = DUB_ASK_HD,
                         kb: IKM | None = None) -> None:
    _set_ui_profile(uid, "dub")
    _dubflow[uid] = {"step": "hd", "hd": None, "dub": None}
''', "/dub -> working in the dub-sync set")

rep('''    # A guided dub-sync takes priority; otherwise behave exactly as before.
    if await _dubflow_take(uid, m):
        return
    _enqueue(uid, m)
''', '''    # A guided dub-sync takes priority; otherwise behave exactly as before.
    if await _dubflow_take(uid, m):
        _set_ui_profile(uid, "dub")
        return
    _set_ui_profile(uid, "banner")
    _enqueue(uid, m)
''', "a video for the logo -> working in the banner set")

rep('''    uid = cq.from_user.id
    if not _allowed(uid):
        return await cq.answer("private", show_alert=True)
    job = _pending.get(uid)
    data = cq.data
''', '''    uid = cq.from_user.id
    if not _allowed(uid):
        return await cq.answer("private", show_alert=True)
    job = _pending.get(uid)
    data = cq.data
    _set_ui_profile(uid, "dub" if _is_dub_msg(uid, cq.message) else "banner")
''', "a button -> the set of its panel")

rep('''        _dubsel[uid] = {"msgs": msgs, "hd_i": hd_i, "brand": True, "panel": None,
''', '''        _set_ui_profile(uid, "dub")
        _dubsel[uid] = {"msgs": msgs, "hd_i": hd_i, "brand": True, "panel": None,
''', "'Dub-sync these two' -> working in the dub-sync set")

rep('''async def _refresh_active_panel(cq, uid: int, job: dict) -> None:
''', '''def _is_dub_msg(uid: int, msg) -> bool:
    """Is this message a dub-sync panel (or one of its submenus)? The same test _refresh_active_panel uses,
    plus the panel's own first line -- a submenu keeps the panel's text."""
    try:
        _sel = _dubsel.get(uid)
        _pm = (_sel or {}).get("panel")
        if _sel and (getattr(_pm, "id", None) == getattr(msg, "id", -1)
                     or (_pm is None and not _pending.get(uid))):
            return True
        first = ((getattr(msg, "text", None) or getattr(msg, "caption", None) or "").strip().splitlines() or [""])[0].lower()
        return "dub-sync" in first or "dubsync" in first
    except Exception:
        return False


async def _refresh_active_panel(cq, uid: int, job: dict) -> None:
''', "helper _is_dub_msg")

rep('''        _awaiting_time[uid] = {"key": key, "msg": cq.message, "job": job}
''', '''        _awaiting_time[uid] = {"key": key, "msg": cq.message, "job": job, "profile": _profile_of(uid)}
''', "a typed time remembers the set of the panel that asked")
rep('''    set_user(uid, **{key: mins})
    _awaiting_time.pop(uid, None)
''', '''    set_user(uid, _profile=info.get("profile"), **{key: mins})
    _awaiting_time.pop(uid, None)
''', "... and goes to that set")

rep('''    c = user_cfg(m.from_user.id)
    await m.reply("⚙️ **Saved defaults**\\n```\\n" +
''', '''    c = user_cfg(m.from_user.id)
    await m.reply("⚙️ **Saved defaults — %s**\\n```\\n" % PROFILE_LABEL[_profile_of(m.from_user.id)] +
''', "/settings names the set")

rep('''async def _main() -> None:
    from pyrogram import idle
    await app.start()
''', '''async def _main() -> None:
    from pyrogram import idle
    try:
        _n = _migrate_profiles()
        if _n:
            log.info("settings: %d user(s) got their own dub-sync set (a copy of their settings as they were)", _n)
    except Exception:
        log.exception("settings: the dub-sync sets could not be made at start (made on first use instead)")
    await app.start()
''', "the dub-sync sets are made at the bot's start")

P.write_text(s)
print("patched %s" % P)
