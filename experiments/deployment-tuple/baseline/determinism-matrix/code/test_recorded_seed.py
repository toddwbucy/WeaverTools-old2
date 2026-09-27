"""A session's held fields, and the path the 2026-09-27 runs took (#716).

A fake agent stands in for the admin, the gate and the trace, so
`run_session` runs whole with no device. Run with
`python3 test_recorded_seed.py` or under pytest.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402

base = dm.base
# Every key the config must carry, the fake agent reading none of them.
CFG = {"trace": "unused", "agent": "karl", "gate_socket": "/unused.sock", "admin_bin": "/unused/admin",
       "admin_config": "/unused/config", "repo": "/unused/repo"}
SEED = 451234785645
DECLARATION = "d" * 64
LOOP = "1" * 64
CARD = [{"ordinal": 0, "name": "card", "pci_bus_id": "0000:01:00.0"}]


class Agent:
    """One load per half: the source's turns land in the first run and the
    replay's in the second, each turn a deterministic function of its text,
    its ordinal and the seed its half was loaded under, or no seed at all."""

    def __init__(self, source_seed=SEED, replay_seed=SEED,
                 served=(DECLARATION, DECLARATION), loops=(LOOP, LOOP),
                 devices=({"devices": CARD}, {"devices": CARD})):
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
        if verb == "load":
            self.loads += 1
            self.starts += 1
            self.run = f"run-{self.loads}"
            self.runs[self.run] = []
        return {"kind": "state"}

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

    def newest_load(self, trace, keep=2):
        """The load event each half's load writes: the declaration's digest
        and the loop that composed it."""
        if self.run is None:
            return None, None
        half = self.loads - 1
        return self.run, {"kind": "load", "payload": {
            "declaration": self.served[half],
            "composer": {"binary": "pyworker", "sha256": self.loops[half]}}}


def session(agent, depth=2, declared_seed=None, declaration_sha=None, cfg=CFG):
    saved = {k: getattr(base, k)
             for k in ("admin", "wait_socket", "gate_turn", "await_turns", "newest_load",
                       "serving_device", "unit_invocation")}
    try:
        for k in saved:
            setattr(base, k, getattr(agent, k))
        return dm.run_session(cfg, dm.PROMPTS[0], depth, 1, declared_seed, declaration_sha)
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
    text = "decoder:\n  tunable-values:\n    seed: 451234785645\n    context-capacity: 16384\n"
    assert dm.standing_seed(text) == SEED
    assert dm.session_seed(None, SEED, 3, 5) == SEED
    assert dm.session_seed([11, 12, 13], SEED, 1, 0) == 11
    for bad in ("tunable-values:\n", text + "    seed: 7\n", "    seed: abc\n"):
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


def summary(**changes):
    held = {"status": "unchanged", "reading": {}}
    s = {k: held for k in dm.HELD_BY_WINDOW}
    s["serving_device"] = [{"ordinal": 0, "name": "card", "pci_bus_id": "0000:01:00.0"}]
    s.update(changes)
    return s


def test_the_exit_gate_counts_every_held_field():
    # Codex's round-two P1: the serving device was recorded and not gated,
    # and the weights were not read at all. Perturbation: drop the device
    # clause, or weights from HELD_BY_WINDOW, and a case here passes.
    assert dm.unheld(summary()) == []
    for k in ("weights", "engine_libraries", "weaver_binaries", "toolchain"):
        assert dm.unheld(summary(**{k: {"status": "varied"}})) == [k]
        assert dm.unheld(summary(**{k: {"status": "at_close_unreadable"}})) == [k]
    card = {"ordinal": 0, "name": "card", "pci_bus_id": "0000:01:00.0"}
    for device in ({"varied": [[card], [dict(card, ordinal=1)]]}, {"varied": []},
                   {"unreadable": "journalctl exit 2"}, [], [{"unreadable": "no line"}], None):
        assert dm.unheld(summary(serving_device=device)) == ["serving_device"], device


def test_the_weights_are_the_artifacts_bytes():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "model.gguf")
        with open(path, "wb") as fh:
            fh.write(b"weights")
        reading = dm.weights(path)(CFG)
        assert reading["artifact"]["sha256"] == base._sha256(path)
        assert base.is_reading(reading)
        missing = dm.weights(path + ".gone")(CFG)
        assert not base.is_reading(missing)
    assert dm.artifact_of("model-binding:\n  artifact: /opt/m.gguf\n  devices: [0]\n") == "/opt/m.gguf"
    for bad in ("devices: [0]\n", "artifact: /a\nartifact: /b\n"):
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


def run_main(agent, device=None, hours="0.00003", extra=(), prepare=None, inspect=None):
    """`main` whole on the fake agent: a real declaration and config in a
    temporary directory, the stack's readers answering a fixed reading, and
    the exit code and the per-session records returned."""
    import contextlib
    import hashlib
    import io
    import tempfile
    card = [{"ordinal": 0, "name": "card", "pci_bus_id": "0000:01:00.0"}]
    fixed = {"lib": {"path": "/lib", "sha256": "f" * 64}}
    with tempfile.TemporaryDirectory() as tmp:
        model = os.path.join(tmp, "model.gguf")
        with open(model, "wb") as fh:
            fh.write(b"weights")
        decl = os.path.join(tmp, "karl.yaml")
        with open(decl, "w") as fh:
            fh.write(f"model-binding:\n  artifact: {model}\ntunable-values:\n  seed: {SEED}\n")
        digest = hashlib.sha256(open(decl, "rb").read()).hexdigest()
        if agent.served == (DECLARATION, DECLARATION):
            agent.served = (digest, digest)
        cfg = os.path.join(tmp, "config.json")
        with open(cfg, "w") as fh:
            json.dump(dict(CFG, declaration=decl), fh)
        if prepare:
            prepare(tmp, decl)
        fakes = {"_resolve_spu": lambda c: "/spu", "engine_libraries": lambda c, s: fixed,
                 "weaver_binaries": lambda c, s: fixed,
                 "toolchain": lambda c: {"rustc": {"path": "/rustc", "sha256": "e" * 64}},
                 "closing_resolution": lambda c: ("/spu", None),
                 "device_bindings": lambda c, since: [device if device is not None else card]}
        for k in ("admin", "wait_socket", "gate_turn", "await_turns", "newest_load",
                  "serving_device", "unit_invocation"):
            fakes[k] = getattr(agent, k)
        saved = {k: getattr(base, k) for k in fakes}
        argv = sys.argv
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
            sys.argv = argv
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
