# Running the determinism matrix

What the matrix measures, its session cycle, its verdicts and what a result does not
establish are `../determinism-matrix-Spec.md`'s. This page is how to run it on a box.

## What is here

`determinism_matrix.py` is the one entry point and imports `confirm_cells.py`, the
replay harness, from beside it. `confirm_cells.py` has no entry point of its own: the
cross-precision protocol it once ran is the matrix's `--cells` mode. Both come from the
`weaver-experiments` tree at `d04da2a`. Both carry the fixes of #716, named in the
Spec's section 0, with a test holding that on the path the 2026-09-27 runs took every
verdict, seed and turn is what it was before, the fields that move named: the declared
seed and the device each load logged. The `test_*.py` files are the tests of the two,
three from that tree and `test_recorded_seed.py`, `test_absence_and_evidence.py`,
`test_round_five.py`, `test_round_seven.py`, `test_round_eight.py`,
`test_round_nine.py`, `test_round_ten.py`, `test_round_eleven.py`,
`test_round_twelve.py`, `test_round_thirteen.py`, `test_round_fourteen.py`,
`test_round_fifteen.py`, `test_round_sixteen.py`, `test_round_seventeen.py`,
`test_round_eighteen.py` and `test_one_entry_point.py` from #716, and
`test_record_offset.py` from #698. Each is a plain script and exits non-zero on the
first failure:

```
python3 test_seed_schedule.py
python3 test_loop_digest.py
python3 test_provenance_close.py
python3 test_recorded_seed.py
python3 test_absence_and_evidence.py
python3 test_round_five.py
python3 test_round_seven.py
python3 test_round_eight.py
python3 test_round_nine.py
python3 test_round_ten.py
python3 test_round_eleven.py
python3 test_round_twelve.py
python3 test_round_thirteen.py
python3 test_round_fourteen.py
python3 test_round_fifteen.py
python3 test_round_sixteen.py
python3 test_round_seventeen.py
python3 test_round_eighteen.py
python3 test_record_offset.py
python3 test_one_entry_point.py
```

Stdlib only. It needs the installed agent stack, one agent whose declaration it
drives, and nothing else from this repository at run time.

## The config

One JSON file per box. The matrix reads these fields:

| Field | Box-specific | What it names |
| --- | --- | --- |
| `agent` | no | the agent the admin loads and unloads, `karl` for the baseline |
| `declaration` | yes | the agent's declaration file, whose one seed and one artifact are read at the start, whose digest every load is held to, and which a seed schedule, `--artifact` or `--cells` rewrites and restores |
| `gate_socket` | yes | the agent's gate socket, under the admin's coordination root |
| `trace` | yes | the agent's trace sink, which every comparison is read from |
| `admin_bin` | yes | the installed `weaver-admin` |
| `admin_config` | yes | the admin's configuration directory, passed as `WEAVER_ADMIN_CONFIG` |
| `repo` | yes | the checkout the stack was built from, for the toolchain reading |
| `loop_sha256` | optional | the sha256 of the loop the agent composes with, 64 lowercase hex digits or refused at preflight, which every load is held to, a load composed by another being a fault. Absent, the loop is unchecked |

**`cells` is read only by `--cells`.** It lists the cross-precision protocol's cells,
each an object with a `name`, a `precision` and an absolute `artifact`, the names plain
and none repeated. With `--cells` the run serves each cell once, the protocol's two
turns under the declaration with that cell's artifact, in place of the prompt-by-depth
matrix, and takes none of `--artifact`, `--seed-schedule` or `--hours`: a cells run
serves every cell, whatever the clock. Without it the run takes its artifact from the
declaration or from `--artifact`. Other keys, such as a `box` or `build_flags` an older
config carries, are not read.

```
python3 determinism_matrix.py --config <deposit>/config.json --outdir <deposit> --cells
```

**Every file the config names is opened before the run writes anything.** The artifact
must be readable, the declaration writable where the run rewrites it, `admin_bin` an
executable file and `repo` a directory, and the stack's opening readings, the admin
configuration's entries and the binaries and libraries they name, must be readings and
not guesses. Every path the stack resolves, the artifacts, `trace`, `gate_socket`,
`admin_config` and the binaries the admin configuration names, must be absolute, and
cell names must not repeat. A config carrying `spu_bin` is refused: the admin launches
the SPU its configuration names, and the run reads it there. A run refused there exits 2
and names what it refused.

## Before a run

**Install the stack at the commit the run is named for, engine libraries included.**
`deploy/update-stack.sh --install` installs the weaver binaries and not the engine
libraries the SPU links from the admin's library directory. On a box whose libraries
predate the build, install the build's own set from its `llama-cpp-sys-2` output,
keeping the old set aside, or the deposit names new binaries over old kernels.

