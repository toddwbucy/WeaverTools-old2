"""Absence never passes as agreement, and no evidence is dropped (#716).

Round three walked both classes across `confirm_cells.py` and
`determinism_matrix.py`. Each test here holds one site, and each names the
perturbation that fails it. Run with `python3 test_absence_and_evidence.py`
or under pytest.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import CARD, HELD, Agent, session, unheld  # noqa: E402

base = dm.base


class Editing(Agent):
    """An agent whose trace a test edits after each turn is written: `edit`
    receives the half (0 source, 1 replay) and that half's events."""

    def __init__(self, edit, **kw):
        Agent.__init__(self, **kw)
        self.edit = edit

    def gate_turn(self, cfg, text, timeout=None):
        close = Agent.gate_turn(self, cfg, text)
        self.edit(self.loads - 1, self.runs[self.run])
        return close


def of(events, kind):
    return [e for e in events if e["kind"] == kind]


def test_a_check_absent_from_both_records_is_a_fault():
    # Codex's round-three thread 1, the comparator: two records both missing
    # a CHECKS value compared equal and matched. Perturbation: compare_turn
    # without the `absent` clause, and the first case reads REPRODUCED.
    def drop_generation_seed(half, events):
        for e in of(events, "model.request"):
            e["payload"]["sampling"].pop("generation_seed", None)

    def null_entropies(half, events):
        for e in of(events, "model.measurement"):
            e["payload"]["entropies"] = None

    def drop_on_replay(half, events):
        if half == 1:
            for e in of(events, "model.output"):
                e["payload"].pop("resident", None)
    for edit, want in [(drop_generation_seed, "derived generation seed absent from the source and replay record"),
                       (null_entropies, "per-token entropies absent from the source and replay record"),
                       (drop_on_replay, "resident count absent from the replay record")]:
        rec = session(Editing(edit))
        assert rec["verdict"] == f"t-1: {want}", rec["verdict"]


def test_an_incomplete_turn_is_refused_by_name_not_dropped():
    # C1 and C2: cut_turns dropped a turn missing a payload kind and read a
    # kind's first event only. Perturbation: restore the filter, and the
    # surplus replay turn vanishes and the session reads REPRODUCED.
    def no_output_on_source(half, events):
        if half == 0:
            for e in of(events, "model.output"):
                events.remove(e)

    def twice_on_replay(half, events):
        if half == 1:
            events.append(dict(of(events, "model.output")[-1]))

    def surplus_on_replay(half, events):
        if half == 1 and len(of(events, "turn.started")) == 2:
            events.append({"run": events[0]["run"], "turn": "t-3", "kind": "message.user",
                           "wall_ms": 0, "payload": {"content": [{"type": "text", "text": "x"}]}})
    rec = session(Editing(no_output_on_source), depth=2)
    assert rec["verdict"] == "source t-1 is incomplete: no model.output", rec["verdict"]
    rec = session(Editing(twice_on_replay))
    assert rec["verdict"] == "replay t-1 is incomplete: 2 model.output events", rec["verdict"]
    rec = session(Editing(surplus_on_replay))
    assert rec["verdict"] == ("replay t-3 is incomplete: no model.request, no model.output,"
                              " no model.measurement, no turn.closed"), rec["verdict"]


def test_await_turns_waits_on_complete_turns_only():
    # Keeping incomplete turns must not end the wait on a turn still being
    # written. Perturbation: count every turn, and the half-written one ends
    # the wait.
    complete = [{"run": "r", "turn": "t-1", "kind": k, "payload": {"content": [{"type": "text", "text": "a"}]}
                 if k == "message.user" else {}}
                for k in ("message.user", "model.request", "model.output", "model.measurement", "turn.closed")]
    saved = base.read_runs
    try:
        # Half-written, and written but for its closing event: the wait runs
        # on through both (#716, after round twelve, for the second).
        for part in (complete[:2], complete[:-1]):
            base.read_runs = lambda path, keep=None, part=part: (["r"], {"r": part})
            started = __import__("time").time()
            turns, _ = base.await_turns("unused", 1, "r", timeout=0.3)
            assert __import__("time").time() - started >= 0.3, "the wait ended on an unclosed turn"
            assert turns and turns[0]["incomplete"], turns
        base.read_runs = lambda path, keep=None: (["r"], {"r": complete})
        turns, _ = base.await_turns("unused", 1, "r", timeout=0.3)
        assert turns and not turns[0]["incomplete"], turns
    finally:
        base.read_runs = saved


def test_a_replay_turn_missing_by_name_is_a_fault_not_divergence():
    # A source turn the replay does not carry read DIVERGED, the strongest
    # model negative, for what is the record. Perturbation: restore the
    # `missing` append and `continue`, and it reads DIVERGED.
    def rename_on_replay(half, events):
        if half == 1:
            for e in events:
                if e.get("turn") == "t-1":
                    e["turn"] = "t-9"
    rec = session(Editing(rename_on_replay))
    assert rec["verdict"] == "the replay carries no t-1", rec["verdict"]


def test_each_load_reads_its_own_device():
    # Codex's round-three thread 2, at the root: the journal window read at
    # the end of a run on this box keeps minutes, so each load's device is
    # read as it stands. Perturbation: skip load_device, or the halves'
    # comparison, and a case here reads REPRODUCED.
    other = [dict(CARD[0], ordinal=1, pci_bus_id="0000:02:00.0")]
    saved = base.load_devices.__defaults__
    base.load_devices.__defaults__ = (1, 0)
    try:
        for devices, want in [(({"unreadable": "journal"}, {"devices": CARD, "complete": True}), "the source load's serving device could not be read"),
                              (({"devices": CARD, "complete": True}, {"devices": [], "complete": True}),
                               "the replay load's serving device could not be read"),
                              (({"devices": CARD, "complete": True}, {"devices": other, "complete": True}),
                               "source and replay did not bind the same devices")]:
            rec = session(Agent(devices=devices))
            assert rec["verdict"].startswith(want), rec["verdict"]
    finally:
        base.load_devices.__defaults__ = saved
    assert base.run_binding([{"devices": CARD}, {"devices": CARD}, {}]) == CARD
    assert base.run_binding([{"devices": CARD}, {"devices": other}]) == {"varied": [CARD, other]}
    assert "unreadable" in base.run_binding([{}, {}])
    assert unheld(devices=[CARD, other]) == ["serving_device"]


