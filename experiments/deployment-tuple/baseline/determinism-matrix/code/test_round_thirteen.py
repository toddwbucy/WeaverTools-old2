"""A binding accepted only once its block is complete, every output created
at preflight, and every step between the loop and the summary guarded
(#716, Codex's second pass on 4ad99b1).

Run with `python3 test_round_thirteen.py` or under pytest.
"""
import contextlib
import io
import os
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import Reloading, cells_main, run_main, session  # noqa: E402
from test_round_five import BOUNDARY, COMPLETE, device_line  # noqa: E402

base = dm.base
TWO = [{"ordinal": 0, "name": "NVIDIA RTX PRO 5000 Blackwell Generation Laptop GPU", "pci_bus_id": "0000:01:00.0"},
       {"ordinal": 1, "name": "NVIDIA RTX PRO 5000 Blackwell Generation Laptop GPU", "pci_bus_id": "0000:02:00.0"}]


def arriving(reads, invocation="c" * 32):
    """`sh` as the box answers while journald delivers a load's lines one
    read at a time: each journal read returns the next of `reads`, the last
    repeating."""
    served = []

    def sh(args, **kw):
        if args[0] == "systemctl":
            return subprocess.CompletedProcess(args, 0, invocation + "\n", "")
        if "-g" in args:
            lines = reads[min(len(served), len(reads) - 1)]
            served.append(lines)
            return subprocess.CompletedProcess(args, 0, "\n".join(lines) + "\n", "")
        return subprocess.CompletedProcess(args, 0, "a line\n", "")
    return sh, served


def test_a_two_card_block_split_over_two_reads_records_both():
    # Codex's second pass, thread 1: the reader took the first non-empty
    # list, so a block arriving a line at a time recorded its first card.
    # Perturbation: accept a reading without its completion marker, and the
    # first read's one card is recorded.
    first = [BOUNDARY, device_line(0, "0000:01:00.0")]
    whole = first + [device_line(1, "0000:02:00.0"), COMPLETE]
    sh, served = arriving([first, whole])
    saved = base.sh
    base.sh = sh
    try:
        seen, invocation = base.load_devices({"agent": "karl"}, 5, 0)
    finally:
        base.sh = saved
    assert seen == {"devices": TWO, "complete": True} and len(served) == 2, (seen, len(served))


def test_a_block_that_never_completes_is_unreadable():
    # Perturbation: return the last reading when the tries run out, and the
    # one card stands as the binding.
    sh, _ = arriving([[BOUNDARY, device_line(0, "0000:01:00.0")]])
    saved = base.sh
    base.sh = sh
    try:
        seen, invocation = base.load_devices({"agent": "karl"}, 3, 0)
    finally:
        base.sh = saved
    assert "did not complete within 3 reads" in seen["unreadable"] and invocation == "c" * 32, seen


def test_a_device_line_after_the_marker_undoes_it():
    # The engine names every device before the loader line, so a device
    # line after it is a block this reader cannot vouch for. Perturbation:
    # leave a group complete once its marker is read, and the late card's
    # block is accepted.
    late = [BOUNDARY, device_line(0, "0000:01:00.0"), COMPLETE, device_line(1, "0000:02:00.0")]
    sh, _ = arriving([late])
    saved = base.sh
    base.sh = sh
    try:
        groups = base._device_groups({"agent": "karl"}, None, "c" * 32)
        seen, invocation = base.load_devices({"agent": "karl"}, 3, 0)
    finally:
        base.sh = saved
    assert groups == {"groups": [TWO], "complete": [False]}, groups
    assert "did not complete within 3 reads" in seen["unreadable"], seen


def test_a_session_holds_the_whole_binding():
    # Through a session: the first read of each load is the first card
    # alone, and the binding recorded is both cards.
    class Arriving(Reloading):
        def __init__(self):
            Reloading.__init__(self)
            self.reads = 0

        def serving_device(self, cfg, since, invocation=None):
            self.reads += 1
            return {"devices": TWO[:1], "complete": False} if self.reads % 2 else {"devices": TWO, "complete": True}
    saved = base.load_devices.__defaults__
    base.load_devices.__defaults__ = (15, 0)
    try:
        rec = session(Arriving())
    finally:
        base.load_devices.__defaults__ = saved
    assert rec["verdict"] == "REPRODUCED" and rec["devices"] == TWO, (rec["verdict"], rec.get("devices"))


