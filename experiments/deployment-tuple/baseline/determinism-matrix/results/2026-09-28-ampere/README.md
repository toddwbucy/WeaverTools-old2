# The determinism matrix on the olympus A6000 pair, and against run3, 2026-09-28

A dated result note in the shape of `determinism-matrix-Spec` section 8, read by no
gate. It compares three seven-hour runs of the baseline determinism matrix, all at stack
`39fe573` and harness `07a7e5d`:

| Run | Box | Card | Deposit under `/bulk-store/weaver-testing/` |
|---|---|---|---|
| karl | olympus | RTX A6000, 0000:01:00.0 | `determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000` |
| fred | olympus | RTX A6000, 0000:41:00.0 | `determinism-matrix-olympus-2026-09-27-39fe573-fred-a6000` |
| run3 | thinkpad | RTX PRO 5000 Blackwell Laptop, 0000:01:00.0 | `determinism-matrix-thinkpad-2026-09-27-39fe573-run3` |

The deposits are on the shared bulk store, which olympus exports and the thinkpad mounts
at `/mnt/bulk-store/weaver-testing/`. Each holds its run's record, log, summary, clock
log, box facts, config and `evidence/`, and none of them is copied here. Each olympus
deposit also carries its own `RESULT-2026-09-28.md`, and the same two notes sit beside
this README as `karl-a6000/RESULT-2026-09-28.md` and `fred-a6000/RESULT-2026-09-28.md`.
Run3 carries thinkpad's own note, and `../2026-09-28-blackwell/` holds its report. This
README is the comparison across the three. It is kept three times, byte for byte, in the
repository as `2026-09-28-ampere/README.md` under the determinism matrix's `results/`
and in each olympus deposit as `RESULT-2026-09-28-a6000-pair.md`, and every relative
path in it, every "here" and every "beside this README" is read from the repository's
copy.

## Facts found

**Each A6000 run reproduced every session.** Each served 5,296 sessions over 166 sweeps
of 8 prompts by 4 depths, from 23:11:26 CDT on 2026-09-27 to 06:11:28 on 2026-09-28:

- 5,296 REPRODUCED, 0 diverged, 0 errors, and exit 0, each.
- 10,592 unit invocations each, all distinct, and one serving device for the whole run.
- 76,640 turns compared each, 0 unmatched, of which 4,634 generated more than one
  token, the substantive generations the Spec's section 8 counts apart.
- The weights, the engine libraries, the binaries and the toolchain each read
  `unchanged` at the close.
- Whether journald suppressed any worker message is not known. olympus caps its system
  journal at 50M, and the window rotated out before it was read.

**Within each run, one emission per turn slot.** The 32 cells hold 464 turn slots, and
on each A6000 every slot produced exactly one emission hash across all its sessions. So
did run3's 6,886 reproduced sessions on thinkpad.

**The two A6000 cards agree exactly: 464 of 464 turn slots identical.** The two runs
shared one box, one driver, one compiler, one build of the binaries and one set of
engine-library files, and ran over the same window. Their declarations differ only in
`devices` and the trace path. Within this generation, on this stack, the card did not
move a single emission.

**Each A6000 against run3: 444 turn slots identical, 20 different.** Both A6000 runs
give the same 20, which follows from the line above:

- All 20 are on the probe turn, out of 32 probe-turn slots, and none is on a filler.
  All 20 generate more than one token, on the A6000 side and on run3's.
- By prompt character, the cells with a difference are near-tie 11 of 12
  (creative-long, creative-short, openended), mid 8 of 8 (code-long, explain-long) and
  confident 1 of 12 (one definition cell).
- factual-short and arithmetic are identical in every cell.

The differences sit where the model's choice is least forced and do not reach the
single-token fillers.

**Reproduction held under every clock state the A6000s visited.** No clock was held.
The five-second `dmon` samples, joined to the sessions they fall inside by
`clock_join.py`, put each session under the memory-clock states it saw:

| Run | Sessions with a sample | 7,601 MHz only | 8,001 MHz only | Both | 810 MHz | Graphics clock inside sessions |
|---|---|---|---|---|---|---|
| karl | 4,354 of 5,296 | 3,046 | 1,188 | 119 | 1 | 780 to 1,890 MHz |
| fred | 4,356 of 5,296 | 3,050 | 1,172 | 132 | 2 | 900 to 1,890 MHz |

