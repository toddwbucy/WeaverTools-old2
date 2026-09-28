"""One session verification for every session, presence rather than
truth for every optional value (#716 round eight).

Run with `python3 test_round_eight.py` or under pytest.
"""
import hashlib
import inspect
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import CFG, SEED, Agent, Reloading, cells_main, run_main, session  # noqa: E402
from test_round_five import drive_cell  # noqa: E402

base = dm.base
DECLARED = f'[spu-instruction.decoder.model-binding]\nartifact = "/m.gguf"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'


def test_a_seed_the_record_does_not_bear_out_refuses_in_both_modes():
    # Codex round seven's thread 1: the standalone run_cell held no recorded
    # seed to the declaration's. 451234785645 declared and 7 recorded on both
    # halves refuses a cell as it refuses a matrix cell, with one verdict.
    # Perturbation: drop the declared-seed check in verify_session, and both
    # read REPRODUCED.
    digest = hashlib.sha256(DECLARED.encode()).hexdigest()
    want = f"the declared seed did not reach the record: declared {SEED}, recorded 7"
    with tempfile.TemporaryDirectory() as tmp:
        cell = drive_cell(Agent(source_seed=7, replay_seed=7, served=(digest, digest)), tmp)
    matrix = session(Agent(source_seed=7, replay_seed=7, served=(digest, digest)),
                     declared_seed=SEED, declaration_sha=digest)
    assert cell["verdict"] == matrix["verdict"] == want, (cell["verdict"], matrix["verdict"])


def test_every_session_verifies_through_the_one_function():
    # A cell and a matrix cell are both run by run_session, which calls
    # verify_session. Perturbation: inline a check back into run_session,
    # bypassing the function, and its call count drops.
    calls = []
    real = base.verify_session

    def counted(*a, **k):
        calls.append(inspect.stack()[1].function)
        return real(*a, **k)
    digest = hashlib.sha256(DECLARED.encode()).hexdigest()
    base.verify_session = counted
    try:
        with tempfile.TemporaryDirectory() as tmp:
            assert drive_cell(Agent(served=(digest, digest)), tmp)["verdict"] == "REPRODUCED"
        assert session(Agent(), declared_seed=SEED)["verdict"] == "REPRODUCED"
    finally:
        base.verify_session = real
    assert calls == ["run_session", "run_session"], calls


def test_the_session_function_verifies_nothing_outside_it():
    # The claim the PR body tables, held by reading the one caller's source,
    # and the standalone caller gone: run_session calls no verification
    # primitive of its own. Perturbation: put any of them back into it and
    # this names it.
    assert not hasattr(base, "run_cell") and not hasattr(base, "main")
    primitives = ("load_held", "load_devices", "compare_turn", "unobserved", "await_turns",
                  "gate_turn", "wait_socket", "run_load", "sampling/seed", "assert_loop")
    for fn in (dm.run_session,):
        source = inspect.getsource(fn)
        found = [p for p in primitives if p in source]
        assert not found, (fn.__name__, found)


def test_an_empty_optional_argument_is_refused_not_omitted():
    # Codex round seven's thread 2: `--artifact ''` read as omitted.
    # Perturbation: `if args.artifact:` again, and the run starts on the
    # declaration's own artifact.
    for extra in (["--artifact", ""],):
        seen = {}

        def inspect_out(tmp, decl):
            seen["written"] = sorted(f for f in os.listdir(tmp) if f.startswith(("matrix", "summary")))
        agent = Reloading()
        code, _, _ = run_main(agent, extra=extra, inspect=inspect_out)
        assert code == 2 and seen["written"] == [] and agent.starts == 0, (extra, code, seen)


def test_an_empty_or_missing_config_value_is_refused():
    # An empty admin_config fell through to guessing the SPU. Perturbation:
    # drop config_values, and a case here reaches the run. The `spu_bin`
    # case this held is refused whatever its value since the pass on
    # 90b9a8a, `test_round_seventeen.py`.
    for change in (dict(admin_config=""), dict(loop_sha256=""), dict(repo=None)):
        def prepare(tmp, decl, change=change):
            path = os.path.join(tmp, "config.json")
            cfg = json.load(open(path))
            for k, v in change.items():
                if v is None:
                    cfg.pop(k, None)
                else:
                    cfg[k] = v
            json.dump(cfg, open(path, "w"))
        agent = Reloading()
        code, records, _ = run_main(agent, prepare=prepare)
        assert code == 2 and records is None and agent.starts == 0, (change, code)


def test_an_empty_outdir_is_refused():
    # Perturbation: drop the empty-outdir check, and makedirs raises unnamed.
    with tempfile.TemporaryDirectory() as tmp:
        decl = os.path.join(tmp, "karl.toml")
        with open(decl, "w") as fh:
            fh.write(DECLARED)
        path = os.path.join(tmp, "config.json")
        json.dump(dict(CFG, declaration=decl), open(path, "w"))
        argv = sys.argv
        try:
            sys.argv = ["determinism_matrix.py", "--config", path, "--outdir", "", "--hours", "1"]
            try:
                dm.main()
                code = 0
            except SystemExit as e:
                code = e.code
        finally:
            sys.argv = argv
        assert code == 2, code


def test_the_refusal_fixtures_would_otherwise_run():
    # The control for every cells-mode preflight refusal test: the full
    # config passes preflight and the run reaches its first cell, so each
    # refusal is refused for the reason its test names.
    called = []

    def stop(*a, **k):
        called.append("run_session")
        raise SystemExit(0)
    with tempfile.TemporaryDirectory() as tmp:
        code, *_ = cells_main(tmp, dm_fakes={"run_session": stop})
        assert not os.path.exists(os.path.join(tmp, "karl.toml.pre-matrix"))
    assert called == ["run_session"] and code == 0, (called, code)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
