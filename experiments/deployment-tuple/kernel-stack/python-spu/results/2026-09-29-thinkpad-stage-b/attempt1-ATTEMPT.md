# Stage B, attempt 1, 2026-09-29: the load failed, and the failure is a finding

The operator loaded karl2 through `/etc/weaver/admin-stageb` at about 10:39:11 CDT, on
the b62812e worker (84991e7a), weaver-admin (55529678) and weaver-gate (488babf3), with
python-spu.pyz (23a18eb2) as karl2's SPU. No turn ran.

## What happened, from `worker-journal.txt` (karl2's unit, captured live)

- 10:39:11.814: systemd started the worker with the zipapp as the SPU.
- 10:39:16.923: during python-spu's admission, triton compiled
  `triton/backends/nvidia/driver.c` with `/bin/gcc`, against the prefix's
  `include/python3.14/Python.h`. That is triton building its `cuda_utils` extension at
  runtime, into a temporary directory.
- 10:39:17.198: `collect2: fatal error: cannot find 'ld'`. The unit's environment carries
  no linker on its PATH.
- 10:39:17.327: python-spu's last word:
  `{"python_spu_fault": "CalledProcessError", "detail": "Command '['/bin/gcc', ...driver.c', '-O3', ...`
- 10:39:18.051: `worker: service ended below the exchange layer: Closed`, and the
  unit exited 1.

Admin answered `no_residency` and rolled back. Its stage B log,
`/var/log/weaver/admin-operations-stageb.ndjson` (root 0640), carries three rollback
lines, as the Planner read them. The GPU showed no compute process afterwards.

## Why it is a finding, not a fault of the unit

In every earlier CUDA run of python-spu, triton did the same compile silently, in a shell
where gcc and ld were on PATH:

- the CUDA import half of 2026-09-29;
- the enforced serves.

So the served SPU loaded a shared object built at runtime, by the system's compiler, into
a temporary directory. That object is in no lock and no tree digest. The CUDA import
half's additions were its symptom: triton, gluon, `torch._native`'s triton path, and
`cuda_utils`. python-spu-Spec section 8's rule, that nothing enters unless operations
require it, is broken by code compiled at load. The fix is #726's item "python-spu
compiles and loads no code at runtime".

## Nothing else changed

Taken before (10:38:02) and after (10:40:10). The `untouched` pair diffs empty. The karl
pair differs in its first line only, which is those two capture times, and its other
lines are equal:

- `karl-before.txt` and `karl-after.txt`: below the timestamp, `weaver-worker@karl.service`
  inactive, and no `/run/weaver-karl`, in both.
- `untouched-before.sha256` and `untouched-after.sha256`, 36 lines each: the sha256 of
  `/etc/weaver/admin/*`, `/opt/weaver/bin/*` and `/opt/weaver/lib/*`, karl's declaration
  a2a03d10, karl's trace by size and mtime (3,839,610,101 bytes), and admin's own log
  (102c7aba), whose line was appended by the operator under sudo.

## Also found

`sg` is not installed on this box, so the plan's turn line needs another route:
`sudo -u $OPERATOR -g weaver-karl2 python3 turn.py`, or a fresh login shell now that $OPERATOR is in
the group.
