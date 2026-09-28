# blackwell-probe - Spec

**Status:** MERGED. In `main` and the source of truth.

**Date filed:** 2026-09-25
**Document ID:** `blackwell-probe-Spec`
**Parent:** `deployment-tuple-PRD`
**Editorial:** Per the Working Rules.
**Landing PR:** #716

---

## 0. What this document is

The Spec of the Blackwell probe, one measurement of the device field of the
deployment tuple, filed at `experiments/deployment-tuple/device/blackwell/` beside its
code and its results. The experiment's charter, the root `README.md` of
`experiments/deployment-tuple/`, registers the tuple, the device field's claims and
this probe's place among them, and this document states what the probe's code
enforces, per the operator's rulings of 2026-09-25 recorded at Working Process
section 5 and Document Format section 3: a Spec belongs to any code that requires
one, and a probe's code requires one for the reason a crate's does, that no code
lands in phase three without a ratified document. The probe landed as a held
preparation with an issue for authority, and this document closes that gap by
stating what the code does and why, in the order the operator meets it, so a reader
of the code finds each refusal's reason here and a reader of this document finds each
claim's instrument in the suite.

It is written from the code as it stood after sixteen review passes on pull request
#683 and from the registration on issues #511 and #679. The code lands in `code/`
beside this document with #683, which moves it there and cites the assertion
records declared here from its file headers with `conforms:` lines, which stand
unmaintained and are read by nothing until release. Results, when a leg has run, sit in
`results/`, dated and read by no gate.
What the probe measures and why is the charter's and is restated in sections 1
through 3 only as far as the code enforces it. How the seams it drives behave is the
crate charters' and contracts' and is cited rather than repeated. What this document
owns is the workflow: the tuple as the code holds it, the legs as the code schedules
them, the order of operations, the privilege boundary, the identity verdict, the
assessment, and the refusals.

**Words.** The chapter's word for one variable's experiment is an arm, the weights
arm or the batch arm, and that is the word the charter and the directory use. This
probe's three measurements, the control, the device comparison and the kernel
comparison, are its legs in this document, and the code's identifier for them is
`arms`, kept until the code is next touched so that no identifier moves in a
documents-only act.

**One probe, many cells.** The device field has been measured on Ampere and Ada, on
olympus under the tooling #516 retired, and the Blackwell probe is its third cell.
The charter names the next, the re-verification of Ampere and Ada at the same tuple
on the new driver. What varies per cell is the plan: the stacks, the agent name and
root, the interlock, the device tuple and the registered claims. What does not vary
is every rule this document states and the code enforces. The constants of the
Blackwell cell appear here where the code fixes them today, and the act that stands
the next cell moves them into the plan.

```graph
node: blackwell-probe
kind: probe

edge: parent
from: blackwell-probe
to: deployment-tuple
```

## 1. What the probe is

**One card, one commit, two stacks, three legs.** The cell runs the Weaver probe of
#511 on this box's RTX PRO 5000 Blackwell under one source commit, `e69916a`, so
the device leg is not also a build leg. `B1` is olympus's `e69916a` stack copied by
bytes, the kernel held as bytes, and is the device cell. `B2` is `e69916a` built on
this box under its own toolkit and CUDA user-space libraries. Whether the two stacks'
executable sections are identical decides whether the kernel leg runs at all, per
section 6.

The three legs are `TB0`, the control, which asks whether the card reproduces under
itself, `TB-d`, the device cell, which re-feeds the Ampere and Ada Q8_0 records of
#511 through `B1`, and `TB-k`, the kernel leg, which re-feeds `B1`'s own records
through `B2`. Every claim, prediction and falsifier is registered before any leg runs,
and section 3 carries them as the code enforces them.

**The driver confound is carried, not hidden.** The olympus deposits were taken on
driver 610.57.04 under CUDA 13.3 and this box runs 615.71.09, so a `B1` reading
against those deposits varies device and driver together until the olympus seat
re-verifies at the same tuple. A `B1` divergence is never attributed to the card
alone, and the report says so.

**It runs the loops the corpus already has.** A free run is a gate turn through
`basic_loop.py` under a serving binding. A re-feed is the diagnostic replay loop,
per `diagnostic-replay-loop`, driven through `weaver-analysis`'s `derive` and
`preload` against a diagnostic load. The probe adds no loop of its own, and the
admin, gate, harness, analysis and state members it drives are the installed
`e69916a` binaries, not the tree at head. That is why a finding about the head's
admin does not reach this workflow unless the stacks are re-staged from head, which
is a ruling on #679 and not this document's.

## 2. The tuple, held

The tuple is fixed in the plan and the coordinator refuses a plan whose tuple is not
exactly this one, field for field, under the `tuple` refusal of `validate_plan`. What
each field is and what a run records of it are declared once for the experiment, in
`determinism-matrix-Spec` section 6.1, and the values below are this probe's:

| Field | Value |
| --- | --- |
| artifact | `/opt/weaver/models/Qwen3-8B-Q8_0.gguf` |
| weights | sha256 `0cfbf745760f07a76ddeb358dd025a27f2e11d1ca9c9a4169a373d52990fe86e` |
| devices | `[0]` |
| context capacity | 12288 |
| max tokens per turn | 8192 |
| field depth | 200 |
| surprisal | elected |
| residual readout | not elected |
| identity | the `identity` string of olympus's `config-q8.json`, verbatim |
| seeds | 451234785645, 1156316220, 7, 1000003, 123456789, 987654321, 2718281828, 3141592653 |
| runs per seed | 2 |
| driver | 615.71.09 |

