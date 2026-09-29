# How the label-split measurement was run

As run on olympus on 2026-09-29 from the executor seat's shell, and recorded from it.
`<herobench>` is a checkout of the HeroBench fork at `32c1e0f`, `<repo>` a checkout of
this repository, and `<deposit>` is
`/bulk-store/weaver-testing/herobench-positions-2026-09-29` on olympus, the same path
under `/mnt/bulk-store/weaver-testing/` on the thinkpad.

**Every fenced command says where it runs, and is one of two kinds.** A command marked
*to rerun* reads only committed files and the benchmark's own, and writes to the path
it names. A command marked *as it ran* is what was typed at the time, kept as the
record, and says why it is not rerun as it stands.

## The environment

As it ran, and not rerun, since it starts servers. One arm of the fork's harness,
SQLite, which flushes no redis database:

```
cd <herobench>/weaver/bench && ./herobench up --arms 1 --no-install
```

The fork's server enforces one-tile moves and the recorded results predate that, so
the replay also ran against the benchmark's tree at `7a9579e`, the last upstream commit
before the fork's gameplay changes, exported without touching the checkout and served on
a loopback port from a directory holding the `app` link the server's relative paths
need:

```
git -C <herobench> archive 7a9579e | tar -x -C <upstream-tree>
mkdir <arm-dir> && ln -s <upstream-tree>/Virtual_Environment/FastApi_SQLite_Ver/app <arm-dir>/app
cd <arm-dir> && <herobench>/.venv/bin/fastapi run \
  <upstream-tree>/Virtual_Environment/FastApi_SQLite_Ver/main.py --host 127.0.0.1 --port 8020
```

## The replay

To rerun, with a server of each kind up as above, from the tree whose `utils` and
`api_calls` are to be used, the fork's shim redirecting the benchmark's `:8000` to the
arm's port:

```
cd <upstream-tree> && PYTHONPATH=<herobench>/weaver/bench/shim:<upstream-tree> \
  HEROBENCH_PORT=8020 <herobench>/.venv/bin/python \
  <repo>/experiments/trace-content/label-split/code/replay.py \
  <upstream-tree> gpt-4.1 1 "14_Cultist Emperor_kill" <deposit>/replay/gpt-4.1_1_14.json
```

and the same for `"5_Cultist Emperor_kill"` into `gpt-4.1_1_5.json`. Against the
fork's server, with `<herobench>` in place of `<upstream-tree>` and port 8000, into
`<deposit>/replay-fork-server/`. Each prints whether its log matches the recorded one.
The replay reproduces recorded programs the pipeline already ran to completion and
bounds them with an in-process alarm a program could catch or cancel, unlike
`safe_exec`'s process join, so it is a reproduction of known runs and not a sandbox for
unknown code.

The position table of each, to rerun:

```
python3 <repo>/experiments/trace-content/label-split/code/positions_table.py \
  <deposit>/replay/gpt-4.1_1_14.json 160
```

## The split

To rerun. It reads `<herobench>`'s results, scoring, datasets and data tables, writes
`positions.jsonl`, `completions.jsonl` and `split.json` into the directory it names,
and prints the summary kept as `<deposit>/split/summary.txt`:

```
python3 <repo>/experiments/trace-content/label-split/code/segment.py <herobench> <out-dir>
python3 <repo>/experiments/trace-content/label-split/code/tables.py <out-dir>/split.json
```

The second prints the tables kept as `<deposit>/split/tables.md`, every share the
result note states among them.

## The specimen

To rerun, for each of `pumpkin` and `spice`:

```
python3 <repo>/experiments/trace-content/label-split/code/specimen.py pumpkin \
  <herobench>/results/results_base <herobench>/results/results_hard \
  <herobench>/results/results_base_scoring <herobench>/results/results_hard_scoring \
  ~/.local/state/herobench <herobench>/datasets \
  <herobench>/Virtual_Environment/FastApi_SQLite_Ver/app/Data \
  /bulk-store/arangodb_dumps/weaver-demo-herobench-gpu1-end-of-run1-2026-04-27
```

Each exits 0, every root read and every file opened. A root that does not exist or
cannot be traversed refuses the run before it searches, and a directory or file the
walk cannot read is printed and makes the run exit 1, so a count of zero is a count
and never a place it could not see.

As it ran for the gpu0 dump, whose collections are readable only by the account that
wrote them, and not rerun as it stands: the same search read as that account, each
collection decompressed, with no match for either word in any collection.
