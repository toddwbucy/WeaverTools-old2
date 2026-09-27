#!/usr/bin/env python3
# conforms: blackwell-probe-tuple-held-field-for-field
# conforms: blackwell-probe-elected-series-from-the-tuple
# conforms: blackwell-probe-falsifier-halts-after-unload
# conforms: blackwell-probe-one-command-one-seat-per-step
# conforms: blackwell-probe-operator-input-read-once
# conforms: blackwell-probe-refeed-completes-against-a-verified-source
# conforms: blackwell-probe-exactness-is-bitwise-over-elected-readings
# conforms: blackwell-probe-load-stands-on-the-interlock
"""One blocking TB arm. Privilege belongs exclusively to operator `next`.

Uses #516's pinned probe readers from a local, reviewed git-archive extraction.
It never calls the old driver's sudo/admin verbs or rewrites source records.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time

from tb_order import Order, Refused, atomic, check, elected, notice, same, sha
from tb_payload import m1_clear, m1_reading


def readers(plan):
    root = Path(plan['instrument'])
    for name, path in [('confirm_cells', root / 'cross-precision-repro/confirm_cells.py'),
                       ('weaver_probe', root / 'weaver-probe/weaver_probe.py')]:
        # One read: these bytes are hashed and these bytes are compiled. The
        # path names the code in tracebacks only; no cached pyc and no second
        # read of the file is ever executed.
        data = path.read_bytes()
        check('reader-approved', hashlib.sha256(data).hexdigest() == plan['files'][str(path)])
        module = importlib.util.module_from_spec(importlib.util.spec_from_file_location(name, path))
        sys.modules[name] = module
        exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def parse(data):
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def events(path):
    return parse(Path(path).read_bytes())


def receipt(receipts, step):
    """A recorded step's evidence, read once and parsed only after its bytes
    match the digest the coordinator recorded for it and handed back with the
    wait or the record that returned these receipts."""
    check('receipt-present', step in receipts)
    data = Path(receipts[step]['path']).read_bytes()
    check('receipt-digest', hashlib.sha256(data).hexdigest() == receipts[step]['sha256'])
    return json.loads(data)


def closed_prefix(data, run, kind):
    """The sink's bytes through the line recording `kind` for `run`, or None.
    A sink grows after its run closes, the unload appending its own event, so
    what a re-feed is later held to is this prefix and not the whole file."""
    offset = 0
    for line in data.splitlines(keepends=True):
        offset += len(line)
        if line.strip():
            event = json.loads(line)
            if event.get('kind') == kind and event.get('run') == run:
                return data[:offset]
    return None


def until_closed(path, kind, timeout=3600):
    """The sink's bytes from the one read the close was seen in (#693 thread
    1): the caller parses and cuts exactly the bytes the kind was found in,
    so a sink that changed after the close was seen is never what gets hashed.
    The sink is read whole only when its size has moved since the last poll,
    so an idle wait does not re-read a large trace every second."""
    deadline = time.monotonic() + timeout
    seen = None
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size != seen:
            data = path.read_bytes()
            seen = len(data)
            # Ignore only the currently incomplete final line while the writer
            # runs. A malformed complete line is a refusal, not dropped evidence.
            tail = data[-65536:]
            lines = tail.split(b'\n')[1:] if len(data) > 65536 else tail.split(b'\n')
            for line in lines[:-1]:
                if line and json.loads(line).get('kind') == kind:
                    return data
        time.sleep(1)
    raise Refused(f'{kind} not recorded inside bound')


# The record key extract_run fills for each per-token reading a tuple can
# elect. A true election with no key here raises rather than going unread, so
# an election added to the tuple cannot be forgotten by both functions below.
ELECTED_SERIES = {'surprisal': 'surprisals'}


def series(t):
    """The per-token float series a record must carry: entropies always, and
    each reading the tuple elects (#683 finding 23; weaver-spu-Spec 1803-1810:
    elected surprisals render, and disagreement is a defect)."""
    return ['entropies'] + [ELECTED_SERIES[k] for k, v in sorted(t.items()) if elected(v)]


# The kinds the pinned extract_run reads once per run (weaver_probe.py:174-200):
# it keeps the last event of each, so each must occur exactly once in a run's
# selected events. model.field is read per position and is held below. The
# measurement's count is each path's own guard (single-turn, source-measurement,
# replay-measurement), taken from measurements() here so the count lives once.
SINGULAR_KINDS = ('model.request', 'model.output')


def measurements(rows):
    return sum(e['kind'] == 'model.measurement' for e in rows)


def well_formed(rows):
    """One run's selected events, judged before anything is extracted from
    them, on the free, source and replay paths alike: exactly one of each
    singular kind, and one model.field event per output position with none
    beyond the measurement's output length. Each fault refuses by the kind and
    the fault, so a halt says which event the record was missing or had twice.
    Called after the path's measurement guard, which the field bound rests on."""
    kinds = collections.Counter(e['kind'] for e in rows)
    check('request-absent', kinds['model.request'] >= 1)
    check('request-duplicated', kinds['model.request'] <= 1)
    check('output-absent', kinds['model.output'] >= 1)
    check('output-duplicated', kinds['model.output'] <= 1)
    positions = [e['payload']['position'] for e in rows if e['kind'] == 'model.field']
    # Positions are told apart as JSON facts, so 3 and 3.0 are two, and the
    # bound below refuses the one that is not an int.
    check('field-duplicated', len(positions) == len({json.dumps(p) for p in positions}))
    measurement = next(e for e in rows if e['kind'] == 'model.measurement')
    check('field-beyond-output', all(type(p) is int and 0 <= p < len(measurement['payload']['output_tokens'])
                                     for p in positions))


