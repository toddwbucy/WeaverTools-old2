# deployment-tuple - Charter

**Status:** MERGED. In `main` and the source of truth.

**Date filed:** 2026-09-25
**Document ID:** `deployment-tuple-PRD`
**Editorial:** Per the Working Rules.
**Landing PR:** #757

---

## 0. What this document is

The charter of the deployment-tuple experiment: the hypothesis that a deployment's
output is reproducible exactly when six declared fields are held, and that each of
the six moves bits when it alone is varied. It is the primary document of the
experiment and carries no parent, per the operator's rulings of 2026-09-25 recorded at
Working Process section 5. It registers the tuple as the chapter declares it (Bucy,
2026), names for each field what is predicted, what would falsify it, what the record
already shows and what is still owed, and says which probe answers for each. The
probes carry their own Specs and code beneath the arm they belong to, and this
document states no rule that code conforms to. Its filename is the README a reader
opens first and its Document ID is the charter's, `deployment-tuple-PRD`, per
Document Format section 3, and the experiment node below is the one record it
authors.

```graph
node: deployment-tuple
kind: experiment
```

**The tuple is a declaration set and not a set of demonstrated sensitivities.** Of the
six fields, four have been shown to move bits when varied alone, and two are declared
on argument with the experiment owed. One of the four, weights, was shown by a
control and not by its registered run, and its marker stays open. The markers below
say which is which, and a marker moves only when a probe's result lands in this tree.

## 1. Words

A **field** is one member of the tuple. An **arm** is one field's experiment, the
weights arm or the batch arm, and each arm is a directory beneath this charter. The
**baseline** arm is the one arm no field owns: it holds all six fields and asks
whether the replay instrument every other arm reads by reproduces what it served. A
**probe** is one measurement within an arm, a directory holding its Spec, its `code/`
and its `results/`. A **cell** is one card family a device probe runs on. A probe's
own internal measurements, where it has several, are its **legs**, and a probe's Spec
says so where its code spells them otherwise.

## 2. The six fields

**Weights, w.** The field names an artifact and not a model: two publisher revisions
under one name are two values, and the prediction is that they diverge from position
zero with everything else held, while the same hash re-fetched reproduces. The record
holds a control and not the registered run. A base Qwen3-8B beside an abliterated
variant of it, everything else held, gave no identical emission in 108 paired cells,
which shows that a large edit to the weights moves bits and says nothing about the
case a deployment meets without choosing it, two revisions shipped under one name.
Under a quantization ladder each rung is its own artifact, so the weights hash moves
with the precision and with nothing else, and five hashes on one ladder are one value
of this field. **Owed:** the weights arm on two revisions of one quant, issue #485.
Marker: control only. Arm: `weights/`.

**Precision, q.** Precision changes the bits. On one card, one stack, one publisher's
five artifacts of one model at bf16, q8_0, q6_k, q5_k_m and q4_k_m, every rung
reproduces itself and every rung differs from every other under a held seed: eight
declared seeds, two free runs per cell, no divergence within a rung, none of eighty
cross-rung pairs identical. Where the paths part does not order by precision: every
differing pair parts within the first few dozen tokens at the stimulus's near-ties,
as pairs differing in a seed or an architecture do, so the parting position is a
property of the stimulus and not a reading of the field's size. Not shown: whether
precision moves the distribution at position zero the way a card does, because
feeding one rung's recorded path through another rung is an election the record does
not carry. **Owed:** the cross-rung re-feed under a declared election, issue #515.
Marker: shown, olympus 2026-09-08. Arm: `precision/`.

**Device, d.** Three claims, and they are not one claim. First, across card families
bits differ with every other field held: Ada against Ampere on one chassis, one
driver, one pair of engine libraries, per-token entropies part at position zero on
every turn, and at 8B one Ampere run's recorded path fed through the Ada differs in
entropy at every position and the Ada's argmax leaves the recorded path exactly
where the free runs parted, on every seed. The distribution moved everywhere,
slightly, and the text moved once, completely. Second, across two dies of one card
model bits are identical, sixteen same-seed pairs and sixteen re-feeds exact, so the
field names a model and not a serial. What the record cannot say is whether the grain
is the card model or the architecture, because its one cross-card difference is also
a cross-architecture difference, and the cell that decides, one architecture at two
SM counts, is not in the record. Third, a driver or kernel update on one card with
the engine libraries held does not move bits, which is a claim about the kernel
stack rather than about the device and which no device row can settle. **Owed:** the
Blackwell cell, `device/blackwell/`, which carries the first claim on a third
architecture and the driver confound the third claim exists to remove, the grain
cell, and the same card across a driver or kernel update, issue #485. Marker: the
first two shown, the third owed. Arm: `device/`.

