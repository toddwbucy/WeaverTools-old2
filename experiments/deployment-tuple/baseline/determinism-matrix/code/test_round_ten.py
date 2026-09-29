"""A raise and an interrupt are one verdict on every session, every path
the stack resolves is absolute, and every file a run writes is its own
(#716 round ten).

Run with `python3 test_round_ten.py` or under pytest.
"""
import contextlib
import hashlib
import inspect
import io
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import CFG, FIXED, MODEL, SEED, Agent, Reloading, cells_main, declaration, run_main, session  # noqa: E402
from test_round_nine import TWO_CELLS, agent_fakes, cells_run  # noqa: E402

base = dm.base
TRUNCATED = json.JSONDecodeError("Expecting value", "", 0)
WANT = f"error: JSONDecodeError: {TRUNCATED}"


class Truncating(Reloading):
    """A gate whose answer is cut off, so the harness's JSON read raises."""

    def gate_turn(self, cfg, text, timeout=None):
        raise TRUNCATED


class InterruptedSecond(Reloading):
    """An interrupt landing in the second session's first turn."""

    def gate_turn(self, cfg, text, timeout=None):
        if self.starts == 3:
            raise KeyboardInterrupt
        return Reloading.gate_turn(self, cfg, text, timeout)


def refused(fn, *args):
    try:
        fn(*args)
    except ValueError as e:
        return str(e)
    return None


