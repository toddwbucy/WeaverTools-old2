"""The figures of a sessions sequence, per session and over the sequence.

    python3 sessions_report.py --trace TRACE --state STATE --sessions DIR
                               [--prefix s-rusty-n-] [--out FILE]

Reads the agent's trace, its sqlite state store read-only, and the directory
sessions.py wrote, and prints one JSON document: a row per session and the
totals. Only sessions whose name starts with --prefix are read, so a trace
carrying earlier sessions yields the same figures as one carrying these alone.

**A position** is what the evaluation plan's section 2 names. Within a turn: each
non-blank line of a text part of `message.assistant`, prose or program, each
action's request at `tool.call.started`, and each `message.tool_result`. The
assistant message's `tool_call` parts are not positions, the request being one
position at `tool.call.started` and a second count of it being a double count.
Outside every turn: each run's `score` event, a position of the computable
share that no candidate reads, counted in a session's and the sequence's
positions and never in a per-turn figure. Over the calibration session of
2026-09-29, `s-rusty-b`, this gives 785 positions, 783 in 41 turns and 2 score
events, a median of 4 per turn and a maximum of 115.

**Only sessions with a run record are counted**, so an attempt that left no
`run.json` contributes no turn, position or maximum, even where its events stand
in the trace.

**A decayed turn** is one whose model output broke the call format, read from
`model.output`'s verbatim emission: a call opened and never closed, the closing
tag missing or a second opening tag or a stray token in its place, the signature
#746 records. The parsed message is not the witness, and neither is the loop's
unclosed-call feedback, which lands a turn later. A session is decayed when any
of its turns is.

**The typed landing** is counted from the store by the event table's session:
messages, parts by block, measurements, series readings, and fields, the last
being values that landed verbatim rather than typed.
"""
import argparse
import collections
import json
import os
import sqlite3
import statistics



