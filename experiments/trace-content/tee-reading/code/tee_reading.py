"""What crossed the state tee, what the tool results cost, what the asks carried,
how much of the context is the model's own text, and what the readings weigh.

    python3 tee_reading.py --trace TRACE --state STATE --sessions PREFIX[,PREFIX]
                           --out FILE [--asks]

Reads an agent's trace and its sqlite state store, read-only, over the sessions
whose names start with any PREFIX, and writes one JSON document to --out with a
section per question. It prints only the section names and their sizes, so the
figures are read from the file rather than from the console. With --asks it
writes the asks section alone, for sessions of more than one run.

Sizes are bytes of UTF-8, of a payload value as compact JSON unless named
otherwise. Tokens are the model's own counts, from `model.measurement`'s
`input_tokens` and `output_tokens` and `model.output`'s `resident`.

**The context at a model call** is what was resident before its delta, rebuilt
from the record, and a turn's fill is that context over the capacity at the
turn's first call: the prefix the run's
open seated, then every delta rendered before the call and every emission
before it, in order. The prefix is not in any delta, so its size is read as the
first call's resident count less that call's input and output tokens and its
terminator, which every generation leaves resident. A delta's
tokens are split between its rendered segments by their share of its bytes,
each segment being user text, a tool response, or the model's own text. The
rebuild is checked against every call's `resident`, and the largest difference
is written beside the figures, so a flush or elision the rebuild missed shows
there rather than hiding in a share.
"""
import argparse
import collections
import json
import re
import sqlite3
import statistics

EXIT = "\n\nexit status"
SEGMENT = re.compile(r"<\|im_start\|>(\w+)\n(.*?)(?=<\|im_start\|>|\Z)", re.S)
# A reference to an earlier run names the run, task or session it points back
# to. "Again" and "already" are left out on purpose: in these traces they point
# back within the run, to the model's own last action, and they would count as
# continuity what is repetition.
EARLIER = re.compile(r"\b(earlier|previous|prior|last|first) (run|runs|task|tasks|session)\b"
                     r"|\bbefore this task\b|\bearlier runs?\b", re.I)


def size(value):
    return len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode())


def spread(values):
    values = sorted(values)
    if not values:
        return {"n": 0}
    pick = lambda q: values[min(len(values) - 1, int(q * len(values)))]
    return {"n": len(values), "total": sum(values), "min": values[0],
            "p50": pick(0.5), "p90": pick(0.9), "p99": pick(0.99), "max": values[-1]}


def sessions_of(path, prefixes, exact=False):
    by = collections.defaultdict(list)
    with open(path) as trace:
        for line in trace:
            event = json.loads(line)
            name = str(event.get("session", ""))
            if (name in prefixes) if exact else any(name.startswith(p) for p in prefixes):
                by[event["session"]].append(event)
    return by


def texts(event):
    return [p.get("text", "") for p in event["payload"].get("content", [])
            if p.get("type") == "text"]


def turn_key(event):
    """A turn named whole, so no two sessions' or runs' turns share a key."""
    return (event["session"], event["run"], event.get("turn"))


def decayed(emission):
    """The signature #746 records, read from the model's verbatim emission: a
    call opened and never closed, whether the closing tag is missing, replaced
    by a second opening tag, or replaced by a stray token."""
    return emission.count("<tool_call>") > emission.count("</tool_call>")


def decayed_turns(events):
    """The turns holding a decayed emission. The decay is the turn's own, so it
    is read from `model.output` rather than from the parsed message or from the
    loop's feedback, which lands a turn later."""
    return {turn_key(event) for event in events
            if event["kind"] == "model.output"
            and decayed(event["payload"].get("emission", ""))}


RECALLED = ("message.system", "message.user", "message.assistant",
            "message.tool_result", "message.restored")


