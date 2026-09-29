#!/usr/bin/env python3
"""The watches for #426: the driver refuses a run composed by another loop.

Committed rather than claimed, per the lesson `test_provenance_close.py`
records. Runnable from the tree:

    python3 test_loop_digest.py

Plain asserts, stdlib only, exit 0 or a traceback. Nothing here touches a
box: the trace is a temp file, the admin verbs and the socket wait are
stubbed, and the gate is a sentinel that proves whether a turn was reached.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import confirm_cells as g  # noqa: E402
import determinism_matrix as dm  # noqa: E402

DECLARED = "aa" * 32
OTHER = "bb" * 32


def _trace(td, events):
    p = os.path.join(td, "trace.ndjson")
    with open(p, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return p


def _load(run, composer, declaration=None):
    """One load event in the shape the record carries since #419, with the
    digest of the declaration it served where one is given."""
    payload = {"residual_readout": False, "surprisal": False}
    if composer is not None:
        payload["composer"] = composer
    if declaration is not None:
        payload["declaration"] = declaration
    return {"session": "s-1", "run": run, "sequence": "0", "kind": "load",
            "subsystem": "harness", "wall_ms": 0, "monotonic_ns": "0",
            "payload": payload}


def _file(name, digest):
    return {"binary": "pyworker", "file": f"/usr/local/libexec/weaver/loops/{name}",
            "sha256": digest}


def check(cfg, trace):
    """The loop check on the trace's one run, read by that run."""
    run = g.read_runs(trace)[0][-1]
    return g.assert_loop(cfg, g.run_load(trace, run), run)


def test_matching_digest_passes():
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", DECLARED))])
    assert check({"loop_sha256": DECLARED}, t) is None


def test_other_digest_refuses_with_both_digests():
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", OTHER))])
    r = check({"loop_sha256": DECLARED}, t)
    assert r is not None
    assert r["declared"] == DECLARED and r["recorded"] == OTHER, r
    assert r["run"] == "r1" and r["composer"]["file"].endswith("alpha_loop.py")


def test_the_name_is_not_the_identity():
    """The same name at other bytes refuses, another name at the declared
    bytes passes - the finding #426 was opened on."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", OTHER))])
    assert check({"loop_sha256": DECLARED}, t) is not None
    t = _trace(td, [_load("r2", _file("bravo_loop.py", DECLARED))])
    assert check({"loop_sha256": DECLARED}, t) is None


def test_compiled_loop_refuses_where_a_digest_is_declared():
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", {"binary": "worker"})])
    r = check({"loop_sha256": DECLARED}, t)
    assert r is not None and r["recorded"] is None, r
    assert r["composer"] == {"binary": "worker"}


def test_no_composer_at_all_refuses_where_a_digest_is_declared():
    """A build from before #419 recorded no composer. It cannot be shown to
    be the declared loop, so it is refused rather than passed on absence."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", None)])
    r = check({"loop_sha256": DECLARED}, t)
    assert r is not None and r["recorded"] is None and r["composer"] is None, r


def test_absent_key_is_unchecked():
    """A config that declares no loop keeps today's behaviour, whatever the
    record says, so the configs that predate the key still run."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", OTHER))])
    assert check({}, t) is None
    assert check({"box": "x"}, t) is None


def test_a_run_with_no_load_event_refuses_where_a_digest_is_declared():
    """A run whose load event has not reached the trace cannot pass on
    another run's."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", DECLARED))])
    r = g.assert_loop({"loop_sha256": DECLARED}, g.run_load(t, "r2"), "r2")
    assert r is not None and r["recorded"] is None and r["run"] == "r2", r
    assert "no load event for run r2" in r["note"]


