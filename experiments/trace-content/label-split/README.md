# HeroBench positions and the label split, 2026-09-29

A dated measurement, read by no gate, taken for the state-management work: what the
trace carries at each position of a HeroBench task, and how the labels those positions
could carry split between what game state computes and what needs a model. Nothing is
built, trained or installed by it, and no HeroBench file is modified.

The deposit is on the shared bulk store at
`/bulk-store/weaver-testing/herobench-positions-2026-09-29/`, mounted on the thinkpad
under `/mnt/bulk-store/weaver-testing/`. It holds the replays, their position tables,
the segmented positions as JSONL, the split's counts and tables, the specimen search and
`SHA256SUMS`, and none of it is copied here. The scripts that produced every number
below are beside this note in `code/`, and `COMMANDS.md` gives how each was run.

## The two shares

HeroBench's recorded results were segmented into positions, each position given the
recipe that labels it, and the positions each recipe reaches were counted. The corpus
is 4,617 single-shot completions: 24 base result sets over 9 levels of 20 tasks, 4,317
completions, and 15 hard result sets of 20, 300. Of these, 3,882 have the model's text
on disk, and the shares are taken over those.

| Weighting | Positions | Computable | Judgmental | Unreached |
|---|---|---|---|---|
| every position | 1,477,957 | 51.4% | 44.6% | 4.0% |
| what the model wrote | 834,725 | 13.9% | 78.9% | 7.1% |

The two weightings answer different questions and neither is the other's correction.
Every position counts the environment's answers too, and an executed action is a
position, so a program that gathers in a loop contributes thousands of computable
positions a task. What the model wrote counts only its prose, its drafts and its
program's statements, which is what a label about the model's own reasoning is about.

**Computable** is a label that joins to game state by position with no model: an
executed action accepted or refused and the inventory delta its log line states, the
task's scored outcome, and a program statement calling the environment with literal
arguments, bound to the function's parameters as Python binds them and labelled by
parameter: whether the call fits the signature at all, whether its item code exists in
the ontology, whether its slot is one the character has, whether its move reaches a tile
that exists and what stands there, whether a gather or a fight is on the kind of tile
the preceding move reached, and whether it names the character the task created.
**Judgmental** is a label that needs a model: each line of prose the model wrote, for
whether it recites the dump, states a plan, or contradicts what was recited.
**Unreached** is what neither reaches here: a program statement whose arguments are
computed, a statement that calls nothing in the environment, and a line inside a code
block that is not the final program. A statement is judged by the first environment call
anywhere in its own expressions, so `print(gather(...))` and `if fight(...)[0] != 200:`
are calls. **The program is identified by equality with what the pipeline ran, and a
fenced block that differs from it in any way is a draft, whatever it contains**:
equality after the pipeline's own angle-bracket stripping and line by line with
whitespace trimmed and blank lines dropped, the fences found with the pipeline's own
pattern, and only where no fence equals the program is every fence a draft and the
program's lines taken out of the prose, which restored 4,735 prose lines in 108
completions that the filter had also taken where a fence was the program. That is the
recipe's limit. The first-and-last-line match it replaced accepted 307 fences that
equality does not, and alone decided which fence was the program in 8 completions, whose
chosen fences now count as drafts, 259 lines. **The step recipe is a static reading of
the program as written**: a gather or a fight joins the last literal move written before
it in source order, and the recipe does not execute, branch or simulate, because what
executed is the action bucket, read from the environment's own log, which is why the two
buckets are kept apart. Each of these corrected a first count: reading wrapped calls
moved 120 positions from unreached to computable, and binding arguments by parameter,
reading the fences by content, and labelling slots and signatures added 3,678 draft
lines that a following markerless program had hidden, moved 36 steps from unreached to
computable as calls that do not fit their signature and 1 back the other way, a gather
whose preceding move no longer binds, and relabelled 6,930 computable steps, 293 of them
calls read as valid that do not fit their signature and 494 equips naming no slot the
character has.

