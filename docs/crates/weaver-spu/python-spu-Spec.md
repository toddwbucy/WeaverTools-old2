# python-spu - Spec

**Status:** MERGED. In `main` and the source of truth.

**Date filed:** 2026-09-28
**Document ID:** `python-spu-Spec`
**Parent:** `weaver-spu-PRD`
**Editorial:** Per the Working Rules.
**Landing PR:** #729

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

**A second implementation of one organ's decode role, honoring the same contracts.**
The organ is the one `weaver-spu-PRD` section 1 charters: it holds a model on the device
for as long as the worker that forked it lives, and it answers the harness across a
two-initiator channel. `python-spu` is party to the two contracts the Rust decode
process is party to, `weaver-harness-spu-contract` for residency and
`weaver-harness-spu-decode-contract` for the token seam, and it honors each as written.
The contracts name no language, no type and no module, so the seams admit a second
implementation as they stand and neither changes for it.

**The classify role is not this implementation's.** The label seam is served by a
process of its own, `weaver-spu-classify`, which the harness launches from its own
binary path, per `weaver-spu-Spec` section 11, so `spu-binary` does not reach it. A
declaration electing classify under `python-spu` is served by that process as it is
today. `python-spu` accepts the instruction's `classify` member as the wire admits it
and acts on none of it, as the Rust decode process acts on none of it.
`weaver-harness-spu-classify-contract` binds that process and not this one, and a Python
classifier with its own binding is a later version, per section 9.

**It writes no trace, as the Rust SPU writes none.** The harness is the sole writer, per
`weaver-harness-trace-contract` and `weaver-spu-PRD` section 2. What `python-spu`
reports crosses the token seam in the shapes the decode contract fixes, and the harness
authors the records from it. The trace contract binds this implementation through that
route alone: a record the harness writes from a `python-spu` report verifies under the
trace contract exactly as a record written from a Rust report does.

**Nothing else in the agent changes, and nothing else learns which SPU served.** Admin
launches whatever file its `spu-binary` configuration names, and the harness hashes that
file into `weaver_binaries` at both ends of a run. `spu-binary` is admin-wide, so one
implementation serves a box for the length of a run.

**What served is named by two digests, and neither waits on the SPU reporting its own
identity**, which section 10 defers. The first is the `spu-binary` hash. Section 2 ships
`python-spu` as one file whose first line names the pinned interpreter by absolute path,
so that hash covers every line of `python-spu`'s own code and fixes which interpreter
runs it, the interpreter's version being the toolchain reader's to record. The second is
the digest of the installed tree section 8 defines, which covers the engine as installed
rather than as the lock says it should be. The box facts carry it beside the lock's
hash, and the matrix's record carries it once section 5's second precondition reaches
it.

**It does not replace the Rust SPU.** Both serve, and the record says which. Under the
deployment tuple a different implementation is a different kernel stack, and so a
different deployment, which is why the two are compared rather than required to agree
bit for bit.

## 2. Where it lives

    python-spu/
      src/python_spu/    the SPU: the channel ends, the wire, the session, the engine,
                         the family and the sampler
      tests/             the conformance suite and the behaviour tests
      oracle/            a Rust program linking the workspace crates, which answers
                         the suite with the Rust code's own results
      scripts/           the model smoke test and the build of the one file below

**It ships as one file.** The build packs `src/python_spu/` into a zipapp with the
standard library's `zipapp` module, its first line naming the pinned interpreter by
absolute path, and admin's `spu-binary` names that file. A launcher importing a package
from elsewhere would leave the package out of the hash the harness takes, so two runs of
different code could report one provenance. The zipapp holds no third-party package: the
engine is imported from the environment, whose installed tree section 8 digests. The
file is built, not committed.

**The oracle depends on the workspace crates at a pinned commit and on no copy of
them.** It is a Rust program outside the workspace, so it is not a member and its
manifest names `weaver-spu`, `weaver-types` and `weaver-traits` by the repository and a
commit. The suite therefore reads what the Rust code computes rather than a
transcription of it, and a copied source tree would be an archive directory, which
Working Process section 1 keeps out of the tree.

