"""A session's held fields, and the path the 2026-09-27 runs took (#716).

A fake agent stands in for the admin, the gate and the trace, so
`run_session` runs whole with no device. Run with
`python3 test_recorded_seed.py` or under pytest.
"""
import atexit
import contextlib
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402

base = dm.base
# The files preflight opens, real so that a full config passes it: an
# executable admin, a repository directory and an artifact.
FIXTURE = tempfile.mkdtemp(prefix="matrix-fixture-")
atexit.register(shutil.rmtree, FIXTURE, True)
ADMIN = os.path.join(FIXTURE, "weaver-admin")
with open(ADMIN, "w") as _fh:
    _fh.write("#!/bin/sh\n")
os.chmod(ADMIN, 0o755)
MODEL = os.path.join(FIXTURE, "m.gguf")
with open(MODEL, "wb") as _fh:
    _fh.write(b"weights")
# Every key the config must carry, the fake agent reading none of them.
CFG = {"trace": "/unused/trace", "agent": "karl", "gate_socket": "/unused.sock", "admin_bin": ADMIN,
       "admin_config": "/unused/config", "repo": FIXTURE}
FIXED = {"lib": {"path": "/lib", "sha256": "f" * 64}}


def answer(verb):
    """The admin's answer to a load or an unload that succeeded."""
    return {"kind": "state", "state": "idle" if verb == "load" else "unloaded", "exit": 0}


def stack_fakes(device=None):
    """The stack's readers answering a fixed reading at both ends."""
    card = [{"ordinal": 0, "name": "card", "pci_bus_id": "0000:01:00.0"}]
    return {"_resolve_spu": lambda c: "/spu", "engine_libraries": lambda c, s: FIXED,
            "weaver_binaries": lambda c, s: FIXED,
            "toolchain": lambda c: {"rustc": {"path": "/rustc", "sha256": "e" * 64}},
            "closing_resolution": lambda c: ("/spu", None),
            "device_bindings": lambda c, since: [device if device is not None else card]}


