# The determinism matrix on the olympus Ada, against the A6000 pair and run3, 2026-09-28

A dated result note in the shape of `determinism-matrix-Spec` section 8, read by no
gate. It is the Ada cell the A6000 pair's report named as one of its two follow-ups, and
it compares four seven-hour runs of the baseline determinism matrix, all at stack
`39fe573` and harness `07a7e5d`:

| Run | Box | Card | Deposit under `/bulk-store/weaver-testing/` |
|---|---|---|---|
| karl | olympus | RTX A6000, 0000:01:00.0 | `determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000` |
| fred | olympus | RTX A6000, 0000:41:00.0 | `determinism-matrix-olympus-2026-09-27-39fe573-fred-a6000` |
| run3 | thinkpad | RTX PRO 5000 Blackwell Laptop, 0000:01:00.0 | `determinism-matrix-thinkpad-2026-09-27-39fe573-run3` |
| ada | olympus | RTX 2000 Ada, 0000:86:00.0 | `determinism-matrix-olympus-2026-09-28-39fe573-fred-ada` |

The deposits are on the shared bulk store, which olympus exports and the thinkpad mounts
at `/mnt/bulk-store/weaver-testing/`, and none of them is copied here. The Ada deposit
carries its own `RESULT-2026-09-28.md`, and the same note sits beside this README as
`fred-ada/RESULT-2026-09-28.md`. `../2026-09-28-ampere/` holds the A6000 pair's report
and `../2026-09-28-blackwell/` run3's. This README is the comparison across the four. It
is kept twice, byte for byte, in the repository as `2026-09-28-ada/README.md` under the
determinism matrix's `results/` and in the Ada deposit as
`RESULT-2026-09-28-ada-cell.md`, and every relative path in it, every "here" and every
"beside this README" is read from the repository's copy.

## Why this cell

The A6000 pair against run3 differed on 20 of 464 turn slots, and that difference
coincided with the card generation, its kernel path, the engine-library files and the
binaries, which those runs could not separate. The Ada cell holds every file of the
A6000 pair and varies the card. It ran fred's agent with karl's declaration, two lines
changed for the device and the trace path, on the same box, the same stack, the same
five engine-library files and the same harness as the A6000 runs of the night before,
on an Ada card, compute 8.9, where the A6000 is compute 8.6.

## Facts found

**The Ada run reproduced every session.** It served 5,170 sessions over 162 sweeps of
8 prompts by 4 depths, from 08:33:21 CDT to 15:33:23 on 2026-09-28: 5,170 REPRODUCED,
0 diverged, 0 errors, exit 0, 10,340 unit invocations all distinct, one serving device,
74,816 turns compared with 0 unmatched, of which 4,523 generated more than one token,
and the weights, engine libraries, binaries and toolchain `unchanged` at the close.

**Within the run, one emission per turn slot**, on each of the 464 slots, as within
each A6000 run and within run3.

**The files held are the A6000 pair's, by reading.** The weights `2f822336`, all five
engine-library files, the worker, SPU and gate binaries, and the toolchain read the same
in the Ada deposit as in both A6000 deposits, and all but the weights and toolchain
differ from run3's. The box, the driver 615.71.09, CUDA 13.4.92 and the compiler are the
A6000 pair's too.

**The Ada against each A6000: 443 turn slots identical, 21 different.** Both A6000
runs give the same 21, since they agree with each other on all 464:

- All 21 are on the probe turn, out of 32 probe-turn slots, and none is on a filler.
  All 21 generate more than one token, on the A6000 side and on the Ada's.
- By prompt character, the cells with a difference are near-tie 11 of 12
  (creative-long, creative-short, openended), mid 8 of 8 (code-long, explain-long) and
  confident 2 of 12 (both definition cells, at depths 8 and 16).
- factual-short and arithmetic are identical in every cell.

**The Ada against run3: 443 identical, 21 different**, the same 21 slots.

**How the four runs group, slot by slot.** Over the 464 slots all four hold:

| Slots | Turn | Grouping by emission |
|---|---|---|
| 432 | filler | all four agree |
| 11 | probe | all four agree |
| 20 | probe | karl and fred agree, run3 differs, the Ada differs from both |
| 1 | probe | karl, fred and run3 agree, the Ada differs |

The 20 are the slots on which the A6000 pair and run3 differed, and on every one of them
the Ada gives a third emission. The one slot of the Ada's own is definition at depth 8.

**Reproduction held under every clock state the Ada visited.** No clock was held.
Joined to the sessions by `clock_join.py`, whose session bounds are approximate per
issue #721, 4,344 of the 5,170 sessions hold a sample: 2,719 at the memory clock's
6,801 MHz only, 1,346 at 7,001 MHz only, 268 at both, 10 at 5,001 only and 1 at 5,001
and 6,801, with the graphics clock at 750 to 2,475 MHz inside them. Every one
reproduced.

## What these runs do not establish

- **Which part of the card's path moves the emission.** With every file held, the Ada
  and the A6000s differ, so the files alone do not account for the difference, and the
  card does. The card differs in generation, compute capability and so the kernels
  llama.cpp dispatches, in memory and clocks, and in driving the display, and one run
  does not separate them.
- **The other follow-up.** Thinkpad's rerun on olympus's whole install set holds every
  file across the two boxes while the card and kernel path differ, and is not run here.
- **Anything the Spec's section 5 leaves out, and the baseline's limits of section 8.**
  The agent declares no loop file, the model is the 0.5b at q6_k, most turns generate
  one token, time to first token is not measured, and no clock was held.

## Where the evidence is

The Ada deposit's `summary.json`, `matrix.jsonl`, `matrix.log`, `clock.log`,
`config.json`, `box-facts.txt` and `RESULT-2026-09-28.md`, on the share and not copied
here. Its `evidence/` holds this run's trace, split from fred's sink by run id after
the run, and its smoke with that smoke's own trace.

Beside this README are the commands and the scripts behind every number it and the note
state, each taking deposits as arguments and writing nothing:

- `compare_emissions.py <name>=<deposit> ...` gives the one emission per turn slot, each
  pair of runs by probe turn, by token count and by character, the four-way grouping
  above, and the held files by sha256 side by side. It is the A6000 report's script of
  the same name, generalised from three fixed deposits to named ones.
- `record_counts.py <deposit>` gives the run's window, sweeps, sessions, verdicts,
  invocations, turns and multi-token turns, seeds and device.
- `clock_stats.py <deposit>` gives the clock figures over the whole window.
- `clock_join.py <deposit>`, carried unchanged from #719's run3, joins the clock samples
  to the sessions.
- `fred-ada/COMMANDS.md` gives how the run was executed, and the trace split after it.