def test_the_named_run_is_the_one_compared():
    """The load read by its run, never as the newest (#716, the pass on
    26b93db): a newer load of another run does not answer for this one, and
    an older one does not either."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", OTHER)),
                    _load("r2", _file("alpha_loop.py", DECLARED))])
    assert g.assert_loop({"loop_sha256": DECLARED}, g.run_load(t, "r2"), "r2") is None
    r = g.assert_loop({"loop_sha256": DECLARED}, g.run_load(t, "r1"), "r1")
    assert r is not None and r["run"] == "r1", r


def test_missing_trace_is_an_absence_not_a_raise():
    assert g.run_load("/nonexistent/trace.ndjson", "r1") is None


class _Served(BaseException):
    """Raised by the gate stub: a turn was about to be served. Not an
    `Exception`, which the shared session path records as a fault (#716
    round ten), so it stops the drive at the gate."""


def _drive_cell(composer_digest, served=None):
    """One cell of the matrix's cells mode, by `run_session`, with the box
    stubbed, up to the read of its source turns, after the load's hold. The load event records the declaration
    file's digest as it stands at the load, as the admin does, or `served`
    where a test gives one."""
    saved = {n: getattr(g, n) for n in
             ("admin", "wait_socket", "gate_turn", "serving_device", "unit_invocation", "await_turns")}
    td = tempfile.mkdtemp()
    # An older run at the declared digest already stands in the trace, so a
    # check that read the wrong load would pass on it. The fake load below
    # appends this cell's own load event, the way the harness does.
    trace = _trace(td, [_load("r-old", _file("alpha_loop.py", DECLARED))])
    decl = os.path.join(td, "k.toml")
    standing = '[spu-instruction.decoder.model-binding]\nartifact = "/a"\n[spu-instruction.decoder.tunable-values]\nseed = 7\n'
    with open(decl, "w") as f:
        f.write(standing)
    cfg = {"agent": "karl", "declaration": decl, "trace": trace,
           "gate_socket": "/s", "admin_bin": "/bin/true", "admin_config": td,
           "repo": td, "loop_sha256": DECLARED}
    cell = {"name": "c1", "precision": "q8", "artifact": "/a"}
    steps = []

    def fake_admin(cfg, verb):
        steps.append(verb)
        if verb == "load":
            digest = served if served is not None else g._sha256(decl)
            with open(trace, "a") as f:
                f.write(json.dumps(_load(
                    "r-cell", _file("alpha_loop.py", composer_digest), digest)) + "\n")
            return {"kind": "state", "state": "idle", "exit": 0}
        return {"kind": "no_residency", "exit": 1}

    def fake_gate(cfg, text, timeout=600):
        return {"kind": "answered", "run": "r-cell"}

    def fake_await(*a, **k):
        # Past the load's hold, the turns are read: the drive stops here.
        raise _Served("turns read")

    try:
        g.admin = fake_admin
        g.wait_socket = lambda cfg, timeout=120: True
        g.gate_turn = fake_gate
        g.await_turns = fake_await
        g.serving_device = lambda cfg, since, invocation=None: {"devices": [{"ordinal": 0}], "complete": True}
        # Each load its own unit invocation, as systemd starts each.
        invocations = iter(f"{i:032x}" for i in range(1, 1000))
        g.unit_invocation = lambda cfg: next(invocations)
        outcome = "returned"
        report = None
        try:
            report = dm.run_session(cfg, next(dm.cell_sessions(standing, [cell])))
        except _Served:
            outcome = "served"
        return outcome, report, steps
    finally:
        for n, fn in saved.items():
            setattr(g, n, fn)


def test_a_cell_refuses_before_its_turns_are_read():
    outcome, report, steps = _drive_cell(OTHER)
    assert outcome == "returned", outcome
    assert report["verdict"].startswith("loop refused at the source load"), report
    refused = report["loop_refused"]
    assert refused["declared"] == DECLARED and refused["recorded"] == OTHER
    assert refused["half"] == "source" and refused["run"] == "r-cell"
    assert report["turns"] == [] and report["source_run"] == "r-cell" and report["replay_run"] is None
    # the finally still released the device
    assert steps[-1] == "unload", steps


def test_a_cell_holds_each_load_to_the_declaration_it_wrote():
    # #716 round six: the standalone entry point checked the loop and never
    # the declaration, so a declaration changed between the rewrite and a
    # load served another artifact or seed on both halves. Perturbation:
    # restore the bare assert_loop in load_held, and the cell is served.
    outcome, report, steps = _drive_cell(DECLARED, served="e" * 64)
    assert outcome == "returned", outcome
    assert report["verdict"].startswith("the source load served another declaration"), report["verdict"]
    assert report["turns"] == [], report["turns"]


def test_a_cell_proceeds_on_the_declared_digest():
    """The same drive with the digest matching reaches the gate, which is
    the perturbation half: remove the check and the refusing test above
    lands here instead."""
    outcome, report, steps = _drive_cell(DECLARED)
    assert outcome == "served", outcome
    assert steps == ["unload", "load", "unload"], steps


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all watches held")