def read_only(path):
    os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)


def test_a_read_only_outdir_is_refused_before_any_load():
    # Codex's second pass, thread 2. Perturbation: drop the output probe,
    # and the run loads and fails at its first record.
    err, agent = io.StringIO(), Reloading()

    def prepare(tmp, decl):
        read_only(tmp)

    def inspect(tmp, decl):
        os.chmod(tmp, stat.S_IRWXU)
    with contextlib.redirect_stderr(err):
        code, records, _ = run_main(agent, prepare=prepare, inspect=inspect)
    assert code == 2 and agent.starts == 0 and records is None, (code, agent.starts)
    assert "cannot take the run's outputs" in err.getvalue(), err.getvalue()
    err = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
        out = os.path.join(tmp, "out")
        os.makedirs(out)
        read_only(out)
        try:
            code, called, *_ = cells_main(tmp, outdir=out)
        finally:
            os.chmod(out, stat.S_IRWXU)
        assert code == 2 and called == [] and os.listdir(out) == [], (code, called, os.listdir(out))
    assert "cannot take the run's outputs" in err.getvalue(), err.getvalue()


def test_an_interrupt_in_the_last_unload_still_writes_the_summary():
    # Codex's second pass, thread 3. Perturbation: unguard release in the
    # finally, and the interrupt escapes before summary.json.
    real, calls = base.release, []

    def release(cfg):
        calls.append(1)
        if len(calls) == 1:
            raise KeyboardInterrupt
        return real(cfg)
    logged = {}

    def inspect(tmp, decl):
        logged["text"] = open(os.path.join(tmp, "matrix.log")).read()
    base.release = release
    try:
        code, records, summary = run_main(Reloading(), inspect=inspect)
    finally:
        base.release = real
    assert summary is not None and records and code == 1, (code, summary is not None)
    assert calls == [1, 1] and "interrupted during the run's last unload, trying it once more" in logged["text"]


def test_an_interrupt_or_a_failure_in_the_restore_still_writes_the_summary():
    # The sibling in the same finally. An interrupt is tried once more and
    # the declaration restored. A failure is logged, the backup left
    # standing for the operator, and the summary still written.
    # Perturbation: unguard the restore, and summary.json is never written.
    real = os.unlink
    for raised, backup_left in ((KeyboardInterrupt, False), (PermissionError, True)):
        calls, seen = [], {}

        def unlink(path, *a, raised=raised, **k):
            if str(path).endswith(".pre-matrix"):
                calls.append(path)
                if raised is PermissionError or len(calls) == 1:
                    raise raised("the backup")
            return real(path, *a, **k)

        def inspect(tmp, decl):
            seen["backup"] = os.path.lexists(decl + ".pre-matrix")
            seen["seed"] = dm.standing_seed(open(decl).read())
            if seen["backup"]:
                real(decl + ".pre-matrix")
        dm.os.unlink = unlink
        try:
            code, records, summary = run_main(Reloading(), extra=["--seed-schedule", "11,12,13"], inspect=inspect)
        finally:
            dm.os.unlink = real
        assert summary is not None and records, (raised, code)
        assert seen["backup"] is backup_left and seen["seed"] == 451234785645, (raised, seen)


def test_an_interrupt_in_the_summary_write_is_tried_once_more():
    # The last guarded step. Perturbation: write the summary unguarded, and
    # the interrupt escapes with no summary.
    import json
    import types
    calls = []

    def dump(obj, fh, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise KeyboardInterrupt
        return json.dump(obj, fh, **kw)
    real = dm.json
    dm.json = types.SimpleNamespace(dump=dump, dumps=json.dumps, loads=json.loads)
    try:
        code, records, summary = run_main(Reloading())
    finally:
        dm.json = real
    assert summary is not None and records and code == 1 and calls == [1, 1], (code, calls)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
