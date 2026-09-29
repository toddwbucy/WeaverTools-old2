# Sketch: the trace-content classifier

**Status:** LIVING, outside the set. A sketch in `docs/project/`, per the Document
Format: it maps into no graph and nothing is written against it. What it settles
moves into a charter or a Spec by an act of its own.

**Date filed:** 2026-09-29

**Landing PR:** #738

---

## 0. What this document is

The plan for typing the trace's payload. The envelope is typed and positional
already, per `weaver-trace-PRD` section 3. The payload is not: the model's own
output text and the input text at each position ride `message.*` and
`model.measurement` as raw JSON, and `weaver-state` lands them as text pairs.
Typing that payload is what the state organ needs, per the operator's word of
2026-09-28, and it is the prerequisite for the prefetch organ's text head.

The instrument is a trace-content classifier run in the loop as a routing stage
and never a judging one: it types content so the loops can decide, and decides
nothing itself. That is the shape the classify seam already has, per
`weaver-harness-spu-classify-contract` and `weaver-spu-PRD` section 15, and this
sketch is written against that seam rather than beside it.

## 1. The method

HeroBench, the operator's fork at the workshop level, supplies the label ontology
from the game: items, recipes, level gates, locations and actions, each finite and
external to the traces. A label set derived from the traces would be circular. A
label set taken from the game is a middle-range mapping in which the known
process is external and finite, and a classifier trained on it can be measured
against the game's own record of what happened.

The agent plays HeroBench through the gate's shell, the environment's actions
being a CLI in the agent's home, so every action and the environment's answer
crosses as `message.tool_result` at a position in the trace. The task arrives as
`message.user`, the rules and the game dump as `message.system`, and the model's
reasoning and program as `message.assistant`. The join from a position to game
state is by position, and it is free.

## 2. The split that decides the architecture

Nothing is built before this is measured. The label space is split in two and
both halves are counted, over HeroBench's own results and one replayed pair of
programs:

- **Computable.** The label joins to game state by position: an item code exists
  in the ontology or does not, a location matches the resource's, a level gate is
  met or not, the environment accepted or refused the action, the inventory moved
  or did not, the task scored or did not.
- **Judgmental.** The label needs a model: this span recites the dump, this span
  states a plan, this plan contradicts what was just recited. The game does not
  enumerate these. The Pumpkin Spice specimen is that failure and the template
  case for deriving them.

Positions no recipe reaches are a third count, never folded into either.

Measured 2026-09-29 over HeroBench's own results, 3,882 single-shot completions
whose text is on disk, segmented into positions (prose lines, draft lines,
program steps, executed actions, refusals, the scored outcome):

    Weighting               Positions    Computable   Judgmental   Unreached
    every position          1,477,957    51.4%        44.6%        4.0%
    what the model wrote      834,725    13.9%        78.9%        7.1%

The first weighting is mostly the environment's log, a looping program
contributing thousands of accepted actions per task. The second is the text the
model authored, and four of every five of its positions are judgmental.
Judgmental of authored text runs 87.0 per cent at level 1 and 79.4 to 83.7 from
level 2 to 9. The scripts are under `experiments/trace-content/label-split/`,
and the deposit is `herobench-positions-2026-09-29` on the share. **The judgmental
count is the count of the model's prose lines, which no game-join labels, a
definition, and not yet a measurement of any model's difficulty on them**, which the
evaluation of section 4 supplies.

## 3. The candidates

Four are weighed and one is ruled out. The table records what each is, the
memory it takes to serve, its licence, and how it meets the seam.

    Candidate        What it is                                   Serve      Licence     Seam
    ModernBERT       encoder, 149M, classify head, id2label       under 1G   Apache-2.0  as built
    Laya             Convai, 421M, runs on a T4                   (owed)     Apache-2.0  (owed)
    open-jev         DeBERTa-v3-large encoder                     (owed)     (owed)      as built
    Kev-0.8B / 4B    Qwen3.5-Base, LoRA r=16, pointer head        4G / 9-17G Apache-2.0  contract change

**ModernBERT is the first classify family the SPU carries**, per
`weaver-spu-Spec` section 11, and `ModernBERT-base-zeroshot-v2.0` is on olympus
under the models store, so the encoder default is one admission away.

**Kev is a decision model rather than a label head.** One state document and a
set of typed questions, `noul`, `choice` and `score`, answered as a probability
distribution per question in one forward pass, states to 65,536 tokens, served
over its own HTTP endpoint on PyTorch, transformers and peft, fine-tuned from the
released adapter on JSONL of state, questions and labels. The judgmental labels
above are `noul` and `choice` questions over the trace window at a position,
which is Kev's shape exactly. Its serving memory is stated at about 9 GB on the
model card and 17 GB in the repository, and which is true on this hardware is a
measurement.

**The constraint that decides between them.** A LoRA over the decode model makes
the observer part of the observed and puts the adapter into the deployment
tuple. A separate model keeps them apart on weights, and can keep them apart on
device. Kev is not a LoRA over the decode model, it is its own base, so it meets
the constraint on weights. What it adds is a second model with a tuple of its
own, weights, precision, device and kernel stack, PyTorch where the decoder is
candle, and that tuple is recorded in every deposit beside the decoder's or the
classifier's answers are not reproducible. **The encoder is the default unless
measurement says otherwise**, on the operator's position of 2026-09-28.

**Where Kev disagrees with the corpus.** The classify contract's section 2 says
the label set is the artifact's and never the ask's, an ask carrying content
alone. Kev's questions ride the ask. Serving it behind the label seam is a
contract change reaching both parties, on the operator's ruling, and the member
honouring the seam would be a Python process, which the contracts permit since
they name no language.

**Jev is ruled out.** TypeSafe's Master Customer Agreement section 2.3(b) forbids
training a model to imitate the Services' output, breach is an excluded claim
outside the liability cap, and the clause survives termination. Recorded here so
the exclusion is not rediscovered.

## 4. The evaluation

On the same labeled positions, side by side: the encoder for the computable-
adjacent labels, Kev for the judgmental questions. If the split says the
judgmental share dominates, Kev's question-shaped interface is the better
instrument and the contract changes on that measurement. If the computable share
dominates, the encoder stands and the judgmental questions are the smaller
problem. Either way the classifier's own tuple is recorded and the observer stays
off the decoder's weights and device.

## 5. Open cells

- A model's measured accuracy on the judgmental positions, per candidate.
- The Pumpkin Spice specimen is not an artifact on disk: it names a decision
  point, the moment after a retrieved fact lands, per the operator's word of
  2026-08-31. The template case for the judgmental labels is still to be chosen
  or captured.
- Kev's serving memory on the Ada, 9 or 17 GB, a measurement.
- Whether the classify contract changes to carry questions on the ask, the
  operator's ruling after the evaluation.
- The prefetch organ's text head, which this sketch is prerequisite to and does
  not design.