**Smoke first, and read the smoke's record before the long run.** A few minutes'
run to a scratch directory:

```
python3 determinism_matrix.py --config <deposit>/config.json \
  --outdir <scratch> --hours 0.03
```

Its `summary.json` names the worker, SPU and gate binaries and every engine library by
sha256. They must be the ones the box facts name, and its `errors` must be zero.

**Record the journal's retention**, `journalctl --disk-usage` and the oldest entry
`journalctl -o short | head -1`, in the box facts. The harness reads each load's device
by its unit invocation as the load stands, so retention does not limit the gate, but the
journal window it also records at the close covers only what the journal still holds,
and on a box keeping minutes that is the tail of a run.

## What the exit code says

**Exit 0 means every session reproduced and every field the run holds held.** The
weights, every cell's artifact in a cells run, the engine libraries, the binaries and
the toolchain must read the same at the start and the end, the serving device must be
one binding for the whole run, and every session must bear out its declared seed and
serve its declared declaration. Anything less exits 1, and the log names the fields that
did not hold. Both modes exit on the one verdict, `run_verdict`, and a cells run short
of its cells exits 1 naming the cells it did not serve. A session that raises is
recorded as `error: <type>: <message>`, and an interrupt records the session it cut
short as `interrupted`, closes the run and exits 1. A run whose `summary.json` could not
be written, or whose declaration could not be restored, exits 1 and names the step.
Batch composition is recorded rather than held: one caller and one turn at a time by
construction, which the record cannot show. What an exit 0 certifies, and what it does
not guard against, is the Spec's section 5, with the table.

## The sudo requirement

**Every load and unload runs `sudo -n`**, four times a session, so the run needs a
credential that holds without a prompt for its whole window. Grant nothing standing
for it: a rule that passes `WEAVER_ADMIN_CONFIG` through lets any process of the
operator's uid choose the configuration the admin executes from as root.

**The ticket belongs to one terminal.** sudo keys it to the terminal session, so a run
lives as a background job of the shell that holds the ticket, which leaves that
shell's prompt free to renew it. A new terminal or a multiplexer pane is a new session
with no ticket. In that one terminal:

```
sudo -v
( sudo -n -v && echo renewed || echo refused ) < /dev/null &
```

The second line takes five seconds and must print `renewed`. Then the run, with its
clock recorder and a renewal loop, all ending together:

```
OUT=<deposit>
( ( while sleep 120; do sudo -n -v || break; done ) & K=$!
  nvidia-smi dmon -s pc -d 5 -o DT > $OUT/clock.log 2>&1 & D=$!
  python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT \
    --hours 7 > $OUT/run-console.log 2>&1
  kill $D $K ) < /dev/null &
```

**If the ticket lapses** the run does not stop: each session records `load refused` and
the run goes on until its hours are spent, the refusals counted under the summary's
`errors` apart from the verdicts. Typing `sudo -v` at the same prompt restores it for
the next session.

**Keep the terminal open and the box awake and on power.** Closing the terminal sends
a hangup that kills the run before it writes `summary.json`, and a suspend stops the
card mid-session. An interrupt, by contrast, ends the run cleanly and writes the
summary.

## The clock

**Record the clock where it is not held.** `nvidia-smi dmon -s pc` is the readout,
sampled every five seconds beside the run as above, and a result joins the samples
to sessions by time. Do not read clocks through `nvidia-smi --query-gpu=clocks.sm`:
on driver 610.57.04 it reported 210 MHz at full load on olympus, where `dmon` agreed
with achieved throughput. Holding a clock needs root per load and is the clock-state
driver's, which stays in `weaver-experiments`. A laptop part may not hold one at all.

## The deposit

One directory per run, never appended to by a second run. The harness refuses an outdir
already holding `matrix.jsonl`, `matrix.log` or `summary.json`, and refuses to start
while a `.pre-matrix` backup of the declaration stands, which a run leaves only when it
was killed before restoring the declaration. Restore the declaration from it by hand and
remove it first:

| File | What it holds |
| --- | --- |
| `config.json` | the config the run read |
| `box-facts.txt` | the box facts, per the Spec's section 6.2 |
| `matrix.jsonl` | one line per session, written as each session closes, a cell's labelled by its name, precision and artifact |
| `matrix.log` | the run's log, including the stack it read at the start |
| `summary.json` | counts and provenance, written at the end |
| `clock.log` | the `dmon` samples |
| `run-console.log` | the run's console |

A result note beside them states what the run establishes and what it does not, in
the shape of the Spec's section 8, and lands dated in `../results/`.