def journal(lines, probe="-- some line --"):
    """`sh` answering the device grep with these lines and the probe read."""
    def sh(args, **kw):
        if "-g" in args:
            return subprocess.CompletedProcess(args, 0 if lines else 1, "\n".join(lines) + "\n", "")
        return subprocess.CompletedProcess(args, 0, probe, "")
    return sh


BOUNDARY = "ggml_cuda_init: found 1 CUDA devices (Total VRAM: 24075 MiB):"
DEVICE = ("llama_model_load_from_file_impl: using device CUDA0 (NVIDIA RTX PRO 5000 Blackwell"
          " Generation Laptop GPU) (0000:01:00.0) - 23322 MiB free")


def test_the_device_reader_drops_no_load():
    # D1-D3: an empty group was filtered out, a device line before any
    # boundary was dropped, and a line the pattern could not read vanished.
    # The first two lines are today's journal, verbatim, which parses to one
    # clean binding. Perturbation: restore `[g for g in groups if g]`, or the
    # `current is not None` guard, or the silent skip, and a case fails.
    saved = base.sh
    try:
        base.sh = journal([BOUNDARY, DEVICE, BOUNDARY, DEVICE])
        assert base._device_groups({"agent": "karl"}, "t")["groups"] == [[CARD_ON_BOX], [CARD_ON_BOX]]
        base.sh = journal([BOUNDARY, DEVICE, BOUNDARY])
        assert base._device_groups({"agent": "karl"}, "t")["groups"][-1] == []
        base.sh = journal([DEVICE, BOUNDARY, DEVICE])
        assert base._device_groups({"agent": "karl"}, "t")["groups"] == [[CARD_ON_BOX], [CARD_ON_BOX]]
        base.sh = journal([BOUNDARY, "using device CUDA0 in a shape nobody wrote"])
        groups = base._device_groups({"agent": "karl"}, "t")["groups"]
        assert "unreadable" in groups[0][0], groups
        assert "unreadable" in base.serving_device({"agent": "karl"}, "t")
        assert unheld(devices=[groups[0]]) == ["serving_device"]
    finally:
        base.sh = saved


CARD_ON_BOX = {"ordinal": 0, "name": "NVIDIA RTX PRO 5000 Blackwell Generation Laptop GPU",
               "pci_bus_id": "0000:01:00.0"}


def test_an_engine_library_line_nobody_can_parse_is_unreadable():
    # S2. Perturbation: restore the bare `continue`, and the library is not
    # in the reading at all.
    import tempfile
    saved_sh, saved_stat = base.sh, base._stat_spu
    with tempfile.NamedTemporaryFile() as lib:
        ldd = f"\tlibggml.so.0 => {lib.name} (0x00007f)\n\tlibllama.so.0 (0x00007f)\n"
        try:
            base._stat_spu = lambda p: None
            base.sh = lambda args, **kw: subprocess.CompletedProcess(args, 0, ldd, "")
            reading = base.engine_libraries({}, ("/spu", "admin config spu-binary"))
            assert "libggml.so.0" in reading and not base.is_reading(reading), reading
        finally:
            base.sh, base._stat_spu = saved_sh, saved_stat


def test_a_guessed_binary_is_not_held():
    # S1. Perturbation: drop the guessed clause in run_verdict.
    held = dict(HELD, weaver_binaries={"status": "unchanged", "reading": {
        "spu-binary": {"path": "/x", "sha256": "a" * 64, "resolved_by": "guessed beside admin_bin, the admin config naming none"}}})
    assert unheld(held) == ["weaver_binaries"]


def test_a_run_is_never_held_by_default():
    # RC3: an empty `all()` held a report carrying no closing window. The
    # run-wide verdict holds nothing it did not read: no session, no window,
    # or a window missing a stack field. Perturbation: take the fields from
    # the windows alone, or test `all()` over no sessions, and a case passes.
    one = [{"verdict": "REPRODUCED", "devices": CARD}]
    assert base.run_verdict([], HELD) == (False, ["serving_device"])
    assert base.run_verdict(one, {}) == (True, list(base.REQUIRED_WINDOWS))
    assert base.run_verdict(one, {"toolchain": {"status": "unchanged"}}) == (True, ["weights", "engine_libraries", "weaver_binaries"])
    assert base.run_verdict(one, dict(HELD, toolchain={"status": "varied"})) == (True, ["toolchain"])
    assert base.run_verdict(one, HELD) == (True, [])


def test_a_non_numeric_entropy_is_counted_not_hidden():
    # E1. Perturbation: drop the `non_numeric` count.
    turn = {"payload": {"model.measurement": {"entropies": [0.5, None, 1.5]}}}
    assert dm.entropies_of(turn)["non_numeric"] == 1
    # A boolean is not an entropy, though Python counts it an int.
    assert dm.entropies_of({"payload": {"model.measurement": {"entropies": [0.5, True]}}})["non_numeric"] == 1
    assert "non_numeric" not in dm.entropies_of({"payload": {"model.measurement": {"entropies": [0.5]}}})


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
