"""The position table of one replayed completion: each position kind, its
size, the weaver-trace kind it would land in when our agent plays the task,
and a bounded quote of the real payload.

    python3 positions_table.py <replay.json> [<quote-chars>]

Stdlib only; it reads what replay.py wrote and prints a markdown table, then
every executed action as a request and the environment's answer, each quote
bounded to <quote-chars> (default 160). It writes nothing.

The prompt is cut where its own headings fall: the rules to "You can perform
the following actions:", the action list to the game dump (the first line
opening a `{`), the dump to "Character Stats:", the stats to "Your task", and
the task to the end. The completion is the text before the program and the
program. When our agent plays, the prompt's standing part is the identity
prefix (`message.system`) and the task is the turn's input (`message.user`),
the model's text and program are its answer (`message.assistant`), and, where
the agent plays action by action with each action its own shell call, each
action is a tool call through the gate's shell (`tool.call.started` and
`tool.call.completed`) whose answer is the next input (`message.tool_result`).
The harness brackets one shell tool call per invocation, so a program run as one
shell call is one bracket and one tool result carrying the whole execution's
output.
"""
import json
import re
import sys

# The tag and whitespace of extract_final_code's fence pattern in utils.py,
# r"```(?:[\w.+-]+)?\s*\n?([\s\S]*?)```", read from the opening fence to the code.
OPENING = re.compile(r"(?:[\w.+-]+)?\s*")


def cut(prompt):
    marks = [("rules", 0),
             ("actions", prompt.find("You can perform the following actions:")),
             ("dump", prompt.find("\n{")),
             ("stats", prompt.find("Character Stats:")),
             ("task", prompt.find("Your task"))]
    marks = [(k, i) for k, i in marks if i >= 0]
    return {k: prompt[i:(marks[n + 1][1] if n + 1 < len(marks) else len(prompt))]
            for n, (k, i) in enumerate(marks)}


def program_start(answer, code):
    """Where the program the pipeline ran begins in the answer: the last place
    the extracted program occurs, or its first line where the fenced text
    differs by whitespace, and the "final answer" phrase only where neither is
    found. The text before it is the completion's text before the program, and
    an opening fence whose tag and whitespace are all that stand between it and
    the program is the program's, as the pipeline reads it."""
    code = (code or "").strip()
    at = answer.rfind(code) if code else -1
    if at < 0 and code:
        at = answer.rfind(code.splitlines()[0].strip())
    if at < 0:
        at = answer.lower().rfind("final answer")
    if at < 0:
        return len(answer)
    fence = answer.rfind("```", 0, at)
    # A fence opening the program belongs to the program, not to the text,
    # where what lies between them is the pipeline's own opening-fence
    # pattern: an optional tag of [\w.+-]+ and then whitespace only.
    return fence if fence >= 0 and OPENING.fullmatch(answer[fence + 3:at]) else at


def quote(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + " ..."


def main():
    replay = json.load(open(sys.argv[1]))
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 160
    parts = cut(replay["prompt"])
    answer = replay["answer"]
    before = answer[:program_start(answer, replay["code"])]
    rows = [
        ("prompt: rules", "message.system", parts.get("rules", "")),
        ("prompt: action list", "message.system", parts.get("actions", "")),
        ("prompt: game dump", "message.system", parts.get("dump", "")),
        ("prompt: character stats", "message.system", parts.get("stats", "")),
        ("prompt: task", "message.user", parts.get("task", "")),
        ("completion: reasoning (provider's own)", "message.assistant", replay.get("reasoning", "")),
        ("completion: text before the program", "message.assistant", before),
        ("completion: program", "message.assistant", replay["code"]),
    ]
    print(f"{replay['model']} level {replay['difficulty']} {replay['task']}: "
          f"{replay['result']} (score {replay['score']:.1f}), recorded "
          f"{replay['recorded']['result']} (score {replay['recorded']['score']:.1f})\n")
    print("| Position | Lands in | Chars | Quote |")
    print("|---|---|---|---|")
    for name, kind, text in rows:
        print(f"| {name} | `{kind}` | {len(text)} | {quote(text, n) or '(none)'} |")
    calls = replay["calls"]
    print(f"| executed action: request, x{len(calls)} | `tool.call.started` | - | "
          f"{quote(json.dumps({'func': calls[0]['func'], 'args': calls[0]['args']}), n) if calls else '(none)'} |")
    print(f"| executed action: environment's answer, x{len(calls)} | `tool.call.completed`, "
          f"`message.tool_result` | - | "
          f"{quote(json.dumps({'status': calls[0].get('status'), 'body': calls[0].get('body')}), n) if calls else '(none)'} |")
    print(f"| character log, x{len(replay['logs'])} | (the environment's own record) | - | "
          f"{quote(replay['logs'][0].get('log'), n) if replay['logs'] else '(none)'} |")
    print("\nEvery executed action, in order:\n")
    for c in calls:
        print(f"- {c['seq']} `{c['func']}{tuple(c['args'][1:])}` -> {c.get('status')} "
              f"{quote(json.dumps(c.get('body')), n)}")


if __name__ == "__main__":
    main()