def crossed_pairs(event, paths):
    """The pairs an event's distillate carries, key to canonical JSON text, by
    `weaver_trace::tee::distill`'s rule: a turnless `message.system` and a
    `message.restored` cross whole, one pair per top-level payload member under
    every election, and any other kind crosses its elected paths it holds."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return {}
    if ((event["kind"] == "message.system" and not event.get("turn"))
            or event["kind"] == "message.restored"):
        keys = list(payload)
    else:
        keys = [path for path in paths if path in payload]
    return {key: json.dumps(payload[key], separators=(",", ":"), ensure_ascii=False)
            for key in keys}


def recall_frame(events):
    """A recall answer as `weaver-state`'s `render_recall_answer` serialises it:
    each event's envelope and pairs, keys in sorted order as serde_json's map
    holds them, pair values spliced as custody kept them, which the landing's
    exactness rule makes the text that crossed."""
    rendered = []
    for event, pairs in events:
        envelope = {"session": event["session"], "run": event["run"],
                    "kind": event["kind"], "sequence": str(event["sequence"])}
        if event.get("turn"):
            envelope["turn"] = event["turn"]
        env = json.dumps(dict(sorted(envelope.items())), separators=(",", ":"),
                         ensure_ascii=False)
        body = ",".join(json.dumps(k, ensure_ascii=False) + ":" + v
                        for k, v in sorted(pairs.items()))
        rendered.append('{"envelope":' + env + ',"pairs":{' + body + "}}")
    return '{"answer":{"recall":{"events":[' + ",".join(rendered) + "]}}}\n"


# 1 and 5: what crossed, and what the store holds of it.

def crossing(by, store, prefixes, exact=False):
    """Each event is measured against the election its own run's load declared,
    so a document over runs of different elections counts each by its own."""
    elected = {}
    by_run = {}
    elections = collections.Counter()
    kinds = collections.defaultdict(lambda: {"events": 0, "payload_bytes": 0,
                                             "elected_bytes": 0})
    readings = collections.defaultdict(list)
    per_turn = collections.defaultdict(int)
    for events in by.values():
        for event in events:
            if event["kind"] == "load":
                tee = event["payload"].get("tee", {})
                elections[json.dumps(tee, sort_keys=True)] += 1
                by_run[(event["session"], event["run"])] = {
                    k["kind"]: k["paths"] for k in tee.get("keys", [])}
                if not elected:
                    elected = dict(by_run[(event["session"], event["run"])])
                    elected["all_kinds"] = tee.get("all_kinds")
            row = kinds[event["kind"]]
            row["events"] += 1
            payload = event.get("payload")
            if payload is not None:
                row["payload_bytes"] += size(payload)
            paths = by_run.get((event["session"], event["run"]), {}).get(event["kind"], [])
            for path, text in crossed_pairs(event, paths).items():
                n = len(text.encode())
                row["elected_bytes"] += n
                if event["kind"] == "model.measurement":
                    readings[path].append(n)
                    per_turn[turn_key(event)] += n
    # The store is filtered by the trace's own rule, a name whole or a literal
    # prefix compared byte for byte, so a document never counts one session's
    # events and another's rows. LIKE is not that rule: its _ and % are
    # wildcards and it folds case.
    if exact:
        like = list(prefixes)
        where = " OR ".join("e.session = ?" for _ in like)
    else:
        like = [v for p in prefixes for v in (p, p)]
        where = " OR ".join("substr(e.session, 1, length(?)) = ?" for _ in prefixes)

    def rows(sql):
        return store.execute(sql.replace("WHERE", f"WHERE ({where}) AND")
                             if "WHERE" in sql else sql + f" WHERE {where}", like).fetchall()

    typed = {
        "event_rows": rows("SELECT count(*) FROM event e")[0][0],
        "message_rows": rows("SELECT count(*) FROM message t JOIN event e ON e.id = t.event_id")[0][0],
        "part_rows_by_block": dict(rows(
            "SELECT p.block, count(*) FROM part p JOIN event e ON e.id = p.event_id "
            "WHERE 1 GROUP BY p.block")),
        "part_bytes_by_block": {b: n for b, n in rows(
            "SELECT p.block, sum(length(CAST(coalesce(p.text,'') AS BLOB)) + "
            "length(CAST(coalesce(p.arguments,'') AS BLOB)) + "
            "length(CAST(coalesce(p.content,'') AS BLOB)) + length(CAST(coalesce(p.name,'') AS BLOB))) "
            "FROM part p JOIN event e ON e.id = p.event_id WHERE 1 GROUP BY p.block")},
        "measurement_rows": rows("SELECT count(*) FROM measurement t JOIN event e ON e.id = t.event_id")[0][0],
        "measurement_perplexity_typed": rows(
            "SELECT count(*) FROM measurement t JOIN event e ON e.id = t.event_id "
            "WHERE t.perplexity IS NOT NULL")[0][0],
        "series_values_by_member": dict(rows(
            "SELECT s.member, count(*) FROM series s JOIN event e ON e.id = s.event_id "
            "WHERE 1 GROUP BY s.member")),
        "series_events_by_member": dict(rows(
            "SELECT s.member, count(DISTINCT s.event_id) FROM series s JOIN event e "
            "ON e.id = s.event_id WHERE 1 GROUP BY s.member")),
    }
    verbatim = [{"kind": k, "key": key, "rows": n, "bytes": b} for k, key, n, b in rows(
        "SELECT e.kind, f.key, count(*), sum(length(CAST(f.value AS BLOB))) FROM field f "
        "JOIN event e ON e.id = f.event_id WHERE 1 GROUP BY e.kind, f.key")]
    # Would a correct parse have typed the verbatim perplexities? A value whose
    # shortest round-trip repr is its own text is one a correctly rounded parse
    # renders back exactly, so the landing's exactness rule would have typed it.
    roundtrip = [v == repr(float(v)) for (v,) in rows(
        "SELECT f.value FROM field f JOIN event e ON e.id = f.event_id WHERE f.key = 'perplexity'")]
    return {
        "elected": elected,
        "loads_by_distinct_election": sorted(elections.values(), reverse=True),
        "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1]["payload_bytes"])),
        "store_typed": typed,
        "store_verbatim": verbatim,
        "verbatim_perplexity_roundtrips_under_a_correct_parse":
            {"values": len(roundtrip), "roundtrip": sum(roundtrip)},
        "reading_bytes_per_measurement": {k: spread(v) for k, v in readings.items()},
        "reading_bytes_per_turn": spread(list(per_turn.values())),
    }


# 2: the tool results, and a distillate of each.

def classify(parsed):
    if parsed is None:
        return "unparsed"
    keys = set(parsed)
    if keys == {"error"}:
        return "error"
    for name in ("destination", "fight", "details", "item"):
        if name in keys:
            return name
    if {"x", "y", "content"} <= keys and "character" not in keys and "inventory" not in keys:
        return "tile"
    if "inventory" in keys:
        return "character"
    if "craft" in keys:
        return "item_info"
    return "other"


def character_distillate(character):
    return {"x": character.get("x"), "y": character.get("y"), "hp": character.get("hp"),
            "inventory": [{"code": s.get("code"), "quantity": s.get("quantity")}
                          for s in character.get("inventory", []) if s.get("code")]}


def distil(text):
    """What a tool result would keep if it kept the action's outcome, the
    character's position, hit points and inventory, and the exit status."""
    body, _, status = text.partition(EXIT)
    try:
        parsed = json.loads(body)
    except ValueError:
        return text, "unparsed"
    if not isinstance(parsed, dict):
        return text, "unparsed"
    kind = classify(parsed)
    kept = {}
    if kind == "error":
        kept["error"] = parsed["error"].get("message")
    elif kind == "destination":
        d = parsed["destination"]
        kept["at"] = {"x": d.get("x"), "y": d.get("y"), "content": d.get("content")}
    elif kind == "fight":
        f = parsed["fight"]
        kept["fight"] = {"result": f.get("result"), "xp": f.get("xp"), "drops": f.get("drops")}
    elif kind == "details":
        kept["details"] = parsed["details"]
    elif kind == "item":
        kept["slot"] = parsed.get("slot")
        kept["item"] = (parsed.get("item") or {}).get("code")
    elif kind == "tile":
        kept = parsed
    elif kind == "character":
        kept["character"] = character_distillate(parsed)
    else:
        kept = parsed
    if isinstance(parsed.get("character"), dict):
        kept["character"] = character_distillate(parsed["character"])
    out = json.dumps(kept, separators=(",", ":"))
    if status:
        out += EXIT + status
    return out, kind


