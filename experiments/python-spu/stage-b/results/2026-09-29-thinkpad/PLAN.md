# Stage B plan: one real turn through python-spu on thinkpad, at main b62812e

*The plan as the Planner reviewed it before attempt 1, kept as the record of the criteria
registered before either run. Paths are written as the README beside it names them.
Attempt 1 ran sections 2 to 5, the operator adding `--only-binary=:all:` to section
3's pip line, and stopped at the load. Attempt 2 replaced section 3's python-spu
block and extended section 5, per `attempt2-COMMANDS.md`, and its pass criterion 4 there
supersedes the one in section 5.*

Read-only preparation. Nothing below has been run. Every path and fact was read on
thinkpad on 2026-09-29 against a clean worktree at b62812e
(`$WT`, detached, read-only).

## 0. The decision this plan rests on: a second admin configuration, not a stack update

The installed stack is 39fe573. It predates #734, the per-agent SPU (`spu-implementations`
and `agent-spu`), and #731, the TOML declarations. Stage B needs both. But
`deploy/update-stack.sh --install` at b62812e would touch karl in three ways:

1. It refuses unless every allow-listed agent has a `<agent>.toml`
   (`update-stack.sh:92-107`). The allow-list holds `karl` and `m1`, and both have YAML
   only. So a karl.toml would have to be written.
2. It replaces `/opt/weaver/bin`, karl's binaries.
3. Its verify step loads and unloads every allow-listed agent (`update-stack.sh:607-642`).
   That writes load events into karl's live trace, `$AGENTS/karl/trace.ndjson`.

**Instead, stage B runs under its own admin configuration directory,
`/etc/weaver/admin-stageb`,** selected with `WEAVER_ADMIN_CONFIG`. That's the variable
admin already reads, and the matrix and W4a both passed it. It gets its own binaries
built at b62812e in `/opt/weaver-stageb/bin`, its own allow-list (karl2 alone), its own
log, and its own unit-properties. The following stay byte-for-byte untouched: karl's
config, its declaration, its trace, `/etc/weaver/admin`, `/opt/weaver/bin` and
`/opt/weaver/lib`. Units and runtime directories are keyed by agent name
(`weaver-worker@karl2`, `/run/weaver-karl2`), so nothing collides.

## 1. Executor steps, no sudo, before the operator

- **E1.** Build at b62812e from the clean worktree, into its own target, at nice 19 -j 4:

      cargo build --release --locked -p weaver-harness --bin worker -p weaver-admin \
        -p weaver-gate -p weaver-analysis -p weaver-state

  `weaver-analysis` and `weaver-state` (sqlite, its default feature) are for the replay
  only (section 6). No CUDA feature is needed, since
  karl2's SPU is python-spu and the Rust SPU is not built.
- **E2.** Adapt W4a's replay driver, `handoffs/w4a-evidence/replay.py`, into scratch for
  section 6. Its derived-declaration reader becomes `tomllib`.
- **E3.** Record the sha256 of every built binary for the box facts.

## 2. Operator steps: karl2's territory (sudo, verbatim)

karl declares `state-store.engine = none`, so `deploy/create-agent.sh` cannot make karl2:
it provisions postgres only, and refuses `none` by name. karl2 is made by hand, the way
karl stands today. karl's shape, as read:

- the account is `weaver-karl`, home `/var/lib/weaver/agents/karl`, mode 0700, in `render`
  and `video`;
- the trace directory is `root:$OPERATOR 2750`;
- `$OPERATOR` is in group `weaver-karl`, which is how the operator's uid reaches `/run/weaver-karl/gate.sock`.
  The unit's runtime directory is 0750, owned by the agent's group.

```sh
sudo useradd --system --user-group --home-dir /var/lib/weaver/agents/karl2 --create-home \
    --shell /usr/sbin/nologin --groups render,video weaver-karl2
sudo chmod 0700 /var/lib/weaver/agents/karl2
sudo usermod -aG weaver-karl2 $OPERATOR
sudo install -d -o root -g $OPERATOR -m 2750 $AGENTS/karl2
```

The group change reaches the operator's shell only in a new login. The turn in section 5
runs under `sudo -u $OPERATOR -g weaver-karl2` instead of asking for one, `sg` not being installed on this box.

