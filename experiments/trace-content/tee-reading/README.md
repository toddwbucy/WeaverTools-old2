# The tee reading, 2026-09-30

A dated reading, read by no gate, for the state work's second step: what the agent
needs back across turns and runs, through which ask, and so what the typed tee should
carry. Nothing in a crate changed and nothing on the box changed. Every figure below is
in one of two files that `code/tee_reading.py` wrote, and none is computed by hand.

The first file is `tee-reading/rusty.json` in the deposit
`herobench-sessions-2026-09-30` on the shared bulk store, read from rusty's 50 sessions
`s-rusty-n-001` to `s-rusty-n-050`, their trace and their copied state store. Each of
those sessions is one run of one level-1 task, so none of them has an earlier run to ask
about. The second file, `tee-reading/asks-2026-09-29.json` beside it, reads the asks
from the sessions of more than one run, `s-rusty`, `s-rusty-b` and `s-rusty-c` of
`herobench-agents-2026-09-29`, from that deposit's trace and store after the v4 pass.
pyra's sessions are running as this is written and are read in a follow-up.

The model is Qwen2.5-7B-Instruct on the Rust SPU at a 32,768-token context, sampled
at the frozen tunables of #746. The installed stack was deployed from `99494511`,
before #748, and section 5 says what that did to the store.

## 1. What crossed the tee, and what the store holds of it

**The tee was elected the same way at all 50 loads**: every event kind lands as an
event row, and four kinds carry keys, `role` and `content` on `message.user`,
`message.assistant` and `message.tool_result`, and `perplexity`, `entropies` and
`surprisals` on `model.measurement`. The store holds 14,120 event rows.

Of 15,052,399 bytes of payload over every kind, 7,661,911 were elected, 50.9 per cent.
By kind:

| Kind | Events | Payload bytes | Elected bytes |
|---|---|---|---|
| `model.measurement` | 1,963 | 8,773,630 | 5,714,194 |
| `model.request` | 1,963 | 2,020,852 | 0 |
| `message.tool_result` | 1,613 | 1,136,220 | 1,103,960 |
| `tool.call.completed` | 1,613 | 1,076,517 | 0 |
| `model.output` | 1,963 | 755,813 | 0 |
| `message.assistant` | 1,963 | 700,991 | 661,731 |
| `message.system` | 50 | 235,650 | 0 |
| `message.user` | 392 | 189,866 | 182,026 |

**The three readings are 74.6 per cent of what the tee elects.** The conversation is the
rest: 1,103,960 bytes of tool results, 661,731 of the model's own messages and 182,026
of user messages.

The store typed 4,018 messages. Their parts are 2,405 text parts of 841,806 bytes,
1,627 tool calls of 51,011 bytes and 1,613 tool results of 917,280 bytes, 1,810,097
bytes typed in all. It typed 1,661 measurement rows, 1,657 of them with a perplexity,
and 25 series of 305 values. It landed 5,684,725 bytes verbatim, every one of them a
reading: 1,948 entropy series of 2,854,362 bytes, 1,953 surprisal series of 2,824,855
bytes, and 306 perplexities of 5,508 bytes.

## 2. The tool results

**The model is the only reader of a tool result.** The loop reads the game's own log
over the environment's server for its verdict and never parses what the tool answered.

The 1,613 tool results run from 59 to 3,688 bytes, a median of 163 and a 90th
percentile of 1,223, 917,280 bytes in all. By what the environment answered:

| Class | Results | Bytes | Distilled bytes |
|---|---|---|---|
| a move, `destination` and `character` | 354 | 422,457 | 45,513 |
| a fight, `fight` and `character` | 60 | 161,559 | 6,141 |
| an error | 859 | 133,620 | 113,863 |
| the CLI's usage text, not JSON | 100 | 93,207 | 93,207 |
| a gather or craft, `details` and `character` | 52 | 63,781 | 10,632 |
| the character's whole record | 26 | 27,633 | 1,308 |
| a map tile | 157 | 12,198 | 12,041 |
| an item's description | 4 | 1,068 | 1,064 |
| an item equipped | 1 | 1,757 | 119 |

Every success carries the character's whole record, whichever action ran: skill
levels, equipment slots and resistances. It is a median 1,036 bytes, and the 467
results that carry it hold 502,560 bytes of it. A fight also carries its turn by turn
log.

**A distillate keeping the action's outcome, the character's position, hit points and
inventory, and the exit status holds 283,888 bytes, 31.0 per cent of the whole.** It
saves most on moves and fights, and least on errors and on the usage text, which the
CLI prints whole on every malformed call and which the distillate keeps as it is.

**Tool results are the larger part of the context.** At each run's last call, rebuilt
from the record, the context is 56.3 per cent tool responses, 23.9 per cent the model's
own earlier text, 10.6 per cent user messages and 9.3 per cent the identity prefix. The
rebuild agrees with the model's own resident count to within 165 tokens over a run.

## 3. The asks

**Over the 50 sessions every opening read "This session has no earlier runs."**, each
session being one run. The harness's `recall` at each open was the identity ask, and it
returned nothing, the identity being seeded from the declaration on a session's first
run.

