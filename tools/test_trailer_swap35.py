"""bot35 = /trailer takes the trailer's own Somali version (patch_bot_trailerswap35.py). Offline: fake messages, a fake
engine that prints the real `swap` lines, temporary folders; pyrogram's real StopPropagation. Nothing is sent.
Run inside the bot container:  python3 test_trailer_swap35.py <bot dir before (bot34)> <bot dir after>
  A. Which second video is "the trailer in Somali"? Only one about as long as the trailer. A film, a video of
     another length, a file without a length: the flow of before (the same prompt as the file of before gives).
  B. The swap: the engine is called as `swap` with the two files; the result is sent with a plain caption; the panel
     shows its stages.
  C. Refused by the engine (not the same trailer): nothing sent, the reason shown, the intake back at step 2 with
     the trailer kept -- the film sent next goes the way of before.
  D. A crash and Cancel end cleanly.
  E. Only _take_step and _start changed; new: the swap's own functions.
Prints TRAILERSWAP35_TESTS ALL PASS."""
import asyncio
import importlib.util
import inspect
import json
import os
import sys
import tempfile
import time

from pyrogram import StopPropagation

BASE, NEW = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:600]), flush=True)
    ok &= bool(cond)


def load(d, name):
    sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, "trailer_flow.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    sys.path.remove(d)
    return mod


TB, T = load(BASE, "tf34"), load(NEW, "tf35")
TMP = tempfile.mkdtemp(prefix="tf35_")
UID = 4242


class U:
    def __init__(self, uid):
        self.id = uid


class F:
    def __init__(self, name, size=5_000_000, mime="video/mp4", duration=None):
        self.file_name, self.file_size, self.mime_type = name, size, mime
        if duration is not None:
            self.duration = duration


class Msg:
    def __init__(self, video=None, document=None):
        self.from_user, self.video, self.document, self.caption = U(UID), video, document, None
        self.edits, self.replies = [], []

    async def reply(self, txt, reply_markup=None):
        m = Msg()
        self.replies.append((txt, reply_markup, m))
        return m

    async def edit(self, txt, reply_markup=None):
        self.edits.append((txt, reply_markup))

    def stop_propagation(self):
        raise StopPropagation()


class CQ:
    def __init__(self, data, message):
        self.from_user, self.data, self.message, self.answers = U(UID), data, message, []

    async def answer(self, txt="", show_alert=False):
        self.answers.append(txt)

    def stop_propagation(self):
        pass


class App:
    def __init__(self):
        self.videos = []

    async def send_video(self, uid, path, supports_streaming=True, progress=None, caption=""):
        if progress:
            await progress(1, 2)
        self.videos.append((path, caption))


async def send(mod, m):
    try:
        await mod._take(None, m)
        return "through"
    except StopPropagation:
        return "stopped"


def buttons(rm):
    return [(b.text, b.callback_data) for row in rm.inline_keyboard for b in row] if rm else []


async def build_job(uid, m, status, prog=None, key=None):
    return {"src": "/x/%s" % (m.video or m.document).file_name, "duration": 134.0}


def intake(mod):
    prompt = Msg()
    mod._intake[UID] = {"step": "trailer", "trailer": None, "film": None, "orig": None, "subs": None, "movie_subs": None, "prompt": prompt}
    return prompt


