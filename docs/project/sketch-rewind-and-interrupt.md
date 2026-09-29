# Sketch: rewind, retry, and the researcher's interrupt

**Status:** LIVING, outside the set. A sketch in `docs/project/`: it maps into no
graph and nothing is written against it. What it settles moves into the apex, the
contracts and the Specs by acts of their own, and the apex moves only on the
operator's ruling.

**Date filed:** 2026-09-29

**Landing PR:** #750

---

## 0. What this document is

The design for stopping a running agent and continuing from any recorded
position, and for the researcher's interrupt as the first caller of that door.
It rests on one property the record already has: the trace carries what the
agent was presented at every position, the rendered prompt on every
`model.request`, so a state the agent stood in can be stood up again from the
record rather than reassembled from ingredients. It is written on the operator's
word of 2026-09-29, in his framing: the trace is the append-only source of
truth, a reload is a bookkeeping event in it, and the power of a trace this
detailed is the ability to rewind and try again from a given spot.

## 1. The door: preload to a position

The corpus has a preload door, the restore election of the operator's ruling of
2026-09-04 on #432, per `weaver-state-PRD` section 4 and
`weaver-analysis-state-contract`, which stands a session up from its record, whole or
cut at a named turn. A restored conversation is recorded under `message.restored`, per
`weaver-trace-Spec` section 3, and a diagnostic binding's record opens with
`replay.opened`, per `weaver-diagnostic-Spec` section 4. This sketch adds one parameter
to it, the position, and one rule of lineage.

