# How run3 was executed

As executed, from the operator's terminal echo, which they pasted back. The prompt,
which carries a username, is left out.

The deposit this names is on the share, and the index beside this folder gives its
path and the sha256 of every file in it. Nothing from it is copied here.

## The harness

WeaverTools main at `07a7e5d`, as for the smoke, run from the primary checkout at that
commit: `determinism_matrix.py` `2657c8b2` and `confirm_cells.py` `25ab96db`:

```
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

The stack is the partial run's, at 39fe573, re-hashed unchanged before this run, per
the deposit's `box-facts.txt`.

## The run

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

`capture.py` here ran beside the run from 01:12, read-only, as
`python3 capture.py "2026-09-27 21:55"`, from a directory under the operator's home.
Every five minutes it appended journald's Suppressed lines to `suppressed.txt` and each
worker invocation's line count and device markers to `invocations.jsonl`, and it
stopped when the run ended. After the run, in that directory:

```
sort -u suppressed.txt > suppressed-unique.txt && awk '{s+=$5; n++} END{print n" events, "s" messages"}' suppressed-unique.txt
```

That gives the note's 58 events and 9,491 messages, and `invocations_final.py` here,
run as `python3 invocations_final.py`, wrote `invocations-final.jsonl`, each
invocation's fullest read. Both results moved to the deposit's `run3-evidence/`, and
the two raw files were not kept.

## The counts

Each script here reads the deposit on the share by its full path, and each reproduced
the note's figures from it when this folder was assembled.

- `record_counts.py`, run as `python3 record_counts.py`, gives the summary's counts and
  window, the faulted session, the sweeps, the turns compared and unmatched, the turns
  of more than one token, the 13,772 invocations, the device binding and the seeds.
- `invocation_markers.py`, run as `python3 invocation_markers.py`, gives the 7,471
  invocations captured, the faulted one's 490 lines without a marker, and the rest
  carrying all three.
- `clock_join.py`, run3's copy, run as `python3 clock_join.py <run3 deposit> >
  run3-evidence/clock-join.txt`, gives the clock figures. It differs from run2's copy
  in skipping a session with no replay run, which the faulted session is.

The prompt-character counts are the harness's own, in the deposit's `summary.json`.
