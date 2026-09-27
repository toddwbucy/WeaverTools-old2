#!/usr/bin/env python3
# conforms: blackwell-probe-approval-gates-every-step
"""Stage the TB coordinator locally, held and unapproved. No host/remote changes."""
import argparse
import json
from pathlib import Path
import shutil
from tb_order import atomic, sha

SEEDS = [451234785645, 1156316220, 7, 1000003, 123456789, 987654321, 2718281828, 3141592653]


def template(deposit, operator, uid):
    deposit = Path(deposit).resolve()
    jobs = [dict(id=f'B1-s{seed}-n{n}', kind='free', seed=seed, stack='B1') for n in [1, 2] for seed in SEEDS]
    refeeds = [dict(id='own-' + j['id'], kind='refeed', source_job=j['id'], stack='B1') for j in jobs]
    kernel = [dict(id='kernel-' + j['id'], kind='refeed', source_job=j['id'], stack='B2') for j in jobs]
    instrument = deposit / 'instrument/experiments'
    files = {}
    for directory in [deposit / 'stacks', instrument]:
        if directory.exists():
            for path in sorted(directory.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:
                    files[str(path)] = sha(path)
    model = deposit / 'models/Qwen3-8B-Q8_0.gguf'
    if model.exists():
        files[str(model)] = sha(model)
    return dict(version=1, agent='bravo', install_root='/var/lib/weaver-tb', deposit=str(deposit),
                operator=operator, operator_uid=uid, instrument=str(instrument), model_source=str(model),
                stacks={s: str(deposit / 'stacks' / s) for s in ['B1', 'B2']}, files=files,
                # Each ruling is filled in at re-staging (679.4). The CUDA
                # provenance ruling of 2026-09-26 (679.3) is the one the plan
                # will carry: https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-5851860887
                rulings=dict(hold_lifted=None, cuda_provenance=None, control_count=None),
                tuple=dict(artifact='/opt/weaver/models/Qwen3-8B-Q8_0.gguf',
                           weights_sha256='0cfbf745760f07a76ddeb358dd025a27f2e11d1ca9c9a4169a373d52990fe86e',
                           devices=[0], context_capacity=12288, max_tokens=8192, field_depth=200,
                           surprisal=True, residual=False, identity='You are Karl, a careful writer. Answer plainly and at length when asked, and do not stop early.',
                           seeds=SEEDS, runs_per_seed=2, driver='615.71.09'),
                arms=[dict(name='TB0', jobs=jobs + refeeds), dict(name='TB-d', jobs=[]),
                      dict(name='TB-k', executable_identity=False, jobs=kernel)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoffs', required=True, type=Path)
    parser.add_argument('--deposit', required=True, type=Path)
    parser.add_argument('--operator', default='todd')
    parser.add_argument('--uid', type=int, default=1000)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    target = args.handoffs.resolve() / 'tb'
    evidence = args.handoffs.resolve() / 'tb-evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    state = evidence / 'tb-state.json'
    if state.exists() or target.exists():
        parser.error('staging already exists; inspect it instead of replacing approval or progress')
    target.mkdir()
    for path in source.iterdir():
        if path.suffix in ['.py', '.sh', '.md']:
            shutil.copy2(path, target / path.name)
    plan = evidence / 'tb-plan.json'
    atomic(plan, template(args.deposit, args.operator, args.uid))
    # Held by construction: no approval is recorded, and the review, the hold
    # and the approved digests live in the root-owned approval record that
    # `tb-operator.sh approve` writes, never in this state file (679.5).
    atomic(state, dict(version=1, cursor=0, done={}, driver=None, halt=None, refusals=[], approval=None))
    atomic(evidence / 'staged-files.json', {str(p): sha(p) for p in sorted(target.iterdir()) if p.is_file()})
    print(f'Staged held preparation at {target}, plan {plan}; WAITING ON: review seat - rulings, then the '
          'review record, then the operator runs approve')


if __name__ == '__main__':
    main()
