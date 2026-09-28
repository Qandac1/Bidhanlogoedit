"""After every dub-sync delivery the bot sends WHAT THE DUB REMOVED in John's approved style
(2026-09-28: "now understandable, same like that the report will be"): places grouped, Somali +
English, one picture with a numbered frame per place (censored places show the dub's picture).
tools/cut_list.py + tools/cut_summary.py make it; if they cannot, the bot says so in one line --
never silently. Additive: the delivery itself is untouched and happens first.
Usage: python3 patch_bot_cutsummary.py <dir with bot.py and dubsync_job.py>"""
import os
import sys

d = sys.argv[1]
J, B = os.path.join(d, "dubsync_job.py"), os.path.join(d, "bot.py")
sj, sb = open(J, encoding="utf-8").read(), open(B, encoding="utf-8").read()
if "make_cut_summary" in sj:
    raise SystemExit("already patched")


def rep(s, old, new, what):
    assert s.count(old) == 1, "anchor %s found %d times" % (what, s.count(old))
    return s.replace(old, new)


sj = rep(sj, '''def _contract_missing(st: dict, out) -> list:''', '''CUT_LIST = "/opt/dubsync2/tools/cut_list.py"
CUT_SUMMARY = "/opt/dubsync2/tools/cut_summary.py"


def pretty_name(fname: str) -> str:
    """'Half.Girlfriend.2017.1080p.NF.WEB-DL...mkv' -> 'Half Girlfriend (2017)'."""
    base = os.path.splitext(os.path.basename(fname))[0]
    base = re.sub(r"[._]+", " ", base).strip()
    base = re.sub(r"^(\\(.*?\\)|\\[.*?\\]|@\\S+)\\s*", "", base)   # a leading (tag) / [tag] / @channel word
    m = re.search(r"\\b(19|20)\\d{2}\\b", base)
    if m:
        name = base[:m.start()].strip(" -([")
        if name:
            return "%s (%s)" % (name, m.group(0))
    return base[:60]


async def make_cut_summary(title: str, name: str, stats: dict):
    """(text, picture path): what the dub removed from the HD, plain Somali + English with one
    numbered picture. (None, None) when it cannot be made; the reason is in stats."""
    try:
        intro = float(stats.get("hd_intro_s", 0.0) or 0.0)
        cj, img = OUT_DIR / f"{title}_cuts.json", OUT_DIR / f"{title}_cuts.jpg"
        p1 = await asyncio.create_subprocess_exec(
            DLG_PY, CUT_LIST, title, "--intro", "%.3f" % intro, "--json", str(cj),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        o1 = (await asyncio.wait_for(p1.communicate(), timeout=600))[0].decode("utf-8", "replace")
        if "CUT_LIST" not in o1 or not cj.exists():
            raise RuntimeError("cut list: " + o1.strip()[-160:])
        p2 = await asyncio.create_subprocess_exec(
            DLG_PY, CUT_SUMMARY, title, str(cj), str(img), name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        o2 = (await asyncio.wait_for(p2.communicate(), timeout=900))[0].decode("utf-8", "replace")
        lines = o2.splitlines()
        if not any(x.startswith("CUT_SUMMARY") for x in lines) or not img.exists():
            raise RuntimeError("summary: " + o2.strip()[-160:])
        body = "\\n".join("" if x == "---" else x for x in lines if not x.startswith("CUT_SUMMARY"))
        return body.strip(), str(img)
    except Exception as exc:
        stats["cut_summary_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
        return None, None


def _contract_missing(st: dict, out) -> list:''', "helpers")

sb = rep(sb, '''        if await _deliver_file(uid, entry, status, msgs[0]):
            _remove_pending(uid, saved)''', '''        if await _deliver_file(uid, entry, status, msgs[0]):
            # what the dub removed: plain Somali + English with a numbered picture (John's style)
            try:
                _nm = dubsync_job.pretty_name(hd_job["name"])
                _ct, _ci = await dubsync_job.make_cut_summary(title, _nm, res.stats)
                if _ct:
                    await msgs[0].reply(_ct[:4000])
                if _ci:
                    await msgs[0].reply_photo(_ci, caption="✂️ %s — where the Somali channel cut the film" % _nm)
                if not _ct:
                    await msgs[0].reply("✂️ Cut summary could not be made: %s"
                                        % str(res.stats.get("cut_summary_error", "unknown"))[:300])
            except Exception as _cse:
                log.warning("cut summary not sent for %s: %s", title, _cse)
            _remove_pending(uid, saved)''', "bot send")
open(J, "w", encoding="utf-8").write(sj)
open(B, "w", encoding="utf-8").write(sb)
print("patched", J, B)
