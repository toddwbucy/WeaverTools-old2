"""One run-wide verdict for every run, record values compared by
type as well as value, and every file a run opens opened at preflight
(#716 round nine).

Run with `python3 test_round_nine.py` or under pytest.
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import (CARD, CFG, FIXED, MODEL, SEED, Agent, Reloading,  # noqa: E402
                                cells_main, run_main, session)
from test_round_five import drive_cell  # noqa: E402

base = dm.base
OTHER = [dict(CARD[0], ordinal=1, pci_bus_id="0000:02:00.0")]
CELL_DECL = f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'
TWO_CELLS = [{"name": "q8", "precision": "q8", "artifact": MODEL},
             {"name": "bf16", "precision": "bf16", "artifact": MODEL}]


class SwitchingCard(Reloading):
    """Each session internally stable, the sessions binding different cards
    in turn."""

    def serving_device(self, cfg, since, invocation=None):
        return {"devices": CARD if (self.starts - 1) // 2 % 2 == 0 else OTHER, "complete": True}


class ReusedInvocation(Reloading):
    """Two invocations per session, told apart within it and the same in
    every session."""

    def invocation(self):
        return f"{(self.starts - 1) % 2 + 1:032x}"


def agent_fakes(agent):
    """The agent's own stand-ins for the admin, the gate and the trace, and
    a trace read that finds no whole run to deposit."""
    fakes = {k: getattr(agent, k) for k in ("admin", "wait_socket", "gate_turn", "await_turns",
                                            "run_load", "serving_device", "unit_invocation")}
    fakes["read_runs"] = lambda path, keep=None: ([], {})
    return fakes


def cells_run(agent, stack=None):
    """Two cells through the cross-precision `main`, served by `agent`."""
    digest = hashlib.sha256(CELL_DECL.encode()).hexdigest()
    agent.served = (digest, digest)
    with tempfile.TemporaryDirectory() as tmp:
        return cells_main(tmp, dict(cells=TWO_CELLS), fakes=dict(agent_fakes(agent), **(stack or {})))


def varying_toolchain():
    """A toolchain reader answering one pin at the open and another at the
    close."""
    reads = iter(["nightly-a", "nightly-b"])
    return {"toolchain": lambda c: {"rustc": "rustc stub", "active_toolchain": next(reads)}}


GUESSED = {"spu-binary": {"path": "/x", "sha256": "a" * 64,
                          "resolved_by": "guessed beside admin_bin, the admin config naming none"}}


# Class 1: one run-wide verdict.

def test_both_modes_exit_on_the_one_run_wide_verdict():
    # The one main calls run_verdict in either mode, and the standalone
    # main is gone. Perturbation: inline a rule back into the main,
    # bypassing the function, and its call count drops.
    calls = []
    real = base.run_verdict

    def counted(*a, **k):
        calls.append("called")
        return real(*a, **k)
    base.run_verdict = counted
    try:
        code, _, _ = run_main(Reloading())
        assert code == 0 and calls == ["called"], (code, calls)
        code, _, _, *_ = cells_run(Reloading())
        assert code == 0 and calls == ["called"] * 2, (code, calls)
    finally:
        base.run_verdict = real
    assert not hasattr(dm, "unheld") and not hasattr(base, "windows_held") and not hasattr(base, "main")


def test_a_device_varying_across_sessions_fails_the_exit_in_both_modes():
    # Codex round eight's thread 1: each cell internally stable, the cells
    # on different cards, and the standalone exit read 0. Perturbation: drop
    # the device rule in run_verdict, and both modes read 0.
    code, records, s = run_main(SwitchingCard(), hours="0.0002")
    assert len(records) >= 2 and all(r["verdict"] == "REPRODUCED" for r in records), len(records)
    assert code == 1 and "varied" in s["serving_device"], (code, s["serving_device"])
    code, _, printed, *_ = cells_run(SwitchingCard())
    assert code == 1 and "did not hold: serving_device" in printed, (code, printed)


def test_a_window_that_moved_fails_the_exit_in_both_modes():
    # Perturbation: drop the window rule, and both modes read 0.
    code, records, s = run_main(Reloading(), stack=varying_toolchain())
    assert records and code == 1 and s["toolchain"]["status"] == "varied", (code, s["toolchain"])
    code, _, printed, *_ = cells_run(Reloading(), stack=varying_toolchain())
    assert code == 1 and "did not hold: toolchain" in printed, (code, printed)


def test_a_reused_invocation_fails_the_exit_in_both_modes():
    # The run-wide invocation rule, held in the matrix loop alone until
    # now. Perturbation: drop hold_invocations from either loop, and that
    # exit reads 0.
    code, records, _ = run_main(ReusedInvocation(), hours="0.0002")
    assert len(records) >= 2 and code == 1, (len(records), code)
    assert records[0]["verdict"] == "REPRODUCED"
    assert all(r["verdict"].startswith("a load read invocation") for r in records[1:]), records[1]["verdict"]
    code, _, printed, *_ = cells_run(ReusedInvocation())
    assert code == 1 and "cell bf16: a load read invocation" in printed, (code, printed)


def test_a_guessed_binary_is_refused_before_either_run_starts():
    # A binary resolved by a guess can never be counted held at the exit,
    # so a run in either mode refuses it at preflight. Perturbation: drop the
    # guessed clause in opening_readings, and both runs start.
    guessed = {"weaver_binaries": lambda c, s: GUESSED}
    agent = Reloading()
    code, records, _ = run_main(agent, stack=guessed)
    assert code == 2 and records is None and agent.starts == 0, (code, agent.starts)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code, _, _, *_ = cells_run(Reloading(), stack=guessed)
    assert code == 2 and "resolved a binary by a guess" in err.getvalue(), (code, err.getvalue())


def test_the_real_binaries_reader_is_refused_where_admin_names_no_spu():
    # The same through the real reader: an admin configuration naming no SPU
    # is one admin refuses every verb on, spu-binary being required, so the
    # opening reading is refused as unreadable naming it, and never resolved
    # by the guess beside the admin binary (#734, the pass on 9d1853a).
    # Perturbation: read a required file's absence as absence in
    # `_read_admin`, and the guess is resolved and refused only as a guess.
    with tempfile.TemporaryDirectory() as tmp:
        conf, bindir = os.path.join(tmp, "admin"), os.path.join(tmp, "bin")
        os.makedirs(conf)
        os.makedirs(bindir)
        for name in ("worker", "gate", "weaver-spu"):
            with open(os.path.join(bindir, name), "w") as fh:
                fh.write(name)
        for key, name in (("worker-binary", "worker"), ("gate-binary", "gate")):
            with open(os.path.join(conf, key), "w") as fh:
                fh.write(os.path.join(bindir, name))
        with open(os.path.join(conf, "allow-list"), "w") as fh:
            fh.write("karl\n")
        cfg = dict(CFG, admin_config=conf, admin_bin=os.path.join(bindir, "weaver-admin"))
        saved = base.engine_libraries, base.toolchain
        base.engine_libraries, base.toolchain = (lambda c, s: FIXED), (lambda c: {"rustc": "stub"})
        try:
            try:
                base.opening_readings(cfg)
                raise AssertionError("an SPU admin names none of was read as a reading")
            except ValueError as e:
                assert "is not a reading" in str(e) and "absent, and admin requires it" in str(e), e
                assert "guess" not in str(e), e
            with open(os.path.join(conf, "spu-binary"), "w") as fh:
                fh.write(os.path.join(bindir, "weaver-spu"))
            assert set(base.opening_readings(cfg)["weaver_binaries"]) == {"worker-binary", "spu-binary", "gate-binary"}
        finally:
            base.engine_libraries, base.toolchain = saved


def test_an_unreadable_opening_reading_is_refused_by_both():
    # Perturbation: drop the is_reading clause in opening_readings, and both
    # runs start on a reading the exit can never hold.
    gone = {"engine_libraries": lambda c, s: {"unreadable": "no SPU binary at /spu"}}
    agent = Reloading()
    code, records, _ = run_main(agent, stack=gone)
    assert code == 2 and records is None and agent.starts == 0, (code, agent.starts)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code, _, _, *_ = cells_run(Reloading(), stack=gone)
    assert code == 2 and "the opening engine_libraries is not a reading" in err.getvalue(), (code, err.getvalue())


# Class 2: a record value is compared by type as well as value.

def test_a_recorded_seed_of_another_type_is_refused_in_both_modes():
    # Codex round eight's thread 2: `True == 1` and `1.0 == 1`, so a seed
    # recorded as true or 1.0 matched the declared 1. Perturbation: compare
    # before recorded_seed, and the float case reads REPRODUCED on both.
    for value in (float(SEED), True, -1, 2 ** 64, "451234785645"):
        rec = session(Agent(source_seed=value, replay_seed=value), declared_seed=SEED)
        assert "is not an integer within the sampler's u64" in rec["verdict"], (value, rec["verdict"])
    digest = hashlib.sha256(f'[spu-instruction.decoder.model-binding]\nartifact = "/m.gguf"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'.encode()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        cell = drive_cell(Agent(source_seed=float(SEED), replay_seed=float(SEED), served=(digest, digest)), tmp)
    assert "is not an integer within the sampler's u64" in cell["verdict"], cell["verdict"]
    rec = session(Agent(source_seed=True, replay_seed=True), declared_seed=1)
    assert "true is not an integer" in rec["verdict"], rec["verdict"]
    # The replay's seed is held the same way.
    rec = session(Agent(replay_seed=float(SEED)), declared_seed=SEED)
    assert rec["verdict"].startswith("the replay t-1 recorded seed"), rec["verdict"]


def mutated(value):
    """A value Python's `==` takes for `value` and JSON does not."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        for i, v in enumerate(value):
            m = mutated(v)
            if m is not None:
                return value[:i] + [m] + value[i + 1:]
    if isinstance(value, dict):
        for k, v in sorted(value.items()):
            m = mutated(v)
            if m is not None:
                return dict(value, **{k: m})
    return None


