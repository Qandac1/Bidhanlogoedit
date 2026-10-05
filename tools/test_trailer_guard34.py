"""bot34 = the /trailer intake keeps its files (patch_bot_trailerguard34.py). Offline: fake messages; pyrogram's real
StopPropagation. Run inside the bot container:  python3 test_trailer_guard34.py <bot dir before (bot33)> <bot dir after>
  A. BEFORE (bot33): a prompt whose edit is refused lets the film fall through (the fault is real).
  B. AFTER: the same refusal -> the step is shown as a NEW message, the intake goes on, the film does not fall through;
     every later step works on the new message; a normal intake is prompt for prompt the one of before.
  C. AFTER: a step that breaks for any other reason -> the user is told, the film does not fall through.
  D. A file from someone who is NOT in the /trailer intake is not touched (it goes on to the bot's other flows).
  E. Nothing but _take / _take_step / _show changed.
Prints TRAILERGUARD34_TESTS ALL PASS."""
import asyncio
import importlib.util
import inspect
import os
import sys

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
    sys.modules[name] = mod                    # inspect.getsource of a CLASS looks its module up by name
    spec.loader.exec_module(mod)
    sys.path.remove(d)
    return mod


TB, T = load(BASE, "tf33"), load(NEW, "tf34")
UID = 4242


class U:
    def __init__(self, uid):
        self.id = uid


class F:
    def __init__(self, name, size=5_000_000, mime="video/mp4"):
        self.file_name, self.file_size, self.mime_type = name, size, mime


class Refused(Exception):
    pass


class Msg:
    def __init__(self, video=None, document=None, uid=UID, dead=False):
        self.from_user, self.video, self.document, self.caption = U(uid), video, document, None
        self.edits, self.replies, self.dead = [], [], dead

    async def reply(self, txt, reply_markup=None):
        m = Msg()
        m.first = txt
        self.replies.append((txt, reply_markup, m))
        return m

    async def edit(self, txt, reply_markup=None):
        if self.dead:
            raise Refused("Telegram says: [400 MESSAGE_ID_INVALID]")
        self.edits.append((txt, reply_markup))

    def stop_propagation(self):
        raise StopPropagation()


async def send(mod, m):
    """What pyrogram does with a handler: 'stopped' = the message goes no further; 'through' = the bot's other
    flows get it; 'error' = the handler broke (pyrogram logs it and the message goes on to the other groups)."""
    try:
        await mod._take(None, m)
        return "through"
    except StopPropagation:
        return "stopped"
    except Exception as exc:
        return "error:%s" % type(exc).__name__


def intake(mod, dead):
    prompt = Msg(dead=dead)
    mod._intake[UID] = {"step": "trailer", "trailer": None, "film": None, "orig": None, "subs": None, "movie_subs": None, "prompt": prompt}
    return prompt


async def main():
    started = []
    for mod in (TB, T):
        mod._start = lambda uid, _m=mod: started.append(_m._intake.pop(uid))

    # A: before
    pr = intake(TB, dead=True)
    r = await send(TB, Msg(video=F("trailer.mp4")))
    check("A: BEFORE, a refused prompt edit: the handler breaks and the trailer goes on to the bot's other flows (%s)" % r, r.startswith("error"), r)
    TB._intake.pop(UID, None)

    # B: after
    pr = intake(T, dead=True)
    v1 = Msg(video=F("trailer.mp4"))
    r = await send(T, v1)
    st = T._intake[UID]
    check("B: AFTER, the same refusal: the file stays with /trailer (%s)" % r, r == "stopped", r)
    check("B: the next step is shown as a NEW message (a reply to the file) and the intake goes on with it",
          len(v1.replies) == 1 and "Trailer received" in v1.replies[0][0] and "2/4" in v1.replies[0][0] and st["prompt"] is v1.replies[0][2]
          and st["step"] == "film" and st["trailer"] is v1, (v1.replies, st["step"]))
    new_prompt = st["prompt"]
    r2 = await send(T, Msg(video=F("somali.mp4")))
    r3 = await send(T, Msg(video=F("own.mkv")))
    check("B: the later steps edit that new message (film, then the film with its own sound)",
          r2 == "stopped" and r3 == "stopped" and len(new_prompt.edits) == 2 and new_prompt.edits[0][0] == T.ORIG_ASK
          and new_prompt.edits[1][0] == T.SUBS_ASK_FAST and T._intake[UID]["step"] == "subs", (r2, r3, new_prompt.edits))
    T._intake.pop(UID, None)

    # B: a normal intake, both files side by side
    seq = {}
    for name, mod in (("before", TB), ("after", T)):
        pr = intake(mod, dead=False)
        out = []
        for m in (Msg(video=F("trailer.mp4")), Msg(video=F("somali.mp4")), Msg(video=F("own.mkv")), Msg(document=F("t.srt", 900, "text/plain"))):
            out.append(await send(mod, m))
        # (a later bot may add one sentence to the step-2 prompt -- bot35: "If this trailer already exists in Somali ..."
        #  -- the steps, their order and their buttons are what this check is about)
        seq[name] = (out, [(t.split("\nIf this trailer already exists")[0], [[(b.text, b.callback_data) for b in row] for row in k.inline_keyboard])
                           for t, k in pr.edits], len(started))
        mod._intake.pop(UID, None)
    check("B: a normal intake is the one of before, prompt for prompt and button for button (%d edits)" % len(seq["after"][1]),
          seq["before"][:2] == seq["after"][:2] and seq["after"][0] == ["stopped"] * 4 and len(seq["after"][1]) == 3, seq)
    check("B: and it starts the job as before", len(started) == 2 and started[1].get("orig") is not None, len(started))

    # C: a step that breaks for another reason
    pr = intake(T, dead=False)
    real = T._is_video

    def broken(m):
        raise RuntimeError("boom")

    T._is_video = broken
    v = Msg(video=F("trailer.mp4"))
    r = await send(T, v)
    T._is_video = real
    check("C: a step that breaks: the file stays with /trailer and the user is told to send it again (%s)" % r,
          r == "stopped" and v.replies and "send the file again" in v.replies[0][0] and T._intake[UID]["step"] == "trailer", (r, v.replies))
    T._intake.pop(UID, None)

    # D: not in the intake
    r = await send(T, Msg(video=F("some film.mp4"), uid=777))
    check("D: a file from a user who is not in the /trailer intake goes on to the bot's other flows untouched (%s)" % r, r == "through", r)

    # E: what changed
    names = sorted(n for n, f in inspect.getmembers(TB, inspect.isfunction) if f.__module__ == TB.__name__)
    same = [n for n in names if hasattr(T, n) and inspect.getsource(getattr(TB, n)) == inspect.getsource(getattr(T, n))]
    diff = [n for n in names if n not in same]
    new = sorted(n for n, f in inspect.getmembers(T, inspect.isfunction) if f.__module__ == T.__name__ and n not in names)
    later = sorted(set(diff) - {"_take"}) + sorted(set(new) - {"_show", "_take_step"})
    check("E: of the %d functions of before _take differs, _show and _take_step are new%s"
          % (len(names), (" (a later bot's own changes, checked by its own test: %s)" % later) if later else ""),
          "_take" in diff and {"_show", "_take_step"} <= set(new) and set(diff) <= {"_take", "_start"}, (diff, new))
    cls_same = inspect.getsource(TB._Panel) == inspect.getsource(T._Panel)
    check("E: the panel class is untouched", cls_same)
    print("TRAILERGUARD34_TESTS " + ("ALL PASS" if ok else "FAILED"))


asyncio.run(main())
sys.exit(0 if ok else 1)
