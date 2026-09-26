"""dub_queue offline: fake Telegram, fake films.  Checks: films run ONE at a time in queue
order; a failing film and a cancelled film don't stop the queue; remove / move-up; the
busy wait; a restart mid-film runs that film again first; panel text.
Run: /opt/media-os/venv/bin/python test_dub_queue.py [dir with dub_queue.py]"""
import asyncio
import importlib
import os
import sys
import tempfile
import time

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/opt/Bidhanlogoedit")


class Chat:
    id = 777


class Msg:
    def __init__(self, i):
        self.id, self.chat, self.empty = i, Chat(), False
        self.edits = []

    async def edit(self, txt, reply_markup=None):
        self.edits.append(txt)

    async def reply(self, txt, reply_markup=None):
        m = Msg(0)
        m.edits.append(txt)
        return m


class App:
    def __init__(self):
        self.sent = []

    def add_handler(self, *a, **k):
        pass

    async def get_messages(self, chat, ids):
        return [Msg(i) for i in ids]

    async def send_message(self, uid, txt):
        self.sent.append((uid, txt))


def load(store):
    import dub_queue as Q
    Q = importlib.reload(Q)
    Q.STORE = store
    Q.BUSY_POLL_S = 0.02
    return Q


async def main():
    store = os.path.join(tempfile.mkdtemp(), "q.json")
    Q = load(store)
    log, running, busy = [], [], [False]
    gate = {}

    async def run(uid, msgs, hd_i, brand, mode):
        name = "film%d" % msgs[0].id
        running.append(name)
        assert len(running) == 1, ("two films at once", running)
        log.append(("start", name))
        try:
            ev = gate.get(name)
            if ev:
                await ev.wait()
            else:
                await asyncio.sleep(0.05)
            if name == "film3":
                raise RuntimeError("engine blew up")
        finally:
            running.remove(name)
            log.append(("end", name))

    async def cancel_running(uid):
        Q._current["task"].cancel()

    async def start_flow(uid, m):
        pass

    app = App()
    Q.register(app, lambda u: True, run, lambda: busy[0], cancel_running, start_flow)

    # 1) three films queue in order, one at a time; film3 fails, the queue goes on
    for k in (1, 3, 5):
        p = await Q.enqueue(1, [Msg(k), Msg(k + 1)], 0, True, "auto", "Movie %d" % k)
    assert p == 3, p
    for _ in range(100):
        await asyncio.sleep(0.02)
        if not Q._waiting() and not Q._current:
            break
    starts = [n for a, n in log if a == "start"]
    assert starts == ["film1", "film3", "film5"], starts
    st = {e["title"]: e["state"] for e in Q._q}
    assert st == {"Movie 1": "finished", "Movie 3": "failed", "Movie 5": "finished"}, st
    assert "engine blew up" in next(e for e in Q._q if e["title"] == "Movie 3")["note"]

    # 2) a cancelled film: the queue carries on; remove + move-up while waiting
    gate["film11"] = asyncio.Event()
    await Q.enqueue(1, [Msg(11), Msg(12)], 0, True, "auto", "Long one")
    await asyncio.sleep(0.05)
    assert Q.running_title() == "Long one"
    for k in (21, 31, 41):
        await Q.enqueue(1, [Msg(k), Msg(k + 1)], 0, True, "auto", "Next %d" % k)
    w = Q._waiting()
    assert [e["title"] for e in w] == ["Next 21", "Next 31", "Next 41"]
    # remove "Next 31", move "Next 41" up (to first)
    class CQ:
        def __init__(self, data):
            self.data, self.from_user, self.message = data, type("U", (), {"id": 1})(), Msg(0)

        async def answer(self, *a, **k):
            pass

        def stop_propagation(self):
            pass
    await Q._cb(None, CQ("dq:rm:%d" % w[1]["id"]))
    await Q._cb(None, CQ("dq:up:%d" % w[2]["id"]))
    assert [e["title"] for e in Q._waiting()] == ["Next 41", "Next 21"], [e["title"] for e in Q._waiting()]
    txt = Q.panel_text(1)
    assert "▶️ **Now** `Long one`" in txt and "⏳ **1.** `Next 41`" in txt and "✖️ `Next 31`" in txt, txt
    await cancel_running(1)                       # /cancel on the running film
    for _ in range(100):
        await asyncio.sleep(0.02)
        if not Q._waiting() and not Q._current:
            break
    st = {e["title"]: e["state"] for e in Q._q}
    assert st["Long one"] == "cancelled" and st["Next 41"] == "finished" and st["Next 21"] == "finished", st
    starts = [n for a, n in log if a == "start"]
    assert starts[-3:] == ["film11", "film41", "film21"], starts

    # 3) busy: a trailer job runs -> the next film waits, then starts
    busy[0] = True
    await Q.enqueue(1, [Msg(51), Msg(52)], 0, True, "auto", "After trailer")
    await asyncio.sleep(0.1)
    assert ("start", "film51") not in log and "waiting for the job" in Q.panel_text(1)
    busy[0] = False
    for _ in range(100):
        await asyncio.sleep(0.02)
        if ("end", "film51") in log:
            break
    assert ("end", "film51") in log

    # 4) restart mid-film: the running film runs again, first; waiting ones follow
    gate["film61"] = asyncio.Event()
    await Q.enqueue(1, [Msg(61), Msg(62)], 0, True, "auto", "Interrupted")
    await Q.enqueue(1, [Msg(71), Msg(72)], 0, True, "auto", "Behind it")
    await asyncio.sleep(0.05)
    assert Q.running_title() == "Interrupted"
    Q._worker.cancel()                            # the bot process dies here
    for t in [Q._current.get("task")]:
        if t:
            t.cancel()
    await asyncio.sleep(0.05)
    running.clear()
    gate.pop("film61")
    Q2 = load(store)                              # a new process reads the saved queue
    app2 = App()
    Q2.register(app2, lambda u: True, run, lambda: False, cancel_running, start_flow)
    await Q2.resume()
    for _ in range(200):
        await asyncio.sleep(0.02)
        if not Q2._waiting() and not Q2._current:
            break
    starts = [n for a, n in log if a == "start"]
    assert starts[-2:] == ["film61", "film71"], starts
    assert app2.sent and "queue** carries on" in app2.sent[0][1], app2.sent
    st = {e["title"]: e["state"] for e in Q2._q}
    assert st["Interrupted"] == "finished" and st["Behind it"] == "finished", st
    print(Q2.panel_text(1))
    print("PASS test_dub_queue")


asyncio.run(main())
