"""The figures of a sessions sequence, per session and over the sequence.

    python3 sessions_report.py --trace TRACE --state STATE --sessions DIR
                               [--prefix s-rusty-n-] [--out FILE]

Reads the agent's trace, its sqlite state store read-only, and the directory
sessions.py wrote, and prints one JSON document: a row per session and the
totals. Only sessions whose name starts with --prefix are read, so a trace
carrying earlier sessions yields the same figures as one carrying these alone.

**A position** is what the evaluation plan's section 2 names, counted per turn:
each non-blank line of a text part of `message.assistant` and each of its
`tool_call` parts, each `tool.call.started`, and each `message.tool_result`.
Over the counted pair of 2026-09-29, session `s-rusty-b`, this gives 978
positions over 41 turns, a median of 4 per turn and a maximum of 132.

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
            elif part.get("type") == "tool_call":
                count += 1
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

    store = sqlite3.connect(f"file:{args.state}?mode=ro", uri=True)
    landing = collections.defaultdict(dict)
    for table in ("message", "measurement", "field", "series"):
        for session, count in store.execute(
                f"SELECT e.session, count(*) FROM {table} t JOIN event e ON e.id = t.event_id "
                "WHERE e.session LIKE ? GROUP BY e.session", (args.prefix + "%",)):
            landing[session][table] = count
    for session, block, count in store.execute(
            "SELECT e.session, p.block, count(*) FROM part p JOIN event e ON e.id = p.event_id "
            "WHERE e.session LIKE ? GROUP BY e.session, p.block", (args.prefix + "%",)):
        landing[session]["part." + block] = count

    rows = []
    for name in sorted(os.listdir(args.sessions)):
        record_path = os.path.join(args.sessions, name, "run.json")
        if not name.startswith(args.prefix) or not os.path.exists(record_path):
            continue
        record = json.load(open(record_path))
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
        rows.append({
            "session": name, "seed": record.get("seed"), "task": record.get("task"),
            "name": task.get("name"), "ended": record.get("ended"),
            "ended_by": task.get("ended_by"), "result": task.get("result"),
            "score": task.get("score"), "actions": task.get("actions"),
            "seconds": task.get("seconds"), "turns": len(opened),
            "positions": sum(counts), "positions_max_turn": max(counts, default=0),
            "decayed_turns": len(decayed), "landing": landing.get(name, {}),
        })

    every_turn = []
    for name, events in by_session.items():
        per_turn = collections.Counter()
        for event in events:
            if event.get("turn"):
                per_turn[(event["run"], event["turn"])] += positions(event)
        every_turn += [per_turn[(e["run"], e["turn"])] for e in events
                       if e["kind"] == "turn.started"]
    totals = {
        "sessions": len(rows),
        "completed": sum(r["ended"] == "completed" for r in rows),
        "wins": sum(r["result"] == "win" for r in rows),
        "decayed_sessions": sum(r["decayed_turns"] > 0 for r in rows),
        "turns": len(every_turn),
        "positions": sum(every_turn),
        "positions_per_turn_median": statistics.median(every_turn) if every_turn else 0,
        "positions_per_turn_max": max(every_turn, default=0),
        "landing": dict(sum((collections.Counter(r["landing"]) for r in rows),
                            collections.Counter())),
    }
    document = json.dumps({"totals": totals, "sessions": rows}, indent=1)
    if args.out:
        open(args.out, "w").write(document + "\n")
    print(document)


if __name__ == "__main__":
    main()
