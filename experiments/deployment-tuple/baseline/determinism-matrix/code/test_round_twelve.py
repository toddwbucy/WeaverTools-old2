"""Every admin answer is read, its exit status and its kind agreeing, at
every site of a session, in both modes (#716 round twelve).

Run with `python3 test_round_twelve.py` or under pytest.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import Reloading, answer, run_main  # noqa: E402
from test_round_nine import cells_run  # noqa: E402

base = dm.base
# The admin's refusals a lifecycle verb answers, each printed with exit 1.
REFUSALS = {
    "no_residency": {"kind": "no_residency", "exit": 1},
    "the worker's leave": {"kind": "organ_refused", "organ": "worker",
                           "reason": {"kind": "carried_work"}, "exit": 1},
    "boundary_unverified": {"kind": "boundary_unverified", "exit": 1},
    "activity_not_at_rest": {"kind": "activity_not_at_rest", "exit": 1},
    "bind_failed": {"kind": "bind_failed", "exit": 1},
}
# The five admin calls of one session, in order.
SITES = ("opening unload", "load", "unload between the halves", "reload", "closing unload")
WANT = {"opening unload": "the opening unload was refused", "load": "load refused",
        "unload between the halves": "the unload between the halves was refused",
        "reload": "reload refused", "closing unload": "the closing unload was refused"}


class Refusing(Reloading):
    """The first session's admin call at `site` answers `said`, and every
    other call answers as the admin does when it succeeds."""

    def __init__(self, site, said, **kw):
        Reloading.__init__(self, **kw)
        self.target, self.said, self.calls = SITES.index(site), said, 0

    def admin(self, cfg, verb):
        out = Reloading.admin(self, cfg, verb)
        self.calls += 1
        return self.said if self.calls - 1 == self.target else out


def through_both(site, said):
    """The first session's verdict and the exit code in each mode, the
    matrix's and the cells'."""
    code, records, _ = run_main(Refusing(site, said))
    cell_code, _, _, cell_records, _ = cells_run(Refusing(site, said))
    return (records[0]["verdict"], code), (cell_records[0]["verdict"], cell_code)


def test_each_refusal_at_each_site_is_a_fault_in_both_modes():
    # Codex round eleven's thread: every unload answer was dropped. Each of
    # the admin's refusals, at each of a session's five calls, is a fault
    # naming it in both modes, except nothing resident at the opening
    # unload, which is a clean start. Perturbation: drop the check at any
    # site, and its cases read REPRODUCED and exit 0.
    for site in SITES:
        for name, said in REFUSALS.items():
            (verdict, code), (cell, cell_code) = through_both(site, said)
            if site == "opening unload" and name == "no_residency":
                assert verdict == cell == "REPRODUCED" and code == cell_code == 0, (site, name, verdict, cell)
                continue
            for got, exit_code in ((verdict, code), (cell, cell_code)):
                assert got.startswith(WANT[site]) and json.dumps(said["kind"]) in got and exit_code == 1, \
                    (site, name, got, exit_code)


def test_an_answer_its_exit_status_does_not_bear_out_is_no_answer():
    # The kind is read only where the exit status agrees. Perturbation: read
    # the kind alone, and a state answer with exit 1 or a load answering
    # unloaded passes.
    unloaded, idle = answer("unload"), answer("load")
    for site, said in (("load", dict(idle, exit=1)), ("load", answer("unload")),
                       ("unload between the halves", dict(unloaded, exit=1)),
                       ("unload between the halves", idle),
                       ("closing unload", {"kind": "unparsed", "stdout": "", "stderr": "sudo: a password is required", "exit": 1}),
                       ("opening unload", {"kind": "no_residency", "exit": 0})):
        (verdict, code), (cell, cell_code) = through_both(site, said)
        assert verdict.startswith(WANT[site]) and cell.startswith(WANT[site]) and code == cell_code == 1, \
            (site, said, verdict, cell)
    assert base.admin_answered(unloaded, states=("unloaded",))
    assert not base.admin_answered({"kind": "state", "state": "unloaded"}, states=("unloaded",))


def test_admin_carries_the_exit_status_beside_the_answer():
    # Perturbation: return the parsed answer alone, and every step reads as
    # no answer; parse a non-object, and it passes as one.
    saved = base.sh
    try:
        for stdout, code, want in (('{"kind":"state","state":"unloaded"}\n', 0, {"kind": "state", "state": "unloaded", "exit": 0}),
                                   ('{"kind":"bind_failed"}\n', 1, {"kind": "bind_failed", "exit": 1})):
            base.sh = lambda args, stdout=stdout, code=code, **kw: subprocess.CompletedProcess(args, code, stdout, "")
            assert base.admin({"admin_config": "/c", "admin_bin": "/a", "agent": "karl"}, "unload") == want
        for stdout in ('["state"]\n', "not json\n", ""):
            base.sh = lambda args, stdout=stdout, **kw: subprocess.CompletedProcess(args, 0, stdout, "")
            assert base.admin({"admin_config": "/c", "admin_bin": "/a", "agent": "karl"}, "unload")["kind"] == "unparsed"
    finally:
        base.sh = saved


def test_the_runs_last_unload_is_read_in_both_modes():
    # The unload the main makes as a run ends: its answer is read, and a
    # refusal says the agent may still be loaded. No session rests on it.
    # Perturbation: drop release from the main, and its note is gone.
    class RefusingLast(Reloading):
        def __init__(self):
            Reloading.__init__(self)
            self.last = False

        def admin(self, cfg, verb):
            out = Reloading.admin(self, cfg, verb)
            return REFUSALS["bind_failed"] if self.last else out
    agent, logged = RefusingLast(), {}
    real = base.release

    def last(cfg):
        agent.last = True
        return real(cfg)

    def read_log(tmp, decl):
        logged["text"] = open(os.path.join(tmp, "matrix.log")).read()
    base.release = last
    try:
        code, records, _ = run_main(agent, inspect=read_log)
        agent.last = False
        cell_code, _, printed, *_ = cells_run(agent)
    finally:
        base.release = real
    note = "the run's closing unload was refused, the agent may still be loaded"
    assert code == 0 and records and note in logged["text"], code
    assert cell_code == 0 and note in printed, (cell_code, printed[-400:])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
