# Stage B result, thinkpad, 2026-09-29: python-spu serves a real agent turn under admin

A dated result, read by no gate. **Claim:** an agent whose SPU is python-spu loads under
admin, answers a turn through its gate and unloads, leaving the card empty. Admin chooses
the SPU per agent through `spu-implementations` and `agent-spu` (#734). The agent's trace
names the SPU that served by digest, and the turn's diagnostic replay certifies. Nothing
belonging to karl changed.

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
- the unit journals;
- the before and after pairs;
- the trace copies;
- the derived declaration;
- the diagnostic replay's trace and logs.

None of it is copied here. `deposit.sha256` beside this note gives every deposit file's
sha256 and path, except this report's own copy, `RESULT.md`. The deposit's `SHA256SUMS`
is the same list.

**What is here:**
- this report;
- `PLAN.md`, the plan and its criteria as registered before attempt 1, which is also
  attempt 1's command sequence;
- `attempt1-ATTEMPT.md` and `attempt2-ATTEMPT.md`;
- `attempt2-COMMANDS.md`, attempt 2's sequence as run;
- `code/turn.py`, the one turn;
- `code/replay.py`, the diagnostic replay's driver, adapted from W4a's.

**The copies are scrubbed of one box's paths.** `$WT` is a clean worktree at the commit
each attempt names. `$AGENTS` is the operator's agent-configuration directory,
`$MODELS` the operator's model directory, and `$OPERATOR` the operator's account.

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

## Attempt 2 (python-spu at 850720e, the stack at b62812e): pass

`attempt2-ATTEMPT.md`, with the sequence as run in `attempt2-COMMANDS.md`.

| Criterion | Result |
| --- | --- |
| The load answers, and admin's log names the SPU | pass: `outcome: ready`, `spu: python /opt/weaver/python-spu/python-spu.pyz` |
| The load event's `stack` names what served | pass: python-spu.pyz 8197449f, worker 84991e7a and weaver-gate 488babf3, each equal to the installed file. The pyz rebuilt from 850720e is the same bytes |
| One turn, with its request and measurement in the trace | pass: "The answer is four." The weights_hash is be1a0490, blake3 over the safetensors directory, recomputed independently |
| Only admitted code is mapped | the external listing was not taken, a pgrep defect recorded in `attempt2-ATTEMPT.md`. The in-process maps rule passed at admission and after the first generation, and the journal carries no violation and no fault |
| The card is empty after the unload | pass |
| Nothing of karl's changed | pass: three before and after pairs, each diffing empty |
| The diagnostic replay | **certified** |

**The recreated prefix:**
- `installed_set.py` exits 0 against the lock (9aa7e037);
- its tree digest is 1dce454a.

## What this does not establish

- **Two SPUs on one card, or python-spu against the Rust SPU.** That is stage C. One of
  its preconditions in #726 is that the matrix read which SPU served from the load
  event's `stack`, and this run shows that field is recorded.
- **More than one turn.** A multi-turn replay's re-feed is #515's arrangement question.
- **An external maps listing of the served process.** The in-process rule stands in for
  it.

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
