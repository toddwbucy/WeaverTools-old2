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

## The journal's cap, the smoke and the run

Each as executed, from the operator's terminal echo, which they pasted back to the
Planner, with the prompt left out. None is rerun, since each changes root-owned
configuration or drives the stack.

The journal's size cap, raised first:

```
sudo mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=4G\n' | sudo tee /etc/systemd/journald.conf.d/50-weaver-runs.conf
sudo systemctl restart systemd-journald
journalctl --disk-usage
```

`journalctl --disk-usage` printed 50M, the journal's size as the old cap had left
it. The smoke, from the harness's `code/` directory in the primary checkout after
`sudo -v`, run4's smoke lines without the `systemctl` one:

```
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run5-smoke
S=$(date '+%F %T')
python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT --hours 0.03 2>&1 | tail -5; echo "exit ${PIPESTATUS[0]}"
journalctl --since "$S" -q -g 'Suppressed' | grep -c weaver-worker
```

It printed 31 of 31 reproduced, `exit 0`, and a count of 0. Then the run, run3's
arrangement, from the same directory:

```
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run5
sudo -v
( sudo -n -v && echo renewed || echo refused ) < /dev/null &
```

The console printed `renewed`. Then:

```
( ( while sleep 120; do sudo -n -v || break; done ) & K=$!
  nvidia-smi dmon -s pc -d 5 -o DT > $OUT/clock.log 2>&1 & D=$!
  python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT \
    --hours 7 > $OUT/run-console.log 2>&1
  kill $D $K ) < /dev/null &
```

The console printed `[1] 2062685`, and the matrix process was PID 2062688, per
`run5-evidence/found.txt`. `matrix.log` opens at 19:51:54 and closes at 02:52:09 on
2026-09-29, and `run-console.log` is byte-identical to it.

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
