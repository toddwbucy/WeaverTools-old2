# How run4 was executed

The deposit this names is on the share, and the index beside this folder gives its
path and the sha256 of every file in it. Nothing from it is copied here but the note.

**Every fenced command says where it runs, and is one of two kinds.** A command marked
*to rerun* runs from the root of a checkout of this repository with the share mounted
at `/mnt/bulk-store`. It names its script by the committed path, reads the deposit by
its absolute path, and writes to stdout. A command marked *as it ran* is what was typed
at the time, kept as the record, and says why it is not rerun.

## The harness

WeaverTools main at `6072c69`, run from the primary checkout at that commit:
`determinism_matrix.py` `37b5de3c`, #717's, and `confirm_cells.py` `25ab96db`, run3's.
To rerun, printing each file:

```
git show 6072c69:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show 6072c69:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

The stack is run3's, at 39fe573, re-hashed unchanged before this run, per the deposit's
`box-facts.txt`, which also records the worker unit's properties and journal retention.

## The smokes

Two smokes ran before the run, one per rate-limit setting, and their comparison is in
the run's `box-facts.txt`. Each is as executed, from the operator's terminal echo, which
they pasted back, with the prompt left out. Each ran from the harness's `code/`
directory in the primary checkout after `sudo -v`, and none is rerun, since each changes
root-owned configuration or drives the stack.

The first setting, then the first smoke:

```
echo 'LogRateLimitIntervalSec=0' | sudo tee -a /etc/weaver/admin/unit-properties
```

```
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run4-smoke
S=$(date '+%F %T')
python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT --hours 0.03 2>&1 | tail -5; echo "exit ${PIPESTATUS[0]}"
systemctl show 'weaver-worker@karl.service' -p LogRateLimitIntervalUSec
journalctl --since "$S" -q -g 'Suppressed' | grep -c weaver-worker
```

It printed 31 of 31 reproduced, `exit 0`, `LogRateLimitIntervalUSec=0` and a count of
1, the Suppressed line that showed an interval of 0 does not lift the limit.

The second setting, then the second smoke, the same lines without the `systemctl` one:

```
sudo sed -i 's/^LogRateLimitIntervalSec=0$/LogRateLimitIntervalSec=30s\nLogRateLimitBurst=1000000/' /etc/weaver/admin/unit-properties
```

```
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run4-smoke2
S=$(date '+%F %T')
python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT --hours 0.03 2>&1 | tail -5; echo "exit ${PIPESTATUS[0]}"
journalctl --since "$S" -q -g 'Suppressed' | grep -c weaver-worker
```

Its console tail was not pasted back. Its summary reads 31 of 31 reproduced.

## The run

As given to the operator, not echoed: no echo of this run's launch was pasted back.
It is run5's block with this run's deposit, which is run3's arrangement, and the
deposit agrees with it. `matrix.log` opens at 10:06:53 and closes at 14:42:09,
`run-console.log` is byte-identical to it, and `clock.log` is `nvidia-smi dmon`'s
output by its header. Not rerun, since it drives the stack for hours and writes into
the deposit:

```
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run4
sudo -v
( sudo -n -v && echo renewed || echo refused ) < /dev/null &
```

Then:

```
( ( while sleep 120; do sudo -n -v || break; done ) & K=$!
  nvidia-smi dmon -s pc -d 5 -o DT > $OUT/clock.log 2>&1 & D=$!
  python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT \
    --hours 7 > $OUT/run-console.log 2>&1
  kill $D $K ) < /dev/null &
```

The operator interrupted it at 14:42 to free the card, and unloaded karl by hand after
the harness's closing unload was refused.

## During and after the run

`capture.py` here is the deposit's copy, the one that ran. It was written into the
deposit's `run4-evidence/` at 14:41 and started there, read-only, against the matrix
process. As it ran, not rerun since it reads the live journal and appends beside itself:

```
cd $D && nohup setsid python3 capture.py 1605135 > capture.stderr 2>&1 < /dev/null &
```

with `$D` the deposit's `run4-evidence/`. Its first read, at 14:41:12, took the journal
from 00:00, which then held back to 14:27:40. It read once more after the matrix process
exited and stopped at 14:43:14.

## The counts

Each to rerun, and each reproduced the note's figures when this folder was assembled.
Each wrote its output into the deposit's `run4-evidence/` when it ran, on 2026-09-29.

The summary's counts and windows, the two faulted records, the sweeps, the turns
compared and unmatched, the turns of more than one token, the invocations, the device
binding and the seeds, `record-counts.txt`:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run4/record_counts.py
```

The capture's 294 invocations with one of each device marker, the 13:24 fault's two
invocations absent from it, the empty `suppressed.txt` and the capture's reads,
`invocation-markers.txt`:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run4/invocation_markers.py
```

The clock figures, `clock-join.txt`, by run3's script unchanged:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run3/clock_join.py /mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run4
```

As they ran: each from a scratch directory under the operator's home on 2026-09-29, the
same files, and then copied into the deposit. The prompt-character counts are the
harness's own, in the deposit's `summary.json`.
