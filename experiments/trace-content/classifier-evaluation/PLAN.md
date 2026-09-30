# The classifier evaluation: plan

A plan, reviewed as a plan before any candidate is fitted, and read by no gate. Nothing
below has been run. It settles the protocol that the classifier sketch,
`docs/project/sketch-the-trace-content-classifier.md`, section 4 drafts and section 5's
protocol cell sends here, and a further finding against the protocol is answered in this
document. The measurement it follows is `experiments/trace-content/label-split/`, which
counts the positions and makes the case for building a classifier. This plan chooses
between candidates and is not that case.

## 1. The data

**The positions are our own per-action traces**, because the deployment plays one action
per tool call and the benchmark's published results are single-shot programs. The first
are the rusty runs of `herobench-agents-2026-09-29` on the shared bulk store,
Qwen2.5-7B-Instruct on the Rust SPU playing HeroBench's level-1 crafting tasks. Its
counted pair, session `s-rusty-b`, holds 978 positions of the kinds section 2 names over
40 turns. That is one session of two runs. Section 4 cuts by session into three splits
and section 8 requires at least 10 sessions in each of the two held out, so the corpus
needs at least 50 sessions before any fitting, at least 49 more than the one in hand,
each named by its deposit when it lands. The single-shot corpus of the label split is
not used to fit or to score.

## 2. Positions and the input at each

A labeled position is an event and a span of its payload, per the sketch's section 2: a
prose line or a program statement of `message.assistant`, an action's request on
`tool.call.started`, or its answer on `message.tool_result`. The run's `score` event is
a position of the computable share, and no candidate reads it.

**The input at a position is what the model was shown**, the accumulation of the
recorded contributions from the identity prefix, with every recorded flush and elision
replayed, then the generation cut at the span's end, and for a span on a tool result
that result's content cut at the span. Nothing any organ authored about the generation
is in it.

**The window is that input cut from the left to a bound fixed now**, the span's own
event kept whole. The bound is the smaller of two:

- **The seam's frame.** The classify seam carries the serialised `LabelDirective`, its
  JSON wrapper and escaping included, and a frame is at most `MAX_ENVELOPE_BYTES`,
  65,536 bytes, in `weaver-types`, the bound `weaver-spu-Spec` section 11 states for the
  classify channel, which carries no segment series. The bound is measured on the
  serialised directive and never inferred from the raw window's length.
- **The artifact's positions.** The window's token count, in each candidate's own
  tokenizer, is at most the smallest position limit among the candidates.
  `ModernBERT-base-zeroshot-v2.0`, the one on the box, declares 8,192. The others'
  limits are read from their artifacts when fetched and recorded here before fitting.

The bound, and each position's serialised size and token count under it, are recorded in
the deposit beside the labels.

## 3. Labels

Three predicates, each its own binary decision per position: the span recites the game
dump, the span states a plan, and the span contradicts what was recited. A position may
hold more than one. **The labels come from outside every candidate**: no candidate, and
no model of a candidate's family, labels a position it is scored on, and the labels'
source is recorded beside them. Who labels is the first open cell.

**Labeling follows a rubric merged before any position is labeled**,
`experiments/trace-content/classifier-evaluation/RUBRIC.md` beside this plan and its own
act. It holds:

- The three predicates' definitions, with their boundary cases enumerated: a recited
  fact that is wrong, a plan phrased as a question, a contradiction of an earlier plan
  rather than of the dump, and an action narrated as done.
- A second labeler over a fifth of the positions, drawn at random by session and
  recorded.
- A minimum agreement, Cohen's kappa per predicate between the two labelers of at least
  0.6, below which labeling stops and the rubric is revised before it resumes.

Until the rubric is written it is the fourth open cell.

## 4. The split

**By session, never by task, run, line or result set.** Every session falls whole in one
split, because the input at a position accumulates the session's earlier contributions,
per section 2 and `weaver-trace-PRD` section 3.2, so two tasks of one run or of one
session share inputs and cannot sit in different splits.