The declaration is written as $OPERATOR, no sudo, to `$AGENTS/karl2.toml`.
It is karl's a2a03d10, converted to TOML because admin at b62812e reads
`<agent>.toml` (`main.rs:518`). Three things differ:

- **the session:** `s-karl2-1`. This is not required by admin. It keeps a later joined
  reading of two traces unambiguous;
- **the trace path;**
- **the artifact:** python-spu admits a safetensors directory and refuses a GGUF file as
  `artifact_unresolvable`.

The identity text is byte-equal to karl's, checked. The TOML parses with `tomllib`. Admin's
`validate` in section 4 is the authoritative check. The draft was the executor's, outside
this tree.

## 3. Operator steps: python-spu, the model, the stack (sudo, verbatim)

**The Python SPU**, exactly the README block at b62812e, run from `python-spu/` of the
clean worktree:

```sh
cd $WT/python-spu
T=cpython-3.14.7+20260924-x86_64-unknown-linux-gnu-install_only.tar.gz
curl -fLO https://github.com/astral-sh/python-build-standalone/releases/download/20260924/$T
echo "5539eaf1de20bd9b5f43ea11c3c1f84cbac74fe927ac050318a9210c022618cb  $T" | sha256sum -c
sudo mkdir -p /opt/weaver/python-spu
sudo tar -xzf $T -C /opt/weaver/python-spu --strip-components=1
sudo /opt/weaver/python-spu/bin/python3.14 -m pip install --require-hashes --no-deps \
    -r requirements.lock
sudo /opt/weaver/python-spu/bin/python3.14 scripts/build_zipapp.py \
    --output /opt/weaver/python-spu/python-spu.pyz
python3 scripts/tree_digest.py /opt/weaver/python-spu
rm $T
```

