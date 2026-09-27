"""A session's recorded seed, and the path the 2026-09-27 runs took (#716).

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
CFG = {"trace": "unused", "agent": "karl"}
SEED = 451234785645


class Agent:
    """One load per half: the source's turns land in the first run and the
    replay's in the second, each turn a deterministic function of its text,
    its ordinal and the seed its half was loaded under, or no seed at all."""

    def __init__(self, source_seed=SEED, replay_seed=SEED):
        self.seeds, self.loads, self.runs = (source_seed, replay_seed), 0, {}

    def admin(self, cfg, verb):
        if verb == "load":
            self.loads += 1
            self.run = f"run-{self.loads}"
            self.runs[self.run] = []
        return {"kind": "state"}

    def wait_socket(self, cfg):
        return True

    def gate_turn(self, cfg, text):
        turns = self.runs[self.run]
        n = len(turns) + 1
        seed = self.seeds[self.loads - 1]
        sampling = {"generation_seed": 7 * n, "temperature": 0.7}
        if seed is not None:
            sampling["seed"] = seed
        turns.append({
            "turn": f"t-{n}", "text": text,
            "payload": {
                "model.request": {"rendered": f"<user>{text}", "sampling": sampling},
                "model.output": {"emission": [len(text), n], "finish": "stop", "resident": 12 * n},
                "model.measurement": {"input_tokens": [n, len(text)], "entropies": [0.25, 0.5 * n]},
            },
            "wall": {"turn.started": 1000 * n, "turn.closed": 1000 * n + 40},
        })
        return {"kind": "answered", "run": self.run}

    def await_turns(self, trace, want, run):
        return list(self.runs.get(run, [])), None


def session(agent, depth=2, declared_seed=None):
    saved = {k: getattr(base, k) for k in ("admin", "wait_socket", "gate_turn", "await_turns")}
    try:
        for k in saved:
            setattr(base, k, getattr(agent, k))
        return dm.run_session(CFG, dm.PROMPTS[0], depth, 1, declared_seed)
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


def test_the_path_the_runs_took_is_unchanged():
    # Perturbation: any change to a verdict, a seed field or a turn's
    # comparison on this path fails the equality.
    assert session(Agent()) == BEFORE


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

    def drifting(cfg, text):
        close = real(cfg, text)
        if agent.loads == 2:
            agent.runs[agent.run][-1]["payload"]["model.output"]["emission"].append(0)
        return close
    agent.gate_turn = drifting
    assert session(agent)["verdict"] == "DIVERGED"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