**Nothing under `crates/` changes for it.** The pyworker inside `weaver-harness` is the
precedent for Python in this tree and not the model for this one: that is Python behind
a feature of a crate, and this is a separate program behind the organ's seams.


### 2.1 What the tree holds: a prototype, and where it falls short

**`python-spu/` holds the prototype built on thinkpad on 2026-09-28, carried as it
stood**, per Working Process section 6's rule that a carry is not a hardening. It is a
lab instrument until the acts that close the gaps below have landed, and no verdict
rests on it. The carry changed what landing needed and nothing more: the oracle's
manifest names the workspace crates by the repository and a commit instead of a copied
tree, the smoke report reads that commit from the manifest, and the README lost a home
path and a device identifier. Its suite passes on the CPU against the crates at the
pinned commit.

**Where it falls short of this document**, each gap named with the section it falls
short of:

- Section 1: admission refuses an instruction carrying a `classify` member, answering
  `artifact_unreadable` (`server.py`), where section 1 has the member accepted and left
  unread.
- Section 2: it installs as a package with entry-point scripts, not as one zipapp, so a
  `spu-binary` hash would name a launcher. It also carries an experimental ModernBERT
  classifier and its entry point, which section 1 scopes out of this implementation.
- Section 3 and `weaver-harness-spu-decode-contract`: a cancel arriving during a
  generation is consumed and never answered, the generation's close being sent without
  the cancel exchange's `at_rest` close (`server.py`), so a harness waiting on the
  cancel can wait forever.
- Section 3.1, the `knobs` row: `context-capacity` is bounded below 2^64 rather than
  2^32 (`server.py`). The Rust resolution holds it as `u32` and refuses a value at or
  past 2^32 as `NotACount`, where the prototype passes it to the engine and refuses it
  late, or admits it.
- Section 3.1: its oracle answers five operations, `session`, `seed`, `measure`,
  `render` and `round`, and a transport test over the oracle's descriptor. Every other
  operation the walk names is unbuilt.
- Section 4: the engine loads at FP32, not BF16.
- Section 5: the sampler is the native engine's, ported and proven as section 5 says,
  and it samples in pure Python at about 120 ms a token over a Qwen2.5 vocabulary on
  thinkpad, the softmax's glibc `expf` over every logit and the partition over every
  index being most of it.
- Section 8: its manifest carries version ranges and no hashes, the interpreter is a
  floor rather than a pin, `pydantic` is in the core, the Python `tokenizers` it has run
  under is 0.23.2 rather than the release built on the 0.21.4 crate, nothing digests the
  installed tree, and there is no import-set test.

**The list names the gaps known at the carry, and it is not a walk.** Three of them were
found by the review of the carry itself. The hardening act walks every exchange and
every refusal of `weaver-harness-spu-contract` and `weaver-harness-spu-decode-contract`
against the prototype, per H3's rule that a seam is exercised against its contract's
failure cases. It starts from the cancel gap's sibling, which the walk judges against
the contract's exchange rule: `server.py` answers an ask arriving mid-generation with a
bare `{'kind': 'out_of_order'}` message. Epic #726 carries the walk as one item.

## 3. What it carries identically

Every row names the `weaver-spu-Spec` section that states the behaviour, and the
instrument that proves `python-spu` carries it the same. An oracle row runs the Rust
code at the pinned commit and compares its answer with Python's. A contract row is a
check the named contract's Conformance section lists.

| Behaviour | `weaver-spu-Spec` | Proven by |
| --- | --- | --- |
| The two channel ends at descriptors 3 and 4, close-on-exec set on both, the dumpable flag cleared before the engine's runtime is imported | 2 | a process test |
| The `SOCK_SEQPACKET` envelope and the segmented frame, per `weaver-organ-channel` | 2 | oracle, over a socket pair |
| Every payload of the two contracts it is party to, accepted and refused, and the instruction's `classify` member accepted and left unread | 2, 9 | oracle, serde round trips both ways |
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