**Held means every load carries it and every reading is checked against it.** The
payload renders each job's declaration from the tuple, per `declaration`, with the
seed the job's own, the loop `basic_loop.py` from the job's stack, the operator's uid
as the gate's one allowed dialer, and a fresh trace sink per job. A re-feed's derived
declaration must name the served model and no other artifact and must carry the
tuple's context capacity, token cap and identity, and the seed its source free run
declared where the source is local or a seed the tuple admits where the source is an
external trace, per `holds_tuple`, under the `derived-artifact` and `derived-tuple`
refusals. Every
measured record must carry the tuple's weights hash and the job's seed, under
`weights-held` and `seed-held`, and a re-feed must carry them on both sides of the
comparison, under `source-weights-held`, `source-seed-held`, `replay-weights-held`
and `replay-seed-held`, because a comparison across two tuples is another experiment
under this one's name.

**The elected readings are derived from the tuple and not from a list.** A record is
sufficient when it carries one output token or more, a field entry per token at the
tuple's depth, and one value per token in every per-token series the tuple elects,
entropies always and surprisals because the tuple elects them, per `series` and
`enough`. A true election with no record key raises rather than going unread, so an
election added to the tuple cannot be forgotten by the sufficiency check and the
comparison both. `weaver-spu-Spec` section 6's rule, carrying charter section 13.12,
stands beneath this: elected surprisals render, and disagreement between elected
readings is a defect.

```graph
node: blackwell-probe-tuple-held-field-for-field
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-tuple-held-field-for-field

node: blackwell-probe-elected-series-from-the-tuple
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-elected-series-from-the-tuple
```

## 3. The legs, and the claims the code enforces

**The schedule is fixed and validated whole.** The plan holds exactly the legs
`TB0`, `TB-d` and `TB-k` in that order, every job identity unique and plain, every
job free or a re-feed on `B1` or `B2`. The control holds two free runs per seed, all
on `B1`, and one own re-feed per free run. A re-feed names a source that precedes it
in the schedule or a reviewed external trace with its run. The device leg holds only
re-feeds on `B1` from reviewed external traces, at least one from each of the
`ampere` and `ada` cells, each measuring a distinct trace and run, with no trace
shared between the cells, because a repeated selection or a shared trace would
complete the leg without measuring one of its cells. The kernel leg holds every `B1`
record as a re-feed on `B2`, or is empty only on the identity evidence of section 6.
The refusals are `arm-order`, `job-identities`, `job-types`, `control-schedule`,
`own-refeeds`, `source-order`, `device-sources`, `device-traces`,
`device-selections-distinct` and `kernel-schedule`.

**TB0, the control.** The claim: holding the seed reproduces on this card, and
changing it moves the draw and not the distribution. The prediction the code checks:
every same-seed pair is exact and emits the same text, every own re-feed is certified
and exact at every position, and every pair of distinct seeds, taken one run per seed
in the tuple's order, parts within the first twenty-four tokens. The falsifier stops
the leg where it
falls: after the operator has unloaded a free run whose earlier same-seed run it does
not match, under `pair-falsifier`, or an own re-feed that is not certified and exact,
under `own-refeed-falsifier`, and at the leg's assessment under `control-falsifier`
and `changed-seed-prediction`. A card that does not reproduce under itself cannot be
read against another, so the halt is the finding.

**TB-d, the device cell.** The claim: Blackwell moves the distribution from position
zero relative to Ampere and to Ada, as Ada moved it against Ampere in #511. The
prediction: each record re-fed through `B1` has per-position readings that differ from
the recorded ones, and the divergence is reported in the historical instrument's
input-plus-output coordinate with the output ordinal beside it. The falsifier: a re-feed
exact to the bit at every position. A falsifier of this leg is a result and not a halt:
the leg records it in the reading and completes, since a card whose arithmetic matches
another's is the finding this leg exists to make or unmake, and only the control's
falsifier stops the probe. The leg carries the driver confound of section 1 as a
qualifier on every reading.

**TB-k, the kernel leg.** If every executable section of `B1` and `B2` is identical by
section 6's verdict, the leg is recorded as the kernel held by executable identity
across the two toolchains and nothing runs. If sections differ, the claim is that the
differing kernels move the distribution on one card, the prediction is that a `B1`
record re-fed through `B2` departs at some position, and the falsifier is every record
re-feeding exact. As for the device leg, that falsifier is recorded and completes the
leg rather than halting it. `B2` also differs in its CUDA user-space libraries, and the
reading carries that as part of the kernel stack.

```graph
node: blackwell-probe-schedule-validated-whole
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-schedule-validated-whole

node: blackwell-probe-falsifier-halts-after-unload
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-falsifier-halts-after-unload
```

## 4. The order of operations

