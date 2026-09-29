# python-spu-probe - Spec

**Status:** MERGED. In `main` and the source of truth.

**Date filed:** 2026-09-29
**Document ID:** `python-spu-probe-Spec`
**Parent:** `deployment-tuple-PRD`
**Editorial:** Per the Working Rules.
**Landing PR:** #749

---

## 0. What this document is

The Spec of the kernel-stack arm's python-spu probe. It says what the probe measures,
the criteria each measurement is judged by, and what the probe's own code enforces.

**The implementation under test is not this probe's code.** `python-spu/` at the tree's
root is the served program, and `docs/crates/weaver-spu/python-spu-Spec.md` governs it.
This document cites that Spec for the implementation and for the lines a comparison
reads against, and restates neither. The claim, the prediction and the falsifier are
the kernel-stack paragraph of the charter, `experiments/deployment-tuple/README.md`, as
python-spu-Spec section 10 assigns them.

## 1. What the probe is

Two measurements, in order:
- **Stage B, the precondition.** python-spu serves an agent under admin, and the
  agent's turn certifies under the diagnostic replay. Section 2.
- **Stage C, the comparison.** Cells in which python-spu and the Rust SPU serve the
  same weights at the same precision. Section 3.

Stage A, epic #726's Spec, carry, sampler and environment, is code and not a
measurement. Its pass is python-spu-Spec section 6's conformance suite, and it records
nothing here.

The probe's directory holds this Spec, `code/` and `results/`:
- `code/turn.py` sends one turn through an agent's gate.
- `code/replay.py` drives the diagnostic replay of a served run.
- `results/<date>-<box>-<stage>/` holds one dated record, which no gate reads.

## 2. Stage B, the precondition

### 2.1 The arrangement

- **One agent under its own admin configuration directory**, selected by
  `WEAVER_ADMIN_CONFIG`, so no other agent's configuration, binaries or trace is
  touched. `spu-implementations` names the python-spu zipapp, and `agent-spu` names
  that key for the agent, per `weaver-admin-Spec` section 9.
- **python-spu installed by its README's block**, so the prefix is recreated and held
  to the lock, per python-spu-Spec section 8.
- **A safetensors directory the agent's uid can read.**

### 2.2 The criteria

They are registered before the run, in the plan the result keeps. Each is decided by
the evidence named:

1. **The load answers ready.** Admin's log line for the load names the SPU admin
   launched.
2. **The load event's `stack` names the SPU**, by a sha256 equal to the installed
   file's, beside the worker's and the gate's.
3. **One turn is answered.** The trace carries the turn's `model.request` and
   `model.measurement`, and the measurement's `weights_hash` is the directory's digest
   as python-spu computes it, recomputed independently.
4. **Only admitted code is mapped.** The served SPU's executable file-backed mappings,
   read from `/proc/<pid>/maps` from outside the process, are each admitted by
   python-spu-Spec section 8's rule. The SPU is selected by its command line, anchored
   at the interpreter the zipapp's shebang names, and the listing is read only when
   exactly one process matched.
5. **The card is empty after the unload**, and the agent's unit is inactive.
6. **The diagnostic replay of the turn certifies.**

**Beside the criteria, nothing belonging to another agent changes.** The following are
captured before the load and after the unload, and each pair must diff empty:
- The other agent's unit state and runtime directory.
- Admin's configuration, binaries and libraries for the other agents.
- The other agent's declaration, and its trace by size and modification time.
- Admin's own log.

The capture time is written to a file of its own, never into a compared file.

**A criterion that was not measured is reported as not measured.** Evidence of another
kind is recorded beside it and never counted as the criterion. The in-process maps rule
of python-spu-Spec section 8 is such evidence for criterion 4.

### 2.3 What the code enforces

- **`turn.py` exits 0 only when the gate's reply is a newline-terminated `answered`
  line carrying text.** A closed connection, a line cut before its newline, a line that
  is not JSON, or any other kind exits 1, naming what came back.
- **`replay.py` runs inside `unshare -Ur`**, because the preload door admits uid 0
  alone. It refuses a declaration that is not diagnostic, and it never overwrites the
  diagnostic sink.
- **`replay.py` serves and records one declaration.** It writes the derived
  declaration with the decoder's re-feed and column permissions set to
  `replay-declaration.toml` in the deposit. It parses that file back, and refuses it
  unless it equals the derived declaration with exactly those two keys set. It serves
  the instruction from that parse, and records that file's sha256 as the enter's
  declaration, never the derived file's.
- **`replay.py` exits 0 only when all of these hold:**
  - `replay.closed` reads certified.
  - The leave is answered `left`.
  - The worker and the state member exit 0 on their own within the grace after the
    leave.
  - The temporary directory is removed.
- **Anything else exits 1, each reason named.** That includes:
  - Another closing outcome.
  - A turn stopped before the close.
  - A leave refused or unanswered.
  - A process that had to be signalled.
  - A process that exited non-zero.
  - A directory left behind.
- **`replay.py` reads the sink only by its newline-terminated lines** while the
  harness writes it. The unterminated tail waits for the next poll, and a complete line
  that is not JSON fails the run, naming its number. A coordination answer longer than
  the receive buffer refuses rather than parsing what was cut.
- **After a clean leave, a process that does not exit is signalled only when the grace
  runs out.** Otherwise each is signalled at once.
- **`--stand-only` exits 1 unless** coordination bound and both processes stood.

## 3. Stage C, the comparison

**A cell** is one card, serving two agents under one admin configuration. One agent's
`agent-spu` names python-spu, and the other's names the Rust SPU at its native engine.
The two are held equal in everything else:
- The same safetensors directory.
- The precision python-spu-Spec sections 5 and 7 hold.
- The same declared seed, knobs and prompts.

**The two agents are loaded one at a time during a comparison run, never together.**
With both resident, the second's allocation changes the first's free device memory, and
a library that chooses its algorithm by free memory or workspace can then compute
differently. That would give a difference a second cause, the co-resident agent, where
python-spu-Spec section 7 claims one. So one agent is loaded, serves its half of the
cell and is unloaded, and `nvidia-smi` reads no compute process before the other agent
is loaded. That reading is part of the cell's record.

**The drives, the measures and the lines are python-spu-Spec section 7's.** That
covers the distribution level along the partner's recorded path, the token level under
the shared sampler, and every position reported with substantive as a label. None is
restated here.

**Each cell's record names each SPU from its own load event's `stack`**, never from
admin's configuration.

**Its preconditions are #726's items, and a cell runs only once they have landed.**
One has: python-spu loads at BF16, as python-spu-Spec sections 4 and 9 state. Two are
open in the checklist:
- The determinism matrix reading which SPU served from the record.
- The matrix's readers for both SPUs' provenance.

**The comparison's code is not written.** It lands in `code/` with its own act, and
this section is revised to state what that code enforces before the code is hardened,
per Working Process section 6.

## 4. What this document does not carry

- **python-spu's behaviour, its environment and its conformance.** They are
  python-spu-Spec's.
- **The lines of section 7 and the two levels they read at.** They are also
  python-spu-Spec's.
- **The claim, the prediction and the falsifier.** They are the charter's kernel-stack
  paragraph.
- **Admin's configuration and its lifecycle.** They are `weaver-admin-Spec`'s.
- **What the diagnostic replay certifies.** It is the replay's own Specs'. This probe
  reads the outcome and does not define it.