def tool_results(by):
    sizes, distilled, characters = [], [], []
    classes = collections.defaultdict(lambda: {"n": 0, "bytes": 0, "distilled_bytes": 0})
    for events in by.values():
        for event in events:
            if event["kind"] != "message.tool_result":
                continue
            for part in event["payload"].get("content", []):
                text = part.get("content", "")
                if not isinstance(text, str):
                    text = json.dumps(text)
                kept, kind = distil(text)
                try:
                    parsed = json.loads(text.partition(EXIT)[0])
                except ValueError:
                    parsed = None
                if isinstance(parsed, dict) and isinstance(parsed.get("character"), dict):
                    characters.append(size(parsed["character"]))
                n, m = len(text.encode()), len(kept.encode())
                sizes.append(n)
                distilled.append(m)
                classes[kind]["n"] += 1
                classes[kind]["bytes"] += n
                classes[kind]["distilled_bytes"] += m
    return {"bytes": spread(sizes), "distilled_bytes": spread(distilled),
            "character_block_bytes": spread(characters),
            "classes": dict(sorted(classes.items(), key=lambda kv: -kv[1]["bytes"]))}


# 2 and 4: the context at each call, rebuilt, by origin.

def origin(role, body):
    if role == "user" and body.lstrip().startswith("<tool_response>"):
        return "tool"
    if role == "assistant":
        return "own"
    return "user"