**Three splits, each with one use.** The training split fits each candidate and chooses
its cutoffs. The selection split computes every candidate's key and the order of section
8. The test split is read once, for the selected candidate alone, to report its interval
and apply section 8's floor.

**The allocation is a procedure.** The sessions are listed in order of their names and
shuffled by `random.shuffle` of Python's `random.Random`, a stream of its own seeded
once with 20260930, distinct from section 6's. Of the n sessions, the first floor(0.2 n)
in the shuffled list are the selection split, the next floor(0.2 n) the test split, and
the remainder the training split, which takes whatever the rounding leaves. The
allocation, the seed and the interpreter's version are recorded in the deposit before
any candidate is fitted, and a score on positions a candidate was fitted on is not
reported.

## 5. Fitting and thresholds

Each candidate is fitted on the training split, in the one shape section 7 finds the
seam can serve: **one softmax head over the eight combinations of the three
predicates**, each label one combination. A position's probability for a predicate is
the sum of the probabilities of the combinations that hold it, which gives each
predicate its own decision out of one forward. **The threshold is a procedure.** For
each candidate and predicate, the cutoff is the value of the predicate's probability
that maximises F1 on the training split, over the distinct probabilities the training
positions take. A tie between cutoffs goes to the largest, and a position whose
probability is at or above the cutoff counts positive. F1 is zero where a cutoff
predicts no positive, precision being undefined there. The cutoff is recorded, and none
is chosen on the selection or test splits.

**Each candidate's fitting record is written before it is fitted** and recorded in the
deposit: the artifact and its revision, the preprocessing from the window of section 2
to the model's input, the hyperparameters, the optimiser and its schedule, and the
training seed. The recipe belongs to the record rather than to this plan, because it
differs by candidate, and a fitting with no record written before it is not reported.

## 6. Scoring

The candidates are compared per predicate on precision and recall over the selection
split's positions. No figure pooled across the predicates is reported.

**Every figure carries its uncertainty, by a fixed procedure.** Each F1 per predicate
has a percentile bootstrap interval over the sessions of the split it is read on. The
generator is Python's `random.Random`, the standard library's Mersenne Twister, one
stream seeded once with 20260929, with the interpreter's version recorded in the
deposit. A split's sessions are listed in order of their names, and a resample is as
many draws of `randrange` over that list as the split holds sessions, with replacement.
The stream draws 1,000 resamples of the selection split in sequence, then 1,000 of the
test split, before any candidate is scored. **Every candidate and every predicate is
scored on the same resamples of a split**, so the intervals compare candidates on one
draw and every compliant run draws the same sessions. The interval runs from the 2.5th
to the 97.5th percentile of the resampled F1, and its lower bound is the 2.5th
percentile. The unit is the session and not the position, for the reason section 4
splits by session: positions of one session share inputs, and treating them as
independent would draw an interval narrower than the data supports.

## 7. Serving

**The eligible configurations are the ones the harness can serve as built**: one
classify arm, one admitted artifact and one head, whose scores are one softmax over the
artifact's labels, per `weaver-harness-Spec` section 6 and `weaver-spu-Spec` section 11.
Section 5's head over the eight combinations is that shape. An encoder with one head per
predicate needs more than one classify arm, a multi-label head needs a score per label
rather than one softmax, and Kev's questions ride the ask, a contract change, per the
sketch's section 3. Each is out of the eligible set until the act that serves it lands,
and the plan budgets nothing for them. Each is measured and reported beside the eligible
results where it is fitted, since the measurement is what argues for that act.

**Per answer.** Each candidate's latency is measured at the window's bound, on the
device it would serve from, and its maximum is recorded, not a percentile. One answer
past `CLASSIFY_ANSWER_BOUND_MS` in `weaver-harness`, 30,000 ms, retires the classify arm
for the rest of the run, per `weaver-harness-Spec` section 6.

