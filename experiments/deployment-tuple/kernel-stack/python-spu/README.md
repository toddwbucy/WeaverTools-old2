# kernel-stack/python-spu - probe

The deployment tuple's probe of a second SPU implementation. python-spu serves the
weights the Rust native engine serves, at the precision `python-spu-Spec` sections 5
and 7 hold, so a difference between the two has the implementation as its one cause,
kernels included. Epic #726 runs it.

**Its Spec and its code sit outside this directory.** The code is the served program
itself, `python-spu/` at the tree's root, and its Spec is
`docs/crates/weaver-spu/python-spu-Spec.md`. That Spec states what the code enforces
and, in its section 7, the line a comparison reads against. The claim, the prediction
and the falsifier are the kernel-stack paragraph of this experiment's charter,
`experiments/deployment-tuple/README.md`, per that Spec's section 10. This directory
holds the probe's `results/` and nothing that restates either document.

## Results

| Result | What it establishes | Where |
| --- | --- | --- |
| Stage B, thinkpad, 2026-09-29 | The precondition: python-spu serves an agent under admin, chosen per agent by `agent-spu`, its load event's `stack` names it by digest, and its turn certifies under the diagnostic replay. Five of six registered criteria are measured, and the external maps listing rests on in-process evidence only | [`results/2026-09-29-thinkpad-stage-b/`](results/2026-09-29-thinkpad-stage-b/README.md) |
| Stage C, the comparison | the charter's claim, cell by cell | owed, with its preconditions in #726 |

Stage A, the Spec, the carry, the sampler and the environment, landed as code and
carries no result here: #727, #729, #732, #735, #739 and #741.