def contexts(by):
    """Per model call: the context's tokens by origin, the fill, and the turn."""
    calls = []
    worst = 0
    for session, events in by.items():
        runs = collections.OrderedDict()
        for event in events:
            runs.setdefault(event["run"], []).append(event)
        for run, run_events in runs.items():
            held = collections.Counter()
            prefix = None
            request = None
            output = None
            # A call is recorded as its request, its output, then its measurement,
            # so the call is accounted when the measurement closes it.
            for event in run_events:
                kind = event["kind"]
                if kind == "model.request":
                    request = event
                elif kind == "model.output" and request is not None:
                    output = event
                elif kind == "model.measurement" and output is not None:
                    payload = output["payload"]
                    inputs = len(event["payload"].get("input_tokens", []))
                    outputs = len(event["payload"].get("output_tokens", []))
                    rendered = request["payload"].get("rendered", "")
                    segments = [(origin(r, b), len(b.encode())) for r, b in SEGMENT.findall(rendered)]
                    total = sum(n for _, n in segments) or 1
                    # Each generation leaves its terminator resident, one token
                    # past its output tokens, whatever ended it.
                    outputs += 1
                    if prefix is None:
                        prefix = payload.get("resident", 0) - inputs - outputs
                        held["prefix"] = prefix
                    before = dict(held)
                    for name, n in segments:
                        held[name] += inputs * n / total
                    calls.append({"session": session, "run": run, "turn": request.get("turn"),
                                  "before": before, "delta": inputs,
                                  "resident": payload.get("resident", 0),
                                  "capacity": payload.get("capacity", 0)})
                    held["own"] += outputs
                    rebuilt = sum(held.values())
                    worst = max(worst, abs(rebuilt - payload.get("resident", 0)))
                    request = output = None
    return calls, worst


def context_shares(calls, by):
    decayed = set()
    for events in by.values():
        decayed |= decayed_turns(events)
    first = {}
    for call in calls:
        first.setdefault((call["session"], call["run"], call["turn"]), call)
    rows = []
    for key, call in first.items():
        b = call["before"]
        total = sum(b.values()) or 1
        rows.append({"fill": sum(b.values()) / call["capacity"] if call["capacity"] else 0,
                     "own": b.get("own", 0) / total, "tool": b.get("tool", 0) / total,
                     "user": b.get("user", 0) / total, "prefix": b.get("prefix", 0) / total,
                     "decayed": key in decayed})
    final = {}
    for call in calls:
        final[(call["session"], call["run"])] = call
    composition = collections.Counter()
    for call in final.values():
        for k, v in call["before"].items():
            composition[k] += v
    whole = sum(composition.values()) or 1

    def median_of(rows, name):
        values = [r[name] for r in rows]
        return round(statistics.median(values), 4) if values else None

    buckets = []
    for low in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8):
        high = {0.6: 0.8, 0.8: 1.01}.get(low, round(low + 0.1, 1))
        inside = [r for r in rows if low <= r["fill"] < high]
        buckets.append({"fill": f"{low:.1f}-{min(high, 1.0):.1f}", "turns": len(inside),
                        "decayed": sum(r["decayed"] for r in inside),
                        "own_median": median_of(inside, "own"),
                        "tool_median": median_of(inside, "tool")})
    return {
        "turns": len(rows),
        "at_run_end_by_origin_share": {k: round(v / whole, 4) for k, v in composition.items()},
        "clean_turns": {k: median_of([r for r in rows if not r["decayed"]], k)
                        for k in ("fill", "own", "tool", "user", "prefix")},
        "decayed_turns": {k: median_of([r for r in rows if r["decayed"]], k)
                          for k in ("fill", "own", "tool", "user", "prefix")},
        "by_fill": buckets,
    }