**A behaviour this implementation does not yet carry is refused at admission, never
dropped silently.** An election the declaration makes and `python-spu` cannot honor
refuses the load naming it, per `weaver-spu-PRD` section 13.7's rule that a load
granting an election it cannot honor fails at its cheapest moment. The table is the set
this document binds, and a row whose instrument is not yet built is a row the
implementation does not advertise.

### 3.1 The model-free surface, walked

The table above names behaviours. This one walks the code: every public item of
`weaver-spu` outside its engines, taken from the crate at the commit the oracle pins,
with the oracle operation that compares `python-spu` against it or the reason it is
excluded. Each module is `pub` in the crate's root, so every operation calls the Rust
code itself from outside the crate, and nothing under `crates/` changes for it. Two rows
are mirrors rather than calls, and each says why: the item they compare against is
reachable only through a loaded model. The walk is what closes the conformance class. A
later finding that names an item is answered by its row, and an item added to the crate
joins the walk in the act that moves the pin to it.

| `weaver-spu` items | Oracle operation, or why excluded |
| --- | --- |
| `artifact`: `resolve`, `pin`, `PinnedArtifact` and its accessors, `names_a_split` | `artifact`, over a fixture directory: the resolved paths, the split judgment, each refusal |
| `artifact`: `read_header`, `ArtifactHeader`, `Container` | `artifact`: the header of a safetensors directory. A GGUF container is refused at admit, a container this implementation does not serve |
| `artifact`: `weights_hash`, and `residency`: `WeightsHash` and its sentinel | `artifact`: the blake3 digest over the fixture, and the sentinel |
| `channel`: `adopt`, `Inherited`, `EntryFault` | excluded from the oracle: they read the process's inherited descriptors, which no call can hand over. A process test, per section 3 |
| `channel`: `LifecycleChannel`, `DecodeSocket`, `lifecycle_from_owned`, `decode_from_owned`, `send`, `recv`, `send_octets`, `recv_octets`, `try_recv_octets`, `as_fd`, `ChannelFault` | `frame`, over a socket pair with the Rust code at one end: envelopes, segmented frames, truncation and closure faults |
| `channel`: `ClassifySocket`, `adopt_classify` | excluded: the label seam is not this implementation's, per section 1 |
| `decoder::backend`: `TokenId`, `DecodeFault`, `FlushMechanism`, `for_container` | `session` for the faults and the flush mechanism, `artifact` for the container judgment |
| `decoder::backend`: `Backend` | excluded as a trait: it is the engine's seam, and the engine is this implementation's own, per section 4. The `session` operation drives the Rust session over a scripted backend so the session's rules are compared without an engine |
| `decoder::session`: `Session` and every method, `Stopped`, `Generated`, `StopCondition`, `CancelPoll`, `NeverCancels`, `SamplerBuild`, `PositionedSinks` | `session`: one script of opens, appends, generations, re-feeds, flushes, elisions and cancels run through both sessions over a scripted backend, the resident sequence and every answer compared |
| `family`: the `Family` trait's rendering methods, `render_each`, `render_template`, `common_role_name`, `text_content`, `fold_system_into_first_user`, `RenderRefusal` | `render`: the identity prefix, each delta, and each refusal |
| `family`: `Family::parse`, `scan`, `Markers`, `Parsed`, `Content`, `Unrecovered`, `has_unrecovered_call`, `text` | `parse`: an emission's canonical text and tool-call blocks over plain text, valid calls, and malformed and unrecovered call fragments. `Generation::content` carries what the parse chose, and a wire round trip proves only its encoding |
| `family`: `Declaration`, `permits_truncation`, `shards_across`, `FamilyName`, `lookup`, `select`, `same_key`, `normalised_key`, `judge_width`, `FamilyRefusal` | `registry`: selection by architecture and marker set, the key's normalisation, the width judgment, each refusal. Where the Rust code selects a family this implementation does not serve, this implementation refuses at admit, and the operation asserts it refuses exactly there |
| `family::qwen2`: `renderer`, `Qwen2` | `render` and `parse`, for the first version's one family |
| `family::gemma4`, `gpt_oss`, `llama`, `mistral3`, `phi`: each renderer and its type | excluded: families the first version does not serve, refused at admit per the `registry` row. Each joins the `render` and `parse` rows when a version serves it |
| `family::modernbert`: every item | excluded: the classify role, per section 1 |
| `measurement`: `log_sum_exp`, `entropy_bits`, `surprisal_bits`, `field` | `measure`, over supplied logits |
| `measurement`: `Accumulator` and its methods, `Signals`, `absent`, `steps`, `NonEmpty` and its methods | `accumulate`: a sequence of records, abandons and a finish, the signals compared, absence included |
| `measurement`: `PromptPartition` and its accessors, `PartitionDefect` | `partition`: offsets and text lengths, accepted and defective |
| `readout`: `Reduction` and its methods | `reduce`, over supplied activations and norms |
| `readout`: `ReadoutElection`, `judge`, `judge_column_ask`, `ReadoutRefusal`, `TapOutcome` | `registry`: each judgment against a declaration |
| `readout`: `Tap` | excluded as a trait: the tap reads the engine's hidden states and is the engine's own |
| `residency`: `promote_stop_conditions`, `StopSet` | `stops`, over supplied stop inputs |
| `residency`: `Headroom`, `AdmitRefusal` | the wire rows of section 3 for the refusals. The headroom judgment needs a device, per the `gpu` row |
| `residency`: `Residency` and its methods, `Admission` and its accessors, `Resident`'s `model`, `open_session`, `declared_eos` and `stop_set`, `LoadedModel` | excluded from the oracle: each needs a loaded model or a device. The process tests and the contract rows of section 3 |
| `residency`: `Resident::tokenize`, `Resident::detokenize` | `tokenize`, a mirror. Both reach the native engine's `tokenize` and `detokenize`, which are `pub(crate)` and need a loaded model, so the operation calls `tokenizers` 0.21.4, the version `weaver-spu` links, with the two calls `native.rs` makes, `encode(text, false)` and `decode(ids, false)`, against the artifact's `tokenizer.json`. This implementation pins the Python `tokenizers` release built on the 0.21.4 crate, so both sides run one tokenizer, and the operation compares both directions on the rendered prefix and every delta |
| `sampling`: `Disposition`, `is_frozen`, `Knobs`, `EffectiveKnobs`, `SessionParameters`, `EffectiveSessionParameters`, `tunable_names`, `resolve`, `KnobRefusal` | `knobs`: resolution against supplied tunable values, and each refusal |
| `sampling`: `derived_seed` | `seed`, and section 8.5's test vectors |
| the native engine's `sample` | `generation`, `probs`, `select`, `weighted` and `rng`, mirrors, per section 5: it needs a loaded model, so the operations run the code it runs at the pinned revisions. `generation` is candle's `LogitsProcessor` with the engine's penalty over a whole generation, `probs` the probability vector's bits, `select` the whole index order `select_nth_unstable_by` leaves, `weighted` rand's `WeightedIndex` over scripted words, and `rng` the generator's words |
| `decoder::native`, `native_pair`, `gguf`, `gguf_tap`, `gpu` | excluded as a whole: the engines, their taps and the device judgment, which section 4 makes this implementation's own, the native sampler excepted per the row above |

