# determinism-matrix - Spec

**Status:** MERGED. In `main` and the source of truth.

**Date filed:** 2026-09-27
**Document ID:** `determinism-matrix-Spec`
**Parent:** `deployment-tuple-PRD`
**Editorial:** Per the Working Rules.
**Landing PR:** #734

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

**The cells mode is the same run over other sessions.** With `--cells` the run serves
the config's cells, each once: the cross-precision protocol, one artifact at one
precision per cell, the protocol's two pinned turns, one short and one longer, under the
declaration with that cell's artifact and everything else as the operator wrote it. The
schedule is data, the sessions it yields, and nothing else differs: one main, one
session loop and one exit, per the operator's ruling of 2026-09-27. A cells run is
finite and takes no deadline, so it takes no `--hours`, and a run short of its cells is
not a reproduction result, the log naming the cells it did not serve. A cell's record is
labelled by its name, precision and artifact, and the summary counts cells as `by_cell`.
`confirm_cells.py` has no entry point of its own.

## 3. The session

**One session is serve, unload, reload, reissue, compare.** In order:

1. Unload the agent, load it, and wait for the gate socket to stand. Once the half's
   closes name its run, hold that run's load event to the session's declaration and
   loop, per section 5.
2. Serve the session's texts, depth minus one filler turns and then the probe, and
   read the served turns back from the trace. They must all belong to one run and
   number exactly the depth.
3. Unload fully, reload, wait for the socket again, and hold the reload the same way.
4. Reissue every served turn byte-exact, the texts read back from the record's own
   user messages and not from the script's copy, and read the replayed turns back.
   They must land in one fresh run named by the gate's closes. Before the reissue the
   record's requests, in order, must be the texts the session served, byte-exact, and
   the replay's must be the source's, or the record is of another session.
5. Compare every turn.

**Every answer the admin gives is read.** The admin prints its answer and exits 0, or
prints its refusal and exits 1, and an answer counts only where the two agree. A load
must answer the state `idle`. The unload between the halves and the unload that closes
the session must answer `unloaded`, and the unload that opens it `unloaded` or the
refusal `no_residency`, nothing resident being a clean start. Any other answer is a
fault naming it, the first fault of a session standing. The unload the run makes as
it ends is read too, and a refusal is logged as the agent perhaps still
loaded, since no session's verdict rests on it.

**A turn is compared on eight fields**, per `CHECKS`: the rendered prompt, the derived
generation seed, the effective sampling knobs, the emission bytes, the finish kind, the
resident count, the input token ids, and the per-token entropies. A check either record
carries no value for, missing or null, is never a match and is a fault, so absence on
both sides cannot read as agreement. A turn matches when all eight are observed and
equal as JSON, type included, since Python's `==` takes 1, 1.0 and true for one value
and a replay recording one where its source recorded another did not reproduce. A
session matches when every served turn matches and the replay holds no
surplus turn, since a replay carrying turns the source did not is interleaved traffic
and never a match.

**The verdict is REPRODUCED or DIVERGED, and anything else is an apparatus fault.** A
session that could not complete records the step it stopped at as its verdict: a load or
reload refused, a socket that never stood, a load composed by a loop other than the
config's, a load that served a declaration other than the session's or wrote no load
event, a load whose unit invocation or serving device cannot be read, or which names no
device, a reload under the load's own invocation, a load under an invocation an earlier
session read, source and replay loads on different devices, a replay carrying turns the
source did not, an admin answer other than the step's, a turn not answered, a turn
missing its request, a payload kind or its closing event, carrying a compared kind
twice, or named by anything but a string, a source turn the replay does not carry, a
check a record carries no value for, source or replay turns split across runs, under a
run the gate names by anything but a string, or short of the depth, a replay read short,
a seed mismatch under section 4, an exception, recorded as `error: <type>: <message>`,
or an interrupt, recorded as `interrupted`. The one session path records each of these,
and the loop's boundary around each session makes a raise in formatting its record that
session's `error:` fault too, so no session and no summary is lost to a raise. A replay
read short is the sink one turn behind and is kept apart from DIVERGED, which is the
strongest negative the harness emits. Faults are counted apart from both verdicts, as
the summary's `errors`, so a run's divergence count is never inflated by sessions that
were not compared.

