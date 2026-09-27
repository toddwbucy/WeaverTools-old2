# determinism-matrix - Spec

**Status:** MERGED. In `main` and the source of truth.

**Date filed:** 2026-09-27
**Document ID:** `determinism-matrix-Spec`
**Parent:** `deployment-tuple-PRD`
**Editorial:** Per the Working Rules.
**Landing PR:** #716

---

## 0. What this document is

The Spec of the determinism matrix, the baseline probe of the deployment-tuple
experiment, filed at `experiments/deployment-tuple/baseline/determinism-matrix/`
beside its code. The charter registers the tuple and its arms. This document states
what the probe's code does and claims, and it carries the two declarations every
probe of the experiment shares: the tuple fields a run records, and the box facts a
deposit carries beside its record.

The code is `determinism_matrix.py` and the harness it imports, `confirm_cells.py`, from
the `weaver-experiments` tree at `d04da2a`, where the matrix ran from 2026-08-27 until
it moved here. Both differ from that copy by the fixes of pull request #716, which hold
every tuple field the probe claims held, per section 5, and refuse absence and
unreadable evidence rather than read them as agreement, per section 3. A test pins that
on the path every session of the 2026-09-27 runs took, a recorded seed, no schedule,
every compared field present in both records and every load logging its device, the
verdict, the recorded seeds and every turn are the ones the `d04da2a` file returns, and
the fields that move are named: the declared seed, null in those runs' records and now
the declaration's own, and the device each session's loads logged. A run from this
directory is the same instrument as the two thinkpad runs of 2026-09-27, made from
`d04da2a`. The deposits before them ran earlier revisions of the matrix, and each names
its own by sha256 where its box facts record one. The two files keep their own
docstrings and comments, and this document restates only what a reader needs to hold a
result against.

**Words.** The charter's cell is a card family a device probe runs on. This probe's
code calls one combination of a prompt and a depth a cell, and in this document that
combination is a **matrix cell**. A **session** is one matrix cell served, replayed
and compared once. A **sweep** is one pass over every matrix cell.

```graph
node: determinism-matrix
kind: probe

edge: parent
from: determinism-matrix
to: deployment-tuple
```

## 1. What the probe is

**It asks whether the replay instrument holds, and it asks on the easiest target on
purpose.** With the smallest artifact at a single precision, a session that fails is
the apparatus failing rather than the model being unfaithful. Every other arm reads
a divergence as a finding about a field, and that reading is sound only where this
probe says the instrument reproduces what it served. It varies no tuple field. It
holds all six and asks whether holding them is enough.

**The path it exercises is the served one, and nothing in it is stubbed.** Every turn
goes from the script to the agent's gate socket, through `weaver-gate` to the worker
and on to `weaver-spu` on the card, and the trace proves it: the bracket, the message
kinds and the residency events carry `subsystem=harness`, and the model events carry
`subsystem=spu_decoder`. A session covers the gate seam, the harness's bracketing and
authoring, the decode seam, the SPU, and the whole unload-and-reload residency cycle.

## 2. The matrix

**Three axes, chosen for what could plausibly break a replay rather than for
repetition.** Repeating one prompt exercises kernel nondeterminism and the allocator
and nothing else, so the matrix varies instead.

**Prompt character**, eight prompts spanning the draw's confidence, since a near-tie is
where a float wobble flips the draw and diverges the whole emission:

| Probe | Character |
| --- | --- |
| `factual-short` | confident |
| `arithmetic` | confident |
| `definition` | confident |
| `explain-long` | mid |
| `code-long` | mid |
| `creative-short` | near-tie |
| `creative-long` | near-tie |
| `openended` | near-tie |

The texts are the `PROMPTS` constant, and the short and long pairs cross different
kernel tile boundaries, which is the third axis, length, carried by the prompts rather
than by a flag.

**Depth**, one of 2, 8, 16 or 32 turns per session. The probe is the last turn, and
the turns before it are one fixed filler text, short and confident, so the depth it
builds costs little wall clock and adds little entropy of its own. A turn at position
2 meets a nearly empty resident sequence and one at 32 meets a long accumulated one,
and the derived generation seed carries the turn ordinal, so depth moves the seed as
well as the state.

**Sweeps, not repeats.** A sweep takes the depths in order and every prompt at each
depth, 32 matrix cells, and every matrix cell is seen once before any is seen twice.
A run is bounded by wall clock and not by a count: it finishes the session in hand
and stops once its hours are spent, so a run cut short by the clock still covers the
matrix rather than the front of it.

## 3. The session

**One session is serve, unload, reload, reissue, compare.** In order:

1. Unload the agent, load it, wait for the gate socket to stand, and hold the load to
   the session's declaration and loop, per section 5.
2. Serve the session's texts, depth minus one filler turns and then the probe, and
   read the served turns back from the trace. They must all belong to one run and
   number exactly the depth.
