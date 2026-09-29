"""Reads tied to their action, outputs no earlier run survives into, and
hand-parsed formats refused by name (#716 round five).

Each test holds one site of the three walks and names the perturbation that
fails it. Run with `python3 test_round_five.py` or under pytest.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import CFG, SEED, Agent, Reloading, cells_main, run_main, session  # noqa: E402

base = dm.base
BOUNDARY = "ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24075 MiB):"
# The engine's next line after its device block, which marks it complete.
COMPLETE = ("llama_model_loader: loaded meta data with 26 key-value pairs and 291 tensors"
            " from /proc/self/fd/5 (version GGUF V3 (latest))")


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
    current = [BOUNDARY, device_line(1, "0000:02:00.0"), COMPLETE]
    seen, invocation = with_sh(box(inv, current, previous), lambda: base.load_devices({"agent": "karl"}, 1, 0))
    assert invocation == inv and seen == {"devices": [{"ordinal": 1, "name": "NVIDIA RTX PRO 5000 Blackwell"
                                                        " Generation Laptop GPU", "pci_bus_id": "0000:02:00.0"}],
                                            "complete": True}, seen


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


def test_a_cells_run_refuses_an_earlier_runs_deposit_and_backup():
    # The same class in the cells mode, whose deposit is the matrix's: a
    # record or summary an earlier run wrote, or its declaration backup,
    # refuses before anything runs. Perturbation: drop either refusal, and
    # the admin is called.
    for stand in ("matrix.jsonl", "summary.json", "BACKUP"):
        with tempfile.TemporaryDirectory() as tmp:
            def prepare(tmp, decl, stand=stand):
                with open(decl + ".pre-matrix" if stand == "BACKUP" else os.path.join(tmp, stand), "w") as fh:
                    fh.write("x")
            code, called, *_ = cells_main(tmp, prepare=prepare, outdir=tmp)
            assert code == 2 and called == [], (stand, code, called)


BINDING = "[spu-instruction.decoder.model-binding]\n"
TUNABLE = "[spu-instruction.decoder.tunable-values]\n"


def test_the_artifact_is_read_as_toml():
    # Codex round four, thread 3, carried to TOML. Perturbation: take the
    # value as source text, and the quoted path keeps its quotes and the
    # commented one reads its comment.
    for text, want in [(BINDING + 'artifact = "/opt/m.gguf"\n', "/opt/m.gguf"),
                       (BINDING + "artifact = '/opt/m.gguf'  # the model\n", "/opt/m.gguf"),
                       (BINDING + '  artifact = "/opt/m.gguf" # the model\n', "/opt/m.gguf"),
                       (BINDING + 'artifact = "/opt/m\\u0023.gguf"\n', "/opt/m#.gguf"),
                       ('[spu-instruction.decoder]\nmodel-binding = { artifact = "/opt/m.gguf", devices = [0] }\n',
                        "/opt/m.gguf")]:
        assert dm.artifact_of(text) == want, (text, dm.artifact_of(text))
    for text in (BINDING + 'artifact = "/opt/m.gguf\n', BINDING + 'artifact = "/opt/m.gguf" trailing\n',
                 BINDING + "artifact = /opt/m.gguf\n", BINDING + 'artifact = ["/a", "/b"]\n',
                 BINDING + "artifact = 7\n", BINDING + 'artifact = "m.gguf"\n',
                 BINDING + 'artifact = "/a"\nartifact = "/b"\n', 'artifact = "/opt/m.gguf"\n',
                 '[spu-instruction.decoder.other]\nartifact = "/opt/m.gguf"\n'):
        try:
            dm.artifact_of(text)
        except ValueError:
            continue
        raise AssertionError(f"read an artifact from {text!r}")


def test_the_artifact_rewrite_stays_on_its_line():
    # The old `(artifact:\s*).*` ran past an empty value into the next key.
    # Perturbation: a value pattern crossing the line end, and `devices` is
    # overwritten, or drop the reparse, and a site off the path is written.
    text = BINDING + 'artifact = "/old.gguf" # was\ndevices = [0]\n'
    out = base.with_artifact(text, "/new.gguf")
    assert out == BINDING + 'artifact = "/new.gguf" # was\ndevices = [0]\n', out
    inline = '[spu-instruction.decoder]\nmodel-binding = { artifact = \'/old.gguf\', devices = [0] }  # was\n'
    assert base.with_artifact(inline, "/new.gguf") == inline.replace("'/old.gguf'", '"/new.gguf"')
    # A path a quoted string carries is written and read back whole.
    for path in ("/my model.gguf", "/m#1.gguf", '/"m".gguf', "/m\\n.gguf", "/m: b"):
        assert dm.artifact_of(base.with_artifact(text, path)) == path, path
    # An empty value is not a TOML document, and the rewrite reaches no key.
    empty = BINDING + "artifact =\ndevices = [0]\n"
    for bad_text in (empty, BINDING + 'artifact = "/a"\nartifact = "/b"\n',
                     BINDING + 'devices = [0]\nnote = "x, artifact = \'/y\'"\n',
                     'artifact = "/old.gguf"\n' + BINDING + "devices = [0]\n"):
        try:
            base.with_artifact(bad_text, "/new.gguf")
        except ValueError:
            continue
        raise AssertionError(f"rewrote the artifact in {bad_text!r}")
    # The same key in another table is another value: TOML says which is
    # which, so it is left as it stands rather than read as a second site.
    other = text + '[other]\nartifact = "/old.gguf"\n'
    assert base.with_artifact(other, "/new.gguf") == other.replace('"/old.gguf" # was', '"/new.gguf" # was')
    for path in ("&m", "", "m.gguf"):
        try:
            base.with_artifact(text, path)
        except ValueError:
            continue
        raise AssertionError(f"wrote {path!r} as the artifact")


def test_the_seed_is_read_as_toml():
    # Perturbation: read the seed as source text, and the commented one
    # refuses, or take a string for an integer, and the quoted one reads.
    for text, want in [(TUNABLE + "seed = 451234785645\n", SEED),
                       (TUNABLE + "seed = 7 # the seed\n", 7),
                       ("[spu-instruction.decoder]\ntunable-values = { seed = 7, context-capacity = 16 }\n", 7)]:
        assert dm.standing_seed(text) == want, text
    for value in ('"451234785645"', "-7", "7.0", "true", "[7]", "", "7 7"):
        try:
            dm.standing_seed(TUNABLE + f"seed = {value}\n")
        except ValueError as e:
            assert "seed" in str(e) or "TOML" in str(e), e
            continue
        raise AssertionError(f"read a seed from {value!r}")
    for text in (TUNABLE + "seed = 7\nseed = 8\n", "seed = 7\n", "[spu-instruction.decoder.other]\nseed = 7\n"):
        try:
            dm.standing_seed(text)
        except ValueError:
            continue
        raise AssertionError(f"read a seed from {text!r}")


def test_an_ldd_path_holding_a_space_is_read_whole():
    # Perturbation: the old `(\S+)` path, and the library reads unreadable
    # at the path's first word.
    with tempfile.TemporaryDirectory(prefix="my libs ") as tmp:
        lib = os.path.join(tmp, "libggml.so.0")
        with open(lib, "wb") as fh:
            fh.write(b"lib")
        ldd = f"\tlibggml.so.0 => {lib} (0x00007f)\n\tlibllama.so.0 => not found\n"
        saved_stat = base._stat_spu
        try:
            base._stat_spu = lambda p: None
            reading = with_sh(lambda args, **kw: subprocess.CompletedProcess(args, 0, ldd, ""),
                              lambda: base.engine_libraries({}, ("/spu", "admin config spu-binary")))
        finally:
            base._stat_spu = saved_stat
        assert reading["libggml.so.0"] == {"path": lib, "sha256": base._sha256(lib)}, reading
        assert "unreadable" in reading["libllama.so.0"], reading


def test_malformed_events_and_requests_are_named():
    # Perturbation: `e["kind"]` again, and the first case raises; the
    # first text part alone, and the second is replayed short.
    events = [{"run": "r", "turn": "t-1", "kind": k, "payload": p} for k, p in [
        ("message.user", {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}),
        ("model.request", {}), ("model.output", {}), ("model.measurement", {}), ("turn.closed", {})]]
    assert base.cut_turns(events)[0]["incomplete"] == ["the request is not one text part"]
    events[0]["payload"]["content"] = [{"type": "text", "text": "a"}]
    events.append({"run": "r", "turn": "t-1", "payload": {}})
    assert base.cut_turns(events)[0]["incomplete"] == ["1 events with no string kind"]


def test_a_surplus_replay_turn_is_a_fault_not_a_divergence():
    # The surplus-turn item on #698: a replay carrying a complete turn the
    # source did not is interleaved traffic. Perturbation: the old count
    # check folded into `all_match`, and it reads DIVERGED.
    class Surplus(Agent):
        def gate_turn(self, cfg, text, timeout=None):
            close = Agent.gate_turn(self, cfg, text)
            if self.loads == 2 and sum(1 for e in self.runs[self.run] if e["kind"] == "turn.started") == 2:
                Agent.gate_turn(self, cfg, "interleaved")
            return close
    rec = session(Surplus())
    assert rec["verdict"] == "the replay carries 1 turns the source did not: t-3", rec["verdict"]


def drive_cell(agent, tmp, artifact="/m.gguf"):
    """One cell of the matrix's cells mode, run whole by `run_session` on the
    fake agent: the session writes the cell's declaration, loads, serves,
    reloads, reissues and compares, and its record returns."""
    decl = os.path.join(tmp, "karl.toml")
    standing = f'[spu-instruction.decoder.model-binding]\nartifact = "{artifact}"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'
    with open(decl, "w") as fh:
        fh.write(standing)
    cfg = dict(CFG, declaration=decl, trace=os.path.join(tmp, "trace"))
    names = ("admin", "wait_socket", "gate_turn", "await_turns", "run_load", "serving_device",
             "unit_invocation")
    saved = {n: getattr(base, n) for n in names}
    try:
        for n in names:
            setattr(base, n, getattr(agent, n))
        cell = {"name": "c", "precision": "q6", "artifact": artifact}
        return dm.run_session(cfg, next(dm.cell_sessions(standing, [cell])))
    finally:
        for n, fn in saved.items():
            setattr(base, n, fn)


def test_a_cell_holds_both_loads_to_its_declaration():
    # #716 round six: the standalone run_cell checked only the loop after
    # each load. A cell's loads go through load_held as every session's do.
    # Perturbation: restore the bare assert_loop at either site, and that
    # half's case reads REPRODUCED.
    import hashlib
    for served, half in [(("e" * 64, None), "source"), ((None, "e" * 64), "replay")]:
        with tempfile.TemporaryDirectory() as tmp:
            digest = hashlib.sha256(f'[spu-instruction.decoder.model-binding]\nartifact = "/m.gguf"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'.encode()).hexdigest()
            both = tuple(digest if s is None else s for s in served)
            report = drive_cell(Agent(served=both), tmp)
            assert report["verdict"].startswith(f"the {half} load served another declaration"), report["verdict"]
    with tempfile.TemporaryDirectory() as tmp:
        digest = hashlib.sha256(f'[spu-instruction.decoder.model-binding]\nartifact = "/m.gguf"\n[spu-instruction.decoder.tunable-values]\nseed = {SEED}\n'.encode()).hexdigest()
        assert drive_cell(Agent(served=(digest, digest)), tmp)["verdict"] == "REPRODUCED"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
