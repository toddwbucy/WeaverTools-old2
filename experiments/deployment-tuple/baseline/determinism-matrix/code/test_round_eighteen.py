"""The session an interrupt cuts short is recorded, in the record and the
summary alike (#716, the pass on 9402e08).

Run with `python3 test_round_eighteen.py` or under pytest.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import Reloading, run_main  # noqa: E402
from test_round_nine import cells_run  # noqa: E402

base = dm.base


def both(patch, restore):
    """The matrix bounded to three sessions and a cells run, each with
    `patch` applied, and each one's exit, records and summary."""
    patch()
    try:
        code, records, summary = run_main(Reloading(), sessions=3)
    finally:
        restore()
    patch()
    try:
        cell_code, _, _, cell_records, cell_summary = cells_run(Reloading())
    finally:
        restore()
    return (code, records, summary), (cell_code, cell_records, cell_summary)


def held(run, cut_at):
    """The run stopped on the session cut short, recorded as `interrupted`
    in matrix.jsonl, and the summary counting exactly those records."""
    code, records, summary = run
    assert code == 1, code
    assert [r["verdict"] for r in records] == ["REPRODUCED"] * (cut_at - 1) + ["interrupted"], \
        [r["verdict"] for r in records]
    assert summary["sessions"] == len(records) and summary["errors"] == 1, (summary["sessions"], summary["errors"])


def test_an_interrupt_in_formatting_is_recorded_in_both_files():
    # Codex's pass on 9402e08: a Ctrl-C after verify_session returned left
    # record_session and the loop, and the session cut short was recorded
    # nowhere. Perturbation: drop the KeyboardInterrupt clause in
    # record_session, and the second session is missing from both files.
    real, calls = dm.entropies_of, []

    def entropies_of(turn):
        calls.append(1)
        if len(calls) == 3:  # the second session's first turn
            raise KeyboardInterrupt
        return real(turn)

    def patch():
        calls.clear()
        dm.entropies_of = entropies_of

    def restore():
        dm.entropies_of = real
    matrix, cells = both(patch, restore)
    held(matrix, 2)
    held(cells, 2)


def test_an_interrupt_during_the_append_is_recorded_in_both_files():
    # The loop body's other half: a Ctrl-C while the record is written
    # makes the session `interrupted`, written whole, and joins the results
    # with it. Perturbation: append outside `closing`, or add to the results
    # before the write lands, and the files disagree or the run raises out.
    calls = []

    def dumps(obj, *a, **k):
        if isinstance(obj, dict) and "verdict" in obj and obj.get("verdict") == "REPRODUCED":
            calls.append(1)
            if len(calls) == 2:
                raise KeyboardInterrupt
        return json.dumps(obj, *a, **k)
    real = dm.json

    def patch():
        calls.clear()
        dm.json = types.SimpleNamespace(dump=json.dump, dumps=dumps, loads=json.loads)

    def restore():
        dm.json = real
    matrix, cells = both(patch, restore)
    held(matrix, 2)
    held(cells, 2)


class HalfWritten:
    """A file whose first write of a record lands half its line and then
    raises KeyboardInterrupt, as a Ctrl-C mid-write can."""

    def __init__(self, fh, state):
        self.fh, self.state = fh, state

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fh.close()
        return False

    def truncate(self, *a):
        return self.fh.truncate(*a)

    def write(self, s):
        if not self.state["done"]:
            self.state["done"] = True
            self.fh.write(s[:len(s) // 2])
            self.fh.flush()
            raise KeyboardInterrupt
        return self.fh.write(s)


def test_a_partial_line_is_rewritten_whole():
    # The append's rewrite after a write that landed half a line: the retry
    # truncates back to where the line began, so matrix.jsonl holds whole
    # lines, one per record. Perturbation: drop the truncate, and the half
    # line and the whole one run together and the record no longer parses.
    import builtins
    state = {"records": 0, "done": False}

    def opener(path, mode="r", *a, **k):
        fh = builtins.open(path, mode, *a, **k)
        if str(path).endswith("matrix.jsonl") and mode == "a":
            state["records"] += 1
            if state["records"] == 2:
                return HalfWritten(fh, state)
        return fh

    def patch():
        state.update(records=0, done=False)
        dm.open = opener

    def restore():
        del dm.open
    matrix, cells = both(patch, restore)
    held(matrix, 2)
    held(cells, 2)


def test_an_interrupt_in_the_loop_body_is_recorded_in_both_files():
    # After record_session returns and before the write: the invocation
    # hold stands for the loop body's lines. Perturbation: drop the loop
    # body's KeyboardInterrupt clause, and the session is lost.
    real, calls = base.hold_invocations, []

    def hold(rec, seen):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real(rec, seen)

    def patch():
        calls.clear()
        base.hold_invocations = hold

    def restore():
        base.hold_invocations = real
    matrix, cells = both(patch, restore)
    held(matrix, 2)
    held(cells, 2)


def test_a_record_that_never_lands_is_not_counted_and_fails_the_exit():
    # A write that fails outright leaves the record out of the results, so
    # the summary counts what matrix.jsonl holds, and the run exits 1 naming
    # it. Perturbation: add the record to the results whatever the write,
    # and the summary counts a session the record lacks.
    calls = []

    def dumps(obj, *a, **k):
        if isinstance(obj, dict) and "verdict" in obj:
            calls.append(1)
            if len(calls) == 2:
                raise ValueError("unwritable")
        return json.dumps(obj, *a, **k)
    real = dm.json
    dm.json = types.SimpleNamespace(dump=json.dump, dumps=dumps, loads=json.loads)
    try:
        code, records, summary = run_main(Reloading(), sessions=3)
    finally:
        dm.json = real
    assert code == 1 and len(records) == 2 and summary["sessions"] == 2, (code, len(records), summary["sessions"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