**One command, one state file, three seats.** The operator runs `next` and nothing else,
never under sudo, per `Order.operator`, and the payload refuses a `next` whose invoking
uid is not the plan's recorded operator, under its `operator` guard. The state file
`tb-state.json` carries the cursor over a schedule the plan determines: `provision`,
then for each leg `start`, and for each job `load`, `measure`, `unload` and `settle`,
then `finish`, and after the last leg `report` and `review`. Each step names its seat.
The operator owns `provision`, `load` and `unload`. The coding seat owns `start`,
`measure`, `settle`, `finish` and `report`. The review seat owns `review`, which is its
own edit of the state file under the coordinator's lock and never a command of this
program, its receipt naming the state's approval as every receipt does. Approval is no
step of the schedule: it is the review seat's record, snapshotted root-owned when the
operator runs `approve`, per section 5. A step out of order, by the wrong seat, or
already recorded is refused under `step-order`, `seat` and `not-repeated`, and every
step first re-verifies every earlier receipt against its recorded digest, and against
the approval it names, which must be the state's, a state holding none refusing it,
under `prior-success`, `prior-approval` and `prior-evidence`. **A free run's `measure`
receipt also holds its sink as it stood at the run's `turn.closed`**, the path, the
length of the prefix through that line and that prefix's digest, recorded by the driver
under the coordinator's lock as of 2026-09-26 (#679 item 1). A local re-feed's `load` is
handed that length and digest beside the plan, and refuses under `source-sink-recorded`
where the source run's receipt holds no well-formed sink at the path its job names.

**Approval gates every step and is not this program's to grant.** `next` waits while the
state records no approval. Once one is recorded, every step reads it from the root-owned
record the state's `approval` digest names and never from the state, per section 5, and
verifies that the record is root's and matches that digest, that it states a passed
review with the hold lifted, naming its seat and reference, that its artifact map covers
the plan and the ten staged files, the nine scripts and the suite, that every artifact
still hashes as recorded, that the plan snapshot parses from the bytes that matched the
approved digest, that the plan's file map is covered by the artifact map and agrees with
it, and that no halt is recorded, under `approval-digest`, `approval-custody`,
`approval-record`, `approval-coverage`, `artifact-hashes`, `plan-snapshot`,
`manifest-coverage`, `manifest-hashes` and `halt`. Staging creates the state with no
approval and refuses to overwrite an existing state, so approval is never manufactured.

**The driver blocks, and the coordinator holds the lock only while it decides.** An
leg runs in one driver invocation that takes a lease bound to its process start time,
per `live`, and the coding-seat steps are refused to any process but the lease
holder under `driver-owner`. Each wait is bounded at four hours, verifies the driver's
own live lease, and runs the full approval verification only when the state bytes
have moved and always before returning, so an idle driver does not hash the deposit
every second under the lock the operator's `next` needs, under `wait-owner`,
`wait-order` and `wait-deadline`. A wait that returns, and every record the coding seat
makes, answers the receipts as they then stand, which is what the driver reads evidence
against, per section 7. A falsified control is judged after the operator's unload and
before the next load becomes due, so the halt lands with the card unloaded.

**A halt is evidence.** A refusal records its reason and a transcript in the state and
never advances the cursor. A timeout, a dead driver, a refused payload or an
insufficient measurement leaves the cursor where it was. No refusal is bypassed by
editing the state, and partial resources left by an interrupted step are evidence the
review seat rules on with a bounded recovery step, since the payload holds no general
root shell and no arbitrary command.

```graph
node: blackwell-probe-one-command-one-seat-per-step
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-one-command-one-seat-per-step

node: blackwell-probe-approval-gates-every-step
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-approval-gates-every-step

node: blackwell-probe-wait-verifies-when-the-state-moves
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-wait-verifies-when-the-state-moves

node: blackwell-probe-halt-is-evidence
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-halt-is-evidence
```

## 5. The privilege boundary, and custody