@contextlib.contextmanager
def patched(fakes):
    """`fakes` set on confirm_cells for the block, restored after it."""
    saved = {k: getattr(base, k) for k in fakes}
    try:
        for k, v in fakes.items():
            setattr(base, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(base, k, v)
SEED = 451234785645
DECLARATION = "d" * 64


def declaration(artifact, seed):
    """A declaration in the TOML shape the agent reads, the seed in an inline
    tunable-values table and the artifact on its own line."""
    return ('session = "s-karl-1"\ntool-set = []\npermission-mode = "ask"\n\n'
            "[spu-instruction.decoder]\nresidual-readout-election = false\n"
            'identity = [{ role = "system", content = [{ type = "text", text = "You are Karl." }] }]\n'
            f"tunable-values = {{ seed = {seed}, context-capacity = 16384, max-tokens-per-turn = 1024 }}\n\n"
            "[spu-instruction.decoder.model-binding]\n"
            f"artifact = {json.dumps(artifact)}  # the model\ndevices = [0]\n")


LOOP = "1" * 64
CARD = [{"ordinal": 0, "name": "card", "pci_bus_id": "0000:01:00.0"}]


class Agent:
    """One load per half: the source's turns land in the first run and the
    replay's in the second, each turn a deterministic function of its text,
    its ordinal and the seed its half was loaded under, or no seed at all."""

    def __init__(self, source_seed=SEED, replay_seed=SEED,
                 served=(DECLARATION, DECLARATION), loops=(LOOP, LOOP),
                 devices=({"devices": CARD, "complete": True}, {"devices": CARD, "complete": True})):
        self.seeds, self.loads, self.runs = (source_seed, replay_seed), 0, {}
        self.served, self.loops, self.run, self.devices = served, loops, None, devices
        self.starts = 0

    def serving_device(self, cfg, since, invocation=None):
        """The device each half's load logs, as the journal read by that
        load's invocation answers it."""
        assert invocation == self.invocation(), (invocation, self.invocation())
        return self.devices[self.loads - 1]

    def invocation(self):
        return f"{self.starts:032x}"

    def unit_invocation(self, cfg):
        """The unit's invocation: a new one at every load, as systemd starts."""
        return self.invocation()

    def admin(self, cfg, verb):
        """The admin's answers as it prints them, the exit status beside."""
        if verb == "load":
            self.loads += 1
            self.starts += 1
            self.run = f"run-{self.loads}"
            self.runs[self.run] = []
        return answer(verb)

    def wait_socket(self, cfg):
        return True

    def gate_turn(self, cfg, text, timeout=None):
        """One turn's trace events, written as the sink writes them, so the
        harness reads them back through its own `cut_turns`."""
        events = self.runs[self.run]
        n = sum(1 for e in events if e["kind"] == "turn.started") + 1
        seed = self.seeds[self.loads - 1]
        sampling = {"generation_seed": 7 * n, "temperature": 0.7}
        if seed is not None:
            sampling["seed"] = seed
        turn = f"t-{n}"
        for kind, payload, wall in [
                ("turn.started", {}, 1000 * n),
                ("message.user", {"role": "user", "content": [{"type": "text", "text": text}]}, 1000 * n),
                ("model.request", {"rendered": f"<user>{text}", "sampling": sampling}, 1000 * n),
                ("model.output", {"emission": [len(text), n], "finish": "stop", "resident": 12 * n}, 1000 * n),
                ("model.measurement", {"input_tokens": [n, len(text)], "entropies": [0.25, 0.5 * n]}, 1000 * n),
                ("turn.closed", {"close": "clean"}, 1000 * n + 40)]:
            events.append({"run": self.run, "turn": turn, "kind": kind, "wall_ms": wall, "payload": payload})
        return {"kind": "answered", "run": self.run}

    def await_turns(self, trace, want, run, **kw):
        events = list(self.runs.get(run, []))
        return base.cut_turns(events), events

    def run_load(self, trace, run, keep=4):
        """The load event each half's load writes in its run: the
        declaration's digest and the loop that composed it."""
        if run not in self.runs:
            return None
        half = int(run.rsplit("-", 1)[1]) - 1
        return {"kind": "load", "payload": {
            "declaration": self.served[half],
            "composer": {"binary": "pyworker", "sha256": self.loops[half]}}}


def session(agent, depth=2, declared_seed=None, declaration_sha=None, cfg=CFG):
    saved = {k: getattr(base, k)
             for k in ("admin", "wait_socket", "gate_turn", "await_turns", "run_load",
                       "serving_device", "unit_invocation")}
    try:
        for k in saved:
            setattr(base, k, getattr(agent, k))
        return dm.run_session(cfg, dm.matrix_session(dm.PROMPTS[0], depth, 1, declared_seed), declaration_sha)
    finally:
        for k, v in saved.items():
            setattr(base, k, v)


# The record the harness at `d04da2a`, before #716, returns for this session:
# a recorded seed on every turn and no schedule, which is the path every
# session of the 2026-09-27 runs took. Taken by running that file's
# `run_session` against this fake agent.
BEFORE = json.loads("""
{
 "character": "confident",
 "declared_seed": null,
 "depth": 2,
 "iteration": 1,
 "probe": "factual-short",
 "recorded_seed": 451234785645,
 "replay_recorded_seed": 451234785645,
 "replay_run": "run-2",
 "source_run": "run-1",
 "turns": [
  {
   "emission_sha256": "dfd1a244108634af041f05dade309d7ca22603aedca931097ebbc26a47aef994",
   "entropy": {
    "count": 2,
    "max": 0.5,
    "mean": 0.375,
    "min": 0.25
   },
   "failed_checks": [],
   "is_probe": false,
   "matched": true,
   "replay_ms": 40,
   "source_ms": 40,
   "turn": "t-1"
  },
  {
   "emission_sha256": "ea8d5b60a178d380e12ffafaeb076aae94d932c6683f3d94742654159c4a9587",
   "entropy": {
    "count": 2,
    "max": 1.0,
    "mean": 0.625,
    "min": 0.25
   },
   "failed_checks": [],
   "is_probe": true,
   "matched": true,
   "replay_ms": 40,
   "source_ms": 40,
   "turn": "t-2"
  }
 ],
 "verdict": "REPRODUCED"
}
""")


# The fields a session record gains since d04da2a on today's path, named so
# that nothing else may move: the device each load logged (round three).
ADDED = {"devices": CARD, "invocations": [f"{1:032x}", f"{2:032x}"]}


def test_the_path_the_runs_took_is_unchanged():
    # Perturbation: any change to a verdict, a seed field or a turn's
    # comparison on this path fails the equality. On that path every CHECKS
    # field is present in both records and every load logs its device.
    assert session(Agent()) == dict(BEFORE, **ADDED)


def test_the_path_main_now_drives_differs_by_the_named_fields_alone():
    # #716 round two: main reads the declaration's seed without a schedule
    # and holds every load to the declaration's digest. On today's path the
    # verdict, the recorded seeds and every turn are the d04da2a record's,
    # and the one field that moves is `declared_seed`, null in today's
    # records and now the seed the declaration holds.
    rec = session(Agent(), declared_seed=SEED, declaration_sha=DECLARATION)
    assert rec == dict(BEFORE, declared_seed=SEED, **ADDED), sorted(
        k for k in rec if rec[k] != BEFORE.get(k))


def test_the_declarations_seed_is_read_on_every_path():
    # The default path read no seed, so a record under a wrong one passed.
    # Perturbation: session_seed answering None without a schedule, and the
    # wrong-seed session reads REPRODUCED.
    text = ("[spu-instruction.decoder.tunable-values]\n"
            "seed = 451234785645\ncontext-capacity = 16384\n")
    assert dm.standing_seed(text) == SEED
    assert dm.session_seed(None, SEED, 3, 5) == SEED
    assert dm.session_seed([11, 12, 13], SEED, 1, 0) == 11
    for bad in ("[spu-instruction.decoder.tunable-values]\n", text + "seed = 7\n",
                "[spu-instruction.decoder.tunable-values]\nseed = abc\n",
                "seed = 451234785645\n"):
        try:
            dm.standing_seed(bad)
        except ValueError:
            continue
        raise AssertionError(f"read a seed from {bad!r}")
    rec = session(Agent(source_seed=7, replay_seed=7),
                  declared_seed=dm.session_seed(None, SEED, 1, 0))
    assert rec["verdict"].startswith("the declared seed did not reach the record"), rec["verdict"]


def test_each_load_serves_the_declared_declaration():
    # Perturbation: drop the digest comparison in load_held and both read
    # REPRODUCED.
    for served, half in [(("e" * 64, DECLARATION), "source"), ((DECLARATION, "e" * 64), "replay")]:
        rec = session(Agent(served=served), declared_seed=SEED, declaration_sha=DECLARATION)
        assert rec["verdict"].startswith(f"the {half} load served another declaration"), rec["verdict"]


def test_each_load_is_composed_by_the_declared_loop():
    # Codex's round-two P2: loop_sha256 was never checked. Perturbation: drop
    # the assert_loop call and both read REPRODUCED.
    cfg = dict(CFG, loop_sha256=LOOP)
    assert session(Agent(), cfg=cfg)["verdict"] == "REPRODUCED"
    for loops, half in [(("2" * 64, LOOP), "source"), ((LOOP, "2" * 64), "replay")]:
        rec = session(Agent(loops=loops), cfg=cfg)
        assert rec["verdict"].startswith(f"loop refused at the {half} load"), rec["verdict"]
        assert rec["loop_refused"]["half"] == half


# The matrix's windows, every one unchanged.
HELD = {k: {"status": "unchanged", "reading": {}} for k in ("weights",) + base.STACK_WINDOW}


def unheld(windows=HELD, devices=(CARD,)):
    """The run-wide verdict's unheld fields over sessions that reproduced,
    each carrying one of `devices`."""
    records = [{"verdict": "REPRODUCED", **({} if d is None else {"devices": d})} for d in devices]
    return base.run_verdict(records, windows)[1]


def test_the_exit_gate_counts_every_held_field():
    # Codex's round-two P1: the serving device was recorded and not gated,
    # and the weights were not read at all. Perturbation: drop the device
    # clause, or a window field, and a case here passes.
    assert unheld() == []
    for k in ("weights", "engine_libraries", "weaver_binaries", "toolchain"):
        assert unheld(dict(HELD, **{k: {"status": "varied"}})) == [k]
        assert unheld(dict(HELD, **{k: {"status": "at_close_unreadable"}})) == [k]
    card = CARD[0]
    for devices in ([[card], [dict(card, ordinal=1)]], [None], [None, None], [[]],
                    [[{"unreadable": "no line"}]], []):
        assert unheld(devices=devices) == ["serving_device"], devices


def test_the_weights_are_the_artifacts_bytes():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "model.gguf")
        with open(path, "wb") as fh:
            fh.write(b"weights")
        reading = base.weights(path)(CFG)
        assert reading["artifact"]["sha256"] == base._sha256(path)
        assert base.is_reading(reading)
        missing = base.weights(path + ".gone")(CFG)
        assert not base.is_reading(missing)
    binding = "[spu-instruction.decoder.model-binding]\n"
    assert dm.artifact_of(binding + 'artifact = "/opt/m.gguf"\ndevices = [0]\n') == "/opt/m.gguf"
    for bad in (binding + "devices = [0]\n", binding + 'artifact = "/a"\nartifact = "/b"\n',
                'artifact = "/opt/m.gguf"\n'):
        try:
            dm.artifact_of(bad)
        except ValueError:
            continue
        raise AssertionError(f"read an artifact from {bad!r}")


