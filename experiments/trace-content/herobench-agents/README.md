# HeroBench played action by action, 2026-09-29

A dated run, read by no gate, taken for the state-management work: an agent playing
HeroBench one action per tool call through the gate's shell, so that every action and
the environment's answer lands in the trace at a position of its own, and the state
member's typed landing sees real traffic. Two agents were set up on one model,
`Qwen/Qwen2.5-7B-Instruct`, `rusty` served by the Rust SPU on the first A6000 and
`pyra` served by python-spu on the second. `rusty` ran. `pyra` was refused at load, and
its runs are a second act.

The deposit is on the shared bulk store at
`/bulk-store/weaver-testing/herobench-agents-2026-09-29/`, mounted on the thinkpad under
`/mnt/bulk-store/weaver-testing/`. It holds rusty's trace and state store, every task's
character log and grade, the probes, pyra's refusal, the box facts and `SHA256SUMS`, and
none of it is copied here. The CLI, the loop file, the run script and the identity
prefix are beside this note in `code/`, and `COMMANDS.md` gives how each step ran.

## What was run

Base level 1, tasks 1 to 3 of HeroBench's small dataset, three crafting tasks: Gold,
Spruce Plank and Hardwood Plank. Each task is one work item on the agent's gate. The
loop file presents the task's game data and the task, runs turns until HeroBench's own
result rule is met in the character's log or eight turns have passed, and records the
verdict as a `score` event. As the deposited runs were driven, each run was one load and
one unload of the agent with three tasks in one session context, and a pair of runs
shared a session so that the second opened with a past. Every task is graded after the
fact with the benchmark's own functions from the environment's log.

**The deposited runs carry one score event each.** The harness takes one score per run
and refuses a second, and the driver as it ran played three tasks in a run, so each
run's score event is its first task's verdict and the later tasks' scores were refused,
a refusal the loop did not check. rusty's trace holds 8 loads and 7 score events over
100 turns, the eighth load being the probe that stood no gate. The per-task outcomes in
the tables below come from the environment's logs, graded into each run's `run.json` and
task files, and not from score events. The driver in `code/` now runs each task as its
own run under the same session, so every task's outcome is a position of the record, and
the loop raises on a refused score. A task that times out is not graded and ends the
driver after an unload, and no task timed out in the deposited runs, the longest taking
724 seconds.

The environment is the fork at `32c1e0f`, two SQLite arms on ports 8030 and 8031, one
per agent, so the two games share the game table and not their world state. The fork
enforces one-tile moves, a move to any tile further than one step in x or y being
refused with HTTP 489, and that rule is where most of the model's actions went.

## Results

| Pair | Loop | Run | Gold | Spruce Plank | Hardwood Plank |
|---|---|---|---|---|---|
| `s-rusty` | v2 | 1 | lose, 0 actions | lose, 0 | lose, 0 |
| `s-rusty` | v2 | 2 | lose, 13 | lose, 2 | lose, 4, score 33.3 |
| `s-rusty-b` | v3 | 1 | lose, 5 | lose, 0 | lose, 0 |
| `s-rusty-b` | v3 | 2 | lose, 13 | lose, 5 | lose, 2 |

The actions are the accepted actions the environment logged, the character's creation
excluded. The counted pair is `s-rusty-b` under loop v3, and the `s-rusty` pair under
loop v2 is kept as its own record. No task was won. The published table tops out at 24
per cent for open models, and a 7B model at the sampling below was not expected to win
many, so the run's result is the traces rather than the score.

| Run | Turns | Generations | Tool calls | Answers accepted | Answers refused |
|---|---|---|---|---|---|
| `s-rusty` run 1 | 24 | 24 | 0 | 0 | 0 |
| `s-rusty` run 2 | 24 | 58 | 34 | 16 | 18 |
| `s-rusty-b` run 1 | 24 | 37 | 13 | 5 | 8 |
| `s-rusty-b` run 2 | 17 | 196 | 180 | 27 | 153 |

**The session's shape reached the model.** Every second run opened its first task with
"This session has 1 earlier runs and 24 turns before this task", read through the seat's
shape ask, and every first run with "This session has no earlier runs."

