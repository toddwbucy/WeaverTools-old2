# How run2 was executed

As executed, from the operator's `~/.bash_history` on thinkpad, where bash wrote each
multi-line block as one line joined by `;`. Home paths are shown as `~`.

The deposit this names is on the share, and the index beside this folder gives its
path and the sha256 of every file in it. Nothing from it is copied here.

## The harness

The partial run's: `weaver-experiments` at `d04da2a`, `determinism_matrix.py`
`00f2dd76` and `confirm_cells.py` `d17475de`, carried byte-identical at `afae421`:

```
git show afae421:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show afae421:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

The stack is the partial run's, re-hashed unchanged before this run, per the
deposit's `box-facts.txt`. The partial run's `COMMANDS.md` has the install.

## The run

The window title set first so the terminal would not be closed again:

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
into a directory that later moved to the deposit as `run2-close/`:

```
J=~/Projects/WeaverTools_Project/matrix-logs/run2-close; mkdir -p $J; date +%T > $J/captured-at.txt; journalctl -o short-iso-precise -u 'weaver-worker@karl.service' --no-pager -q > $J/worker-journal.txt 2>&1; journalctl -o json -u 'weaver-worker@karl.service' --no-pager -q --output-fields=_SYSTEMD_INVOCATION_ID,MESSAGE,__REALTIME_TIMESTAMP > $J/worker-journal.json 2>&1; journalctl --disk-usage > $J/journal-usage.txt 2>&1
```

## The counts

Each script here reads the deposit on the share by its full path, and each reproduced
the note's figures from it when this folder was assembled.

- `stats.py`, run as `python3 stats.py > run2-close/stats.txt`, gives the sessions, the
  sweeps, the turns compared and unmatched, the turns of more than one token and the
  seeds.
- `journal_window_sessions.py`, run as `python3 journal_window_sessions.py`, gives the
  125 sessions inside the captured journal and the 0 straddling its start.
- `cuda_init_invocations.py`, run as `python3 cuda_init_invocations.py`, gives the 250
  distinct invocations that logged a CUDA initialization.
- `clock_join.py`, run as `python3 clock_join.py <run2 deposit> <partial deposit> >
  run2-close/clock-join.txt`, gives both runs' clock figures.

Three counts came from shell lines over the captured journal, here with `J` set to the
deposit's `run2-close/`. The initializations and the device lines:

```
grep -c "ggml_cuda_init: found" $J/worker-journal.txt; grep -c "using device CUDA" $J/worker-journal.txt
```

Which device each of them bound:

```
grep "using device" $J/worker-journal.txt | sed 's/.*using device/using device/' | sed 's/ - [0-9]* MiB free//' | sort | uniq -c
```

The journal's size is `run2-close/journal-usage.txt`, written by the capture above.
