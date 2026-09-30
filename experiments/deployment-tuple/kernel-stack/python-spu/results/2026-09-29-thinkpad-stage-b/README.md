# Stage B result, thinkpad, 2026-09-29: python-spu serves a real agent turn under admin

A dated result, read by no gate. **Claim:** an agent whose SPU is python-spu loads under
admin, answers a turn through its gate and unloads, leaving the card empty. Admin chooses
the SPU per agent through `spu-implementations` and `agent-spu` (#734). The agent's trace
names the SPU that served by digest, and the turn's diagnostic replay certifies. Nothing
belonging to karl changed.

**Stage B passes on five of its six registered criteria, and the sixth is not
measured.** The six are `PLAN.md` section 5's five pass criteria and section 6's
replay. Criterion 4, the external listing of the served process's code mappings, was
not taken in attempt 2, and it rests on in-process evidence only. That evidence is
python-spu's own maps rule and a clean journal, which is not the observation the plan
registered. A narrow attempt 3 is offered to the operator: load, one turn, the listing
with the corrected selector, unload. If it runs, its listing joins this record and the
pass reads whole.

*Attempt 3 was not run. Criterion 4 was measured in stage B2, at main on 2026-09-30,
`../2026-09-30-thinkpad-stage-b2/`: the anchored selector found one SPU process, and
python-spu's own rule admitted all 72 of its code mappings.*

**Scope:**
- one agent, karl2;
- one turn;
- one card, an RTX PRO 5000 Blackwell on driver 615.71.09;
- Qwen2.5-0.5B-Instruct safetensors, BF16 on disk and loaded FP32, per python-spu-Spec
  2.1's known gap.

This is not stage C. No comparison with the Rust SPU is made here.

The deposit is on the shared bulk store at
`/bulk-store/weaver-testing/stage-b-thinkpad-2026-09-29-b62812e/`, mounted on the
thinkpad under `/mnt/bulk-store/weaver-testing/`. It holds:
- both attempts' records;
- the plan as registered, unscrubbed (`PLAN.md`);
- the unit journals;
- the before and after pairs;
- the trace copies;
- the derived declaration;
- the diagnostic replay's trace and logs.

None of it is copied here. `deposit.sha256` beside this note gives every deposit file's
sha256 and path, except this report's own copy, `RESULT.md`, and `attempt3-2026-09-29/`,
which is prepared and not yet run. The deposit's `SHA256SUMS` is the same list.

**What is here:**
- this report;
- `PLAN.md`, the plan and its criteria as registered before attempt 1, which is also
  attempt 1's command sequence;
- `attempt1-ATTEMPT.md` and `attempt2-ATTEMPT.md`;
- `attempt2-COMMANDS.md`, attempt 2's sequence as run.

The scripts the commands run are the probe's own code, `../../code/`:
- `turn.py`, the one turn;
- `replay.py`, the diagnostic replay's driver, adapted from W4a's.

`python-spu-probe-Spec` states what each enforces. Each now exits non-zero unless its
outcome holds: `turn.py` unless the reply is `answered` with text, and `replay.py`
unless `replay.closed` reads certified and the teardown is clean. That gate was added
in review, after the run, and the run's own records read `answered` and certified.

**The copies are scrubbed of one box's paths.** `$WT` is a clean worktree at the commit
each attempt names. `$AGENTS` is the operator's agent-configuration directory,
`$MODELS` the operator's model directory, and `$OPERATOR` the operator's account.
`code/` in the plan and the commands is the probe's `code/`.

## Attempt 1 (b62812e): the load failed, and the failure was a finding

`attempt1-ATTEMPT.md`. At the first CUDA forward, triton compiled its driver helper with
the system's gcc into a temporary directory. The unit had no linker, so admission faulted
and admin rolled back. Every earlier CUDA run had done the same compile silently. That
became #726's item "python-spu compiles and loads no code at runtime", answered by #741
(merged 850720e):
- triton left the locks;
- torch's native JIT was turned off before torch is imported;
- an in-process maps rule now faults any executable mapping from outside the prefix and
  a named system list.

Codex's passes on #741 added two more:
- a build that requires every module the server imports;
- an install that recreates the prefix and holds it to the lock
  (`python-spu/scripts/installed_set.py`), since `pip install -r` removes nothing.

## Attempt 2 (python-spu at 850720e, the stack at b62812e): pass on five criteria, criterion 4 not measured

`attempt2-ATTEMPT.md`, with the sequence as run in `attempt2-COMMANDS.md`.

| Criterion | Result |
| --- | --- |
| The load answers, and admin's log names the SPU | pass: `outcome: ready`, `spu: python /opt/weaver/python-spu/python-spu.pyz` |
| The load event's `stack` names what served | pass: python-spu.pyz 8197449f, worker 84991e7a and weaver-gate 488babf3, each equal to the installed file. The pyz rebuilt from 850720e is the same bytes |
| One turn, with its request and measurement in the trace | pass: "The answer is four." The weights_hash is be1a0490, blake3 over the safetensors directory, recomputed independently |
| Only admitted code is mapped | **not measured**: the external listing was not taken, a pgrep defect recorded in `attempt2-ATTEMPT.md`. In-process evidence only: python-spu's maps rule passed at admission and after the first generation, and the journal carries no violation and no fault |
| The card is empty after the unload | pass |
| Nothing of karl's changed, required beside the criteria | pass: the `untouched` and `admin-log` pairs diff empty. The karl pair differs in its first line only, the capture's own timestamp, shown below, and its other lines are equal |
| The diagnostic replay | **certified** |

The karl pair, whose sha256 values in `deposit.sha256` differ for this reason alone:

```
$ diff attempt2-2026-09-29/karl-before.txt attempt2-2026-09-29/karl-after.txt
1c1
< 2026-09-29 11:50:29 CDT
---
> 2026-09-29 11:58:51 CDT
```

Attempt 1's karl pair differs the same way, 10:38:02 against 10:40:10. From attempt 3
on, the capture time is written to a file of its own.

**The replay's recorded declaration.** Attempt 2's replay enter carried `derived.toml`'s
sha256 as its declaration, not the declaration it served, which added the re-feed and
column permissions. No record in the deposit carries that digest, because the
diagnostic trace records none. No criterion rests on it: criterion 2 reads the served
run's load event, and criterion 6 reads `replay.closed`. The probe's code now hashes
the declaration it serves.

**The recreated prefix:**
- `installed_set.py` exits 0 against the lock (9aa7e037);
- its tree digest is 1dce454a.

## What this does not establish

- **Two SPUs on one card, or python-spu against the Rust SPU.** That is stage C. One of
  its preconditions in #726 is that the matrix read which SPU served from the load
  event's `stack`, and this run shows that field is recorded.
- **More than one turn.** A multi-turn replay's re-feed is #515's arrangement question.
- **Criterion 4, an external maps listing of the served process.** It was not measured.
  The in-process rule is evidence toward it, not the observation registered.

## Found for #726

- **python-spu takes no `--headroom-bytes`.** The stage B configuration avoids it, and
  the item "python-spu takes the worker's whole argument vector" stands.
- **A retry reaps the failed unit first.** An earlier attempt's failed unit must be
  reaped with `systemctl reset-failed` before admin can load the agent again. That is
  admin's stated behaviour (`PriorUnitUnreaped`), not a defect, and it belongs in any
  retry procedure.
- **Select python-spu's process by its command line.** Selecting it by name fails,
  because a process started through a shebang takes the script's name as its comm. The
  command line anchored at the interpreter works.
