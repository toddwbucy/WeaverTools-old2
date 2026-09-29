# How the HeroBench two-agent run was set up and run

As run on olympus on 2026-09-29 from the executor seat's shell, and recorded from it.
`<herobench>` is a checkout of the HeroBench fork at `32c1e0f`, `<repo>` a checkout of
this repository at `99494511`, and `<deposit>` is
`/bulk-store/weaver-testing/herobench-agents-2026-09-29` on olympus, the same path
under `/mnt/bulk-store/weaver-testing/` on the thinkpad. The provisioning of the box,
its accounts, its admin configuration and its declarations, was done by the operator's
approval through local scripts that are not in this repository, and is described here
in prose.

## The stack and the model

The stack was redeployed from `99494511` with `deploy/update-stack.sh --install`, and
the existing agents validated after it. The model is `Qwen/Qwen2.5-7B-Instruct` at
Hugging Face revision `a09a35458c702b33eeacc393d103063234e8bc28`, its safetensors on
the shared bulk store and linked under the installation's models directory, so both
SPUs read one directory. The file digests are in the deposit's box facts.

## python-spu

Installed as `python-spu/README.md` "Installing it on a box" gives it, then smoke-tested
on the second A6000, named by its UUID, with the report into the deposit:

```
cd <repo>/python-spu
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=<gpu-uuid> PYTHONPATH=src \
  /opt/weaver/python-spu/bin/python3.14 scripts/smoke.py <model-dir> --device cuda \
  --output <deposit>/pyra/smoke.json
```

## The agents

Two agents, `rusty` served by the Rust SPU on the first A6000 and `pyra` served by
python-spu on the second, each named to its SPU by the admin configuration's
`spu-implementations` and `agent-spu`, per `weaver-admin-Spec` section 9. Both declare
the same model, tunables and seed, the identity prefix in `code/identity.txt`, the loop
file `code/herobench_loop.py` as installed under the stack's loops directory, a sqlite
state store, and a state election of the message kinds' `role` and `content` and the
measurement's `perplexity`, `entropies` and `surprisals`. `deploy/create-agent.sh`
provisions a postgres store and refuses sqlite, so their accounts, territories and
declarations were made by hand following its steps, the territory under a directory the
state member's group can traverse rather than under the operator's home. The loop file
needs the pyworker, the compiled worker refusing a loop file, so the installation's
worker was the pyworker for the act and was restored after it.

Each agent's home holds `code/hb` with an `hb.conf` naming its environment server and
its character.

## The environment

Two arms of the fork's harness, one per agent, so the two games share the game table and
not their world state:

```
cd <herobench>/weaver/bench && ./herobench up --arms 2 --base-port 8030 --backend sqlite --no-install
```

## A run

To rerun, with the agent provisioned and its arm up, from the HeroBench checkout so the
benchmark's own interpreter and shim are used. The driver runs as the operator with the
agent's group, which the gate's world socket admits, and the operator's groups are read
fresh because the groups were joined during the act:

```
cd <herobench>
sudo setpriv --reuid=<operator> --regid=<operator> --init-groups env HOME=<operator-home> \
  PATH=/usr/bin:/bin HEROBENCH_PORT=<port> PYTHONPATH=weaver/bench/shim:. .venv/bin/python \
  <repo>/experiments/trace-content/herobench-agents/code/run.py \
  --agent <agent> --port <port> --herobench <herobench> \
  --out <deposit>/<agent>/<label> --level 1 --tasks 1-3 --turn-cap <cap> --label <label>
```

It runs each task as its own run: it loads the agent, plays the task as one work item
through the agent's gate, grades it with the benchmark's own functions, and unloads.
The deposited runs were driven by its earlier form, three tasks in one run, which the
result note describes.

The counted pair ran as session `s-rusty-b` with loop v3, `--turn-cap 8`, labels `run1`
and `run2`, and the first pair as session `s-rusty` with loop v2. The probes ran as
their own sessions, one task each. Reading a trace or a store afterwards needs the state
member's group or root, the territory being that group's.
