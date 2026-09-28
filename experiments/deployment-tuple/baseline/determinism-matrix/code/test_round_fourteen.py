"""A cells run serves every cell, a session's record is held to the texts it
served, and every closing read marks an interrupt (#716, the pass on
99b37c4).

Run with `python3 test_round_fourteen.py` or under pytest.
"""
import contextlib
import hashlib
import io
import itertools
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import CARD, HELD, MODEL, SEED, Agent, Reloading, cells_main, run_main, session  # noqa: E402
from test_round_five import drive_cell  # noqa: E402
from test_round_nine import TWO_CELLS, agent_fakes  # noqa: E402

base = dm.base
DIGEST = hashlib.sha256(f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'.encode()).hexdigest()


def cells(agent=None, dm_fakes=None, change=None):
    agent = agent or Reloading()
    agent.served = (DIGEST, DIGEST)
    with tempfile.TemporaryDirectory() as tmp:
        return cells_main(tmp, dict(dict(cells=TWO_CELLS), **(change or {})), fakes=agent_fakes(agent),
                          dm_fakes=dm_fakes)


# Class 1: a cells run serves every cell.

def test_a_cells_run_takes_no_deadline():
    # Codex's pass on 99b37c4, thread 1: the fold put cells under the
    # matrix's deadline. Perturbation: give the cells the matrix's deadline,
    # and a clock past it serves no cell; drop the --hours refusal, and it is
    # taken.
    import time
    clock = itertools.count(time.time(), 10 ** 9)
    fast = types.SimpleNamespace(time=lambda: next(clock), strftime=time.strftime,
                                 localtime=time.localtime, sleep=time.sleep)
    code, _, _, records, summary = cells(dm_fakes={"time": fast})
    assert code == 0 and [r["cell"] for r in records] == ["q8", "bf16"], (code, records)
    err = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
        code, records, _ = run_main(Reloading(), extra=["--cells"])
    assert code == 2 and records is None and "--hours" in err.getvalue(), (code, err.getvalue())


def test_a_cells_run_short_of_its_cells_fails_naming_them():
    # A finite schedule's sessions are expected whole. Perturbation: drop
    # `expected` from run_verdict, and a run of one cell of two exits 0.
    real = dm.cell_sessions
    code, _, printed, records, summary = cells(
        dm_fakes={"cell_sessions": lambda standing, cs: itertools.islice(real(standing, cs), 1)})
    assert code == 1 and len(records) == 1 and "cells not served: bf16" in printed, (code, printed[-300:])
    one = [{"verdict": "REPRODUCED", "devices": CARD}]
    assert base.run_verdict(one, HELD, expected=2)[0] is False
    assert base.run_verdict(one, HELD, expected=1) == (True, [])


# Class 2: a session's record is held to the texts it served.

class Rewriting(Reloading):
    """The trace records one half's requests other than as served: once the
    half's two turns stand, `change` maps their texts, in order, to the
    texts recorded."""

    def __init__(self, change, half=1, **kw):
        Reloading.__init__(self, **kw)
        self.change, self.half = change, half

    def gate_turn(self, cfg, text, timeout=None):
        close = Reloading.gate_turn(self, cfg, text, timeout)
        users = [e for e in self.runs[self.run] if e["kind"] == "message.user"]
        if self.loads == self.half and len(users) == 2:
            texts = self.change([u["payload"]["content"][0]["text"] for u in users])
            for u, t in zip(users, texts):
                u["payload"]["content"][0]["text"] = t
        return close


def swapped(texts):
    return texts[::-1]


def altered(texts):
    return texts[:-1] + [texts[-1] + " "]


def test_a_reordered_or_altered_source_is_refused_in_both_modes():
    # Codex's pass on 99b37c4, thread 2: the source half was accepted on its
    # turn count alone, and a replay reissued from a wrong record could
    # reproduce under this session's labels. Perturbation: drop the texts
    # check, and each case replays the wrong record and reads REPRODUCED.
    for change, first in ((swapped, 1), (altered, 2)):
        rec = session(Rewriting(change))
        assert rec["verdict"] == f"source t-{first} carries a request other than turn {first} of the texts served", \
            (change.__name__, rec["verdict"])
        with tempfile.TemporaryDirectory() as tmp:
            digest = hashlib.sha256(f'[spu-instruction.decoder.model-binding]\nartifact = "/m.gguf"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'.encode()).hexdigest()
            cell = drive_cell(Rewriting(change, served=(digest, digest)), tmp)
        assert cell["verdict"] == f"source t-{first} carries a request other than turn {first} of the texts served", \
            (change.__name__, cell["verdict"])
    assert session(Agent())["verdict"] == "REPRODUCED"


def test_a_replay_recording_other_requests_is_refused_in_both_modes():
    # The record's replay carries the source's requests, in order.
    # Perturbation: drop the replay's texts check, and an altered replay
    # reads as a divergence of the model, or reproduces.
    rec = session(Rewriting(altered, half=2))
    assert rec["verdict"] == "replay t-2 carries a request other than source t-2's", rec["verdict"]
    with tempfile.TemporaryDirectory() as tmp:
        digest = hashlib.sha256(f'[spu-instruction.decoder.model-binding]\nartifact = "/m.gguf"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'.encode()).hexdigest()
        cell = drive_cell(Rewriting(altered, half=2, served=(digest, digest)), tmp)
    assert cell["verdict"] == "replay t-2 carries a request other than source t-2's", cell["verdict"]


# Class 3: every step between the loop and the summary marks an interrupt.

def once(fn, raised=KeyboardInterrupt):
    """`fn` raising `raised` on its first call and itself after."""
    calls = []

    def wrapped(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise raised()
        return fn(*a, **k)
    wrapped.calls = calls
    return wrapped


def test_an_interrupt_in_the_journal_read_marks_the_run():
    # Codex's pass on 99b37c4, thread 3: the journal read caught an
    # interrupt into an unreadable window, which is not gated, so the run
    # could exit 0. Perturbation: catch it there again, and the run exits 0.
    card = [{"ordinal": 0, "name": "card", "pci_bus_id": "0000:01:00.0"}]
    read = once(lambda c, since: [card])
    code, records, summary = run_main(Reloading(), stack={"device_bindings": read})
    assert code == 1 and summary["serving_device_journal_window"] == card and read.calls == [1, 1], (code, summary)
    twice = once(once(lambda c, since: [card]))
    code, records, summary = run_main(Reloading(), stack={"device_bindings": twice})
    assert code == 1 and "did not complete" in summary["serving_device_journal_window"]["unreadable"], summary


def test_an_interrupt_in_a_closing_reading_marks_the_run():
    # The siblings: each closing provenance read and the SPU's closing
    # resolution. Perturbation: let provenance_close or closing_resolution
    # catch the interrupt again, and the run exits 0 on a window that held.
    tools = {"rustc": {"path": "/rustc", "sha256": "e" * 64}}
    reads = []

    def toolchain(c):
        reads.append(1)
        if len(reads) == 2:
            raise KeyboardInterrupt
        return tools
    code, records, summary = run_main(Reloading(), stack={"toolchain": toolchain})
    assert code == 1 and summary["toolchain"]["status"] == "unchanged" and len(reads) == 3, (code, reads)
    # The real closing_resolution, its resolver interrupted at the close.
    resolves = []

    def resolve(c):
        resolves.append(1)
        if len(resolves) == 2:
            raise KeyboardInterrupt
        return "/spu"
    real = base.closing_resolution
    stack = {"_resolve_spu": resolve, "closing_resolution": real}
    code, records, summary = run_main(Reloading(), stack=stack)
    assert code == 1 and summary["engine_libraries"]["status"] == "unchanged" and len(resolves) == 3, (code, resolves)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
