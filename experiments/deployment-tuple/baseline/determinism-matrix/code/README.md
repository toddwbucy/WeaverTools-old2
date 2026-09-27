# Running the determinism matrix

What the matrix measures, its session cycle, its verdicts and what a result does not
establish are `../determinism-matrix-Spec.md`'s. This page is how to run it on a box.

## What is here

`determinism_matrix.py` drives the matrix and imports `confirm_cells.py`, the replay
harness, from beside it. Both are byte-identical to their copies in the
`weaver-experiments` tree at `d04da2a`, so a run from here is the same instrument as
the runs that predate this directory. The three `test_*.py` files are that tree's
tests of the two, also byte-identical. Each is a plain script and exits non-zero on
the first failure:

```
python3 test_seed_schedule.py
python3 test_loop_digest.py
python3 test_provenance_close.py
```

Stdlib only. It needs the installed agent stack, one agent whose declaration it
drives, and nothing else from this repository at run time.

## The config

One JSON file per box. The matrix reads these fields:

| Field | Box-specific | What it names |
| --- | --- | --- |
| `box` | yes | the box's name, recorded in the deposit |
| `agent` | no | the agent the admin loads and unloads, `karl` for the baseline |
| `declaration` | yes | the agent's declaration file, which a seed schedule or `--artifact` rewrites and restores |
| `gate_socket` | yes | the agent's gate socket, under the admin's coordination root |
| `trace` | yes | the agent's trace sink, which every comparison is read from |
| `admin_bin` | yes | the installed `weaver-admin` |
| `admin_config` | yes | the admin's configuration directory, passed as `WEAVER_ADMIN_CONFIG` |
| `repo` | yes | the checkout the stack was built from, for the toolchain reading |
| `spu_bin` | optional | overrides the `spu-binary` the admin configuration names |
| `build_flags` | yes | a description of the build, recorded and not parsed |
| `loop_sha256` | optional | the sha256 of a loop file the agent composes with |

**`cells` is not read by the matrix.** It lists artifacts for `confirm_cells.py`'s own
entry point, the cross-precision protocol, and a config shared with that protocol
may carry it. The matrix takes its artifact from the declaration or from `--artifact`.

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

Its `summary.json` names the worker, SPU and gate binaries and every engine library
by sha256. They must be the ones the box facts name, and the faults must be zero.

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

**If the ticket lapses** the run does not stop: each session records `load refused`
and the run goes on until its hours are spent, the refusals counted as faults apart
from the verdicts. Typing `sudo -v` at the same prompt restores it for the next
session.

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

One directory per run, never appended to by a second run:

| File | What it holds |
| --- | --- |
| `config.json` | the config the run read |
| `box-facts.txt` | the box facts, per the Spec's section 6.2 |
| `matrix.jsonl` | one line per session, written as each session closes |
| `matrix.log` | the run's log, including the stack it read at the start |
| `summary.json` | counts and provenance, written at the end |
| `clock.log` | the `dmon` samples |
| `run-console.log` | the run's console |

A result note beside them states what the run establishes and what it does not, in
the shape of the Spec's section 8, and lands dated in `../results/`.