**Per turn.** The routing stage asks about every position a turn produces, one ask at a
time, the harness blocking on each, and an eligible configuration asks once per
position. A turn's classify cost is the sum over its positions of their asks, taken at
the maximum positions per turn and recorded beside the median. The preliminary pair's
turns run to a median of 4 and a maximum of 132, and section 8's gates recompute both
over the fitting corpus. The number the per-turn cost is held to is the third open cell.

The classifier's own deployment tuple is recorded beside its results, and it serves off
the decoder's weights and off the decoder's device.

## 8. Gates, then the selection rule, declared before fitting

**No selection is made unless every gate holds**, and the report names each gate that
failed:

1. **Label support.** Every predicate has 20 positives and 20 negatives in each of the
   three splits, the plan's floor: below it a single label moves precision or recall by
   more than five points. A predicate short of it fails the gate, its shortfall reported
   by split, and more labelled sessions are owed.
2. **Sessions held out.** The selection split and the test split each hold at least 10
   sessions. The bootstrap resamples sessions, one session yields an interval of zero
   width, and fewer than 10 give too few distinct resamples for a 95 per cent interval
   to mean what it says.
3. **Serving bounds over the fitting corpus.** The maximum positions per turn and every
   candidate's maximum answer latency are recomputed over the corpus the fitting uses,
   not the preliminary pair, and the per-turn budget is set against that maximum.
4. **The rubric.** `RUBRIC.md` is merged and the two labelers' agreement meets its floor
   for every predicate.
5. **The fitting records.** Every candidate's fitting record of section 5 is written
   before its fitting and stands in the deposit.

**The selection is a procedure over one key.** Among the eligible candidates, those with
every observed answer under 30,000 ms and a per-turn cost within the budget:

1. **The key.** For each candidate, the key is the minimum over the three predicates of
   the lower bound of its F1 interval on the selection split, section 6's 2.5th
   percentile.
2. **The order.** Candidates are ordered by key, highest first, then by per-turn cost at
   the maximum positions per turn, lowest first, then by name. The order is total, so no
   set of candidates can cycle, and the first is the selected candidate.
3. **The test.** The test split is read once, for the selected candidate alone: its
   interval per predicate, and its key computed the same way on the test split.
4. **The floor.** The selected candidate is adopted only if its test key is at least
   0.5. F1 is a harmonic mean and never falls below the smaller of precision and recall,
   so a key under 0.5 means that on some predicate, at the interval's low end, one of
   the two is under one half: the classifier is wrong more often than right on that
   predicate's positives or on its positive calls. Under the floor none is adopted, and
   no other candidate is read on the test split in its place.
5. **None.** With no eligible candidate, none is selected, and the report says which
   bound each one missed.

Precision, recall, F1 and the intervals are reported for every candidate and every
predicate on the selection split, and for the selected candidate on the test split. The
selection split's results are read only after the allocation, the bound, the cutoffs,
the budget and the gates are recorded, and the test split only after the order has named
its candidate. **This procedure stands as merged and changes only by an act of its
own.**

## 9. Deposit

A deposit under `weaver-testing/` on the shared bulk store, named for the date the
fitting starts. It holds the positions with their inputs' sizes, the labels and their
source, the allocation, each candidate's thresholds, its selection-split predictions and
latencies, the selected candidate's test predictions, the tuples, and `SHA256SUMS`. The
result note goes beside this plan and in the deposit.

## 10. Open cells

- **Who labels the judgmental positions**, the operator's. The plan requires only that
  no candidate and no model of a candidate's family does.
- **Each candidate's serving memory on the Ada**, a measurement, Kev's being stated as
  about 9 GB on its model card and 17 GB in its repository.
- **The per-turn budget's number**, the operator's, set against the positions per turn
  the traces show, before any candidate is fitted.
- **The rubric**, `RUBRIC.md`, its own act, merged before any position is labeled,
  holding what section 3 requires of it.