def test_a_record_carrying_no_seed_is_a_fault_before_any_comparison():
    # #716 round one: both halves missing the seed agreed on None and the
    # session read REPRODUCED. Perturbation: drop the check and the verdict
    # is REPRODUCED again.
    rec = session(Agent(source_seed=None, replay_seed=None))
    assert rec["verdict"] == "the source turns carry no recorded seed", rec["verdict"]
    assert rec["turns"] == [] and rec["replay_run"] is None


def test_a_replay_carrying_no_seed_is_a_fault_too():
    rec = session(Agent(replay_seed=None))
    assert rec["verdict"] == "the replay turns carry no recorded seed", rec["verdict"]
    rec = session(Agent(replay_seed=SEED + 1))
    assert rec["verdict"].startswith("the replay was recorded under another seed"), rec["verdict"]


def test_a_divergence_still_reads_as_one():
    # The fault above sits before the comparison and leaves it whole: a
    # replay under the same seed whose emission differs is still DIVERGED.
    agent = Agent()
    real = agent.gate_turn

    def drifting(cfg, text, timeout=None):
        close = real(cfg, text)
        if agent.loads == 2:
            output = [e for e in agent.runs[agent.run] if e["kind"] == "model.output"][-1]
            output["payload"]["emission"].append(0)
        return close
    agent.gate_turn = drifting
    assert session(agent)["verdict"] == "DIVERGED"