def enough(t, rec):
    n = len(rec['output_tokens'])
    check('nonempty-measurement', n > 0 and len(rec['field']) == n and
          all(len(rec.get(k) or []) == n for k in series(t)))
    check('field-depth', all(len(value['ranked']) == t['field_depth'] for value in rec['field'].values()))


def float_bits(values):
    return b''.join(struct.pack('!d', v) for v in values)


def exact(t, source, replay):
    enough(t, source)
    enough(t, replay)
    # The stimulus is part of exactness: two records that read the same tokens
    # out of different input lengths did not run the same experiment.
    return (same(source['input_tokens'], replay['input_tokens']) and
            same(source['output_tokens'], replay['output_tokens']) and
            all(float_bits(source[k]) == float_bits(replay[k]) for k in series(t)) and
            same({str(k): v for k, v in source['field'].items()}, {str(k): v for k, v in replay['field'].items()}))


def source_record(plan, job, probe, receipts):
    if job.get('source_job'):
        return receipt(receipts, f'measure:{job["source_job"]}')
    path = Path(job['source_trace'])
    # One read, hashed and parsed: the record the report compares against is
    # cut from the bytes the manifest approved, the same selection the payload
    # makes for the replay it feeds.
    data = path.read_bytes()
    check('source-trace', hashlib.sha256(data).hexdigest() == plan['files'][str(path)])
    rows = [e for e in parse(data) if e['run'] == job['source_run']]
    check('source-measurement', measurements(rows) == 1)
    well_formed(rows)
    return dict(probe.extract_run(rows), trace=str(path), run=job['source_run'])


def interlock_at_close():
    """The interlock read again as the measurement closes: m1 standing now
    means it may have stood during the reading, so the reading is refused. The
    reading is returned to be recorded beside the result it vouches for."""
    reading = m1_reading()
    check('m1-unloaded-at-close', m1_clear(reading))
    return reading


