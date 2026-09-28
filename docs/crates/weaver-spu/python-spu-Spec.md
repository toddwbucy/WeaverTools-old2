# python-spu - Spec

**Status:** MERGED. In `main` and the source of truth.

**Date filed:** 2026-09-28
**Document ID:** `python-spu-Spec`
**Parent:** `weaver-spu-PRD`
**Editorial:** Per the Working Rules.
**Landing PR:** #727

---

## 0. What this document is

The Spec of `python-spu`, a second implementation of the SPU organ, written in Python
and held at the top of the tree as `python-spu/`. It is filed beside `weaver-spu-Spec`
because it implements the organ that document builds, and it names `weaver-spu-PRD` as
its parent because that charter is where the organ is defined. It is not a crate and
does not enter the mirror of Document Format section 2, which pairs a crate's documents
with a crate's sources. It is code that requires a Spec, which Document Format section 3
makes sufficient: a Spec belongs to any code that requires one.

Level discipline. The four contracts govern what crosses the seams and how it fails.
`weaver-spu-Spec` governs how the Rust SPU represents that. This document says which of
the Rust SPU's represented behaviours `python-spu` carries identically, by which
instrument each is proven the same, which are its own, and what a comparison of the two
SPUs certifies. It restates no contract clause and no clause of `weaver-spu-Spec`, and
cites each by section.

It is written before the code it governs lands, per Working Process section 6's rule
that no code lands without a merged Spec, and it states what a pass of the conformance
suite certifies before that suite is hardened, per the same section's rule that a pass
is stated before it is hardened. Epic #726 carries the work in stages, and this document
governs all of them.

## 1. What python-spu is

**A second implementation of one organ, honoring the same contracts.** The organ is the
one `weaver-spu-PRD` section 1 charters: it holds a model on the device for as long as
the worker that forked it lives, and it answers the harness across a two-initiator
channel. `python-spu` is party to the three contracts the Rust SPU is party to,
`weaver-harness-spu-contract` for residency, `weaver-harness-spu-decode-contract` for
the token seam and `weaver-harness-spu-classify-contract` for the label seam, and it
honors each as written. The contracts name no language, no type and no module, so the
seams admit a second implementation as they stand and none of them changes for it.

**It writes no trace, as the Rust SPU writes none.** The harness is the sole writer, per
`weaver-harness-trace-contract` and `weaver-spu-PRD` section 2. What `python-spu`
reports crosses the token seam in the shapes the decode contract fixes, and the harness
authors the records from it. The trace contract binds this implementation through that
route alone: a record the harness writes from a `python-spu` report verifies under the
trace contract exactly as a record written from a Rust report does.

**Nothing else in the agent changes, and nothing else learns which SPU served.** Admin
launches whatever file its `spu-binary` configuration names, and the harness hashes that
file into `weaver_binaries` at both ends of a run. `spu-binary` is admin-wide, so one
implementation serves a box for the length of a run. Until the SPU reports its own
identity, which section 10 defers, the `spu-binary` hash and the environment lock the
box facts record are what name the implementation that served.

**It does not replace the Rust SPU.** Both serve, and the record says which. Under the
deployment tuple a different implementation is a different kernel stack, and so a
different deployment, which is why the two are compared rather than required to agree
bit for bit.

## 2. Where it lives

    python-spu/
      src/python_spu/    the SPU: the channel ends, the wire, the session, the engine,
                         the family, the sampler and the classifier
      tests/             the conformance suite and the behaviour tests
      oracle/            a Rust program linking the workspace crates, which answers
                         the suite with the Rust code's own results
      scripts/           the model smoke test

**The oracle depends on the workspace crates at a pinned commit and on no copy of
them.** It is a Rust program outside the workspace, so it is not a member and its
manifest names `weaver-spu`, `weaver-types` and `weaver-traits` by the repository and a
commit. The suite therefore reads what the Rust code computes rather than a
transcription of it, and a copied source tree would be an archive directory, which
Working Process section 1 keeps out of the tree.

**Nothing under `crates/` changes for it.** The pyworker inside `weaver-harness` is the
precedent for Python in this tree and not the model for this one: that is Python behind
a feature of a crate, and this is a separate program behind the organ's seams.

