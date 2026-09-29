# Stage B, attempt 2: the operator's command sequence

The python-spu sources and zipapp come from `stageb-read` at 850720e, #741's merge. The
worker, weaver-admin and weaver-gate stay the b62812e builds in `/opt/weaver-stageb/bin`
(sha256 unchanged: 84991e7a, 55529678, 488babf3). `/etc/weaver/admin-stageb`, karl2 and
the model copy are unchanged. Between b62812e and 850720e, nothing changed in
`crates/weaver-types`, `crates/weaver-admin` or python-spu's `wire.py`. The one other
merge, #740, touched weaver-state only.

## (a) python-spu, recreated: main's README block, verbatim

Run from python-spu/ of the worktree at 850720e. Stop at the first line that fails. In
particular, `installed_set.py` must print nothing and exit 0.

```sh
cd $WT/python-spu
systemctl is-active weaver-worker@karl2.service    # must not read active
T=cpython-3.14.7+20260924-x86_64-unknown-linux-gnu-install_only.tar.gz
curl -fLO https://github.com/astral-sh/python-build-standalone/releases/download/20260924/$T
echo "5539eaf1de20bd9b5f43ea11c3c1f84cbac74fe927ac050318a9210c022618cb  $T" | sha256sum -c
sudo rm -rf /opt/weaver/python-spu
sudo mkdir -p /opt/weaver/python-spu
sudo tar -xzf $T -C /opt/weaver/python-spu --strip-components=1
sudo /opt/weaver/python-spu/bin/python3.14 -m pip install --require-hashes --no-deps \
    --only-binary=:all: -r requirements.lock
/opt/weaver/python-spu/bin/python3.14 -I -B scripts/installed_set.py requirements.lock
sudo /opt/weaver/python-spu/bin/python3.14 scripts/build_zipapp.py \
    --output /opt/weaver/python-spu/python-spu.pyz
python3 scripts/tree_digest.py /opt/weaver/python-spu
rm $T
```

The first and last lines are outside the README block: the unit check before the prefix
goes, and the tarball's removal after. Record the digest line. The executor records
`sha256sum /opt/weaver/python-spu/python-spu.pyz requirements.lock` into the deposit.

## (b) the load, one turn, the unload

```sh
D=/mnt/bulk-store/weaver-testing/stage-b-thinkpad-2026-09-29-b62812e/attempt2-2026-09-29
sudo sha256sum /var/log/weaver/admin-operations.ndjson > $D/admin-log-before.sha256
sudo systemctl reset-failed weaver-worker@karl2.service
systemctl is-active weaver-worker@karl2.service    # must read inactive
S=$(date '+%F %T')
sudo env WEAVER_ADMIN_CONFIG=/etc/weaver/admin-stageb /opt/weaver-stageb/bin/weaver-admin load karl2
sudo env WEAVER_ADMIN_CONFIG=/etc/weaver/admin-stageb /opt/weaver-stageb/bin/weaver-admin show karl2
sudo -u $OPERATOR -g weaver-karl2 python3 code/turn.py | tee $D/turn.txt
P=$(pgrep -u weaver-karl2 -f python-spu.pyz); sudo awk '$2 ~ /x/ && $6 ~ /^\// {print $6}' /proc/$P/maps | sort -u | tee $D/maps-code.txt
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv | tee $D/nvidia-smi-loaded.txt
sudo env WEAVER_ADMIN_CONFIG=/etc/weaver/admin-stageb /opt/weaver-stageb/bin/weaver-admin unload karl2
nvidia-smi --query-compute-apps=pid --format=csv,noheader | tee $D/nvidia-smi-after.txt
sudo tail -n 5 /var/log/weaver/admin-operations-stageb.ndjson | tee $D/admin-stageb-log-tail.txt
sudo sha256sum /var/log/weaver/admin-operations.ndjson > $D/admin-log-after.sha256
```

**Why `reset-failed`:** attempt1 left `weaver-worker@karl2` failed. Per weaver-admin-Spec,
a failed prior unit's name "refuses every later start under it until the manager is
asked to reap it", so without that line the load answers `PriorUnitUnreaped`.

**The maps line** lists every executable file-backed mapping, not only the
libcu/libnv/libtorch grep of the plan. Pass criterion 4 then reads: every object is under
`/opt/weaver/python-spu` or in python-spu's admitted system list, which is glibc's
family, libgcc_s, libstdc++, libz, `/usr/lib/libcuda.so.*` and `/usr/lib/libnvidia-*`,
and none is from `/opt/cuda/lib64` or `/tmp`. The card run of 2026-09-29 mapped libcuda
and libnvidia-ml from `/usr/lib`, which the plan's earlier criterion would have read as a
failure.

A further pass condition: the journal carries no `loaded_code_violation`, no
`import_violation` and no `python_spu_fault`.

## After (b), the executor

The journal follower stops. The executor lines of the after-capture go into
`karl-after.txt` and `untouched-after.sha256`. Admin's own log has its own pair,
`admin-log-before.sha256` and `admin-log-after.sha256`, both written by the operator's
sudo lines, so neither file mixes two writers' order. Each of the three pairs must
`diff` empty. The load event's `stack` is extracted from karl2's
trace, and the zipapp's sha256 is checked against it.