**A continuation from position N of run R is a new run under the same session, and its
opening event names R and N.** Nothing in R is rewritten and nothing is removed. The new
run's first event after its load is the branch event, carrying the parent run, the
branch position, the reason (a retry, an interrupt's resumption, a diagnostic entry),
and the deployment tuple the branch stands on. Every later reader can walk from any run
to the position it grew from, which is the lineage the analysis-web contract's branch
position already expects a record to state.

**That departs from a standing ruling, and the departure is the operator's to make.**
Under `weaver-state-PRD` section 4 today, a cut lands as a branch under a new session
name, and a cut under the record's own session name is refused before the preload,
because a session cannot rewind under its own name while its record carries what the cut
would drop. A same-session continuation keeps the abandoned line in the session's record
and its holdings, so the ruling changes with it, or the branch takes a new session name
and the lineage rides the branch event across sessions.

**The reload is exact on the tuple that ran and approximate across a card.** The
determinism matrix of 2026-09-27 and 2026-09-28 is the measurement: 464 of 464 turn
slots identical across the two A6000 cards of one tuple, and across card generations 20
of 464 differing between the A6000 pair and the Blackwell and 21 of 464 between the Ada
and either. So a branch on the same tuple is a controlled experiment, what differs after
N being what was changed, and a branch on another card is a run whose first divergence
may be the card's. The branch event carries the tuple so the reader can tell which.

**Nothing in the SPU rewinds.** `weaver-spu-Spec` section 4 holds the session
append-only, `resident_len` and truncation a fault. So the branch is never a cache
operation on the running session: it is a reload, a fresh admission re-prefilled
to N from the record, and the running session either continues on its own line
or is unloaded. That is what keeps the record honest, because the state the new
run starts from is one the record can show, not one a cache held.

## 2. Rewinding the agent does not rewind the world

The record restores what the agent was presented. The world the agent's tools
touched has moved on: a HeroBench character has the position, inventory and
equipment the abandoned line left it with, and a filesystem has the files. A
branch from N is therefore exact on the agent's side and one of two things on the
world's side, and the sketch names which applies to each tool rather than
letting the question be discovered by a retry that behaves strangely.

- **The tool resets the world to its state at N.** HeroBench can: the environment
  creates a character, and a branch recreates it and replays the accepted actions to N,
  or restores the character block the record carries. The environment's answer to an
  accepted action carries the character block, recorded verbatim in the tool result,
  which is what makes the restore possible from the record alone.
- **The record carries the world's state at every tool result, and the branch measures
  the divergence.** Where a tool cannot reset, the tool result's content is the evidence
  of what the world was, and a branch reports what it found the world to be against what
  the record said it was at N.
- **The shell tool has neither.** A branch there is a new experiment against a changed
  world and the branch event says so, so a reader does not take it for a retry.

## 3. The researcher's interrupt, the first caller

The interrupt is a run-level state transition, not a message, and the back end
owns it. Its shape, settled against the corpus:

**Quiescence is admitted over admin.** It is administrative control of the run
rather than work, so it rides `weaver-admin-harness-contract`, which has two
initiators and one dial per verb already. On receipt the harness stops admitting
work at the turn boundary: it refuses the next `turn()` its loop asks for as
quiesced, in-flight forward passes and concurrent organ work finish, nothing is
cancelled mid-flight, and the harness declares the run quiesced. A half-written
state is a state that never existed and is not worth interviewing. The trace
records a quiescence event carrying the position, the wall clock instant and
what was in flight when the request arrived, so a clean stop reads differently
from a stop that caught the loop mid-turn.

**The interview enters through the gate as ordinary traffic.** The gate is the
sole work ingress and it authenticates the researcher already, so a second
channel would cost a socket and a contract for nothing. What distinguishes an
interview turn is the harness's state rather than the channel: a turn admitted
while the run is quiesced is an interview turn, and `turn.started` carries the
interrupt's identifier for it. The trace is turn-bracketed, so the turn is the
unit that is marked, and a replay presents the run with the interview or without
it by that mark alone, and a count reports both.

**Cleanliness is read rather than inferred.** The run's closing event carries
the list of interrupt identifiers it saw, the empty list being the positive
uninterrupted marker.

**Resumption takes two forms and the operator elects between them.**
Resume-with-interview releases the loaded agent from quiescence with its cache
warm, the interview now part of the run by construction and marked as such.
Resume-clean is section 1's door with a filter: a reload to the quiescence
position with the interview turns excluded, a new run whose branch event names
the interrupt it resumes from. Either way the interview is recorded, since an
interview that left no mark on the resumed line is still evidence about the
agent.

**The lifecycle gains two verbs and one state.** Quiesce and resume join load,
unload and validate in apex section 6, under its rule that no verb auto-chains
another, and `Quiesced` joins the agent's states, whose case set
`weaver-types-Spec` holds as not free. That is the operator's ruling at the apex,
with `weaver-admin`, `weaver-harness`, `weaver-trace` and `weaver-types`
following in one act, contracts included.

## 4. The frontend

The fog toggle, the full map against the map the agent has been shown, needs no back-end
work beyond what the record holds: the game dump the agent was given rides the task's
user turn and the full map is the environment's table, so both are derivable, and the
web contract is the only document it touches.

## 5. What lands where

- The apex, section 6: the two verbs and the state, the operator's ruling.
- `weaver-admin-harness-contract`, `weaver-admin-PRD` and Spec: the quiescence
  and resume exchanges and their refusals.
- `weaver-harness-PRD` and Spec: the boundary behaviour, the interview marking by
  state, the two resumptions, the branch as a preload with a position.
- `weaver-trace-Spec` section 3: the quiescence event, the branch event, the
  turn marker, the closing list.
- `weaver-types-Spec`: the state case.
- The web contract: the branch lineage as presented.

## 6. Open cells

- Whether a branch's parent is named by run identifier and sequence alone, or
  also by the hash of the rendered prompt at N, so a branch against an edited
  record refuses rather than continues.
- What "in flight" enumerates on the quiescence event: the forward pass, a tool
  call, an organ exchange, or any of them.
- Whether resume-with-interview and a warm-cache continuation after a plain
  quiescence are one verb or two.
- The diagnostic replay sketch's mid-run entry cell, whether entry at N matches a
  full replay at N, is this door's measurement and is not in the repository.
- The cost of a reload to N, which is a re-prefill and is measured rather than
  guessed.