def test_a_replay_differing_only_by_type_is_a_divergence():
    # The sibling site: compare_turn read a replay recording 1.0 where its
    # source recorded 1 as a match. Every CHECKS field that can carry a
    # number is changed in type alone. Perturbation: restore `a == b`, and
    # every case reads as a match.
    agent = Agent()
    src = {"payload": {"model.request": {"rendered": "<user>x", "sampling": {"generation_seed": 14, "temperature": 0.7}},
                       "model.output": {"emission": [3, 2], "finish": "stop", "resident": 24},
                       "model.measurement": {"input_tokens": [2, 3], "entropies": [0.25, 1.0]}}}
    assert all(c["match"] for c in base.compare_turn(src, json.loads(json.dumps(src))))
    tried = 0
    for name, kind, ptr in base.CHECKS:
        value = base.pointer(src["payload"][kind], ptr)
        other = mutated(value)
        if other is None:
            continue  # a string: no other type compares equal to it
        assert other == value and base.canonical(other) != base.canonical(value), name
        rep = json.loads(json.dumps(src))
        parent, key = rep["payload"][kind], ptr.strip("/").split("/")
        for part in key[:-1]:
            parent = parent[part]
        parent[key[-1]] = other
        failed = {c["check"] for c in base.compare_turn(src, rep) if not c["match"]}
        assert name in failed, (name, failed)
        tried += 1
    assert tried == 6, tried
    # And through a whole session: a replay whose generation seed is 14.0
    # where its source recorded 14 did not reproduce.
    real = agent.gate_turn

    def floated(cfg, text, timeout=None):
        close = real(cfg, text)
        if agent.loads == 2:
            req = [e for e in agent.runs[agent.run] if e["kind"] == "model.request"][-1]
            req["payload"]["sampling"]["generation_seed"] = float(req["payload"]["sampling"]["generation_seed"])
        return close
    agent.gate_turn = floated
    assert session(agent)["verdict"] == "DIVERGED"


