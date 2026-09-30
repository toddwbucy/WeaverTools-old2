# kernel-stack/python-spu - probe

The deployment tuple's probe of a second SPU implementation. python-spu serves the
weights the Rust native engine serves, at the precision `python-spu-Spec` sections 5
and 7 hold, so a difference between the two has the implementation as its one cause,
kernels included. Epic #726 runs it.

**What is where:**
- **The probe's Spec** is `python-spu-probe-Spec.md` beside this README. It states what
  the probe measures, the criteria each measurement is judged by, and what its code
  enforces.
- **The probe's code** is `code/`: `turn.py` and `replay.py`.
- **The dated records** are in `results/`, which no gate reads.
- **The implementation under test** is `python-spu/` at the tree's root, governed by
  `docs/crates/weaver-spu/python-spu-Spec.md`. It is the program being measured, not
  the probe's code.
- **The claim, the prediction and the falsifier** are the kernel-stack paragraph of
  this experiment's charter, `experiments/deployment-tuple/README.md`.

## Results

| Result | What it establishes | Where |
| --- | --- | --- |
| Stage B, thinkpad, 2026-09-29 | The precondition: python-spu serves an agent under admin, chosen per agent by `agent-spu`, its load event's `stack` names it by digest, and its turn certifies under the diagnostic replay. Five of six registered criteria are measured, and criterion 4, the external maps listing, rests on in-process evidence only | [`results/2026-09-29-thinkpad-stage-b/`](results/2026-09-29-thinkpad-stage-b/README.md) |
| Stage B2, thinkpad, 2026-09-30 | The precondition at main: python-spu at 112ec31c on the dc3a0f7a stack, with the worker's `--headroom-bytes` and no deployment `CUBLAS_WORKSPACE_CONFIG`. Every registered criterion is measured. Eight pass as registered, criterion 4 among them: one SPU process, its 72 code mappings all admitted by python-spu's own rule, read from outside. The seventh, registered against dc3a0f7a's zipapp, passes as amended before the resume to #756's | [`results/2026-09-30-thinkpad-stage-b2/`](results/2026-09-30-thinkpad-stage-b2/README.md) |
| Stage C, the comparison | the charter's claim, cell by cell, per the probe Spec's section 3 | owed, with its preconditions in #726 |