def measure(plan, job, probe, receipts):
    """One job's measurement: its result file and, for a free run, its sink as
    it stood at the run's close, which the coordinator records in the measure
    receipt."""
    trace = Path(plan['install_root']) / 'sinks' / job['id'] / 'trace.ndjson'
    root = Path(plan['deposit'])
    dest = root / ('runs' if job['kind'] == 'free' else 'refeeds') / job['id']
    dest.mkdir(parents=True, exist_ok=False)
    sink = None
    if job['kind'] == 'free':
        close = probe.base.gate_turn({'gate_socket': '/run/weaver-bravo/gate.sock'}, probe.ESSAY_PROMPT, timeout=3600)
        check('gate-answer', close.get('kind') == 'answered' and bool(close.get('run')))
        prefix = closed_prefix(until_closed(trace, 'turn.closed'), close['run'], 'turn.closed')
        check('sink-closed', prefix is not None)
        sink = dict(path=str(trace), length=len(prefix), sha256=hashlib.sha256(prefix).hexdigest())
        mine = [e for e in parse(prefix) if e['run'] == close['run']]
        check('single-turn', measurements(mine) == 1)
        well_formed(mine)
        rec = probe.extract_run(mine)
        enough(plan['tuple'], rec)
        # The expected side is present at each guard, so an absent record
        # refuses here by name rather than as a KeyError or as two absences.
        check('seed-held', type(job.get('seed')) is int and same(rec.get('declared_seed'), job['seed']))
        check('weights-held', rec.get('weights_hash') == plan['tuple']['weights_sha256'])
        rec.update(name=job['id'], arm='TB0', seed=job['seed'], run=close['run'], trace=str(trace), verdict='RAN',
                   sink=sink, interlock=interlock_at_close())
        target = dest / 'run.json'
    else:
        rows = parse(until_closed(trace, 'replay.closed'))
        closes = [e for e in rows if e['kind'] == 'replay.closed']
        check('single-replay', len(closes) == 1)
        close = closes[0]
        outcome = close['payload']['outcome']
        # A diverged outcome carries its divergence, tagged on kind
        # (weaver-diagnostic event.rs ReplayOutcome at e69916a): one without it
        # would read below as no divergence at all.
        check('replay-completed', outcome['kind'] == 'certified' or
              (outcome['kind'] == 'diverged' and isinstance(outcome.get('divergence'), dict) and
               isinstance(outcome['divergence'].get('kind'), str)))
        mine = probe.measured_events(rows, close['run'])
        # Exactly one, as the free path requires under single-turn: extract_run
        # takes the last measurement's fields over a run's accumulated field
        # events, so two measurements make one ambiguous record.
        check('replay-measurement', mine is not None and measurements(mine) == 1)
        well_formed(mine)
        refed = probe.extract_run(mine)
        enough(plan['tuple'], refed)
        src = source_record(plan, job, probe, receipts)
        # A divergence is read as a device or kernel effect only when both sides
        # ran the tuple's weights, as the free-run path already requires.
        check('source-weights-held', src.get('weights_hash') == plan['tuple']['weights_sha256'])
        check('replay-weights-held', refed.get('weights_hash') == plan['tuple']['weights_sha256'])
        # The same for the seed: the replay's own model.request must report the
        # source run's seed, and that seed must be one the tuple holds.
        check('source-seed-held', any(same(src.get('declared_seed'), s) for s in plan['tuple']['seeds']))
        check('replay-seed-held', type(src.get('declared_seed')) is int and
              same(refed.get('declared_seed'), src['declared_seed']))
        reading = probe.reading_two(src, refed)
        # A replay that tokenized the prompt differently ran another stimulus:
        # the source and the replay must hold one input length, and a
        # token-path divergence inside that input is a stimulus change the
        # pinned comparator reports as an ordinary divergence
        # (weaver-harness replay.rs:385-416 at e69916a), never a device or
        # kernel reading. Both refuse before any reading is taken.
        check('input-held', type(src.get('input_tokens')) is int and same(src['input_tokens'], refed.get('input_tokens')))
        div = outcome.get('divergence') or {}
        check('divergence-in-input', div.get('kind') != 'token_path' or
              (type(div.get('position')) is int and div['position'] >= refed['input_tokens']))
        # Historical #516 stack coordinate: input-plus-output, not resident.
        ordinal = div['position'] - refed['input_tokens'] if div.get('kind') == 'token_path' else None
        free_readings = []
        for candidate in plan['arms'][0]['jobs']:
            if candidate['kind'] == 'free' and same(candidate['seed'], src.get('declared_seed')):
                # Every free run measured so far has its receipt; one not yet
                # measured has none, and is not read.
                if f'measure:{candidate["id"]}' in receipts:
                    free_readings.append(dict(target=candidate['id'], reading=probe.reading_one(
                        src, receipt(receipts, f'measure:{candidate["id"]}'))))
        rec = dict(free_readings=free_readings, name=job['id'], trace=str(trace), run=close['run'], verdict='RAN',
                   replay_outcome=outcome['kind'], replay_divergence=div,
                   replay_divergence_ordinal=ordinal, reading_two=reading,
                   exact=exact(plan['tuple'], src, refed), refed=refed, interlock=interlock_at_close())
        target = dest / 'refeed.json'
    atomic(target, rec)
    with (root / 'probe.jsonl').open('a') as out:
        out.write(json.dumps(dict(job=job, result=str(target), sha256=sha(target))) + '\n')
    return target, sink


