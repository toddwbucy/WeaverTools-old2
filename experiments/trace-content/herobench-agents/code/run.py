"""One run of one agent through HeroBench tasks, action by action.

    python run.py --agent NAME --port PORT --herobench DIR --out DIR
                  [--level 1] [--tasks 1-3] [--turn-cap 8] [--label run1]

Run with the benchmark's own interpreter and its shim on the path, so the
benchmark's client reaches this arm's server:

    HEROBENCH_PORT=PORT PYTHONPATH=<herobench>/weaver/bench/shim:<herobench> \\
        <herobench>/.venv/bin/python run.py ...

Each task is one run, one load and one unload of the agent through its admin,
under the declaration's session, because the harness takes one score per run.
Between them the task is one work item on the agent's gate: the task's character is created
first, with the benchmark's own `create_character` and the stats the task's
prompt states, under the agent's name. The work item's first line is a header
the loop file reads, and the rest is the task's game data and the task, without
the benchmark's instruction to write a program. The loop plays the task over as
many turns as it needs, up to the cap, and answers. The run script then reads
the character's log from the server and grades it with the benchmark's own
functions: `extract_result`, `compute_episode_reward` and
`compute_ideal_episode_reward`, the score being reward over ideal times 100 as the
pipeline computes it. Nothing in the benchmark is modified.

A task with no answer within --task-timeout is not graded and ends the driver:
the agent is unloaded before anything else, because the relay does not cancel a
frame it admitted.

Writes, under --out, which must not already hold a `run.json`: one
`<task>.json` per task with the gate's answer, the character's log since
creation, the result, the reward and the score, and `run.json` with each task's
load, unload and outcome and what ended the run, written on every exit.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

ADMIN = "/usr/local/libexec/weaver/weaver-admin"
ADMIN_CONFIG = "/etc/weaver/config"
LOG_CUTOFF = 4000  # scoring_pipeline's CUTOFF_ACTIONS


def admin(verb, agent):
    """The admin's last stdout line as JSON, with the exit status beside it."""
    done = subprocess.run(
        ["sudo", "-n", f"WEAVER_ADMIN_CONFIG={ADMIN_CONFIG}", ADMIN, verb, agent],
        capture_output=True, text=True, timeout=900,
    )
    line = (done.stdout.strip().splitlines() or [""])[-1]
    try:
        answer = json.loads(line)
    except json.JSONDecodeError:
        answer = {"kind": "unparsed", "stdout": done.stdout, "stderr": done.stderr}
    if not isinstance(answer, dict):
        answer = {"kind": "unparsed", "stdout": done.stdout}
    answer["exit"] = done.returncode
    return answer


