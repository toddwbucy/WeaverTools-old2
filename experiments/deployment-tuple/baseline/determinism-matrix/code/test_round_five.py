"""Reads tied to their action, outputs no earlier run survives into, and
hand-parsed formats refused by name (#716 round five).

Each test holds one site of the three walks and names the perturbation that
fails it. Run with `python3 test_round_five.py` or under pytest.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import SEED, Agent, Reloading, run_main, session  # noqa: E402

base = dm.base
BOUNDARY = "ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24075 MiB):"


def device_line(ordinal, bus):
    return (f"llama_model_load_from_file_impl: using device CUDA{ordinal} (NVIDIA RTX PRO 5000"
            f" Blackwell Generation Laptop GPU) ({bus}) - 23322 MiB free")


def box(invocation, by_invocation, by_window):
    """`sh` as the box answers: systemctl names the unit's invocation, the
    journal read by invocation returns that load's lines, and a window read
    returns what the window holds."""
    def sh(args, **kw):
        if args[0] == "systemctl":
            return subprocess.CompletedProcess(args, 0, invocation + "\n", "")
        if any(a.startswith("_SYSTEMD_INVOCATION_ID=") for a in args):
            lines = by_invocation
        else:
            lines = by_window
        if "-g" in args:
            return subprocess.CompletedProcess(args, 0 if lines else 1, "\n".join(lines) + "\n", "")
        return subprocess.CompletedProcess(args, 0, "a line\n", "")
    return sh


def with_sh(sh, fn):
    saved = base.sh
    base.sh = sh
    try:
        return fn()
    finally:
        base.sh = saved


def test_the_device_read_is_the_load_just_started():
    # Codex round four, thread 1: a window with slack held the previous load,
    # whose group the read took. Bound to the invocation, the read is this
    # load's. Perturbation: _device_groups ignoring `invocation`, and the
    # previous load's CUDA0 is returned for a load that bound CUDA1.
    inv = "b" * 32
    previous = [BOUNDARY, device_line(0, "0000:01:00.0")]
    current = [BOUNDARY, device_line(1, "0000:02:00.0")]
    seen, invocation = with_sh(box(inv, current, previous), lambda: base.load_devices({"agent": "karl"}, 1, 0))
    assert invocation == inv and seen == {"devices": [{"ordinal": 1, "name": "NVIDIA RTX PRO 5000 Blackwell"
                                                        " Generation Laptop GPU", "pci_bus_id": "0000:02:00.0"}]}, seen


def test_an_unreadable_or_crowded_invocation_is_refused():
    # Perturbation: accept any systemctl answer, or more than one load
    # under an invocation, and a case here returns devices.
    seen, invocation = with_sh(box("", [], []), lambda: base.load_devices({"agent": "karl"}, 1, 0))
    assert invocation is None and "unreadable" in seen, seen
    two = [BOUNDARY, device_line(0, "0000:01:00.0"), BOUNDARY, device_line(0, "0000:01:00.0")]
    seen, _ = with_sh(box("c" * 32, two, []), lambda: base.load_devices({"agent": "karl"}, 1, 0))
    assert "unreadable" in seen, seen


class Unrestarted(Agent):
    """A reload that systemd never started: the unit's invocation is the
    load's own."""

    def admin(self, cfg, verb):
        out = Agent.admin(self, cfg, verb)
        if verb == "load" and self.loads == 2:
            self.starts -= 1
        return out


def test_a_reload_that_did_not_start_a_unit_is_refused():
    # Perturbation: drop the source-against-replay invocation check.
    rec = session(Unrestarted())
    assert rec["verdict"] == f"the reload is the load's own invocation {1:032x}", rec["verdict"]


class Stale(Reloading):
    """Every session's loads read the same two invocations."""

    def admin(self, cfg, verb):
        out = Reloading.admin(self, cfg, verb)
        if verb == "load":
            self.starts = self.loads
        return out


def test_a_load_an_earlier_session_read_is_refused():
    # Perturbation: drop the run-wide invocation set in main, and every
    # session after the first reads REPRODUCED.
    code, records, _ = run_main(Stale())
    assert code == 1 and records[0]["verdict"] == "REPRODUCED", (code, records[:1])
    assert all(r["verdict"].startswith("a load read invocation") for r in records[1:]), records[1]["verdict"]