**Kernel stack, k.** Two claims. A rebuild of the engine libraries from pinned sources
yields identical hashes, and identical hashes reproduce, shown by Run 4 of issue #485.
And forcing the reduction library's kernel selection off its measured default moves
bits, which is the mechanism named as the leading candidate for the one unexplained
divergence in the record. **Owed:** the forced dispatch path, issue #485, blocked on an
environment passthrough. A third claim: a second implementation of the SPU is another
kernel stack. python-spu, serving the weights the Rust native engine serves with the
precision held as `python-spu-Spec` sections 5 and 7 hold it, is predicted to move bits
against it, and that Spec's section 7 labels each departing position substantive or
numerical by lines stated before any comparison run. It is falsified by the two serving
identical fields at every position the comparison reads. Its precondition, that
python-spu serves an agent under admin and its turn certifies under the diagnostic
replay, is shown on thinkpad, the external maps listing among its criteria, measured in
stage B2 at main. **Owed:** the comparison, epic #726. Marker: the first shown, the
second owed, the third's precondition shown and its comparison owed. Arm:
`kernel-stack/`, probe `kernel-stack/python-spu/`.

**Batch composition, b.** Batch shape moves bits because reduction order moves with
it, and that is the literature's result rather than this program's. The baseline
arrangement fixes the batch at one by construction, one caller and one turn at a
time, so the field is declared and not measured here, and no run in the corpus
supports or contradicts it. The arm is designed rather than absent: it needs a
forward pass carrying several sequences at once, which is a build and not a sweep.
**Owed:** the batch composition arm, epic #495. Marker: declared. Arm: `batch/`.

**Sampler and seed, sigma.** The declared seed is a live condition: change it and the
draw diverges, hold it and it reproduces, and the distribution under the draw does not
move. Eight declared seeds, each run twice at every cell of the matrix, gave
sixty-four identical same-seed pairs of sixty-four, a changed seed parted the essay
within the first two dozen tokens at every rung, and every run fed back through its
own arrangement reproduced its per-position entropy to the bit. The falsifier was
sharp, identical bits under a changed seed would have meant the seed never reached
the sampler, and it did not fire. A seed moves where the path goes and a card moves
what the path is drawn from. The derived generation seed holds one value across both
cards and all five precisions and changes only with the declared seed. **Owed:** the
probe-set envelope, the arm having run on one stimulus. Marker: shown, olympus
2026-09-08. Arm: `seed/`.

## 3. Where the arms stand

| Field | Marker | Arm | Probes in this tree |
| --- | --- | --- | --- |
| weights | control only | `weights/` | none yet |
| precision | shown | `precision/` | none yet, the olympus run predates this tree |
| device | shown, third claim owed | `device/` | `blackwell/`, held |
| kernel stack | first claim shown, third's precondition shown | `kernel-stack/` | `python-spu/`, the precondition in [`results/2026-09-29-thinkpad-stage-b/`](kernel-stack/python-spu/results/2026-09-29-thinkpad-stage-b/README.md) and, every criterion measured, [`results/2026-09-30-thinkpad-stage-b2/`](kernel-stack/python-spu/results/2026-09-30-thinkpad-stage-b2/README.md) |
| batch composition | declared | `batch/` | none yet, a build |
| sampler and seed | shown | `seed/` | none yet, the olympus run predates this tree |
| none, the instrument | held on olympus and thinkpad | `baseline/` | `determinism-matrix/`, results in [`results/2026-09-28-blackwell/`](baseline/determinism-matrix/results/2026-09-28-blackwell/README.md) |

A probe joins this table when its directory lands with its Spec, and a marker moves
when a result lands in that probe's `results/`. The runs cited above that predate
this tree are held in the `weaver-experiments` tree per Working Process section 5,
and a rerun under a probe here is what brings each into this table. The determinism
matrix deposits in that tree, olympus's from 2026-08-27 to 2026-09-08 and thinkpad's of
2026-08-27 and 2026-08-29, are the baseline probe's pre-tree runs, made by earlier
revisions of the code `baseline/determinism-matrix/code/` now holds, and each deposit
names its revision by sha256 where its box facts record one.

## 4. What this document does not carry

The rules any probe's code conforms to, which are that probe's Spec's. The results,
which are each probe's `results/`, dated. The chapter's argument for the tuple, which
this charter registers and does not restate (Bucy, 2026). And the epics that schedule
the owed arms, #485, #495 and #515, which hold the findings each produces.
