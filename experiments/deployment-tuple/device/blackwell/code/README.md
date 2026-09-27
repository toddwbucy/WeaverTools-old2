# TB preparation (issue #679)

**The authority is `blackwell-probe-Spec`** (`../blackwell-probe-Spec.md`, the
Blackwell probe's Spec, one measurement under the deployment tuple's device arm);
this file is the run instructions. Every unit here
cites the Spec's assertion records it holds an instrument for, in its header.

This is the Blackwell probe's operator coordinator and blocking driver. It is
preparation, not a measurement result. The operator's narrowed HOLD permits this
code and the build comparison. No probe arm, privileged operator step or further
Olympus copy is permitted while that HOLD stands. The designated seat reviews
this draft and supplies approval only after the HOLD lifts.

The implementation adapts W4a's flock, atomic-state, process-start-time lease,
private payload, transcript receipt and best-effort notice mechanisms. It does
not restore the retired experiment tree to the repository. The historical
measurement functions come from a local extraction of
`a4f81d26f9c50c82681197d21126c38709936698` (the #516 instrument):

```
git archive -o /tmp/tb-probe-source.tar a4f81d26f9c50c82681197d21126c38709936698 experiments/weaver-probe experiments/cross-precision-repro
```

Extract that archive into the deposit's `instrument/` directory. Every source
file there is in the approval manifest. The new driver compiles the hashed
reader source directly, ignoring cached bytecode. It uses the old readers and
gate client, never the old driver's sudo/admin verbs. Diagnostic divergence is
reported in that historical binary's input-plus-output coordinate, with output
ordinal beside it; do not substitute a current replay binary into this stack.

## Stage, then keep held

Run the nonprivileged staging command once, supplying local absolute paths:

```
python3 experiments/deployment-tuple/device/blackwell/code/prepare.py --handoffs /path/to/handoffs --deposit /path/to/blackwell-deposit
```

It creates `handoffs/tb/`, `handoffs/tb-evidence/tb-plan.json`,
`tb-state.json`, and a manifest of the staged files. It refuses to overwrite
existing staging or state. The state starts with no approval, and it never
manufactures one. Approval is the review seat's record, published after the
rulings are filled, and the operator's `approve` of it, below. The staged
operator command is:

```
bash handoffs/tb/tb-operator.sh next
```

Do not invoke that command on this installation during HOLD. Tests invoke it
only against disposable held fixtures. Named commands such as `load:JOB` and
`unload:JOB` pass the same ordering and approval checks as `next`.

The staged plan deliberately remains incomplete where #679 has unresolved
inputs. Before review, the coding seat must fill and hash the historical
Ampere/Ada source traces, both CUDA library directories, and the rulings. Do not
put an arbitrary nonempty placeholder in a ruling field. Each is the URL of the
actual decision. `cuda_provenance` stays unset until the re-staging, which fills
it with the ruling of 2026-09-26,
https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-5851860887.
`control_count` must explicitly accept eight Q8_0 pairs and all
16 own-record re-feeds for this schedule. If the operator chooses more pairs,
change the schedule validator and tests in a reviewed rework first. No optional
BF16 rung is silently added. The kernel schedule contains all 16 B1 records;
it may be emptied only with `executable_identity: true` and an `identity_report`
naming the section comparison, hashed in `files`. Approval reads that report
once and refuses unless it is `sections.py compare`'s verdict on B1 against B2
and the verdict is true. The current comparison does not permit that.

`TB-d` jobs identify the source cell (`ampere` or `ada`), source trace and source
run. All source records selected by the ruling must be listed, not one convenient
representative. Their full content hashes, and both original instrument files,
belong in `files`. The plan's file map covers every stack input, including CUDA
libraries and model. The review artifact map covers every such file, the plan,
and the seven scripts and the test suite. The coordinator refuses missing
coverage, changed artifacts, changed receipts or a recorded refusal.

## Operator boundary and order

Only the operator runs `next`, as the recorded operator uid, without wrapping it
in sudo. The coordinator requests sudo internally, and **sudo runs one program
and nothing else**: `tb_root.py`, installed once by hand at
`/usr/local/libexec/weaver-tb/tb-root`, on the ruling of 2026-09-27,
https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-5852640576. A
step runs as `sudo /usr/local/libexec/weaver-tb/tb-root run <step> <approval
digest>` with stdin closed and a transcript captured. The root program finds
that approval complete, every file of it checked, and executes the approval's
root-owned copy of the reviewed payload with `python3 -I`. Root is never handed
bytes or a path the operator's UID can write: a file that UID can rename, any
process of that UID can swap between a check and root's open, and a program that
checks itself proves nothing, since the swapped program skips the check.

**Approval is in root custody**, on the ruling of 2026-09-26,
https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-5851860966. The
operator runs `bash handoffs/tb/tb-operator.sh approve <record>` on the review
seat's published record. The coordinator hashes the record once and runs `sudo
/usr/local/libexec/weaver-tb/tb-root approve <record> <record sha256>`. Root
holds its read of the record to that digest, reads every artifact it names once,
as data, checks each digest before its first write, copies the reviewed payload
and plan root-owned under `/var/lib/weaver-tb/approval/<digest>/`, writes
`approval.json` (0600) and `approval.pub.json` (0644), and prints the digest. It
leaves nothing on any refusal. A second approve of the same record adopts the
approval root already made and writes nothing, so a coordinator that died after
root committed recovers by running `approve` again. Anything in the approvals
that is not a complete approval refuses by name. The state keeps only that
digest, as `approval`. The payload parses the root-owned plan copy beside it.
The coordinator reads the public copy and takes the hold and the review's fields
from it, never from the state.

**The trust anchor is the operator's hash check of the root program at install
time**, the one program everything privileged goes through. The snapshot closes
the window between approval and `next` (#683 thread 24). The window before
approval closes only once the review seat has an identity of its own and signs
its record, owed on #698. No sudo is run by the probe driver. Notification
failure never changes a successful step.

### Installing the root program, once

The probe's sudoers entry names the installed path and nothing else. No
`python3` entry remains, and no `-c` form is admitted:

```
OPERATOR ALL=(root) /usr/local/libexec/weaver-tb/tb-root
```

Install it from the merge that last changed `tb_root.py`, then check the
installed copy, which only root can change, against the file at that commit.
Compare the two digests by eye. They must be identical.

```
sudo install -d -o root -g root -m 0755 /usr/local/libexec/weaver-tb
sudo install -o root -g root -m 0755 handoffs/tb/tb_root.py \
  /usr/local/libexec/weaver-tb/tb-root
sudo sha256sum /usr/local/libexec/weaver-tb/tb-root
git show MERGE:experiments/deployment-tuple/device/blackwell/code/tb_root.py \
  | sha256sum
```

`MERGE` is that merge commit. Hashing the installed copy rather than the staged
one leaves no window between the check and the install, since a process of the
operator's UID can swap the staged file but not the installed one. If the
digests differ, remove the installed copy with `sudo rm` and stop. A later merge
that changes `tb_root.py` is installed and checked the same way. Until the
program is installed, every privileged step fails at sudo and nothing is run.

Provisioning refuses a link anywhere in a stack before its first write, since a
stack is copied by bytes, and each installed stack must then hold exactly the
reviewed files with no link, which every later step checks again.

**Nothing privileged reads an operator-owned input twice.** A check on a path
followed by a second read of that path binds nothing, so every such input is
read once into a root-owned private file whose own bytes are verified against
the recorded digest, and only that file is used afterwards: the installed model,
and a re-feed's source trace. A re-feed then cuts the plan's `source_run` from
that snapshot into a second private file, because `derive` refuses a record
holding two runs, and `derive` and `preload` both receive that one file. The
driver likewise hashes and compiles one read of each reader, and hashes and
parses one read of each source trace.

The sequence is provision, then each arm's start, and for each job:

1. Operator load (a re-feed load derives, starts load, preloads concurrently,
   then waits for load, because diagnostic entry waits for the seal).
2. Coding-seat measurement, in the same still-running arm invocation.
3. Operator unload, verifying the unloaded state.
4. Coding-seat settlement of that result before the next load becomes due.

Finally the driver assesses and finishes the arm. The next arm requires a new
driver invocation. Each wait is bounded at four hours and checks approval, the
live process lease and the prior transcript hashes. It blocks until the due
operator step succeeds; returning means done or refused. A timeout, driver death,
refused payload or invalid measurement never advances the cursor. A control
failure is evaluated after unload and before the next load. The resulting halt
requires the review seat's ruling, not a blind retry.

```
python3 handoffs/tb/tb_driver.py --state handoffs/tb-evidence/tb-state.json TB0
```

After `finish:TB-k` the coding seat records the report in a fresh process, which
takes its own lease the way an arm's start does. It is refused while any driver
lease is live, and until every earlier step, each arm's `finish:` included, is
recorded with its evidence hash intact:

```
python3 handoffs/tb/tb_driver.py --state handoffs/tb-evidence/tb-state.json report REPORT.json
```

The cursor then rests on `review`, and `next` prints `WAITING ON: review seat -
review`. **The review is the review seat's own edit of the state file, never a
command of this program**, and approval is the operator's `approve` of the
review seat's record. Holding the coordinator lock
(`flock handoffs/tb-evidence/tb-state.lock`), the review seat records
`done.review` as `{status: SUCCESS, path, sha256, approval}` naming its review
evidence and the state's approval digest, as every receipt does, and advances
`cursor` by one. A receipt naming another approval refuses every later step. A new
approval means a new state, and `approve` refuses a state that already holds one.
`next` then prints `COMPLETE`.

The same verb takes TB-d or TB-k only when due. This is documentation for after
approval, not a request to run it now. The driver appends `probe.jsonl`, preserves
per-run and per-refeed readings, and writes each arm's result separately.
Certification and exact per-position evidence are both required for own re-feeds;
empty or partial measurements refuse. Changed-seed divergence is reported for all
pairs of the first repetition and must satisfy the registered first-24 bound.

Provisioning uses only `/var/lib/weaver-tb`, its own two admin roots and the
`weaver-bravo` account/group. It refuses an existing root or bravo account rather
than adopting custody. It installs the approved model at the historical absolute
artifact path (or checks an already-existing identical file). It never overwrites
a different model. Binaries live under the isolated root, never `/opt/weaver/bin`.
The installed declaration uses pyworker/basic_loop, the held identity and tuple.
M1, karl, their declarations and `/etc/weaver/admin` are not changed.

Provisioning adds the operator to bravo's group. Start a fresh login shell with
that group before running the driver. Every bravo load refuses a non-inactive m1
unit, an unreadable unit status, a remaining m1 coordination door, or processes
under m1's uid. It checks the GPU/driver tuple and stack-local CUDA resolution.
**No other agent is loaded while a leg runs.** The interlock is read at every load,
again when each measurement closes, and again at each unload, and the reading is
recorded each time: in the load and unload transcripts, and in the measurement's
result. m1 standing at any of the three refuses. An agent that starts and stops
wholly between two readings is not seen, which is why the rule is the operator's.
Each trace has a fresh directory: retries cannot truncate or relabel old evidence.

An interrupted provisioning or a refusal after load may leave partial resources.
They are evidence, not permission to clean up automatically. The halt records the
transcript. The review seat must specify a bounded cleanup/recovery step before
continuation; the script has no general root shell or arbitrary command hook.
Do not delete the state to bypass a refusal. This draft has not been exercised
against the installed stack, intentionally under HOLD.

## Build sections and tests

`sections.py DEPOSIT B1` (or B2) inventories already-extracted CUDA members plus
each host ELF's header, program headers and sections. Extract with the local `cuobjdump -xelf all LIBRARY` and
`-xptx all LIBRARY` in distinct `sections/STACK/cubin` and `ptx` directories.
No library is loaded and no kernel runs. Compare with:

```
python3 experiments/deployment-tuple/device/blackwell/code/sections.py compare B1-MANIFEST B2-MANIFEST OUTPUT.json
```

The result distinguishes cubin container hashes from code-section hashes. All
host sections, including relocation/read-only data, are retained; the identity
verdict conservatively requires all recorded sections, headers and CUDA members
to match, and every host file to be byte-identical. The entry point and segment
permissions live outside every section, so equal sections do not make equal
hosts. A manifest written before the headers were inventoried still carries
each file hash, which the verdict reads; only the header diff needs a fresh
inventory. An identity verdict cannot be inferred from equal file counts or
.text alone.

```
cd experiments/deployment-tuple/device/blackwell/code
python3 -B -m unittest test_tb
python3 -B perturb.py > /tmp/tb-perturbations.json
```

The tests use temporary files, a temporary Unix socket and stub admin/GPU calls.
**Every stub is built from `golden.py`**, never from what the code expects: each
constant there is a real tool's output captured unprivileged on this box, a
line copied from a real trace, or a shape read from the tool's source at
`e69916a`, with its command or file and lines, and a sha256, beside it. A stub
written to its own code's assumption is how derive's quoted artifact reached
review as a refusal every re-feed would hit on the device.
They make no installed-stack change and need no root. The mutation command copies
scripts to a temporary directory, runs the unmodified suite there first and
refuses with `BASELINE FAILED` unless it passes, then removes and inverts every
named check and requires each run to fail. Each record carries its failing output. A mutation
that destroys a wait bound is killed by a process-group timeout and identified
as such. The original files and local deposit are not mutated.
