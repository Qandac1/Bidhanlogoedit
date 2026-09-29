"""Proves patch_bot_panels (bot14) on the REAL bot.py handlers, driven with fake Telegram messages and
buttons (nothing is sent anywhere). Run INSIDE the bot container: python3 test_bot_panels.py <bot dir>
Each check is the exact scene of 2026-09-29 plus the flows that must stay as they were.
Prints PANELS_TESTS ALL PASS"""
import asyncio
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

D = sys.argv[1]
sys.path.insert(0, D)
os.chdir(D)
spec = importlib.util.spec_from_file_location("botmod", os.path.join(D, "bot.py"))
b = importlib.util.module_from_spec(spec)
sys.modules["botmod"] = b
spec.loader.exec_module(b)

UID = 424242                     # a test user: never John's id, so no real settings are touched
LOG, ENQ = [], []
ok = True


def check(name, cond, info=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  -- %s" % (info,)))
    ok &= bool(cond)


class FakeMsg:
    n = [900000]

    def __init__(self, text="", video=None):
        FakeMsg.n[0] += 1
        self.id = FakeMsg.n[0]
        self.text, self.caption, self.video, self.document, self.photo = text, None, video, None, None
        self.from_user = SimpleNamespace(id=UID)
        self.chat = SimpleNamespace(id=UID)
        self.reply_markup = None

    async def reply(self, text, reply_markup=None, **kw):
        r = FakeMsg(text)
        r.reply_markup = reply_markup
        LOG.append(("reply", r.id, text))
        return r

    async def edit(self, text, reply_markup=None, **kw):
        self.text, self.reply_markup = text, reply_markup
        LOG.append(("edit", self.id, text))
        return self

    async def edit_text(self, *a, **k):
        return await self.edit(*a, **k)

    async def edit_reply_markup(self, reply_markup=None, **k):
        self.reply_markup = reply_markup
        return self

    async def delete(self):
        pass


class FakeCQ:
    def __init__(self, data, message):
        self.data, self.message = data, message
        self.from_user = SimpleNamespace(id=UID)
        self.answers = []

    async def answer(self, text="", show_alert=False, **k):
        self.answers.append(text)


class FakeDQ:
    _q = []

    async def enqueue(self, uid, msgs, hd_i, brand, mode, title):
        self._q.append({"uid": uid, "state": "waiting"})
        return 1


def video(name):
    return FakeMsg(video=SimpleNamespace(file_name=name, width=1280, height=720, duration=8383,
                                         file_size=1787000000, mime_type="video/mp4"))


def buttons(m):
    return [x.callback_data for row in (m.reply_markup.inline_keyboard if m.reply_markup else []) for x in row]


b._allowed = lambda uid: True
b._enqueue = lambda uid, m: ENQ.append(m.id)
b._dq = FakeDQ()


def reset():
    for d in (b._dubflow, b._dubsel, b._pending, b._active, getattr(b, "_dubchoice", {})):
        d.pop(UID, None)
    LOG.clear()
    ENQ.clear()


async def start_a_dub_film():
    """/dub -> HD -> Somali dub -> Start, as John did for Aadyaa at 17:05"""
    await b._dubflow_start(UID, FakeMsg("/dub"))
    await b._on_video(None, video("Aadyaa HD.mkv"))
    await b._on_video(None, video("AADYAA FA SOMALI.mp4"))
    panel = b._dubsel[UID]["panel"]
    await b._cb(None, FakeCQ("dub:start", panel))


async def main():
    # 1. the 17:59 scene: a banner video after a dub film was started
    reset()
    await start_a_dub_film()
    check("after Start the 'Next movie?' intake is open", UID in b._dubflow, b._dubflow.get(UID))
    LOG.clear()
    v = video("QASRIGA SIRTA.mp4")
    await b._on_video(None, v)
    replies = [x for x in LOG if x[0] == "reply"]
    check("a video there gets a NEW visible message, not an edit far up",
          replies and "brand this video" in replies[-1][2], LOG)
    last = replies[-1][1] if replies else None
    check("it is NOT silently taken as a dub movie", b._dubflow.get(UID, {}).get("hd") is None, b._dubflow.get(UID))
    check("it is NOT sent to branding before John chooses", not ENQ, ENQ)
    # 2. John taps "Brand this video"
    choice = FakeMsg("choice")
    choice.id = last
    await b._cb(None, FakeCQ("dubflow:asbrand", choice))
    check("'Brand this video' sends THAT video to the banner flow", ENQ == [v.id], ENQ)
    check("... and closes the dub intake", UID not in b._dubflow, b._dubflow.get(UID))
    # 3. the other answer: it IS the next dub movie
    reset()
    await start_a_dub_film()
    hd2 = video("Next film HD.mkv")
    await b._on_video(None, hd2)
    ch = FakeMsg("choice")
    await b._cb(None, FakeCQ("dubflow:asdub", ch))
    check("'Next dub-sync movie' takes it as that movie's HD", b._dubflow.get(UID, {}).get("hd") is hd2, b._dubflow.get(UID))
    check("... the next step is asked on the visible message", "Somali dub" in (ch.text or ""), ch.text)
    await b._on_video(None, video("Next film SOMALI.mp4"))
    check("... its Somali dub then builds the dub panel (no second question)",
          UID in b._dubsel and len(b._dubsel[UID]["msgs"]) == 2, b._dubsel.get(UID))
    # 4. an explicit /dub is unchanged: files are taken directly
    reset()
    await b._dubflow_start(UID, FakeMsg("/dub"))
    h = video("Film HD.mkv")
    await b._on_video(None, h)
    check("/dub: the HD is taken directly, no question", b._dubflow.get(UID, {}).get("hd") is h and not ENQ,
          b._dubflow.get(UID))
    # 5. no dub state at all: a video goes straight to branding (unchanged)
    reset()
    v5 = video("plain.mp4")
    await b._on_video(None, v5)
    check("no dub state: straight to branding", ENQ == [v5.id], ENQ)
    # 6. the 18:26 scene: a leftover dub selection and a banner job
    reset()
    dubpanel = FakeMsg("dub panel")
    b._dubsel[UID] = {"msgs": [video("QASRIGA SIRTA.mp4"), video("QASRIGA SIRTA.mp4")], "hd_i": 0,
                      "brand": True, "panel": dubpanel, "mode": "conform", "named": None}
    job = {"name": "QASRIGA SIRTA.mp4", "duration": 8383.0, "w": 1280, "h": 720, "src": "", "work": "",
           "msg": video("QASRIGA SIRTA.mp4")}
    b._pending[UID] = job
    bannerpanel = FakeMsg("banner panel")
    await b._refresh_active_panel(FakeCQ("m:main", bannerpanel), UID, job)
    check("the BANNER panel stays a banner panel (no 'Ready to dub-sync')",
          "Ready to dub-sync" not in (bannerpanel.text or "") and "dub:start" not in buttons(bannerpanel),
          (bannerpanel.text or "")[:80])
    await b._refresh_active_panel(FakeCQ("m:main", dubpanel), UID, job)
    check("the dub panel's own message still redraws as the dub panel", "Ready to dub-sync" in (dubpanel.text or ""),
          (dubpanel.text or "")[:80])
    done = await b._cancel_everything(UID)
    check("/cancel clears the leftover dub selection", UID not in b._dubsel and any("dub-sync selection" in x for x in done),
          done)
    # 7. the 18:41 scene: /cancel during a scan that runs ffmpeg in a thread
    reset()
    w = tempfile.mkdtemp(prefix="bot14_job_")
    other = tempfile.mkdtemp(prefix="bot14_other_")
    p1 = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", w + "/pretrim.mp4"])
    p2 = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", other + "/pretrim.mp4"])
    b._act(UID).update(work=w, phase="Banner scan", proc=None, cancelled=False, task=None)
    done = await b._cancel_everything(UID)
    time.sleep(0.5)
    check("/cancel stops the scan's process (it registered no process)", p1.poll() is not None, done)
    check("/cancel says what it stopped", any("Banner scan cancelled" in x for x in done), done)
    check("a process in ANOTHER folder is untouched", p2.poll() is None)
    p2.kill()
    # 8. the scan registers its folder in the real render code
    src = open(os.path.join(D, "bot.py"), encoding="utf-8").read()
    check("the render's scan registers its job folder", '_act(uid).update(work=work, phase="Banner scan")' in src)


asyncio.run(main())
print("PANELS_TESTS", "ALL PASS" if ok else "FAILED")