## 4. What is its own

**The engine.** The first version runs Hugging Face `transformers` in eager mode at
BF16, loading with `torch_dtype=bfloat16`, on one CUDA device, serving the Qwen2 family
from a local safetensors directory. It makes no download, runs no remote code, converts
no quantization, falls back to no other device, and shards nothing. Section 9 names the
versions after it.

**The kernel stack.** The kernels are PyTorch's and the CUDA libraries PyTorch brings
with it, its own cuBLAS and cuDNN among them, not the ones the Rust SPU links. They are
recorded beside the environment lock, since two runs on one card under two kernel
stacks are two deployments under the tuple, and the matrix's engine-library reader
does not reach them until section 5's second precondition lands.

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

**The first version's partner is the Rust native engine**, candle on the same
safetensors directory, which maps the weights at BF16 (`native.rs`, the single-device
load's `DType::BF16`), on the Planner's election of 2026-09-28 recorded on #726. It is
the one pairing that holds both the weights and the dtype fixed without changing
`crates/`, since llama.cpp computes on quantized blocks that no dequantized forward
reproduces. Its chain, from `crates/weaver-spu/src/decoder/native.rs` and candle's
`LogitsProcessor` at the pinned revision, is this:

1. The repetition penalty over the last `repetition_window` resident tokens, as candle's
   `apply_repeat_penalty` computes it, skipped where the penalty is 1 or the window 0.
2. Temperature zero or below is the argmax, and nothing below applies. The cutoff is
   `native.rs`'s own, which builds the sampler by `from_sampling`, and not the 1e-7 of
   candle's `LogitsProcessor::new`, which the engine does not call, so a temperature
   just above zero divides the logits and samples.
3. The logits divided by the temperature, then the softmax.
4. Top-k where k is above zero, then top-p. A top-k of zero disables that gate.
5. The draw, `WeightedIndex` over the remaining weights, from `rand`'s `StdRng` seeded
   by `seed_from_u64` with the whole 64-bit derived seed, at the `rand` version the lock
   pins, 0.9.5, whose `StdRng` is ChaCha12 by `rand_chacha` 0.9.0.

**The GGUF engine's chain is never ported to Python.** It runs penalties, the truncating
filters, then temperature, then llama.cpp's own draw from a seed folded to 32 bits. The
later control version, `llama-cpp-python` against the Rust GGUF cells, uses llama.cpp's
sampler natively and inherits that chain rather than reimplementing it.

**The sampler reads more than the logits, and the port is proven over whole
generations.** Within one generation the native engine's draw at a position reads five
things: that position's logits, the knobs, the derived seed the generation's sampler
was built from, the state of `StdRng` after every draw before it in the generation,
and the resident tail the penalty reads, which grows by each drawn token. The penalty
visits each distinct token of the last `repetition_window` resident tokens once,
dividing a non-negative logit by the penalty and multiplying a negative one, per
candle's `apply_repeat_penalty`. A single draw over fixed logits tests none of the
stream, so the oracle gains an operation over a whole generation: it takes the seed,
the knobs, the resident tail at the generation's start and a sequence of logits
vectors, one per position, and returns the sequence of draws candle's own
`LogitsProcessor` and the engine's penalty produce, appending each draw to the tail
before the next. The suite requires Python's sequence to equal it over many seeds,
knob sets and sequences. The edges are named cases: near-ties, a temperature at zero
and one just above it, a top-k of zero and one at or past the vocabulary, a top-p of
one and one at or past the mass top-k kept, a tail holding repeated and unrepeated
tokens, a token entering and leaving the window at its edge, a penalty of one and a
window of zero, each of which skips the penalty, and sequences long enough that the
generator's state carries across many draws. The arithmetic is ported in candle's
order and precision, since identical inputs give identical draws only where the
arithmetic is the same. **The order the filters leave the candidates in is part of the
draw.** Candle keeps the top-k by `select_nth_unstable_by`, whose partition decides
the order `WeightedIndex` walks, so the port reproduces that order and not only the
set.

**The arithmetic is candle's CPU path on the partner's host, so bit for bit holds on one
box.** The native engine builds the sampler's input as a host tensor (`native.rs`,
`Tensor::new(logits, &Device::Cpu)` in `sample`), so the softmax runs candle's CPU f32
code and never a device kernel. Three facts of that code bind the port. The softmax's
sum is `cpu::vec_sum`, which takes an AVX2 order of four accumulators of eight lanes
where `std::is_x86_feature_detected!("avx2")` holds and a sequential order where it does
not, so the port detects AVX2 the same way and reproduces whichever order the host
takes. The exponential is Rust's `f32::exp`, which on Linux is glibc's `expf`, so the
port calls that `expf` through `ctypes`, keeping the core in the standard library, where
a vectorised `exp` would differ in the last bit. And `&logits / temperature` is candle's
`affine(1 / temperature, 0)`, the reciprocal taken in f64 and cast to f32, then a
multiply, so the port never divides. The two SPUs therefore agree draw for draw where
they share one glibc and one CPU feature set, which the comparison's cells already
assume, and the box facts record the host's `avx2` flag and its glibc version for both.