def test_a_run_or_turn_id_is_a_string_and_nothing_else():
    # The identities the comparison rests on: a close naming a run that is
    # not a string names no run, a trace event of such a run belongs to none,
    # and turns 1 and true stay two turns, each refused as incomplete.
    # Perturbation: key cut_turns by the value, or drop run_named, and a case
    # here merges or passes.
    agent = Agent()
    real = agent.gate_turn
    agent.gate_turn = lambda cfg, text, timeout=None: dict(real(cfg, text), run=1)
    assert session(agent)["verdict"] == "the source turns did not share one run"
    turns = base.cut_turns([{"turn": 1, "kind": "model.request"}, {"turn": True, "kind": "model.request"},
                            {"turn": "", "kind": "model.request"}, {"turn": "t-1", "kind": ["x"]}])
    assert [t["turn"] for t in turns] == [1, True, "", "t-1"], turns
    assert all(t["incomplete"][0].startswith("the turn id") for t in turns[:3]), turns
    assert "1 events with no string kind" in turns[3]["incomplete"], turns[3]
    with tempfile.TemporaryDirectory() as tmp:
        trace = os.path.join(tmp, "trace")
        with open(trace, "w") as fh:
            for run in ("r-1", 1, True, ["r-1"], "r-2"):
                fh.write(json.dumps({"run": run, "kind": "load"}) + "\n")
        for keep in (None, 1):
            order, runs = base.read_runs(trace, keep=keep)
            assert all(isinstance(r, str) for r in order) and order[-1] == "r-2", (keep, order)