def assess(plan, arm, probe, receipts):
    root = Path(plan['deposit'])
    results = [(job, receipt(receipts, f'measure:{job["id"]}')) for job in arm['jobs']]
    report = dict(arm=arm['name'], jobs=len(results))
    if arm['name'] == 'TB0':
        free = [(j, r) for j, r in results if j['kind'] == 'free']
        pairs = []
        for seed in plan['tuple']['seeds']:
            records = [r for j, r in free if j['seed'] == seed]
            check('pair-count', len(records) == 2)
            a, b = records
            pairs.append(dict(seed=seed, equal=exact(plan['tuple'], a, b) and same(a['emission'], b['emission']),
                              reading=probe.reading_one(a, b)))
        report['pairs'] = pairs
        report['own_refeeds'] = [dict(id=j['id'], exact=r['exact'], certified=r['replay_outcome'] == 'certified')
                                 for j, r in results if j['kind'] == 'refeed']
        # One run per distinct seed, in the tuple's seed order. The validator
        # constrains only the multiset of free seeds, so the job order carries
        # no repetition structure to rely on.
        seeds = plan['tuple']['seeds']
        first = {seed: next(r for j, r in free if j['seed'] == seed) for seed in seeds}
        report['changed_seeds'] = [dict(a=a, b=b, first_difference=probe.first_divergence(first[a]['output_tokens'], first[b]['output_tokens']))
                                   for i, a in enumerate(seeds) for b in seeds[i + 1:]]
        report['control_passed'] = all(p['equal'] for p in pairs) and all(r['exact'] and r['certified'] for r in report['own_refeeds'])
        report['changed_seed_prediction'] = all(p['first_difference'] is not None and p['first_difference'] < 24 for p in report['changed_seeds'])
    else:
        report['readings'] = [dict(id=j['id'], **{k: r[k] for k in ['exact', 'replay_outcome', 'reading_two', 'replay_divergence_ordinal', 'free_readings']}) for j, r in results]
        report['executable_identity'] = arm.get('executable_identity', False)
    target = root / f'{arm["name"]}-result.json'
    atomic(target, report)
    if arm['name'] == 'TB0':
        check('control-falsifier', report['control_passed'])
        check('changed-seed-prediction', report['changed_seed_prediction'])
    return target


def drive(order, arm_name):
    state = order.read()
    plan = order.approved(state)
    arm = next(a for a in plan['arms'] if a['name'] == arm_name)
    probe = readers(plan)
    root = Path(plan['deposit'])
    root.mkdir(exist_ok=True)
    start = root / f'{arm_name}-start.json'
    check('fresh-arm', not start.exists())
    atomic(start, dict(arm=arm_name, pid=os.getpid(), plan=order.approval['plan']['sha256']))
    # Every evidence read below is against the receipts the coordinator last
    # verified and handed back, never a path read alone (#683 thread 14).
    receipts = order.coding(f'start:{arm_name}', start)
    for job in arm['jobs']:
        notice('load:' + job['id'])
        receipts = order.wait('measure:' + job['id'])
        result, sink = measure(plan, job, probe, receipts)
        order.coding('measure:' + job['id'], result, sink=sink)
        notice('unload:' + job['id'])
        index = arm['jobs'].index(job)
        receipts = order.wait('settle:' + job['id'])
        # Stop immediately after the operator has unloaded a falsified control.
        rec = receipt(receipts, 'measure:' + job['id'])
        if arm_name == 'TB0' and job['kind'] == 'refeed':
            check('own-refeed-falsifier', rec['exact'] and rec['replay_outcome'] == 'certified')
        if arm_name == 'TB0' and job['kind'] == 'free':
            earlier = [j for j in arm['jobs'][:index] if j['kind'] == 'free' and j['seed'] == job['seed']]
            if earlier:
                old = receipt(receipts, 'measure:' + earlier[0]['id'])
                check('pair-falsifier', exact(plan['tuple'], old, rec) and same(old['emission'], rec['emission']))
        receipts = order.coding('settle:' + job['id'], result)
    result = assess(plan, arm, probe, receipts)
    order.coding('finish:' + arm_name, result)
    print(f'DONE: {arm_name}; results {result}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True)
    parser.add_argument('arm', choices=['TB0', 'TB-d', 'TB-k', 'report'])
    parser.add_argument('path', nargs='?', help='report only: the report file to record')
    args = parser.parse_args()
    order = Order(args.state)
    try:
        check('driver-not-root', os.geteuid() != 0)
        if args.arm == 'report':
            # Due only once every arm's finish: evidence is recorded and still
            # hash-intact; the review that follows is the review seat's edit.
            check('report-path', bool(args.path))
            order.coding('report', Path(args.path).resolve())
            print(f'DONE: report {args.path}; NEXT: review seat - review', flush=True)
        else:
            drive(order, args.arm)
    except (Exception, KeyboardInterrupt) as error:
        try:
            order.fail(error)
        except Exception as failure:
            print(f'Cannot persist refusal: {failure}', file=sys.stderr)
        print(f'REFUSED: {error}; NEXT: review seat - inspect state and arrange cleanup if loaded', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