**The proof reads the bits, not only the draws.** A one-ulp slip in a probability moves
a draw only when the uniform lands on the boundary it moved, which a run of draws rarely
shows. So beside `generation`, the oracle's `probs` returns the probability vector's
bits for a supplied penalty, temperature and logits, `select` returns the whole index
order the partition leaves, including inputs an adversary built to drive it into
`median_of_medians`, `weighted` samples `WeightedIndex` from scripted words so a choice
can land on a cumulative weight on purpose, and `rng` returns the generator's words.
Core's partition is read at the rustc commit `rust-toolchain.toml` pins,
47611e16044c68ef27bac31c35fda2ba1dc20b73: `library/core/src/slice/sort/select.rs`,
`shared/pivot.rs`, `shared/smallsort.rs` and `unstable/quicksort.rs`, whose
`partition_lomuto_branchless_cyclic` a `usize` slice takes.

**Where exact draws prove impossible, the comparison falls back to distributions and
says so.** If a draw cannot be reproduced exactly, the suite records which operation
departs, the comparison of section 7 is made at the distribution level alone, and every
cell it produces states that token streams are not comparable.

**Two preconditions before any comparison run.** The first: the native engine is
confirmed to load the safetensors directory the Python SPU serves, and the declaration
that selects the native engine for it is recorded, since which backend serves is a
property of the artifact decided at admit, per `weaver-spu-Spec` section 4.1.