**Each session's record** carries the prompt, its character, the depth, the sweep,
both run identities, the declared and recorded seeds, the verdict and the wall time,
and for every turn whether it was the probe, whether it matched, the checks it
failed, its per-token entropy summary, its source and replay wall times, and the
sha256 of its emission.

## 4. The seed

**Every session is declared under a seed, the declaration's own where no schedule
stands.** The declaration is parsed as TOML at the start on every path, and its seed is
the one value at `spu-instruction.decoder.tunable-values.seed`, written inline or on its
own line. A document that does not parse, a seed that is absent, and a seed that is not
a TOML integer from 0 to 2^63 - 1, the sampler's u64 narrowed to what a TOML integer
carries and the stack's parser loads, a quoted number, a boolean or a float among them,
is refused by name before anything loads, and each seed of a schedule is held to the
sampler's u64. The artifact is read the same way, as the string at
`spu-instruction.decoder.model-binding.artifact` holding an absolute path. `--artifact`
rewrites only that value, as a quoted string, and with `--seed-schedule`, a
comma-separated list of distinct integers, only the seed's value is rewritten before
each session, every other byte of the file kept. A rewrite finds its value by the key
path it sits at, reading the document as TOML reads it so that text inside a string or a
comment names nothing, and a rewrite that finds other than one value at the path, or
whose result does not read back the new value with the rest of the document unchanged,
is refused, as is a scheduled seed past 2^63 - 1, the largest a TOML integer carries,
before the first session. Both halves of a session read the same seed and successive
sessions read different ones. The seed a matrix cell takes rotates by matrix cell and is
offset by sweep, so over as many sweeps as the schedule has seeds every matrix cell
meets every seed and no matrix cell keeps one seed from one sweep to the next. A
schedule that cannot hold both properties with the sweep boundary, one seed or two, is
refused. The declaration is restored when the run ends, by its clock or by an interrupt,
and not by a hangup, per section 5. `--artifact` overrides the declaration's artifact
for every session in the same way and is restored with it.

**A session whose seed the record does not bear out is a fault, not a verdict.** The
source turns must carry one recorded seed, `sampling.seed` on each `model.request`, with
or without a schedule, and it must be the seed the session was declared under, the
schedule's or the declaration's own. Every recorded seed is held to the u64 domain a
declared one is, an integer and never a boolean or a float, before it is compared, so a
seed recorded as true or 1.0 cannot stand for 1. The replay's recorded seed must equal
the source's, since both halves load from one declaration and a replay under another
seed is the apparatus and not the model.

## 5. Provenance

**The stack and the weights are read at the start and again at the end, and the summary
says whether each held.** The artifact the declaration binds, by sha256, the engine
libraries the SPU links, the worker, SPU and gate binaries, and the toolchain are each
read when the run opens and again when it closes. A field that reads the same at both
ends is `unchanged`, and one that differs says so with both readings, a changed claim
being made only where both sides are readings and not where a closing read failed. The
serving device is read from the worker's journal for each load as it stands, bound to
that load by its unit's InvocationID and never by a time window, which a fast reload or
a trailing journal holds the previous load inside. A binding is taken only once its
block is complete, the engine's next line seen after the device lines, since a block of
several cards can reach the journal a line at a time. Both halves of a session are on
one binding under two invocations, and no invocation recurs in a run. A journal kept by
size holds minutes, so a read at the close would miss most of a run. The window read at
the close is kept as a record and not counted. The summary carries these as `weights`,
`engine_libraries`, `weaver_binaries`, `toolchain` and `serving_device`, the window read
as `serving_device_journal_window`, and the counts as `sessions`, `reproduced`,
`diverged` and `errors`, the faults, with the verdicts by prompt character and by
declared seed as `by_character` and `by_seed`, the verdicts by cell in a cells run as
`by_cell`, the schedule as `declared_seed_schedule`, and the first twenty divergences
and faults as `diverged_detail` and `error_detail`. The keys are the ones the earlier
deposits' summaries carry, `by_cell` aside, which the fold added.

