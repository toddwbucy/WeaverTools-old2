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

DECLARED = "aa" * 32
OTHER = "bb" * 32


def _trace(td, events):
    p = os.path.join(td, "trace.ndjson")
    with open(p, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return p


def _load(run, composer):
    """One load event in the shape the record carries since #419."""
    payload = {"residual_readout": False, "surprisal": False}
    if composer is not None:
        payload["composer"] = composer
    return {"session": "s-1", "run": run, "sequence": "0", "kind": "load",
            "subsystem": "harness", "wall_ms": 0, "monotonic_ns": "0",
            "payload": payload}


def _file(name, digest):
    return {"binary": "pyworker", "file": f"/usr/local/libexec/weaver/loops/{name}",
            "sha256": digest}


def test_matching_digest_passes():
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", DECLARED))])
    assert g.assert_loop({"loop_sha256": DECLARED}, t) is None


def test_other_digest_refuses_with_both_digests():
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", OTHER))])
    r = g.assert_loop({"loop_sha256": DECLARED}, t)
    assert r is not None
    assert r["declared"] == DECLARED and r["recorded"] == OTHER, r
    assert r["run"] == "r1" and r["composer"]["file"].endswith("alpha_loop.py")


def test_the_name_is_not_the_identity():
    """The same name at other bytes refuses, another name at the declared
    bytes passes - the finding #426 was opened on."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", OTHER))])
    assert g.assert_loop({"loop_sha256": DECLARED}, t) is not None
    t = _trace(td, [_load("r2", _file("bravo_loop.py", DECLARED))])
    assert g.assert_loop({"loop_sha256": DECLARED}, t) is None


def test_compiled_loop_refuses_where_a_digest_is_declared():
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", {"binary": "worker"})])
    r = g.assert_loop({"loop_sha256": DECLARED}, t)
    assert r is not None and r["recorded"] is None, r
    assert r["composer"] == {"binary": "worker"}


def test_no_composer_at_all_refuses_where_a_digest_is_declared():
    """A build from before #419 recorded no composer. It cannot be shown to
    be the declared loop, so it is refused rather than passed on absence."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", None)])
    r = g.assert_loop({"loop_sha256": DECLARED}, t)
    assert r is not None and r["recorded"] is None and r["composer"] is None, r


def test_absent_key_is_unchecked():
    """A config that declares no loop keeps today's behaviour, whatever the
    record says, so the configs that predate the key still run."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", OTHER))])
    assert g.assert_loop({}, t) is None
    assert g.assert_loop({"box": "x"}, t) is None


def test_the_previous_load_does_not_answer_for_this_one():
    """With `before` naming the newest run that stood ahead of the load, a
    trace the sink has not yet appended to cannot pass on the old run."""
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", DECLARED))])
    r = g.assert_loop({"loop_sha256": DECLARED}, t, before="r1", timeout=0.1)
    assert r is not None and r["recorded"] is None and r["run"] is None, r
    assert "no load event" in r["note"]


def test_the_newest_load_is_the_one_compared():
    td = tempfile.mkdtemp()
    t = _trace(td, [_load("r1", _file("alpha_loop.py", OTHER)),
                    _load("r2", _file("alpha_loop.py", DECLARED))])
    assert g.assert_loop({"loop_sha256": DECLARED}, t, before="r1") is None
    t = _trace(td, [_load("r1", _file("alpha_loop.py", DECLARED)),
                    _load("r2", _file("alpha_loop.py", OTHER))])
    r = g.assert_loop({"loop_sha256": DECLARED}, t, before="r1")
    assert r is not None and r["run"] == "r2", r


def test_missing_trace_is_an_absence_not_a_raise():
    assert g.newest_load("/nonexistent/trace.ndjson") == (None, None)


class _Served(Exception):
    """Raised by the gate stub: a turn was about to be served."""


def _drive_run_cell(composer_digest):
    """`run_cell` with the box stubbed, up to the first turn."""
    saved = {n: getattr(g, n) for n in
             ("admin", "wait_socket", "gate_turn", "serving_device")}
    td = tempfile.mkdtemp()
    # An older run at the declared digest already stands in the trace, so a
    # check that read the wrong load would pass on it. The fake load below
    # appends this cell's own load event, the way the harness does.
    trace = _trace(td, [_load("r-old", _file("alpha_loop.py", DECLARED))])
    decl = os.path.join(td, "k.yaml")
    with open(decl, "w") as f:
        f.write("artifact: a\n")
    out = os.path.join(td, "out")
    os.makedirs(out)
    cfg = {"box": "t", "agent": "karl", "declaration": decl, "trace": trace,
           "gate_socket": "/s", "admin_bin": "/bin/true", "admin_config": td,
           "repo": td, "build_flags": "x", "loop_sha256": DECLARED}
    cell = {"name": "c1", "precision": "q8", "artifact": "a"}
    steps = []

    def fake_admin(cfg, verb):
        steps.append(verb)
        if verb == "load":
            with open(trace, "a") as f:
                f.write(json.dumps(_load(
                    "r-cell", _file("alpha_loop.py", composer_digest))) + "\n")
            return {"kind": "state"}
        return {"kind": "no_residency"}

    def fake_gate(cfg, text, timeout=600):
        raise _Served(text)

    try:
        g.admin = fake_admin
        g.wait_socket = lambda cfg, timeout=120: True
        g.gate_turn = fake_gate
        g.serving_device = lambda cfg, since: {"devices": [{"ordinal": 0}]}
        outcome = "returned"
        report = None
        try:
            report = g.run_cell(cfg, cell, out, {}, {}, {})
        except _Served:
            outcome = "served"
        deposits = [n for n in os.listdir(out) if n.startswith("cell-")]
        return outcome, report, steps, deposits
    finally:
        for n, fn in saved.items():
            setattr(g, n, fn)


def test_run_cell_refuses_before_a_turn_is_served():
    outcome, report, steps, deposits = _drive_run_cell(OTHER)
    assert outcome == "returned", outcome
    assert report["verdict"].startswith("loop refused at the source load"), report
    refused = report["loop_refused"]
    assert refused["declared"] == DECLARED and refused["recorded"] == OTHER
    assert refused["half"] == "source" and refused["run"] == "r-cell"
    assert report["turns"] == [] and "source_run" not in report
    assert deposits == [], deposits
    # the finally still released the device
    assert steps[-1] == "unload", steps


def test_run_cell_proceeds_on_the_declared_digest():
    """The same drive with the digest matching reaches the gate, which is
    the perturbation half: remove the check and the refusing test above
    lands here instead."""
    outcome, report, steps, deposits = _drive_run_cell(DECLARED)
    assert outcome == "served", outcome
    assert steps == ["unload", "load", "unload"], steps


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all watches held")
