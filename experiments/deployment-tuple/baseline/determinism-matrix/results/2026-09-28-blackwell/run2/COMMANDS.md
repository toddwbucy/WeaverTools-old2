# How run2 was executed

As executed, from the operator's `~/.bash_history` on thinkpad, where bash wrote each
multi-line block as one line joined by `;`. Home paths are shown as `~`.

The deposit this names is on the share, and the index beside this folder gives its
path and the sha256 of every file in it. Nothing from it is copied here.

**Every fenced command says where it runs, and is one of two kinds.** A command marked
*to rerun* runs from the root of a checkout of this repository with the share mounted
at `/mnt/bulk-store`. It names its script by the committed path, reads the deposit by
its absolute path, and writes to stdout. A command marked *as it ran* is what was typed
at the time, kept as the record, and says why it is not rerun.

## The harness

The partial run's: `weaver-experiments` at `d04da2a`, `determinism_matrix.py`
`00f2dd76` and `confirm_cells.py` `d17475de`, carried byte-identical at `afae421`. To
rerun, printing each file:

```
git show afae421:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show afae421:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

The stack is the partial run's, re-hashed unchanged before this run, per the
deposit's `box-facts.txt`. The partial run's `COMMANDS.md` has the install.

## The run

As it ran, the window title set first so the terminal would not be closed again. Its
first line sets the working directory, and it is not rerun, since it drives the stack
for seven hours and writes into the deposit:

```
cd ~/Projects/WeaverTools_Project/weaver-experiments/determinism-matrix
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run2
printf '\e]2;MATRIX RUN - DO NOT CLOSE\a'
sudo -v
( sudo -n -v && echo renewed || echo refused ) < /dev/null &
( ( while sleep 120; do sudo -n -v || break; done ) & K=$!;   nvidia-smi dmon -s pc -d 5 -o DT > $OUT/clock.log 2>&1 & D=$!;   python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT --hours 7 > $OUT/run-console.log 2>&1;   kill $D $K ) < /dev/null &
```

The run went from 11:47:05 to 18:47:08 CDT on 2026-09-27 and wrote its summary.

## After the run

The worker journal was captured at the close, 18:47:34, before journald rotated it,
into a directory that later moved to the deposit as `run2-close/`. As it ran, in one
line: `J` names that directory, under the operator's home, and it is not rerun, since
journald has long since rotated what it read:

```
J=~/Projects/WeaverTools_Project/matrix-logs/run2-close; mkdir -p $J; date +%T > $J/captured-at.txt; journalctl -o short-iso-precise -u 'weaver-worker@karl.service' --no-pager -q > $J/worker-journal.txt 2>&1; journalctl -o json -u 'weaver-worker@karl.service' --no-pager -q --output-fields=_SYSTEMD_INVOCATION_ID,MESSAGE,__REALTIME_TIMESTAMP > $J/worker-journal.json 2>&1; journalctl --disk-usage > $J/journal-usage.txt 2>&1
```

## The counts

Each to rerun, and each reproduced the note's figures when this folder was assembled.

The sessions, the sweeps, the turns compared and unmatched, the turns of more than one
token and the seeds, which the deposit holds as `run2-close/stats.txt`:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run2/stats.py
```

As it ran: from `~/Projects/WeaverTools_Project/matrix-logs`, the file's body given
inline to `python3 - <<'EOF' > run2-close/stats.txt`, on 2026-09-27 at 18:49 CDT.

The 125 sessions inside the captured journal, and the 0 straddling its start:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run2/journal_window_sessions.py
```

As it ran: the file's body given inline to `python3 - <<'EOF'` at 18:49, reading the
deposit by its absolute path.

The 250 distinct invocations that logged a CUDA initialization:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run2/cuda_init_invocations.py
```

As it ran: the file's body given inline to `python3 -c` at 18:47, as the last step of
the capture above, with `$J` for the capture's directory.

Both runs' clock figures, which the deposit holds as `run2-close/clock-join.txt`:

```
python3 experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run2/clock_join.py /mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run2 /mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573
```

As it ran, at 18:49, from a directory under the operator's home that held the script
and the capture:

```
cd ~/Projects/WeaverTools_Project/matrix-logs && timeout 300 python3 clock_join.py /mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run2 /mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573 > run2-close/clock-join.txt 2>&1
```

The CUDA initializations and the device lines in the captured journal, and which device
each bound. These name no script, so they run from any directory:

```
J=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run2/run2-close
grep -c "ggml_cuda_init: found" $J/worker-journal.txt; grep -c "using device CUDA" $J/worker-journal.txt
grep "using device" $J/worker-journal.txt | sed 's/.*using device/using device/' | sed 's/ - [0-9]* MiB free//' | sort | uniq -c
```

As it ran: the same two lines at 18:47, with `J` set to the capture's directory under
the operator's home, as in the capture above.

The journal's size is `run2-close/journal-usage.txt`, written by the capture above.