async def main():
    # ---- A
    started = {"swap": [], "fast": [], "long": []}

    async def fake_swap(uid, st):
        started["swap"].append(st)

    async def fake_fast(uid, st):
        started["fast"].append(st)

    async def fake_long(uid, st):
        started["long"].append(st)

    real = (T._run_swap, T._run_fast, T._run)
    T._run_swap, T._run_fast, T._run = fake_swap, fake_fast, fake_long
    TR = Msg(video=F("Agent trailer.mp4", duration=134))
    pr = intake(T)
    await send(T, TR)
    check("A: the step-2 prompt names both ways (the Somali film, or the trailer in Somali)",
          "Now send the **Somali film**" in pr.edits[-1][0] and "already exists in Somali" in pr.edits[-1][0], pr.edits[-1:])
    r = await send(T, Msg(video=F("Agent somali trailer.mp4", duration=132)))
    await asyncio.sleep(0)
    check("A: a second video about as long as the trailer (132 s of 134) = the trailer in Somali -> the swap starts, no further question",
          r == "stopped" and len(started["swap"]) == 1 and started["swap"][0]["somali_trailer"] is not None and started["swap"][0]["trailer"] is TR
          and UID not in T._intake and not started["fast"] and not started["long"], (r, started))
    cases = (("a film (9342 s)", F("somali film.mp4", 1_500_000_000, duration=9342)), ("a 60-s clip (the trailer is 134 s)", F("clip.mp4", duration=60)),
             ("a file without a length", F("somali film.mkv", 1_500_000_000, "video/x-matroska")))
    for name, f in cases:
        seqs = []
        for mod in (TB, T):
            pr = intake(mod)
            await send(mod, Msg(video=F("Agent trailer.mp4", duration=134)))
            rr = await send(mod, Msg(video=f))
            seqs.append((rr, pr.edits[-1][0], buttons(pr.edits[-1][1]), mod._intake[UID]["step"]))
            mod._intake.pop(UID, None)
        check("A: %s -> the Somali FILM, the way of before (the same next prompt as the file of before gives)" % name,
              seqs[0] == seqs[1] and seqs[1][3] == "orig" and len(started["swap"]) == 1, seqs)
    check("A: 'about as long' = within 20 s or a quarter of the trailer (134 s: 100.5..167.5; 30-s teaser: 10..50)",
          T._is_somali_trailer(Msg(video=F("t", duration=134)), Msg(video=F("s", duration=101))) and not T._is_somali_trailer(Msg(video=F("t", duration=134)), Msg(video=F("s", duration=100)))
          and T._is_somali_trailer(Msg(video=F("t", duration=30)), Msg(video=F("s", duration=50))) and not T._is_somali_trailer(Msg(video=F("t", duration=30)), Msg(video=F("s", duration=51)))
          and not T._is_somali_trailer(Msg(video=F("t")), Msg(video=F("s", duration=134))))
    T._run_swap, T._run_fast, T._run = real

    # ---- B: the swap with a fake engine that prints the engine's real lines (Agent, 2026-10-05)
    eng = os.path.join(TMP, "fake_engine.py")
    open(eng, "w").write("""import json, os, sys, time
a = sys.argv[1:]
open(os.environ["FAKE_ARGV"], "w").write(json.dumps(a))
mode = os.environ.get("FAKE", "ok")
out, rep = a[a.index("--out") + 1], a[a.index("--report") + 1]
print("the Somali trailer's colour tag was unreadable for ffmpeg: re-wrapped (no re-encode)")
if mode == "refused":
    print("REFUSED: the two videos do not show the same picture (0 places agree; a trailer under 40 s is too short to compare)"); sys.exit(3)
print("picture: the Somali trailer is the official one moved by -2.50 s (27 places, -2.50 .. -2.40)")
time.sleep(1.2)
print("sound: the same music in 18 windows -> offset -2.6822 s (range 77 ms); the Somali trailer plays it at 0.48 x the official level")
if mode == "slow":
    time.sleep(60)
if mode == "crash":
    print("Traceback: boom"); sys.exit(2)
json.dump({"offset": -2.6822, "somali_from": 3.18, "somali_to": 134.07, "seconds": 134.07, "picture_same": True}, open(rep, "w"))
open(out, "wb").write(b"x" * 3000000)
print("built: picture the official trailer's (md5), the Somali trailer's sound from 3.18 to 134.07 s, lag head / middle / tail +0 / +0 / +0 ms")
print("SWAPPED offset=-2.682 somali_from=3.18 somali_to=134.07 seconds=134.07")
""")
    T.ENGINE = [sys.executable, eng]
    T.JOBS = __import__("pathlib").Path(TMP) / "jobs"
    os.environ["FAKE_ARGV"] = os.path.join(TMP, "argv.json")

    async def swap(mode, cancel_after=None):
        os.environ["FAKE"] = mode
        app = App()
        T._deps.update(app=app, allowed=lambda u: True, build_job=build_job, busy=lambda: False)
        T._cancelled.discard(UID)
        T._intake.pop(UID, None)
        prompt = Msg()
        st = {"trailer": Msg(video=F("Agent trailer.mp4", duration=134)), "somali_trailer": Msg(video=F("Agent somali trailer.mp4", duration=132)),
              "film": None, "orig": None, "subs": None, "movie_subs": None, "prompt": prompt}
        t0 = time.time()
        task = asyncio.get_event_loop().create_task(T._run_swap(UID, st))
        if cancel_after:
            await asyncio.sleep(cancel_after)
            try:
                await T._cb(None, CQ("trl:cancel", prompt))
            except StopPropagation:
                pass
        await asyncio.wait_for(task, 40)
        return app, prompt, st, time.time() - t0

    app, pr, st, el = await swap("ok")
    argv = json.load(open(os.environ["FAKE_ARGV"]))
    cap = app.videos[0][1] if app.videos else ""
    check("B: the engine is called as `swap` with the official trailer, the Somali version, the output and a report",
          argv[0] == "swap" and argv[argv.index("--trailer") + 1] == "/x/Agent trailer.mp4" and argv[argv.index("--somali") + 1] == "/x/Agent somali trailer.mp4"
          and "--out" in argv and "--report" in argv, argv)
    check("B: the result is sent with a plain caption (whose sound, how far it was moved, the picture, the first seconds)",
          len(app.videos) == 1 and "own sound" in cap and "moved -2.68 s" in cap and "official trailer, untouched" in cap and "The first 3.2 s are the official trailer's own sound" in cap, cap)
    txts = " || ".join(e[0] for e in pr.edits)
    check("B: the panel showed the stages (two downloads, the swap with what it found, the sending)",
          "Download the Somali trailer" in txts and "Put its real sound on the clean picture" in txts and "Send it to you" in txts
          and ("the same picture" in txts or "its sound placed on the picture" in txts), txts[-700:])

    # ---- C
    app, pr, st, el = await swap("refused")
    last = pr.edits[-1][0] if pr.edits else ""
    check("C: refused by the engine -> nothing sent, the reason shown, and the ask for the Somali FILM",
          not app.videos and "not this trailer in Somali" in last and "do not show the same picture" in last and "Send the **Somali film**" in last, last)
    back = T._intake.get(UID)
    check("C: the intake is back at step 2 with the trailer kept", bool(back) and back["step"] == "film" and back["trailer"] is st["trailer"] and back["prompt"] is pr, back)
    r = await send(T, Msg(video=F("somali film.mp4", 1_500_000_000, duration=9342)))
    check("C: the film sent next goes the way of before (the optional step with its Skip button)",
          r == "stopped" and T._intake[UID]["step"] == "orig" and pr.edits[-1][0] == T.ORIG_ASK and ("⏭ Skip", "trl:noorig") in buttons(pr.edits[-1][1]), pr.edits[-1:])
    T._intake.pop(UID, None)

    # ---- D
    app, pr, st, el = await swap("crash")
    check("D: a crash of the engine -> a plain failure line, nothing sent", not app.videos and "❌" in pr.edits[-1][0] and UID not in T._intake, pr.edits[-1:])
    app, pr, st, el = await swap("slow", cancel_after=3)
    check("D: Cancel stops a running swap within seconds (%.1f s), nothing sent" % el, not app.videos and el < 15 and "cancelled" in pr.edits[-1][0].lower(), (el, pr.edits[-1:]))

    # ---- E
    names = sorted(n for n, f in inspect.getmembers(TB, inspect.isfunction) if f.__module__ == TB.__name__)
    diff = [n for n in names if not hasattr(T, n) or inspect.getsource(getattr(TB, n)) != inspect.getsource(getattr(T, n))]
    new = sorted(n for n, f in inspect.getmembers(T, inspect.isfunction) if f.__module__ == T.__name__ and n not in names)
    check("E: of the %d functions of before only _take_step and _start differ (%s); new: %s" % (len(names), diff, new),
          diff == ["_start", "_take_step"] and new == ["_is_somali_trailer", "_run_swap", "_seconds", "swap_caption"], (diff, new))
    check("E: the panel class is untouched", inspect.getsource(TB._Panel) == inspect.getsource(T._Panel))
    print("TRAILERSWAP35_TESTS " + ("ALL PASS" if ok else "FAILED"))


asyncio.run(main())
sys.exit(0 if ok else 1)
