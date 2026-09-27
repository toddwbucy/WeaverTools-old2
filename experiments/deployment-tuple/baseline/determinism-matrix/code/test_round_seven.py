"""Every value a run takes is checked against its consumer's domain at
preflight, before the run writes or loads anything (#716 round seven).

Run with `python3 test_round_seven.py` or under pytest.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import Reloading, run_main  # noqa: E402

base = dm.base
U64_MAX = 2 ** 64 - 1


def refused(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def test_a_seed_is_a_u64_on_both_paths():
    # Codex round six's thread: the sampler's seed is a u64, and the harness
    # took a negative or larger seed and failed every session. Perturbation:
    # drop the upper bound in seed_value, or parse the schedule with int()
    # again, and a refused case here is taken.
    for good in ("0", str(U64_MAX)):
        assert dm.parse_seed_schedule(f"{good},5,6") == [int(good), 5, 6]
        assert dm.standing_seed(f"    seed: {good}\n") == int(good)
        assert dm.standing_seed(f'    seed: "{good}"\n') == int(good)
    for bad in ("-1", str(U64_MAX + 1), "+5", "1_000", "0x10", "7.0", " "):
        assert refused(dm.parse_seed_schedule, f"{bad},5,6"), bad
        assert refused(dm.standing_seed, f'    seed: "{bad}"\n'), bad
    assert refused(dm.standing_seed, "    seed: -1\n")
    assert refused(dm.standing_seed, f"    seed: {U64_MAX + 1}\n")


def test_the_hours_are_a_bound_the_clock_reaches():
    # Perturbation: drop hours_value, and zero runs no session, nan never
    # starts one, and inf never ends.
    assert dm.hours_value(7.0) == 7.0 and dm.hours_value(0.001) == 0.001
    for bad in (0.0, -1.0, float("nan"), float("inf"), 1e308):
        assert refused(dm.hours_value, bad), bad


def test_the_loop_digest_has_the_shape_a_load_records():
    # Perturbation: drop loop_digest at preflight, and a malformed digest
    # refuses every session at its first load instead.
    assert base.loop_digest({}) is None
    assert base.loop_digest({"loop_sha256": "a" * 64}) == "a" * 64
    for bad in ("A" * 64, "a" * 63, 5, "sha256:" + "a" * 64):
        assert refused(base.loop_digest, {"loop_sha256": bad}), bad


def test_the_matrix_refuses_at_preflight_and_writes_nothing():
    # Each refusal comes before the run writes a byte or loads the agent.
    # Perturbation: move a check below the first log line or the first load,
    # and its case leaves matrix.log behind or calls the admin.
    def seed_line(value):
        def prepare(tmp, decl):
            text = open(decl).read()
            with open(decl, "w") as fh:
                fh.write(text.replace("seed: 451234785645", f"seed: {value}"))
        return prepare

    def loop(tmp, decl):
        path = os.path.join(tmp, "config.json")
        cfg = json.load(open(path))
        cfg["loop_sha256"] = "not a digest"
        json.dump(cfg, open(path, "w"))
    cases = [dict(extra=["--seed-schedule", "-1,5,6"]),
             dict(extra=["--seed-schedule", f"{U64_MAX + 1},5,6"]),
             dict(extra=["--hours", "0"]), dict(extra=["--hours", "nan"]), dict(extra=["--hours", "inf"]),
             dict(prepare=seed_line(U64_MAX + 1)), dict(prepare=seed_line("-1")), dict(prepare=loop)]
    for case in cases:
        agent, seen = Reloading(), {}

        def inspect(tmp, decl):
            seen["written"] = sorted(f for f in os.listdir(tmp) if f.startswith(("matrix", "summary")))
            seen["loads"] = agent.starts
        extra = list(case.get("extra", []))
        hours = "0.00003"
        if "--hours" in extra:
            hours = extra[extra.index("--hours") + 1]
            extra = []
        code, _, _ = run_main(agent, hours=hours, extra=extra, prepare=case.get("prepare"), inspect=inspect)
        assert code == 2 and seen == {"written": [], "loads": 0}, (case, code, seen)
    code, records, _ = run_main(Reloading(), extra=["--seed-schedule", f"0,5,{U64_MAX}"])
    assert code == 1 and records, code  # the fake agent records SEED, so the declared seeds do not reach it


def test_a_refused_run_makes_no_outdir():
    # The outdir is made only after every check passes. Perturbation: make
    # it before the declaration is checked, and the refused run leaves it.
    with tempfile.TemporaryDirectory() as tmp:
        decl = os.path.join(tmp, "karl.yaml")
        with open(decl, "w") as fh:
            fh.write(f"artifact: /m.gguf\nseed: {U64_MAX + 1}\n")
        path = os.path.join(tmp, "config.json")
        json.dump({"agent": "karl", "declaration": decl, "trace": "unused"}, open(path, "w"))
        out = os.path.join(tmp, "new")
        argv = sys.argv
        try:
            sys.argv = ["determinism_matrix.py", "--config", path, "--outdir", out, "--hours", "1"]
            try:
                dm.main()
                code = 0
            except SystemExit as e:
                code = e.code
        finally:
            sys.argv = argv
        assert code == 2 and not os.path.exists(out), (code, os.path.exists(out))


def test_the_cells_refuse_at_preflight_and_write_nothing():
    # The cross-precision entry point: a name that becomes a filename, a
    # cell artifact the declaration cannot carry, or a malformed loop digest
    # is refused before the outdir, the backup or a load. Perturbation: drop
    # the preflight, and the bad name writes outside the outdir or the bad
    # artifact reaches its cell's load.
    for change in (dict(box="../elsewhere"), dict(cells=[{"name": "q8/..", "precision": "q8", "artifact": "/m.gguf"}]),
                   dict(cells=[{"name": "q8", "precision": "q8", "artifact": "/my model.gguf"}]),
                   dict(loop_sha256="short")):
        with tempfile.TemporaryDirectory() as tmp:
            decl = os.path.join(tmp, "karl.yaml")
            with open(decl, "w") as fh:
                fh.write("artifact: /m.gguf\n")
            out = os.path.join(tmp, "out")
            cfg = dict({"box": "thinkpad", "declaration": decl,
                        "cells": [{"name": "q8", "precision": "q8", "artifact": "/m.gguf"}]}, **change)
            path = os.path.join(tmp, "config.json")
            json.dump(cfg, open(path, "w"))
            called, saved, argv = [], base.admin, sys.argv
            try:
                base.admin = lambda c, v: called.append(v) or {"kind": "state"}
                sys.argv = ["confirm_cells.py", "--config", path, "--outdir", out]
                try:
                    base.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
            finally:
                base.admin, sys.argv = saved, argv
            assert code == 2 and called == [] and not os.path.exists(out) \
                and not os.path.exists(decl + ".pre-cells"), (change, code, called)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