Every one of those sessions reproduced, including each that spanned a memory-clock
change. The sessions with no sample inside were shorter than the five-second cadence.

**What the two boxes share, by reading.** The source commit 39fe573 and its pins
(candle `aee9af9c`, llama-cpp-rs `ecce255`), the harness at 07a7e5d, the declaration
`a2a03d10`, the model `2f822336`, driver 615.71.09, CUDA 13.4.92, CCCL 3.3.4-1, GCC
16.2.1 and rustc 47611e160. Both run the Rust worker with no loop file.

**What differs between the boxes, by reading, beside the card.**

- **All five engine-library files**, each built from the same source on its own box.
  `libggml-cuda` reads `77bd4828` on olympus against `abec199d` on thinkpad, and
  `libggml-base`, `libggml`, `libggml-cpu` and `libllama` differ as well.
- **The three weaver binaries the harness holds**, the worker, the SPU and the gate,
  which also differ by hash between the boxes.
- **The CUDA kernel path.** llama.cpp dispatches architecture-specific kernels, so the
  A6000's compute 8.6 and the Blackwell part's compute 12.0 take different code through
  the same library source.

## What these runs do not establish

- **That the card generation is the variable.** The cross-box difference coincides with
  the card generation, the kernel path, the engine-library files and the binaries, and
  these runs do not separate them. "The device moves the output" is not what they show.
- **The two follow-ups that do separate them.** The Ada cell on olympus runs karl's
  declaration on the RTX 2000 Ada, compute 8.9, with the same binaries and the same
  library files as the A6000 pair, ran 2026-09-28 08:33 to 15:33 CDT, and its result is
  in `../2026-09-28-ada/`. Against the A6000 pair it holds every file and varies only
  the generation and its kernel path. Thinkpad's rerun on olympus's whole install set,
  the six weaver binaries and the five library files, holds every file across the two
  boxes while the card and kernel path differ.
- **Anything the Spec's section 5 leaves out, and the baseline's limits of section 8.**
  The agent declares no loop file, the model is the 0.5b at q6_k, most turns generate
  one token (4,634 of 76,640 on each A6000 generated more), time to first token is not
  measured, and no clock was held.

## Where olympus departs from the README and from thinkpad

- **The worker was switched to the Rust worker** on 2026-09-27, on the operator's word.
  olympus had run `pyworker`, which with no loop file composes with its deployed default
  loop, and the switch makes the agent compose with no loop, as thinkpad's does.
- **The runs were started detached**, with `setsid` and `nohup`, on the operator's word,
  and not as background jobs of an operator's terminal. Otherwise the README's block was
  followed, with one renewal loop and a `dmon` per card.
- **The two runs shared the box**, one per A6000, over the same window. A concurrent
  smoke before them had shown both at 0 errors.

## Where the evidence is

Each deposit's `summary.json`, `matrix.jsonl`, `matrix.log`, `clock.log`, `config.json`,
`box-facts.txt` and `RESULT-2026-09-28.md`, on the share and not copied here.

Beside this README are the commands and the scripts behind every number it and the two
notes state, each taking the deposits as arguments and writing nothing:

- `compare_emissions.py <karl deposit> <fred deposit> <run3 deposit>` gives the one
  emission per turn slot, karl against fred, each A6000 against run3 by probe turn, by
  token count and by character, and the held files by sha256 side by side.
- `record_counts.py <deposit>` gives each run's window, sweeps, sessions, verdicts,
  invocations, turns and multi-token turns, seeds and device.
- `clock_stats.py <deposit>` gives each run's clock figures over the whole window.
- `clock_join.py <karl deposit> <fred deposit>`, carried unchanged from #719's run3,
  joins the clock samples to the sessions and gives the clock table above.
- `karl-a6000/COMMANDS.md` and `fred-a6000/COMMANDS.md` give how each run was executed:
  the harness by commit, the stack's install, the config, the smokes, the detached start
  and its wrapper, and the readings behind the journal paragraph.

Each olympus deposit also holds an `evidence/` directory: the agent's trace, the smokes
its box facts cite, and `JOURNAL-NOT-CAPTURED.txt`, which says why the window's journal
records are absent. karl's trace is its sink file whole. fred's sink file also carried
the Ada cell, which appended to it, and after that run ended the file was split by run
id between the two deposits, each smoke's records beside its smoke under
`evidence/smokes/`. The snapshot fred-a6000 held before the split was removed once the
split was reviewed.
