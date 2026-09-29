# Stage B, attempt 2, 2026-09-29: python-spu served one turn and the replay certified, with criterion 4 not measured

The operator loaded karl2 through `/etc/weaver/admin-stageb` at 11:57:48 CDT. The
worker (84991e7a), weaver-admin (55529678) and weaver-gate (488babf3) are the b62812e
builds. karl2's SPU is python-spu.pyz (8197449f), built from 850720e, #741's merge,
into a prefix recreated by main's README block. One turn ran and answered. The unload
left the card empty. The diagnostic replay of the turn certified. Five of the six
registered criteria were measured and passed. Criterion 4, the external maps listing,
was not measured, and rests on in-process evidence only.

## What changed since attempt 1

Only python-spu. #741 took triton out of the locks, set `TORCH_DISABLE_NATIVE_JIT=1`
before torch, and added the in-process maps rule. The prefix was removed and installed
again from #741's lock (`attempt2-COMMANDS.md` (a)), so no package of #735's lock remains in it.
`/opt/weaver-stageb/bin`, `/etc/weaver/admin-stageb`, karl2 and the model copy are as
attempt 1 had them. Between b62812e and 850720e, nothing changed in `crates/weaver-types`,
`crates/weaver-admin` or python-spu's `wire.py`. The one other merge, #740, touched
weaver-state only, and the replay ran the b62812e build.

## The timeline, from the system journal

- 11:57:00: the tarball was unpacked into the emptied prefix, and pip installed the lock.
- 11:57:25: the zipapp was built.
- 11:57:48.747: `systemctl reset-failed weaver-worker@karl2`. Attempt 1 left the unit
  failed, and a failed unit's name refuses every later start until it is reaped
  (weaver-admin-Spec, `PriorUnitUnreaped`).
- 11:57:48.773: systemd started the worker with the zipapp as its SPU.
- 11:57:50.885: python-spu loaded the weights (290 tensors). That progress bar is the
  SPU's only output in the unit's journal.
- By 11:58:02.77 the load had answered, and `show` ran.
- 11:58:02.789: the turn.
- 11:58:04.398: the unload.
- 11:58:05.220: `weaver-worker@karl2.service: Deactivated successfully`, after 19.4 s of
  CPU over 16.4 s wall, with a memory peak of 2.4 GB.

## The pass criteria

1. **The load.** It answered, and admin's stage B log carries
   `{"agent":"karl2","outcome":"ready","spu":"python /opt/weaver/python-spu/python-spu.pyz","verb":"load"}`.
   `show` named run `2026-09-29T16:57:48.786Z-karl2-b28bb6c0d88a7d72` and declaration
   335696d9, as the Planner read the operator's console. Pass.
2. **The load event's `stack`** (karl2's trace, run b28bb6c0, sequence 0) is
   `python-spu.pyz` 8197449f, `weaver-gate` 488babf3 and `worker` 84991e7a. Each equals
   the sha256 of the installed file. The zipapp rebuilt from 850720e with the pinned
   interpreter is 8197449f too, so what served is #741's merge, byte for byte. Pass.
3. **The turn.** `turn.txt` is
   `{"kind":"answered","run":"...b28bb6c0d88a7d72","text":"The answer is four.","turn":"t-1"}`.
   The trace carries the turn's `model.request`, `model.output` and `model.measurement`,
   and the measurement's `weights_hash` is be1a0490. That value is blake3 over
   `/opt/weaver/models/qwen2.5-0.5b-instruct-safetensors` by python-spu's own walk,
   recomputed independently here: the directory's hash, not a GGUF's. Pass.
4. **Not measured: the maps listing was not taken.** `pgrep -u weaver-karl2 -f python-spu.pyz`
   matched two processes, the worker (2777435), whose argv names the zipapp, and the SPU
   (2777439). awk was handed `/proc/2777435 2777439/maps` and read nothing, so
   `maps-code.txt` is empty. The defect is in the command the executor wrote.
   **What stands is in-process evidence, which is not the observation registered.** python-spu's `enforce` judges every
   executable file-backed mapping at admission and again after the first generation,
   and exits 3 on a foreign one. The process served past both, and the journal carries
   no `loaded_code_violation`, no import violation and no `python_spu_fault`. The
   replay's SPU passed the same two checks. The card run of 2026-09-29 (#741) is the
   nearest listing: libcuda and libnvidia-ml from `/usr/lib`, the rest from glibc's
   family and the prefix. A later listing selects the SPU alone by its command line,
   which begins with the interpreter the shebang names, where the worker's begins with
   `/opt/weaver-stageb/bin/worker`:
   `pgrep -u weaver-karl2 -f '^/opt/weaver/python-spu/bin/python3.14 '`. Selecting by
   name does not work: a process started through a shebang takes the script's name as
   its comm, checked on this box, so `-x python3.14` would match nothing.