## 3. What it carries identically

Every row names the `weaver-spu-Spec` section that states the behaviour, and the
instrument that proves `python-spu` carries it the same. An oracle row runs the Rust
code at the pinned commit and compares its answer with Python's. A contract row is a
check the named contract's Conformance section lists.

| Behaviour | `weaver-spu-Spec` | Proven by |
| --- | --- | --- |
| The two channel ends at descriptors 3 and 4, close-on-exec set on both, the dumpable flag cleared before the engine's runtime is imported | 2 | a process test |
| The `SOCK_SEQPACKET` envelope and the segmented frame, per `weaver-organ-channel` | 2 | oracle, over a socket pair |
| Every payload of the three SPU contracts, accepted and refused | 2, 9 | oracle, serde round trips both ways |
| Admission refuses and never evicts, and the weights hash is blake3 at admit | 3 | a process test, oracle for the hash |
| The session appends and never rewinds, the identity prefix is permanent, an overflow refuses before any append | 4.2 | contract, decode section 8 |
| The turn terminator made resident on every path, the stop within a token boundary of the cancel | 4.2, 4.3 | contract, decode section 8 |
| The flush per resolved entry and the elision's exact removal | 4.4, 4.5 | contract, decode section 8 |
| The re-feed drive, its registry and its recorded path | 4.6 | contract, decode section 8 |
| The family's rendering, prefix and markers, for each family served | 5 | oracle |
| The signals computed before the sampler, the surprisal election, positional pairing, absent and not zeroed | 6 | oracle for the arithmetic, contract for the pairing |
| The residual readout, elected at admit, a tap failure while elected a fault | 7 | contract, decode section 8 |
| The probability field, its depth refused below the sampling cutoff at admit | 7.5 | oracle |
| The dispositions, the knob set, the tunables arriving in the declaration, the effective values in the record | 8 | oracle, contract |
| The derived seed, to the bit | 8.5 | the section's own test vectors, oracle |
| The failure vocabulary: refusals typed at the floor, faults below the exchange | 9 | oracle, contract |
| The classify submodule: completeness, the bound, readiness, the trace context echoed byte-exact | 11 | contract, classify section 8 |

**A behaviour this implementation does not yet carry is refused at admission, never
dropped silently.** An election the declaration makes and `python-spu` cannot honor
refuses the load naming it, per `weaver-spu-PRD` section 13.7's rule that a load
granting an election it cannot honor fails at its cheapest moment. The table is the set
this document binds, and a row whose instrument is not yet built is a row the
implementation does not advertise.

## 4. What is its own

**The engine.** The first version runs Hugging Face `transformers` in eager mode at FP32
on one CUDA device, serving the Qwen2 family from a local safetensors directory. It
makes no download, runs no remote code, converts no quantization, falls back to no other
device, and shards nothing. Section 9 names the versions after it.

**The kernel stack.** The kernels are PyTorch's and the CUDA libraries PyTorch brings
with it, its own cuBLAS and cuDNN among them, not the ones the Rust SPU links. They are
recorded in the box facts beside the environment lock, since two runs on one card under
two kernel stacks are two deployments under the tuple.

**The runtime.** A CPython interpreter, one exact version per build, named by the lock
of section 8.

**The cache.** It owns the hot cache on the same terms `weaver-spu-PRD` section 2 sets:
the harness decides the flush and never touches the cache, and the cache ends with the
residency. How the cache is held is the engine's. The first version recomputes the
retained sequence after a truncation rather than rolling a cache back, which changes the
time a flush costs and not what it leaves resident.

## 5. The sampler

**The draws match exactly the sampler of the Rust engine the comparison is made
against.** The Rust SPU has two engines and they sample differently, per
`weaver-spu-Spec` section 4.1's two backends. Both build their sampler per generation
from the derived seed of section 8.5, and they differ in the order of the chain and in
the generator that draws. A comparison that let the two generators differ would measure
the generators at every sampled position, whatever the engines did, so `python-spu`
carries the partner's sampler and never an approximation of it.

