# The HeroBench loop: one task per crossing, played action by action.
#
# The run script submits one work item per task through the gate. Its first line
# is `HEROBENCH ` and a JSON object naming the environment server, the
# character, the task's kind and target, the task's name and the turn cap. The
# rest is what the model is shown: the task's game data and the task itself.
#
# **A task spans turns, and the tool-round cap is the harness's.** Each
# seat.turn runs the model, and every `./hb` call it makes executes through the
# gate's shell inside that turn, up to the harness's own round bound. When a turn
# ends and the task is not done, the loop opens the next turn with a short user
# message, so a task that needs more actions than one turn allows goes on in the
# next, and the session's shape counts every turn. The loop never raises the
# harness's bound and never authors a tool result.
#
# **The outcome is read from the environment, not from the model.** After each
# turn the loop reads the character's log from the server and applies
# HeroBench's own result rule, `extract_result` in the benchmark's utils.py: a
# kill task is won by a winning fight against the target monster, and a craft
# task by a craft of the target item with no failed craft of it. The events
# counted are those after this task's character was created. The loop stops on
# a win or at the cap, and records the verdict with seat.score. Each
# continuing turn states that verdict to the model, so a claim that the task is
# done meets the game's record. HeroBench's
# reward and score are computed by the run script from the same log, with the
# benchmark's own functions, and do not ride this record.
#
# **The session's past reaches the model as one line.** The first turn of a
# task opens with the count of the session's earlier runs and turns, read
# through seat.session_shape, so a second run of a session starts from a past
# and a first one says it has none. Nothing else in the loop depends on state.
#
# THE SYSTEM PROMPT IS NOT HERE. It is the session's identity prefix, seated
# from the declaration, holding the game's rules, the move rule and the `./hb`
# usage.

import json
import urllib.request

CONTINUE = "Continue the task."

# **A call that never closed did not run, and the next turn says so in words.**
# Both SPUs sample at a compiled temperature with a repetition penalty over the
# last 64 tokens, and a sampled call can close with a second opening tag, which
# neither SPU's parse recovers, so nothing executes and the turn ends. The loop
# names the fault without spelling the tags: a message ending in the tag tokens
# puts them in the penalty's window just before the model writes its next call,
# and on 2026-09-29 that produced a stray token in the tag's place on every
# following call. The tags stand in the identity prefix, well outside the window.
UNCLOSED = (
    "Your last call did not run, because it was not closed with the closing "
    "tag from your instructions. "
)


def _not_done(task):
    """The environment's verdict, stated, so a claim of completion meets the
    game's record rather than the loop's say-so."""
    if task["kind"] == "kill":
        return f"The game's log shows no win against {task['target']} yet, so the task is not done. "
    return f"The game's log shows no {task['target']} crafted yet, so the task is not done. "


def _events(url, character):
    """The character's log since its creation, oldest first."""
    with urllib.request.urlopen(f"{url}/logs/500/{character}", timeout=30) as response:
        answer = json.load(response)
    entries = answer if isinstance(answer, list) else answer.get("logs", answer.get("data", []))
    since = []
    created = f"Successfully created custom character - {character}."
    for entry in entries:
        since.append(entry)
        if entry.get("log") == created:
            break
    since.reverse()
    return since


def _won(url, character, kind, target):
    """HeroBench's result rule over the task's own events."""
    target = target.lower()
    try:
        events = _events(url, character)
    except Exception:
        return False
    if kind == "kill":
        return any(
            entry.get("action_type") == "fight"
            and target in entry.get("log", "").lower()
            and "win" in entry.get("log", "").lower()
            for entry in events
        )
    crafted = False
    for entry in events:
        text = entry.get("log", "").lower()
        if target in text:
            if "failed to craft" in text:
                return False
            if "crafts" in text or "crafted" in text:
                crafted = True
    return crafted


def _past(seat):
    try:
        runs = seat.session_shape() or []
    except Exception:
        return None
    turns = sum(int(run.get("kinds", {}).get("turn.started", 0)) for run in runs)
    earlier = max(len(runs) - 1, 0)
    if earlier == 0:
        return "This session has no earlier runs."
    return f"This session has {earlier} earlier runs and {turns} turns before this task."


def drive(seat, text):
    head, _, body = text.partition("\n")
    if not head.startswith("HEROBENCH "):
        seat.turn([{"role": "user", "text": text}])
        return
    task = json.loads(head[len("HEROBENCH "):])
    past = _past(seat)
    opening = f"{past}\n\n{body}" if past else body
    cap = int(task.get("turn_cap", 8))
    won = False
    ended = None
    turns = 0
    message = opening
    while turns < cap:
        # **A refused turn ends the task and still leaves its verdict.** The
        # harness refuses a turn that cannot fit the context, among others, and
        # the seat raises. The environment's verdict is read again and scored
        # below, between turns, so the run carries its score event whatever
        # ended it. On 2026-09-29 a task's tool results filled the 32,768-token
        # context at its eighth turn, and the loop died there unscored.
        try:
            outcome = seat.turn([{"role": "user", "text": message}])
        except RuntimeError as error:
            # The pyworker maps every turn error to RuntimeError, so the cause
            # rides the verdict's predicate and a fault-ended run reads as one.
            ended = " ".join(str(error).split())[:200]
            # The harness opened and recorded the refused turn, so it counts,
            # and the verdict's figure matches the record's turns.
            turns += 1
            won = _won(task["url"], task["character"], task["kind"], task["target"])
            break
        turns += 1
        won = _won(task["url"], task["character"], task["kind"], task["target"])
        if won:
            break
        emission = outcome.get("emission", "") if isinstance(outcome, dict) else ""
        unclosed = "<tool_call>" in emission and "</tool_call>" not in emission
        message = (UNCLOSED if unclosed else "") + _not_done(task) + CONTINUE
    # **A refused score is not survived quietly.** The harness takes one score
    # per run and refuses a second, so a refusal means this task shared its run
    # with an earlier one and its verdict is not in the record. Raising ends the
    # crossing with the refusal in the worker's log rather than letting the next
    # task begin as if it had been scored.
    predicate = f"herobench {task['name']} won"
    if ended:
        predicate += f", the run ended by a refused turn: {ended}"
    if not seat.score(predicate, won, turns, cap):
        raise RuntimeError(
            f"the harness refused the score for {task['name']}: one run carries one verdict"
        )