5. **The card after.** While loaded, `nvidia-smi` showed pid 2777439,
   `/opt/weaver/python-spu/bin/python3.14`, at 2422 MiB. After the unload it listed no
   compute process. The unload answered unloaded, and admin's log carries
   `{"outcome":"inactive","verb":"unload"}`. Pass.

## The diagnostic replay: certified

`weaver-analysis derive` refuses a trace holding two runs, and karl2's trace holds
attempt 1's refused run and this one. So the replay's source is
`karl2-trace-run2.ndjson`, the trace's last 11 lines byte for byte (4b8bdc9d), with the
whole trace beside it (`karl2-trace-full.ndjson`, 359519b1).

- `derive` wrote `derived.toml`, session `s-karl2-1-replay`, with the artifact the
  safetensors copy.
- The W4a driver ran the b62812e worker and sqlite `weaver-state` in `unshare -Ur`, with
  the zipapp as the SPU and `CUBLAS_WORKSPACE_CONFIG=:4096:8`.
- **`replay.closed` reads `{"kind": "certified"}`** (`replay-terminal.json`).
- The diagnostic trace runs `replay.opened`, `recall`, `replay.identity` (weights_hash
  be1a0490), the turn's request, output, measurement and assistant message, then
  `turn.closed` and `replay.closed`.
- Both processes exited 0, and the temporary directory was removed
  (`replay-cleanup.json`).
- No log carries a violation, a fault or a traceback. The card was empty after.

## The recreated prefix, measured afterwards by the executor, read-only

- `installed_set.py requirements.lock`, run by the prefix's interpreter with `-I -B`:
  exit 0, nothing printed.
- `tree_digest.py /opt/weaver/python-spu`: 1dce454a... (`tree-digest.txt`).
- `python-spu.pyz` 8197449f and `requirements.lock` 9aa7e037 (`python-spu.sha256`).
- No file under the prefix is newer than the zipapp, so serving wrote nothing into it.

The operator ran part (a)'s `installed_set` line unprivileged, so the system journal
does not record it. The clean exit above is the executor's reading after the run.

## Nothing else changed

Three pairs. The `untouched` and `admin-log` pairs diff empty. The karl pair differs in
its first line only, which is the capture's own timestamp, and its other lines are
equal:

```
$ diff karl-before.txt karl-after.txt
1c1
< 2026-09-29 11:50:29 CDT
---
> 2026-09-29 11:58:51 CDT
```

- `karl-before.txt` and `karl-after.txt`: below the timestamp, `weaver-worker@karl.service`
  inactive, and no `/run/weaver-karl`, in both. From attempt 3 on, the timestamp is
  written to a file of its own, so the pair can diff empty.
- `untouched-before.sha256` and `untouched-after.sha256`, 35 lines each:
  `/etc/weaver/admin/*`, `/opt/weaver/bin/*`, `/opt/weaver/lib/*`, karl's declaration
  a2a03d10, and karl's trace by size and mtime (3,839,610,101 bytes).
- `admin-log-before.sha256` and `admin-log-after.sha256`: admin's own log, 102c7aba,
  written by the operator's sudo lines. It has its own pair so that no file mixes two
  writers.

## Files

In the deposit, beside this record: `COMMANDS.md`, the sequence as run, which is
`attempt2-COMMANDS.md` here. `worker-journal.txt` is karl2's unit, followed live.
Also in the deposit: `turn.txt`, `nvidia-smi-loaded.txt`, `nvidia-smi-after.txt`,
`admin-stageb-log-tail.txt`, `maps-code.txt` (empty, criterion 4), the before and after
pairs, `tree-digest.txt`, `python-spu.sha256`, `traces.sha256`, both trace copies,
`derived.toml`, `derive.out`, and the replay's `replay-*` files.
