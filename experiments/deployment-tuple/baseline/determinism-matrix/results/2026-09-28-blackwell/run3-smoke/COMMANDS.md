# How the run3 smoke was executed

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

WeaverTools main at `07a7e5d`, #716 merged, run from the primary checkout at that
commit: `determinism_matrix.py` `2657c8b2` and `confirm_cells.py` `25ab96db`, per the
deposit's `box-facts.txt`. git holds them. To rerun, printing each
file:

```
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show 07a7e5d:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

The stack is the partial run's, at 39fe573, unchanged.

## The run

As it ran: its second line sets the working directory, the primary checkout at
`07a7e5d`, and it is not rerun, since it drives the stack and writes into the deposit:

```
printf '\e]2;MATRIX SMOKE - DO NOT CLOSE\a'
cd ~/Projects/WeaverTools_Project/WeaverTools/experiments/deployment-tuple/baseline/determinism-matrix/code
sudo -v
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run3-smoke
python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT --hours 0.03 2>&1 | tail -5; echo "exit ${PIPESTATUS[0]}"
```

Its console output:

```
[21:43:31] i1 creative-long/d32: REPRODUCED (9.6s) H_mean=1.086466
[21:43:32] done: 31/31 reproduced, 0 diverged, 0 errors
[21:43:32]   confident: 12/12
[21:43:32]   mid: 8/8
[21:43:32]   near-tie: 11/11
exit 0
```

The smoke ran without the clock recorder and without `run-console.log`, which is why
its deposit holds neither. It wrote no result note, and the index states its result
from the console output above and the deposit's `summary.json`, with no script.
