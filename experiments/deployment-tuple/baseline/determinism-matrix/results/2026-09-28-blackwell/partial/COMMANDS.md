# How the partial run was executed

As executed, from the operator's `~/.bash_history` on thinkpad, where bash wrote each
multi-line block as one line joined by `;`. Home paths are shown as `~`.

The deposit this names is on the share, and the index beside this folder gives its
path and the sha256 of every file in it. Nothing from it is copied here.

## The harness

`weaver-experiments` at `d04da2a`, run from its `determinism-matrix` directory:
`determinism_matrix.py` `00f2dd76` and `confirm_cells.py` `d17475de`, which the
deposit's `box-facts.txt` records. #716 carried both files into this tree
byte-identical at `afae421`, so git holds them:

```
git show afae421:experiments/deployment-tuple/baseline/determinism-matrix/code/determinism_matrix.py
git show afae421:experiments/deployment-tuple/baseline/determinism-matrix/code/confirm_cells.py
```

In `weaver-experiments` the driver imports `confirm_cells` from
`../cross-precision-repro`, and at `afae421` both files sit together in `code/`.

## The stack, installed before the runs

The stack all four runs used, at 39fe573, built and installed from the deploy worktree,
with the build's own engine libraries installed after it:

```
cd ~/Projects/WeaverTools_Project/deploy-39fe573
NVCC_CCBIN=/usr/bin/g++ CARGO_TARGET_DIR=~/Projects/WeaverTools_Project/deploy-39fe573-target   ./deploy/update-stack.sh --install 2>&1 | tee ~/Projects/WeaverTools_Project/matrix-logs/install-39fe573.log
sudo cp -a /opt/weaver/lib /opt/weaver/lib.backup-20260927
B=~/Projects/WeaverTools_Project/deploy-39fe573-target/release/build/llama-cpp-sys-2-ac8331245f4ed19e/out/lib
for f in libggml-base.so.0.9.11 libggml.so.0.9.11 libggml-cpu.so.0.9.11 libggml-cuda.so.0.9.11 libllama.so.0.0.8783; do sudo install -o root -g root -m 0755 "$B/$f" /opt/weaver/lib/$f; done
```

## The smoke before it

31 sessions, all reproduced, into a scratch directory not kept as a deposit:

```
cd ~/Projects/WeaverTools_Project/weaver-experiments/determinism-matrix
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573
python3 determinism_matrix.py --config $OUT/config.json   --outdir ~/Projects/WeaverTools_Project/matrix-logs/smoke2-39fe573 --hours 0.03
```

## The run

```
cd ~/Projects/WeaverTools_Project/weaver-experiments/determinism-matrix
OUT=/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573
sudo -v
( sudo -n -v && echo renewed || echo refused ) < /dev/null &
( ( while sleep 120; do sudo -n -v || break; done ) & K=$!;   nvidia-smi dmon -s pc -d 5 -o DT > $OUT/clock.log 2>&1 & D=$!;   python3 determinism_matrix.py --config $OUT/config.json --outdir $OUT --hours 7 > $OUT/run-console.log 2>&1;   kill $D $K ) < /dev/null &
```

The run started at 10:58:20 CDT on 2026-09-27 and stopped at 11:44:42, when the
terminal window closed and its hangup ended the run, the clock recorder and the
renewal loop together. `PARTIAL-2026-09-27.md` has the account.

## The counts

The note's session, turn and sweep counts are `record_counts.py` here, run as
`python3 record_counts.py`. It reads the deposit's `matrix.jsonl` and reproduced the
note's figures from it when this folder was assembled. The memory clock's range was
read from the deposit's `clock.log` with `tail`, with no script. Run2's note joins this
run's clock to its sessions, with run2's `clock_join.py`.
