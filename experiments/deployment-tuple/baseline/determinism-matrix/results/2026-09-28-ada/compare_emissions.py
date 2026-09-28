"""Compare the emissions of any number of determinism-matrix deposits, turn slot by
turn slot, every pair, and the files each run held.

    python3 compare_emissions.py <name>=<deposit> <name>=<deposit> ...

Stdlib only. It reads each deposit's matrix.jsonl and summary.json and writes nothing.

A turn slot is one (probe, depth, turn) of the 8 prompts by 4 depths. Within a run,
every session of a cell carries an emission_sha256 per turn, and a slot's emission set
is every hash that slot produced across the run. Two runs agree on a slot when the sets
are equal.

It backs the lines of README.md beside it that give, per run, the slots with one
emission, and for each pair of runs the slots identical and different, how many of the
different slots are probe turns and multi-token, the differing cells by prompt
character, and the probes identical in every cell. It also gives, over the slots every run holds, how the runs group by
emission, pattern by pattern, and the held files by sha256 side by side. It is the Ampere report's script of the same name, generalised
from three fixed deposits to named ones.
"""
import ast
import collections
import itertools
import json
import os
import sys


def load(deposit):
    emissions = collections.defaultdict(set)
    is_probe = {}
    tokens = collections.defaultdict(set)
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
    print(f"  on the probe turn {on_probe} of {len(differ)}, out of {probe_slots} probe-turn slots")
    multi_a = sum(1 for slot in differ if max(tok_a[slot]) > 1)
    multi_b = sum(1 for slot in differ if max(tok_b[slot]) > 1)
    print(f"  generating more than one token: {multi_a} of {len(differ)} in {name_a}, "
          f"{multi_b} of {len(differ)} in {name_b}")
    cells = {(p, d) for p, d, _ in ea}
    differing = {(p, d) for p, d, _ in differ}
    for kind in ("near-tie", "mid", "confident"):
        of_kind = [c for c in cells if char_a[c[0]] == kind]
        hit = [c for c in differing if char_a[c[0]] == kind]
        print(f"  {kind}: {len(hit)} of {len(of_kind)} cells differ {sorted({c[0] for c in hit})}")
    untouched = sorted({p for p, _ in cells} - {p for p, _ in differing})
    print(f"  probes identical in every cell: {untouched}")


def partition(names, runs):
    """Over the slots every run holds, how the runs group by emission: each pattern
    names the runs that agree, groups separated by a bar, and counts the slots."""
    shared = set.intersection(*(set(runs[n][0]) for n in names))
    patterns = collections.Counter()
    probe = runs[names[0]][1]
    for slot in sorted(shared):
        groups = []
        for n in names:
            hashes = runs[n][0][slot]
            for g in groups:
                if runs[g[0]][0][slot] == hashes:
                    g.append(n); break
            else:
                groups.append([n])
        patterns[(" | ".join("=".join(g) for g in groups), probe[slot])] += 1
    print(f"\nagreement over the {len(shared)} slots every run holds, by pattern (probe turn or filler):")
    for (pattern, is_probe), count in sorted(patterns.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {'probe ' if is_probe else 'filler'}  {pattern}")


def held(names, deposits):
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
    print("\nserving_device")
    for name, summary in zip(names, summaries):
        print(f"  {name}: {summary.get('serving_device')}")


def main():
    args = sys.argv[1:]
    if len(args) < 2 or any("=" not in a for a in args):
        sys.exit("usage: compare_emissions.py <name>=<deposit> <name>=<deposit> ...")
    names = [a.split("=", 1)[0] for a in args]
    deposits = [a.split("=", 1)[1] for a in args]
    runs = {n: load(d) for n, d in zip(names, deposits)}
    for name in names:
        within(name, runs[name])
    for a, b in itertools.combinations(names, 2):
        compare(a, runs[a], b, runs[b])
    if len(names) > 2:
        partition(names, runs)
    held(names, deposits)


if __name__ == "__main__":
    main()
