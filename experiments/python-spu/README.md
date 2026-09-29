# python-spu - Charter

**Status:** MERGED. In `main` and the source of truth.

**Date filed:** 2026-09-29
**Document ID:** `python-spu-PRD`
**Editorial:** Per the Working Rules.
**Landing PR:** PENDING

---

## 0. What this document is

The charter of the python-spu experiment, the one epic #726 runs:
- **The hypothesis.** A second implementation of the SPU, written in Python against the
  same contracts, serves an agent under admin exactly where the Rust SPU does.
- **Why it matters.** Once it serves, the two can be compared with weights and precision
  held, so a difference between them has the implementation as its one cause.

This document registers the three stages the epic names. For each it says what is
predicted, what would falsify it and where it stands. It carries no parent.

**python-spu varies no field of the deployment tuple.** It is an integration, not a
variable, so its stages sit where an arm would sit, each with a `results/` of dated
records. The code's rules are `docs/crates/weaver-spu/python-spu-Spec.md`, which is why
no stage here carries a probe Spec. The comparison of stage C is a measurement of the
tuple's kernel-stack field, so it runs as a probe under
`experiments/deployment-tuple/kernel-stack/`, and this charter only points to it.

**Filed after stages A and B ran.** Stage A's predictions are the Spec's, stated there
before each act's code. Stage B's criteria were registered in its plan before either
attempt, and the plan is kept with its results.

## 1. The stages

| Stage | Predicted | Falsified by | Where it stands |
| --- | --- | --- | --- |
| **A**: the Spec, the carry, the sampler, the environment | python-spu's sampler draws what the Rust sampler draws, draw for draw, on the Rust oracle's inputs. Its environment is exactly pinned and minimal, and a serving process holds only the declared imports and maps only admitted code | one differing draw. An undeclared import or a foreign executable mapping in a clean serving run | shown: #727 (the Spec), #729 (the carry), #732 (the sampler), #735, #739 and #741 (the environment) |
| **B**: one real turn | an agent whose SPU is python-spu, chosen by admin's `agent-spu`, loads, answers one turn and unloads, leaving the card empty. Its load event's `stack` names the SPU by digest, and the turn's diagnostic replay certifies | a correctly installed prefix that fails to load or to serve. A `stack` that omits or misnames the SPU. A replay that diverges | shown on thinkpad, 2026-09-29: [`stage-b/results/2026-09-29-thinkpad/`](stage-b/results/2026-09-29-thinkpad/README.md) |
| **C**: the comparison | as `python-spu-Spec` section 7 states what a substantive difference is, before any comparison run | as section 7 states | owed. Its preconditions are #726's, and it runs under `experiments/deployment-tuple/kernel-stack/` |

A stage's marker moves only when its result lands in this tree.

## 2. What this document does not carry

- **The rules python-spu's code conforms to.** They are `python-spu-Spec`'s.
- **The threshold of stage C.** It is section 7 of that Spec, not restated here.
- **The tuple and its fields.** They are `experiments/deployment-tuple/README.md`'s.
- **The later Python variants.** #726 lists them. Each is its own deployment under the
  tuple and would join section 1 when its first result lands.
