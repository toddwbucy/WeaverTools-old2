"""A load held by its run, and every session's raise its own fault (#716,
the pass on 26b93db).

Run with `python3 test_round_fifteen.py` or under pytest.
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import MODEL, SEED, Reloading, run_main  # noqa: E402
from test_round_nine import TWO_CELLS, cells_run  # noqa: E402

base = dm.base
OTHER = "e" * 64


def event(run, declaration):
    return {"run": run, "kind": "load", "payload": {"declaration": declaration,
                                                    "composer": {"binary": "worker"}}}


def stale_then_current(session, expected, tmp):
    """One session on a real trace: the sink, trailing, writes the previous
    load's event, carrying the expected declaration, after this load stands,
    and this load's own event, carrying another, only as the gate answers.
    Answers the session's record."""
    trace = os.path.join(tmp, "trace.ndjson")
    with open(trace, "w") as fh:
        fh.write(json.dumps(event("r-older", OTHER)) + "\n")
    decl = os.path.join(tmp, "karl.toml")
    with open(decl, "w") as fh:
        fh.write(f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n')
    cfg = {"agent": "karl", "declaration": decl, "trace": trace, "gate_socket": "/s",
           "admin_bin": "/bin/true", "admin_config": tmp, "repo": tmp}

    def admin(c, verb):
        if verb == "load":
            with open(trace, "a") as fh:
                fh.write(json.dumps(event("r-old", expected)) + "\n")
            return {"kind": "state", "state": "idle", "exit": 0}
        return {"kind": "state", "state": "unloaded", "exit": 0}

    def gate(c, text, timeout=600):
        with open(trace, "a") as fh:
            fh.write(json.dumps(event("r-cell", OTHER)) + "\n")
        return {"kind": "answered", "run": "r-cell"}
    invocations = iter(f"{i:032x}" for i in range(1, 100))
    fakes = {"admin": admin, "gate_turn": gate, "wait_socket": lambda c, timeout=120: True,
             "serving_device": lambda c, since, invocation=None: {"devices": [{"ordinal": 0}], "complete": True},
             "unit_invocation": lambda c: next(invocations),
             "await_turns": lambda *a, **k: ([], [])}
    saved = {k: getattr(base, k) for k in fakes}
    try:
        for k, v in fakes.items():
            setattr(base, k, v)
        return dm.run_session(cfg, session, expected)
    finally:
        for k, v in saved.items():
            setattr(base, k, v)


def test_a_stale_load_event_does_not_answer_for_the_current_run():
    # Codex's pass on 26b93db, thread 1: the first load event of a run other
    # than the snapshot's was taken, and a trailing sink handed back the
    # previous load's. Perturbation: read the newest load again, and both
    # modes take the stale event and serve on.
    standing = f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'
    want = "the source load served another declaration"
    with tempfile.TemporaryDirectory() as tmp:
        expected = hashlib.sha256(standing.encode()).hexdigest()
        rec = stale_then_current(dm.matrix_session(dm.PROMPTS[0], 2, 1, SEED), expected, tmp)
    assert rec["verdict"].startswith(want) and rec["source_run"] == "r-cell", rec["verdict"]
    with tempfile.TemporaryDirectory() as tmp:
        cell = next(dm.cell_sessions(standing, [TWO_CELLS[0]]))
        expected = hashlib.sha256(cell["declaration"].encode()).hexdigest()
        rec = stale_then_current(cell, expected, tmp)
    assert rec["verdict"].startswith(want) and rec["source_run"] == "r-cell", rec["verdict"]


def test_a_run_whose_load_event_never_arrives_is_a_fault():
    # Perturbation: pass the hold where no event of the run stands, and the
    # session serves on under an unheld declaration.
    rec = {}
    with tempfile.TemporaryDirectory() as tmp:
        trace = os.path.join(tmp, "trace.ndjson")
        with open(trace, "w") as fh:
            fh.write(json.dumps(event("r-old", "a" * 64)) + "\n")
        held = base.load_held({"trace": trace}, "r-cell", "a" * 64, "source", rec, timeout=0.1)
    assert held is False and rec["verdict"] == "no load event reached the trace for the source run r-cell", rec


class BadWall(Reloading):
    """The source's turns carry a wall time that is not a number."""

    def gate_turn(self, cfg, text, timeout=None):
        close = Reloading.gate_turn(self, cfg, text, timeout)
        if self.loads == 1:
            for e in self.runs[self.run]:
                if e["kind"] == "turn.started":
                    e["wall_ms"] = "x"
        return close


class NoEmission(Reloading):
    """The source's outputs carry no emission."""

    def gate_turn(self, cfg, text, timeout=None):
        close = Reloading.gate_turn(self, cfg, text, timeout)
        if self.loads == 1:
            for e in self.runs[self.run]:
                if e["kind"] == "model.output":
                    e["payload"].pop("emission", None)
        return close


def test_a_raise_in_formatting_is_the_sessions_fault_in_both_modes():
    # Codex's pass on 26b93db, thread 2: run_session formatted after the
    # verification returned, outside any boundary, and a wall time that is
    # not a number ended the run with no record or summary. Perturbation:
    # call run_session without the boundary, and the run raises out.
    code, records, summary = run_main(BadWall(), sessions=2)
    assert code == 1 and summary is not None and len(records) == 2, (code, records and len(records))
    assert all(r["verdict"].startswith("error: TypeError") for r in records), records[0]["verdict"]
    assert records[0]["source_run"] == "run-1" and records[0]["recorded_seed"] == SEED
    code, _, _, records, summary = cells_run(BadWall())
    assert code == 1 and summary is not None and len(records) == 2, code
    assert all(r["verdict"].startswith("error: TypeError") for r in records), records[0]["verdict"]


def test_a_missing_emission_is_a_fault_record_in_both_modes():
    # The same boundary's other case, caught earlier by the verification as
    # an unobserved check. A fault record is appended and the summary still
    # written.
    want = "t-1: emission bytes absent from the source record"
    code, records, summary = run_main(NoEmission(), sessions=2)
    assert code == 1 and summary is not None and {r["verdict"] for r in records} == {want}, \
        (code, records and records[0]["verdict"])
    code, _, _, records, summary = cells_run(NoEmission())
    assert code == 1 and summary is not None and {r["verdict"] for r in records} == {want}, code


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