def test_a_deposit_an_earlier_run_wrote_is_refused():
    # Codex round four, thread 2. Perturbation: drop stale_outputs in main,
    # and the earlier record survives beneath a summary of this run alone.
    for name in ("matrix.jsonl", "matrix.log", "summary.json"):
        left = {}

        def prepare(tmp, decl, name=name):
            with open(os.path.join(tmp, name), "w") as fh:
                fh.write("an earlier run\n")

        def inspect(tmp, decl, name=name):
            left["files"] = sorted(f for f in os.listdir(tmp) if f.startswith(("matrix", "summary")))
            left["kept"] = open(os.path.join(tmp, name)).read()
        code, _, _ = run_main(Reloading(), prepare=prepare, inspect=inspect)
        assert code == 2 and left["files"] == [name] and left["kept"] == "an earlier run\n", (name, code, left)


def test_an_unrestored_declaration_is_refused_and_a_restored_one_leaves_no_backup():
    # A killed schedule leaves its last seed in the declaration, which the
    # next run would read as the declaration's own. Perturbation: drop the
    # `.pre-matrix` refusal, or its removal after the restore.
    def stand(tmp, decl):
        with open(decl + ".pre-matrix", "w") as fh:
            fh.write("the operator's text\n")
    code, _, _ = run_main(Reloading(), prepare=stand)
    assert code == 2, code
    after = {}

    def inspect(tmp, decl):
        after["backup"] = os.path.lexists(decl + ".pre-matrix")
        after["seed"] = dm.standing_seed(open(decl).read())
    code, records, _ = run_main(Reloading(), extra=["--seed-schedule", "11,12,13"], inspect=inspect)
    assert after == {"backup": False, "seed": SEED}, after


def test_the_cells_deposit_and_backup_refuse_an_earlier_run():
    # The same class in confirm_cells: a report or a cell file an earlier
    # run wrote, or its declaration backup, refuses before anything runs.
    # Perturbation: drop either refusal, and the admin is called.
    for stand in ("report-thinkpad.json", "cell-q8-source.ndjson", "BACKUP"):
        with tempfile.TemporaryDirectory() as tmp:
            decl = os.path.join(tmp, "karl.yaml")
            with open(decl, "w") as fh:
                fh.write("artifact: /m.gguf\n")
            if stand == "BACKUP":
                with open(decl + ".pre-cells", "w") as fh:
                    fh.write("x")
            else:
                with open(os.path.join(tmp, stand), "w") as fh:
                    fh.write("x")
            cfg = os.path.join(tmp, "config.json")
            with open(cfg, "w") as fh:
                json.dump({"box": "thinkpad", "declaration": decl, "cells": []}, fh)
            called = []
            saved, argv = base.admin, sys.argv
            try:
                base.admin = lambda c, v: called.append(v) or {"kind": "state"}
                sys.argv = ["confirm_cells.py", "--config", cfg, "--outdir", tmp]
                try:
                    base.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
            finally:
                base.admin, sys.argv = saved, argv
            assert code == 2 and called == [], (stand, code, called)


def test_the_artifact_is_read_as_a_yaml_scalar():
    # Codex round four, thread 3. Perturbation: the old `(\S+)` value, and
    # the quoted path keeps its quotes and the commented one is not found.
    for text, want in [('artifact: "/opt/m.gguf"\n', "/opt/m.gguf"),
                       ("artifact: '/opt/m.gguf'  # the model\n", "/opt/m.gguf"),
                       ("  artifact: /opt/m.gguf # the model\n", "/opt/m.gguf"),
                       ("artifact: /opt/m.gguf\n", "/opt/m.gguf")]:
        assert dm.artifact_of(text) == want, (text, dm.artifact_of(text))
    for text in ('artifact: "/opt/m.gguf\n', 'artifact: "/opt/m\\\\.gguf"\n', "artifact: '/o''m'\n",
                 'artifact: "/opt/m.gguf" trailing\n', "artifact:\n  - /opt/m.gguf\n", "artifact: [a, b]\n",
                 "artifact: &x /opt/m.gguf\n", "artifact: a: b\n", "artifact: /a\nartifact: /b\n"):
        try:
            dm.artifact_of(text)
        except ValueError:
            continue
        raise AssertionError(f"read an artifact from {text!r}")


