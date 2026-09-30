# Stage B2 result, thinkpad, 2026-09-30: karl2 end to end at main, every criterion measured

A dated result, read by no gate. **Claim:** an agent whose SPU is python-spu, here
python-spu at 112ec31c on the dc3a0f7a stack, loads under admin with the worker's
`--headroom-bytes`, answers a turn, and unloads with the card empty. The load event's
`stack` names what served. The SPU is one process mapping only admitted code, read from
outside while it serves. The turn's diagnostic replay certifies, and nothing of karl's
changes. **All nine of `PLAN.md`'s criteria were measured and passed**, criterion 4, the
external maps listing, among them. Stage B left that one untaken.

**Scope:**
- one agent, karl2, and one turn;
- one card, an RTX PRO 5000 Blackwell on driver 615.71.09;
- Qwen2.5-0.5B-Instruct safetensors at BF16.

The deposit is on the shared bulk store at
`/bulk-store/weaver-testing/stage-b2-thinkpad-2026-09-30-dc3a0f7/`, mounted on the
thinkpad under `/mnt/bulk-store/weaver-testing/`. It holds `build/` and `build-resume/`,
both runs' evidence in `run/` and `run2/`, and the traces, journals and logs. None of it
is copied here. `deposit.sha256` gives every deposit file's sha256 and path, except this
report's own copy.

**What is here:**
- this report;
- `PLAN.md`, the criteria registered before the first run;
- `stage-b2.sh` and `stage-b2-resume.sh`, the two root scripts as the operator ran them;
- `deposit.sha256`.

**The copies are scrubbed of one box's paths.** In `PLAN.md`, `<workspace>` is the
operator's checkout directory, `<agents>` the agent-configuration directory and
`<operator>` the operator's account. The scripts carry the same three as `$WORKSPACE`,
`$AGENTS_DIR` and `$OPERATOR`, so they still parse. The deposit keeps the originals.

## What differs from stage B

- **Every binary was rebuilt at dc3a0f7a:** the worker, weaver-admin, weaver-gate,
  weaver-analysis and weaver-state (`build/binaries.sha256`).
- **python-spu was built at 112ec31c.** That tree includes #749's BF16 load, #754's
  argument vector, room judgment and pinned admit, and #756's single process.
- **admin-stageb gained `headroom-bytes` 268435456.**
- **`unit-properties` dropped `CUBLAS_WORKSPACE_CONFIG`.**
- **The python-spu prefix stayed as stage B installed it.** `installed_set.py` exits 0
  against the lock, and only the zipapp was swapped.

## Two runs

**The first run, `run/`, at dc3a0f7a's zipapp, stopped at its step 3.**
- The install, the admin-stageb edits, admin's `validate`, the load and the turn all
  passed. The turn answered "The answer is four." in run
  `2026-09-30T04:36:55.630Z-karl2-0fb10116cee8c2e2`.
- The anchored selector then matched two processes. Every python-spu process had
  started Python's multiprocessing resource tracker during the load: transformers'
  progress bar made a tqdm, whose default write lock is a multiprocessing lock.
- The script unloaded karl2 once and stopped.
- **That second process was the finding.** #756, merged `112ec31`, removed it, removed
  a transient `ldconfig` spawn as well, and pinned that the SPU is one process.

**The resume, `run2/`, 07:43:54 to 07:44:41, at 112ec31c's zipapp (bf1e0870) on the
dc3a0f7a stack.**
- It checked read-only what the first run had left: the dc3a0f7a binaries with the
  b62812e set beside them, admin-stageb's edits and backup, admin's `validate`, the
  prefix and its digest 2cb9db60, the card empty, and karl and karl2 not loaded.
- It installed only #756's zipapp, dc3a0f7a's kept beside it.
- It ran stage B2's steps 3 to 5 unchanged. **Every step passed.**

## The criteria, run2