**Root runs one hand-installed program and no bytes the operator's uid can write.**
Every privileged step enters `tb_root.py`, installed once by hand at
`/usr/local/libexec/weaver-tb/tb-root`, root-owned, mode 0755, the one path the probe's
sudoers entry names, on the ruling of 2026-09-27,
https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-5852640576. The
coordinator runs `sudo <that path> run <step> <approval digest>` with standard input
closed and the transcript captured, per `payload`, and hands root no bytes and no path.
The root program finds the approval that digest names complete in root custody, every
file of it checked, and executes the approval's root-owned copy of the reviewed payload
with `python3 -I`, under `known-verb`, `run-arguments`, `approval-digest`,
`approval-custody`, `approval-complete` and `approval-record`. The payload parses the
one plan snapshot beside it whose bytes match the approved digest, under `plan-hash`,
before anything else. The reason is stated where it binds: a file the operator's uid can
rename, any process of that uid can swap between a check and root's open, and a program
that checks its own bytes proves nothing, since a swapped program skips the check
(#709's fourth pass). The root program and the payload refuse to run as anything but
root, the payload refuses a plan not naming the isolated root and the `bravo` agent, and
an invoking uid that is not the plan's recorded operator is refused, by the payload at
every step and by the root program at `approve`, under `root-program`, `root-payload`,
`fixed-root-agent` and `operator`. The coordinator and the driver refuse to run as root,
under `operator-not-root` and `driver-not-root`.

**Approval is in root custody, by one privileged step, `approve`**, on the ruling of
2026-09-26 on #698 (679.5). The review seat publishes its review as a record: the
status, the hold, the seat, the reference, the plan's path, the payload's path and the
artifact map, every path with its sha256. The operator runs `tb-operator.sh approve
<record>`. The coordinator hashes the record once and runs the root program's `approve`
with the record's path and that digest. Root reads the record once, refusing a link,
holds it to the coordinator's digest, and reads every artifact it names once, as data,
each held to its digest before the first write: nothing it reads is executed. It copies
the reviewed payload and the plan into a directory under `/var/lib/weaver-tb/approval/`,
writes `approval.json` (0600) and `approval.pub.json` (0644), the same bytes, names the
directory by their digest, and prints it. A refusal leaves nothing behind, under
`approve-arguments`, `approval-record`, `approval-record-digest`, `approval-root`,
`root-chain-custody`, `approval-artifacts` and `approval-new`. **The state keeps that
digest and nothing else about approval**, as `approval`, a pointer the coordinator
records only once the public copy it names is root's and matches it and the record
digest taken before sudo, the record never read again after root has run, under
`approve-exit`, `approve-printed` and `approve-record`. **A new approval means a new
state**: the pointer is set once, a second `approve` against a state holding one refuses
before root is asked, under `one-approval-per-state`, and every receipt records the
approval it ran under, so no run carries evidence of two. The hold and the review's
fields are the record's. `halt` and `cursor` stay the operator's by design: a halt is
the operator's right, and the cursor selects a step whose every earlier receipt is
verified.

**Every handoff across sudo answers a death between its two sides**, on #709's third
pass. An interrupted step is never silently resumed, and adopting a finished, verified
result is not a resume. **`approve` is adopted on retry**: a coordinator that dies after
root commits and before the state is written leaves an approval the state does not name,
and the retry hands root the same record, which root finds complete and answers with its
digest, writing nothing. Two complete approvals of one record refuse, under
`approval-once`. A directory a crash left mid-write, or anything in the approvals that
is not a complete approval, is never adopted and refuses by name, under
`approval-complete`. **Complete means every file checked**, on #709's fourth pass: the
directory named by its record's digest and locked, holding the four files and nothing
else, each a regular file of one name, locked, at its written mode, the public copy the
private record's bytes, and the plan and payload copies hashing as the record says.
**The scheduled steps refuse rather than repeat**: a `provision` retried over its own
partial or finished work refuses under `fresh-install-root`, a `load` whose sink stands
refuses under `fresh-sink` rather than loading the run twice, and an `unload`
re-measures its whole claim, the agent unloaded and the interlock clear, from nothing it
recorded before. A coordinator that survives the failure records a halt, and every later
step refuses under `halt` while it stands.

**The trust anchor is the operator's hash check of the root program at install time**,
on the ruling of 2026-09-27. The operator installs `tb_root.py` once, by hand, with
`sudo install -o root -g root -m 0755`, and compares the installed copy's sha256 by eye
against the file at the merged commit, per the README. Every privileged step goes
through that one program, and its bytes are fixed once installed. The operator at the
sudo prompt was the anchor before, and it now sits where the bytes being trusted are
fixed. The snapshot closes the window between approval and `next`, the one the security
review on #683 found, where any operator-uid process could rewrite what was approved
before root read it. **The window before approval stays open**: a process of that uid
can still change what the review seat is about to approve, and that closes only when the
review seat has an identity of its own, another uid or another box, and signs its
record. The signed review record is owed on #698, and the record's shape is kept so a
signature slots in without moving the consumer.

```graph
node: blackwell-probe-approval-in-root-custody
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-approval-in-root-custody
```

**No privileged step acts on a copy of a fact held by another party without checking
it against evidence it verified itself**, as a rule of this probe's custody from
2026-09-26 (#690 C2.11, the operator's ruling of that date). A copy is a second
statement of a fact whose first statement is evidence: a local re-feed's sink length
and digest stand in the state file and in the source run's measure result, and the
coordinator hands root the state's copy only after reading the result once, holding
its bytes to the receipt's digest, and finding the result's own record equal to it,
under `source-sink-recorded`. **The rule is substrate-neutral**: a state store that
moved from a file on this box to a service across a network would change nothing on
the consuming side but the address, the copy still arriving from another party and
still checked against evidence the consumer verifies. **Where no such evidence exists
the fact is named rather than trusted**: the halt, the cursor and each receipt's status
are read by shape or equality and acted on, and they rest on the state file's owner.
The halt and the cursor do so by design, per the approval paragraph above, and each
receipt's bytes are held to their recorded digest before its status is read.

**Nothing privileged reads an operator-owned input twice.** A check on a path
followed by a second read of the path binds nothing, so every operator-owned input
is read once into a root-owned private file whose bytes are verified against the
recorded digest, and only that file is used afterwards: the served model and a
re-feed's external source trace, each under `snapshot-hash`, every file the plan
names having first been checked against its manifest digest under
`source-file-hash`. The re-feed
then cuts the plan's source run from that snapshot into a second private file, since
`derive` refuses a record holding two runs, and `derive` and `preload` both receive
that one file, under `source-run-selected`. The driver likewise hashes and compiles
one read of each reader and hashes and parses one read of each source trace, under
`reader-approved` and `source-trace`.

**Everything root serves from is locked when made and verified before it is trusted.**
Provisioning refuses a link anywhere in a source stack before its first write, under
`stack-no-symlinks`, and requires every stack file to be in the plan's file map, under
`stack-file-coverage`. It copies each stack by bytes, then locks the installed tree with
the root included, since the copy preserves the source root's mode and a walk of
descendants never reaches the root, and it locks the isolated root and every directory
it makes beneath it as it makes them, since a directory's mode is masked by the umask.
The installed copy must then hold exactly the reviewed files, no link, every entry owned
by the payload's user with no group or world write, under `installed-no-symlinks`,
`installed-stack-custody`, `installed-stack-coverage` and `installed-stack-hash`, and
every later step checks the served directories again under `served-directory-custody`.
The served model is a regular file with one name, owned by the payload's user, not group
or world writable, in a directory held the same way, whether it was found or freshly
installed, under `existing-model-custody`, `new-model-custody` and
`installed-model-custody`, and its bytes are the tuple's, under `model-source`,
`existing-model` and `installed-model`. Every precondition a later command asserts is
held before the first write, since an interrupted provision otherwise leaves the root
standing and every retry refusing under `fresh-install-root`: the account and group, the
operator's group, the model's chain and the root's own chain, under `no-bravo-account`,
`no-bravo-group`, `operator-group`, `model-chain-custody` and `root-chain-custody`.
Writes beneath a held root are made through link-refusing opens behind the named check,
and the remaining edge, an ancestor changing owner or mode during provisioning, needs
root and is outside the adversary this document names.

**The installation is isolated and refuses to adopt.** Provisioning uses only
`/var/lib/weaver-tb`, its own two admin roots and the `weaver-bravo` account and
group, and refuses rather than adopting custody: an existing account, and a root that
is not exactly as `approve` left it, standing, locked and holding `approval/` and
nothing else, under `fresh-install-root`. It installs the model at the historical
absolute artifact path or checks an identical existing file and never overwrites a
different one, and changes nothing of `m1`, `karl`, their declarations or
`/etc/weaver/admin`. The sinks directory is root-owned, its group the operator's own,
mode `2750`, so the operator reads evidence and no member writes outside its own trace.

**Every load stands on an interlock.** A `bravo` load refuses a non-inactive `m1`
unit, an unreadable unit status, a remaining `m1` coordination door, or any process
under `m1`'s uid, under `m1-inactive`, `m1-state-readable`, `m1-no-door` and
`m1-no-process`. It checks the device and driver tuple, that the CUDA engine library
`libggml-cuda.so` resolves every dependency, and that the CUDA runtime resolves from
the stack's own library directory
and nowhere else, under `gpu-tuple`, `resolved-libraries` and `cuda-local`. A
diagnostic load waits for the preload door to stand and for the loader to answer,
under `preload-door` and `diagnostic-load`, and an admin answer is read for its content
and never for its exit status alone, under `admin-answer`. **The interlock is read again
when the measurement closes and at the unload**, as of 2026-09-26 (#683 thread 49): the
driver reads the same four facts without privilege and refuses the reading under
`m1-unloaded-at-close`, recording the reading in the result, and the unload reads them
after `bravo` is unloaded and refuses the step under `m1-unloaded-at-unload`, printing
the reading to its transcript, so a reading taken with `m1` standing at any point the
probe can see is never settled. A fact that cannot be read is recorded as unread and
never as clear, any failure to read a fact mapping to unread, and a `/proc` mounted with
`hidepid` counting as an unread process scan for an unprivileged reader, since it hides
other users' processes without an error. **The edge is the window between two
readings**: an agent that starts and stops wholly between the load and the close, or
between the close and the unload, is seen by none of them, and the admin guards per
agent. The README states the operator's rule that no other agent is loaded while a leg
runs, and that rule is what covers the window.

```graph
node: blackwell-probe-root-runs-no-operator-bytes
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-root-runs-no-operator-bytes

node: blackwell-probe-operator-input-read-once
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-operator-input-read-once

node: blackwell-probe-served-tree-locked-and-verified
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-served-tree-locked-and-verified

node: blackwell-probe-model-in-custody-on-both-paths
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-model-in-custody-on-both-paths

node: blackwell-probe-installation-refuses-to-adopt
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-installation-refuses-to-adopt

node: blackwell-probe-load-stands-on-the-interlock
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-load-stands-on-the-interlock
```

## 6. Executable identity

**The inventory covers every file a load can execute from.** The served
directories of a stack are one constant, `STACK_ROOTS`, held by the payload and
imported by the inventory: `bin`, `engine-lib` and `cuda-lib`, the last two being
what the payload puts on the library path. The inventory walks every file beneath
them, records ELF files by header, program headers and every section with its hash,
records every other file by whole-file hash, and refuses a link, since a stack is
copied by bytes and a link would vouch for bytes nobody read. It also records every
extracted cubin and PTX member by size and hash, with the cubins' sections. A test
derives the served set from the payload's own environment and configured binaries and
pins it to the constant, so a directory served from outside the inventoried roots is
a test failure and not silent drift.

**The comparison takes `B1` then `B2` and nothing else.** It refuses any other pair,
including one inventory twice, and any inventory with no hosts, no cubins or no PTX,
since an empty scope makes every verdict vacuous. Its report names the two inventories
it read by path and digest, and it records per host file whether the file is
byte-identical and whether each recorded section matches, and per CUDA architecture
group how many members match by container and by code section and which members
changed or went missing, so a container that differs while its code sections match
is told apart from a kernel that changed.

**The verdict is conservative and bound to the stacks it judged.** Identity holds
only when every recorded section, header and CUDA member matches and every host file
is byte-identical. The entry point and segment permissions live outside every
section, so equal sections do not make equal hosts, and an identity verdict cannot be
inferred from equal file counts or `.text` alone. An emptied kernel leg names the
report that empties it, hashed in the plan's file map, and approval reads that report
once against its digest, requires it to be the comparison's verdict on `B1` against
`B2` and true, requires each inventory it names to be a reviewed artifact at the
digest the report records, and requires the inventoried file hashes to equal the
approved hashes of every file under that stack exactly, under `identity-evidence`,
`identity-inputs` and `identity-binds-stacks`. A report over stacks that have since
changed, or over an inventory that missed a reviewed file, empties nothing.

```graph
node: blackwell-probe-inventory-covers-every-served-file
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-inventory-covers-every-served-file

node: blackwell-probe-comparison-takes-b1-then-b2
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-comparison-takes-b1-then-b2

node: blackwell-probe-identity-bound-to-approved-stacks
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-identity-bound-to-approved-stacks
```

## 7. Measurement and assessment

**A free run is one gate turn, one measurement, one fresh trace.** The driver dials
the gate with the essay prompt, requires an answered close naming a run, waits for the
turn's close in the trace, and requires exactly one measurement in that run, under
`gate-answer` and `single-turn`. The record is extracted by the historical readers,
compiled from the hashed bytes the manifest approved and never from cached bytecode,
and must be sufficient per section 2. Each trace has a fresh directory, so a retry
cannot truncate or relabel earlier evidence.

**A re-feed is one completed replay against one verified source.** The source record is
the earlier free run's record, read once and parsed only after its bytes match the
digest of that run's `measure` receipt, under `receipt-present` and `receipt-digest`, or
the reviewed external trace's selected run, read once, hashed and parsed, with exactly
one measurement, under `source-trace` and `source-measurement`. The replay must
complete, certified or diverged, and carry exactly one measurement, under
`replay-completed`, `single-replay` and `replay-measurement`. Only the control's own
re-feeds must be certified, per section 3, since a diverged replay is what the device
and kernel legs predict. Exactness is the output tokens equal, every elected per-token
series equal to the bit, and the field equal at every position, per `exact`, the input
length included: the extractor carries the input as a count, so the length is held
between source and replay under `input-held`, the comparator's report of a divergence
inside the input is refused under `divergence-in-input` rather than read as a device or
kernel effect, and token-by-token identity of the input is not a record the instrument
carries, and the reading is the historical instrument's divergence coordinate with its
ordinal. **Every result the driver reads, it reads against its receipt**, as of
2026-09-26 (#679 item 2, #683 thread 14): the free readings a re-feed takes, the record
a `settle` judges and the records a leg's assessment reads each come from the receipts
the last wait or record answered, so a file substituted after the coordinator verified
it is refused where it is read. **A local re-feed replays its source sink as it stood at
the source run's close**: the driver cuts the sink at that run's `turn.closed` line from
one read, refusing under `sink-closed` where the line is not there, and records the
prefix per section 4, and the payload freezes exactly that many bytes and verifies them
against the recorded digest under `source-sink-given` and `snapshot-hash`, so what the
unload appended after the close is outside the replay. **The shape refusals precede the
first write and the content refusal follows it**: a recorded sink whose length is not a
positive integer or whose digest is not 64 lowercase hex is refused by the coordinator
under `source-sink-recorded` before root is invoked, and again by the payload under
`source-sink-given` before it creates any directory, so a corrected state can retry the
job. A well-formed digest the sink no longer matches is refused under `snapshot-hash`
after the job's directories stand, the snapshot needing its own, and the rule that a run
is never reused leaves them as evidence for the review seat.

**Assessment is per leg, and the control's falsifiers halt before it.** The control's
report carries every same-seed pair with its equality and reading, every own re-feed
with its exactness and certification, the first difference for every pair of distinct
seeds taken one run per seed in the tuple's order, and the two verdicts `control_passed`
and `changed_seed_prediction`. The device and kernel legs' reports carry each re-feed's
reading and, for the kernel leg, whether identity emptied it. Each leg's result is
written whole and recorded as that leg's `finish` receipt, and the report step runs only
after every earlier receipt, each `finish` included, stands with its digest intact.

```graph
node: blackwell-probe-refeed-completes-against-a-verified-source
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-refeed-completes-against-a-verified-source

node: blackwell-probe-exactness-is-bitwise-over-elected-readings
kind: assertion
tag: perturbation

edge: asserts
from: blackwell-probe
to: blackwell-probe-exactness-is-bitwise-over-elected-readings
```

## 8. The refusals

Every guard is named, and its name is the reason in the halt. Three of the payload's
names arrive with the citations commit on #683, where they had raised as plain errors:
`no-bravo-account` for an existing `bravo` account, `known-step` for a verb that is
neither a load nor an unload, and `command-exit` for a privileged command exiting
nonzero, which prints the command's output to the transcript first. They are grouped
here by the module that raises them, and section 9 says how each is watched. The
coordinator's: `schema`, `agent`, `stacks-distinct`, `isolated-root`, `tuple`,
`rulings`, `arm-order`, `job-identities`, `job-types`, `control-schedule`,
`own-refeeds`, `source-order`, `device-sources`, `device-traces`,
`device-selections-distinct`, `kernel-schedule`, `approval-digest`, `approval-custody`,
`approval-record`, `approval-coverage`, `artifact-hashes`, `halt`, `plan-snapshot`,
`manifest-coverage`, `manifest-hashes`, `identity-evidence`, `identity-inputs`,
`identity-binds-stacks`, `identity-recomputed`, `cursor`, `prior-success`,
`prior-approval`, `prior-evidence`, `step-order`, `seat`, `not-repeated`, `driver-live`,
`driver-owner`, `no-live-driver`, `report-evidence`, `payload-exit`, `payload-receipt`,
`wait-owner`, `wait-order`, `wait-deadline`, `source-sink-recorded`,
`one-approval-per-state`, `approve-exit`, `approve-printed`, `approve-record`,
`approve-record-named`, `no-record-outside-approve` and `operator-not-root`. The root
program's: `root-program`, `known-verb`, `approve-arguments`, `run-arguments`,
`approval-record`, `approval-record-digest`, `approval-root`, `approval-complete`,
`approval-once`, `root-chain-custody`, `approval-artifacts`, `fixed-root-agent`,
`operator`, `approval-new`, `approval-digest` and `approval-custody`. The payload's:
`root-payload`, `fresh-sink`, `approval-digest`, `approval-custody`, `approval-record`,
`plan-hash`, `fixed-root-agent`, `operator`, `source-file-hash`, `job-found`,
`model-source`, `existing-model-custody`, `existing-model`, `stack-no-symlinks`,
`stack-libraries`, `stack-file-coverage`, `fresh-install-root`,
`no-symlink-destination`, `snapshot-hash`, `new-model-custody`, `installed-no-symlinks`,
`installed-stack-custody`, `installed-stack-coverage`, `installed-stack-hash`,
`installation-plan`, `installed-model-custody`, `served-directory-custody`,
`installed-model`, `m1-inactive`, `m1-state-readable`, `m1-no-door`, `m1-no-process`,
`gpu-tuple`, `resolved-libraries`, `cuda-local`, `source-run-selected`,
`derived-artifact`, `derived-tuple`, `preload-door`, `diagnostic-load`, `admin-answer`,
`no-bravo-account`, `no-bravo-group`, `operator-group`, `model-chain-custody`,
`root-chain-custody`, `source-sink-given`, `m1-unloaded-at-unload`, `known-step` and
`command-exit`. The driver's: `driver-not-root`, `reader-approved`, `fresh-arm`,
`gate-answer`, `single-turn`, `nonempty-measurement`, `field-depth`, `seed-held`,
`weights-held`, `source-trace`, `source-measurement`, `source-weights-held`,
`source-seed-held`, `replay-completed`, `single-replay`, `replay-measurement`,
`request-absent`, `request-duplicated`, `output-absent`, `output-duplicated`,
`field-duplicated`, `field-beyond-output`, `replay-weights-held`, `replay-seed-held`,
`input-held`, `divergence-in-input`, `pair-count`, `pair-falsifier`,
`own-refeed-falsifier`, `control-falsifier`, `changed-seed-prediction`, `sink-closed`,
`receipt-present`, `receipt-digest`, `m1-unloaded-at-close` and `report-path`. The
inventory raises its refusals as errors on the command line, since it runs before any
plan exists.

**The rulings are refusals too.** A plan whose `hold_lifted`, `cuda_provenance` or
`control_count` ruling is empty is refused under `rulings`, and each names the URL
of the decision rather than a placeholder. The `control_count` ruling accepts eight
Q8_0 pairs and sixteen own re-feeds for this schedule, and a larger schedule changes
the validator and its tests in a reviewed rework first.

## 9. What is enforced, and by which instrument

**Two instruments, run unprivileged, and every guard is watched by both.** The suite
`test_tb.py` runs against temporary files, a temporary Unix socket and stubbed admin,
gate and device calls, and makes no change to any installed stack. The mutation run
`perturb.py` copies the scripts to a temporary directory, refuses unless the
unmodified suite passes there, then removes and inverts every named guard of section 8
in turn, and makes each exception handler of the interlock's reading catch nothing, and
requires each run to fail, recording the failing output, and kills with a process-group
timeout any mutation that destroys a wait bound. A guard the mutation run cannot fail is
a guard that enforces nothing, and the count is a reading taken at an act and never a
fact this document holds: the instrument is the run, and an act states the numbers it
got in its own body, as #683's does.

**Every stub is built from a capture, never from what the code expects.** Each
constant in `golden.py` is a real tool's output captured unprivileged on this box, a
line copied from a real trace, or a shape read from the tool's source at `e69916a`,
with its command or file and lines and a sha256 beside it. The rule was earned:
a stub written to its own code's assumption is how a quoted artifact in `derive`'s
declaration reached review as a refusal every re-feed would have hit on the device.
This claim is review's and the tag says what was not bought rather than that
nothing could be: a test that walks every constant in `golden.py` and refuses one
without a source line and a digest beside it is buyable, and this act declines it
because the constants are few and each is read at review, which is the instrument
named.

**The enforcement table.** Every record this document declares, with the instrument
that holds it. A perturbation row is held by `perturb.py` removing and inverting the
guards the clause names and by the suite's test of the same name.

| Claim | Instrument |
| --- | --- |
| `blackwell-probe-tuple-held-field-for-field` | perturbation, `tuple`, `derived-tuple`, `weights-held`, `seed-held` and their re-feed siblings |
| `blackwell-probe-elected-series-from-the-tuple` | perturbation, `nonempty-measurement`, `field-depth`, `exact` on surprisals |
| `blackwell-probe-schedule-validated-whole` | perturbation, the ten schedule guards of `validate_plan` and `stacks-distinct`, the two stacks resolved, distinct and disjoint |
| `blackwell-probe-falsifier-halts-after-unload` | perturbation, `pair-falsifier`, `own-refeed-falsifier`, `control-falsifier`, `changed-seed-prediction` |
| `blackwell-probe-one-command-one-seat-per-step` | perturbation, `step-order`, `seat`, `not-repeated`, `driver-owner`, `operator-not-root`, `driver-not-root` |
| `blackwell-probe-approval-gates-every-step` | perturbation, `approval-digest`, `approval-custody`, `approval-record`, `approval-coverage`, `artifact-hashes`, `plan-snapshot`, `manifest-coverage`, `manifest-hashes`, `halt` |
| `blackwell-probe-approval-in-root-custody` | perturbation, `one-approval-per-state`, `prior-approval`, `approval-record-digest`, `approval-complete`, the interrupted-approve test, the every-file test, `approval-record`, `approval-root`, `approval-once`, `approval-artifacts`, `approval-new`, `approval-digest`, `approval-custody`, `approve-arguments`, `approve-exit`, `approve-printed`, `approve-record`, the tampered-artifact, flipped-state, replaced-payload and second-approve tests |
| `blackwell-probe-wait-verifies-when-the-state-moves` | perturbation, `wait-owner`, `wait-order`, `wait-deadline` and the state-moves test |
| `blackwell-probe-halt-is-evidence` | perturbation, `prior-success`, `prior-approval`, `prior-evidence`, `payload-exit`, `payload-receipt`, `cursor`, `fresh-sink` |
| `blackwell-probe-root-runs-no-operator-bytes` | perturbation, `root-program`, `known-verb`, `run-arguments`, `approval-complete`, `plan-hash`, `root-payload`, `fixed-root-agent`, `operator`, the no-operator-bytes and root-copy tests |
| `blackwell-probe-operator-input-read-once` | perturbation, `snapshot-hash`, `source-file-hash`, `source-run-selected`, `reader-approved`, `source-trace`, `receipt-present`, `receipt-digest` |
| `blackwell-probe-served-tree-locked-and-verified` | perturbation, `stack-no-symlinks`, `stack-file-coverage`, `installed-no-symlinks`, `installed-stack-custody`, `installed-stack-coverage`, `installed-stack-hash`, `served-directory-custody`, `root-chain-custody` |
| `blackwell-probe-model-in-custody-on-both-paths` | perturbation, `existing-model-custody`, `new-model-custody`, `installed-model-custody`, `model-source`, `existing-model`, `installed-model`, `model-chain-custody` |
| `blackwell-probe-installation-refuses-to-adopt` | perturbation, `fresh-install-root` and the approval-only-root test, `no-bravo-account`, `no-bravo-group`, `operator-group`, `no-symlink-destination`, `installation-plan` |
| `blackwell-probe-load-stands-on-the-interlock` | perturbation, `m1-inactive`, `m1-state-readable`, `m1-no-door`, `m1-no-process`, `m1-unloaded-at-close`, `m1-unloaded-at-unload`, `gpu-tuple`, `resolved-libraries`, `cuda-local`, `preload-door`, `diagnostic-load`, `admin-answer` |
| `blackwell-probe-inventory-covers-every-served-file` | perturbation, the inventory tests and the pin of `STACK_ROOTS` |
| `blackwell-probe-comparison-takes-b1-then-b2` | perturbation, `compare`'s refusals and the scope test |
| `blackwell-probe-identity-bound-to-approved-stacks` | perturbation, `kernel-schedule`, `identity-evidence`, `identity-inputs`, `identity-binds-stacks`, `identity-recomputed` |
| `blackwell-probe-refeed-completes-against-a-verified-source` | perturbation, `source-sink-recorded`, `sink-closed`, `source-sink-given`, `source-measurement`, `replay-completed`, `single-replay`, `replay-measurement`, `gate-answer`, `single-turn`, and `well_formed`'s `request-absent`, `request-duplicated`, `output-absent`, `output-duplicated`, `field-duplicated`, `field-beyond-output` on every path |
| `blackwell-probe-exactness-is-bitwise-over-elected-readings` | perturbation, the `exact` tests with the empty, absent and one-bit cases, and `input-held`, `divergence-in-input` on the re-feed path, with the input length in `exact` |
| `blackwell-probe-stubs-are-captures` | review, the citations beside each `golden.py` constant |

**What the instruments cannot buy, named.** No test here touches the card, loads a
model, or runs as root, so `gpu-tuple`, `cuda-local`, `diagnostic-load` and the
provisioning path are watched against stubs and captured shapes and are proven only
by the first held run under the operator's own sequence. The window before approval of
section 5, an operator-uid process changing what the review seat is about to approve,
has no instrument until the review seat has an identity of its own, and this document
says so rather than claiming otherwise.

```graph
node: blackwell-probe-stubs-are-captures
kind: assertion
tag: review

edge: asserts
from: blackwell-probe
to: blackwell-probe-stubs-are-captures
```

## 10. What this document does not carry

The results of any leg, which are #679's evidence and the report's. The re-staging of
the two stacks without links and with their CUDA libraries (679.4), and the signed
review record owed on #698. The `cuda_provenance` ruling is made, on 2026-09-26, and the
re-staged plan carries its URL,
https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-5851860887. The
evidence digests passed from the coordinator's state into the driver, design item B
there, are held in section 7 since 2026-09-26. The historical instrument's readers and
gate client, which are #516's and are cited by hash rather than restated. And the
question this document was written to answer, whether operator tooling under `deploy/`
answers to a document in this corpus: it does, and this is the document.