def positions(event):
    kind = event["kind"]
    if kind == "message.assistant":
        count = 0
        for part in event["payload"].get("content", []):
            if part.get("type") == "text":
                count += sum(1 for line in part.get("text", "").splitlines() if line.strip())
        return count
    return 1 if kind in ("tool.call.started", "message.tool_result") else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--sessions", required=True)
    parser.add_argument("--prefix", default="s-rusty-n-")
    parser.add_argument("--out")
    args = parser.parse_args()

    by_session = collections.defaultdict(list)
    with open(args.trace) as trace:
        for line in trace:
            event = json.loads(line)
            if str(event.get("session", "")).startswith(args.prefix):
                by_session[event["session"]].append(event)

    # The store is selected by the trace's rule, a literal prefix compared byte
    # for byte, rather than by LIKE, whose _ and % are wildcards and which folds
    # case.
    store = sqlite3.connect(f"file:{args.state}?mode=ro", uri=True)
    landing = collections.defaultdict(dict)
    for table in ("message", "measurement", "field", "series"):
        for session, count in store.execute(
                f"SELECT e.session, count(*) FROM {table} t JOIN event e ON e.id = t.event_id "
                "WHERE substr(e.session, 1, length(?)) = ? GROUP BY e.session", (args.prefix, args.prefix)):
            landing[session][table] = count
    for session, block, count in store.execute(
            "SELECT e.session, p.block, count(*) FROM part p JOIN event e ON e.id = p.event_id "
            "WHERE substr(e.session, 1, length(?)) = ? GROUP BY e.session, p.block", (args.prefix, args.prefix)):
        landing[session]["part." + block] = count

    rows = []
    incomplete = []
    for name in sorted(os.listdir(args.sessions)):
        record_path = os.path.join(args.sessions, name, "run.json")
        attempt_path = os.path.join(args.sessions, name, "attempt.json")
        if not name.startswith(args.prefix):
            continue
        # The attempt record holds the session's facts from before any external
        # work, so a run record that lacks one takes it from there, and an
        # attempt that left no run record is listed rather than counted.
        attempt = json.load(open(attempt_path)) if os.path.exists(attempt_path) else {}
        if not os.path.exists(record_path):
            if attempt:
                incomplete.append(attempt)
            continue
        record = dict(attempt, **json.load(open(record_path)))
        task = (record.get("tasks") or [{}])[0]
        events = by_session.get(name, [])
        per_turn = collections.Counter()
        decayed = set()
        opened = []
        for event in events:
            turn = event.get("turn")
            if not turn:
                continue
            key = (event["run"], turn)
            if event["kind"] == "turn.started":
                opened.append(key)
            per_turn[key] += positions(event)
            if event["kind"] == "model.output":
                emission = event["payload"].get("emission", "")
                if emission.count("<tool_call>") > emission.count("</tool_call>"):
                    decayed.add(key)
        counts = [per_turn[key] for key in opened]
        hashes = sorted({e["payload"].get("weights_hash") for e in events
                         if e["kind"] == "model.measurement" and "weights_hash" in e["payload"]})
        rows.append({
            "session": name, "seed": record.get("seed"), "task": record.get("task"),
            "name": task.get("name"), "ended": record.get("ended"),
            "ended_by": task.get("ended_by"), "result": task.get("result"),
            "score": task.get("score"), "actions": task.get("actions"),
            "seconds": task.get("seconds"), "turns": len(opened),
            "turn_positions": sum(counts),
            "score_positions": sum(1 for e in events if e["kind"] == "score"),
            "positions": sum(counts) + sum(1 for e in events if e["kind"] == "score"),
            "positions_max_turn": max(counts, default=0), "per_turn": counts,
            "decayed_turns": len(decayed), "landing": landing.get(name, {}),
            "weights_hash": [h[:16] if h else "" for h in hashes],
        })

    every_turn = [n for r in rows for n in r["per_turn"]]
    totals = {
        "sessions": len(rows),
        "completed": sum(r["ended"] == "completed" for r in rows),
        "wins": sum(r["result"] == "win" for r in rows),
        "decayed_sessions": sum(r["decayed_turns"] > 0 for r in rows),
        "turns": len(every_turn),
        "positions": sum(r["positions"] for r in rows),
        "turn_positions": sum(every_turn),
        "score_positions": sum(r["score_positions"] for r in rows),
        "positions_per_turn_median": statistics.median(every_turn) if every_turn else 0,
        "positions_per_turn_max": max(every_turn, default=0),
        "landing": dict(sum((collections.Counter(r["landing"]) for r in rows),
                            collections.Counter())),
        "decayed_turns": sum(r["decayed_turns"] for r in rows),
        "no_action_sessions": sum(r["actions"] == 0 for r in rows),
        "scored_above_zero": [[r["session"], r["name"], r["score"]] for r in rows if r["score"]],
        "ended_by": dict(collections.Counter(r["ended_by"] for r in rows if r["ended_by"])),
        "play_seconds": round(sum(r["seconds"] or 0 for r in rows)),
        "weights_hash_by_session": {r["session"]: r["weights_hash"] for r in rows},
    }
    by_task = collections.defaultdict(list)
    for r in rows:
        by_task[r["task"]].append(r)
    totals["incomplete_attempts"] = incomplete
    totals["by_task"] = [{
        "task": task, "name": group[0]["name"], "sessions": len(group),
        "scored_above_zero": sum(1 for r in group if r["score"]),
        "decayed": sum(1 for r in group if r["decayed_turns"]),
        "no_action": sum(1 for r in group if r["actions"] == 0),
        "positions": sum(r["positions"] for r in group),
        "positions_max_turn": max(r["positions_max_turn"] for r in group),
    } for task, group in sorted(by_task.items())]
    document = json.dumps({"totals": totals, "sessions": rows}, indent=1)
    if args.out:
        open(args.out, "w").write(document + "\n")
    print(document)


if __name__ == "__main__":
    main()