**Every load is held to the session's declaration and loop.** Each load event records
the digest of the declaration it served, the sha256 of the declaration file, and the
loop that composed it. Once a half's gate closes name the run its turns were served in,
the harness reads that run's load event, never the newest one a trailing sink wrote, and
holds the first to the declaration the session wrote, which holds the artifact path, the
seed, the sampling knobs and every other declared field per load, and where the config
names `loop_sha256` it holds the second to that digest. The declaration the loads are
held to is the bytes the run read at preflight, or the bytes it wrote for the session,
by the digest of those bytes and never by a read of the file back, and the disk is held
to them before the run starts. **Every check a session makes is one function**,
`verify_session` in `confirm_cells.py`: the load, declaration, loop and device holds,
the recorded seed, absence, the comparison and the surplus. The one session function,
the matrix's `run_session`, calls it for every session in either mode and verifies
nothing outside it, so no check can hold for one kind of session and be missing from
another. It records a raise from its closing unload as it records any other, an
interrupt there as `interrupted` and anything else as a fault. A config naming no loop
leaves the loop unchecked.

**The run-wide verdict is one function too**, `run_verdict` in `confirm_cells.py`: at
least one session ran and every session reproduced, every window field reads
`unchanged`, the weights window and the stack's three required, no binary was resolved
by a guess, and the sessions read one device binding. The one main exits on it and only
formats it. The invocation rule, that no invocation recurs in a run, is held on each
record as it closes by `hold_invocations`, which the one session loop calls.

**Each tuple field the probe holds, and how:**

| Field | Held how | Counted at the exit |
| --- | --- | --- |
| weights | the artifact's path held per load by the declaration's digest, and its bytes read at both ends of the run's window, every cell's artifact in a cells run | yes, `weights` must read `unchanged` |
| precision | fixed by the weights hash | yes, with the weights |
| device | each load's binding read by its unit invocation as it stands, both halves on one under two invocations, and every session on the same one | yes, `serving_device` must be one binding |
| kernel stack | the engine libraries, the binaries and the toolchain read at both ends | yes, each must read `unchanged` |
| batch composition | recorded, not held: one caller and one turn at a time by construction, and the record carries nothing a second caller would change | no |
| sampler and seed | the declared seed on every session's recorded seed, the replay's equal to the source's, the knobs compared per turn and held per load by the declaration's digest | yes, every session's verdict |

**The exit code is the whole claim.** A run in either mode exits 0 only where it ran a
session, every session reproduced, and every field counted above held, and
otherwise 1, with a log line naming the fields that did not hold. A field read only at
the two ends is held against a change that stands at the close, not one undone within
the run, and the per-load declaration digest is what holds the declared fields between.

**What an exit 0 certifies.** Every session's replay, served by a fresh process on the
declared stack, matched its source on all eight `CHECKS` fields, and every field counted
above held across the run's window. Each of those facts rests on evidence the harness
read itself: the admin's answers with their exit status, each load's unit invocation and
the device its journal names, each load event's declaration and loop digests, the
recorded seeds and turns from the trace, and the stack and the weights by sha256 at both
ends. None rests on a party's word that a step happened.

**It guards against accidental change.** A build or an install landing mid-run, a
deposit an earlier run left, a config that is wrong, malformed or names a relative path,
a step the admin refused or that failed, a value a record does not carry, and an
interrupted run each make the run refuse at preflight or exit 1, as the sections above
and section 7 say.

**It does not guard against a deliberate party on the operator's box racing the run.**
An edit made to a file between two of the harness's reads of it, or an artifact swapped
for one load and restored before the window's closing read, is outside what an exit 0
claims. A window cannot see a swap made and reverted between its two reads, and the
declaration's digest binds each load to the artifact's path and not to its bytes. A
finding that needs such a party is declined by citing this section. The instrument that
would buy the guarantee is a per-load hash of the weights and the stack, read at each
load and held like the declaration, and this probe has not bought it.

**The boundary is this measurement's alone.** The custody rule for privileged steps,
that no privileged step acts on a copy of a fact without verified evidence, is the
Blackwell probe's, in `blackwell-probe-Spec` section 5, and this section leaves it
unchanged.

