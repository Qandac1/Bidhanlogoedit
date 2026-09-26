"""/trailer progress panel, offline: fake message + fake clock, the engine's real output
lines fed through trailer_flow._prep_line.  Checks: stages tick in order, the overall bar
never goes backwards, a stage without numbers stops at 90 %, the film transcript moves
on real chunk lines, cached films skip it, time left is sane, finish panel ends at 100 %.
Run: /opt/media-os/venv/bin/python test_trailer_panel.py [dir with trailer_flow.py]"""
import asyncio
import re
import sys

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/opt/Bidhanlogoedit")
import trailer_flow as T  # noqa: E402

NOW = [1000.0]
T.time.time = lambda: NOW[0]


class Msg:
    def __init__(self):
        self.texts = []

    async def edit(self, txt, reply_markup=None):
        self.texts.append(txt)


def overall(txt):
    return float(re.search(r"\*\*Overall\*\* `[▰▱]+\s+(\d+)%`", txt).group(1))


async def prep(cached: bool, dur: float):
    m = Msg()
    p = T._Panel(m, "AGENT Trailer (Telugu)", T.PREP_STAGES)
    p.optional.add("lines")
    seen = []

    async def feed(line, dt=0.0):
        NOW[0] += dt
        await T._prep_line(p, line, dur)
        await p.draw(force=True)
        seen.append(m.texts[-1])

    p.begin("dl_trailer")
    await p.set("dl_trailer", 50, "20/40 MB")
    NOW[0] += 5
    await p.set("dl_trailer", 100)
    p.done("dl_trailer")
    p.begin("dl_film")
    for k in range(1, 11):
        NOW[0] += 12
        await p.set("dl_film", 10 * k, "%d/1400 MB" % (140 * k), force=True)
        seen.append(m.texts[-1])
    p.done("dl_film", "%d min film" % (dur // 60))
    p.exp["text"] = max(dur, 600) * T.TEXT_S_PER_FILM_S
    p.begin("shots")
    await feed("FILM cached=%d" % cached)
    await feed("STEP Finding the trailer's shots in the Somali film")
    await feed("", 60)
    await feed("", 600)                                        # far past its typical length
    assert "`▰▰▰▰▰▰▰▰▰▰▰▱   90%`" in seen[-1], seen[-1]       # stops at 90 %, not "done"
    await feed("STEP Somali transcript of the film (cached after the first time)", 5)
    assert "✅ Find the trailer's shots" in seen[-1]
    if cached:
        await feed("STEP film transcript: cached (somtext_abc)", 1)
        assert "✅ Somali transcript of the film  · already made for this film" in seen[-1], seen[-1]
    else:
        await feed("STEP film transcript: separating the Somali voice (about 12 min per hour of film)")
        n = int(-(-dur // 600))
        for k in range(n):
            await feed("chunk %d (%d-%d s): 80 spoken lines | %d s elapsed" % (k, 600 * k, min(dur, 600 * (k + 1)),
                                                                              150 * (k + 1)), 150)
        a_end = overall(seen[-1])
        await feed("STEP film transcript: Somali text + English (about 7 min per hour of film)")
        for k in range(n):
            await feed("transcript chunk %03d: 90 lines (70 with words) | 400 s of speech in %d s" % (k, 60 * k), 90)
        assert "part 2/2" in seen[-1] and overall(seen[-1]) >= a_end
    await feed("STEP Placing the lines that are proven", 3)
    await feed("", 60)
    await feed("STEP Making the listening clips", 100)
    assert "✅ Place the proven lines" in seen[-1] and "⏳ **Listening clips**" in seen[-1], seen[-1]
    ov = [overall(t) for t in seen]
    assert all(b >= a for a, b in zip(ov, ov[1:])), ov      # never backwards
    assert "Listen to the trailer" not in seen[-1]           # English subtitles: stage hidden
    p.close()
    return seen


async def listen_path():
    """Non-English subtitles -> the engine listens to the trailer: that stage appears."""
    m = Msg()
    p = T._Panel(m, "t", T.PREP_STAGES)
    p.optional.add("lines")
    p.begin("shots")
    await T._prep_line(p, "STEP The trailer subtitles are not English (auto-captions?) - listening to the trailer instead", 0)
    await T._prep_line(p, "STEP Listening to the trailer's lines", 0)
    await T._prep_line(p, "STEP trailer language: te", 0)
    await p.draw(force=True)
    t = m.texts[-1]
    assert "⏳ **Listen to the trailer's lines**  · language: te" in t, t
    p.close()


async def finish():
    m = Msg()
    p = T._Panel(m, "t", T.FINISH_STAGES, cancel=False)
    for k in range(1, 41):
        NOW[0] += 0.2
        await p.set("best", 100 * k / 40, "line %d of 20" % ((k + 1) // 2), force=True)
    p.done("best")
    p.begin("build")
    NOW[0] += 60
    await p.draw(force=True)
    assert "⏳ **Build the Somali trailer**" in m.texts[-1]
    p.done("build")
    p.begin("send")
    for k in range(1, 6):
        NOW[0] += 5
        await p.set("send", 20 * k, "%d / 55 MB" % (11 * k), force=True)
    p.done("send")
    await p.draw(force=True)
    assert overall(m.texts[-1]) == 100 and "finished" in m.texts[-1], m.texts[-1]
    p.close()
    return m.texts


async def main():
    un = await prep(False, 9600)
    ca = await prep(True, 9600)
    await listen_path()
    fin = await finish()
    print("---- uncached film, during the transcript ----")
    print(next(t for t in un if "part 1/2" in t and "chunk" not in t and overall(t) > 30))
    print("---- cached film, shots ----")
    print(next(t for t in ca if "⏳ **Find the trailer" in t))
    print("---- finish ----")
    print(fin[len(fin) // 2])
    print(fin[-1])
    print("time left (uncached, right after downloads):",
          re.search(r"· (.*)$", next(t for t in un if "⏳ **Find the trailer" in t)).group(1))
    print("PASS test_trailer_panel")


asyncio.run(main())
