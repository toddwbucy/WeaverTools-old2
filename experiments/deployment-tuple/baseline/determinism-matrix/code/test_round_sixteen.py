"""A closing step the result rests on joins the exit (#716, the pass on
7ba83d5).

Run with `python3 test_round_sixteen.py` or under pytest.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import MODEL, Reloading, run_main  # noqa: E402
from test_round_eleven import DiskServing  # noqa: E402
from test_round_nine import cells_run  # noqa: E402

base = dm.base


def logged(**kw):
    """The matrix whole, and its log read back."""
    seen = {}

    def inspect(tmp, decl):
        seen["log"] = open(os.path.join(tmp, "matrix.log")).read()
        seen["backup"] = decl + ".pre-matrix"
        if os.path.lexists(seen["backup"]):
            os.unlink(seen["backup"])
    code, records, summary = run_main(Reloading(), inspect=inspect, **kw)
    return code, records, summary, seen["log"]


def failing_dump(*a, **k):
    raise PermissionError("the summary")


def test_a_summary_that_was_not_written_fails_the_exit():
    # Codex's pass on 7ba83d5: closing answered None on failure and the
    # summary's write dropped it, so a run with no summary.json exited 0.
    # Perturbation: drop the write from the exit, and both modes exit 0.
    real = dm.json
    dm.json = types.SimpleNamespace(dump=failing_dump, dumps=json.dumps, loads=json.loads)
    try:
        code, records, summary, log = logged()
        cell_code, _, printed, cell_records, cell_summary = cells_run(Reloading())
    finally:
        dm.json = real
    want = "these closing steps did not complete: the summary's write"
    assert code == 1 and records and summary is None and want in log, (code, summary)
    assert all(r["verdict"] == "REPRODUCED" for r in records)
    assert cell_code == 1 and cell_summary is None and want in printed, (cell_code, printed[-300:])


class LockingAtEnd(DiskServing):
    """After the `last`th session's closing unload, the declaration is made
    read-only, so the run's restore cannot land. Each load serves the
    declaration on disk, as the admin does."""

    def __init__(self, last):
        DiskServing.__init__(self)
        self.last, self.sessions, self.replayed = last, 0, False

    def gate_turn(self, cfg, text, timeout=None):
        self.replayed = self.replayed or self.loads == 2
        return DiskServing.gate_turn(self, cfg, text, timeout)

    def admin(self, cfg, verb):
        if verb == "unload" and self.replayed:
            self.replayed = False
            self.sessions += 1
            if self.sessions == self.last:
                os.chmod(cfg["declaration"], 0o444)
        return DiskServing.admin(self, cfg, verb)


def test_a_restore_that_did_not_land_fails_the_exit():
    # The declaration left unrestored is not a result either. Perturbation:
    # drop the restore from the exit, and both modes exit 0.
    want = "these closing steps did not complete: the declaration's restore"
    seen = {}

    def inspect(tmp, decl):
        seen["log"] = open(os.path.join(tmp, "matrix.log")).read()
        seen["backup"] = os.path.lexists(decl + ".pre-matrix")
    code, records, summary = run_main(LockingAtEnd(2), sessions=2, extra=["--artifact", MODEL], inspect=inspect)
    assert code == 1 and summary is not None and want in seen["log"] and seen["backup"], (code, seen)
    assert [r["verdict"] for r in records] == ["REPRODUCED", "REPRODUCED"], records
    cell_code, _, printed, cell_records, cell_summary = cells_run(LockingAtEnd(2))
    assert cell_code == 1 and cell_summary is not None and want in printed, (cell_code, printed[-300:])
    assert [r["verdict"] for r in cell_records] == ["REPRODUCED", "REPRODUCED"], cell_records


def test_the_notes_stay_notes():
    # The run's last unload and the journal's device read are notes: no
    # session rests on them. Perturbation: count either in the exit, and a
    # reproduced run exits 1.
    def boom(*a, **k):
        raise RuntimeError("the box")
    for stack in ({"device_bindings": boom}, {}):
        real = base.release
        base.release = boom if not stack else real
        try:
            code, records, summary, log = logged(stack=stack)
        finally:
            base.release = real
        assert code == 0 and records and summary is not None, (stack, code)
        assert "failed: the box" in log, log[-300:]


def test_a_closing_resolution_that_did_not_complete_is_not_unchanged():
    # The SPU's closing resolution feeds the binaries and the libraries, so
    # one that never completed closes them unreadable. Perturbation: take a
    # failed resolution for a good one, and both windows read unchanged.
    def interrupted(c):
        raise KeyboardInterrupt
    code, records, summary, log = logged(stack={"closing_resolution": interrupted})
    assert code == 1, code
    for field in ("weaver_binaries", "engine_libraries"):
        assert summary[field]["status"] == "at_close_unreadable", (field, summary[field])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
