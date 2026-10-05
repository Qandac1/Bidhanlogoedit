"""bot33 = /trailer, THE FAST WAY (patch_bot_trailerfast33.py: trailer_flow.py). Offline: fake messages, a fake
engine (a small script that prints the build's real lines), temporary folders. Nothing is sent anywhere.
Run inside the bot container:  python3 test_trailer_fast33.py <bot dir before> <bot dir after>
  A. Intake: after the Somali film the optional step is offered; Skip gives the prompt of before, word for word,
     and the long way runs; a film with its own sound leads to the fast way (with or without trailer subtitles);
     subtitles sent straight away = the long way.
  B. The fast way with the engine's lines: a trailer is sent with the plain count and the times of the lines that
     stayed original; "no sound track carries the trailer's voices" and "too few lines" stop the engine at once
     and offer the long way; a refused pair, a crash and Cancel end cleanly; the engine is called with --orig.
  C. "The long way with these files" starts the flow of before with the same files.
  D. The long way's own code (_run, _auto, _question, _finish, _Panel) is untouched; the panel test still passes.
Prints TRAILERFAST33_TESTS ALL PASS."""
import asyncio
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time

BASE, NEW = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:700]), flush=True)
    ok &= bool(cond)


def load(d, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, "trailer_flow.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


TB, T = load(BASE, "tf_base"), load(NEW, "tf_new")
TMP = tempfile.mkdtemp(prefix="tf33_")
UID = 4242


class Stop(Exception):
    pass


class U:
    def __init__(self, uid):
        self.id = uid


class F:
    def __init__(self, name, size=5_000_000, mime="video/mp4"):
        self.file_name, self.file_size, self.mime_type = name, size, mime


class Msg:
    def __init__(self, video=None, document=None):
        self.from_user, self.video, self.document, self.caption = U(UID), video, document, None
        self.edits, self.replies = [], []
        Msg.n = getattr(Msg, "n", 100) + 1
        self.id = Msg.n

    async def reply(self, txt, reply_markup=None):
        m = Msg()
        m.first = txt
        self.replies.append((txt, reply_markup, m))
        return m

    async def edit(self, txt, reply_markup=None):
        self.edits.append((txt, reply_markup))

    def stop_propagation(self):
        raise Stop()

    async def download(self, file_name=None):
        open(file_name, "w").write("1\n00:00:01,000 --> 00:00:03,000\nYou are the one and I will be there with you\n\n"
                                   "2\n00:00:04,000 --> 00:00:06,000\nWhat do you want from me and my family\n")
        return file_name


class CQ:
    def __init__(self, data, message):
        self.from_user, self.data, self.message, self.answers = U(UID), data, message, []

    async def answer(self, txt="", show_alert=False):
        self.answers.append(txt)

    def stop_propagation(self):
        pass


class App:
    def __init__(self):
        self.videos, self.msgs = [], []

    async def send_video(self, uid, path, supports_streaming=True, progress=None, caption=""):
        if progress:
            await progress(1, 2)
        self.videos.append((path, caption))

    async def send_message(self, uid, txt, **kw):
        m = Msg()
        self.msgs.append(txt)
        return m


async def call(coro):
    try:
        await coro
    except Stop:
        pass


def buttons(rm):
    return [(b.text, b.callback_data) for row in rm.inline_keyboard for b in row] if rm else []


async def build_job(uid, m, status, prog=None, key=None):
    return {"src": "/x/%s" % (m.video or m.document).file_name, "duration": 6000.0}


started = []


async def fake_run(uid, st):
    started.append(("long", dict(st)))


async def fake_fast(uid, st):
    started.append(("fast", dict(st)))


async def intake(mod, steps):
    """Drive the intake; returns the prompt message (its .edits) and what was started."""
    app = App()
    mod._deps.update(app=app, allowed=lambda u: True, build_job=build_job, busy=lambda: False)
    mod._intake.clear()
    started.clear()
    keep = (mod._run, getattr(mod, "_run_fast", None))
    mod._run = fake_run
    if keep[1]:
        mod._run_fast = fake_fast
    cmd = Msg()
    await call(mod._cmd(None, cmd))
    prompt = cmd.replies[0][2]
    for kind, val in steps:
        if kind == "video":
            await call(mod._take(None, Msg(video=F(val))))
        elif kind == "srt":
            await call(mod._take(None, Msg(document=F(val, 2000, "application/x-subrip"))))
        elif kind == "btn":
            await call(mod._cb(None, CQ(val, prompt)))
        await asyncio.sleep(0.05)
    mod._run = keep[0]
    if keep[1]:
        mod._run_fast = keep[1]
    return cmd, prompt, list(started)


async def main():
    # ---- A. intake --------------------------------------------------------------------------------------------------
    cmd, pr, st = await intake(T, [("video", "trailer.mp4"), ("video", "somali.mp4")])
    check("A: after the Somali film the optional step is offered, with a Skip button",
          pr.edits and "Fast way (optional)" in pr.edits[-1][0] and ("⏭ Skip", "trl:noorig") in buttons(pr.edits[-1][1]), pr.edits[-1:])
    _c, pb, _s = await intake(TB, [("video", "trailer.mp4"), ("video", "somali.mp4")])
    cmd, pr, st = await intake(T, [("video", "trailer.mp4"), ("video", "somali.mp4"), ("btn", "trl:noorig")])
    check("A: Skip -> the prompt of before, word for word, with its No subtitles button",
          pr.edits[-1][0] == pb.edits[-1][0] and buttons(pr.edits[-1][1]) == buttons(pb.edits[-1][1]), (pr.edits[-1][0], pb.edits[-1][0]))
    seq = [("btn", "trl:nosubs"), ("btn", "trl:nomovie")]
    _c, pb2, sb = await intake(TB, [("video", "trailer.mp4"), ("video", "somali.mp4")] + seq)
    cmd, pr, st = await intake(T, [("video", "trailer.mp4"), ("video", "somali.mp4"), ("btn", "trl:noorig")] + seq)
    check("A: ... and the long way starts exactly as before (same prompts after it, the old _run, no film with its own sound)",
          [e[0] for e in pr.edits[-1:]] == [e[0] for e in pb2.edits[-1:]] and len(st) == 1 and st[0][0] == "long" and st[0][1].get("orig") is None
          and len(sb) == 1 and sb[0][0] == "long", (st, pr.edits[-1:]))
    cmd, pr, st = await intake(T, [("video", "trailer.mp4"), ("video", "somali.mp4"), ("video", "hd_tamil.mkv")])
    check("A: a film with its own sound -> asks only for the trailer's subtitles (any language) or No subtitles",
          "Film with its own sound received" in pr.edits[-1][0] and ("⏭ No subtitles", "trl:nosubs") in buttons(pr.edits[-1][1]) and not st, pr.edits[-1:])
    cmd, pr, st = await intake(T, [("video", "trailer.mp4"), ("video", "somali.mp4"), ("video", "hd_tamil.mkv"), ("btn", "trl:nosubs")])
    check("A: ... No subtitles -> the FAST way starts, with the three files",
          len(st) == 1 and st[0][0] == "fast" and st[0][1]["orig"].video.file_name == "hd_tamil.mkv" and st[0][1]["subs"] is None, st)
    cmd, pr, st = await intake(T, [("video", "trailer.mp4"), ("video", "somali.mp4"), ("video", "hd_tamil.mkv"), ("srt", "trailer.ta.srt")])
    check("A: ... trailer subtitles -> the FAST way starts with them", len(st) == 1 and st[0][0] == "fast" and st[0][1]["subs"] is not None, st)
    cmd, pr, st = await intake(T, [("video", "trailer.mp4"), ("video", "somali.mp4"), ("srt", "trailer.en.srt")])
    _c, pb3, _s = await intake(TB, [("video", "trailer.mp4"), ("video", "somali.mp4"), ("srt", "trailer.en.srt")])
    check("A: subtitles sent straight away (no Skip) = the long way: the movie-subtitles prompt of before",
          pr.edits[-1][0] == pb3.edits[-1][0] and not st and T._intake[UID]["step"] == "movie_subs", (pr.edits[-1][0][:120], pb3.edits[-1][0][:120]))

    # ---- B. the fast way -----------------------------------------------------------------------------------------------
    eng = os.path.join(TMP, "fake_engine.py")
    open(eng, "w").write('''
import json, os, sys, time
a = sys.argv[1:]
open(os.environ["FAKE_ARGV"], "w").write(json.dumps(a))
mode = os.environ.get("FAKE", "ok")
out = a[a.index("--out") + 1]
rep = a[a.index("--report") + 1]
print("picture: 68% of the trailer found in the Somali film")
if mode == "refused":
    print("REFUSED: only 5% of the trailer's picture is in this Somali film - wrong film or wrong episodes?"); sys.exit(1)
if mode in ("text", "textonly"):                      # the engine's real lines of Agent 2023 (2026-10-05)
    print("listening to the trailer's lines (the film has English subtitles)")
    print("trailer language: te")
    print("[sound] film track a:0: 1 of 29 lines clear, 1 found")
    if mode == "text":
        print("[sound] film track a:1: 8 of 29 lines clear, 9 found")
        print("[sound] 2 more by the full mix (each backed by the voice or by a found neighbour)")
        print("[text] line 29: sound named 2303.4 s, the words are at 4387.7 s (meaning 0.97) -- sound heard the music")
    time.sleep(1.5)
    print("[text] 7 lines placed by what is said (the film's own recording heard at 0 of them)")
    if mode == "textonly":
        print("[sound] the film's sound tracks do not hold the trailer's recording; its lines are placed by what is said")
    time.sleep(1.5)
    print("sound chain: %d of 30 lines proven (film track a:%d)" % ((18, 1) if mode == "text" else (9, -1)))
    n_s, n_t = (11, 7) if mode == "text" else (0, 7)       # (the chain's count is over the cue lines, the report's over the built lines)
    lines = ([{"t0": 3.0 * i, "t1": 3.0 * i + 2, "status": "placed", "why": "sound (clear, likeness 0.66) + picture (clear, margin +0.62)"} for i in range(n_s)]
             + [{"t0": 40 + 3.0 * i, "t1": 42 + 3.0 * i, "status": "placed", "why": "text (meaning 0.96, +0.52 clear) + picture (clear, margin +0.69)"} for i in range(n_t)]
             + [{"t0": 70.0, "t1": 71.0, "status": "placed", "why": "on-screen"}]
             + [{"t0": t, "t1": t + 1, "status": "unresolved", "why": "voice-over / unmatched picture"} for t in (44.5, 66.6, 128.0)])
    json.dump({"lines": lines, "lines_placed": n_s + n_t + 1}, open(rep, "w"))
    open(out, "wb").write(b"x" * 4000000)
    print("Somali lines placed: %d of %d" % (n_s + n_t + 1, len(lines)))
    sys.exit(0)
print("[sound] film track a:0: 0 of 41 lines clear, 0 found")
if mode == "nosound":
    print("[sound] no sound track of this film carries the trailer's recording -- the chain proves nothing here")
    time.sleep(60); sys.exit(0)
print("[sound] film track a:1: 24 of 41 lines clear, 37 found")
if mode == "few":
    print("sound chain: 2 of 41 lines proven (film track a:1)"); time.sleep(60); sys.exit(0)
print("sound chain: 37 of 41 lines proven (film track a:1)")
if mode == "slow":
    time.sleep(60)
if mode == "crash":
    print("Traceback: boom"); sys.exit(2)
print("speech lines: 41 | on proven picture: 39")
lines = [{"t0": 2.0 * i, "t1": 2.0 * i + 1.5, "status": "placed", "why": "sound (clear, likeness 0.7) + picture (clear, margin +0.2)"} for i in range(38)] + [{"t0": t, "t1": t + 1, "status": "unresolved"} for t in (73.7, 118.2, 157.3)]
json.dump({"lines": lines, "lines_placed": 38}, open(rep, "w"))
open(out, "wb").write(b"x" * 4000000)
print("Somali lines placed: 38 of 41 (95% of the speech) | 330 s")
''')
    T.ENGINE = [sys.executable, eng]
    T.JOBS = __import__("pathlib").Path(TMP) / "jobs"
    os.environ["FAKE_ARGV"] = os.path.join(TMP, "argv.json")

    async def fast(mode, subs=False, cancel_after=None):
        os.environ["FAKE"] = mode
        app = App()
        T._deps.update(app=app, allowed=lambda u: True, build_job=build_job, busy=lambda: False)
        T._cancelled.discard(UID)
        prompt = Msg()
        st = {"trailer": Msg(video=F("Jigarthanda trailer.mp4")), "film": Msg(video=F("somali.mp4")),
              "orig": Msg(video=F("hd_tamil.mkv")), "subs": Msg(document=F("t.srt", 900, "text/plain")) if subs else None,
              "movie_subs": None, "prompt": prompt}
        t0 = time.time()
        task = asyncio.get_event_loop().create_task(T._run_fast(UID, st))
        if cancel_after:
            await asyncio.sleep(cancel_after)
            await call(T._cb(None, CQ("trl:cancel", prompt)))
        await asyncio.wait_for(task, 40)
        return app, prompt, time.time() - t0

    app, pr, el = await fast("ok", subs=True)
    argv = json.load(open(os.environ["FAKE_ARGV"]))
    cap = app.videos[0][1] if app.videos else ""
    check("B: the engine is called as `build` with the three files, --orig, the report and the trailer's subtitles",
          argv[0] == "build" and argv[argv.index("--orig") + 1] == "/x/hd_tamil.mkv" and argv[argv.index("--film") + 1] == "/x/somali.mp4"
          and argv[argv.index("--trailer") + 1] == "/x/Jigarthanda trailer.mp4" and "--report" in argv and "--subs" in argv, argv)
    check("B: the trailer is sent with a plain count and the times of the lines that stayed original",
          len(app.videos) == 1 and "38 of the trailer's 41 lines** (38 by their sound)" in cap and "Still original (3): 1:13, 1:58, 2:37." in cap
          and "Picture identical" in cap, cap)
    txts = " || ".join(e[0] for e in pr.edits)
    check("B: the panel showed the stages (downloads, finding the lines with its count, build, send)",
          "Find every line (by sound, then by words)" in txts and "37 of 41 lines found" in txts and "Build the Somali trailer" in txts and "Send it to you" in txts, txts[-600:])
    app, pr, el = await fast("ok")
    check("B: without trailer subtitles the engine gets no --subs", "--subs" not in json.load(open(os.environ["FAKE_ARGV"])) and len(app.videos) == 1)
    app, pr, el = await fast("text")
    cap = app.videos[0][1] if app.videos else ""
    txts = " || ".join(e[0] for e in pr.edits)
    check("B2: lines found by their WORDS (Agent's real engine lines): the trailer is sent, the caption counts sound, words and picture",
          len(app.videos) == 1 and "19 of the trailer's 22 lines** (11 by their sound, 7 by their words, 1 by the picture)" in cap
          and "Still original (3): 0:44, 1:06, 2:08." in cap, cap)
    check("B2: the panel said what it was doing (listening to the trailer, then how many lines the words placed, then the count)",
          "listening to the trailer's lines" in txts and "7 lines placed by what is said" in txts and "18 of 30 lines found" in txts, txts[-900:])
    app, pr, el = await fast("textonly")
    cap = app.videos[0][1] if app.videos else ""
    check("B2: a film file WITHOUT the trailer's voices but with subtitles: not stopped -- the trailer is sent (7 by their words, 1 by the picture)",
          len(app.videos) == 1 and "8 of the trailer's 11 lines** (7 by their words, 1 by the picture)" in cap and UID not in T._fast, (cap, pr.edits[-1:]))
    for mode, words in (("nosound", "not be found in that film file"), ("few", "Only **2 of 41**")):
        app, pr, el = await fast(mode)
        last = pr.edits[-1] if pr.edits else ("", None)
        check("B: '%s' -> the engine is stopped at once (%.1f s), nothing is sent, the long way is offered" % (mode, el),
              not app.videos and words in last[0] and ("🔁 The long way with these files", "trl:long") in buttons(last[1]) and el < 15 and UID in T._fast,
              (el, last[0][:200], buttons(last[1])))
    app, pr, el = await fast("refused")
    check("B: a refused pair -> its reason, nothing sent", not app.videos and "⛔" in pr.edits[-1][0] and "wrong film" in pr.edits[-1][0], pr.edits[-1:])
    app, pr, el = await fast("crash")
    check("B: a crash of the engine -> a plain failure line, nothing sent", not app.videos and "❌" in pr.edits[-1][0], pr.edits[-1:])
    app, pr, el = await fast("slow", cancel_after=3.0)
    check("B: Cancel stops a running build within seconds (%.1f s), nothing sent" % el, not app.videos and el < 15 and "cancelled" in pr.edits[-1][0].lower(), (el, pr.edits[-1:]))

    # ---- C. the long way with the same files ------------------------------------------------------------------------------
    app, pr, el = await fast("nosound")
    started.clear()
    keep = T._run
    T._run = fake_run
    cq = CQ("trl:long", pr)
    await call(T._cb(None, cq))
    await asyncio.sleep(0.05)
    T._run = keep
    check("C: 'The long way with these files' starts the flow of before with the trailer and the Somali film (no film with its own sound)",
          len(started) == 1 and started[0][0] == "long" and started[0][1]["trailer"].video.file_name == "Jigarthanda trailer.mp4"
          and started[0][1]["film"].video.file_name == "somali.mp4" and started[0][1].get("orig") is None and UID not in T._fast, started)
    cq2 = CQ("trl:long", pr)
    await call(T._cb(None, cq2))
    check("C: a second tap does nothing", len(started) == 1 and cq2.answers and "ended" in cq2.answers[-1])

    # ---- D. the long way's code is untouched --------------------------------------------------------------------------------
    same = [n for n in ("_run", "_auto", "_question", "_finish", "_Panel", "_prep_line", "_ask_engine", "_srt_is_english", "register")
            if inspect.getsource(getattr(TB, n)) == inspect.getsource(getattr(T, n))]
    check("D: _run, _auto, _question, _finish, _Panel, _prep_line, _ask_engine, _srt_is_english, register are untouched (%d of 9)" % len(same), len(same) == 9, same)
    pt = os.path.join(BASE, "test_trailer_panel.py")
    if os.path.exists(pt):
        r = subprocess.run([sys.executable, pt, NEW], capture_output=True, text=True)
        check("D: the panel test of before passes on the new file (%s)" % (r.stdout.strip().splitlines() or ["?"])[-1][:60], r.returncode == 0, r.stderr[-300:])


asyncio.get_event_loop().run_until_complete(main())
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("TRAILERFAST33_TESTS " + ("ALL PASS" if ok else "FAILED"))
sys.exit(0 if ok else 1)
