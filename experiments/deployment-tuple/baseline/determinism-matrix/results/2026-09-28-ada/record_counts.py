"""Count one determinism-matrix deposit's record, for its result note.

    python3 record_counts.py <deposit>

Stdlib only. It reads the deposit's matrix.jsonl, matrix.log, summary.json and
run-exit.txt and writes nothing.

It backs these lines of fred-ada/RESULT-2026-09-28.md, and the matching lines of
README.md: the window's start and close, the sweeps, the
sessions and their verdicts, the counts by prompt character, the exit, the unit
invocations and how many are distinct, the turns compared and unmatched, the turns
that generated more than one token (entropy.count above 1), which the Spec's section 8
counts separately as substantive generations, the declared
and recorded seeds, and the device every session bound.
"""
import ast
import collections
import json
import os
import sys


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: record_counts.py <deposit>")
    deposit = sys.argv[1]
    verdicts = collections.Counter()
    invocations = []
    turns = unmatched = multi_token = 0
    seeds = collections.Counter()
    devices = collections.Counter()
    iterations = set()
    with open(os.path.join(deposit, "matrix.jsonl")) as fh:
        for line in fh:
            record = json.loads(line)
            verdicts[record["verdict"]] += 1
            invocations.extend(record.get("invocations", []))
            iterations.add(record["iteration"])
            seeds[(record["declared_seed"], record["recorded_seed"],
                   record["replay_recorded_seed"])] += 1
            for device in record.get("devices", []):
                devices[(device["ordinal"], device["name"], device["pci_bus_id"])] += 1
            record_turns = record["turns"]
            if isinstance(record_turns, str):
                record_turns = ast.literal_eval(record_turns)
            for turn in record_turns:
                turns += 1
                unmatched += 0 if turn.get("matched") else 1
                multi_token += 1 if (turn.get("entropy") or {}).get("count", 0) > 1 else 0
    with open(os.path.join(deposit, "matrix.log")) as fh:
        log = fh.read().splitlines()
    with open(os.path.join(deposit, "summary.json")) as fh:
        summary = json.load(fh)
    exit_line = ""
    exit_path = os.path.join(deposit, "run-exit.txt")
    if os.path.exists(exit_path):
        with open(exit_path) as fh:
            exit_line = fh.read().strip()

    first = log[0].split("]")[0].lstrip("[")
    last = next(line for line in reversed(log) if line.startswith("[")).split("]")[0].lstrip("[")
    print(f"window, by the log's clock: {first} to {last}")
    print(f"sweeps: {min(iterations)} to {max(iterations)}")
    print(f"sessions: {sum(verdicts.values())}, verdicts {dict(verdicts)}")
    print(f"summary: reproduced {summary['reproduced']}, diverged {summary['diverged']}, "
          f"errors {summary['errors']}")
    for kind, counts in summary["by_character"].items():
        print(f"  {kind}: {counts['ok']} of {counts['n']}")
    print(f"exit: {exit_line or 'no run-exit.txt'}")
    print(f"invocations: {len(invocations)}, distinct {len(set(invocations))}")
    print(f"turns compared: {turns}, unmatched {unmatched}")
    print(f"turns generating more than one token: {multi_token}")
    print(f"seeds (declared, recorded, replay recorded): {dict(seeds)}")
    print(f"devices bound: {dict(devices)}")
    print(f"serving_device: {summary['serving_device']}")
    held = {k: summary[k]["status"] for k in
            ("weights", "engine_libraries", "weaver_binaries", "toolchain")}
    print(f"held at the close: {held}")


if __name__ == "__main__":
    main()
