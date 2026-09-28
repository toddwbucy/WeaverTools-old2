# How the karl A6000 run was executed

As executed on olympus from the executor seat's shell, on the operator's word, and
recorded from that shell. It ran karl on the RTX A6000 at 0000:01:00.0, CUDA 0, beside
fred on the other A6000.

The deposit this names is on the share, at
`/bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000/`
on olympus, which the thinkpad mounts under `/mnt/bulk-store/weaver-testing/`. Nothing
from it is copied here.

**Every fenced command says where it runs, and is one of two kinds.** A command marked
*to rerun* runs from the root of a checkout of this repository on a box with the share
mounted, and reads each deposit by its absolute path: `/bulk-store/weaver-testing/` on
olympus, `/mnt/bulk-store/weaver-testing/` on the thinkpad. It names its script by the
committed path and writes to stdout. A command marked *as it ran* is what was typed at
the time, kept as the record, and says why it is not rerun.

## The harness

WeaverTools main at `f2a0b82e`, which is `07a7e5d` plus a handoff document, run on
olympus from a clean detached worktree of the primary checkout at that commit:
`determinism_matrix.py` `2657c8b2` and `confirm_cells.py` `25ab96db`, all 19 of its
`test_*.py` exiting 0 there before the run. To rerun, printing each file:

```
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

## The stack

As it ran, on olympus in a second clean detached worktree at `39fe5732` with its own
cargo target directory, and not rerun, since it installs onto the box:

```
WEAVER_ADMIN_CONFIG=/etc/weaver/config deploy/update-stack.sh --install
```

It reported `the box is at 39fe5732`, its test step `300 passed, 0 failed`, and it
validated and load-verified both agents. As it ran, on olympus as root in the same
shell, and not rerun: the build's five engine libraries copied from its
`llama-cpp-sys-2` `out/lib` into `/usr/local/lib/weaver`, which the SPU reaches through
`ld.so.conf`, the 2026-08-28 set kept aside first, then `ldconfig`. And the admin's
`worker-binary` set to the Rust worker:

```
printf '/usr/local/libexec/weaver/worker\n' > /etc/weaver/config/worker-binary
```

Every file is named by sha256 in the deposit's `box-facts.txt`. karl's declaration is
thinkpad's run3 `karl.yaml` byte for byte, installed on olympus as
`/etc/weaver/agents/karl.yaml`. It hashes `a2a03d10`.

## The config

`config.json` in the deposit names `agent` `karl`, `declaration`
`/etc/weaver/agents/karl.yaml`, `gate_socket` `/run/weaver-karl/gate.sock`, `trace` the
declaration's trace sink, `admin_bin` `/usr/local/libexec/weaver/weaver-admin`,
`admin_config` `/etc/weaver/config`, and `repo` the stack's worktree at `39fe5732`. It
carries no `spu_bin` and no seed schedule.

## The smokes

As they ran, on olympus from the harness worktree's `code/` directory, each into a
scratch directory, and not rerun, since each drives the stack:

```
python3 determinism_matrix.py --config /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000/config.json --outdir <scratch> --hours 0.03
```

One for karl alone, and one concurrent smoke of both agents, started together. The
scratch directories were copied into the deposit's `evidence/smokes/`.

## The run

As it ran, and not rerun, since it drives the stack for seven hours and writes into the
deposits. Both runs were started together at 23:11:25 CDT on 2026-09-27 by one script,
on olympus from the harness worktree's `code/` directory, detached with `setsid` and
`nohup` so that no terminal held them, with the README's sudo renewal loop. The script,
with the harness worktree's path left out:

```
cd <harness worktree>/experiments/deployment-tuple/baseline/determinism-matrix/code
KO=/bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000
FO=/bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-fred-a6000
( while sleep 120; do sudo -n -v || break; done ) & R=$!
( nvidia-smi dmon -s pc -d 5 -o DT -i 0 > $KO/clock.log 2>&1 & D=$!
  python3 determinism_matrix.py --config $KO/config.json --outdir $KO --hours 7 > $KO/run-console.log 2>&1
  echo "karl exit=$?" > $KO/run-exit.txt
  kill $D ) & A=$!
( nvidia-smi dmon -s pc -d 5 -o DT -i 1 > $FO/clock.log 2>&1 & D=$!
  python3 determinism_matrix.py --config $FO/config.json --outdir $FO --hours 7 > $FO/run-console.log 2>&1
  echo "fred exit=$?" > $FO/run-exit.txt
  kill $D ) & B=$!
wait $A $B
kill $R
```

launched on olympus as

```
setsid nohup <script> > <log> 2>&1 < /dev/null & disown
```

karl's matrix process was PID 2243172 and its `dmon` PID 2243171. The run went from
23:11:26 CDT on 2026-09-27 to 06:11:28 on 2026-09-28, wrote its summary, and wrote
`karl exit=0`.

## The counts

Each to rerun, and each reproduced the note's and the README's figures when this folder
was assembled. As they ran, the same scripts on olympus from the result worktree's root,
with the same deposit paths.

The window, the sweeps, the sessions and verdicts, the counts by prompt character, the
exit, the invocations, the turns compared, unmatched and of more than one token, the
seeds, the device every session bound, and the held fields:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-ampere/record_counts.py /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000
```

The clock paragraph's whole-window figures:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-ampere/clock_stats.py /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000
```

Its per-session figures, the clock samples joined to the sessions, for both A6000 runs:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-ampere/clock_join.py /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000 /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-fred-a6000
```

The one emission per turn slot, and the comparison across the three runs that the
README states:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-ampere/compare_emissions.py /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-karl-a6000 /bulk-store/weaver-testing/determinism-matrix-olympus-2026-09-27-39fe573-fred-a6000 /bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run3
```

## The journal readings

As they ran, on olympus from the executor seat's shell at about 09:25 CDT on
2026-09-28, and not rerun, since they read the journal as it stood then:

```
systemd-analyze cat-config systemd/journald.conf | grep SystemMaxUse
journalctl --system -o short-iso | head -1
journalctl -u weaver-worker@fred.service --since -10min | wc -l
```

They read `SystemMaxUse=50M`, 2026-09-28 09:10:58, and about 120,000 lines, and they
are what the note's journal paragraph rests on.