3. Unload fully, reload, wait for the socket again, and hold the reload the same way.
4. Reissue every served turn byte-exact, the texts read back from the record's own
   user messages and not from the script's copy, and read the replayed turns back.
   They must land in one fresh run named by the gate's closes.
5. Compare every turn.

**A turn is compared on eight fields**, per `CHECKS`: the rendered prompt, the derived
generation seed, the effective sampling knobs, the emission bytes, the finish kind, the
resident count, the input token ids, and the per-token entropies. A check either record
carries no value for, missing or null, is never a match and is a fault, so absence on
both sides cannot read as agreement. A turn matches when all eight are observed and
equal, and a session matches when every served turn matches and the replay holds no
surplus turn, since a replay carrying turns the source did not is interleaved traffic
and never a match.

**The verdict is REPRODUCED or DIVERGED, and anything else is an apparatus fault.** A
session that could not complete records the step it stopped at as its verdict: a load or
reload refused, a socket that never stood, a load composed by a loop other than the
config's, a load that served a declaration other than the session's or wrote no load
event, a load whose serving device cannot be read or names none, source and replay loads
on different devices, a turn not answered, a turn missing its request or a payload kind
or carrying a compared kind twice, a source turn the replay does not carry, a check a
record carries no value for, source or replay turns split across runs or short of the
depth, a replay read short, a seed mismatch under section 4, or an exception. A replay
read short is the sink one turn behind and is kept apart from DIVERGED, which is the
strongest negative the harness emits. Faults are counted apart from both verdicts, so a
run's divergence count is never inflated by sessions that were not compared.

**Each session's record** carries the prompt, its character, the depth, the sweep,
both run identities, the declared and recorded seeds, the verdict and the wall time,
and for every turn whether it was the probe, whether it matched, the checks it
failed, its per-token entropy summary, its source and replay wall times, and the
sha256 of its emission.

## 4. The seed

**Every session is declared under a seed, the declaration's own where no schedule
stands.** The declaration's one `seed:` line is read at the start on every path, and a
declaration carrying other than exactly one, or a seed that is not an integer, is
refused before anything loads. With `--seed-schedule`, a comma-separated list of
distinct integers, that line is rewritten before each session. Both halves of a session
read the same seed and successive sessions read different ones. The seed a matrix cell
takes rotates by matrix cell and is offset by sweep, so over as many sweeps as the
schedule has seeds every matrix cell meets every seed and no matrix cell keeps one seed
from one sweep to the next. A schedule that cannot hold both properties with the sweep
boundary, one seed or two, is refused. The declaration is restored when the run ends, by
its clock or by an interrupt, and not by a hangup, per section 5. `--artifact` overrides
the declaration's artifact for every session in the same way and is restored with it.

**A session whose seed the record does not bear out is a fault, not a verdict.** The
source turns must carry one recorded seed, `sampling.seed` on each `model.request`, with
or without a schedule, and it must be the seed the session was declared under, the
schedule's or the declaration's own. The replay's recorded seed must equal the source's,
since both halves load from one declaration and a replay under another seed is the
apparatus and not the model.

## 5. Provenance

**The stack and the weights are read at the start and again at the end, and the summary
says whether each held.** The artifact the declaration binds, by sha256, the engine
libraries the SPU links, the worker, SPU and gate binaries, and the toolchain are each
read when the run opens and again when it closes. A field that reads the same at both
ends is `unchanged`, and one that differs says so with both readings, a changed claim
being made only where both sides are readings and not where a closing read failed. The
serving device is read from the worker's journal for each load as it stands, both halves
of a session on one binding, since a journal kept by size holds minutes and a read at
the close would miss most of a run. The window read at the close is kept as a record and
not counted. The summary carries these with the counts: sessions, reproduced, diverged,
faults, the verdicts by prompt character and by declared seed, and the first twenty
divergences and faults.

**Every load is held to the session's declaration and loop.** Each load event records
the digest of the declaration it served, the sha256 of the declaration file, and the
loop that composed it. After each half's load stands the harness holds the first to the
declaration the session wrote, which holds the artifact path, the seed, the sampling
knobs and every other declared field per load, and where the config names `loop_sha256`
it holds the second to that digest, as `confirm_cells.run_cell` does. A config naming no
loop leaves the loop unchecked.

**Each tuple field the probe holds, and how:**

| Field | Held how | Counted at the exit |
| --- | --- | --- |
| weights | the artifact's path held per load by the declaration's digest, and its bytes read at both ends | yes, `weights` must read `unchanged` |
| precision | fixed by the weights hash | yes, with the weights |
| device | each load's binding read as it stands, both halves on one, and every session on the same one | yes, `serving_device` must be one binding |
| kernel stack | the engine libraries, the binaries and the toolchain read at both ends | yes, each must read `unchanged` |
| batch composition | recorded, not held: one caller and one turn at a time by construction, and the record carries nothing a second caller would change | no |
| sampler and seed | the declared seed on every session's recorded seed, the replay's equal to the source's, the knobs compared per turn and held per load by the declaration's digest | yes, every session's verdict |

