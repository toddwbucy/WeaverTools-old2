"""Segment every HeroBench completion into positions, give each position the
recipe that labels it, and count the positions each recipe reaches.

    python3 segment.py <herobench> <out-dir>

Stdlib only. It reads the results, the scoring, the datasets and the
environment's data tables under <herobench>, writes `positions.jsonl` (one
line per position) and `split.json` (the counts) into <out-dir>, and prints the
summary the result note states. It modifies nothing under <herobench>.

A completion is one model's single-shot answer to one task. Its positions:

  prose      each non-empty line of the text the model wrote outside its final
             code block, the provider's separate reasoning included
  draft      each non-empty line inside a code block that is not the final one
  step       each statement of the final program, the one the pipeline ran
  action     each action the environment accepted, from the recorded log
  refusal    each call the environment refused, from the scored func_errors
  outcome    the task's scored result, one per completion

The buckets, each by the recipe that labels the position:

  computable  the label joins to game state by position, with no model:
              an action or refusal (accepted or refused, the inventory delta
              the log line states), the outcome (win or lose, the score), and
              a program step that calls the environment with literal
              arguments: an item code that exists in the ontology or not, a
              move to a tile that exists and what stands on it, a gather or
              fight joined to the tile the preceding literal move reached
  judgmental  the label needs a model: a prose line (does it recite the dump,
              state a plan, contradict what was recited)
  unreached   no recipe here reaches it: a program step whose arguments are
              computed, a step that calls nothing in the environment
              (assignments, control flow, prints), and a draft line

Completions whose text is not on disk (no full log for the model, or no entry
for the task) have program, action, refusal and outcome positions and no prose
or draft positions. They are counted, and the shares are given with and
without them.
"""
import ast
import collections
import glob
import json
import os
import re
import sys

API = {"move", "fight", "equip", "unequip", "gather", "craft", "buy"}
FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
THINK = re.compile(r"<think>(.*?)</think>", re.S)
# What the model wrote, as against what the environment answered: the second
# weighting, since executed actions run to thousands a task where a program
# loops, and a share weighted by them is a share of the environment's log.
AUTHORED = ("prose", "draft", "step")
BUCKET = {"prose": "judgmental", "draft": "unreached", "action": "computable",
          "refusal": "computable", "outcome": "computable"}


UNREADABLE = []
HEROBENCH = ""


def load(path, default=None):
    """A JSON file, or `default` where it does not parse, the path recorded:
    one result file in the benchmark's own tree is malformed, and a count that
    stopped there would count nothing."""
    try:
        with open(path) as fh:
            return json.load(fh)
    except ValueError as exc:
        UNREADABLE.append(f"{os.path.relpath(path, HEROBENCH)}: {exc}")
        return default


def table(data_dir, name):
    data = load(os.path.join(data_dir, name))
    return data if isinstance(data, list) else data.get("data", data)


def ontology(herobench):
    data = os.path.join(herobench, "Virtual_Environment", "FastApi_SQLite_Ver", "app", "Data")
    items = {i["code"] for i in table(data, "items.json")}
    items |= {i["code"] for i in table(data, "noise_items.json")}
    tiles = {(m["x"], m["y"]): (m.get("content") or {}) for m in table(data, "maps.json")}
    return items, tiles


def text_of(entry):
    """The provider's separate reasoning and its answer, as text."""
    if entry is None:
        return None, None
    if isinstance(entry, str):
        thought = "\n".join(THINK.findall(entry))
        return thought, THINK.sub("", entry)
    if "output" in entry:
        reasoning, answer = [], []
        for item in entry.get("output") or []:
            if item.get("type") == "reasoning":
                reasoning += [s.get("text", "") for s in item.get("summary") or []]
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    answer.append(part.get("text", ""))
        return "\n".join(reasoning), "\n".join(answer)
    if "choices" in entry:
        message = (entry.get("choices") or [{}])[0].get("message") or {}
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        return reasoning, message.get("content") or ""
    if "content" in entry:
        return "", entry.get("content") or ""
    return None, None


def prose_and_drafts(reasoning, answer, program):
    """Prose lines and draft-code lines. The final code block is the program,
    counted as steps, so its lines are neither. Where the answer carries its
    program without a fence, as `utils.extract_final_code` also accepts after a
    `<code>` tag or a "final answer" marker, a line of the answer that is a
    line of the program the pipeline ran is the program's and not prose."""
    program_lines = {l.strip() for l in (program or "").splitlines() if l.strip()}
    blocks = list(FENCE.finditer(answer))
    final = blocks[-1] if blocks else None
    prose, drafts = [], []
    outside = answer
    for block in reversed(blocks):
        if block is not final:
            drafts += [l for l in block.group(1).splitlines() if l.strip()]
        outside = outside[:block.start()] + "\n" + outside[block.end():]
    prose += [l for l in (reasoning or "").splitlines() if l.strip()]
    prose += [l for l in outside.splitlines() if l.strip() and not l.strip().startswith("```")
              and l.strip() not in program_lines]
    return prose, drafts