**The second: the determinism matrix's provenance readers are extended, as their own act
under `determinism-matrix-Spec`, because three of them assume the Rust GGUF deployment
and no comparison run could exit 0 on either side without them.** The weights reader
hashes one file, so every safetensors directory reads unreadable, the Rust native
partner's included, and it becomes a directory digest over the sorted relative paths and
each file's sha256, a symbolic link refused. The engine-library reader runs `ldd` on the
SPU binary and looks for llama.cpp's libraries, which names nothing a Python engine
loads, since PyTorch opens its kernels at run time. It reads the libraries the loaded
SPU holds instead, and how is that act's to elect: the obvious source, the process's own
mappings under `/proc`, is closed to an unprivileged reader by the dumpable flag both
SPUs clear at entry, per `weaver-spu-Spec` section 2, and reopening it would undo that
section's claim. The toolchain reader reads `rustc` alone, and it reads per
implementation: `rustc` for the Rust SPU, and the interpreter's version with the lock's
hash for this one. Epic #726 carries the act as a stage C item, and no document here
changes the matrix.

## 6. What conforms means

This section is the statement of the conformance suite's pass, made before the suite is
hardened, per Working Process section 6.

**A pass certifies that `python-spu` answers every question the Rust code can answer
without a model the way the Rust code answers it**, at the commit the oracle pins. Those
questions are every row of section 3.1 that names an oracle operation, the sampler's
sequence of draws over a whole generation among them, per section 5. It also certifies
every check that section 8 of `weaver-harness-spu-decode-contract` lists, and the
ordering and failure cases of `weaver-harness-spu-contract` sections 3 and 5, run
against `python-spu` itself.

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
- The label seam, which the classify process serves and this implementation does not.
- Speed.

## 7. What a substantive difference is

Stated before any comparison run, per the same rule, so that no result chooses its own
threshold. The comparison holds the weights, the dtype, the knobs, the declared seed and
the prompts fixed, and serves them from each SPU in turn. **Fixing the dtype does not
fix the arithmetic.** Both sides compute at BF16, and each engine's accumulation and
reduction order, which BF16 rounding makes visible, is part of the implementation being
measured rather than a variable held apart from it. A difference therefore has one cause
in the sense the comparison needs, the implementation, and the implementation includes
its kernels.

**At the distribution level**, both SPUs are driven along one token path, the partner's
recorded path, with the re-feed drive of `weaver-spu-Spec` section 4.6, so each position
is read against the same context. The re-feed fixes the output path and not the input,
which each SPU tokenizes for itself, so the same context rests on the `tokenize` row of
section 3.1 and is checked in every run: each generation's token identifiers in are
equal on both sides, and a run where they differ is not a comparison. The run elects one
probability-field depth for both, at least two and never below the effective top-k,
which `weaver-spu-Spec` section 7.5 already refuses at admit. A position differs
substantively when any of these holds:

- The two fields name different top-1 tokens, and each SPU's own margin between its
  top-1 and top-2 log-probabilities exceeds 0.01 nats. A disagreement where either
  margin is smaller is a near-tie and is numerical.
- The two fields' top sets share no token.
- The divergence over their shared tokens exceeds 0.001 nats. Each field carries only
  its own top candidates, so the divergence is taken over the tokens both fields hold,
  each at its own probability, with each SPU's remaining mass held as one further
  outcome. That is a coarsening of the full distributions, so the figure is a lower
  bound on the full Kullback-Leibler divergence of the partner's distribution from
  `python-spu`'s, and a position under the line may still differ beyond it where the
  mass lies outside the shared set. The report carries the shared set's size beside
  the figure for that reason.

Each measure is read from a member the record already carries, so the comparison adds
nothing to either SPU's record but the elected depth:

| Measure | Read from | `weaver-spu-Spec` |
| --- | --- | --- |
| Entropy per position, over the whole vocabulary | the signal vector each generation carries | 6 |
| Top-1 token, and the margin to top-2 in log-probability | the probability field's first two ranks, as probabilities | 7.5 |
| The shared set, its size, and the divergence over it | both fields at the position, to the elected depth | 7.5 |
| The first departing position under the shared sampler | the token identifiers out of each generation | 6 |
| Whether the departure is substantive | both fields at that position, by the three tests above | 7.5 |

**At the token level**, both SPUs sample with the shared sampler of section 5 from the
same derived seeds, so their streams agree until a draw departs. Both runs elect the
same field depth, and up to the first departure their contexts are one context, so the
first departing position is recorded with both fields at it, read against the same
context, and the departure is substantive exactly
when that position differs substantively by the distribution level. A departure at a
position that does not is a draw falling between two fields that agree within the
numbers above, and it is numerical.

**Every position is reported, and substantive is a label on it, never a filter.** A
report carries every position's measures, so a reader can apply a different line to the
same record without a second run.

**The two numbers are elections, and they are revised only before a run.** 0.01 nats of
margin is a probability ratio of about 1.01 between the top two tokens, and a top-1 flip
inside it is a near-tie any rounding can move. 0.001 nats of divergence is chosen as the
line for a distribution's shape, and at BF16 the rounding of two kernel stacks may reach
it, which is the point of the next sentence: a label above the line says the two
implementations differ at that position, kernels included, and not why. Both numbers
are the operator's to confirm on this document. A run that finds many positions near
either line raises that as a finding before the next run, and a later run that wants
different numbers states them in its own charter before it runs, never in the report of
the run that prompted them.

## 8. The environment

**Every package is pinned to an exact version and a hash.** The build installs from a
lock that carries a hash for every file, and an install that meets a file without one
refuses. A range, `torch>=2` or `transformers>=5,<6`, is not a pin, and the prototype's
ranges are replaced by the lock.

**The interpreter is pinned.** One CPython version per build, named in the lock. A build
under another interpreter is another build.

**The installed tree is digested, because a lock states what should be installed and not
what is.** The digest is taken over the environment's site-packages directory: its
files' paths relative to it, sorted, each with its sha256, a symbolic link refused. It
is recorded beside the lock's hash, and with the `spu-binary` hash it is what section 1
names as what served.

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

**The first version is `transformers` eager at BF16, one CUDA device, Qwen2
safetensors.**

**Each later version is a separate binary, with its own locked environment, and a
separate deployment under the tuple**, crossed one axis at a time against the one before
it. Epic #726 lists them: `llama-cpp-python` pinned to the Rust SPU's llama.cpp commit
and build flags, the control, first, then the attention kernels, the precision, which is
`transformers` at FP32 crossed against the first version at BF16, a minimal variant with
the forward written in plain torch, the device, and a classifier serving the label seam
with its own binding. None is chartered by this document, and each extends it when it is
built.

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