**The first version's partner is the Rust native engine**, candle at FP32 on the same
safetensors directory, on the Planner's election of 2026-09-28 recorded on #726. It is
the one pairing that holds both the weights and the precision fixed, since llama.cpp
computes on quantized blocks that no dequantized forward reproduces. Its chain, from
`crates/weaver-spu/src/decoder/native.rs` and candle's `LogitsProcessor` at the pinned
revision, is this:

1. The repetition penalty over the last `repetition_window` resident tokens, as candle's
   `apply_repeat_penalty` computes it, skipped where the penalty is 1 or the window 0.
2. Temperature zero or below is the argmax, and nothing below applies.
3. The logits divided by the temperature, then the softmax.
4. Top-k where k is above zero, then top-p. A top-k of zero disables that gate.
5. The draw, `WeightedIndex` over the remaining weights, from `rand`'s `StdRng` seeded
   by `seed_from_u64` with the whole 64-bit derived seed, at the `rand` version the lock
   pins, 0.9.5, whose `StdRng` is ChaCha12 by `rand_chacha` 0.9.0.

**The GGUF engine's chain is never ported to Python.** It runs penalties, the truncating
filters, then temperature, then llama.cpp's own draw from a seed folded to 32 bits. The
later control version, `llama-cpp-python` against the Rust GGUF cells, uses llama.cpp's
sampler natively and inherits that chain rather than reimplementing it.

**The port is proven draw for draw on fixed logits.** The oracle gains an operation that
runs candle's own `LogitsProcessor` over a supplied logits vector, knob set and seed,
and the suite requires Python's draw to equal it over many vectors and seeds, including
near-ties, a top-k of zero, a top-p of one and a temperature at zero. The sampler is a
function of the logits alone once the knobs and the seed are fixed, so identical logits
give identical draws, and the arithmetic is ported in candle's order and precision for
that reason.

**Where exact draws prove impossible, the comparison falls back to distributions and
says so.** If a draw cannot be reproduced exactly, the suite records which operation
departs, the comparison of section 7 is made at the distribution level alone, and every
cell it produces states that token streams are not comparable.

**A precondition before any comparison run.** The native engine is confirmed to load the
safetensors directory the Python SPU serves, and the declaration that selects the native
engine for it is recorded, since which backend serves is a property of the artifact
decided at admit, per `weaver-spu-Spec` section 4.1.

## 6. What conforms means

This section is the statement of the conformance suite's pass, made before the suite is
hardened, per Working Process section 6.

**A pass certifies that `python-spu` answers every question the Rust code can answer
without a model the way the Rust code answers it**, at the commit the oracle pins. Those
questions are the wire, the framing, the rendering, the seed, the signal arithmetic, the
refusals and faults, and the sampler's draw on fixed logits. It also certifies every
check that section 8 of `weaver-harness-spu-decode-contract` and section 8 of
`weaver-harness-spu-classify-contract` list, and the ordering and failure cases of
`weaver-harness-spu-contract` sections 3 and 5, run against `python-spu` itself.

**The evidence is the Rust code's own answer, read by execution.** The oracle links the
workspace crates at the pinned commit and computes each expected value from them, so the
suite compares two implementations rather than one implementation against a
transcription of the other. The seed also meets `weaver-spu-Spec` section 8.5's test
vectors, which that section states independently of any implementation.

**It guards against drift.** A change on either side to anything the table of section 3
proves by the oracle fails the suite once the pin reaches it.

**It does not guard against, and does not certify:**

- That the two SPUs produce the same tokens from a model. The engines compute different
  logits, and section 7 is where that difference is measured.
- A Rust change the pin has not reached. Conformance is to the pinned commit, and moving
  the pin is its own act, carrying the suite's result at the new commit.
- Behaviour under a real device: admission against a live occupant, headroom and
  injected device faults. These are stage B's, on thinkpad, and not the suite's.
- A turn completed end to end through the harness, the gate and admin, and a trace
  verifying under the diagnostic replay. That is epic #726's deployment item.
- Families, precisions and engines beyond the version served.
- Speed.

## 7. What a substantive difference is

