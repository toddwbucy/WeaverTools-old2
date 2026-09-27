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
    """confirm_cells.main whole, with the box stubbed - defects 2 and 4."""
    LIBS = {"lib": {"path": "/l", "sha256": "aa", "resolved_by": "cfg"}}
    BINS = {"bin": {"path": "/b", "sha256": "bb", "resolved_by": "cfg"}}
    TOOLS = {"rustc": "rustc stub", "active_toolchain": "nightly-stub"}
    saved = {n: getattr(g, n) for n in
             ("_resolve_spu", "engine_libraries", "weaver_binaries",
              "toolchain", "run_cell")}
    calls = {"n": 0}

    def fake_run_cell(cfg, cell, outdir, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2 and die_second_cell:
            raise RuntimeError("cell two died")
        return {"cell": cell["name"], "metadata": {},
                "verdict": "REPRODUCED", "turns": [], "steps": []}

    lib_seq = [json.loads(json.dumps(LIBS)),
               {"lib": {"path": "/l", "sha256": "SWAPPED",
                        "resolved_by": "cfg"}}]
    try:
        g._resolve_spu = lambda cfg: ("/stub", "stub")
        g.engine_libraries = (
            (lambda cfg, spu=None: lib_seq.pop(0)) if swap_libs
            else (lambda cfg, spu=None: json.loads(json.dumps(LIBS))))
        g.weaver_binaries = lambda cfg, spu=None: json.loads(json.dumps(BINS))
        g.toolchain = lambda cfg: dict(TOOLS)
        g.run_cell = fake_run_cell

        td = tempfile.mkdtemp()
        decl = os.path.join(td, "k.yaml")
        with open(decl, "w") as f:
            f.write("artifact: a\n")
        cfgp = os.path.join(td, "c.json")
        with open(cfgp, "w") as f:
            json.dump({"box": "t", "declaration": decl, "repo": ".",
                       "build_flags": "x", "admin_config": td,
                       "admin_bin": "/bin/true", "agent": "karl",
                       "gate_socket": "/s", "trace": "/t",
                       "cells": [
                           {"name": "c1", "precision": "q8", "artifact": "a"},
                           {"name": "c2", "precision": "bf", "artifact": "a"},
                       ]}, f)
        out = os.path.join(td, "out")
        os.makedirs(out)
        sys.argv = ["confirm", "--config", cfgp, "--outdir", out]
        code = "none"
        try:
            g.main()
        except SystemExit as e:
            code = e.code
        except RuntimeError as e:
            code = f"raised:{e}"
        rp = os.path.join(out, "report-t.json")
        deposit = json.load(open(rp)) if os.path.exists(rp) else None
        return code, deposit
    finally:
        for n, fn in saved.items():
            setattr(g, n, fn)


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
    code, dep = _drive_main()
    assert code == 0 and len(dep) == 2
    assert all(v.get("status") == "unchanged"
               for v in dep[0]["metadata"]["provenance_at_close"].values())


def test_midrun_raise_keeps_partial_deposit():
    """Defect 2: the deposit survives a raise past the first cell."""
    code, dep = _drive_main(die_second_cell=True)
    assert str(code).startswith("raised")
    assert dep is not None and len(dep) == 1


def test_midrun_swap_exits_one_over_green_cells():
    """Defect 4: a moved window is not a reproduction result."""
    code, dep = _drive_main(swap_libs=True)
    assert code == 1, code
    pac = dep[0]["metadata"]["provenance_at_close"]
    assert pac["engine_libraries"]["status"] == "varied"
    assert all(r["verdict"] == "REPRODUCED" for r in dep)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all watches held")
