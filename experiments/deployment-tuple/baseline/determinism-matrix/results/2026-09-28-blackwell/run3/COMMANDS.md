# How run3 was executed

As executed, from the operator's terminal echo, which they pasted back. The prompt,
which carries a username, is left out.

The deposit this names is on the share, and the index beside this folder gives its
path and the sha256 of every file in it. Nothing from it is copied here.

**Every fenced command says where it runs, and is one of two kinds.** A command marked
*to rerun* runs from the root of a checkout of this repository with the share mounted
at `/mnt/bulk-store`. It names its script by the committed path, reads the deposit by
its absolute path, and writes to stdout. A command marked *as it ran* is what was typed
at the time, kept as the record, and says why it is not rerun.

## The harness

WeaverTools main at `07a7e5d`, as for the smoke, run from the primary checkout at that
commit: `determinism_matrix.py` `2657c8b2` and `confirm_cells.py` `25ab96db`. To rerun,
printing each file:

```
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

The stack is the partial run's, at 39fe573, re-hashed unchanged before this run, per
the deposit's `box-facts.txt`.

## The run

As it ran, in two parts: its second line sets the working directory, the primary
checkout at `07a7e5d`, and it is not rerun, since it drives the stack for seven hours
and writes into the deposit:

```
printf '\e]2;MATRIX RUN - DO NOT CLOSE\a'
cd ~/Projects/WeaverTools_Project/WeaverTools/experiments/deployment-tuple/baseline/determinism-matrix/code
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run3
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

The console printed `[1] 1007011`, and the matrix process was PID 1007014. The run went
from 21:55:05 CDT on 2026-09-27 to 04:55:09 on 2026-09-28 and wrote its summary.

## During and after the run

`capture.py` here ran beside the run from 01:12, read-only. As it ran, from its own
directory under the operator's home, and not rerun, since it reads the live journal and
appends to files beside itself:

```
cd ~/Projects/WeaverTools_Project/run3-evidence && python3 capture.py "2026-09-27 21:55"
```

Every five minutes it appended journald's Suppressed lines to `suppressed.txt` and each
worker invocation's line count and device markers to `invocations.jsonl`, and it
stopped when the run ended. After the run, as it ran in that directory:

```
sort -u suppressed.txt > suppressed-unique.txt && awk '{s+=$5; n++} END{print n" events, "s" messages"}' suppressed-unique.txt
```

In the same line, `invocations_final.py` here, its body given inline to
`python3 - <<'EOF'`, wrote `invocations-final.jsonl`, each invocation's fullest read. It
is not rerun, since its input was not kept. Both results moved to the deposit's
`run3-evidence/`, and the two raw files were not kept.

## The counts

Each to rerun, and each reproduced the note's figures when this folder was assembled.

The 58 Suppressed events and 9,491 messages. This names no script, so it runs from any
directory:

```
awk '{s+=$5; n++} END{print n" events, "s" messages"}' /mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run3/run3-evidence/suppressed-unique.txt
```

As it ran: the `awk` above, over the file in its directory under the operator's home.

The summary's counts and window, the faulted session, the sweeps, the turns compared and
unmatched, the turns of more than one token, the 13,772 invocations, the device binding
and the seeds:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run3/record_counts.py
```

As it ran: the file's body given inline to `python3 - <<EOF` on 2026-09-28 at 04:56 CDT,
with `$R` for the deposit.

The 7,471 invocations captured, the faulted one's 490 lines without a marker, and the
rest carrying all three:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run3/invocation_markers.py
```

As it ran: the file's body given inline to `python3 - <<'EOF'` at 04:56, reading the raw
`invocations.jsonl` under the operator's home. Its header says why the committed copy
reads `invocations-final.jsonl` and gives the same output.

The clock figures, which the deposit holds as `run3-evidence/clock-join.txt`:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run3/clock_join.py /mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run3
```

As it ran, at 04:57, with the script in its directory under the operator's home:

```
E=~/Projects/WeaverTools_Project/run3-evidence; B=/mnt/bulk-store/weaver-testing
timeout 600 python3 $E/clock_join.py $B/determinism-matrix-thinkpad-2026-09-27-39fe573-run3 > $E/clock-join.txt 2>&1
```

This copy differs from run2's in skipping a session with no replay run, which the
faulted session is. The prompt-character counts are the harness's own, in the deposit's
`summary.json`.
