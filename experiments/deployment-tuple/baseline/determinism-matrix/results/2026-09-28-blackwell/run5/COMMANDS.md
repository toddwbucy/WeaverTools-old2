# How run5 was executed

The deposit this names is on the share, and the index beside this folder gives its
path and the sha256 of every file in it. Nothing from it is copied here but the note.

**Every fenced command says where it runs, and is one of two kinds.** A command marked
*to rerun* runs from the root of a checkout of this repository with the share mounted
at `/mnt/bulk-store`. It names its script by the committed path, reads the deposit by
its absolute path, and writes to stdout. A command marked *as it ran* is what was typed
at the time, kept as the record, and says why it is not rerun.

## The harness

WeaverTools main at `bb28f4f`, run from the primary checkout at that commit:
`determinism_matrix.py` `37b5de3c` and `confirm_cells.py` `25ab96db`, both unchanged
since run4. To rerun, printing each file:

```
git show bb28f4f:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show bb28f4f:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

The stack is run3's, at 39fe573, re-hashed unchanged before this run, per the deposit's
`box-facts.txt`, which also records the two journald settings the run ran under and
the file each lives in.

## The smoke and the run

The operator ran both from their own terminal, and its echo was not returned to this
seat, so neither command is given here as typed. What the deposits show:

- The smoke, `determinism-matrix-thinkpad-2026-09-28-39fe573-run5-smoke`, ran from
  19:49:36 to 19:51:30 CDT on 2026-09-28 and wrote its summary, 31 of 31 reproduced.
  It has no clock log.
- The run's `matrix.log` opens at 19:51:54 and closes at 02:52:09 on 2026-09-29.
  `run-console.log` is byte-identical to it, and `clock.log`, the output of
  `nvidia-smi dmon -s pc -d 5 -o DT` by its header, opens the same second, which is
  run3's arrangement.
  `found.txt` records the matrix process as PID 2062688.

## During and after the run

`launch.py` here, a watcher, ran from 19:47 in a scratch directory under the operator's
home, not rerun since it waits for a process that has exited. It found the matrix
process by its exact `--outdir` in `/proc`, never by a pattern that could match itself,
copied `capture.py` into the deposit's `run5-evidence/`, and started it with the first
read from a minute before the process was found. As it ran, from that directory:

```
python3 launch.py > launch.out 2>&1
```

It printed `capture pid 2062723 for matrix pid 2062688, since 2026-09-28 19:50:55`.

`capture.py` here is the deposit's copy, the one that ran. Read-only, every two minutes
over the last five, it appended each worker line carrying a device marker to
`markers.jsonl`, rewrote each invocation's line count to `line-counts.json`, and
appended journald's Suppressed lines to `suppressed.txt`, which stayed empty. It read
once more after the matrix process exited and stopped at 02:53:48.

The journal read after the run, as it ran at 02:57 CDT from the operator's uid, into the
deposit's `run5-evidence/journal-after.txt`, which carries each command beside its
output. It is not rerun, since the journal it read rotates:

```
journalctl --disk-usage
journalctl -o short-iso-precise -q --no-pager | head -1
journalctl -u systemd-journald --since "2026-09-28 19:49:00" --until "2026-09-29 02:55:00" -q --no-pager -g Suppressed | wc -l
journalctl -u weaver-worker@karl.service --since "2026-09-28 19:51:50" --until "2026-09-29 02:52:30" -o cat -q --no-pager | wc -l
```

## The counts

Each to rerun, and each reproduced the note's figures when this folder was assembled.
Each wrote its output into the deposit's `run5-evidence/` when it ran.

The summary's counts and windows, the sweeps, the turns compared and unmatched, the
turns of more than one token, the 13,710 invocations, the device binding and the seeds,
`record-counts.txt`:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run5/record_counts.py
```

The capture's invocations and lines, every record invocation among them with one of
each device marker, the smoke's 62 and the lines under no invocation ID, and the empty
`suppressed.txt`, `invocation-markers.txt`:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run5/invocation_markers.py
```

The clock figures, `clock-join.txt`, by run3's script unchanged:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run3/clock_join.py /mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run5
```

As they ran: each from a scratch directory under the operator's home at 02:55 to
02:57 CDT, the same files, and then copied into the deposit. The prompt-character
counts are the harness's own, in the deposit's `summary.json`.