**The exit code is the whole claim.** The run exits 0 only where it ran a session, every
session reproduced, and every field counted above held, and otherwise 1, with a log line
naming the fields that did not hold. A field read only at the two ends is held against a
change that stands at the close, not one undone within the run, and the per-load
declaration digest is what holds the declared fields between.

**A run killed outright writes no summary.** An interrupt ends the run cleanly and
still writes it. A hangup, which is what closing the operator's terminal sends, ends
the process before it does, and the per-session record written as each session
closes is then the whole of what the run left.

## 6. The shared declarations

**These are the experiment's, stated once here so that every probe points at them
rather than restating them.** A probe's own Spec states its values, and these state
what the values are of.

### 6.1 The tuple fields a run records

| Field | What a run records | Where |
| --- | --- | --- |
| weights | the artifact's path and its sha256 | box facts, and the declaration's `model-binding` |
| precision | the artifact's quantization, which the weights hash already fixes | the artifact's name, box facts |
| device | ordinal, card name, PCI bus id, driver version | the summary's `serving_device`, box facts |
| kernel stack | the engine libraries and the weaver binaries by sha256, the CUDA toolkit, the reduction library, the host compiler, the toolchain, the source commit and the pinned engine and candle revisions | the summary's provenance fields, box facts |
| batch composition | one caller and one turn at a time, by construction | box facts states it |
| sampler and seed | the declared seed, and the derived generation seed and sampling knobs per request | the declaration, the session record, `model.request` in the trace |

The declaration's other elections, its context capacity, token cap, identity and
readings, are part of what a run holds, and the declaration is recorded by its sha256.

### 6.2 The box facts

A deposit carries a `box-facts.txt` beside its record, because neither the trace nor
the record carries everything the table above names. It is plain text, `#` lines are
comments, and it holds these parts in this order:

1. **A header**: the source commit and how it was installed, the pinned revisions, the
   device line, the driver, the CUDA toolkit and the reduction library, the host
   compiler, the toolchain, and the kernel.
2. **Binaries**: one `sha256sum` line per installed weaver binary.
3. **Engine libraries**: one `sha256sum` line per library the SPU links, and where the
   set was installed from.
4. **Artifact and declaration**: their `sha256sum` lines, and whether the declaration
   names a loop file.
5. **Drivers**: the probe's own scripts and its config by `sha256sum`, and the tree
   and commit they came from.
6. **Clocks**: whether a clock was held, and how. Where one cannot be held without
   privilege the run records the state instead, and this part names the readout, the
   supported maxima and one idle reading.

A second run on an unchanged stack copies the file and records at its head when it
re-read the stack and found it unchanged.

## 7. What a run requires

**Every load and unload is a privileged step.** The harness calls the admin through
`sudo -n` four times a session, so a run needs a sudo credential that holds for its
whole window without a prompt. This probe does not ask for a standing grant, since a
grant that passes the admin's configuration through would let any process of the
operator's uid choose what the admin executes as root. A run lives in the operator's
own terminal on a fresh ticket, and `code/README.md` gives the shape.

**Clocks are recorded where they are not held.** A lock needs root per load, so a run
that holds none records the card's state beside itself with an unprivileged readout
every five seconds, and a result joins those samples to its sessions.

## 8. What the probe does not establish

**No loop behaviour.** The reference agent declares no loop file, so the harness runs
its fallback, one turn carrying the text and no policy. A result says nothing about
replay surviving a loop that edits context.

**Most turns generate one token.** The filler asks for a single word, and in the
2026-08-27 baseline 40,987 of 43,620 compared turns generated exactly one token. A
result counts its substantive generations separately from its turns.

**Time to first token is not measured**, because the record cannot carry it.

**One model, one precision.** The baseline runs the 0.5b at q6_k. A reproduction here
is the instrument holding on the easiest target, and each arm owes its own verdict on
a harder one.

**Record kinds the reference agent never produces are not exercised.** An agent with no
loop and no state member writes no recall, restored-message or score records, so the
harness's reader meets none of them.

**Batch composition is one by construction**, per the charter, and no run here speaks
to it.

## 9. What this document does not carry

The results, which land dated in this probe's `results/`. The runs that predate this
directory are held in `weaver-experiments` with the deposits they produced. On
olympus: 2026-08-27, 2026-08-29 and its loop run, the clock-state run of 2026-09-06
and the seed and W0 runs of 2026-09-08. On thinkpad: 2026-08-27, 2026-08-29 at
`616d0d4` and 2026-08-29 on the basic loop. The clock-state driver, which locks the
card's clock before every load, stays in `weaver-experiments` with the result it
produced and joins this probe by its own act. How to run the probe on a box is
`code/README.md`'s.
