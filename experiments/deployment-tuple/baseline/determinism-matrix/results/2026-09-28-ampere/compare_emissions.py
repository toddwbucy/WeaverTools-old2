"""Compare the emissions of three determinism-matrix deposits, turn slot by turn slot,
and the files each run held.

    python3 compare_emissions.py <karl deposit> <fred deposit> <run3 deposit>

Stdlib only. It reads each deposit's matrix.jsonl and summary.json and writes nothing.

A turn slot is one (probe, depth, turn) of the 8 prompts by 4 depths. Within a run,
every session of a cell carries an emission_sha256 per turn, and a slot's emission set
is every hash that slot produced across the run. Two runs agree on a slot when the sets
are equal.

It backs these lines of README.md beside it:
- "Within each run, one emission per turn slot": the 464 slots of 32 cells, each with
  one hash, for all three runs.
- "The two A6000 cards agree exactly: 464 of 464 turn slots identical."
- "Each A6000 against run3: 444 turn slots identical, 20 different", all 20 on the
  probe turn out of 32 probe-turn slots, how many of the 20 generate more than one
  token on each side, the cells with a difference by prompt
  character (near-tie 11 of 12, mid 8 of 8, confident 1 of 12, and which probes), and
  the probes identical in every cell.
- "What differs between the boxes, by reading": the engine libraries and the weaver
  binaries by sha256, and the artifact and toolchain that match, from each run's
  summary.json.

It is the Planner seat's comparison of 2026-09-28, taking its three paths as arguments.
"""
import ast
import collections
import json
import os
import sys


def load(deposit):
    """Each slot's emission set, whether it is the probe turn, the token counts it
    produced, each probe's character, and the session count and verdicts."""
    emissions = collections.defaultdict(set)
    tokens = collections.defaultdict(set)
    is_probe = {}
    character = {}
    verdicts = collections.Counter()
    with open(os.path.join(deposit, "matrix.jsonl")) as fh:
        for line in fh:
            record = json.loads(line)
            verdicts[record["verdict"]] += 1
            character[record["probe"]] = record["character"]
            turns = record["turns"]
            turns = ast.literal_eval(turns) if isinstance(turns, str) else turns
            for turn in turns:
                if "emission_sha256" in turn:
                    slot = (record["probe"], record["depth"], turn["turn"])
                    emissions[slot].add(turn["emission_sha256"])
                    is_probe[slot] = bool(turn.get("is_probe"))
                    tokens[slot].add((turn.get("entropy") or {}).get("count", 0))
    return emissions, is_probe, character, verdicts, tokens


def within(name, run):
    emissions, _, _, verdicts, _ = run
    cells = {(p, d) for p, d, _ in emissions}
    multi = sum(1 for hashes in emissions.values() if len(hashes) > 1)
    print(f"{name}: sessions {sum(verdicts.values())}, verdicts {dict(verdicts)}, "
          f"cells {len(cells)}, turn slots {len(emissions)}, "
          f"slots with more than one emission {multi}")


def compare(name_a, run_a, name_b, run_b):
    ea, probe_a, char_a, _, tok_a = run_a
    eb, _, _, _, tok_b = run_b
    shared = set(ea) & set(eb)
    differ = sorted(slot for slot in shared if ea[slot] != eb[slot])
    print(f"\n{name_a} against {name_b}: turn slots identical {len(shared) - len(differ)}, "
          f"different {len(differ)}")
    if not differ:
        return
    probe_slots = sum(1 for slot in ea if probe_a[slot])
    on_probe = sum(1 for slot in differ if probe_a[slot])
    print(f"  on the probe turn {on_probe} of {len(differ)}, "
          f"out of {probe_slots} probe-turn slots")
    multi_a = sum(1 for slot in differ if max(tok_a[slot]) > 1)
    multi_b = sum(1 for slot in differ if max(tok_b[slot]) > 1)
    print(f"  generating more than one token: {multi_a} of {len(differ)} in {name_a}, "
          f"{multi_b} of {len(differ)} in {name_b}")
    cells = {(p, d) for p, d, _ in ea}
    differing = {(p, d) for p, d, _ in differ}
    for kind in ("near-tie", "mid", "confident"):
        of_kind = [c for c in cells if char_a[c[0]] == kind]
        hit = [c for c in differing if char_a[c[0]] == kind]
        probes = sorted({c[0] for c in hit})
        print(f"  {kind}: {len(hit)} of {len(of_kind)} cells differ {probes}")
    untouched = sorted({p for p, _ in cells} - {p for p, _ in differing})
    print(f"  probes identical in every cell: {untouched}")


def held(names, deposits):
    """The files each run held, by sha256, side by side."""
    summaries = []
    for deposit in deposits:
        with open(os.path.join(deposit, "summary.json")) as fh:
            summaries.append(json.load(fh))
    for section in ("weights", "engine_libraries", "weaver_binaries", "toolchain"):
        print(f"\n{section}")
        for key in summaries[0][section]["reading"]:
            values = []
            for summary in summaries:
                value = summary[section]["reading"].get(key)
                if isinstance(value, dict):
                    value = value.get("sha256", "")[:8]
                values.append(str(value)[:44])
            same = "same" if len(set(values)) == 1 else "differ"
            print(f"  {key:20s} " + "  ".join(f"{n} {v}" for n, v in zip(names, values))
                  + f"  [{same}]")


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: compare_emissions.py <karl deposit> <fred deposit> <run3 deposit>")
    names = ["karl", "fred", "run3"]
    deposits = sys.argv[1:4]
    runs = dict(zip(names, (load(d) for d in deposits)))
    for name in names:
        within(name, runs[name])
    compare("karl", runs["karl"], "fred", runs["fred"])
    compare("karl", runs["karl"], "run3", runs["run3"])
    compare("fred", runs["fred"], "run3", runs["run3"])
    held(names, deposits)


if __name__ == "__main__":
    main()