In the sessions of more than one run, the loop's shape ask put a continuity line at the
opening of every later run, verbatim from the trace: "This session has 1 earlier runs
and 24 turns before this task." in `s-rusty` and `s-rusty-b`, and in `s-rusty-c` from
"This session has 1 earlier runs and 8 turns before this task." to "This session has 5
earlier runs and 40 turns before this task." The identity ask returned one entry of 98
bytes at each later run's open.

**The loop never asked `recall` for the conversation.** Had it asked for the session's
messages before each later run, the store would have returned 49 messages of 14,360
bytes in `s-rusty`'s second run and 75 of 32,682 in `s-rusty-b`'s. In `s-rusty-c` it
would have returned 43 messages of 23,634 bytes before the second run, 380 of 98,394
before the third, 774 of 194,591 before the fourth, 1,077 of 254,610 before the fifth
and 1,094 of 262,715 before the sixth.

**No text the model wrote in a later run names an earlier run, task or session.** The
test is a phrase naming what it points back to, and it counts 0 in these sessions and 0
over the 50. Words such as "again" and "already" are left out of it, because in these
traces they point back within the run, to the model's own last action. The continuity
line reached the model, and nothing shows the model using it.

## 4. The model's own text, and where decay set in

The model's messages run to a median of 260 bytes a turn, a 90th percentile of 5,861
and a maximum of 18,521. At a turn's opening, its own earlier text is a median 6.2 per
cent of the context in a turn that did not decay and 17.8 per cent in one that did, and
the tool responses 3.9 against 57.2 per cent.

**Decay set in early.** In the 21 sessions that decayed, the first decayed turn was a
median turn 2 of the run, the latest turn 8, at a median fill of 17.2 per cent of the
context, of which 14.4 per cent was the model's own text and 35.9 per cent tool
responses. The rate of decay by the fill at a turn's opening:

| Fill | Turns | Decayed | Rate |
|---|---|---|---|
| 0.0 to 0.1 | 209 | 10 | 0.048 |
| 0.1 to 0.2 | 53 | 10 | 0.189 |
| 0.2 to 0.3 | 61 | 6 | 0.098 |
| 0.3 to 0.4 | 12 | 3 | 0.250 |
| 0.4 to 0.5 | 12 | 9 | 0.750 |
| 0.5 to 0.6 | 21 | 7 | 0.333 |
| 0.6 to 0.8 | 15 | 8 | 0.533 |
| 0.8 to 1.0 | 9 | 5 | 0.556 |

At a fill of 0.3 and over, 32 of 69 turns decayed, and under it 26 of 323. The buckets
over 0.3 hold few turns each, so the rise is read over them together rather than bucket
by bucket.

## 5. The readings

Each measurement carries a perplexity of 18 bytes, and an entropy series and a surprisal
series of one value per output token, a median of 1,323 and 1,296 bytes and at most
20,895 and 21,062. A turn's readings run to a median of 2,670 bytes, a 90th percentile
of 51,907 and a maximum of 161,079.

**The store typed 84.4 per cent of the perplexities and 25 of 3,926 elected series.**
All 306 verbatim perplexities render back exactly under a correctly rounded parse, so
the cause is the parse and not the values: the installed `weaver-state` predates #748's
`float_roundtrip`, and its fast float parse misrounds some values, which the landing's
exactness rule then sends to `field`. A series types only when every value renders back,
so a series of a thousand values almost never does. A stack redeployed from `main` types
them.

## 6. The elections a Spec act would have to make

Stated as questions, with the numbers beside them. None is decided here.

- **What does a tool result distil to, and whose distillate is it?** The model is its
  only reader. Outcome, position, hit points and inventory keep 31.0 per cent of its
  bytes, and tool results are 56.3 per cent of the context by a run's end. Errors and
  the CLI's usage text are 207,070 of the 283,888 bytes the distillate keeps.
- **Does recall serve the loop or the model?** The continuity line reached seven later
  openings and the model referred to an earlier run 0 times. A whole recall grows to
  262,715 bytes by a sixth run, against a context of 32,768 tokens.
- **What of the measurement crosses?** The readings are 74.6 per cent of the elected
  bytes. A perplexity is 18 bytes, a turn's series a median of 2,670 bytes and at most
  161,079. Once `float_roundtrip` is installed they type, so the question is what the
  record keeps, a whole series or a summary or nothing, rather than how it lands.
- **Does the election stay load-declared or become the tee's own?** All 50 loads carried
  one election, from declarations that differ by session and seed alone, so a default in
  the tee would have changed nothing these sessions landed.

## How the figures were produced

From the repository, with the deposits on the shared bulk store:

```
python3 experiments/trace-content/tee-reading/code/tee_reading.py \
  --trace <sessions-deposit>/rusty/trace.ndjson --state <sessions-deposit>/rusty/state.sql \
  --sessions s-rusty-n- --out <sessions-deposit>/tee-reading/rusty.json

python3 experiments/trace-content/tee-reading/code/tee_reading.py \
  --trace <agents-deposit>/rusty/v4-s-rusty-c/trace-after-v4.ndjson \
  --state <agents-deposit>/rusty/v4-s-rusty-c/state-after-v4.sql \
  --sessions s-rusty,s-rusty-b,s-rusty-c --exact --asks \
  --out <sessions-deposit>/tee-reading/asks-2026-09-29.json
```

`<sessions-deposit>` is `herobench-sessions-2026-09-30` and `<agents-deposit>`
`herobench-agents-2026-09-29`. The script reads the store read-only and prints only the
size of each section it writes.