def test_the_artifact_rewrite_stays_on_its_line():
    # The old `(artifact:\s*).*` ran past an empty value into the next key.
    # Perturbation: the old regex, and `devices` is overwritten.
    text = "model-binding:\n  artifact: \"/old.gguf\" # was\n  devices: [0]\n"
    out = base.with_artifact(text, "/new.gguf")
    assert out == "model-binding:\n  artifact: /new.gguf\n  devices: [0]\n", out
    # An empty value: the old `\s*` crossed the line end and the rewrite
    # swallowed the next key.
    empty = "model-binding:\n  artifact:\n  devices: [0]\n"
    assert base.with_artifact(empty, "/new.gguf") == "model-binding:\n  artifact: /new.gguf\n  devices: [0]\n"
    for path in ("/my model.gguf", "/m#1.gguf", '"/m.gguf"', "&m", ""):
        try:
            base.with_artifact(text, path)
        except ValueError:
            continue
        raise AssertionError(f"wrote {path!r} as a plain scalar")


def test_the_seed_is_read_as_a_yaml_scalar():
    # Perturbation: int() on the source text, and the quoted seed refuses.
    for value, want in [("451234785645", SEED), ('"451234785645"', SEED), ("7 # the seed", 7)]:
        assert dm.standing_seed(f"    seed: {value}\n") == want, value
    for value in ("0x10", "-7", "1_000", "7.0", "[7]", ""):
        try:
            dm.standing_seed(f"    seed: {value}\n")
        except ValueError:
            continue
        raise AssertionError(f"read a seed from {value!r}")


def test_an_ldd_path_holding_a_space_is_read_whole():
    # Perturbation: the old `(\S+)` path, and the library reads unreadable
    # at the path's first word.
    with tempfile.TemporaryDirectory(prefix="my libs ") as tmp:
        lib = os.path.join(tmp, "libggml.so.0")
        with open(lib, "wb") as fh:
            fh.write(b"lib")
        ldd = f"\tlibggml.so.0 => {lib} (0x00007f)\n\tlibllama.so.0 => not found\n"
        saved_exists = base.os.path.exists
        try:
            base.os.path.exists = lambda p: True
            reading = with_sh(lambda args, **kw: subprocess.CompletedProcess(args, 0, ldd, ""),
                              lambda: base.engine_libraries({}, ("/spu", "config spu_bin")))
        finally:
            base.os.path.exists = saved_exists
        assert reading["libggml.so.0"] == {"path": lib, "sha256": base._sha256(lib)}, reading
        assert "unreadable" in reading["libllama.so.0"], reading


def test_malformed_events_and_requests_are_named():
    # Perturbation: `e["kind"]` again, and the first case raises; the
    # first text part alone, and the second is replayed short.
    events = [{"run": "r", "turn": "t-1", "kind": k, "payload": p} for k, p in [
        ("message.user", {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}),
        ("model.request", {}), ("model.output", {}), ("model.measurement", {})]]
    assert base.cut_turns(events)[0]["incomplete"] == ["the request is not one text part"]
    events[0]["payload"]["content"] = [{"type": "text", "text": "a"}]
    events.append({"run": "r", "turn": "t-1", "payload": {}})
    assert base.cut_turns(events)[0]["incomplete"] == ["1 events with no kind"]


def test_a_surplus_replay_turn_is_a_fault_not_a_divergence():
    # The surplus-turn item on #698: a replay carrying a complete turn the
    # source did not is interleaved traffic. Perturbation: the old count
    # check folded into `all_match`, and it reads DIVERGED.
    class Surplus(Agent):
        def gate_turn(self, cfg, text):
            close = Agent.gate_turn(self, cfg, text)
            if self.loads == 2 and sum(1 for e in self.runs[self.run] if e["kind"] == "turn.started") == 2:
                Agent.gate_turn(self, cfg, "interleaved")
            return close
    rec = session(Surplus())
    assert rec["verdict"] == "the replay carries 1 turns the source did not: t-3", rec["verdict"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