# Class 3: every file a run opens is opened at preflight.

def refused_without_writing(want, **kw):
    """The matrix refuses with exit 2 and a message carrying `want`, having
    loaded nothing and written none of its outputs."""
    seen, agent, err = {}, Reloading(), io.StringIO()

    def inspect(tmp, decl):
        seen["written"] = sorted(f for f in os.listdir(tmp) if f.startswith(("matrix", "summary")))
        seen["backup"] = os.path.lexists(decl + ".pre-matrix")
    with contextlib.redirect_stderr(err):
        code, _, _ = run_main(agent, inspect=inspect, **kw)
    assert code == 2 and agent.starts == 0 and seen == {"written": [], "backup": False}, (want, code, seen)
    assert want in err.getvalue(), (want, err.getvalue())


def config_change(**changes):
    def prepare(tmp, decl):
        path = os.path.join(tmp, "config.json")
        cfg = json.load(open(path))
        cfg.update({k: v(tmp) if callable(v) else v for k, v in changes.items()})
        json.dump(cfg, open(path, "w"))
    return prepare


def test_the_matrix_opens_every_file_at_preflight():
    # Codex round eight's thread 3: the artifact was parsed at preflight and
    # first opened after the outdir. Perturbation: drop the preflight read
    # of any one, and its case writes matrix.log or loads the agent.
    def no_artifact(tmp, decl):
        os.unlink(os.path.join(tmp, "model.gguf"))

    def read_only(tmp, decl):
        os.chmod(decl, 0o444)

    def not_json(tmp, decl):
        with open(os.path.join(tmp, "config.json"), "w") as fh:
            fh.write("{")
    refused_without_writing("the artifact cannot be read", prepare=no_artifact)
    refused_without_writing("the artifact cannot be read", extra=["--artifact", "/no/such.gguf"])
    refused_without_writing("the declaration", prepare=read_only, extra=["--seed-schedule", "11,12,13"])
    refused_without_writing("cannot be opened: [Errno 13]", prepare=read_only, extra=["--artifact", MODEL])
    refused_without_writing("admin_bin", prepare=config_change(admin_bin=lambda t: os.path.join(t, "none")))
    refused_without_writing("is not an executable file",
                            prepare=config_change(admin_bin=lambda t: os.path.join(t, "karl.toml")))
    refused_without_writing("is not a directory", prepare=config_change(repo=lambda t: os.path.join(t, "karl.toml")))
    refused_without_writing("cannot be read: Expecting property name", prepare=not_json)
    # The control: the declaration read-only is refused only where the run
    # rewrites it.
    code, records, _ = run_main(Reloading(), prepare=read_only)
    assert code == 0 and records, code


def test_a_cells_run_opens_every_file_and_reads_every_key_at_preflight():
    # Codex round eight's thread 4: a key read after preflight but not
    # checked there. `build_flags`, the key it named, is no longer read,
    # the cell metadata that read it gone with the standalone main.
    # Perturbation: drop any one check, and its case calls the admin or
    # leaves the backup.
    def read_only(tmp, decl):
        os.chmod(decl, 0o444)
    cases = [("the cell's precision 12", dict(change=dict(cells=[dict(TWO_CELLS[0], precision=12)]))),
             ("the cell's precision None",
              dict(change=dict(cells=[{k: v for k, v in TWO_CELLS[0].items() if k != "precision"}]))),
             ("the config's cell 'q8' is not an object", dict(change=dict(cells=["q8"]))),
             ("the artifact cannot be read",
              dict(change=dict(cells=[dict(TWO_CELLS[0], artifact="/no/such.gguf")]))),
             ("the config's admin_bin /no/such/admin cannot be read", dict(change=dict(admin_bin="/no/such/admin"))),
             ("is not an executable file", dict(change=dict(admin_bin=MODEL))),
             ("is not a directory", dict(change=dict(repo=MODEL))),
             ("the declaration", dict(prepare=read_only))]
    for want, case in cases:
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            code, called, *_ = cells_main(tmp, **case)
            assert code == 2 and called == [] and not os.path.exists(os.path.join(tmp, "out")) \
                and not os.path.exists(os.path.join(tmp, "karl.toml.pre-matrix")), (case, code, called)
        assert want in err.getvalue(), (want, err.getvalue())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
