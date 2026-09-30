# Stage B2 plan: karl2 end to end at main dc3a0f7a, on thinkpad

Registered 2026-09-29, before the run. The operator runs `sudo bash stage-b2.sh` from
this directory, one password, and the result is written from `run/` afterwards.

## What differs from stage B (b62812e, with python-spu at 850720e)

- **Every binary is rebuilt at dc3a0f7a.** That covers weaver-state's typed state
  (#740 on), the harness's classify deadline, and python-spu's BF16 load (#749), its
  argument vector, its room judgment and its pinned admit (#754). The build is in
  `build/`: the worker, weaver-admin, weaver-gate, weaver-analysis and weaver-state
  from a clean detached worktree at dc3a0f7a, `--release --locked`, with their sha256
  in `binaries.sha256`, and the zipapp 7e3e01b8 from the same tree.
- **The python-spu prefix stays.** The locks are unchanged since 850720e, and read
  before the run, `installed_set.py` exits 0 and the tree digest is stage B's 1dce454a.
  Only the zipapp is replaced.
- **admin-stageb gains `headroom-bytes` 268435456**, olympus's value, so the worker
  passes `--headroom-bytes` to the SPU, the path stage B never ran.
- **`unit-properties` drops `CUBLAS_WORKSPACE_CONFIG`**, and UMask stays, so
  python-spu's own setting is what the run relies on.
- **The serving run stands no state member, as stage B's did.** Admin stands the member
  only when `weaver-state` sits beside the worker (admin `main.rs:250-253`, its stack
  digests `:486-497`), and `/opt/weaver-stageb/bin` holds none. So weaver-state at
  dc3a0f7a, the typed-state work, is exercised only by step 4's replay, which runs the
  built one. A later run installing it beside the worker would need karl2's member
  account and the stack check widened to four. That is a #726 item, not tonight's.
- **Criterion 4 is measured this time.** The external listing supersedes stage B's
  attempt 3, whose follower was stopped and noted.

## Criteria

Stage B's six, then three more. Each is decided by the evidence named, from `run/`.

1. **The load answers idle**, and admin's stage B log names the SPU:
   `load.txt`, `admin-stageb-log-tail.txt`.
2. **The load event's `stack` names the SPU by the installed file's sha256**, beside
   the worker's and the gate's: `trace-judged.json`.
3. **One turn is answered**, with its `model.request` and `model.measurement` in the
   trace, and the weights hash be1a0490, stage B's: `turn.txt`, `trace-judged.json`.
4. **Only admitted code is mapped, read from outside.** The SPU is selected by
   `pgrep -u weaver-karl2 -f '^/opt/weaver/python-spu/bin/python3.14 '`, and exactly
   one process must match. Its executable file-backed mappings are listed from
   `/proc/<pid>/maps` while karl2 is loaded, and python-spu's own rule, `loaded_code.
   foreign` over the prefix, finds nothing foreign: `spu-pid.txt`, `maps-code.txt`,
   `maps-judged.json`.
5. **The card is empty after the unload**, and the unit is inactive:
   `nvidia-smi-after-unload.txt`.
6. **The diagnostic replay of the turn certifies.** `replay.py` exits 0 only for
   certified with a clean teardown: `replay-terminal.json`, `replay-driver.log`.
7. **The stack is dc3a0f7a's:** the load event's `stack` equals the installed
   zipapp 7e3e01b8 and the dc3a0f7a worker and gate, whose hashes are
   `build/binaries.sha256`: `trace-judged.json`, `installed.sha256`.
8. **The worker's argument vector carried `--headroom-bytes 268435456`.** It shows in
   the journal's `Started [systemd-run] ... worker ...` line and in the SPU's own command
   line: `worker-journal.txt`, `spu-cmdline.txt`.
9. **The unit's environment had no `CUBLAS_WORKSPACE_CONFIG`.** Neither the unit's
   `Environment` nor the environment the SPU started with carries it:
   `unit-environment.txt`, `spu-environ.txt`.

**Beside the criteria, nothing of karl's changes.** Three pairs are taken before the
install and after the replay, and each must diff empty. The capture time is in files of
its own:
- `karl-*.txt`: karl's unit state and runtime directory;
- `untouched-*.sha256`: `/etc/weaver/admin`, `/opt/weaver/bin`, `/opt/weaver/lib`,
  karl's declaration, and karl's trace by size and modification time;
- `admin-log-*.sha256`: admin's own log.

**The journal carries no violation, fault or refusal line.**

## How the script behaves

- It stops at the first failed step, logging which step and why in
  `run/steps.log`, and never retries.
- If karl2 is loaded when it stops, it unloads karl2 once, so the card is not held
  overnight. That is cleanup, not a retry.
- It installs the new binaries and zipapp with the old ones beside them
  (`<name>.b62812e`, `python-spu.pyz.850720e`), and backs up admin-stageb to
  `/etc/weaver/admin-stageb.bak-b62812e` before editing it. Both stay in place after,
  since karl2's SPU is fixed for life and this is an upgrade under the same key.
- It touches nothing of karl's, nothing under `/etc/weaver/admin`, `/opt/weaver/bin` or
  `/opt/weaver/lib`, and nothing of olympus's.
- Every deposit file is written as the operator's account.
- The replay runs as the operator's account under `unshare -Ur`, as stage B's did.

**Rehearsed before the run, without the card or root:**
- `weaver-analysis derive` at dc3a0f7a on stage B's recorded run;
- `replay.py --stand-only` with the dc3a0f7a binaries and zipapp;
- both embedded judges, on real inputs;
- `bash -n` on the script.