Stated before any comparison run, per the same rule, so that no result chooses its own
threshold. The comparison holds the weights, the precision, the knobs, the declared seed
and the prompts fixed, and serves them from each SPU in turn, so that a difference has
one cause, the implementation.

**At the distribution level**, both SPUs are driven along one token path, the partner's
recorded path, with the re-feed drive of `weaver-spu-Spec` section 4.6, so each position
is read against the same context. At every position the comparison reads each SPU's
entropy, per section 6 of that Spec, and its probability field, per section 7.5, at one
depth elected for the run. A position differs substantively when either of these holds:

- The two fields name different top-1 tokens, and each SPU's own margin between its
  top-1 and top-2 log-probabilities exceeds 0.01 nats. A disagreement where either
  margin is smaller is a near-tie and is numerical.
- The Kullback-Leibler divergence of the partner's field from `python-spu`'s exceeds
  0.001 nats, taken over the union of the two top-k sets with the remaining mass of each
  held as one outcome.

**At the token level**, both SPUs sample with the shared sampler of section 5 from the
same derived seeds, so their streams agree until a draw departs. The first departing
position is recorded with both fields at it, and the departure is substantive exactly
when that position differs substantively by the distribution level. A departure at a
position that does not is a draw falling between two fields that agree within the
numbers above, and it is numerical.

**Every position is reported, and substantive is a label on it, never a filter.** A
report carries every position's measures, so a reader can apply a different line to the
same record without a second run.

**The two numbers are elections, and they are revised only before a run.** 0.01 nats of
margin is a probability ratio of about 1.01 between the top two tokens, well above what
reordered FP32 arithmetic moves, and 0.001 nats of divergence is far above the same.
Both are the operator's to confirm on this document, and a later run that wants
different numbers states them in its own charter before it runs.

## 8. The environment

**Every package is pinned to an exact version and a hash.** The build installs from a
lock that carries a hash for every file, and an install that meets a file without one
refuses. A range, `torch>=2` or `transformers>=5,<6`, is not a pin, and the prototype's
ranges are replaced by the lock.

**The interpreter is pinned.** One CPython version per build, named in the lock. A build
under another interpreter is another build.

**The core imports the standard library alone, and the engine is the one addition.** The
channel ends, the wire, the session, the seed and the sampler's arithmetic are standard
library code. The engine is the package set the serving version requires, `torch` and
`transformers` for the first. `blake3` stays, because the Rust SPU's weights hash is
blake3 and admission computes it. `pydantic` is dropped once the oracle proves the wire,
since a second model of the payloads beside the oracle's would be a transcription the
suite exists to avoid.

**The import set is a test, and serving depends on it.** After the model loads, the
modules the process holds are compared with the declared set, and a module outside the
set refuses to serve. The test that proves it is perturbation-verified: an extra import
added at load must fail it, and the suite records that it does. This is the Python
counterpart of the rule of 2026-09-23 that nothing enters a binary unless operations
require it.

## 9. The versions

**The first version is `transformers` eager at FP32, one CUDA device, Qwen2
safetensors.**

**Each later version is a separate binary, with its own locked environment, and a
separate deployment under the tuple**, crossed one axis at a time against the one before
it. Epic #726 lists them: `llama-cpp-python` pinned to the Rust SPU's llama.cpp commit
and build flags, the control, first, then the attention kernels, the precision, a
minimal variant with the forward written in plain torch, and the device. None is
chartered by this document, and each extends it when it is built.

## 10. What this document does not carry

**The SPU's self-reported identity.** An SPU naming its implementation and its lock's
hash at admission would change the admission or measurement vocabulary in `weaver-types`
and what the harness records. It waits until it can be coordinated with the olympus
seat, on the operator's ruling of 2026-09-28, and section 1 states what names the
implementation until then.

**A per-agent binding of the SPU**, so two implementations could serve one box side by
side. `spu-binary` is admin-wide today, and that is a later design question.

**The comparison cells.** Their declarations, predictions and falsifiers are the
deployment-tuple charter's, per Document Format section 2, and this document supplies
only the line of section 7 they read against.

**The Rust SPU's behaviours themselves.** Those are `weaver-spu-Spec`'s, and this
document cites them.
