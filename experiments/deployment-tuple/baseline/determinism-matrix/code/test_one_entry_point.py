"""One entry point: the cross-precision cells are the matrix's `--cells`
mode, one main, one session loop and one exit, the sessions it runs being
data (#716, on the operator's ruling of 2026-09-27).

Run with `python3 test_one_entry_point.py` or under pytest.
"""
import contextlib
import hashlib
import inspect
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import MODEL, SEED, Reloading, cells_main, run_main  # noqa: E402
from test_round_nine import TWO_CELLS, agent_fakes  # noqa: E402

base = dm.base


def test_the_harness_has_no_entry_point_of_its_own():
    # Perturbation: put a main, a session function or a CLI back into
    # confirm_cells, and this names it.
    for gone in ("main", "run_cell", "cell_metadata", "cells_weights", "CELL_CONFIG_KEYS"):
        assert not hasattr(base, gone), gone
    assert "__main__" not in inspect.getsource(base)


def test_the_matrix_has_one_session_loop():
    # Both schedules yield sessions of one shape into one loop, which calls
    # record_session once. Perturbation: give the cells a loop of their own
    # in main, and the count or the shapes differ.
    assert inspect.getsource(dm.main).count("record_session(") == 1
    cell = next(dm.cell_sessions(f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n', TWO_CELLS))
    matrix = next(dm.matrix_sessions(f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n', SEED, None))
    assert set(cell) == set(matrix), (set(cell), set(matrix))


def test_a_cells_run_serves_each_cell_once_and_labels_it():
    # Each cell once, in order, the protocol's two turns under its own
    # artifact, its record labelled by the cell, the summary counting by
    # cell and reading each cell's artifact under its name. Perturbation:
    # drop the label, by_cell or the weights keys, and a clause fails.
    agent = Reloading()
    digest = hashlib.sha256(f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'.encode()).hexdigest()
    agent.served = (digest, digest)
    served = []
    real = agent.gate_turn

    def gate(cfg, text, timeout=None):
        served.append(text)
        return real(cfg, text, timeout)
    agent.gate_turn = gate
    with tempfile.TemporaryDirectory() as tmp:
        code, _, _, records, summary = cells_main(tmp, dict(cells=TWO_CELLS), fakes=agent_fakes(agent))
    assert code == 0, code
    assert [(r["cell"], r["precision"], r["artifact"], r["iteration"]) for r in records] == \
        [(c["name"], c["precision"], c["artifact"], 1) for c in TWO_CELLS], records
    assert all(len(r["turns"]) == 2 and not any(t["is_probe"] for t in r["turns"]) for r in records)
    assert served[:2] == list(dm.CELL_TEXTS), served[:2]
    assert summary["by_cell"] == {"q8": {"n": 1, "ok": 1}, "bf16": {"n": 1, "ok": 1}}, summary["by_cell"]
    assert summary["by_character"] == {} and set(summary["weights"]["reading"]) == {"q8", "bf16"}
    code, records, summary = run_main(Reloading())
    assert code == 0 and summary["by_cell"] == {} and set(summary["weights"]["reading"]) == {"artifact"}


def test_the_cells_serve_the_protocols_pinned_turns():
    # The cross-precision protocol's two turns, as its earlier deposits
    # served them. Perturbation: change either, and this names it.
    assert dm.CELL_TEXTS == (
        "Introduce yourself in exactly one short sentence.",
        "Write a detailed step-by-step explanation of how a binary search works, then "
        "implement it in Python with comments, then walk through an example run on a "
        "list of twenty numbers.")


def test_each_cell_is_served_its_own_artifact_and_the_declaration_restored():
    # Each cell's session writes the declaration with that cell's artifact,
    # and the run restores the operator's declaration after the last cell.
    # Perturbation: serve the standing declaration, or do not count a cells
    # run as rewriting the declaration, and a clause fails.
    from test_round_eleven import DiskServing
    with tempfile.TemporaryDirectory() as art_dir:
        other = os.path.join(art_dir, "bf16.gguf")
        with open(other, "wb") as fh:
            fh.write(b"other weights")
        cells = [TWO_CELLS[0], dict(TWO_CELLS[1], artifact=other)]
        agent = DiskServing()
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _, records, _ = cells_main(tmp, dict(cells=cells), fakes=agent_fakes(agent))
            restored = open(os.path.join(tmp, "karl.toml")).read()
            left = os.path.lexists(os.path.join(tmp, "karl.toml.pre-matrix"))
    assert code == 0 and [r["verdict"] for r in records] == ["REPRODUCED", "REPRODUCED"], (code, records)
    assert [t.split("\n")[1] for t in agent.texts] == [f'artifact = "{MODEL}"'] * 2 + [f'artifact = "{other}"'] * 2, agent.texts
    assert restored == f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n' and not left, restored


def test_a_cells_run_takes_neither_override():
    # A cell names its own artifact and runs under the declaration's seed.
    # Perturbation: drop the refusal, and the override is ignored silently.
    for extra in (["--artifact", MODEL], ["--seed-schedule", "11,12,13"]):
        seen, agent, err = {}, Reloading(), io.StringIO()

        def inspect_out(tmp, decl):
            seen["written"] = sorted(f for f in os.listdir(tmp) if f.startswith(("matrix", "summary")))
        with contextlib.redirect_stderr(err):
            code, _, _ = run_main(agent, extra=["--cells", *extra], inspect=inspect_out)
        assert code == 2 and seen["written"] == [] and agent.starts == 0, (extra, code, seen)
        assert "--cells takes neither" in err.getvalue(), err.getvalue()


def test_a_cells_run_without_cells_is_refused():
    # Perturbation: drop cells_values, and a run with no cells writes an
    # empty deposit.
    err = io.StringIO()
    for change, want in ((dict(cells=None), "is not a non-empty list"), (dict(cells=[]), "is not a non-empty list")):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            code, called, *_ = cells_main(tmp, change)
            assert code == 2 and called == [] and not os.path.exists(os.path.join(tmp, "out")), (change, code)
        assert want in err.getvalue(), err.getvalue()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
