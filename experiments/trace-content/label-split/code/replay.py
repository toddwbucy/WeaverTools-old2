"""Replay one scored HeroBench completion against a running environment
backend, recording the server's answer to every action the program takes.

    python replay.py <herobench> <model> <difficulty> <task> <out.json>

Run with the HeroBench harness's own interpreter (`<herobench>/.venv/bin/python`),
with `<herobench>/weaver/bench/shim` and `<herobench>` on PYTHONPATH and
HEROBENCH_PORT naming the arm, from `<herobench>` as the working directory. It
modifies no HeroBench file.

It follows `scoring_pipeline.run_task` step for step: the character is created
from the task's prompt, the completion's recorded program runs with exactly the
seven API functions `utils._worker` injects (`utils._API_TO_WRAP`) and no
others, under the pipeline's timeout, and the character's log is read back,
cut at creation, and graded with the pipeline's own functions. What it adds is
the record: each injected function is wrapped so its arguments and the
server's `(status, body)` answer are kept in call order. The program runs in
this process rather than a spawned child, so no shim has to reach a
subprocess, and the calls are the same calls against the same server.

The output carries the prompt, the completion's text as the provider returned
it, the program, the recorded calls, the replayed log, the scored outcome, and
the original run's log and outcome from the results files for comparison.
"""
import contextlib
import importlib
import io
import json
import os
import signal
import sys
import traceback

TIMEOUT = 100          # scoring_pipeline.TIMEOUT
CUTOFF_ACTIONS = 4000  # scoring_pipeline.CUTOFF_ACTIONS


def completion_text(entry):
    """The provider's response as text, whatever shape the provider returned:
    OpenAI responses (`output`), chat completions (`choices`), LangChain
    (`content`), or a bare string. Reasoning the provider returned separately
    is kept apart from the answer."""
    if isinstance(entry, str):
        return "", entry
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
    return "", ""


def main():
    herobench, model, diff, task_name, out = sys.argv[1:6]
    os.chdir(herobench)
    sys.path.insert(0, herobench)
    utils = importlib.import_module("utils")
    api = importlib.import_module("Virtual_Environment.api_calls")

    results = f"{herobench}/results/results_base"
    code_logs = json.load(open(f"{results}/{model}_code_logs.json"))[diff][task_name]
    full_log = json.load(open(f"{results}/{model}_full_log.json"))[diff][task_name][0]
    scored = json.load(open(f"{results}/{model}.json"))[diff][task_name]
    index = int(task_name.split("_", 1)[0]) - 1
    prompt = json.load(open(f"{herobench}/datasets/dataset_prompts.json"))[diff][index]
    task = json.load(open(f"{herobench}/datasets/dataset_tasks.json"))[diff][index]
    code = code_logs["code"][0]

    calls = []

    def recorded(name, fn):
        def call(*args, **kwargs):
            entry = {"seq": len(calls), "func": name, "args": list(args), "kwargs": kwargs}
            try:
                status, body = fn(*args, **kwargs)
                entry["status"], entry["body"] = status, body
            except Exception as exc:
                entry["exception"] = repr(exc)
                calls.append(entry)
                raise
            calls.append(entry)
            return status, body
        return call

    utils.create_character("Hero", prompt)
    g = {"__name__": "__main__"}
    for name in utils._API_TO_WRAP:
        if hasattr(api, name):
            g[name] = recorded(name, getattr(api, name))

    def expired(signum, frame):
        raise TimeoutError(f"the program ran past the pipeline's {TIMEOUT} s")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(TIMEOUT)
    stdout, stderr, trace = io.StringIO(), io.StringIO(), None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exec(code, g, {})
        except Exception:
            trace = traceback.format_exc()
    signal.alarm(0)

    logs = utils.cut_events_before_creation(api.get_character_logs("Hero", CUTOFF_ACTIONS))
    result = utils.extract_result(logs, prompt, task)
    reward, _ = utils.compute_episode_reward(task, logs)
    ideal, _ = utils.compute_ideal_episode_reward(task)
    reasoning, answer = completion_text(full_log)
    json.dump({
        "model": model, "difficulty": diff, "task": task_name,
        "prompt": prompt, "reasoning": reasoning, "answer": answer, "code": code,
        "calls": calls, "trace": trace,
        "stdout": stdout.getvalue(), "stderr": stderr.getvalue(),
        "logs": logs, "result": result, "reward": reward, "ideal_reward": ideal,
        "score": reward * 100.0 / ideal if ideal else 0.0,
        "recorded": {"logs": code_logs["logs"][0], "result": scored["results"][0],
                     "score": scored["scores"][0]},
    }, open(out, "w"), indent=1, default=repr)
    print(json.dumps({"task": task_name, "calls": len(calls), "logs": len(logs),
                      "result": result, "score": round(reward * 100.0 / ideal if ideal else 0.0, 1),
                      "recorded_result": scored["results"][0],
                      "recorded_score": scored["scores"][0],
                      "logs_match": [e.get("log") for e in logs] == [e.get("log") for e in code_logs["logs"][0]]}))


if __name__ == "__main__":
    main()