| # | Criterion | Evidence (`run2/`) | Result |
| --- | --- | --- | --- |
| 1 | the load answers idle, and admin's log names the SPU | `load.txt`: `{"kind":"state","state":"idle"}`. `admin-stageb-log-tail.txt`: `{"agent":"karl2","outcome":"ready","spu":"python /opt/weaver/python-spu/python-spu.pyz","verb":"load"}` | pass |
| 2 | the load event's `stack` names the SPU by the installed file's sha256 | `trace-judged.json`: `python-spu.pyz` bf1e0870, the installed file | pass |
| 3 | one turn is answered, with its request and measurement, and the weights hash is stage B's | `turn.txt`: "The answer is four." in run `2026-09-30T12:43:58.710Z-karl2-7693a6ae238c63f8`. The trace has `model.request`, `model.output` and `model.measurement`, and `weights_hash` be1a0490 | pass |
| 4 | **only admitted code is mapped, read from outside** | `spu-pid.txt`: **exactly one pid**, 2968909, selected by `pgrep -u weaver-karl2 -f '^/opt/weaver/python-spu/bin/python3.14 '`. `maps-code.txt`: 72 executable file-backed mappings, 60 in the prefix and 12 system objects (glibc's family, libgcc_s, libstdc++, zlib-ng, `libcuda.so.615.71.09`, `libnvidia-ml.so.615.71.09`). `maps-judged.json`: python-spu's `loaded_code.foreign` over the prefix answers `[]` | **pass, measured** |
| 5 | the card is empty after the unload, and the unit is inactive | `nvidia-smi-after-unload.txt` is empty. While loaded, `nvidia-smi-loaded.txt` showed pid 2968909 at 1412 MiB | pass |
| 6 | the diagnostic replay of the turn certifies | `replay-terminal.json`: `replay.closed` `{"kind":"certified"}`. `replay-cleanup.json`: exit codes `[0, 0]`, nothing signalled, temporary directory removed | pass |
| 7 | the stack is the new build | the stack is `python-spu.pyz` bf1e0870, `worker` d157f76e and `weaver-gate` 1f1a2f1e, each equal to the installed file. The worker and gate are the dc3a0f7a build, `build/binaries.sha256` | pass |
| 8 | the worker's vector carried `--headroom-bytes 268435456` | `worker-journal.txt`: `Started [systemd-run] .../worker .../coordination.sock .../python-spu.pyz .../weaver-gate --headroom-bytes 268435456`. `spu-cmdline.txt`: `python3.14 python-spu.pyz --headroom-bytes 268435456` | pass |
| 9 | the unit's environment had no `CUBLAS_WORKSPACE_CONFIG` | `unit-environment.txt`: `Environment=` is empty. `spu-environ.txt` is empty | pass, with the reading below |

**Beside the criteria, nothing of karl's changed.** `karl-*.txt`,
`untouched-*.sha256` and `admin-log-*.sha256` each diff empty, with the capture time
kept apart. The journal carries no violation, fault or refusal line. The run is one run
of 11 records.

**Reading criterion 9.** The SPU's environment is empty because the worker starts it
that way: weaver-harness `spawn.rs:83` calls `execve` with an empty `envp`. So nothing
set in a unit's `Environment=` ever reaches an SPU. That includes the
`CUBLAS_WORKSPACE_CONFIG` stage B's `unit-properties` carried, which was therefore never
in its SPU. python-spu sets the variable for itself at its first import (#754), inside
the process, where `/proc/<pid>/environ`, the environment at exec, cannot show it. The
measured fact is that no deployment line supplied it.

**One label in the resume's log is stale.** Its step-3 line reads "the load event's
stack is the installed dc3a0f7a zipapp". The zipapp installed was 112ec31c's, and the
check compared the stack with the installed file, so the result stands and only the
label is out of date.

## What this does not establish

- **A serving run with its state member.** Admin stands the member only when
  `weaver-state` sits beside the worker, and `/opt/weaver-stageb/bin` holds none. So
  weaver-state at dc3a0f7a, the typed-state work, was exercised only by the replay,
  which ran the built one. That is #726's item "A karl2 run with its state member
  stood".
- **Two SPUs on one card, or the comparison with the Rust SPU.** That is stage C.
- **More than one turn.**