def run_main(agent, device=None, hours="0.00003", extra=(), prepare=None, inspect=None, stack=None,
             sessions=None):
    """`main` whole on the fake agent: a real declaration and config in a
    temporary directory, the stack's readers answering a fixed reading or
    `stack`'s, and the exit code and the per-session records returned.
    `sessions` bounds the matrix's schedule to that many sessions, so a test
    driving the loop to an interrupt ends however the loop behaves."""
    import hashlib
    import io
    with tempfile.TemporaryDirectory() as tmp:
        model = os.path.join(tmp, "model.gguf")
        with open(model, "wb") as fh:
            fh.write(b"weights")
        decl = os.path.join(tmp, "karl.toml")
        with open(decl, "w") as fh:
            fh.write(declaration(model, SEED))
        digest = hashlib.sha256(open(decl, "rb").read()).hexdigest()
        if agent.served == (DECLARATION, DECLARATION):
            agent.served = (digest, digest)
        cfg = os.path.join(tmp, "config.json")
        with open(cfg, "w") as fh:
            json.dump(dict(CFG, declaration=decl), fh)
        if prepare:
            prepare(tmp, decl)
        fakes = dict(stack_fakes(device), **(stack or {}))
        for k in ("admin", "wait_socket", "gate_turn", "await_turns", "run_load",
                  "serving_device", "unit_invocation"):
            fakes[k] = getattr(agent, k)
        saved = {k: getattr(base, k) for k in fakes}
        argv, schedule = sys.argv, dm.matrix_sessions
        if sessions is not None:
            import itertools
            dm.matrix_sessions = lambda *a: itertools.islice(schedule(*a), sessions)
        try:
            for k, v in fakes.items():
                setattr(base, k, v)
            sys.argv = ["determinism_matrix.py", "--config", cfg, "--outdir", tmp, "--hours", hours, *extra]
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    dm.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
        finally:
            sys.argv, dm.matrix_sessions = argv, schedule
            for k, v in saved.items():
                setattr(base, k, v)
        if inspect:
            inspect(tmp, decl)
        records, summary_read = None, None
        try:
            with open(os.path.join(tmp, "matrix.jsonl")) as fh:
                records = [json.loads(line) for line in fh]
            with open(os.path.join(tmp, "summary.json")) as fh:
                summary_read = json.load(fh)
        except (OSError, ValueError):
            pass
    return code, records, summary_read