def onset(by, calls):
    """Where decay set in: each decayed session's first decayed turn, its index
    in the run that holds it and the context at its opening."""
    first = {}
    for call in calls:
        first.setdefault((call["session"], call["run"], call["turn"]), call)
    out = []
    for session, events in by.items():
        decayed = decayed_turns(events)
        if not decayed:
            continue
        order = [turn_key(e) for e in events if e["kind"] == "turn.started"]
        hit = next((k for k in order if k in decayed), None)
        if hit is None or hit not in first:
            continue
        # The index counts the turns of the run that holds the hit, so a hit in
        # a session's second run is its place in that run, not in the session.
        order = [k for k in order if k[1] == hit[1]]
        b = first[hit]["before"]
        total = sum(b.values()) or 1
        out.append({"session": session, "turn_index": order.index(hit) + 1,
                    "fill": round(total / first[hit]["capacity"], 4),
                    "own": round(b.get("own", 0) / total, 4),
                    "tool": round(b.get("tool", 0) / total, 4)})
    return {"sessions": len(out),
            "turn_index": spread([o["turn_index"] for o in out]),
            "fill_median": round(statistics.median(o["fill"] for o in out), 4) if out else None,
            "own_median": round(statistics.median(o["own"] for o in out), 4) if out else None,
            "tool_median": round(statistics.median(o["tool"] for o in out), 4) if out else None}


def assistant_sizes(by):
    per_turn = collections.defaultdict(int)
    for events in by.values():
        for event in events:
            if event["kind"] == "message.assistant":
                per_turn[turn_key(event)] += size(event["payload"].get("content", []))
    return spread(list(per_turn.values()))


# 3: the asks.

def asks(by, store):
    out = []
    for session, events in sorted(by.items()):
        runs = list(collections.OrderedDict((e["run"], None) for e in events))
        recalls = [{"run": e["run"], "ask": e["payload"].get("ask"),
                    "returned": len(e["payload"].get("returned") or []),
                    "returned_bytes": size(e["payload"].get("returned") or [])}
                   for e in events if e["kind"] == "recall"]
        openings, references = [], []
        elections = {e["run"]: {k["kind"]: k["paths"]
                                for k in e["payload"].get("tee", {}).get("keys", [])}
                     for e in events if e["kind"] == "load"}
        for index, run in enumerate(runs):
            opening = next((e for e in events if e["run"] == run and e["kind"] == "message.user"), None)
            line = (texts(opening)[0].split("\n", 1)[0] if opening and texts(opening) else None)
            earlier_rows = store.execute(
                "SELECT count(*), coalesce(sum(length(CAST(coalesce(p.text,'') AS BLOB)) + "
                "length(CAST(coalesce(p.content,'') AS BLOB)) + "
                "length(CAST(coalesce(p.arguments,'') AS BLOB))), 0) "
                "FROM part p JOIN event e ON e.id = p.event_id "
                "WHERE e.session = ? AND e.run IN (%s)" % ",".join("?" * index),
                [session] + runs[:index]).fetchone() if index else (0, 0)
            messages = store.execute(
                "SELECT count(*) FROM message m JOIN event e ON e.id = m.event_id "
                "WHERE e.session = ? AND e.run IN (%s)" % ",".join("?" * index),
                [session] + runs[:index]).fetchone()[0] if index else 0
            # The recall a later run's opening could have asked, as the store
            # serialises it: every message kind of the earlier runs, each with
            # the pairs its own run's election carried across.
            earlier = [(e, crossed_pairs(e, elections.get(e["run"], {}).get(e["kind"], [])))
                       for e in events if e["run"] in runs[:index] and e["kind"] in RECALLED]
            store_events = store.execute(
                "SELECT count(*) FROM event e WHERE e.session = ? AND e.run IN (%s) "
                "AND e.kind IN (%s)" % (",".join("?" * index), ",".join("?" * len(RECALLED))),
                [session] + runs[:index] + list(RECALLED)).fetchone()[0] if index else 0
            openings.append({"run_index": index + 1, "continuity_line": line,
                             "recall_would_return_messages": messages,
                             "recall_would_return_parts": earlier_rows[0],
                             "recall_would_return_bytes": earlier_rows[1],
                             "recall_events_in_trace": len(earlier),
                             "recall_events_in_store": store_events,
                             "recall_serialised_bytes":
                                 len(recall_frame(earlier).encode()) if index else 0})
            if index:
                for e in events:
                    if e["run"] == run and e["kind"] == "message.assistant":
                        for t in texts(e):
                            for m in EARLIER.finditer(t):
                                start = max(0, m.start() - 70)
                                references.append(" ".join(t[start:m.end() + 70].split()))
        out.append({"session": session, "runs": len(runs), "recalls": recalls,
                    "openings": openings, "later_run_references": len(references),
                    "reference_samples": references[:4]})
    lines = collections.Counter(o["continuity_line"] for s in out for o in s["openings"])
    return {"sessions": out, "continuity_lines": dict(lines.most_common(8)),
            "later_openings": sum(1 for s in out for o in s["openings"] if o["run_index"] > 1),
            "later_run_references": sum(s["later_run_references"] for s in out)}