**A run killed outright writes no summary.** An interrupt ends the run cleanly and still
writes it, in either mode: the session it cut short is recorded as `interrupted`,
wherever in the session the interrupt lands, the window is read at the close, and the
run exits 1, since a session it began did not complete. Every step between the session
loop and the summary, the declaration's restore, the run's last unload, the closing
readings of the stack and the weights, the SPU's closing resolution, the journal's
device read and the summary's write, is guarded: an interrupt there marks the run
interrupted and the step is tried once more, and any other failure is logged, a restore
that failed leaving the backup standing. A summary that could not be written, or a
restore that did not land, fails the exit, since the run's result rests on both. A
session's record joins the summary's counts only with its line in `matrix.jsonl`, so the
two agree, and a line that could not be written fails the exit too. The run's last
unload and the journal's device read are notes and do not, no session resting on either.
A hangup, which is what closing the operator's terminal sends, ends the process before
it does, and the per-session record written as each session closes is then the whole of
what the run left.

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
   compiler, the toolchain, the kernel, and the journal's retention, its disk use and
   its oldest entry.
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

**Every value a run takes is checked at preflight, before it writes or loads anything.**
The seeds, per section 4, `--hours`, which must be finite, positive and a deadline the
clock reaches, the config's `loop_sha256`, which must be 64 lowercase hex digits, and
the declaration's artifact and any `--artifact` are refused by name, and the outdir is
made only once every check has passed, the last check being that each output the run
writes can be created in it. A cells run checks each cell's artifact the same way, and
requires `cells` to be a non-empty list of cells whose name, precision and artifact are
non-empty strings, the names plain and none repeated, since each labels its cell's
record and its weights reading. A refused run exits 2.

**Every file a run opens is opened at preflight too.** The config must parse as a JSON
object. The artifact, or in a cells run each cell's, is opened and hashed as the
weights' opening reading. The declaration is read, and where the run rewrites it, it is
opened for writing and its directory must be writable for the backup. The admin binary
must be a regular file with an execute bit, since it runs under `sudo`, and the
repository a directory. The stack's opening readings are taken there, the admin
configuration's entries, the binaries they name, the SPU and each library it links, and
a reading that is not one, or that resolved a binary by a guess, is refused, since the
exit could never count it held. The trace and the gate socket stand only once a load
has, and each is awaited where it is read. No loop file is opened: the loop is held by
its digest against each load event.

**Every path the stack resolves is absolute.** The worker and the admin's units resolve
a relative path against their own working directory and the harness against its launch
directory, so one spelling would name two files and the run would record the bytes of
one while the stack served the other. The declaration's artifact, `--artifact`, each
cell's artifact, the config's `trace`, `gate_socket` and `admin_config`, and every
binary the admin configuration names are refused at preflight unless absolute, and a
library `ldd` names by any other path is unreadable. The paths only the harness opens,
the declaration file, `admin_bin`, `repo` and the outdir, are its own. A config may not
name an SPU of its own: the admin launches the one its configuration names for the
agent, the key `agent-spu` gives it in `spu-implementations` where the agent is named
there and `spu-binary` otherwise, per `weaver-admin-Spec` section 9, and the run reads
it there, so a config carrying `spu_bin` is refused. **Each file the run reads there is
classed as admin's loader classes it.** `allow-list`, `worker-binary`, `spu-binary` and
`gate-binary` are required, and one absent is an unreadable resolution, admin refusing
every verb without it. `spu-implementations` and `agent-spu` are optional, and only
their absence stands the default. A file of either class that stands and does not read,
a dangling link, a directory or a file this run may not read, is an unreadable
resolution the exit gates, never the default, since admin launches what the file says
and not what this run could see. Both maps are judged whole by admin's rules before any
default is taken, whichever agent they name, and a `spu-binary` naming no path is
unreadable rather than guessed.

**Every file a run writes is its own.** A run in either mode writes three fixed names
into its outdir, and its declaration backup beside the declaration.

**A run writes into a deposit no earlier run wrote.** An outdir already holding
`matrix.jsonl`, `matrix.log` or `summary.json` is refused before anything is written,
since an appended record under a summary of one invocation disagrees with it. A run that
rewrites the declaration keeps the operator's text beside it as `.pre-matrix` until it
has restored it, and a run finding one standing refuses, since the declaration on disk
is then not the operator's.

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
`code/README.md`'s, as is its file list: `determinism_matrix.py`, the one entry point,
`confirm_cells.py`, the harness it imports, with no entry point of its own, and the
tests.