def cells_main(tmp, change=None, declared=None, prepare=None, fakes=None, outdir=None, dm_fakes=None):
    """The matrix's `--cells` mode whole on a full config in `tmp`, the stack
    faked and the admin recording its verbs. Answers the exit code, the
    verbs, what the run printed, its records and its summary, the last two
    None where it wrote none. `fakes` replaces more of confirm_cells and
    `dm_fakes` of the matrix."""
    import io
    decl = os.path.join(tmp, "karl.toml")
    with open(decl, "w") as fh:
        fh.write(declared if declared is not None else f'[spu-instruction.decoder.model-binding]\nartifact = "{MODEL}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n')
    cfg = dict(CFG, declaration=decl, cells=[{"name": "q8", "precision": "q8", "artifact": MODEL}])
    for k, v in (change or {}).items():
        if v is None:
            cfg.pop(k, None)
        else:
            cfg[k] = v
    path = os.path.join(tmp, "config.json")
    with open(path, "w") as fh:
        json.dump(cfg, fh)
    if prepare:
        prepare(tmp, decl)
    called, out = [], io.StringIO()
    every = dict(stack_fakes(), admin=lambda c, v: called.append(v) or answer(v))
    every.update(fakes or {})
    outdir = outdir if outdir is not None else os.path.join(tmp, "out")
    argv, saved = sys.argv, {k: getattr(dm, k) for k in (dm_fakes or {})}
    try:
        for k, v in (dm_fakes or {}).items():
            setattr(dm, k, v)
        sys.argv = ["determinism_matrix.py", "--config", path, "--outdir", outdir, "--cells"]
        with patched(every), contextlib.redirect_stdout(out):
            try:
                dm.main()
                code = 0
            except SystemExit as e:
                code = e.code
    finally:
        sys.argv = argv
        for k, v in saved.items():
            setattr(dm, k, v)
    records = summary = None
    try:
        records = [json.loads(line) for line in open(os.path.join(outdir, "matrix.jsonl"))]
        summary = json.load(open(os.path.join(outdir, "summary.json")))
    except (OSError, ValueError):
        pass
    return code, called, out.getvalue(), records, summary


class Reloading(Agent):
    """A fresh agent's state per session: main drives many sessions."""

    def admin(self, cfg, verb):
        if verb == "load" and self.loads == 2:
            self.loads = 0
        return Agent.admin(self, cfg, verb)


def test_main_holds_every_field_without_a_schedule():
    # Codex's round-two P1, at main itself: without a schedule every session
    # is declared under the declaration's own seed and every load is held to
    # the declaration's digest, and the exit gate counts the weights and the
    # device. Perturbation: main passing `declared_seed = None`, or no
    # digest, or dropping `unheld`, fails a clause here.
    code, records, s = run_main(Reloading())
    assert records and code == 0, (code, len(records))
    assert {r["declared_seed"] for r in records} == {SEED}
    assert {r["verdict"] for r in records} == {"REPRODUCED"}
    assert s["weights"]["status"] == "unchanged" and s["by_seed"] == {str(SEED): {"n": len(records), "ok": len(records)}}
    code, records, _ = run_main(Reloading(source_seed=7, replay_seed=7))
    assert code == 1 and all(r["verdict"].startswith("the declared seed did not reach") for r in records)
    code, records, _ = run_main(Reloading(served=("e" * 64, "e" * 64)))
    assert code == 1 and all("served another declaration" in r["verdict"] for r in records)
    # The journal window is recorded and not gated, so a window that lost
    # its loads no longer stands in for them: the sessions' own reads do.
    code, records, s = run_main(Reloading(), device={"varied": []})
    assert code == 0 and s["serving_device"] == CARD, (code, s["serving_device"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