def headline(document):
    """The shares the result note states, computed here so none is by hand."""
    kinds = document["crossing"]["kinds"]
    elected = sum(k["elected_bytes"] for k in kinds.values())
    payload = sum(k["payload_bytes"] for k in kinds.values())
    readings = kinds.get("model.measurement", {}).get("elected_bytes", 0)
    typed = sum(document["crossing"]["store_typed"]["part_bytes_by_block"].values())
    verbatim = sum(v["bytes"] for v in document["crossing"]["store_verbatim"])
    tools = document["tool_results"]
    measured = document["crossing"]["store_typed"]
    series = sum(measured["series_events_by_member"].values())
    return {
        "payload_bytes_all_kinds": payload,
        "elected_bytes": elected,
        "elected_share_of_payload": round(elected / payload, 4) if payload else None,
        "readings_share_of_elected": round(readings / elected, 4) if elected else None,
        "typed_part_bytes": typed,
        "verbatim_field_bytes": verbatim,
        "tool_result_distilled_share": round(tools["distilled_bytes"]["total"]
                                             / tools["bytes"]["total"], 4)
        if tools["bytes"].get("total") else None,
        "perplexity_typed_share": round(measured["measurement_perplexity_typed"]
                                        / kinds["model.measurement"]["events"], 4)
        if kinds.get("model.measurement") else None,
        "series_typed_of_series_elected": [series, 2 * kinds["model.measurement"]["events"]]
        if kinds.get("model.measurement") else None,
        "tool_result_distilled_error_and_unparsed_bytes": sum(
            tools["classes"].get(k, {}).get("distilled_bytes", 0) for k in ("error", "unparsed")),
        "decay_below_and_above_fill_0.3": [
            [sum(b["turns"] for b in document["context"]["by_fill"] if b["fill"] < "0.3"),
             sum(b["decayed"] for b in document["context"]["by_fill"] if b["fill"] < "0.3")],
            [sum(b["turns"] for b in document["context"]["by_fill"] if b["fill"] >= "0.3"),
             sum(b["decayed"] for b in document["context"]["by_fill"] if b["fill"] >= "0.3")]],
        "decay_rate_by_fill": [[b["fill"], b["turns"], b["decayed"],
                                round(b["decayed"] / b["turns"], 3) if b["turns"] else None]
                               for b in document["context"]["by_fill"]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--sessions", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--asks", action="store_true")
    parser.add_argument("--exact", action="store_true",
                        help="--sessions names sessions whole rather than by prefix")
    args = parser.parse_args()
    prefixes = args.sessions.split(",")
    by = sessions_of(args.trace, prefixes, args.exact)
    store = sqlite3.connect(f"file:{args.state}?mode=ro", uri=True)
    if args.asks:
        document = {"sessions": sorted(by), "asks": asks(by, store)}
    else:
        calls, worst = contexts(by)
        document = {
            "sessions": len(by),
            "crossing": crossing(by, store, prefixes, args.exact),
            "tool_results": tool_results(by),
            "context": context_shares(calls, by),
            "context_rebuild_max_token_error": round(worst, 1),
            "decay_onset": onset(by, calls),
            "assistant_bytes_per_turn": assistant_sizes(by),
            "asks": asks(by, store),
        }
        document["headline"] = headline(document)
    text = json.dumps(document, indent=1)
    open(args.out, "w").write(text + "\n")
    for key, value in document.items():
        print(f"{key}: {len(json.dumps(value))} bytes")


if __name__ == "__main__":
    main()