The whole block ran clean against a scratch prefix on 2026-09-29, with sudo dropped (#735).
Record the digest line, `sha256sum /opt/weaver/python-spu/python-spu.pyz` and
`sha256sum requirements.lock`.

**The artifact.** An agent uid cannot read the operator's home, so it cannot read
`$MODELS`. The copy goes under `/opt/weaver/models`.
*(The first sentence is reduced for publication. The deposit's `PLAN.md` keeps it whole.)*
The source's 8 entries are all regular files, and there are no symlinks, which answers
the #729 cross-seat item for this artifact. `model.safetensors` is BF16, 988,097,824 bytes.

```sh
sudo install -d -o root -g root -m 0755 /opt/weaver/models/qwen2.5-0.5b-instruct-safetensors
sudo install -o root -g root -m 0644 $MODELS/Qwen--Qwen2.5-0.5B-Instruct/* \
    /opt/weaver/models/qwen2.5-0.5b-instruct-safetensors/
(cd /opt/weaver/models/qwen2.5-0.5b-instruct-safetensors && sha256sum *)
```

The last line must equal the source's, read 2026-09-29:

```
18e18afcaccafade98daf13a54092927904649e1dd4eba8299ab717d5d94ff45  config.json
e558847a8b4402616f1273797b015104dc266fe4b520056fca88823ba8f8ebe6  generation_config.json
832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e  LICENSE
599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3  merges.txt
fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe  model.safetensors
5b5d4f65d0acd3b2d56a35b56d374a36cbc1c8fa5cf3b3febbbfabf22f359583  tokenizer_config.json
c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539  tokenizer.json
ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910  vocab.json
```

**The b62812e binaries**, from E1:

```sh
B=$WT/target/release
sudo install -d -o root -g root -m 0755 /opt/weaver-stageb/bin
sudo install -o root -g root -m 0755 $B/worker $B/weaver-admin $B/weaver-gate /opt/weaver-stageb/bin/
sha256sum /opt/weaver-stageb/bin/*
```

## 4. Operator steps: the stage B admin configuration (sudo tee, verbatim)

```sh
sudo install -d -o root -g root -m 0755 /etc/weaver/admin-stageb
echo karl2 | sudo tee /etc/weaver/admin-stageb/allow-list
echo /opt/weaver-stageb/bin/worker | sudo tee /etc/weaver/admin-stageb/worker-binary
echo /opt/weaver-stageb/bin/weaver-gate | sudo tee /etc/weaver/admin-stageb/gate-binary
echo /opt/weaver/bin/weaver-spu | sudo tee /etc/weaver/admin-stageb/spu-binary
echo /run | sudo tee /etc/weaver/admin-stageb/coordination-root
echo /var/log/weaver/admin-operations-stageb.ndjson | sudo tee /etc/weaver/admin-stageb/log-path
echo $AGENTS | sudo tee /etc/weaver/admin-stageb/agent-config-directory
echo /usr/bin/systemd-run | sudo tee /etc/weaver/admin-stageb/run-tool
echo /usr/bin/systemctl | sudo tee /etc/weaver/admin-stageb/control-tool
echo 'python /opt/weaver/python-spu/python-spu.pyz' | sudo tee /etc/weaver/admin-stageb/spu-implementations
echo 'karl2 python' | sudo tee /etc/weaver/admin-stageb/agent-spu
printf 'UMask=0000\nEnvironment=CUBLAS_WORKSPACE_CONFIG=:4096:8\n' \
    | sudo tee /etc/weaver/admin-stageb/unit-properties
```

Three choices in that file:

- **`spu-binary`** is required by admin's loader (`read`, not `optional`), so it names the
  installed Rust SPU. karl2 never launches it, because `agent-spu` maps karl2 to
  `python`. The file names are pairwise distinct: `worker`, `weaver-state`,
  `weaver-gate`, and the SPUs `weaver-spu` and `python-spu.pyz`.
- **`unit-properties` differs from karl's on purpose,** in two places:
  - `CUBLAS_WORKSPACE_CONFIG` is set. The engine calls
    `torch.use_deterministic_algorithms(True)` (`engine.py:56`), and torch then raises at
    the first cuBLAS call on CUDA without it. Every CUDA run so far set it by hand.
  - `LD_LIBRARY_PATH=/opt/weaver/lib:/opt/cuda/lib64` is left out. Only python-spu runs
    here, and neither the worker nor the gate needs it. `/opt/cuda/lib64` holds CUDA
    13.4's `libcublas.so.13` (13.8.0.4). Torch maps its own cuBLAS, cudart and cuDNN at
    import even with that path set (checked on CPU, 2026-09-29), but a library torch
    opens lazily later could resolve there.
- **No `headroom-bytes`.** Where it is set, the worker passes `--headroom-bytes N` to the
  SPU (`lifecycle.rs:253`), and python-spu's argparse exits 2 on an argument it does not
  know. The live config has none, and this one must not either. This is a contract gap
  for #726: the SPU argument surface is not in python-spu.

Then validate:

```sh
sudo env WEAVER_ADMIN_CONFIG=/etc/weaver/admin-stageb /opt/weaver-stageb/bin/weaver-admin validate karl2
```

## 5. The test (a few minutes of GPU, the operator's say-so)

**Before the load, evidence that nothing else changes**, written into the deposit.
Executor, read-only, except the one sudo line, which is the operator's, since
`admin-operations.ndjson` is `root:root 0640`:

```sh
D=/mnt/bulk-store/weaver-testing/stage-b-thinkpad-2026-09-29-b62812e
systemctl is-active weaver-worker@karl.service > $D/karl-before.txt 2>&1; ls /run/weaver-karl >> $D/karl-before.txt 2>&1
sha256sum /etc/weaver/admin/* /opt/weaver/bin/* /opt/weaver/lib/* > $D/untouched-before.sha256
sha256sum $AGENTS/karl.yaml >> $D/untouched-before.sha256
stat -c '%s %Y %n' $AGENTS/karl/trace.ndjson >> $D/untouched-before.sha256
sudo sha256sum /var/log/weaver/admin-operations.ndjson >> $D/untouched-before.sha256
```

`karl-before.txt` must read `inactive` and no runtime directory. karl's trace is recorded
by size and mtime rather than hashed, at 3.8 GB. After the unload below, the same lines
run into `untouched-after.sha256` and `karl-after.txt`, and `diff` of each pair must be
empty.

Start a capture first, from the executor's shell, read-only:

```sh
journalctl -u weaver-worker@karl2 -f -o short-iso-precise > <deposit>/worker-journal.txt &
```

Then the operator:

```sh
S=$(date '+%F %T')
sudo env WEAVER_ADMIN_CONFIG=/etc/weaver/admin-stageb /opt/weaver-stageb/bin/weaver-admin load karl2
sudo env WEAVER_ADMIN_CONFIG=/etc/weaver/admin-stageb /opt/weaver-stageb/bin/weaver-admin show karl2
sudo -u $OPERATOR -g weaver-karl2 python3 code/turn.py
P=$(pgrep -u weaver-karl2 -f python-spu.pyz); sudo grep -E 'libcu|libnv|libtorch' /proc/$P/maps | awk '{print $6}' | sort -u
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
sudo env WEAVER_ADMIN_CONFIG=/etc/weaver/admin-stageb /opt/weaver-stageb/bin/weaver-admin unload karl2
nvidia-smi --query-compute-apps=pid --format=csv,noheader
sudo tail -n 5 /var/log/weaver/admin-operations-stageb.ndjson
```

Then the "after" half of the evidence above, and the two `diff`s.

**Pass criteria**, each read from evidence, not from the console:

1. `load` answers loaded, and admin's log line for the load names
   `spu: "python /opt/weaver/python-spu/python-spu.pyz"`.
2. **The load event's `stack`**, the last `"kind":"load"` line in
   `$AGENTS/karl2/trace.ndjson`, which is readable by $OPERATOR, names
   `python-spu.pyz` with the sha256 `sha256sum` gave in section 3, beside `worker` and
   `weaver-gate`. This is #734's provenance on its first real use.
3. The gate answers one turn. The trace carries that turn's `model.request` and
   `model.measurement`, with the `weights_hash` python-spu computed. That is blake3 over
   the directory, not the GGUF's.
4. The SPU's `/proc/<pid>/maps` shows only the prefix's `nvidia/` libraries, none from
   `/opt/cuda/lib64`.
5. After unload, `nvidia-smi` lists no compute process, and `weaver-worker@karl2` is
   inactive.

## 6. The diagnostic replay (executor, no sudo, a minute of GPU)

Admin's diagnostic route needs a diagnostic agent with a postgres state member and its
preload door, dialed as root. That route has not run on this box. **W4a's route has**
(`handoffs/w4a-evidence/replay.py`): the worker and a sqlite `weaver-state` driven
directly, in an `unshare -Ur` namespace mapped to $OPERATOR, on throwaway sockets, with no
sudo. Its outcome on 2026-09-24 was `diverged` at position 27196, on a multi-turn m1
record under the Rust SPU.

For stage B:

- the same driver, with the b62812e worker, `weaver-state` (sqlite) and `weaver-analysis`
  from E1, and `/opt/weaver/python-spu/python-spu.pyz` as the SPU;
- `CUBLAS_WORKSPACE_CONFIG=:4096:8` in its environment;
- the declaration from:

      weaver-analysis derive $AGENTS/karl2/trace.ndjson --as s-karl2-1-replay \
        --devices 0 --sink <deposit>/replay-trace.ndjson --surprisal --out <deposit>/derived.toml

- then `weaver-analysis preload <trace> <preload.sock> --diagnostic --as s-karl2-1-replay`
  against the member's door.

python-spu serves the re-feed that the replay's `refeed-permission` asks for
(`session.py:50-55`).

**The driver** is `code/replay.py`, W4a's
adapted. The commands, executor, no sudo, after the unload in section 5:

```sh
B=$WT/target/release
D=/mnt/bulk-store/weaver-testing/stage-b-thinkpad-2026-09-29-b62812e
$B/weaver-analysis derive $AGENTS/karl2/trace.ndjson --as s-karl2-1-replay \
    --devices 0 --sink $D/replay-trace.ndjson --surprisal --out $D/derived.toml
unshare -Ur python3 code/replay.py \
    $AGENTS/karl2/trace.ndjson $D/derived.toml $D \
    --bin $B --spu /opt/weaver/python-spu/python-spu.pyz
nvidia-smi --query-compute-apps=pid --format=csv,noheader
```

It writes `replay-worker.log`, `replay-state.log`, `replay-preload.log`,
`replay-coordination.ndjson`, `replay-terminal.json` and `replay-cleanup.json` beside
the diagnostic trace. Checked 2026-09-29 with `--stand-only`, which stops before the
enter and so uses no SPU and no GPU. In `unshare -Ur`, the b62812e worker bound
coordination, the member took descriptor 3 and waited for its opener, and both tore
down, with the temporary directory removed. The member stands its preload door only
once the enter's opener arrives, so the door itself is first exercised by the real
run.

**Pass:** the diagnostic trace's `replay.closed` reads `{"kind": "certified"}`. One turn is
the right scope. The replay re-feeds the prompt as one forward, as the source did, so a
one-turn run's token path should reproduce. A multi-turn run re-feeds earlier turns'
outputs as a batch, where the source decoded them one token at a time. That is the
arrangement question of #515, and not stage B's claim.

## 7. What could go wrong, and where it shows

| Risk | Where it shows | Guard |
| --- | --- | --- |
| cuBLAS raises under deterministic algorithms | SPU stderr, teed into the worker's journal (`spawn.rs` `LastWord` copies every line and keeps the last JSON line as the death's `last_word`) | `CUBLAS_WORKSPACE_CONFIG` in the stage B `unit-properties` |
| `--headroom-bytes` passed to python-spu, argparse exits 2 | the load fails, and the journal has argparse's usage line | no `headroom-bytes` in the stage B config |
| The import set faults under the unit's environment (exit 3) | the last word is `{"import_set_violation": ..., "undeclared": [...]}` | the halves came from the same pins, but in my shell's environment, not a unit's. The list names what to regenerate |
| A CUDA library resolves from `/opt/cuda/lib64` | the SPU's `/proc/<pid>/maps` | `LD_LIBRARY_PATH` left out of the stage B `unit-properties` |
| The inherited descriptor count is refused | `descriptors_unusable` in admin's answer and the journal | the worker hands 3, 4 and the stderr pipe, which is the shape `LocalProcess` tests |
| The agent cannot read the zipapp, the prefix or the model | `artifact_unresolvable` or an exec failure in the journal | everything is under `/opt/weaver`, root-owned, 0755 and 0644. Read `namei -l` on each if it fails |
| The operator cannot reach `gate.sock` | `PermissionError` from the turn | `usermod -aG weaver-karl2 $OPERATOR`, and `sg` for the one command |
| The load outlasts admin's wait | admin's answer and the journal | admission loads FP32 (python-spu-Spec 2.1's known gap), about 2 GB on the card, and blake3 over 988 MB |
| Wire drift between python-spu's oracle pin and b62812e | a refused exchange naming a field | checked: weaver-types' wire is unchanged from `f22bf08` to `b62812e`, only `config.rs` moved (#731) |

## 8. Evidence and deposit

**Deposit:** `/mnt/bulk-store/weaver-testing/stage-b-thinkpad-2026-09-29-b62812e/`. It holds:

- box facts: every sha256 above; the tree digest; `requirements.lock`'s sha256; copies of
  `/etc/weaver/admin-stageb/*`; the driver and CUDA facts;
- `worker-journal.txt`;
- admin's log lines for the load and the unload;
- the load event, extracted;
- the turn's answer;
- the maps listing;
- the `nvidia-smi` readings;
- the derived declaration, the diagnostic trace and the replay driver's log.

**Result note:** in the section-1 shape, in the deposit, and copied to the repository
with the scripts.

## 9. Afterwards

- **Leave standing:** `/etc/weaver/admin-stageb`, `/opt/weaver-stageb`, karl2, the
  python-spu prefix and the model copy. Stage C, the comparison, uses them.
- **After stage C, reverse the change to the operator's account:**
  `sudo gpasswd -d $OPERATOR weaver-karl2`. `usermod -aG` is a lasting change, and
  it is recorded here so it is not left behind.
- **Nothing else changed:** karl, `/etc/weaver/admin`, `/opt/weaver/bin` and
  `/opt/weaver/lib`, run5's deposits and olympus.
- **Found for #726:** python-spu does not take `--headroom-bytes`. And the `LD_LIBRARY_PATH`
  in karl's `unit-properties` is not python-spu-safe, if the two ever share one admin
  configuration.