def literal(node):
    try:
        return True, ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return False, None


def steps(code, items, tiles):
    """Each statement of the program, with its bucket and, for a literal call
    to the environment, the label its recipe gives."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return [{"kind": "step", "bucket": "unreached", "recipe": "none", "label": "syntax_error"}]
    out, at = [], None
    # In source order, so a gather or a fight joins the move written before it.
    statements = sorted((n for n in ast.walk(tree) if isinstance(n, ast.stmt)),
                        key=lambda n: (n.lineno, n.col_offset))
    for node in statements:
        call = node.value if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else None
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
        name = call.func.id if call is not None and isinstance(call.func, ast.Name) else None
        if name not in API:
            out.append({"kind": "step", "bucket": "unreached", "recipe": "none",
                        "label": type(node).__name__})
            continue
        values = [literal(a) for a in call.args] + [literal(k.value) for k in call.keywords]
        if not all(ok for ok, _ in values):
            out.append({"kind": "step", "bucket": "unreached", "recipe": "computed_args",
                        "label": name})
            if name == "move":
                at = None
            continue
        args = [v for _, v in values]
        if name == "move" and len(args) >= 3:
            at = (args[1], args[2])
            content = tiles.get(at)
            label = ("no_such_tile" if content is None
                     else f"tile:{content.get('type', 'empty')}:{content.get('code', '')}")
            recipe = "tile_exists_and_content"
        elif name in ("fight", "gather"):
            content = tiles.get(at) if at is not None else None
            want = "monster" if name == "fight" else "resource"
            label = ("tile_unknown" if at is None or content is None
                     else "matches" if content.get("type") == want else f"no_{want}_here")
            recipe = "joins_preceding_move_tile"
            if at is None:
                out.append({"kind": "step", "bucket": "unreached", "recipe": "no_literal_tile",
                            "label": name})
                continue
        else:
            codes = [a for a in args[1:] if isinstance(a, str)
                     and a not in ("weapon", "shield", "helmet", "body_armor", "leg_armor",
                                   "boots", "ring1", "ring2", "amulet", "artifact1",
                                   "artifact2", "artifact3", "consumable1", "consumable2")]
            label = ("no_code" if not codes
                     else "code_exists" if all(c in items for c in codes) else "code_unknown")
            recipe = "item_code_in_ontology"
        out.append({"kind": "step", "bucket": "computable", "recipe": recipe,
                    "label": f"{name}:{label}"})
    return out


def results_sets(herobench, split):
    root = os.path.join(herobench, "results", split)
    names = sorted({os.path.basename(f)[:-5] for f in glob.glob(f"{root}/*.json")
                    if not f.endswith(("_full_log.json", "_code_logs.json"))})
    for name in names:
        exact = f"{root}/{name}_full_log.json"
        full = exact if os.path.exists(exact) else None
        if full is None:
            # A full log named with a qualifier, e.g. `<name>_4-10_full_log.json`,
            # never one that is another result set's own.
            for path in sorted(glob.glob(f"{root}/{name}_*full_log.json")):
                stem = os.path.basename(path)[:-len("_full_log.json")]
                if stem not in names:
                    full = path
        yield name, root, full


def main():
    global HEROBENCH
    herobench, out_dir = sys.argv[1], sys.argv[2]
    HEROBENCH = herobench
    os.makedirs(out_dir, exist_ok=True)
    items, tiles = ontology(herobench)
    counts = collections.defaultdict(collections.Counter)
    labels = collections.Counter()
    completions = collections.Counter()
    with open(os.path.join(out_dir, "positions.jsonl"), "w") as positions, \
            open(os.path.join(out_dir, "completions.jsonl"), "w") as index:
        for split, scoring in (("results_base", "results_base_scoring"),
                               ("results_hard", "results_hard_scoring")):
            for name, root, full in results_sets(herobench, split):
                results = load(f"{root}/{name}.json")
                code_logs = load(f"{root}/{name}_code_logs.json", {})
                full_logs = load(full, {}) if full else {}
                score_path = os.path.join(herobench, "results", scoring, f"{name}_scores.json")
                scores = load(score_path, {}) if os.path.exists(score_path) else {}
                for diff, tasks in results.items():
                    for task, scored in tasks.items():
                        for sample, result in enumerate(scored["results"]):
                            cl = code_logs.get(diff, {}).get(task, {})
                            code = (cl.get("code") or [None])[sample] if sample < len(cl.get("code") or []) else None
                            logs = (cl.get("logs") or [[]])[sample] if sample < len(cl.get("logs") or []) else []
                            fl = full_logs.get(diff, {}).get(task)
                            entry = fl[sample] if isinstance(fl, list) and sample < len(fl) else None
                            reasoning, answer = text_of(entry)
                            on_disk = answer is not None
                            sc = scores.get(diff, {}).get(task)
                            sc = sc[sample] if isinstance(sc, list) and sample < len(sc) else {}
                            level = "hard" if split == "results_hard" else f"base-{diff}"
                            key = (name, split, diff, task, sample)
                            rows = []
                            if on_disk:
                                prose, drafts = prose_and_drafts(reasoning, answer, code)
                                rows += [{"kind": "prose"} for _ in prose]
                                rows += [{"kind": "draft"} for _ in drafts]
                            rows += steps(code, items, tiles)
                            for event in logs:
                                if event.get("action_type") == "create_custom_character":
                                    continue
                                rows.append({"kind": "action", "recipe": "log_line",
                                             "label": event.get("action_type")})
                            for err in sc.get("func_errors") or []:
                                rows.append({"kind": "refusal", "recipe": "func_error",
                                             "label": f"{err.get('func')}:{err.get('error_code')}"})
                            rows.append({"kind": "outcome", "recipe": "scored_result", "label": result})
                            completions[(split, on_disk)] += 1
                            cid = sum(completions.values()) - 1
                            index.write(json.dumps({"c": cid, "model": name, "split": split,
                                                    "level": level, "task": task, "sample": sample,
                                                    "text_on_disk": on_disk, "result": result,
                                                    "positions": len(rows)}) + "\n")
                            for row in rows:
                                if "bucket" not in row:
                                    row["bucket"] = BUCKET[row["kind"]]
                                if "recipe" not in row:
                                    row["recipe"] = "model_labels_span" if row["kind"] == "prose" else "none"
                                positions.write(json.dumps({"c": cid, "k": row["kind"],
                                                            "b": row["bucket"], "r": row["recipe"],
                                                            **({"l": row["label"]} if "label" in row else {})}) + "\n")
                                for group in ("all", f"model:{split[8:]}/{name}", f"level:{level}",
                                              f"split:{split}", f"text:{on_disk}"):
                                    counts[group][row["bucket"]] += 1
                                    counts[group][f"kind:{row['kind']}"] += 1
                                    if on_disk:
                                        counts[f"{group}|text"][row["bucket"]] += 1
                                        if row["kind"] in AUTHORED:
                                            counts[f"{group}|authored"][row["bucket"]] += 1
                                if row["bucket"] == "computable" and row["kind"] == "step":
                                    labels[row["label"].split(":", 1)[1].split(":")[0]] += 1
    split_out = {"counts": {g: dict(c) for g, c in counts.items()},
                 "completions": {f"{s}|text_on_disk={t}": n for (s, t), n in completions.items()},
                 "step_labels": dict(labels), "unreadable": UNREADABLE}
    with open(os.path.join(out_dir, "split.json"), "w") as fh:
        json.dump(split_out, fh, indent=1, sort_keys=True)

    def shares(c):
        total = sum(c[b] for b in ("computable", "judgmental", "unreached"))
        return total, {b: round(100.0 * c[b] / total, 1) if total else 0.0
                       for b in ("computable", "judgmental", "unreached")}

    print("completions", dict(split_out["completions"]))
    for u in UNREADABLE:
        print("unreadable", u[:160])
    for group in ["all", "all|text", "split:results_base|text", "split:results_hard|text",
                  "text:False", "all|authored", "split:results_base|authored",
                  "split:results_hard|authored"]:
        total, s = shares(counts[group])
        print(f"{group:28s} positions {total:7d}  computable {s['computable']:5.1f}%  "
              f"judgmental {s['judgmental']:5.1f}%  unreached {s['unreached']:5.1f}%")
    print("by kind (all):", {k[5:]: v for k, v in counts["all"].items() if k.startswith("kind:")})
    print("computable step labels:", dict(labels))
    for prefix in ("level:", "model:"):
        for group in sorted(g for g in counts if g.startswith(prefix) and "|" not in g):
            total, s = shares(counts[group])
            t_total, ts = shares(counts[f"{group}|text"])
            a_total, a = shares(counts[f"{group}|authored"])
            print(f"{group:44s} {total:6d}  C {s['computable']:5.1f}  J {s['judgmental']:5.1f}  "
                  f"U {s['unreached']:5.1f}   text-only {t_total:6d}  C {ts['computable']:5.1f}  "
                  f"J {ts['judgmental']:5.1f}  U {ts['unreached']:5.1f}   authored {a_total:6d}  "
                  f"C {a['computable']:5.1f}  J {a['judgmental']:5.1f}  U {a['unreached']:5.1f}")


if __name__ == "__main__":
    main()
