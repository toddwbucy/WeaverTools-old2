# python-spu

**A prototype, carried into the tree as it stood.** This is the second implementation
of the SPU organ's decode role that `docs/crates/weaver-spu/python-spu-Spec.md`
governs, landed as a lab instrument under Working Process section 6's rule that a carry
is not a hardening. The Spec says what the implementation must become, and its section
2.1 names where this prototype falls short of it. Nothing here is relied on for a
verdict until the acts epic #726 lists have closed those gaps.

It serves Qwen2 causal models from a local Hugging Face directory with PyTorch in eager
mode, on the CPU for the tests and on one CUDA device for the smoke test. It carries an
experimental ModernBERT classifier, which the Spec scopes out of this implementation.

## Tests

The oracle links the workspace crates at the commit its manifest pins, so the suite
compares Python's answers with the Rust code's own. Build it first, then run the suite
from this directory:

```sh
cargo build --manifest-path oracle/Cargo.toml --locked
pytest -q
```

The suite runs on the CPU. It covers Rust wire comparisons, seed derivation, rendering,
measurement arithmetic, state transitions, tiny-model forwards, rollback, classifier
scoring, Unix packet segmentation, Rust and Python transport, and the child process's
lifecycle. The socket tests need local Unix IPC, so a sandbox that refuses packet sends
cannot run them.

## Model smoke test

The smoke test launches three fresh SPU child processes, comparing two ordinary runs
and one with residual readout enabled. Each loads the model, opens a session,
generates, flushes, releases and exits. It exercises the SPU protocol through a local
test driver, not the WeaverTools harness, admin or trace replay.

```sh
python scripts/smoke.py <model-dir>
python scripts/smoke.py <model-dir> --device cuda --output <report.json>
```

CUDA mode refuses if CUDA is unavailable, and neither mode downloads a model. GPU runs
set a deterministic cuBLAS workspace configuration before the child starts. Name the
card with `CUDA_VISIBLE_DEVICES`. A report goes to the run's deposit on the shared bulk
store, not into this tree.

## Files

- `src/python_spu/`: serving, the protocol, the model engine, sampling and the local
  test driver.
- `tests/`: the compatibility and behaviour tests.
- `oracle/`: the Rust program that answers the suite with the Rust code's results.
- `scripts/smoke.py`: the trained-model process test.

## Not yet shown

Integration with the Rust harness end to end, and a trace verifying under the
diagnostic replay. The full wire vocabulary. GPU admission against a live occupant,
headroom, and injected device faults. Other families, precisions and sharding. The
classifier's equivalence on a trained artifact. Speed. A small model's smoke test
passing establishes none of these.
