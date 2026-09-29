#!/usr/bin/env python3
"""The watches for #379's fix, committed rather than claimed.

#399's review found the verification section asserting unit and flow tests
the tree did not hold - they had run as inline heredocs and were never
committed, which is the report-versus-artifact class this repository keeps
paying for. This file is those watches, runnable from the tree:

    python3 test_provenance_close.py

Plain asserts, stdlib only, exit 0 or a traceback. The real-box level
stays where it was: a full confirm run, the trace-generation smoke, and a
short matrix run, none of which belong in a unit file.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import confirm_cells as g  # noqa: E402


def test_close_statuses():
    """Every branch of the lifted close, one envelope each - defect 1."""
    good = {"lib": {"path": "/x", "sha256": "aa", "resolved_by": "cfg"}}
    # a transient closing failure is not movement
    env = g.provenance_close({}, lambda c: {"unreadable": "blip"}, good, "w")
    assert env["status"] == "at_close_unreadable", env
    # an unsound opening cannot support a claim either
    env = g.provenance_close({}, lambda c: dict(good),
                             {"unreadable": "was bad"}, "w")
    assert env["status"] == "at_start_unreadable", env
    # a genuine swap on one resolution is claimed
    swapped = {"lib": {"path": "/x", "sha256": "bb", "resolved_by": "cfg"}}
    env = g.provenance_close({}, lambda c: swapped, good, "w")
    assert env["status"] == "varied", env
    # a resolution move preempts the content claim
    moved = {"lib": {"path": "/y", "sha256": "bb", "resolved_by": "guess"}}
    env = g.provenance_close({}, lambda c: moved, good, "w")
    assert env["status"] == "resolved_differently", env
    # a raising reader degrades to a note, never propagates
    env = g.provenance_close({}, lambda c: 1 / 0, good, "w")
    assert env["status"] == "at_close_unreadable", env
    assert "division" in json.dumps(env)
    # quiet is the unchanged envelope
    env = g.provenance_close({}, lambda c: dict(good), good, "w")
    assert env["status"] == "unchanged", env
    # the toolchain compares whole, where hashes would answer {}
    t1 = {"rustc": "rustc 1.95.0", "active_toolchain": "nightly-a"}
    t2 = {"rustc": "rustc 1.95.0", "active_toolchain": "nightly-b"}
    env = g.provenance_close({}, lambda c: t2, t1, "t",
                             essence=g.close_whole)
    assert env["status"] == "varied", env


def test_absent_rustup_is_a_reading():
    """Defect 3: a box without rustup is a fact, stable across reads."""
    t = {"rustc": "rustc 1.95.0",
         "active_toolchain": {"absent": "no rustup on this box"}}
    assert g.is_reading(t)
    env = g.provenance_close({}, lambda c: json.loads(json.dumps(t)), t,
                             "toolchain", essence=g.close_whole)
    assert env["status"] == "unchanged", env
    # while a rustup that ran and failed stays unsound
    bad = {"rustc": "rustc 1.95.0",
           "active_toolchain": {"unreadable": "rustup exit 1"}}
    assert not g.is_reading(bad)


def _drive_main(die_second_cell=False, swap_libs=False):
    """The matrix's cells mode whole, with the box stubbed - defects 2 and 4
    of #379, found in the standalone driver since folded into the matrix."""
    import tempfile
    from test_recorded_seed import cells_main
    LIBS = {"lib": {"path": "/l", "sha256": "aa", "resolved_by": "cfg"}}
    BINS = {"bin": {"path": "/b", "sha256": "bb", "resolved_by": "cfg"}}
    TOOLS = {"rustc": "rustc stub", "active_toolchain": "nightly-stub"}
    calls = {"n": 0}

    def fake_run_session(cfg, session, declaration_sha=None, rec=None):
        calls["n"] += 1
        if calls["n"] == 2 and die_second_cell:
            raise RuntimeError("cell two died")
        return dict(session["label"], declared_seed=session["declared_seed"], devices=[{"ordinal": 0}],
                    verdict="REPRODUCED", turns=[])

    lib_seq = [json.loads(json.dumps(LIBS)),
               {"lib": {"path": "/l", "sha256": "SWAPPED", "resolved_by": "cfg"}}]
    fakes = {"_resolve_spu": lambda cfg: ("/stub", "stub"),
             "closing_resolution": lambda cfg: (("/stub", "stub"), None),
             "engine_libraries": ((lambda cfg, spu=None: lib_seq.pop(0)) if swap_libs
                                  else (lambda cfg, spu=None: json.loads(json.dumps(LIBS)))),
             "weaver_binaries": lambda cfg, spu=None: json.loads(json.dumps(BINS)),
             "toolchain": lambda cfg: dict(TOOLS)}
    cells = [{"name": "c1", "precision": "q8", "artifact": None}, {"name": "c2", "precision": "bf", "artifact": None}]
    with tempfile.TemporaryDirectory() as td:
        artifact = os.path.join(td, "a")
        with open(artifact, "w") as f:
            f.write("weights")
        for c in cells:
            c["artifact"] = artifact
        try:
            code, _, _, records, summary = cells_main(
                td, dict(cells=cells), declared=f'[spu-instruction.decoder.model-binding]\nartifact = "{artifact}"\n[spu-instruction.decoder.tunable-values]\nseed = 7\n',
                fakes=fakes, dm_fakes={"run_session": fake_run_session})
        except RuntimeError as e:
            code, summary = f"raised:{e}", None
            path = os.path.join(td, "out", "matrix.jsonl")
            records = [json.loads(line) for line in open(path)] if os.path.exists(path) else None
    return code, records, summary


def test_failed_resolution_closes_unreadable_not_lost():
    """A raising resolution becomes at_close_unreadable envelopes, never a
    lost close - the outside-diff finding of #399's second exchange."""
    saved = g._resolve_spu
    try:
        def boom(cfg):
            raise RuntimeError("resolution died")
        g._resolve_spu = boom
        spu, note = g.closing_resolution({})
        assert spu is None and "resolution raised" in note["unreadable"]
        good = {"lib": {"path": "/x", "sha256": "aa", "resolved_by": "cfg"}}
        env = g.provenance_close(
            {}, lambda c: note or {"never": "reached"}, good, "engine_libraries")
        assert env["status"] == "at_close_unreadable", env
    finally:
        g._resolve_spu = saved


def test_clean_run_exits_zero_window_quiet():
    code, records, summary = _drive_main()
    assert code == 0 and len(records) == 2, code
    assert all(summary[k]["status"] == "unchanged" for k in g.REQUIRED_WINDOWS)


def test_midrun_raise_keeps_partial_deposit():
    """Defect 2: the deposit survives a raise past the first cell. Since the
    fault boundary around each session (#716, the pass on 26b93db) the raise
    is that cell's fault, and the run goes on to its summary."""
    code, records, summary = _drive_main(die_second_cell=True)
    assert code == 1 and summary is not None, code
    assert [r["verdict"] for r in records] == ["REPRODUCED", "error: RuntimeError: cell two died"], records


def test_midrun_swap_exits_one_over_green_cells():
    """Defect 4: a moved window is not a reproduction result."""
    code, records, summary = _drive_main(swap_libs=True)
    assert code == 1, code
    assert summary["engine_libraries"]["status"] == "varied"
    assert all(r["verdict"] == "REPRODUCED" for r in records)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all watches held")