**The typed landing saw the traffic.** rusty's store holds 757 messages typed, their
parts 473 text, 277 tool calls and 275 tool results, and 321 measurements, three of them
with an absent perplexity held as null. 780 measurement readings landed verbatim rather
than typed, and the cause is measured: `serde_json` parses a float by a fast path that
is not correctly rounded unless its `float_roundtrip` feature is on, so the typed value
renders back differently and the landing's exactness rule sends it to `field`. Over
those 780 values, 0 round-trip under the default parse and 780 under the feature.
Custody held, since a value that cannot be typed exactly lands as it crossed.

## What the run found

- **Neither SPU renders a tool advertisement**, so the model is taught its one tool by
  the identity prefix. It carries Qwen2.5's own tools block verbatim, the `# Tools` text
  with the `bash` function's schema its chat template would render, after a first probe
  in which prose alone produced bare commands and no call. See #744.
- **The sampler is frozen and the call format decays under it.** Both SPUs sample at a
  compiled temperature of 0.7, top-k 40 and top-p 0.95, with a repetition penalty of 1.1
  over the last 64 tokens, and only the seed is tunable. The model closes a call with a
  second opening tag, which neither SPU's parse recovers, and as a turn's calls
  accumulate the opening tag itself is replaced by a stray token, " Ronaldo" under loop
  v2 and "Let", "It" or "ntl" under v3, after which the model narrates crafts it never
  made. Loop v2's feedback ended with the tag tokens and made the substitution
  immediate, which v3's wording removes. The unrecovered call leaves `message.assistant`
  empty while `model.output` keeps the emission. See #746.
- **python-spu refuses the harness's SPU arguments.** The worker launches every SPU with
  `--headroom-bytes` from the installation's configuration, and python-spu's argument
  parser rejects it and exits before any exchange, so the load rolls back as
  `no_residency`. See #745 item 3.
- **The agent territory needs ACLs where the script puts it.** `deploy/create-agent.sh`
  grants the state member traversal of the operator's home with `setfacl`, which a
  dataset without ACL support refuses, and it provisions postgres only. The two agents
  were made by hand to its steps with the territory under a directory the member's group
  can traverse. See #743.
- **A loop file needs the pyworker, and the worker is one value for the installation.**
  The compiled worker refuses `--loop-file`, so the installation ran the pyworker for
  the act and was restored to the worker after it.

## What python-spu's end-to-end run showed

Nothing past launch. Its smoke test passed on the second A6000, three fresh processes
exact across runs with the readout neutral, at FP32 as its Spec's section 2.1 records.
Integration with the harness stopped at the argument above, so the section's "not yet
shown" items stand as they were.

## The corrected driver, repeated as v4

The pair was repeated under the corrected driver, one task per run, as session
`s-rusty-c` with the loop file at sha256 `34ca456c` and the same tasks, seed and turn
cap, on the operator's approval of 2026-09-29, the installation's worker switched to the
pyworker for it and restored after. The deposit holds it in `rusty/v4-s-rusty-c/`, the
trace and store as they stood after it beside the passes.

| pass | task | result | score | actions | turns | tool calls | score event |
|---|---|---|---|---|---|---|---|
| pass1 | 1_Gold_craft | lose | 0.0 | 5 | 8 | 13 | present |
| pass1 | 2_Spruce Plank_craft | lose | 0.0 | 1 | 8 | 160 | present |
| pass1 | 3_Hardwood Plank_craft | lose | 33.3 | 8 | 8 | 189 | absent |
| pass2 | 1_Gold_craft | lose | 0.0 | 6 | 8 | 143 | present |
| pass2 | 2_Spruce Plank_craft | lose | 0.0 | 0 | 8 | 0 | present |
| pass2 | 3_Hardwood Plank_craft | lose | 0.0 | 5 | 8 | 56 | present |

No task was won. **Five of the six runs carry their score event and one does not.** Pass
1's Hardwood Plank filled the 32,768-token context at its eighth turn, resident 32,653
with a request of 242, the harness refused the turn with `Overflow`, the seat raised,
and the loop died before `seat.score`, so that run's outcome is the environment's log
graded by `run.py`, and its `run.json` entry says so. The loop in `code/` now catches a
refused turn, reads the environment's verdict again, and scores it between turns, so a
run carries its score event whatever ended it.

**The overflow is a finding of the per-action shape.** Eight turns of tool results fill
a 32k context, because each accepted action's answer carries the whole character block.
How much of that block a tool result carries is a design choice for the HeroBench tool,
a trimmed answer with the block on request or a larger context capacity, and this note
names the choice rather than making it.