def cells_deposit(agent):
    """Two cells through the matrix's cells mode, and its deposit read
    back: the exit code, what it printed, the records, the summary, and the
    declaration and its backup after the run."""
    digest = hashlib.sha256(f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'.encode()).hexdigest()
    agent.served = (digest, digest)
    with tempfile.TemporaryDirectory() as tmp:
        code, _, printed, records, summary = cells_main(tmp, dict(cells=TWO_CELLS), fakes=agent_fakes(agent))
        restored = open(os.path.join(tmp, "karl.toml")).read()
        backup = os.path.lexists(os.path.join(tmp, "karl.toml.pre-matrix"))
    return code, printed, records, summary, (restored, backup)


# Class 1: one session path, whatever the session meets.

def test_a_raising_session_is_one_fault_in_both_modes():
    # Codex round nine's thread 1: the standalone run_cell let a raise out,
    # so the run lost the cell, its closing window and its verdict.
    # Perturbation: drop the Exception clause in verify_session, and a run
    # in either mode raises out of main.
    code, records, s = run_main(Truncating())
    assert records and code == 1 and {r["verdict"] for r in records} == {WANT}, (code, records[:1])
    assert s["errors"] == len(records)
    code, printed, reports, summary, (restored, backup) = cells_deposit(Truncating())
    assert code == 1 and [r["verdict"] for r in reports] == [WANT, WANT], (code, reports)
    assert all(summary[k]["status"] == "unchanged" for k in base.REQUIRED_WINDOWS)
    assert restored == f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n' and not backup


def test_the_session_function_converts_no_raise_of_its_own():
    # The conversion lives in verify_session alone. Perturbation: put a
    # catch back into run_session, and this names it.
    for fn in (dm.run_session,):
        assert "except Exception" not in inspect.getsource(fn), fn.__name__
    assert "except Exception" in inspect.getsource(base.verify_session)


def test_an_interrupt_records_its_session_and_closes_the_run_in_both_modes():
    # Ctrl-C mid-session: the matrix dropped the session and could exit 0,
    # and the standalone cells raised out with no closing window. A run in
    # either mode now records the session as `interrupted`, stops, closes
    # the run and exits 1.
    # Perturbation: drop the KeyboardInterrupt clause in verify_session, or
    # the interrupted flag in run_verdict, and a clause here fails.
    code, records, s = run_main(InterruptedSecond(), hours="1", sessions=4)
    assert [r["verdict"] for r in records] == ["REPRODUCED", "interrupted"], [r["verdict"] for r in records]
    assert code == 1 and s["sessions"] == 2 and s["weights"]["status"] == "unchanged", (code, s["sessions"])

    class InterruptedFirst(Reloading):
        def gate_turn(self, cfg, text, timeout=None):
            raise KeyboardInterrupt
    code, printed, reports, summary, (restored, backup) = cells_deposit(InterruptedFirst())
    assert code == 1 and [r["verdict"] for r in reports] == ["interrupted"], (code, reports)
    assert summary["engine_libraries"]["status"] == "unchanged" and "interrupted - not a reproduction result" in printed
    assert restored == f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n' and not backup
    assert base.run_verdict([{"verdict": "REPRODUCED", "devices": [{}]}], {}, interrupted=True)[0] is False


def test_the_session_declaration_is_written_inside_the_shared_path():
    # The per-session rewrite moved into verify_session from the matrix's
    # loop and from the standalone run_cell, so a failing write is a fault.
    # Perturbation: write outside the try, and this raises.
    with tempfile.TemporaryDirectory() as tmp:
        rec = session(Agent(), declared_seed=SEED, cfg=dict(CFG, declaration=tmp))
        rec2 = {}
        base.verify_session(dict(CFG, declaration=tmp), ["x"], rec2, SEED, None, declaration="[spu-instruction.decoder.tunable-values]\nseed = 1\n",
                            step=lambda verb: {"kind": "state"})
    assert rec["verdict"] == "REPRODUCED", rec["verdict"]
    assert rec2["verdict"].startswith("error: IsADirectoryError"), rec2["verdict"]


# Class 2: a path the stack resolves is absolute.

def test_every_stack_path_is_absolute_or_refused():
    # Codex round nine's thread 2: a relative artifact was hashed against
    # the harness's directory while the worker served its own. Perturbation:
    # drop stack_path from declared_artifact, with_artifact or config_values,
    # and a case here is taken.
    binding = "[spu-instruction.decoder.model-binding]\n"
    assert refused(base.declared_artifact, binding + 'artifact = "m.gguf"\n')
    assert "the artifact path 'm.gguf' is not an absolute path" in refused(
        base.with_artifact, binding + 'artifact = "/m.gguf"\n', "m.gguf")
    assert base.declared_artifact(binding + 'artifact = "/m.gguf"\n') == "/m.gguf"
    for key in base.STACK_PATH_KEYS:
        why = refused(base.config_values, dict(CFG, declaration="/k.toml", **{key: "relative/" + key}))
        assert why and "is not an absolute path" in why, (key, why)
    assert base.config_values(dict(CFG, declaration="/k.toml", loop_sha256="a" * 64)) is not None


def test_both_modes_refuse_a_relative_path_before_writing():
    def relative_artifact(tmp, decl):
        with open(decl, "w") as fh:
            fh.write(declaration("model.gguf", SEED))
    err = io.StringIO()
    agent = Reloading()
    with contextlib.redirect_stderr(err):
        code, records, _ = run_main(agent, prepare=relative_artifact)
        code2, records2, _ = run_main(Reloading(), extra=["--artifact", "model.gguf"])
    assert code == code2 == 2 and records is records2 is None and agent.starts == 0, (code, code2)
    assert err.getvalue().count("is not an absolute path") == 2, err.getvalue()
    for change, want in ((dict(cells=[dict(TWO_CELLS[0], artifact="m.gguf")]), "is not an absolute path"),
                         (dict(trace="trace.ndjson"), "the config's trace 'trace.ndjson' is not an absolute path")):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            code, called, *_ = cells_main(tmp, change)
            assert code == 2 and called == [] and not os.path.exists(os.path.join(tmp, "out")), (change, code)
        assert want in err.getvalue(), (want, err.getvalue())


def test_the_admin_configuration_names_absolute_binaries():
    # The entries weaver_binaries and _resolve_spu follow are launched by the
    # admin's units, so a relative one is unreadable, never hashed here, and
    # the opening readings refuse it. Perturbation: drop either check, and
    # the relative binary is hashed from this directory.
    with tempfile.TemporaryDirectory() as tmp:
        conf = os.path.join(tmp, "admin")
        os.makedirs(conf)
        for key, value in (("worker-binary", "worker"), ("gate-binary", MODEL), ("spu-binary", "spu"),
                           ("allow-list", "karl")):
            with open(os.path.join(conf, key), "w") as fh:
                fh.write(value)
        cfg = dict(CFG, admin_config=conf)
        assert base._resolve_spu(cfg)[0] is None and "relative path" in base._resolve_spu(cfg)[1]
        reading = base.weaver_binaries(cfg)
        assert "relative path" in reading["worker-binary"]["unreadable"], reading
        assert "unreadable" in reading["spu-binary"] and reading["gate-binary"]["sha256"]
        saved = base.engine_libraries, base.toolchain
        base.engine_libraries, base.toolchain = (lambda c, s: FIXED), (lambda c: {"rustc": "stub"})
        try:
            assert refused(base.opening_readings, cfg)
        finally:
            base.engine_libraries, base.toolchain = saved


def test_an_ldd_path_that_is_not_absolute_is_unreadable():
    # ldd names absolute paths. Anything else is unreadable and never
    # resolved here. Perturbation: take any path, and the relative one is
    # opened against this directory.
    saved_sh, saved_stat = base.sh, base._stat_spu
    ldd = "\tlibggml.so.0 => rel/libggml.so.0 (0x00007f)\n\tlibllama.so.0 => not found\n"
    try:
        base._stat_spu = lambda p: None
        base.sh = lambda args, **kw: subprocess.CompletedProcess(args, 0, ldd, "")
        reading = base.engine_libraries({}, ("/spu", "admin config spu-binary"))
    finally:
        base.sh, base._stat_spu = saved_sh, saved_stat
    assert "not absolute" in reading["libggml.so.0"]["unreadable"], reading
    assert reading["libllama.so.0"]["unreadable"] == "ldd reports it not found", reading


# Class 3: every file a run writes is its own, and every label.

def test_two_cells_of_one_name_are_refused_before_anything_is_written():
    # Codex round nine's thread 3: the second cell overwrote the first's
    # source and replay files. Those files left with the standalone main,
    # and a cell's name still labels its record and its weights reading.
    # Perturbation: drop the repeat check, and the run starts.
    err = io.StringIO()
    same = [TWO_CELLS[0], dict(TWO_CELLS[1], name=TWO_CELLS[0]["name"])]
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
        code, called, *_ = cells_main(tmp, dict(cells=same))
        assert code == 2 and called == [] and not os.path.exists(os.path.join(tmp, "out")) \
            and not os.path.exists(os.path.join(tmp, "karl.toml.pre-matrix")), (code, called)
    assert "the cell names ['q8'] repeat" in err.getvalue(), err.getvalue()
    assert cells_run(Reloading())[0] == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