def wait_socket(path, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        try:
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.connect(path)
            probe.close()
            return True
        except OSError:
            time.sleep(0.5)
    return False


def gate_turn(path, text, timeout):
    """One work item through the gate's world socket, one JSON answer back."""
    link = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    link.settimeout(timeout)
    link.connect(path)
    link.sendall((json.dumps({"text": text}) + "\n").encode())
    line = link.makefile().readline()
    link.close()
    return json.loads(line)


def span(text):
    first, _, last = text.partition("-")
    return list(range(int(first), int(last or first) + 1))


def presented(prompt):
    """The prompt's game data and its task, without the rules the identity holds
    and without the instruction to answer with a program."""
    start = prompt.find("\n{'")
    ask = prompt.find("Your task")
    data = prompt[start + 1:ask].rstrip()
    keep = [
        line for line in prompt[ask:].splitlines()
        if line.strip() and not line.startswith(("Think and write", "End your answer"))
    ]
    keep.append("Play it action by action with ./hb, one call per action.")
    return data + "\n\n" + "\n".join(keep)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--herobench", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--level", default="1")
    parser.add_argument("--tasks", default="1-3")
    parser.add_argument("--turn-cap", type=int, default=8)
    parser.add_argument("--label", default="run1")
    parser.add_argument("--task-timeout", type=int, default=7200)
    args = parser.parse_args()

    sys.path.insert(0, args.herobench)
    from utils import (compute_episode_reward, compute_ideal_episode_reward,
                       create_character, cut_events_before_creation,
                       extract_result, get_task_type)
    from Virtual_Environment.api_calls import get_character_logs

    prompts = json.load(open(os.path.join(args.herobench, "datasets", "dataset_prompts.json")))
    tasks = json.load(open(os.path.join(args.herobench, "datasets", "dataset_tasks.json")))
    out = args.out
    os.makedirs(out, exist_ok=True)
    gate = f"/run/weaver-{args.agent}/gate.sock"
    record = {"agent": args.agent, "label": args.label, "port": args.port,
              "level": args.level, "turn_cap": args.turn_cap, "tasks": []}

    # **Each task is its own run**: load, the task's turns, its score, unload,
    # all under the declaration's one session. The harness takes one score per
    # run, so a run of several tasks records only the first task's verdict,
    # which is how the pairs deposited on 2026-09-29 were driven. One task per
    # run makes every task's outcome a position of the record, and the shape ask
    # then counts earlier tasks as earlier runs.
    # **A run's record stands for that run alone.** A directory already holding
    # a run.json is refused before anything is loaded, so a rerun never leaves an
    # earlier record standing beside, or under, its own.
    record_path = os.path.join(out, "run.json")
    if os.path.exists(record_path):
        sys.exit(f"run.py: {record_path} already holds a run's record, name a fresh --out")
    record["ended"] = "started"
    # **run.json is written on every exit**, carrying what ended the run: a
    # refused load with the admin's answer beside it in the task's entry, a load
    # that stood no reachable gate, a timeout, an error, or completion.
    try:
        for number in span(args.tasks):
            prompt = prompts[args.level][number - 1]
            task = tasks[args.level][number - 1]
            kind = get_task_type(prompt)
            subject = task.get("item") or task.get("monster_name")
            name = f"{number}_{subject}_{kind}"
            target = (task.get("monster_name", "") if kind == "kill"
                      else (task.get("crafting_tree") or {}).get("code", ""))
            entry = {"name": name, "load": admin("load", args.agent),
                     "load_wall": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            record["tasks"].append(entry)
            if entry["load"].get("exit") != 0:
                entry["refused"] = "the load was refused"
                break
            timed_out = False
            try:
                if not wait_socket(gate):
                    entry["refused"] = "the load stood no gate this process can reach"
                    break
                create_character(args.agent, prompt)
                header = {"url": f"http://127.0.0.1:{args.port}", "character": args.agent,
                          "kind": kind, "target": target, "name": name,
                          "turn_cap": args.turn_cap}
                text = "HEROBENCH " + json.dumps(header) + "\n" + presented(prompt)
                began = time.time()
                try:
                    answer = gate_turn(gate, text, args.task_timeout)
                except socket.timeout:
                    # **A timed-out task ends the driver.** The relay does not cancel
                    # a frame it admitted, so the task's turns may still be running:
                    # it is not graded, and no further task starts, until the unload
                    # below has stopped the agent.
                    timed_out = True
                    entry["fault"] = f"no answer within {args.task_timeout} s"
                    break
                except Exception as error:
                    answer = {"fault": repr(error)}
                took = time.time() - began
                logs = cut_events_before_creation(
                    get_character_logs(args.agent, LOG_CUTOFF),
                    creation_log=f"Successfully created custom character - {args.agent}.")
                result = extract_result(logs, prompt, task)
                reward, _ = compute_episode_reward(task, logs)
                ideal, _ = compute_ideal_episode_reward(task)
                score = reward * 100.0 / ideal if ideal else 0.0
                outcome = {"name": name, "kind": kind, "target": target, "seconds": took,
                           "answer": answer, "result": result, "reward": reward,
                           "ideal_reward": ideal, "score": score,
                           "actions": sum(1 for e in logs
                                          if not e.get("action_type", "").startswith("create")),
                           "logs": logs}
                json.dump(outcome, open(os.path.join(out, f"{name}.json"), "w"), indent=1)
                # What ended the task's crossing, as the gate answered it: an answer
                # that is not "answered" carries its kind and reason, so a run a
                # refused turn ended reads as one here as well as in the record.
                if isinstance(answer, dict) and answer.get("kind") != "answered":
                    reason = answer.get("reason", answer.get("fault", ""))
                    entry["ended_by"] = f"{answer.get('kind')}: {reason}"
                entry.update({k: outcome[k] for k in
                              ("result", "reward", "ideal_reward", "score", "actions", "seconds")})
                print(f"{args.agent} {args.label} {name}: {result} score {score:.1f} "
                      f"actions {outcome['actions']} in {took:.0f}s", flush=True)
            finally:
                entry["unload"] = admin("unload", args.agent)
                json.dump(record, open(record_path, "w"), indent=1)
            if timed_out:
                break
    except BaseException as error:
        record["ended"] = f"error: {error!r}"
        raise
    else:
        last = record["tasks"][-1] if record["tasks"] else {}
        if "fault" in last:
            record["ended"] = "timeout: " + last["fault"]
        elif "refused" in last:
            record["ended"] = "refused: " + last["refused"]
        else:
            record["ended"] = "completed"
    finally:
        json.dump(record, open(record_path, "w"), indent=1)
    return 0 if record["ended"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