The split holds across the base levels: of what the model wrote, judgmental is 87.0 per
cent at level 1 and between 79.4 and 83.7 per cent from level 2 to 9. The hard set reads
44.9 per cent computable and 41.4 judgmental of what the model wrote, and the difference
is which models ran rather than the tasks: nine of its fifteen result sets are gpt-5, o3
and grok-4 variants, whose completions carry 1.3 to 32.0 per cent judgmental positions
of what they wrote on the hard set and 2.0 to 19.8 on the base set, their providers
returning little or no reasoning text beside the program. The per-level and per-model
tables are in the deposit's `split/tables.md`, produced by `code/tables.py`.

## Positions, and where each lands in our trace

One model's pair was replayed through the execution path, capturing the server's answer
at every action: gpt-4.1 on level 1, `5_Cultist Emperor_kill` (won) and
`14_Cultist Emperor_kill` (lost, score 85.7). Each replay reproduces its recorded run
exactly, the same log line for line, the same outcome and the same score. **The replay
reproduces recorded programs the pipeline already ran to completion** and bounds them
with an in-process alarm a program could catch or cancel, unlike `safe_exec`'s process
join, so it is a reproduction of known runs and not a sandbox for unknown code.

| Position | Lands in, when our agent plays |
|---|---|
| prompt: rules, action list, game dump, character stats | `message.system`, the identity prefix |
| prompt: the task | `message.user` |
| completion: the provider's reasoning, the text before the program, the program | `message.assistant` |
| each action: the request, playing action by action | `tool.call.started`, through the gate's shell |
| each action: the environment's answer, playing action by action | `tool.call.completed`, then `message.tool_result` |
| the whole program, run as one shell call | one `tool.call.started`, one `tool.call.completed` and one `message.tool_result` carrying the whole execution's output |

**The action rows hold only when the agent plays action by action**, each action its own
shell call, because the harness brackets one shell tool call per invocation. That is
the shape the state work wants and not the shape HeroBench's published runs used: those
ran the whole program at once, which our agent would run as one shell call, so the
trace would carry one bracket and one tool result holding every action's output
together, and the per-action positions would sit inside that one payload.

The lost task's prompt is 6,914 characters: rules 2,037, the action list 805, the game
dump 2,385, the character's stats 1,337, and the task 350. Its completion is 5,358
characters of text before a 217-character program of nine calls, the text cut where the
program the pipeline ran begins, each answered with the full state of what it touched,
the move with the destination tile and the whole character, the fight with its drops,
turns and blocked hits. The deposit's `replay/table-*.md` quotes one payload per kind,
from `code/positions_table.py`.

## Where the replay departs from the recording, and how it was held equal

The fork's environment enforces one-tile moves, and the recorded results predate that
change, so the pair replayed against the fork's server diverges on its first move: the
won task replays as a loss with every move refused. The replay was therefore run
against the benchmark's own tree at `7a9579e`, the last upstream commit before the
fork's gameplay changes, exported read-only, its server on a loopback port. Both
divergent replays against the fork's server are kept in the deposit's
`replay-fork-server/` as the evidence.

## What the corpus does not carry

- **Three result sets have no text on disk**, `gpt4.1_mini`, `qwen3_32b_think` and
  `qwen3_8b`, and `DeepSeek-R1-Distill-Llama-70B` and `qwen3_8b_think` lack it for some
  tasks: 735 completions in all, counted with their programs and actions and left out
  of the shares.
- **One result file does not parse.** The benchmark's own
  `results/results_hard/gpt-5-noise_level_code_logs.json` is malformed at character
  1,229,603, so that set has prose and outcomes and no programs or actions, and its
  per-set line reads 98.6 per cent judgmental for that reason alone.
- **The brief's figure of 186 entries over 21 models is not what the files hold**:
  they hold 24 base result sets, some of them one model with and without its thinking
  mode, and 4,317 base completions.

## The specimen

No "Pumpkin Spice" occurs in any HeroBench file, result, score, dataset, the harness's
state, or either April ArangoDB dump. The phrase occurs in two session transcripts: a
turn of 2026-08-31 naming "the Pumpkin Spice decision point" as the moment after a
retrieved fact lands, and the brief of 2026-09-29 naming the specimen as the template
for the judgmental labels. `pumpkin` in the game is a level-20 resource the Scarecrow
drops at rate 20, and `pumpkin_pie` is a level-20 cooking consumable the large dataset
alone asks for. The deposit's `specimen/` holds every match with its context, from
`code/specimen.py`.
