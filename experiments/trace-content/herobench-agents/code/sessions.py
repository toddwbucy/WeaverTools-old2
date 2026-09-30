"""A sequence of sessions, one task each, for the classifier evaluation's corpus.

    python sessions.py --agent NAME --port PORT --herobench DIR --out DIR
                       --declare 'COMMAND {session} {seed}' --seed-base N
                       [--count 50] [--first 1] [--prefix s-NAME-n-]
                       [--level 1] [--tasks 1-9] [--turn-cap 8]
                       [--stop-after 3] [--task-timeout 7200]

Run with the same interpreter and environment as run.py, which it calls once per
session. The unit the evaluation plan splits by is the session, so each session
here is its own: session n is named PREFIX followed by n to three digits, its
seed is the seed base plus n, and its one task is drawn round-robin from --tasks,
session n taking the ((n - first) mod k)-th of the k tasks.

The session and the seed are the declaration's, not the driver's, so before each
session --declare runs with {session} and {seed} filled in, and it must leave the
agent declared under them or exit nonzero. How that is done is the box's affair
and stays out of this script. Then run.py plays the task as one run under
OUT/<session>, and this script adds the session, the seed, the level and the
task to that run.json.

A session fails when the declare command exits nonzero, when run.py leaves no
run.json, or when its run.json ends other than completed: a refused load, a load
that stood no gate, a timeout or an error. A failed session is recorded and the
sequence goes on to the next, and --stop-after consecutive failures stop it. A
session name is used once: an attempt record, `attempt.json`, is written in the
session's directory before anything starts, the declaration included, and a
name with one is skipped on a rerun whether or not its run finished, the
incomplete ones printed for the operator rather than retried. A stopped sequence
resumes by running the same command again, and a failure stands in the record. OUT/sessions.json
lists every session this script touched, written after each one.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def span(text):
    first, _, last = text.partition("-")
    return list(range(int(first), int(last or first) + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--herobench", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--declare", required=True)
    parser.add_argument("--seed-base", type=int, required=True)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--first", type=int, default=1)
    parser.add_argument("--prefix")
    parser.add_argument("--level", default="1")
    parser.add_argument("--tasks", default="1-9")
    parser.add_argument("--turn-cap", type=int, default=8)
    parser.add_argument("--stop-after", type=int, default=3)
    parser.add_argument("--task-timeout", type=int, default=7200)
    args = parser.parse_args()

    prefix = args.prefix or f"s-{args.agent}-n-"
    tasks = span(args.tasks)
    os.makedirs(args.out, exist_ok=True)
    index_path = os.path.join(args.out, "sessions.json")
    index = {"agent": args.agent, "level": args.level, "tasks": tasks,
             "seed_base": args.seed_base, "turn_cap": args.turn_cap,
             "declare": args.declare, "sessions": []}
    if os.path.exists(index_path):
        index["sessions"] = json.load(open(index_path)).get("sessions", [])

    failures = 0
    for n in range(args.first, args.first + args.count):
        session = f"{prefix}{n:03d}"
        seed = args.seed_base + n
        task = tasks[(n - args.first) % len(tasks)]
        out = os.path.join(args.out, session)
        record_path = os.path.join(out, "run.json")
        attempt_path = os.path.join(out, "attempt.json")
        # **A session name is used once.** An attempt record is written before
        # anything starts, the declaration included, so a name that was ever
        # attempted is skipped on a rerun whether or not its run finished, and a
        # partial attempt never shares a name, a directory or a report row with a
        # retry. An attempt that left no run.json is named for the operator.
        if os.path.exists(attempt_path) or os.path.exists(record_path):
            if os.path.exists(record_path):
                print(f"{session}: already attempted, skipped", flush=True)
            else:
                print(f"{session}: attempted and incomplete, skipped, for the operator",
                      flush=True)
            continue
        entry = {"session": session, "seed": seed, "level": args.level, "task": task,
                 "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        os.makedirs(out, exist_ok=True)
        json.dump(entry, open(attempt_path, "w"), indent=1)
        index["sessions"].append(entry)

        declare = [part.format(session=session, seed=seed)
                   for part in shlex.split(args.declare)]
        declared = subprocess.run(declare, capture_output=True, text=True)
        entry["declare_exit"] = declared.returncode
        if declared.returncode != 0:
            entry["ended"] = "declare failed: " + (declared.stderr or declared.stdout)[-400:]
        else:
            subprocess.run(
                [sys.executable, os.path.join(HERE, "run.py"),
                 "--agent", args.agent, "--port", str(args.port),
                 "--herobench", args.herobench, "--out", out,
                 "--level", args.level, "--tasks", str(task),
                 "--turn-cap", str(args.turn_cap), "--label", session,
                 "--task-timeout", str(args.task_timeout)])
            if os.path.exists(record_path):
                record = json.load(open(record_path))
                record.update({"session": session, "seed": seed, "task": task})
                json.dump(record, open(record_path, "w"), indent=1)
                entry["ended"] = record.get("ended", "unknown")
                first = (record.get("tasks") or [{}])[0]
                for key in ("result", "score", "actions", "ended_by"):
                    if key in first:
                        entry[key] = first[key]
            else:
                entry["ended"] = "run.py left no run.json"
        entry["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        json.dump(index, open(index_path, "w"), indent=1)
        print(f"{session} seed {seed} task {task}: {entry['ended']}", flush=True)

        failures = 0 if entry["ended"] == "completed" else failures + 1
        if failures >= args.stop_after:
            print(f"{failures} consecutive sessions failed, the sequence stops",
                  flush=True)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
