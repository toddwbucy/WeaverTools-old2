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
40 turns. That is one session of two runs, which admits no hold-out under section 4, so
several more sessions are owed before any fitting, each named by its deposit when it
lands. The single-shot corpus of the label split is not used to fit or to score.

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

## 4. The split

**By session, never by task, run, line or result set.** Every session falls whole on one
side, because the input at a position accumulates the session's earlier contributions,
per section 2 and `weaver-trace-PRD` section 3.2, so two tasks of one run or of one
session share inputs and cannot sit on different sides. Today's corpus is one session of
two runs and admits no hold-out, and the sessions owed in section 1 land before any
fitting. The split is recorded in the deposit before any candidate is fitted, and a
score on positions a candidate was fitted on is not reported.

## 5. Fitting and thresholds

Each candidate is fitted on the training split. Each candidate's output is normalised to
the three binary decisions: for Kev a `noul` question per predicate with its probability
thresholded, and for an encoder one head per predicate or a multi-label head thresholded
per predicate. **Every threshold is the one that maximises F1 on the training split**,
chosen once per candidate and predicate and recorded, and none is chosen on the held-out
split.

## 6. Scoring

The candidates are compared per predicate on precision and recall over the held-out
positions. No figure pooled across the predicates is reported.

**Each predicate needs 20 positives and 20 negatives on each side of the split**, the
plan's number: below it a single label moves precision or recall by more than five
points, which is larger than the differences the comparison is for. A predicate short of
it on either side is excluded from section 8's worst-predicate selection, its shortfall
is reported by side, and more labelled sessions are owed before it enters.

## 7. Serving

**Per answer.** Each candidate's latency is measured at the window's bound, on the
device it would serve from, over the held-out positions, and its maximum is recorded,
not a percentile. A candidate with any observed answer at or past
`CLASSIFY_ANSWER_BOUND_MS` in `weaver-harness`, 30,000 ms, is not eligible however it
scores, because one answer past the bound retires the classify arm for the rest of the
run, per `weaver-harness-Spec` section 6.

**Per turn.** The routing stage asks about every position a turn produces, one ask at a
time, the harness blocking on each, so a turn's classify cost is the sum over its
positions. In the counted pair the positions per turn run to a median of 4 and a maximum
of 132, and each candidate's per-turn cost is taken at the maximum positions per turn
the traces show, the median recorded beside it. The number the per-turn cost is held to
is the third open cell.

The classifier's own deployment tuple is recorded beside its results, and it serves off
the decoder's weights and off the decoder's device.

## 8. The selection rule, declared before fitting

1. A candidate is eligible when every observed answer is under 30,000 ms and its
   per-turn cost at the maximum positions per turn is within the budget the third cell
   sets.
2. Among eligible candidates, the one selected has the highest held-out F1 on its worst
   predicate, over the predicates that meet section 6's label support. Precision and
   recall are reported beside it for every predicate.
3. A tie on that figure goes to the lower per-turn cost at the maximum.
4. If no candidate is eligible, or no predicate meets section 6's label support, none is
   selected, and the report says which bound each candidate missed and which predicates
   fell short.

The rule stands as merged, and the held-out results are read only after the split, the
bound, the thresholds and the budget are recorded.

## 9. Deposit

A deposit under `weaver-testing/` on the shared bulk store, named for the date the
fitting starts. It holds the positions with their inputs' sizes, the labels and their
source, the split, each candidate's thresholds, held-out predictions and latencies, the
tuples, and `SHA256SUMS`. The result note goes beside this plan and in the deposit.

## 10. Open cells

- **Who labels the judgmental positions**, the operator's. The plan requires only that
  no candidate and no model of a candidate's family does.
- **Each candidate's serving memory on the Ada**, a measurement, Kev's being stated as
  about 9 GB on its model card and 17 GB in its repository.
- **The per-turn budget's number**, the operator's, set against the positions per turn
  the traces show, before any candidate is fitted.

