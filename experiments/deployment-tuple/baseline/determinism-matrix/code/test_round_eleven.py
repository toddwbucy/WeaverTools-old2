"""The weights window required of both entry points, the declaration held
as the bytes read, and the closing unload guarded (#716 round eleven).

Run with `python3 test_round_eleven.py` or under pytest.
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
from test_recorded_seed import CARD, MODEL, SEED, Reloading, cells_main, run_main  # noqa: E402
from test_round_nine import TWO_CELLS, agent_fakes  # noqa: E402

base = dm.base
DECL = f"artifact: {MODEL}\nseed: {SEED}\n"
STACK_HELD = {k: {"status": "unchanged", "reading": {}} for k in base.STACK_WINDOW}


class DiskServing(Reloading):
    """A load serves the declaration as it stands on disk at the load, as
    the admin does, and remembers the text it served."""

    def __init__(self, **kw):
        Reloading.__init__(self, **kw)
        self.decl, self.texts = None, []

    def admin(self, cfg, verb):
        self.decl = cfg["declaration"]
        if verb == "load":
            data = open(self.decl, "rb").read()
            self.texts.append(data.decode())
            digest = hashlib.sha256(data).hexdigest()
            self.served = (digest, digest)
        return Reloading.admin(self, cfg, verb)


class SwappingArtifact(DiskServing):
    """The artifact's bytes replaced at the replay's load and left so."""

    def __init__(self, artifact, **kw):
        DiskServing.__init__(self, **kw)
        self.artifact = artifact

    def admin(self, cfg, verb):
        if verb == "load" and self.loads == 1:
            with open(self.artifact, "ab") as fh:
                fh.write(b"swapped")
        return DiskServing.admin(self, cfg, verb)


class FailingFinalUnload(DiskServing):
    """The unload that closes each session raises `exc`."""

    def __init__(self, exc, **kw):
        DiskServing.__init__(self, **kw)
        self.exc, self.replayed = exc, False

    def gate_turn(self, cfg, text, timeout=None):
        self.replayed = self.replayed or self.loads == 2
        return DiskServing.gate_turn(self, cfg, text, timeout)

    def admin(self, cfg, verb):
        if verb == "unload" and self.replayed:
            self.replayed = False
            raise self.exc
        return DiskServing.admin(self, cfg, verb)


def cells(agent, change=None, declared=None, fakes=None):
    """The cross-precision `main` whole on `agent`, and its deposit and
    declaration read back."""
    with tempfile.TemporaryDirectory() as tmp:
        every = dict(agent_fakes(agent), **(fakes or {}))
        code, _, printed = cells_main(tmp, dict(dict(cells=TWO_CELLS), **(change or {})),
                                      declared=declared, fakes=every)
        path = os.path.join(tmp, "out", "report-thinkpad.json")
        reports = json.load(open(path)) if os.path.exists(path) else None
        restored = open(os.path.join(tmp, "karl.yaml")).read()
    return code, printed, reports, restored


@contextlib.contextmanager
def after_preflight(module, change):
    """`change()` run the moment `module` makes its outdir, after every
    preflight check has passed."""
    real = module.os.makedirs

    def makedirs(*a, **k):
        change()
        return real(*a, **k)
    module.os.makedirs = makedirs
    try:
        yield
    finally:
        module.os.makedirs = real


# Class 1: the weights window is required of both entry points.

def test_run_verdict_requires_a_weights_window():
    # Codex round ten's thread 1: the cells passed no weights and the
    # verdict required only the stack. Perturbation: drop weights from
    # REQUIRED_WINDOWS, and an omitted window passes.
    one = [{"verdict": "REPRODUCED", "devices": CARD}]
    assert base.run_verdict(one, STACK_HELD) == (True, ["weights"])
    assert base.run_verdict(one, dict(STACK_HELD, weights={"status": "unchanged"})) == (True, [])


def test_a_cell_artifact_swapped_between_its_loads_fails_the_cells_exit():
    # Each cell reads its artifact at its open and again at its close.
    # Perturbation: drop the cell's close, or cells_weights from the exit,
    # and the swapped run exits 0.
    with tempfile.TemporaryDirectory() as art_dir:
        artifact = os.path.join(art_dir, "m.gguf")
        with open(artifact, "wb") as fh:
            fh.write(b"weights")
        one = [dict(TWO_CELLS[0], artifact=artifact)]
        code, printed, reports, _ = cells(SwappingArtifact(artifact), dict(cells=one),
                                          declared=f"artifact: {artifact}\nseed: {SEED}\n")
    assert reports[0]["verdict"] == "REPRODUCED", reports[0]["verdict"]
    assert reports[0]["metadata"]["weights"]["status"] == "varied", reports[0]["metadata"]["weights"]
    assert code == 1 and "did not hold: weights" in printed, (code, printed)
    code, _, reports, _ = cells(DiskServing())
    assert code == 0 and all(r["metadata"]["weights"]["status"] == "unchanged" for r in reports), code


def test_the_matrix_weights_window_still_fails_its_exit():
    # The matrix's own window over the run, the key both now pass.
    class Swapping(DiskServing):
        def admin(self, cfg, verb):
            if verb == "load" and self.loads == 1:
                with open(os.path.join(os.path.dirname(cfg["declaration"]), "model.gguf"), "ab") as fh:
                    fh.write(b"swapped")
            return DiskServing.admin(self, cfg, verb)
    code, records, s = run_main(Swapping())
    assert records and code == 1 and s["weights"]["status"] == "varied", (code, s["weights"])


# Class 2: the declaration is the bytes the run read.

def test_a_declaration_changed_during_preflight_is_refused_by_both():
    # Codex round ten's thread 2: the matrix took its expected digest from
    # the disk after the stack readings, so a change in that window became
    # the declaration the run held. Perturbation: drop held_declaration from
    # either preflight, and its run starts.
    def changing_toolchain():
        state = {"done": False}

        def toolchain(cfg):
            if not state["done"]:
                with open(cfg["declaration"], "a") as fh:
                    fh.write("# edited during preflight\n")
                state["done"] = True
            return {"rustc": "stub"}
        return {"toolchain": toolchain}
    err, agent = io.StringIO(), DiskServing()
    with contextlib.redirect_stderr(err):
        code, records, _ = run_main(agent, stack=changing_toolchain())
    assert code == 2 and records is None and agent.starts == 0, (code, agent.starts)
    assert "changed on disk after the run read it" in err.getvalue(), err.getvalue()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code, _, reports, _ = cells(DiskServing(), fakes=changing_toolchain())
    assert code == 2 and reports is None, code
    assert "changed on disk after the run read it" in err.getvalue(), err.getvalue()


def test_the_matrix_holds_its_loads_to_the_bytes_it_read():
    # A change landing after preflight is served by the admin, and the loads
    # are held to the digest of what the run read, so the sessions refuse.
    # Perturbation: take the digest from the disk again, and the changed
    # declaration is held as the run's own and reproduces.
    agent = DiskServing()
    decl = {}

    def remember(tmp, path):
        decl["path"] = path

    def change():
        with open(decl["path"], "a") as fh:
            fh.write("# edited after preflight\n")
    with after_preflight(dm, change):
        code, records, _ = run_main(agent, prepare=remember)
    assert code == 1 and records and all("served another declaration" in r["verdict"] for r in records), \
        (code, records and records[0]["verdict"])


def test_the_cells_serve_and_restore_the_bytes_they_read():
    # run_cell made each cell's declaration from a fresh read of the file,
    # and the restore copied the file as it stood when the backup was taken.
    # Perturbation: re-read in run_cell, or back up and restore from the
    # disk, and the edit is served or left behind.
    agent = DiskServing()
    paths = []
    real = base.run_files

    def run_files(cfg, rewrites):
        paths.append(cfg["declaration"])
        return real(cfg, rewrites)

    def change():
        with open(paths[0], "a") as fh:
            fh.write("# edited after preflight\n")
    base.run_files = run_files
    try:
        with after_preflight(base, change):
            code, _, reports, restored = cells(agent)
    finally:
        base.run_files = real
    assert code == 0 and [r["verdict"] for r in reports] == ["REPRODUCED", "REPRODUCED"], (code, reports)
    assert agent.texts and not any("edited" in t for t in agent.texts), agent.texts
    assert restored == DECL, restored


# Class 3: the closing unload is guarded.

def test_an_interrupt_at_the_closing_unload_is_recorded_by_both():
    # Codex round ten's thread 3. Perturbation: unguard the closing unload,
    # and the session is lost to both loops.
    code, records, s = run_main(FailingFinalUnload(KeyboardInterrupt()), hours="0.01")
    assert [r["verdict"] for r in records] == ["interrupted"] and code == 1, (code, records)
    code, printed, reports, restored = cells(FailingFinalUnload(KeyboardInterrupt()))
    assert code == 1 and [r["verdict"] for r in reports] == ["interrupted"], (code, reports)
    assert "provenance_at_close" in reports[0]["metadata"] and restored == DECL


def test_a_failed_closing_unload_is_a_fault_on_both():
    # The sibling: any other raise from the unload is a fault, and the run
    # goes on. Perturbation: unguard the closing unload, and a traceback
    # ends both runs.
    want = "error: RuntimeError: unload failed (the closing unload)"
    code, records, _ = run_main(FailingFinalUnload(RuntimeError("unload failed")))
    assert records and code == 1 and {r["verdict"] for r in records} == {want}, (code, records[0]["verdict"])
    code, _, reports, restored = cells(FailingFinalUnload(RuntimeError("unload failed")))
    assert code == 1 and [r["verdict"] for r in reports] == [want, want], (code, reports)
    assert restored == DECL


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
