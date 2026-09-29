# How the fred Ada run was executed

As executed on olympus from the executor seat's shell, on the operator's word, and
recorded from that shell. It ran fred on the RTX 2000 Ada at 0000:86:00.0, CUDA 2, with
karl idle.

The deposit this names is on the share, at
`/bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-28-39fe573-fred-ada/` on
olympus, which the thinkpad mounts under `/mnt/bulk-store/weaver-testing/`. Nothing
from it is copied here.

**Every fenced command says where it runs, and is one of two kinds.** A command marked
*to rerun* runs from the root of a checkout of this repository on a box with the share
mounted, and reads each deposit by its absolute path: `/bulk-store/weaver-testing/` on
olympus, `/mnt/bulk-store/weaver-testing/` on the thinkpad. It names its script by the
committed path and writes to stdout. A command marked *as it ran* is what was typed at
the time, kept as the record, and says why it is not rerun.

## The harness

WeaverTools main at `f2a0b82e`, the A6000 pair's, which is `07a7e5d` plus a handoff
document, run on olympus from the same clean detached worktree:
`determinism_matrix.py` `2657c8b2` and `confirm_cells.py` `25ab96db`. To rerun, printing
each file:

```
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

## The stack

The A6000 pair's install of 2026-09-27, unchanged, as
`../../2026-09-28-ampere/fred-a6000/COMMANDS.md` records it. It was re-read at 08:27:54
CDT on 2026-09-28 before the run: all six installed binaries, all five engine
libraries, the artifact and both harness scripts re-hashed to the 2026-09-27 values,
the `worker-binary` still named the Rust worker, and the toolchain still read rustc
`47611e160`. Every file is named by sha256 in the deposit's `box-facts.txt`.

As it ran, on olympus as root, and not rerun, since it edits the installed declaration:
fred's `devices` line set to `[2]`, so that fred's declaration is karl's `a2a03d10` with
`devices: [2]` and the trace path `~/.weaveragents/weaver-fred/trace.ndjson`, written
out in full under the operator's home, and no other line changed. It hashes `84c43db6`.

## The config

`config.json` in the deposit is the fred-a6000 deposit's, naming `agent` `fred`,
`declaration` `/etc/weaver/agents/fred.yaml`, `gate_socket`
`/run/weaver-fred/gate.sock`, `trace` the declaration's trace sink, `admin_bin`
`/usr/local/libexec/weaver/weaver-admin`, `admin_config` `/etc/weaver/config`, and
`repo` the stack's worktree at `39fe5732`. It carries no `spu_bin` and no seed schedule.

## The smoke

As it ran, on olympus from the harness worktree's `code/` directory, into a scratch
directory, and not rerun, since it drives the stack:

```
python3 determinism_matrix.py --config /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-28-39fe573-fred-ada/config.json --outdir <scratch> --hours 0.03
```

It closed at 08:27:31 CDT: 23 sessions, 23 reproduced, 0 errors, exit 0, one binding on
the Ada. The scratch directory was copied into the deposit's
`evidence/smokes/smoke-fred-ada2/`.

## The run

As it ran, and not rerun, since it drives the stack for seven hours and writes into the
deposit. The run was started at 08:33 CDT on 2026-09-28 by one script, on olympus from
the harness worktree's `code/` directory, detached with `setsid` and `nohup` so that no
terminal held it, with the README's sudo renewal loop. The script, with the harness
worktree's path left out:

```
cd <harness worktree>/experiments/deployment-tuple/baseline/determinism-matrix/code
FO=/bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-28-39fe573-fred-ada
( while sleep 120; do sudo -n -v || break; done ) & R=$!
nvidia-smi dmon -s pc -d 5 -o DT -i 2 > $FO/clock.log 2>&1 & D=$!
python3 determinism_matrix.py --config $FO/config.json --outdir $FO --hours 7 > $FO/run-console.log 2>&1
echo "fred exit=$?" > $FO/run-exit.txt
kill $D $R
```

launched on olympus as

```
setsid nohup <script> > <log> 2>&1 < /dev/null & disown
```

The run went from 08:33:21 CDT to 15:33:23, wrote its summary, and wrote
`fred exit=0`.

## The trace split

As it ran, on olympus after the run had ended and with no harness running, and not
rerun, since it writes into both fred deposits. fred's sink file held the records of
the fred A6000 run of 2026-09-27, of this run, and of the smokes before each. A local
script read the sink whole as root and wrote each record, by its `run` id, to the
deposit or smoke whose `matrix.jsonl` names that run as a source or replay run:
each run's records to its deposit's `evidence/trace.ndjson`, and each smoke's to
`evidence/smokes/<smoke>/trace.ndjson` beside its record. It refused any run claimed by
two records and any record claimed by none, and regenerated and verified each
deposit's `evidence/SHA256SUMS`. It read 2,218,120 records and left none over: 1,115,328
to fred-a6000, 1,088,784 to this deposit, and 14,008 across the four smokes, 3,560,
4,472, 3,104 and 2,872. Every run each record names was present in its trace, 10,340
for this run. A first pass that routed only the two runs stopped on the smokes' records
before writing any checksum, and its two partial files were removed before the pass
above.

## The counts

Each to rerun, and each reproduced the note's and the README's figures when this folder
was assembled. As they ran, the same scripts on olympus from the result worktree's root,
with the same deposit paths.

The window, the sweeps, the sessions and verdicts, the counts by prompt character, the
exit, the invocations, the turns compared, unmatched and of more than one token, the
seeds, the device every session bound, and the held fields:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-ada/record_counts.py /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-28-39fe573-fred-ada
```

The clock paragraph's whole-window figures:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-ada/clock_stats.py /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-28-39fe573-fred-ada
```

Its per-session figures, the clock samples joined to the sessions:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-ada/clock_join.py /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-28-39fe573-fred-ada
```

The one emission per turn slot, each pair of runs, the four-way grouping and the held
files that the README states:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-ada/compare_emissions.py karl=/bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000 fred=/bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-fred-a6000 run3=/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run3 ada=/bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-28-39fe573-fred-ada
```
