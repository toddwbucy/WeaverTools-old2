#!/usr/bin/env python3
# conforms: blackwell-probe-tuple-held-field-for-field
# conforms: blackwell-probe-elected-series-from-the-tuple
# conforms: blackwell-probe-schedule-validated-whole
# conforms: blackwell-probe-falsifier-halts-after-unload
# conforms: blackwell-probe-one-command-one-seat-per-step
# conforms: blackwell-probe-approval-gates-every-step
# conforms: blackwell-probe-approval-in-root-custody
# conforms: blackwell-probe-wait-verifies-when-the-state-moves
# conforms: blackwell-probe-halt-is-evidence
# conforms: blackwell-probe-root-runs-no-operator-bytes
# conforms: blackwell-probe-operator-input-read-once
# conforms: blackwell-probe-served-tree-locked-and-verified
# conforms: blackwell-probe-model-in-custody-on-both-paths
# conforms: blackwell-probe-installation-refuses-to-adopt
# conforms: blackwell-probe-load-stands-on-the-interlock
# conforms: blackwell-probe-inventory-covers-every-served-file
# conforms: blackwell-probe-comparison-takes-b1-then-b2
# conforms: blackwell-probe-identity-bound-to-approved-stacks
# conforms: blackwell-probe-refeed-completes-against-a-verified-source
# conforms: blackwell-probe-exactness-is-bitwise-over-elected-readings
"""Host-only tests. All host mutations/admin/GPU calls use stub boundaries."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import golden
import prepare
import sections
import tb_driver as driver
import tb_order as order
import tb_payload as payload
import tb_root as rootprog


def event(line, **fields):
    """A real event from golden.py with named fields replaced."""
    e = json.loads(line)
    e.update(fields)
    return e


def run_events(run, *extra, **fields):
    """One run's singular events as a real run carries them: request, output,
    measurement, each once, plus extra; fields override the envelope."""
    return [event(golden.MODEL_REQUEST, run=run, **fields), event(golden.MODEL_OUTPUT, run=run, **fields),
            event(golden.MODEL_MEASUREMENT, run=run, **fields), *extra]


def trace(run, *extra, **fields):
    return ndjson(*run_events(run, *extra, **fields))


def ndjson(*events):
    """Events as the recorder writes them: compact JSON, one per line."""
    return ''.join(json.dumps(e, separators=(',', ':')) + '\n' for e in events)


def closed_bytes(rows):
    """The sink's bytes as until_closed now returns them, read once."""
    return ndjson(*rows).encode()


def golden_reading(systemctl=None):
    """The interlock reading m1_reading takes from golden's real capture of
    this box's systemctl answer, no door and no m1 process: m1 absent."""
    with patch('tb_payload.subprocess.run',return_value=subprocess.CompletedProcess([],0,systemctl or golden.SYSTEMCTL_SHOW_M1,'')),\
         patch('tb_payload.door_state',return_value=False),patch('tb_payload.Path.iterdir',return_value=[]),\
         patch('tb_payload.pwd.getpwnam',side_effect=KeyError),patch('tb_payload.proc_hides_processes',return_value=False):
        return payload.m1_reading()


def ldd_output(root, cuda_dir):
    """golden's real ldd capture, with the three CUDA libraries resolved in
    cuda_dir, as they would be for an installed stack."""
    lines = []
    for line in golden.LDD_B1_LIBGGML_CUDA.replace('{DEPOSIT}', str(root)).splitlines():
        name = line.strip().split(' ')[0]
        if name.startswith(('libcudart.so', 'libcublas.so', 'libcublasLt.so')):
            line = line.split(' => ')[0] + f' => {cuda_dir}/{name} ' + line.rsplit(' ', 1)[1]
        lines.append(line)
    return '\n'.join(lines) + '\n'


def derived(artifact, sink, held=None, **values):
    """golden's real derive output naming artifact and sink. With held, a plan
    tuple, it carries that tuple's seed, identity, context capacity and token
    cap in the form derive renders them (compact JSON); values override one."""
    text = (golden.DERIVE_DECLARATION.replace(json.dumps(golden.DERIVE_ARTIFACT), json.dumps(str(artifact)))
            .replace('{SINK}', str(sink)))
    if held is None:
        return text
    fields = {'seed': held['seeds'][0], 'context-capacity': held['context_capacity'],
              'max-tokens-per-turn': held['max_tokens'],
              'identity': [{'role': 'system', 'content': [{'type': 'text', 'text': held['identity']}]}]}
    fields.update(values)
    lines = []
    for line in text.splitlines():
        key = line.strip().partition(':')[0]
        if key in fields:
            line = line[:line.index(key)] + key + ': ' + json.dumps(fields[key], separators=(',', ':'))
        lines.append(line)
    return '\n'.join(lines) + '\n'


@contextlib.contextmanager
def swapped_after_hashing(files):
    """Rewrite each file the moment its current bytes have been hashed, as an
    operator could between a check and a second read. Any code that reads a
    file again after checking it then consumes the rewritten bytes."""
    real=hashlib.sha256
    pending={p.read_bytes():(p,new) for p,new in files.items()}
    class Hooked:
        def __init__(s,data=b''):s.h=real(data);s.seen=bytearray(data)
        def update(s,b):s.h.update(b);s.seen+=b
        def hexdigest(s):
            digest=s.h.hexdigest();hit=pending.pop(bytes(s.seen),None)
            if hit:hit[0].write_bytes(hit[1])
            return digest
    with patch('hashlib.sha256',side_effect=Hooked):yield pending


def approval_body(record):
    """The approval record's bytes as `approve` writes them."""
    return (json.dumps(dict(
        version=1, record_sha256='0'*64, record=record,
        plan=dict(path=record.get('plan'), sha256=record.get('artifacts', {}).get(record.get('plan')), copy='plan.json'),
        payload=dict(path=record.get('payload'), sha256=record.get('artifacts', {}).get(record.get('payload')), copy='tb_payload.py'),
        approved_by_uid=1000, approved_at=0), sort_keys=True, indent=1) + '\n').encode()


def stand_approval(approvals, record, plan_bytes=None):
    """One approval directory as root leaves it: the private and public
    records, same bytes, and the plan's copy where given. Returns its digest."""
    body = approval_body(record)
    digest = hashlib.sha256(body).hexdigest()
    directory = approvals / digest
    directory.mkdir(parents=True, exist_ok=True)
    for name in ['approval.json', 'approval.pub.json']:
        (directory / name).write_bytes(body)
    if plan_bytes is not None:
        (directory / 'plan.json').write_bytes(plan_bytes)
    return digest


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = prepare.template(self.root, 'todd', 1000)
        self.plan['rulings'] = {k: f'https://github.com/toddwbucy/WeaverTools/issues/679#issuecomment-{n}' for n, k in enumerate(self.plan['rulings'], 1)}
        self.source = self.root / 'source.ndjson'
        self.source.write_text(trace('r'))
        # One trace per source device, as the historical cells recorded them.
        self.ada_source = self.root / 'ada-source.ndjson'
        self.ada_source.write_text(trace('r-ada'))
        self.plan['files'] = {str(p): order.sha(p) for p in [self.source, self.ada_source]}
        self.plan['arms'][1]['jobs'] = [dict(id=cell, source_cell=cell, kind='refeed', stack='B1',
                                            source_trace=str(trace), source_run=run)
                                        for cell, trace, run in [('ampere', self.source, 'r'), ('ada', self.ada_source, 'r-ada')]]
        self.planpath = self.root / 'plan.json'
        order.atomic(self.planpath, self.plan)
        scripts = Path(__file__).resolve().parent
        # The review record as the review seat publishes it and root snapshots
        # it at `approve` (679.5): the hold, the review, the plan, the payload
        # and every artifact's digest. The state keeps the approval's digest.
        self.record = dict(status='PASS', hold=False, seat=order.REVIEW_SEAT,
                           reference='https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-1',
                           plan=str(self.planpath), payload=str(scripts / 'tb_payload.py'),
                           artifacts={str(p): order.sha(p) for p in scripts.iterdir() if p.suffix in ['.py','.sh']})
        self.record['artifacts'].update({str(self.planpath): order.sha(self.planpath), **self.plan['files']})
        self.approvals = self.root / 'approvals'
        for name, value in [('APPROVAL_ROOT', self.approvals), ('APPROVAL_OWNER', os.getuid())]:
            p = patch.object(order, name, value); p.start(); self.addCleanup(p.stop)
        self.state = dict(cursor=0, done={}, driver=None, halt=None, approval=None)
        self.statepath = self.root / 'state.json'
        self.o = order.Order(self.statepath)
        Fixture.publish(self)

    def publish(self, record=None):
        """Stand an approval as root's `approve` leaves it, for `record` or the
        fixture's own, and point the state at it."""
        self.state['approval'] = stand_approval(self.approvals, record or self.record)
        self.save()

    def save(self):
        order.atomic(self.statepath, self.state)

    def due(self, wanted):
        self.state['cursor'] = [s for s,_ in order.schedule(self.plan)].index(wanted)
        for step,_ in order.schedule(self.plan)[:self.state['cursor']]:
            p = self.root / (step.replace(':','-') + '.log')
            p.write_text('success\n')
            self.state['done'][step] = dict(status='SUCCESS', path=str(p), sha256=order.sha(p), approval=self.state['approval'])
        self.state['driver'] = dict(pid=os.getpid(), ticks=order.ticks(os.getpid()))
        self.save()

    def test_held_next_does_not_invoke_runner(self):
        # No approval recorded: `next` waits on the review seat and hands root
        # nothing (679.5). A published record that is held or not PASS never
        # reaches the runner either.
        s=copy.deepcopy(self.state);s['approval']=None;order.atomic(self.statepath,s)
        with patch('tb_order.payload') as runner, contextlib.redirect_stdout(io.StringIO()) as out:
            self.o.operator()
        runner.assert_not_called()
        self.assertIn('WAITING ON: review seat',out.getvalue())
        for change in [dict(hold=True), dict(status='PENDING')]:
            self.publish(dict(self.record,**change))
            with self.subTest(change=change),patch('tb_order.payload') as runner,contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(order.Refused,'approval-record'):
                self.o.operator()
            runner.assert_not_called()
            s=self.o.read();s['halt']=None;order.atomic(self.statepath,s);self.state=s

    def test_approval_refusals(self):
        # Every review field is the published record's, so each is changed there
        # and published as its own approval (679.5).
        changes = [dict(hold=True), dict(status='PENDING'), dict(seat='coding seat'), dict(reference=None),
                   dict(artifacts={k:v for k,v in self.record['artifacts'].items() if k!=str(self.planpath)}),
                   dict(artifacts={**self.record['artifacts'],str(self.source):'f'*64})]
        good=self.state['approval']
        for change in changes:
            s=copy.deepcopy(self.state);s['approval']=stand_approval(self.approvals,dict(self.record,**change))
            with self.subTest(change=change), self.assertRaises(order.Refused):self.o.approved(s)
        for pointer in [None,'x','0'*64]:
            s=copy.deepcopy(self.state);s['approval']=pointer
            with self.subTest(pointer=pointer), self.assertRaisesRegex(order.Refused,'approval-'):self.o.approved(s)
        s=copy.deepcopy(self.state);s['halt']='refusal'
        with self.assertRaisesRegex(order.Refused,'halt'):self.o.approved(s)
        self.assertEqual(self.state['approval'],good)
        self.assertEqual(self.o.approved(self.state), self.plan)

    def test_manifest_cannot_hide_inputs(self):
        for field in ['absent','mismatch']:
            p=copy.deepcopy(self.plan)
            p['files']={**p['files'],str(self.root/'unreviewed'):'x'} if field=='absent' else {**p['files'],str(self.source):'wrong'}
            order.atomic(self.planpath,p)
            self.record['artifacts'][str(self.planpath)]=order.sha(self.planpath);self.publish()
            with self.assertRaises(order.Refused):self.o.approved(self.state)

    def test_plan_validation(self):
        order.validate_plan(self.plan)
        edits=[('schema',lambda p:p.update(version=2)), ('agent',lambda p:p.update(agent='m1')),
               # #683 thread 48: B1 and B2 are two roots, resolved and disjoint.
               ('stacks-same',lambda p:p['stacks'].update(B2=p['stacks']['B1'])),
               ('stacks-dotdot',lambda p:p['stacks'].update(B2=p['stacks']['B1']+'/../'+Path(p['stacks']['B1']).name)),
               ('stacks-b2-under-b1',lambda p:p['stacks'].update(B2=p['stacks']['B1']+'/inner')),
               ('stacks-b1-under-b2',lambda p:p['stacks'].update(B1=p['stacks']['B2']+'/inner')),
               ('root',lambda p:p.update(install_root='/etc/weaver/admin')),
               ('tuple',lambda p:p['tuple'].update(context_capacity=100)),
               # #683 thread 44: 1 equals True by value and elects nothing by identity.
               ('tuple-election-as-int',lambda p:p['tuple'].update(surprisal=1)),
               ('tuple-seed-as-float',lambda p:p['tuple'].update(seeds=[float(p['tuple']['seeds'][0])]+p['tuple']['seeds'][1:])),
               ('ruling',lambda p:p['rulings'].update(control_count=None)),
               # #683 thread 40: a ruling is the decision's URL, never a placeholder.
               ('ruling-true',lambda p:p['rulings'].update(control_count=True)),
               ('ruling-int',lambda p:p['rulings'].update(control_count=1)),
               ('ruling-text',lambda p:p['rulings'].update(hold_lifted='placeholder')),
               ('ruling-elsewhere',lambda p:p['rulings'].update(cuda_provenance='https://example.org/issues/1')),
               ('arm',lambda p:p['arms'][0].update(name='WRONG')),
               ('identities',lambda p:p['arms'][1]['jobs'][0].update(id=p['arms'][1]['jobs'][1]['id'])),
               ('kind',lambda p:p['arms'][0]['jobs'].append(dict(id='extra',kind='shell',stack='B1',source_trace='/trace',source_run='r'))),
               ('control',lambda p:p['arms'][0]['jobs'][0].update(seed=9)),
               ('own',lambda p:p['arms'][0]['jobs'].pop()),
               ('order',lambda p:p['arms'][0]['jobs'].insert(0,p['arms'][0]['jobs'].pop())),
               ('device',lambda p:p['arms'][1].update(jobs=[])),
               ('kernel',lambda p:p['arms'][2].update(jobs=[])),
               # #683 thread 36: identity true is defined to empty the leg, so a
               # full kernel schedule claiming it is a contradiction, refused.
               ('kernel-identity-with-jobs',lambda p:p['arms'][2].update(executable_identity=True)),
               # #683 thread 38: only absent or exactly false keeps the jobs; a
               # truthy 1 or "true" would be recorded as identity over a run leg.
               ('kernel-identity-truthy-int',lambda p:p['arms'][2].update(executable_identity=1)),
               ('kernel-identity-truthy-str',lambda p:p['arms'][2].update(executable_identity='true'))]
        for name, edit in edits:
            p=copy.deepcopy(self.plan);edit(p)
            with self.subTest(name=name),self.assertRaisesRegex(order.Refused,'stacks-distinct' if name.startswith('stacks-') else '.'):order.validate_plan(p)

    def test_device_arm_measures_each_source_once(self):
        # #683 finding 18: the two cells must not replay one selection, or one
        # trace file between them.
        order.validate_plan(self.plan)
        for fault in ['same-selection','shared-trace','repeated-within-cell']:
            with self.subTest(fault=fault):
                bad=copy.deepcopy(self.plan);jobs=bad['arms'][1]['jobs']
                if fault=='same-selection':jobs[1].update(source_trace=jobs[0]['source_trace'],source_run=jobs[0]['source_run'])
                if fault=='shared-trace':jobs[1].update(source_trace=jobs[0]['source_trace'],source_run='r-other')
                if fault=='repeated-within-cell':jobs.append(dict(jobs[0],id='ampere-again'))
                with self.assertRaisesRegex(order.Refused,'device-selections-distinct'):order.validate_plan(bad)

    def test_device_arm_replays_only_reviewed_external_traces(self):
        # #683 finding 6: a TB-d job naming a local source_job, or a trace the
        # manifest does not hash, would replay a B1 run under a device label.
        order.validate_plan(self.plan)
        free=[j['id'] for j in self.plan['arms'][0]['jobs'] if j['kind']=='free']
        for fault in ['source_job','no-trace','unhashed-trace','no-run']:
            with self.subTest(fault=fault):
                bad=copy.deepcopy(self.plan);job=bad['arms'][1]['jobs'][0]
                if fault=='source_job':job['source_job']=free[0]
                if fault=='no-trace':job.pop('source_trace')
                if fault=='unhashed-trace':job['source_trace']=str(self.root/'elsewhere.ndjson')
                if fault=='no-run':job.pop('source_run')
                with self.assertRaises(order.Refused):order.validate_plan(bad)

    def test_an_emptied_kernel_arm_stands_on_its_comparison(self):
        # #683 findings 26, 29 and 45: executable_identity alone emptied TB-k.
        # The plan must name a hashed comparison report; approval requires it
        # to be sections.compare's own output over two reviewed inventories
        # whose host hashes are exactly the approved hashes of every file
        # under each stack, and its verdict true. A report that is not the
        # comparison's output over those inventories, or whose stacks have
        # since changed, or that claims identity over stacks that differ,
        # empties nothing.
        report=self.root/'identity.json';manifests={};section=dict(name='.text',sha256='a',executable=True)
        members={'cubin':{'x.1.sm_120a.cubin':dict(size=4,sha256='a',sections=[section])},'ptx':{'x.1.sm_75.ptx':dict(size=4,sha256='a')}}
        def stage(b2_bytes=b'same'):
            for stack,data in [('B1',b'same'),('B2',b2_bytes)]:
                src=Path(self.plan['stacks'][stack]);(src/'bin').mkdir(parents=True,exist_ok=True)
                (src/'bin/worker').write_bytes(data);self.plan['files'][str(src/'bin/worker')]=order.sha(src/'bin/worker')
                m=self.root/f'{stack}-manifest.json'
                m.write_text(json.dumps(dict(stack=stack,hosts={'bin/worker':dict(file_sha256=order.sha(src/'bin/worker'),sections=[section])},members=members)))
                manifests[stack]=m;self.plan['files'][str(m)]=order.sha(m)
        stage()
        def inputs(**over):return {s:dict(dict(manifest=str(m),sha256=order.sha(m)),**over.get(s,{})) for s,m in manifests.items()}
        def emptied(verdict,named=True):
            p=copy.deepcopy(self.plan);p['arms'][2]=dict(name='TB-k',executable_identity=True,jobs=[])
            report.write_text(json.dumps(verdict))
            if named:p['arms'][2]['identity_report']=str(report);p['files'][str(report)]=order.sha(report)
            order.atomic(self.planpath,p);self.record['artifacts'].update({str(self.planpath):order.sha(self.planpath),str(report):order.sha(report),**{str(m):order.sha(m) for m in manifests.values()},**{p:h for p,h in self.plan['files'].items()}});self.publish()
            return p
        with self.assertRaisesRegex(order.Refused,'kernel-schedule'):order.validate_plan(emptied({},named=False))
        good=sections.compare(manifests['B1'],manifests['B2']);self.assertTrue(good['executable_identity'])
        for label,guard,verdict in [('false','identity-evidence',dict(good,executable_identity=False)),('unpaired','identity-evidence',dict(executable_identity=True)),
                                    ('same-stack','identity-evidence',dict(good,stacks=['B1','B1'])),('no-inputs','identity-inputs',dict(good,inputs={})),
                                    ('unreviewed-manifest','identity-inputs',dict(good,inputs=inputs(B2=dict(manifest=str(self.root/'elsewhere.json'))))),
                                    ('wrong-digest','identity-inputs',dict(good,inputs=inputs(B2=dict(sha256='0'*64)))),
                                    ('claimed-not-computed','identity-recomputed',dict(good,host={}))]:
            with self.subTest(label=label):
                emptied(verdict)
                with self.assertRaisesRegex(order.Refused,guard):self.o.approved(self.state)
        emptied(good);self.assertEqual(self.o.approved(self.state)['arms'][2]['jobs'],[])
        # The stacks move under a still-hashed report: the verdict no longer binds.
        src=Path(self.plan['stacks']['B2'])/'bin/worker';src.write_text('rebuilt');self.plan['files'][str(src)]=order.sha(src)
        emptied(good)
        with self.assertRaisesRegex(order.Refused,'identity-binds-stacks'):self.o.approved(self.state)
        # #683 thread 45: inventories true to two stacks that differ, under a
        # report that claims identity anyway, are refused by the recomputation.
        stage(b2_bytes=b'different')
        claimed=dict(sections.compare(manifests['B1'],manifests['B2']),executable_identity=True);self.assertFalse(sections.compare(manifests['B1'],manifests['B2'])['executable_identity'])
        emptied(dict(claimed,inputs=inputs()))
        with self.assertRaisesRegex(order.Refused,'identity-recomputed'):self.o.approved(self.state)
        # The same with the two inventories differing in one recorded section only.
        stage();m=manifests['B2'];d=json.loads(m.read_text());d['hosts']['bin/worker']['sections'][0]['sha256']='b';m.write_text(json.dumps(d));self.plan['files'][str(m)]=order.sha(m)
        claimed=dict(sections.compare(manifests['B1'],manifests['B2']),executable_identity=True);self.assertFalse(sections.compare(manifests['B1'],manifests['B2'])['executable_identity'])
        emptied(dict(claimed,inputs=inputs()))
        with self.assertRaisesRegex(order.Refused,'identity-recomputed'):self.o.approved(self.state)

    def test_operator_sequence_success_and_repeat(self):
        def runner(s,step,log):log.write_text('SUCCESS: '+step+'\n');return 0
        with contextlib.redirect_stdout(io.StringIO()):self.o.operator('next',runner)
        s=self.o.read();self.assertEqual(s['cursor'],1)
        with self.assertRaises(order.Refused):self.o.operator('provision',runner)
        with patch('tb_order.payload') as call,contextlib.redirect_stdout(io.StringIO()):self.o.operator()
        call.assert_not_called()

    def test_failed_payload_never_advances(self):
        for rc, line in [(1,'SUCCESS: provision\n'),(0,'no receipt\n')]:
            self.save()
            def runner(s,step,log):log.write_text(line);return rc
            with self.assertRaises(order.Refused):self.o.operator(runner=runner)
            s=self.o.read();self.assertEqual(s['cursor'],0);self.assertTrue(s['halt'])

    def test_history_order_seat_lease(self):
        self.due('load:B1-s451234785645-n1')
        good=copy.deepcopy(self.state)
        cases=[('step',lambda s:None,'unload:B1-s451234785645-n1','operator'),
               ('seat',lambda s:None,'load:B1-s451234785645-n1','coding seat'),
               ('repeat',lambda s:s['done'].update({'load:B1-s451234785645-n1':{}}),'load:B1-s451234785645-n1','operator'),
               ('prior',lambda s:s['done']['provision'].update(status='REFUSED'),'load:B1-s451234785645-n1','operator'),
               ('evidence',lambda s:s['done']['provision'].update(sha256='bad'),'load:B1-s451234785645-n1','operator'),
               ('lease',lambda s:s['driver'].update(ticks='wrong'),'load:B1-s451234785645-n1','operator')]
        for name, edit, step, seat in cases:
            s=copy.deepcopy(good);edit(s)
            with self.subTest(name=name),self.assertRaises(order.Refused):self.o.guard(s,self.plan,step,seat)
        self.o.guard(good,self.plan,'load:B1-s451234785645-n1','operator')
        for cursor in [-1,9999,False]:
            s=copy.deepcopy(good);s['cursor']=cursor
            with self.assertRaises(order.Refused):self.o.due(s,self.plan)

    def test_lease_start_and_coding_owner(self):
        self.due('start:TB0')
        p=self.root/'start.json';p.write_text('{}')
        with self.assertRaises(order.Refused):self.o.coding('start:TB0',p)
        self.state['driver']=None;self.save();self.o.coding('start:TB0',p)
        self.assertEqual(self.o.read()['driver']['pid'],os.getpid())
        self.due('measure:B1-s451234785645-n1')
        with patch('tb_order.live',return_value=True):
            self.state['driver']['pid']=-1
            with self.assertRaises(order.Refused):self.o.guard(self.state,self.plan,'measure:B1-s451234785645-n1','coding seat')

    def test_report_executor(self):
        # #683 finding 12, ruling (a): report runs in a fresh process with its
        # own lease, only after every arm's finish: evidence is recorded and
        # intact, and hands the cursor to the review seat.
        report=self.root/'report.json';report.write_text('{}')
        self.due('finish:TB-k');self.state['driver']=None;self.save()
        with self.assertRaisesRegex(order.Refused,'step-order'):self.o.coding('report',report)
        self.due('report');done=self.state['done'].pop('finish:TB-k');self.state['driver']=None;self.save()
        with self.assertRaisesRegex(order.Refused,'prior-success'):self.o.coding('report',report)
        self.state['done']['finish:TB-k']=done;Path(done['path']).write_text('changed');self.save()
        with self.assertRaisesRegex(order.Refused,'prior-evidence'):self.o.coding('report',report)
        Path(done['path']).write_text('success\n');self.due('report')
        with self.assertRaisesRegex(order.Refused,'no-live-driver'):self.o.coding('report',report)
        self.state['driver']=None;self.save()
        with self.assertRaisesRegex(order.Refused,'report-evidence'):self.o.coding('report',self.root/'absent.json')
        self.o.coding('report',report)
        after=self.o.read();steps=[s for s,_ in order.schedule(self.plan)]
        self.assertEqual(after['cursor'],steps.index('review'))
        self.assertEqual((after['done']['report']['path'],after['driver']['pid']),(str(report),os.getpid()))
        with contextlib.redirect_stdout(io.StringIO()) as out:self.o.operator()
        self.assertEqual(out.getvalue(),'WAITING ON: review seat - review\n')

    def test_a_receipt_of_another_approval_is_no_step_of_this_run(self):
        # #709 round one: previous() held a receipt's status and bytes but not
        # the approval it ran under, so evidence of two approvals could sit in
        # one run. Every receipt names its approval, and every step, the
        # report and COMPLETE among them, refuses one not the state's.
        # Perturbation: drop prior-approval and each case here passes.
        p=self.root/'start.json';p.write_text('{}')
        self.due('start:TB0');self.state['driver']=None;self.save();self.o.coding('start:TB0',p)
        self.assertEqual(self.o.read()['done']['start:TB0']['approval'],self.state['approval'])
        other=stand_approval(self.approvals,dict(self.record,reference=self.record['reference']+'0'))
        report=self.root/'report.json';report.write_text('{}')
        for step,value in [('provision',other),('provision',None),('finish:TB-k',other)]:
            with self.subTest(step=step,value=value):
                self.due('report');self.state['driver']=None
                if value is None:del self.state['done'][step]['approval']
                else:self.state['done'][step]['approval']=value
                self.save()
                with self.assertRaisesRegex(order.Refused,'prior-approval'):self.o.previous(self.state,self.plan)
                with self.assertRaisesRegex(order.Refused,'prior-approval'):self.o.coding('report',report)
                self.assertNotIn('report',self.o.read()['done'])
        # Two absences compare equal: a state holding no approval and a receipt
        # naming none refuse in previous() itself, whatever its caller checked.
        # Perturbation: drop the presence clause and previous() passes this.
        self.due('report');bare=copy.deepcopy(self.state);bare['approval']=None
        for step in bare['done']:del bare['done'][step]['approval']
        with self.assertRaisesRegex(order.Refused,'prior-approval'):self.o.previous(bare,self.plan)
        steps=order.schedule(self.plan);self.due(steps[-1][0])
        review=self.root/'review.log';review.write_text('PASS\n')
        self.state['done']['review']=dict(status='SUCCESS',path=str(review),sha256=order.sha(review),approval=other)
        self.state['cursor']=len(steps);self.save()
        with contextlib.redirect_stdout(io.StringIO()) as out,self.assertRaisesRegex(order.Refused,'prior-approval'):self.o.operator()
        self.assertNotIn('COMPLETE',out.getvalue())

    def test_next_reports_completion_after_the_review(self):
        steps=order.schedule(self.plan);self.due(steps[-1][0])
        p=self.root/'review.log';p.write_text('PASS\n')
        self.state['done']['review']=dict(status='SUCCESS',path=str(p),sha256=order.sha(p),approval=self.state['approval']);self.state['cursor']=len(steps);self.save()
        with contextlib.redirect_stdout(io.StringIO()) as out:self.o.operator()
        self.assertTrue(out.getvalue().startswith('COMPLETE:'))
        self.assertNotIn('refusals',self.o.read())
        # #683 finding 15: completion claims every receipt, so a receipt
        # changed after the review refuses it rather than printing COMPLETE.
        p.write_text('changed after the review\n')
        with contextlib.redirect_stdout(io.StringIO()) as out,self.assertRaisesRegex(order.Refused,'prior-evidence'):self.o.operator()
        self.assertNotIn('COMPLETE',out.getvalue())

    def test_driver_report_command(self):
        report=self.root/'report.json';report.write_text('{}');self.due('report');self.state['driver']=None;self.save()
        with patch('sys.argv',['driver','--state',str(self.statepath),'report']),contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(driver.main(),1)
        self.assertIn('report-path',err.getvalue())
        self.state['halt']=None;self.save()
        with patch('sys.argv',['driver','--state',str(self.statepath),'report',str(report)]),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(driver.main(),0)
        self.assertIn('report',self.o.read()['done'])

    def test_wait_succeeds_only_with_receipt_and_own_live_lease(self):
        self.due('measure:B1-s451234785645-n1')
        self.o.wait('measure:B1-s451234785645-n1',timeout=0)
        self.state['driver']['ticks']='dead';self.save()
        with self.assertRaises(order.Refused):self.o.wait('measure:B1-s451234785645-n1',timeout=0)
        self.due('load:B1-s451234785645-n1')
        with self.assertRaises(order.Refused):self.o.wait('measure:B1-s451234785645-n1',timeout=0)
        self.due('start:TB0')
        with self.assertRaisesRegex(order.Refused,'wait-order'):self.o.wait('measure:B1-s451234785645-n1',timeout=0)

    def test_wait_verifies_approval_only_when_the_state_moves(self):
        # #683 finding 28: approval hashes the whole reviewed deposit, the model
        # included, under the lock next needs; polling it every second starved
        # the operator. It now runs once per state, and again once the state
        # moves, before the wait returns.
        self.due('load:B1-s451234785645-n1');calls=[];real=order.Order.approved
        def counting(o,s):calls.append(s['cursor']);return real(o,s)
        with patch.object(order.Order,'approved',counting):
            with self.assertRaisesRegex(order.Refused,'wait-deadline'):self.o.wait('measure:B1-s451234785645-n1',timeout=0.3,poll=0.01)
            self.assertEqual(len(calls),1)
            self.due('measure:B1-s451234785645-n1');self.o.wait('measure:B1-s451234785645-n1',timeout=0.3,poll=0.01)
        self.assertEqual(len(calls),2)

    def test_process_wait_stays_alive_until_operator_receipt(self):
        self.due('load:B1-s451234785645-n1')
        script="""import os,sys
from pathlib import Path
import tb_order
from tb_order import *
# The fixture's approvals stand under its temporary root, owned by this
# uid, as the parent test patched them; a child imports the module fresh.
tb_order.APPROVAL_ROOT=Path(sys.argv[2]);tb_order.APPROVAL_OWNER=os.getuid()
o=Order(sys.argv[1]);s=o.read();s['driver']={'pid':os.getpid(),'ticks':ticks(os.getpid())};atomic(o.path,s)
print('WAITING',flush=True);o.wait('measure:B1-s451234785645-n1',timeout=10,poll=.02);print('DONE',flush=True)
"""
        child=subprocess.Popen([sys.executable,'-c',script,str(self.statepath),str(self.approvals)],cwd=Path(__file__).parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'WAITING')
            self.assertIsNone(child.poll())
            def runner(s,step,log):log.write_text('SUCCESS: '+step+'\n');return 0
            for _ in range(100):
                try:
                    with contextlib.redirect_stdout(io.StringIO()):self.o.operator(runner=runner)
                    break
                except order.Busy:time.sleep(.01)
            out,err=child.communicate(timeout=10)
            self.assertEqual(child.returncode,0,err);self.assertIn('DONE',out)
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stdout.close();child.stderr.close()

    def test_root_is_handed_no_operator_bytes(self):
        # #683 finding 17, then #709 round four: sudo was handed the payload's
        # bytes by -c, read from the operator-owned staging by operator-owned
        # code, so a process of the operator's uid could hand root anything.
        # Now sudo runs only the hand-installed root program, handed the step
        # and the approval's digest: no bytes and no path the operator writes.
        staged=Path(order.__file__).with_name('tb_payload.py')
        before=sorted(p.name for p in self.root.iterdir());seen=[]
        def as_root(argv,**kw):seen.append((argv,kw['stdin']));return subprocess.CompletedProcess(argv,0)
        with patch('tb_order.subprocess.run',side_effect=as_root),patch.object(Path,'read_bytes',side_effect=AssertionError('the coordinator reads no payload for root')):
            self.assertEqual(order.payload(self.state,'provision',self.root/'log'),0)
        (argv,stdin),=seen
        self.assertIs(stdin,subprocess.DEVNULL)
        self.assertEqual(argv,['sudo',order.ROOT_PROGRAM,'run','provision',self.state['approval']])
        self.assertEqual([a for a in argv[3:] if os.path.exists(a)],[],'root is handed no path at all')
        self.assertNotIn(str(staged),argv)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),sorted(before+['log']))
        # A payload replaced in the staging, its digest written into the state
        # where the review used to live, changes nothing root is handed.
        s=copy.deepcopy(self.state);s['review']=dict(status='PASS',artifacts={str(staged):'f'*64})
        with patch('tb_order.subprocess.run',side_effect=as_root):order.payload(s,'provision',self.root/'log')
        self.assertEqual(seen[-1][0],argv)

    def test_sudo_receives_digest_recorded_at_approval(self):
        # #683 finding 2, since 679.5: a plan edited after approval reaches sudo
        # as nothing but the approval's digest, which names the root-owned
        # record and plan copy root verifies, never a digest recomputed now.
        self.planpath.write_text(self.planpath.read_text().replace('"bravo"','"karl"'))
        self.assertNotEqual(order.sha(self.planpath),self.record['artifacts'][str(self.planpath)])
        seen=[]
        def inspect(argv,**kw):seen.append(argv[3:]);return subprocess.CompletedProcess(argv,0)
        with patch('tb_order.subprocess.run',side_effect=inspect):order.payload(self.state,'provision',self.root/'log')
        self.assertEqual(seen,[['provision',self.state['approval']]])

    def test_approval_parses_the_plan_bytes_it_hashed(self):
        # A plan swapped between the artifact-hash read and the parse is refused,
        # never returned as approved.
        altered=dict(self.plan,note='swapped after hashing')
        real_sha=order.sha;swapped=[]
        def hook(path):
            digest=real_sha(path)
            if Path(path)==self.planpath and not swapped:
                swapped.append(1);self.planpath.write_text(json.dumps(altered))
            return digest
        with patch('tb_order.sha',side_effect=hook),self.assertRaises(order.Refused):self.o.approved(self.state)
        self.assertEqual(swapped,[1])

    def test_best_effort_notice(self):
        for error in [FileNotFoundError(),subprocess.TimeoutExpired('gh',20)]:
            with patch('tb_order.subprocess.run',side_effect=error),contextlib.redirect_stdout(io.StringIO()):order.notice('load:one')

    def test_lock_and_atomic_state(self):
        with self.o.locked():
            with self.assertRaises(order.Busy):
                with self.o.locked():pass
        self.o.fail('finding');self.assertEqual(self.o.read()['halt'],'finding')
        self.assertFalse(list(self.root.glob('.tb-*')))


class ReadingTests(unittest.TestCase):
    def rec(self):
        # extract_run's real key set (golden.EXTRACT_RUN_KEYS); field keys are
        # ints as extract_run builds them, strings once a record is JSON.
        return dict(dict.fromkeys(golden.EXTRACT_RUN_KEYS),output_tokens=[1],entropies=[0.5],surprisals=[0.25],
                    field={20:dict(ranked=[{'token':i,'probability':.005} for i in range(200)],realized=1)})

    def test_exact_rejects_empty_partial_and_changed(self):
        t=prepare.template(Path('/deposit'),'todd',1000)['tuple']
        # #683 thread 44: series() elects by the shared identity predicate, so
        # a 1 the validator would also refuse elects nothing here either.
        self.assertIn('surprisals',driver.series(t));self.assertNotIn('surprisals',driver.series(dict(t,surprisal=1)))
        self.assertTrue(order.elected(True) and not order.elected(1) and order.declined(False) and not order.declined(0))
        a=self.rec();b=copy.deepcopy(a)
        self.assertTrue(driver.exact(t,a,b))
        b['field']={'20':b['field'][20]};self.assertTrue(driver.exact(t,a,b))
        b['entropies']=[.5000000000000001];self.assertFalse(driver.exact(t,a,b))
        b=copy.deepcopy(a);b['field'][20]['ranked'].pop()
        with self.assertRaises(order.Refused):driver.exact(t,a,b)
        b=copy.deepcopy(a);b['entropies']=[]
        with self.assertRaises(order.Refused):driver.exact(t,a,b)
        # #683 finding 23: the tuple elects surprisal, so the surprisals are
        # required and compared like the entropies: absent or empty refuses,
        # one bit changed is unequal.
        self.assertTrue(t['surprisal'])
        for missing in [[],None]:
            b=copy.deepcopy(a);b['surprisals']=missing
            with self.assertRaisesRegex(order.Refused,'nonempty-measurement'):driver.exact(t,a,b)
        b=copy.deepcopy(a);b['surprisals']=[.25000000000000006];self.assertFalse(driver.exact(t,a,b))
        # An unelected reading stays unrequired, and a true election with no
        # record key fails loudly instead of going unread.
        b=copy.deepcopy(a);b['surprisals']=None;self.assertTrue(driver.exact(dict(t,surprisal=False),dict(a,surprisals=None),b))
        with self.assertRaises(KeyError):driver.exact(dict(t,residual=True),a,a)
        self.assertNotEqual(driver.float_bits([0.0]),driver.float_bits([-0.0]))

    def test_trace_close_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            closed=event(golden.TURN_CLOSED);p=Path(tmp)/'trace';p.write_text(ndjson(closed))
            self.assertEqual(driver.until_closed(p,'turn.closed',1),ndjson(closed).encode())
            with self.assertRaises(order.Refused):driver.until_closed(p,'replay.closed',0)

    def test_section_comparison_detects_instruction_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a';q=Path(tmp)/'b'
            section=dict(name='.text',sha256='a',executable=True)
            manifest=dict(stack='B1',hosts={'lib':dict(file_sha256='f',sections=[section])},members={'cubin':{'lib.1.sm_120a.cubin':dict(size=4,sha256='a',sections=[section])},'ptx':{'lib.1.sm_75.ptx':dict(size=4,sha256='a')}})
            p.write_text(json.dumps(manifest));q.write_text(json.dumps(dict(manifest,stack='B2')))
            self.assertTrue(sections.compare(p,q)['executable_identity'])
            changed=dict(copy.deepcopy(manifest),stack='B2');changed['members']['cubin']['lib.1.sm_120a.cubin']['sections'][0]['sha256']='b'
            q.write_text(json.dumps(changed));r=sections.compare(p,q)
            self.assertFalse(r['executable_identity']);self.assertEqual(r['cuda']['cubin']['sm_120a']['code_equal'],0)

    def test_host_identity_requires_the_whole_file(self):
        # #683 finding 3: equal section records do not make equal hosts. A file
        # hash that differs with no section change, or that was never recorded,
        # refuses identity.
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a';q=Path(tmp)/'b'
            section=dict(name='.text',sha256='a',executable=True)
            members={'cubin':{'lib.1.sm_120a.cubin':dict(size=4,sha256='a',sections=[section])},'ptx':{'lib.1.sm_75.ptx':dict(size=4,sha256='a')}}
            p.write_text(json.dumps(dict(stack='B1',hosts={'lib':dict(file_sha256='f',sections=[section])},members=members)))
            for host in [dict(file_sha256='g',sections=[section]),dict(sections=[section])]:
                q.write_text(json.dumps(dict(stack='B2',hosts={'lib':host},members=members)))
                r=sections.compare(p,q)
                self.assertEqual(r['host']['lib']['changes'],[])
                self.assertFalse(r['executable_identity'],host)

    def test_identity_needs_a_b1_b2_pair_with_scope(self):
        # #683 finding 24: the same inventory twice, the pair reversed, or an
        # inventory with no hosts or members would make identity vacuous or
        # self-evident; each refuses rather than returning a verdict.
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a';q=Path(tmp)/'b'
            section=dict(name='.text',sha256='a',executable=True)
            b1=dict(stack='B1',hosts={'lib':dict(file_sha256='f',sections=[section])},
                    members={'cubin':{'lib.1.sm_120a.cubin':dict(size=4,sha256='a',sections=[section])},'ptx':{'lib.1.sm_75.ptx':dict(size=4,sha256='a')}})
            p.write_text(json.dumps(b1));q.write_text(json.dumps(dict(b1,stack='B2')))
            self.assertEqual(sections.compare(p,q)['stacks'],['B1','B2'])
            # One inventory named twice, by another spelling, refuses before it is read.
            same=Path(tmp)/'same';same.write_text(json.dumps(b1))
            with self.assertRaisesRegex(ValueError,'twice'):sections.compare(same,Path(tmp)/'..'/Path(tmp).name/'same')
            for label,first,second in [('same',b1,b1),('reversed',dict(b1,stack='B2'),b1),
                                       ('no-ptx',b1,dict(b1,stack='B2',members=dict(b1['members'],ptx={}))),
                                       ('no-cubin',b1,dict(b1,stack='B2',members=dict(b1['members'],cubin={}))),
                                       ('no-hosts',dict(b1,hosts={}),dict(b1,stack='B2',hosts={}))]:
                with self.subTest(label=label):
                    p.write_text(json.dumps(first));q.write_text(json.dumps(second))
                    with self.assertRaises(ValueError):sections.compare(p,q)

    def test_identity_covers_every_file_a_load_reaches(self):
        # #683 finding 27: the inventory read only ELF files under bin and
        # engine-lib, so a different cuda-lib library, which every load puts on
        # LD_LIBRARY_PATH, or a different bin/basic_loop.py, which the worker
        # runs, left executable_identity true. The real inventory() runs here.
        elf=Path(sys.executable).resolve().read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            deposit=Path(tmp)
            def build(stack,cuda=elf,loop='print(1)\n'):
                root=deposit/'stacks'/stack
                for d in ['bin','engine-lib','cuda-lib']:(root/d).mkdir(parents=True,exist_ok=True)
                (root/'bin/worker').write_bytes(elf);(root/'bin/basic_loop.py').write_text(loop)
                (root/'engine-lib/libggml-cuda.so').write_bytes(elf);(root/'cuda-lib/libcudart.so.13').write_bytes(cuda)
                out=deposit/'sections'/stack
                for d in ['cubin','ptx']:(out/d).mkdir(parents=True,exist_ok=True)
                (out/'cubin/x.1.sm_120a.cubin').write_bytes(elf);(out/'ptx/x.1.sm_75.ptx').write_text('ptx\n')
            def inventory(stack):
                with patch('sys.argv',['sections.py',str(deposit),stack]),contextlib.redirect_stdout(io.StringIO()):sections.inventory()
                return deposit/'sections'/stack/'section-manifest.json'
            def verdict():return sections.compare(inventory('B1'),inventory('B2'))
            build('B1');build('B2')
            r=verdict();self.assertTrue(r['executable_identity'])
            self.assertIn('cuda-lib/libcudart.so.13',r['host']);self.assertIn('bin/basic_loop.py',r['host'])
            changed=bytearray(elf);changed[-1]^=1
            build('B2',cuda=bytes(changed));r=verdict()
            self.assertFalse(r['executable_identity']);self.assertFalse(r['host']['cuda-lib/libcudart.so.13']['file_equal'])
            build('B2',loop='print(2)\n');r=verdict()
            self.assertFalse(r['executable_identity']);self.assertFalse(r['host']['bin/basic_loop.py']['file_equal'])
            build('B2');(deposit/'stacks/B2/cuda-lib/libcudart.so').symlink_to('libcudart.so.13')
            with self.assertRaises(ValueError):inventory('B2')

    def test_host_headers_are_inventoried_and_compared(self):
        # Real ELF bytes: change the entry point, then one segment's permissions.
        # Neither lives in a section payload, so the section records stay equal.
        import struct
        with tempfile.TemporaryDirectory() as tmp:
            original=Path(tmp)/'original';original.write_bytes(Path(sys.executable).resolve().read_bytes())
            base=sections.elf_sections(original)
            self.assertGreater(len(base['program_headers']),0)
            members={'cubin':{'x.1.sm_120a.cubin':dict(size=4,sha256='a',sections=[])},'ptx':{'x.1.sm_75.ptx':dict(size=4,sha256='a')}}
            def manifest(record,stack='B2'):return dict(stack=stack,hosts={'bin/x':record},members=members)
            p=Path(tmp)/'a';p.write_text(json.dumps(manifest(base,'B1')))
            q=Path(tmp)/'b';q.write_text(json.dumps(manifest(base)))
            self.assertTrue(sections.compare(p,q)['executable_identity'])
            flags=base['elf_header']['phoff']+4
            for offset,fmt,part in [(24,'<Q','elf_header'),(flags,'<I','program_headers')]:
                data=bytearray(original.read_bytes())
                struct.pack_into(fmt,data,offset,struct.unpack_from(fmt,data,offset)[0]^1)
                changed=Path(tmp)/'changed';changed.write_bytes(data)
                record=sections.elf_sections(changed)
                self.assertEqual(record['sections'],base['sections'])
                q.write_text(json.dumps(manifest(record)));r=sections.compare(p,q)
                self.assertEqual(r['host']['bin/x']['changes'],[])
                # The first LOAD segment spans the ELF header, so an entry change moves its hash too.
                self.assertIn(part,[h['part'] for h in r['host']['bin/x']['header_changes']])
                self.assertFalse(r['executable_identity'],part)


TWO_RUNS=ndjson(event(golden.TURN_STARTED,run='r1'),event(golden.TURN_STARTED,run='r2'),event(golden.TURN_CLOSED,run='r2'))


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'install';self.model=self.base/'model'
        self.plan=prepare.template(self.base/'deposit','todd',1000)
        self.planpath=self.base/'plan';self.planpath.write_text('{}')
        for name,value in [('ROOT',self.root),('MODEL',self.model),('TRUSTED',self.base)]:
            p=patch.object(payload,name,value);p.start();self.addCleanup(p.stop)
        for name,value in [('ROOT',self.root),('TRUSTED',self.base)]:
            p=patch.object(rootprog,name,value);p.start();self.addCleanup(p.stop)
        p=patch('sys.argv',['payload',str(self.planpath),order.sha(self.planpath),'provision']);p.start();self.addCleanup(p.stop)
        self.user=SimpleNamespace(pw_uid=1000)
        # The install root as `approve` leaves it before provision: standing,
        # locked, holding the approvals and nothing else (679.5).
        (self.root/'approval').mkdir(parents=True);os.chmod(self.root,0o755)

    def untouched(self):
        """A refused provision wrote nothing: the root holds the approvals alone."""
        return sorted(os.listdir(self.root))==['approval']

    CODE=b'# the payload bytes root runs\n'

    def stand(self,p,code=None,**changes):
        """An approval of plan p as `approve` leaves it, complete: its plan and
        the payload copied root-owned beside it, every file at its written
        mode. Returns the digest the coordinator hands over."""
        data=json.dumps(p).encode();self.planpath.write_bytes(data)
        record=dict(status='PASS',hold=False,seat=order.REVIEW_SEAT,
                    reference='https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-1',
                    plan=str(self.planpath),payload='/staged/tb_payload.py',
                    artifacts={str(self.planpath):hashlib.sha256(data).hexdigest(),
                               '/staged/tb_payload.py':hashlib.sha256(code or self.CODE).hexdigest()})
        digest=stand_approval(self.root/'approval',{**record,**changes},data)
        directory=self.root/'approval'/digest;(directory/'tb_payload.py').write_bytes(code or self.CODE)
        for name,mode in rootprog.FILES.items():(directory/name).chmod(mode)
        directory.chmod(0o755);(self.root/'approval').chmod(0o755)
        return digest

    @contextlib.contextmanager
    def as_root(self,code=None):
        """Custody read as if this test's uid were root's, in the payload and
        the root program both: a test cannot own a file as root."""
        import stat as st
        def locked(path):
            e=os.lstat(path);return not st.S_ISLNK(e.st_mode) and e.st_uid==os.getuid() and not e.st_mode&0o022
        def chain(path):
            d=Path(path).parent
            while True:
                e=os.lstat(d)
                if not st.S_ISDIR(e.st_mode) or e.st_uid not in (os.getuid(),0) or e.st_mode&0o022:return False
                if d==payload.TRUSTED or d.parent==d:return d==payload.TRUSTED
                d=d.parent
        with patch.object(payload,'locked',side_effect=locked),patch.object(payload,'chain_custody',side_effect=chain),patch.object(rootprog,'locked',side_effect=locked),patch.object(rootprog,'chain_custody',side_effect=chain):
            yield

    def stacks(self):
        for stack in ['B1','B2']:
            root=Path(self.plan['stacks'][stack])
            for directory in ['bin','engine-lib','cuda-lib']:(root/directory).mkdir(parents=True)
            (root/'bin/pyworker').write_text('stub')
            self.plan['files'][str(root/'bin/pyworker')]=order.sha(root/'bin/pyworker')
        src=Path(self.plan['model_source']);src.parent.mkdir(parents=True);src.write_text('weights')
        self.plan['tuple']['weights_sha256']=order.sha(src)
        self.plan['files'][str(src)]=order.sha(src)

    def test_m1_interlock(self):
        def probe(stdout,rc=0,door=False,procs=None):
            with patch('tb_payload.subprocess.run',return_value=subprocess.CompletedProcess([],rc,stdout,'')),patch('tb_payload.door_state',return_value=door),patch('tb_payload.Path.iterdir',return_value=procs or []),patch('tb_payload.pwd.getpwnam',return_value=self.user),patch('tb_payload.proc_hides_processes',return_value=False):
                payload.m1_unloaded()
        # golden.SYSTEMCTL_SHOW_M1 is this box's real reading; the refusals
        # change one value in that real format.
        probe(golden.SYSTEMCTL_SHOW_M1)
        loaded=golden.SYSTEMCTL_SHOW_M1.replace('LoadState=not-found','LoadState=loaded')
        for out,rc,door,procs in [(loaded.replace('ActiveState=inactive','ActiveState=active'),0,False,[]),(loaded,1,False,[]),(loaded,0,True,[]),(loaded,0,False,[SimpleNamespace(name='42',stat=lambda:SimpleNamespace(st_uid=1000))])]:
            with self.assertRaises(RuntimeError):probe(out,rc,door,procs)

    def test_admin_reply_not_merely_exit_zero(self):
        def cp(state):return subprocess.CompletedProcess([],0,golden.ADMIN_STATE.format(state)+'\n','')
        with patch('tb_payload.run',return_value=cp('unloaded')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(payload.answer('B1','show','unloaded')['state'],'unloaded')
        with patch('tb_payload.run',return_value=cp('idle')),self.assertRaises(RuntimeError):payload.answer('B1','show','unloaded')
        # A real refusal is one line with exit 1: run() keeps the line in the
        # transcript and refuses by name, never an unnamed exception.
        refusal=subprocess.CompletedProcess(['weaver-admin'],1,golden.ADMIN_NO_RESIDENCY+'\n','')
        with patch('tb_payload.subprocess.run',return_value=refusal),contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()),self.assertRaisesRegex(RuntimeError,'command-exit'):payload.answer('B1','unload','unloaded')
        self.assertIn(golden.ADMIN_NO_RESIDENCY,out.getvalue())

    def test_save_refuses_symlink(self):
        # The named guard first; then, with the guard bypassed as a race would
        # bypass it, the open itself refuses to follow a link at the name
        # (#683 thread 47's second half: writes beneath a held root are pinned).
        p=self.base/'file';payload.save(p,'a');self.assertEqual(p.read_text(),'a')
        target=self.base/'elsewhere';target.write_text('x');link=self.base/'linked';link.symlink_to(target)
        with patch('tb_payload.need'),self.assertRaises(OSError):payload.save(link,'b')
        self.assertEqual(target.read_text(),'x')
        link=self.base/'link';link.symlink_to(p)
        with self.assertRaises(RuntimeError):payload.save(link,'b')
        self.assertEqual(p.read_text(),'a')

    def provision(self):
        with patch('tb_payload.pwd.getpwnam',side_effect=KeyError),patch('tb_payload.grp.getgrnam',side_effect=self.groups),patch('tb_payload.os.chown'),patch('tb_payload.run'),contextlib.redirect_stdout(io.StringIO()):payload.provision(self.plan,'d'*64)

    def groups(self,name):
        # The box's groups as a test sets them; before provisioning the
        # operator's exists and bravo's does not.
        if name in getattr(self,'groups_present',{self.plan['operator']}):return SimpleNamespace(gr_gid=os.getgid())
        raise KeyError(name)

    def test_provision_and_installed_hash_checks(self):
        self.stacks();self.provision()
        self.assertTrue((self.root/'config/B1/allow-list').is_file())
        self.assertEqual((self.root/'config/B1/allow-list').read_text(),'bravo\n')
        payload.installed(self.plan,'d'*64)
        file=self.root/'stacks/B1/bin/pyworker';file.write_text('changed')
        with self.assertRaises(RuntimeError):payload.installed(self.plan,'d'*64)
        file.write_text('stub');self.model.write_text('changed')
        with self.assertRaises(RuntimeError):payload.installed(self.plan,'d'*64)
        self.model.write_text('weights');(self.root/'plan-sha256').write_text('changed')
        with self.assertRaises(RuntimeError):payload.installed(self.plan,'d'*64)
        with self.assertRaises(RuntimeError):self.provision()

    def test_provision_refuses_stack_links_before_mutation(self):
        # #683 finding 4: a linked directory is never descended and a linked file
        # is hashed at its target, so either would pass coverage and carry
        # unreviewed bytes into the root-owned install. Both refuse before ROOT.
        self.stacks()
        outside=self.base/'outside';outside.mkdir();(outside/'lib.so').write_text('unreviewed')
        twin=self.base/'twin';twin.write_text('stub')
        stack=Path(self.plan['stacks']['B1'])
        for kind in ['directory','file']:
            with self.subTest(kind=kind):
                if kind=='directory':(stack/'engine-lib/linked').symlink_to(outside,target_is_directory=True)
                else:(stack/'bin/pyworker').unlink();(stack/'bin/pyworker').symlink_to(twin)
                with self.assertRaisesRegex(RuntimeError,'stack-no-symlinks'):self.provision()
                self.assertTrue(self.untouched())
                if kind=='directory':(stack/'engine-lib/linked').unlink()
                else:(stack/'bin/pyworker').unlink();(stack/'bin/pyworker').write_text('stub')
        self.provision();self.assertFalse((self.root/'stacks/B1/bin/pyworker').is_symlink())

    def test_provision_verifies_the_copy_it_installed(self):
        # #683 finding 7: a stack file changed after the pre-copy checks is
        # caught in the installed copy before provisioning reports success.
        self.stacks();real=shutil.copytree
        def racing(src,dst,*args,**kw):
            if (Path(src)/'bin').is_dir():(Path(src)/'bin/pyworker').write_text('changed after the check')
            return real(src,dst,*args,**kw)
        with patch('tb_payload.shutil.copytree',side_effect=racing),self.assertRaisesRegex(RuntimeError,'installed-stack-hash'):self.provision()

    def test_served_model_must_be_in_custody(self):
        # #683 finding 19: a model already present is accepted only as a
        # regular, single-named file only the payload's user can write.
        self.stacks();src=Path(self.plan['model_source'])
        for fault in ['symlink','hard-link','group-writable']:
            with self.subTest(fault=fault):
                if fault=='symlink':self.model.symlink_to(src)
                if fault=='hard-link':os.link(src,self.model)
                if fault=='group-writable':self.model.write_bytes(src.read_bytes());self.model.chmod(0o664)
                try:
                    with self.assertRaisesRegex(RuntimeError,'existing-model-custody'):self.provision()
                    self.assertTrue(self.untouched())
                finally:self.model.unlink()
        self.provision();payload.installed(self.plan,'d'*64)
        self.model.unlink();self.model.symlink_to(src)
        with self.assertRaisesRegex(RuntimeError,'installed-model-custody'):payload.installed(self.plan,'d'*64)

    def test_served_directories_are_locked_and_stay_locked(self):
        # #683 finding 22: copytree copies the source root's mode onto the
        # installed root, and rglob never yields the root, so a world-writable
        # source left stacks/B1 writable. Every served directory is locked when
        # it is made, and installed() refuses one reopened later, by name.
        self.stacks();Path(self.plan['stacks']['B1']).chmod(0o777)
        self.provision()
        installed=self.root/'stacks/B1'
        self.assertEqual(installed.stat().st_mode&0o777,0o755)
        for d in payload.served_directories():self.assertEqual(d.stat().st_mode&0o022,0,d)
        payload.installed(self.plan,'d'*64)
        installed.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError,'installed-stack-custody'):payload.installed(self.plan,'d'*64)
        installed.chmod(0o755);(self.root/'config/B1').chmod(0o777)
        with self.assertRaisesRegex(RuntimeError,'served-directory-custody'):payload.installed(self.plan,'d'*64)

    def test_model_custody_walks_every_ancestor(self):
        # #683 thread 39: a verified model under an operator-writable ancestor
        # is a file the operator can rename out from under the load. The walk
        # runs from the parent up to TRUSTED (the filesystem root in
        # production, this test's base here); a group-writable grandparent
        # refuses by name, at provisioning and at every later step, and the
        # isolated root's own chain is held to the same rule.
        self.stacks()
        deep=self.base/'ancestor'/'models';deep.mkdir(parents=True)
        with patch.object(payload,'MODEL',deep/'model'):
            (self.base/'ancestor').chmod(0o775)
            with self.assertRaisesRegex(RuntimeError,'model-chain-custody'):self.provision()
            self.assertTrue(self.untouched())
            (self.base/'ancestor').chmod(0o755)
            self.provision();payload.installed(self.plan,'d'*64)
            (self.base/'ancestor').chmod(0o775)
            with self.assertRaisesRegex(RuntimeError,'installed-model-custody'):payload.installed(self.plan,'d'*64)
            (self.base/'ancestor').chmod(0o755);payload.installed(self.plan,'d'*64)
            nested=self.base/'under'/'root';nested.parent.mkdir()
            with patch.object(payload,'ROOT',nested):
                shutil.copytree(self.root,nested);(self.base/'under').chmod(0o775)
                with self.assertRaisesRegex(RuntimeError,'served-directory-custody'):payload.installed(self.plan,'d'*64)

    def test_model_directories_are_made_locked_one_by_one(self):
        # #683 thread 50: mkdir(parents=True) makes the intermediate directories
        # at the umask and lock() reaches only the last, so a permissive sudo
        # umask left /opt/weaver group-writable and every retry refusing. Each
        # missing component is made at 0755 and locked as it is made, before
        # ROOT exists.
        self.stacks();deep=self.base/'made'/'below'/'models';old=os.umask(0o002)
        try:
            with patch.object(payload,'MODEL',deep/'model'):self.provision()
        finally:os.umask(old)
        for d in [self.base/'made',self.base/'made'/'below',deep]:self.assertEqual(d.stat().st_mode&0o777,0o755,d)

    def test_new_model_must_be_in_custody(self):
        # #683 finding 30: a model this provisioning creates is held like an
        # existing one; a group-writable parent lets another process replace
        # the new file after its hash, so provisioning refuses before success.
        self.stacks();self.model.parent.chmod(0o775)
        try:
            # Held before the first write since thread 43's walk: the parent is
            # the chain's first link, so nothing is made.
            with self.assertRaisesRegex(RuntimeError,'model-chain-custody'):self.provision()
            self.assertTrue(self.untouched())
        finally:self.model.parent.chmod(0o700)

    def test_inventory_roots_pin_the_served_set(self):
        # #683 finding 31: the inventory walks tb_payload.STACK_ROOTS, so the
        # served set is derived here from the payload's own output, the
        # LD_LIBRARY_PATH it exports and the binaries it configures, and pinned
        # to that constant. A directory served from outside it fails here.
        self.stacks();self.provision()
        stack=self.root/'stacks/B1';served=set()
        for entry in payload.environment('B1')['LD_LIBRARY_PATH'].split(':'):
            served.add(str(Path(entry).relative_to(stack)))
        for name in ['worker-binary','spu-binary','gate-binary']:
            served.add(str(Path((self.root/'config/B1'/name).read_text().strip()).relative_to(stack).parent))
        self.assertTrue(served,served)
        self.assertLessEqual(served,set(payload.STACK_ROOTS),f'served outside the inventoried roots: {served-set(payload.STACK_ROOTS)}')
        self.assertIs(sections.STACK_ROOTS,payload.STACK_ROOTS)

    def test_installed_copy_holds_exactly_the_reviewed_bytes(self):
        self.stacks();self.provision();payload.installed(self.plan,'d'*64)
        installed=self.root/'stacks/B1/bin/pyworker'
        extra=self.root/'stacks/B1/engine-lib/extra.so';extra.write_text('unreviewed')
        with self.assertRaisesRegex(RuntimeError,'installed-stack-coverage'):payload.installed(self.plan,'d'*64)
        extra.unlink();twin=self.base/'twin';twin.write_text('stub')
        installed.unlink();installed.symlink_to(twin)
        with self.assertRaisesRegex(RuntimeError,'installed-no-symlinks'):payload.installed(self.plan,'d'*64)
        installed.unlink();installed.write_text('stub');payload.installed(self.plan,'d'*64)

    def test_provision_holds_every_precondition_before_the_first_write(self):
        # #683 thread 43 and the walk it asked for: groupadd's, the final
        # chown's and the snapshot's preconditions were asserted only after
        # ROOT was made, so a failure left ROOT standing and every retry
        # refusing under fresh-install-root. Each refuses by name with
        # nothing written.
        self.stacks()
        self.groups_present={self.plan['operator'],'weaver-bravo'}
        with self.assertRaisesRegex(RuntimeError,'no-bravo-group'):self.provision()
        self.assertTrue(self.untouched())
        self.groups_present=set()
        with self.assertRaisesRegex(RuntimeError,'operator-group'):self.provision()
        self.assertTrue(self.untouched())
        self.groups_present={self.plan['operator']}
        deep=self.base/'ancestor'/'models';deep.mkdir(parents=True);(self.base/'ancestor').chmod(0o775)
        with patch.object(payload,'MODEL',deep/'model'),self.assertRaisesRegex(RuntimeError,'model-chain-custody'):self.provision()
        self.assertTrue(self.untouched());self.assertFalse((deep/'model').exists())
        (self.base/'ancestor').chmod(0o755)
        # #683 thread 47: ROOT's own ancestry, held before provision writes. ROOT
        # stands as `approve` left it (679.5), its parent opened to the group.
        nested=self.base/'under'/'root';(nested/'approval').mkdir(parents=True);nested.chmod(0o755);nested.parent.chmod(0o775)
        with patch.object(payload,'ROOT',nested),self.assertRaisesRegex(RuntimeError,'root-chain-custody'):self.provision()
        self.assertEqual(sorted(os.listdir(nested)),['approval']);self.assertFalse(self.model.exists())
        nested.parent.chmod(0o755)
        # What new-model-custody alone still catches: the written file itself,
        # here a second name given to it during the write.
        real=payload.snapshot
        def linked(source,digest,destination):
            real(source,digest,destination);os.link(destination,destination.with_name('twin'));return destination
        with patch('tb_payload.snapshot',side_effect=linked),self.assertRaisesRegex(RuntimeError,'new-model-custody'):self.provision()

    def test_provision_preconditions_before_mutation(self):
        self.stacks()
        for fault in ['weights','existing-model','libraries','coverage']:
            with self.subTest(fault=fault):
                changed=copy.deepcopy(self.plan)
                if fault=='weights':changed['tuple']['weights_sha256']='bad'
                if fault=='existing-model':self.model.write_text('bad')
                if fault=='libraries':(Path(changed['stacks']['B1'])/'cuda-lib').rmdir()
                if fault=='coverage':changed['files']={}
                with patch.object(self,'plan',changed),self.assertRaises(RuntimeError):self.provision()
                self.assertTrue(self.untouched())
                self.model.unlink(missing_ok=True)
                (Path(self.plan['stacks']['B1'])/'cuda-lib').mkdir(exist_ok=True)
        with patch('tb_payload.pwd.getpwnam',return_value=self.user),self.assertRaisesRegex(RuntimeError,'no-bravo-account'):payload.provision(self.plan,'d'*64)

    def test_provision_takes_only_the_root_approve_left(self):
        # 679.5: fresh means the root holds its approvals and nothing else.
        # Anything beside them is custody provision did not take, and a root
        # approve never made, or one opened to the group, is no root at all.
        self.stacks()
        for extra in ['stacks','config','stray']:
            with self.subTest(extra=extra):
                (self.root/extra).mkdir()
                with self.assertRaisesRegex(RuntimeError,'fresh-install-root'):self.provision()
                self.assertEqual(sorted(os.listdir(self.root)),sorted(['approval',extra]))
                (self.root/extra).rmdir()
        (self.root/'loose').write_text('x')
        with self.assertRaisesRegex(RuntimeError,'fresh-install-root'):self.provision()
        (self.root/'loose').unlink();(self.root/'approval').rmdir()
        with self.assertRaisesRegex(RuntimeError,'fresh-install-root'):self.provision()
        self.assertEqual(os.listdir(self.root),[])
        (self.root/'approval').mkdir();os.chmod(self.root,0o775)
        with self.assertRaisesRegex(RuntimeError,'fresh-install-root'):self.provision()
        self.assertTrue(self.untouched())
        os.chmod(self.root,0o755);self.provision()

    def setup_load(self):
        self.root.mkdir(exist_ok=True);(self.root/'sinks').mkdir();(self.root/'agents/B1').mkdir(parents=True)
        return dict(id='job',kind='free',stack='B1',seed=7)

    def invoke_load(self,job,gpu=None,ldd=None,loader_rc=0,door=True,artifact=True,on_run=None,declared=None,source_sink=None):
        default_gpu=golden.NVIDIA_SMI.strip()
        default_ldd=ldd_output(self.base,f'{self.root}/stacks/B1/cuda-lib')
        def run(argv,**kwargs):
            if on_run:on_run(argv)
            if 'nvidia-smi' in argv[0]:return subprocess.CompletedProcess(argv,0,default_gpu if gpu is None else gpu,'')
            if 'ldd' in argv[0]:return subprocess.CompletedProcess(argv,0,default_ldd if ldd is None else ldd,'')
            if 'derive' in argv:
                Path(argv[-1]).write_text(derived(self.model if artifact else golden.DERIVE_ARTIFACT,argv[argv.index('--sink')+1],self.plan['tuple'],**(declared or {})))
            return subprocess.CompletedProcess(argv,0,'','')
        sockets=[]
        def loader(*args,**kw):
            import socket
            if door:
                state=self.root/'sinks/job/state';state.mkdir()
                sock=socket.socket(socket.AF_UNIX);sock.bind(str(state/'preload.sock'));sockets.append(sock)
            return SimpleNamespace(poll=lambda:None if door else 1,wait=lambda **kw:loader_rc,kill=lambda:None)
        try:
            with patch('tb_payload.m1_unloaded'),patch('tb_payload.answer'),patch('tb_payload.run',side_effect=run),patch('tb_payload.os.chown'),patch('tb_payload.grp.getgrnam',return_value=SimpleNamespace(gr_gid=os.getgid())),patch('tb_payload.subprocess.Popen',side_effect=loader),contextlib.redirect_stdout(io.StringIO()):payload.load(self.plan,job,source_sink)
        finally:
            for sock in sockets:sock.close()

    def test_load_tuple_and_libraries(self):
        job=self.setup_load()
        # The host-resolved case is golden's real capture: B1 has no cuda-lib.
        for gpu,ldd in [(golden.NVIDIA_SMI.strip().replace('0, ','1, ',1),None),(None,golden.LDD_B1_LIBGGML_CUDA.replace('{DEPOSIT}',str(self.base))),(None,ldd_output(self.base,f'{self.root}/stacks/B1/cuda-lib')+'\tlibother.so => not found\n')]:
            with self.assertRaises(RuntimeError):self.invoke_load(job,gpu=gpu,ldd=ldd)
        self.invoke_load(job)
        self.assertIn('seed: 7',(self.root/'agents/B1/bravo.yaml').read_text())

    def test_a_load_whose_sink_stands_refuses_by_name(self):
        # #709 round three's walk: a coordinator dying after root's load and
        # before its receipt leaves the sink standing, and the retried load
        # refuses by name rather than loading the run twice. Perturbation:
        # drop fresh-sink and the retry refuses unnamed, at mkdir.
        job=self.setup_load();self.invoke_load(job)
        declaration=(self.root/'agents/B1/bravo.yaml').read_bytes()
        with self.assertRaisesRegex(RuntimeError,'fresh-sink'):self.invoke_load(job)
        self.assertEqual((self.root/'agents/B1/bravo.yaml').read_bytes(),declaration)

    def test_replay_load_orders_preload_before_wait(self):
        job=self.setup_load();source=self.base/'source';source.write_text(TWO_RUNS)
        job.update(kind='refeed',source_trace=str(source),source_run='r2');self.plan['files'][str(source)]=order.sha(source)
        self.invoke_load(job)
        self.assertTrue((self.root/'sinks/job/load.log').exists())

    def test_replay_refusals(self):
        job=self.setup_load();source=self.base/'source';source.write_text(TWO_RUNS)
        job.update(kind='refeed',source_trace=str(source),source_run='r2');self.plan['files'][str(source)]=order.sha(source)
        for setting in [dict(artifact=False),dict(door=False),dict(loader_rc=1)]:
            with self.assertRaises(RuntimeError):self.invoke_load(job,**setting)
            import shutil
            shutil.rmtree(self.root/'sinks/job');shutil.rmtree(self.root/'snapshots/job')
        self.plan['files'][str(source)]='wrong'
        with self.assertRaisesRegex(RuntimeError,'snapshot-hash'):self.invoke_load(job)
        self.assertEqual(list((self.root/'snapshots/job').iterdir()),[])

    def test_replay_feeds_one_verified_snapshot_of_the_selected_run(self):
        # #683 findings 9 and 10: derive and preload each read their input.
        # Both must receive one root-owned file cut from a single verified
        # read, holding only the named run, whatever happens to the source.
        job=self.setup_load();source=self.base/'source';source.write_text(TWO_RUNS)
        job.update(kind='refeed',source_trace=str(source),source_run='r2');self.plan['files'][str(source)]=order.sha(source)
        seen={}
        def on_run(argv):
            for verb in ['derive','preload']:
                if verb in argv:
                    fed=Path(argv[argv.index(verb)+1]);seen[verb]=(fed,fed.read_bytes())
                    source.write_text(ndjson(event(golden.TURN_CLOSED,run='r2',sequence='98')))
        with swapped_after_hashing({source:ndjson(event(golden.TURN_CLOSED,run='r2',sequence='99')).encode()}):self.invoke_load(job,on_run=on_run)
        selected=''.join(l for l in TWO_RUNS.splitlines(keepends=True) if json.loads(l)['run']=='r2').encode()
        self.assertNotEqual(seen['derive'][0],source)
        self.assertEqual(seen['derive'],seen['preload'])
        self.assertEqual(seen['derive'][1],selected)

    def test_derived_artifact_is_read_as_derive_renders_it(self):
        # #683 finding 13: derive quotes the artifact (golden's real capture).
        # The check parses the value, so the real form passes and a declaration
        # naming another model, or no parseable model, refuses.
        self.assertEqual(payload.declared_artifacts(golden.DERIVE_DECLARATION),[golden.DERIVE_ARTIFACT])
        self.assertEqual(payload.declared_artifacts(derived(self.model,'/sink')),[str(self.model)])
        self.assertEqual(payload.declared_artifacts(f'      artifact: {self.model}\n'),[None])
        job=self.setup_load();source=self.base/'source';source.write_text(TWO_RUNS)
        job.update(kind='refeed',source_trace=str(source),source_run='r2');self.plan['files'][str(source)]=order.sha(source)
        self.invoke_load(job)
        shutil.rmtree(self.root/'sinks/job');shutil.rmtree(self.root/'snapshots/job')
        with self.assertRaisesRegex(RuntimeError,'derived-artifact'):self.invoke_load(job,artifact=False)

    def test_replay_source_must_hold_the_tuple(self):
        # #683 finding 20: derive carries the source run's own seed, identity,
        # context capacity and token cap into the replay, so each must hold the
        # plan's tuple; golden's real W4a declaration, another tuple, refuses.
        job=self.setup_load();source=self.base/'source';source.write_text(TWO_RUNS)
        job.update(kind='refeed',source_trace=str(source),source_run='r2');self.plan['files'][str(source)]=order.sha(source)
        faults=[{'seed':999},{'context-capacity':32768},{'max-tokens-per-turn':4096},
                {'identity':[{'role':'system','content':[{'type':'text','text':'another identity'}]}]}]
        for fault in faults:
            with self.subTest(fault=list(fault)[0]):
                try:
                    with self.assertRaisesRegex(RuntimeError,'derived-tuple'):self.invoke_load(job,declared=fault)
                finally:shutil.rmtree(self.root/'sinks/job',ignore_errors=True);shutil.rmtree(self.root/'snapshots/job',ignore_errors=True)
        # A local source holds its own free job's seed, not merely a tuple seed.
        free=next(j for j in self.plan['arms'][0]['jobs'] if j['kind']=='free')
        (self.root/'sinks'/free['id']).mkdir();(self.root/'sinks'/free['id']/'trace.ndjson').write_text(TWO_RUNS)
        local=dict(id='job',kind='refeed',stack='B1',source_job=free['id'])
        recorded=(str(len(TWO_RUNS.encode())),hashlib.sha256(TWO_RUNS.encode()).hexdigest())
        other=next(s for s in self.plan['tuple']['seeds'] if s!=free['seed'])
        with self.assertRaisesRegex(RuntimeError,'derived-tuple'):self.invoke_load(local,declared={'seed':other},source_sink=recorded)
        shutil.rmtree(self.root/'sinks/job');shutil.rmtree(self.root/'snapshots/job')
        self.invoke_load(local,declared={'seed':free['seed']},source_sink=recorded)
        self.assertFalse(payload.holds_tuple(self.plan,job,derived(self.model,'/sink')))

    def test_replay_refuses_a_run_the_trace_does_not_hold(self):
        job=self.setup_load();source=self.base/'source';source.write_text(TWO_RUNS)
        job.update(kind='refeed',source_trace=str(source),source_run='r9');self.plan['files'][str(source)]=order.sha(source)
        with self.assertRaisesRegex(RuntimeError,'source-run-selected'):self.invoke_load(job)

    def test_provision_serves_only_verified_model_bytes(self):
        # #683 finding 8: model bytes changed after the model-source check are
        # refused in the installed copy, which is removed, before success.
        self.stacks();src=Path(self.plan['model_source'])
        with swapped_after_hashing({src:b'unreviewed weights'}),self.assertRaisesRegex(RuntimeError,'snapshot-hash'):self.provision()
        self.assertFalse(self.model.exists())

    def test_payload_entry_checks(self):
        p=copy.deepcopy(self.plan);p['install_root']=str(self.root);p['files']={}
        def invoke(p,uid=0,sudo='1000',digest=None,step='provision',code=None):
            pointer=self.stand(p)
            with self.as_root(code),patch('sys.argv',['payload',step,digest or pointer]),patch('tb_payload.os.geteuid',return_value=uid),patch.dict(os.environ,{'SUDO_UID':sudo}),patch('tb_payload.pwd.getpwnam',return_value=self.user),patch('tb_payload.provision'),patch('tb_payload.installed'),patch('tb_payload.answer'),patch('tb_payload.m1_reading',return_value=golden_reading()),contextlib.redirect_stdout(io.StringIO()):payload.main()
        invoke(p)
        for change,kw in [(lambda p:None,dict(uid=1000)),(lambda p:None,dict(digest='wrong')),(lambda p:None,dict(digest='0'*64)),
                          (lambda p:p.update(agent='karl'),{}),(lambda p:None,dict(sudo='9')),(lambda p:p['files'].update({str(self.planpath):'bad'}),{}),(lambda p:None,dict(step='unload:missing'))]:
            bad=copy.deepcopy(p);change(bad)
            with self.assertRaises(RuntimeError):invoke(bad,**kw)
        invoke(p,step='unload:B1-s7-n1')
        with self.assertRaisesRegex(RuntimeError,'known-step'):invoke(p,step='frob:B1-s7-n1')

    def test_payload_parses_the_snapshot_it_verified(self):
        # #683 finding 2: sudo verifies one snapshot. A plan swapped on disk after
        # the digest check must not be what provision receives. Since 679.5 the
        # plan root reads is the approval's root-owned copy, so the swap lands
        # on that copy, the moment its bytes are hashed.
        p=copy.deepcopy(self.plan);p['install_root']=str(self.root);p['files']={}
        pointer=self.stand(p);copy_path=self.root/'approval'/pointer/'plan.json'
        original=copy_path.read_bytes();expected=hashlib.sha256(original).hexdigest()
        altered=dict(p,note='swapped after hashing')
        real=payload.hashlib.sha256;swapped=[]
        class Hooked:
            def __init__(s,*a):s.h=real(*a);s.seen=b''.join(a)
            def update(s,b):s.h.update(b);s.seen+=b
            def hexdigest(s):
                r=s.h.hexdigest()
                if s.seen==original and not swapped:swapped.append(1);copy_path.write_text(json.dumps(altered))
                return r
        with self.as_root(),patch('sys.argv',['payload','provision',pointer]),patch('tb_payload.os.geteuid',return_value=0),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_payload.pwd.getpwnam',return_value=self.user),patch('tb_payload.provision') as provision,patch('tb_payload.hashlib.sha256',side_effect=Hooked),contextlib.redirect_stdout(io.StringIO()):payload.main()
        self.assertEqual(swapped,[1])
        self.assertEqual(provision.call_args.args,(p,expected))


class DriverTests(unittest.TestCase):
    save = Fixture.save
    publish = Fixture.publish

    def setUp(self):
        Fixture.setUp(self)
        self.plan['install_root']=str(self.root/'installed')
        self.plan['deposit']=str(self.root/'deposit');Path(self.plan['deposit']).mkdir()
        self.free=ReadingTests().rec()
        self.free.update(emission='essay',declared_seed=7,weights_hash=self.plan['tuple']['weights_sha256'],input_tokens=10)
        self.probe=SimpleNamespace(base=SimpleNamespace(gate_turn=lambda *a,**kw:dict(json.loads(golden.GATE_ANSWERED),run='r')),
                                   ESSAY_PROMPT='fixed',extract_run=lambda rows:copy.deepcopy(self.free),
                                   measured_events=lambda rows,run:rows,reading_two=lambda a,b:dict(positions_compared=1),
                                   reading_one=lambda a,b:{},first_divergence=lambda a,b:0)
        # The interlock the driver reads at each close: m1 absent, as golden's
        # real capture of this box reads, so no test depends on the host's m1.
        p=patch('tb_driver.m1_reading',return_value=golden_reading());p.start();self.addCleanup(p.stop)

    def receipts(self):
        """The measure receipts the coordinator would hand back, one per result
        in the deposit, each at the digest of the file as it stands."""
        found={}
        for part,name in [('runs','run.json'),('refeeds','refeed.json')]:
            for directory in sorted((Path(self.plan['deposit'])/part).glob('*')):
                f=directory/name
                if f.is_file():found[f'measure:{directory.name}']=dict(status='SUCCESS',path=str(f),sha256=order.sha(f))
        return found

    def job(self,kind='free'):
        return dict(id='job',kind=kind,stack='B1',seed=7,source_trace=str(self.source),source_run='r')

    def close(self,replay=False):
        # A replay run carries its one measurement and its close, as a real one does.
        if replay:return run_events('r',event(golden.REPLAY_CLOSED_CERTIFIED,run='r'))
        return run_events('r',event(golden.TURN_CLOSED,run='r'))

    def cleanup_job(self):
        import shutil
        for part in ['runs','refeeds']:
            shutil.rmtree(Path(self.plan['deposit'])/part,ignore_errors=True)

    def test_free_measurement_refusals(self):
        j=self.job()
        with patch('tb_driver.until_closed',return_value=closed_bytes(self.close())):
            result,_=driver.measure(self.plan,j,self.probe,{})
            self.assertEqual(json.loads(result.read_text())['run'],'r')
        self.cleanup_job()
        for fault in ['answer','single-turn','seed','weights']:
            old=copy.deepcopy(self.free)
            if fault=='seed':self.free['declared_seed']=8
            if fault=='weights':self.free['weights_hash']='bad'
            # A run with everything but its measurement, so single-turn is the guard that refuses.
            rows=[e for e in self.close() if e['kind']!='model.measurement'] if fault=='single-turn' else self.close()
            gate=self.probe.base.gate_turn
            if fault=='answer':self.probe.base.gate_turn=lambda *a,**k:json.loads(golden.GATE_REFUSED)
            with patch('tb_driver.until_closed',return_value=closed_bytes(rows)),self.assertRaisesRegex(order.Refused,'single-turn' if fault=='single-turn' else '.'):driver.measure(self.plan,j,self.probe,{})
            self.probe.base.gate_turn=gate;self.free=old;self.cleanup_job()

    def test_refeed_requires_close_measurement_and_source(self):
        j=self.job('refeed')
        self.source.write_text(trace('r'));self.plan['files'][str(self.source)]=order.sha(self.source)
        with patch('tb_driver.until_closed',return_value=closed_bytes(self.close(True))):
            result,_=driver.measure(self.plan,j,self.probe,{})
            self.assertTrue(json.loads(result.read_text())['exact'])
        self.cleanup_job()
        for fault in ['close','outcome','measurement','double-measurement','source-hash','source-measurement']:
            rows=self.close(True)
            if fault=='close':rows=rows+[rows[-1]]  # two closes, one measurement
            # #683 thread 37: two measurements in the replay run are one
            # ambiguous record, refused like none.
            if fault=='double-measurement':rows=[event(golden.MODEL_MEASUREMENT,run='r',sequence='9')]+rows
            if fault=='outcome':rows[-1]['payload']['outcome']=dict(kind='abandoned',reason=dict(kind='replay_ask_unanswered'))
            if fault=='source-hash':self.plan['files'][str(self.source)]='bad'
            if fault=='source-measurement':self.source.write_text(ndjson(*[e for e in run_events('r') if e['kind']!='model.measurement'],event(golden.TURN_CLOSED,run='r')));self.plan['files'][str(self.source)]=order.sha(self.source)
            self.probe.measured_events=(lambda rows,run:None) if fault=='measurement' else (lambda rows,run:rows)
            with patch('tb_driver.until_closed',return_value=closed_bytes(rows)),self.assertRaises((order.Refused,KeyError)):driver.measure(self.plan,j,self.probe,{})
            self.cleanup_job();self.source.write_text(trace('r'));self.plan['files'][str(self.source)]=order.sha(self.source)

    def test_assess_control_pass_and_falsifiers(self):
        arm=self.plan['arms'][0]
        for j in arm['jobs']:
            directory=Path(self.plan['deposit'])/('runs' if j['kind']=='free' else 'refeeds')/j['id'];directory.mkdir(parents=True)
            r=dict(self.free,seed=j.get('seed')) if j['kind']=='free' else dict(exact=True,replay_outcome='certified')
            order.atomic(directory/('run.json' if j['kind']=='free' else 'refeed.json'),r)
        result=driver.assess(self.plan,arm,self.probe,self.receipts())
        self.assertTrue(json.loads(result.read_text())['control_passed'])
        j=arm['jobs'][-1];p=Path(self.plan['deposit'])/'refeeds'/j['id']/'refeed.json'
        order.atomic(p,dict(exact=False,replay_outcome='diverged'))
        with self.assertRaises(order.Refused):driver.assess(self.plan,arm,self.probe,self.receipts())
        order.atomic(p,dict(exact=True,replay_outcome='certified'))
        self.probe.first_divergence=lambda a,b:24
        with self.assertRaises(order.Refused):driver.assess(self.plan,arm,self.probe,self.receipts())
        shorter=copy.deepcopy(arm);shorter['jobs'].pop(0)
        with self.assertRaises(order.Refused):driver.assess(self.plan,shorter,self.probe,self.receipts())

    def test_changed_seeds_compare_one_run_per_distinct_seed(self):
        # #683 finding 16: the validator constrains only the multiset of free
        # seeds, so a valid plan may put both runs of one seed first. Each seed
        # has its own tokens here and the real first_divergence contract (None
        # only for identical lists), so a same-seed pair would falsify TB0.
        arm=copy.deepcopy(self.plan['arms'][0]);free=sorted((j for j in arm['jobs'] if j['kind']=='free'),key=lambda j:j['seed'])
        arm['jobs']=free+[j for j in arm['jobs'] if j['kind']=='refeed']
        order.validate_plan(dict(self.plan,install_root='/var/lib/weaver-tb',arms=[arm]+self.plan['arms'][1:]))
        for j in arm['jobs']:
            directory=Path(self.plan['deposit'])/('runs' if j['kind']=='free' else 'refeeds')/j['id'];directory.mkdir(parents=True)
            r=dict(self.free,seed=j.get('seed'),output_tokens=[j['seed']%1000]) if j['kind']=='free' else dict(exact=True,replay_outcome='certified')
            order.atomic(directory/('run.json' if j['kind']=='free' else 'refeed.json'),r)
        self.probe.first_divergence=lambda a,b:None if a==b else next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b)))
        report=json.loads(driver.assess(self.plan,arm,self.probe,self.receipts()).read_text())
        seeds=self.plan['tuple']['seeds']
        self.assertEqual({(c['a'],c['b']) for c in report['changed_seeds']},{(a,b) for i,a in enumerate(seeds) for b in seeds[i+1:]})
        self.assertTrue(report['changed_seed_prediction'])

    def test_driver_settles_before_next_load_and_stops_falsifier(self):
        # Small schedule exercises the blocking orchestration; full count and
        # source schedule are independently guarded by validate_plan tests.
        arm=dict(name='TB0',jobs=[dict(id='a',kind='free',seed=7),dict(id='b',kind='free',seed=7),dict(id='c',kind='refeed')])
        self.plan['arms']=[arm]
        state=dict(approval='a'*64);seen=[]
        # The coordinator answers each wait and record with the receipts as
        # they stand, which is what the driver reads its evidence against.
        def coding(step,path,sink=None):seen.append(step);return self.receipts()
        def wait(step):seen.append('wait:'+step);return self.receipts()
        # The approval the coordinator verified names the plan's digest (679.5).
        o=SimpleNamespace(read=lambda:state,approved=lambda s:self.plan,coding=coding,wait=wait,
                          approval=dict(plan=dict(sha256='recorded-at-approval')))
        def measure(plan,job,probe,receipts):
            p=Path(plan['deposit'])/'runs'/job['id']/'run.json';p.parent.mkdir(parents=True,exist_ok=True)
            order.atomic(p,dict(self.free,exact=False,replay_outcome='diverged'));return p,None
        with patch('tb_driver.readers',return_value=self.probe),patch('tb_driver.notice'),patch('tb_driver.measure',side_effect=measure),self.assertRaises(order.Refused):driver.drive(o,'TB0')
        self.assertIn('settle:b',seen);self.assertIn('wait:settle:c',seen);self.assertNotIn('settle:c',seen)
        # The start record names the digest the approval record holds, not a re-hash.
        self.assertEqual(json.loads((Path(self.plan['deposit'])/'TB0-start.json').read_text())['plan'],'recorded-at-approval')
        with patch('tb_driver.readers',return_value=self.probe),self.assertRaises(order.Refused):driver.drive(o,'TB0')
        (Path(self.plan['deposit'])/'TB0-start.json').unlink()
        def bad_pair(plan,job,probe,receipts):
            p,_=measure(plan,job,probe,receipts)
            if job['id']=='b':
                r=json.loads(p.read_text());r['emission']='changed';order.atomic(p,r)
            return p,None
        with patch('tb_driver.readers',return_value=self.probe),patch('tb_driver.notice'),patch('tb_driver.measure',side_effect=bad_pair),self.assertRaisesRegex(order.Refused,'pair-falsifier'):driver.drive(o,'TB0')

    def test_reader_hash_and_no_cached_code(self):
        root=self.root/'instrument'
        for parent,file,content in [('cross-precision-repro','confirm_cells.py','VALUE=1'),('weaver-probe','weaver_probe.py','VALUE=2')]:
            p=root/parent/file;p.parent.mkdir(parents=True);p.write_text(content);self.plan['files'][str(p)]=order.sha(p)
        self.plan['instrument']=str(root)
        self.assertEqual(driver.readers(self.plan).VALUE,2)
        (root/'weaver-probe/weaver_probe.py').write_text('VALUE=3')
        with self.assertRaises(order.Refused):driver.readers(self.plan)

    def test_refeed_requires_the_tuple_weights_on_both_sides(self):
        # #683 finding 11: a reviewed trace from other weights, or a replay
        # that ran them, must not be read as a device effect.
        j=self.job('refeed')
        self.source.write_text(trace('r'));self.plan['files'][str(self.source)]=order.sha(self.source)
        for side in ['source','replay']:
            with self.subTest(side=side):
                other=dict(copy.deepcopy(self.free),weights_hash='f'*64)
                self.probe.extract_run=(lambda rows,side=side,other=other:copy.deepcopy(other) if (side=='replay')==any(e['kind']=='replay.closed' for e in rows) else copy.deepcopy(self.free))
                try:
                    with patch('tb_driver.until_closed',return_value=closed_bytes(self.close(True))),self.assertRaisesRegex(order.Refused,f'{side}-weights-held'):driver.measure(self.plan,j,self.probe,{})
                finally:self.cleanup_job()

    def test_a_second_field_event_for_a_position_refuses_on_every_path(self):
        # #683 thread 41: extract_run keeps the last field event per position,
        # so a duplicate would silently decide the readings. The raw selected
        # events refuse it before extraction on the free, source and replay
        # paths, by a name each.
        dup=[event(golden.MODEL_FIELD,run='r'),event(golden.MODEL_FIELD,run='r',sequence='42')]
        j=self.job('free')
        with patch('tb_driver.until_closed',return_value=closed_bytes(dup+self.close())),self.assertRaisesRegex(order.Refused,'field-duplicated'):driver.measure(self.plan,j,self.probe,{})
        self.cleanup_job()
        j=self.job('refeed')
        self.source.write_text(trace('r',*dup));self.plan['files'][str(self.source)]=order.sha(self.source)
        with self.assertRaisesRegex(order.Refused,'field-duplicated'):driver.source_record(self.plan,j,self.probe,{})
        self.source.write_text(trace('r'));self.plan['files'][str(self.source)]=order.sha(self.source)
        with patch('tb_driver.until_closed',return_value=closed_bytes(dup+self.close(True))),self.assertRaisesRegex(order.Refused,'field-duplicated'):driver.measure(self.plan,j,self.probe,{})
        self.cleanup_job()
        # A position beyond the measurement's output length refuses the same way.
        beyond=[event(golden.MODEL_FIELD,run='r',payload=dict(json.loads(golden.MODEL_FIELD)['payload'],position=10**6))]
        with patch('tb_driver.until_closed',return_value=closed_bytes(beyond+self.close(True))),self.assertRaisesRegex(order.Refused,'field-beyond-output'):driver.measure(self.plan,j,self.probe,{})
        self.cleanup_job()
        # One event per position, within the output length, passes.
        one=[event(golden.MODEL_FIELD,run='r')]
        with patch('tb_driver.until_closed',return_value=closed_bytes(one+self.close(True))):driver.measure(self.plan,j,self.probe,{})

    def test_each_singular_kind_exactly_once_on_every_path(self):
        # #683 threads 41 and 42, as a class: the pinned extractor keeps the
        # last event of each kind, so a run's selected events must carry each
        # singular kind exactly once, on the free, source and replay paths, and
        # the refusal names the kind and the fault.
        self.assertEqual(set(driver.SINGULAR_KINDS)|{'model.measurement'},{k for k,v in golden.EXTRACT_RUN_SOURCES.items() if k!='model.field'})
        lines={'model.request':golden.MODEL_REQUEST,'model.output':golden.MODEL_OUTPUT}
        for kind,name in [('model.request','request'),('model.output','output')]:
            for fault in ['absent','duplicated']:
                def rows(close):
                    base=[e for e in run_events('r') if e['kind']!=kind] if fault=='absent' else run_events('r',event(lines[kind],run='r',sequence='77'))
                    return base+[close]
                with self.subTest(kind=kind,fault=fault,path='free'):
                    with patch('tb_driver.until_closed',return_value=closed_bytes(rows(event(golden.TURN_CLOSED,run='r')))),self.assertRaisesRegex(order.Refused,f'{name}-{fault}'):driver.measure(self.plan,self.job('free'),self.probe,{})
                    self.cleanup_job()
                with self.subTest(kind=kind,fault=fault,path='source'):
                    j=self.job('refeed');self.source.write_text(ndjson(*rows(event(golden.TURN_CLOSED,run='r'))));self.plan['files'][str(self.source)]=order.sha(self.source)
                    with self.assertRaisesRegex(order.Refused,f'{name}-{fault}'):driver.source_record(self.plan,j,self.probe,{})
                    self.source.write_text(trace('r'));self.plan['files'][str(self.source)]=order.sha(self.source)
                with self.subTest(kind=kind,fault=fault,path='replay'):
                    with patch('tb_driver.until_closed',return_value=closed_bytes(rows(event(golden.REPLAY_CLOSED_CERTIFIED,run='r')))),self.assertRaisesRegex(order.Refused,f'{name}-{fault}'):driver.measure(self.plan,self.job('refeed'),self.probe,{})
                    self.cleanup_job()

    def test_exact_holds_the_input_length(self):
        # #683 thread 46: the input length is part of exactness for pairs too.
        t=prepare.template(Path('/deposit'),'todd',1000)['tuple']
        a=dict(copy.deepcopy(self.free),input_tokens=10);b=dict(copy.deepcopy(a),input_tokens=11)
        self.assertTrue(driver.exact(t,a,copy.deepcopy(a)));self.assertFalse(driver.exact(t,a,b))

    def test_refeed_holds_the_input_and_refuses_a_divergence_inside_it(self):
        # #683 thread 46: a replay that tokenized the prompt differently ran
        # another stimulus. Source and replay must hold one input length, and
        # a token-path divergence inside the input refuses rather than being
        # converted to an output ordinal and read as a device effect.
        j=self.job('refeed')
        other=dict(copy.deepcopy(self.free),input_tokens=self.free['input_tokens']+2)
        self.probe.extract_run=lambda rows:copy.deepcopy(other) if any(e['kind']=='replay.closed' for e in rows) else copy.deepcopy(self.free)
        try:
            with patch('tb_driver.until_closed',return_value=closed_bytes(self.close(True))),self.assertRaisesRegex(order.Refused,'input-held'):driver.measure(self.plan,j,self.probe,{})
        finally:self.cleanup_job()
        self.probe.extract_run=lambda rows:copy.deepcopy(self.free)
        inside=run_events('r',event(golden.REPLAY_CLOSED_CERTIFIED,run='r',payload=dict(outcome=dict(kind='diverged',divergence=dict(kind='token_path',position=self.free['input_tokens']-1,recorded=1,recomputed=2)))))
        try:
            with patch('tb_driver.until_closed',return_value=closed_bytes(inside)),self.assertRaisesRegex(order.Refused,'divergence-in-input'):driver.measure(self.plan,j,self.probe,{})
        finally:self.cleanup_job()
        # At the boundary the position is the first output token, ordinal 0.
        at=run_events('r',event(golden.REPLAY_CLOSED_CERTIFIED,run='r',payload=dict(outcome=dict(kind='diverged',divergence=dict(kind='token_path',position=self.free['input_tokens'],recorded=1,recomputed=2)))))
        with patch('tb_driver.until_closed',return_value=closed_bytes(at)):result,_=driver.measure(self.plan,j,self.probe,{})
        self.assertEqual(json.loads(result.read_text())['replay_divergence_ordinal'],0)

    def test_refeed_requires_the_source_seed_on_both_sides(self):
        # #683 finding 21: a replay that ran another seed, or a source outside
        # the tuple's seeds, must not be read as a device or kernel effect.
        j=self.job('refeed')
        self.source.write_text(trace('r'));self.plan['files'][str(self.source)]=order.sha(self.source)
        held=self.plan['tuple']['seeds'][0];other=self.plan['tuple']['seeds'][1]
        for guard,source_seed,replay_seed in [('source-seed-held',424242,424242),('replay-seed-held',held,other)]:
            with self.subTest(guard=guard):
                def extract(rows,s=source_seed,r=replay_seed):
                    replay=any(e['kind']=='replay.closed' for e in rows)
                    return dict(copy.deepcopy(self.free),declared_seed=r if replay else s)
                self.probe.extract_run=extract
                try:
                    with patch('tb_driver.until_closed',return_value=closed_bytes(self.close(True))),self.assertRaisesRegex(order.Refused,guard):driver.measure(self.plan,j,self.probe,{})
                finally:self.cleanup_job()
        self.probe.extract_run=lambda rows:dict(copy.deepcopy(self.free),declared_seed=held)
        with patch('tb_driver.until_closed',return_value=closed_bytes(self.close(True))):driver.measure(self.plan,j,self.probe,{})

    def test_readers_compile_the_bytes_they_hashed(self):
        # Codex pass 4 class, driver side: a reader rewritten after its hash
        # check must not be what runs.
        root=self.root/'instrument';files={}
        for parent,file,content in [('cross-precision-repro','confirm_cells.py','VALUE=1'),('weaver-probe','weaver_probe.py','VALUE=2')]:
            p=root/parent/file;p.parent.mkdir(parents=True);p.write_text(content);self.plan['files'][str(p)]=order.sha(p);files[p]=b'VALUE=99'
        self.plan['instrument']=str(root)
        with swapped_after_hashing(files) as pending:module=driver.readers(self.plan)
        self.assertEqual(pending,{})
        self.assertEqual((module.VALUE,sys.modules['confirm_cells'].VALUE),(2,1))

    def test_source_record_parses_the_bytes_it_hashed(self):
        j=self.job('refeed');seen=[]
        self.source.write_text(trace('r'));self.plan['files'][str(self.source)]=order.sha(self.source)
        self.probe.extract_run=lambda rows:seen.append(rows) or copy.deepcopy(self.free)
        with swapped_after_hashing({self.source:trace('r',sequence='99').encode()}):driver.source_record(self.plan,j,self.probe,{})
        self.assertEqual(seen,[run_events('r')])

    def test_entry_refuses_root(self):
        with patch('sys.argv',['driver','--state',str(self.statepath),'TB0']),patch('tb_driver.os.geteuid',return_value=0),patch('tb_driver.drive'),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(driver.main(),1)
        self.assertTrue(self.o.read()['halt'])



class HoldLiftTests(unittest.TestCase):
    """#679 items 1, 2 and 6, the probe's hold-lift parts that needed no ruling:
    a local source sink held to the digest recorded at its run's close, the
    driver's evidence read once against the coordinator's receipts, and the
    m1 interlock read again at the measurement's close and at the unload."""
    save=Fixture.save
    publish=Fixture.publish
    due=Fixture.due

    def setUp(self):
        Fixture.setUp(self)

    # 679.1: the sink recorded at the producing run's close, handed to root.

    def test_a_local_refeed_load_carries_its_source_sinks_recorded_digest(self):
        # Perturbation: remove source-sink-recorded and the unrecorded load is
        # handed to root with nothing to hold the sink to.
        source='B1-s451234785645-n1';load='load:own-B1-s451234785645-n1'
        self.due(load);seen=[]
        def runner(s,step,log,*sink):seen.append(sink);log.write_text('SUCCESS: '+step+'\n');return 0
        with self.assertRaisesRegex(order.Refused,'source-sink-recorded'),contextlib.redirect_stdout(io.StringIO()):self.o.operator(runner=runner)
        self.assertEqual(seen,[])
        sink=dict(path=str(Path(self.plan['install_root'])/'sinks'/source/'trace.ndjson'),length=512,sha256='a'*64)
        # The measure receipt's evidence is the run's result, which recorded
        # the sink at the close: the state's copy is held to it.
        result=self.root/'run.json';order.atomic(result,dict(name=source,sink=sink))
        def record(state_copy,evidence=result):
            self.state['done'][f'measure:{source}']=dict(status='SUCCESS',path=str(evidence),sha256=order.sha(evidence),sink=state_copy,approval=self.state['approval'])
            self.state['halt']=None;self.save()
        # Perturbation: drop the hex check and "g"*64 reaches root.
        for fault in [dict(sink,path='/elsewhere/trace.ndjson'),dict(sink,length=0),dict(sink,length='512'),dict(sink,sha256='short'),
                      dict(sink,sha256='g'*64),dict(sink,sha256='A'*64)]:
            record(fault)
            with self.assertRaisesRegex(order.Refused,'source-sink-recorded'),contextlib.redirect_stdout(io.StringIO()):self.o.operator(runner=runner)
        record(sink)
        with contextlib.redirect_stdout(io.StringIO()):self.o.operator(runner=runner)
        self.assertEqual(seen,[('512','a'*64)])

    def test_the_states_sink_copy_is_held_to_the_verified_result(self):
        # #690 C2.11, #693's fourth pass: a state edited between the measure
        # and the load cannot hand root another prefix. Perturbation: drop the
        # comparison with the verified result and the substituted copy, well
        # formed and at the right path, reaches root.
        source='B1-s451234785645-n1';load='load:own-B1-s451234785645-n1'
        self.due(load);seen=[]
        def runner(s,step,log,*sink):seen.append(sink);log.write_text('SUCCESS: '+step+'\n');return 0
        sink=dict(path=str(Path(self.plan['install_root'])/'sinks'/source/'trace.ndjson'),length=512,sha256='a'*64)
        result=self.root/'run.json';order.atomic(result,dict(name=source,sink=sink))
        other=dict(sink,length=640,sha256='b'*64)
        # #695: Python equality reads 512.0 as 512, so the result's record and
        # the state's copy could hold different JSON facts and compare equal.
        # Perturbation: compare them with == again and this reaches root.
        with self.subTest('the result records 512.0 and the state 512'):
            order.atomic(result,dict(name=source,sink=dict(sink,length=512.0)))
            self.state['done'][f'measure:{source}']=dict(status='SUCCESS',path=str(result),sha256=order.sha(result),sink=sink,approval=self.state['approval'])
            self.state['halt']=None;self.save()
            with self.assertRaisesRegex(order.Refused,'source-sink-recorded'),contextlib.redirect_stdout(io.StringIO()):self.o.operator(runner=runner)
        with self.subTest('the state copy differs from the result'):
            order.atomic(result,dict(name=source,sink=sink))
            self.state['done'][f'measure:{source}']=dict(status='SUCCESS',path=str(result),sha256=order.sha(result),sink=other,approval=self.state['approval'])
            self.state['halt']=None;self.save()
            with self.assertRaisesRegex(order.Refused,'source-sink-recorded'),contextlib.redirect_stdout(io.StringIO()):self.o.operator(runner=runner)
        # The result's bytes change between previous()'s check and the read
        # source_sink() makes, its sink field still the state's copy: only the
        # digest gate can refuse it. Perturbation: parse the result whatever
        # its bytes (`if True else None`) and this passes to root.
        with self.subTest('the result changed after previous() read it'):
            order.atomic(result,dict(name=source,sink=sink))
            self.state['done'][f'measure:{source}']=dict(status='SUCCESS',path=str(result),sha256=order.sha(result),sink=sink,approval=self.state['approval'])
            self.state['halt']=None;self.save()
            real=order.Order.previous
            def then_changed(o,s,plan):
                real(o,s,plan)
                with result.open('a') as out:out.write('\n')
            with patch.object(order.Order,'previous',then_changed),self.assertRaisesRegex(order.Refused,'source-sink-recorded'),contextlib.redirect_stdout(io.StringIO()):
                self.o.operator(runner=runner)
        self.assertEqual(seen,[],'root is handed nothing')

    def test_root_is_handed_the_sink_after_the_step(self):
        seen=[]
        def as_root(argv,**kw):seen.append(argv[3:]);return subprocess.CompletedProcess(argv,0)
        with patch('tb_order.subprocess.run',side_effect=as_root):order.payload(self.state,'load:own-x',self.root/'log','512','a'*64)
        self.assertEqual(seen,[['load:own-x',self.state['approval'],'512','a'*64]])

    def test_the_driver_records_the_sink_through_its_runs_close(self):
        # The unload appends after the close, so the recorded prefix stops at
        # the run's turn.closed line and still verifies once the sink has grown.
        # Perturbation: remove sink-closed and a sink with no close for the run
        # records nothing to hold a re-feed to.
        d=DriverTests('test_free_measurement_refusals');d.setUp();self.addCleanup(d.doCleanups)
        closing=d.close();tail=[event(golden.TURN_CLOSED,run='other')]
        with patch('tb_driver.until_closed',return_value=closed_bytes(closing+tail)):
            result,sink=driver.measure(d.plan,d.job(),d.probe,{})
        prefix=closed_bytes(closing)
        self.assertEqual(sink,dict(path=str(Path(d.plan['install_root'])/'sinks/job/trace.ndjson'),length=len(prefix),sha256=hashlib.sha256(prefix).hexdigest()))
        self.assertEqual(json.loads(result.read_text())['sink'],sink)
        d.cleanup_job()
        with patch('tb_driver.until_closed',return_value=closed_bytes([e for e in closing if e['kind']!='turn.closed']+tail)),self.assertRaisesRegex(order.Refused,'sink-closed'):
            driver.measure(d.plan,d.job(),d.probe,{})

    def test_the_payload_freezes_the_recorded_prefix_and_refuses_another(self):
        # Perturbation: remove source-sink-given, or snapshot-hash, and a load
        # with no recorded sink, or a sink changed inside the recorded prefix,
        # feeds the replay anyway.
        pt=PayloadTests('test_replay_source_must_hold_the_tuple');pt.setUp();self.addCleanup(pt.doCleanups)
        free=next(j for j in pt.plan['arms'][0]['jobs'] if j['kind']=='free')
        pt.setup_load();(pt.root/'sinks'/free['id']).mkdir()
        sink=pt.root/'sinks'/free['id']/'trace.ndjson'
        recorded=TWO_RUNS.encode();sink.write_bytes(recorded+ndjson(event(golden.TURN_STARTED,run='unload')).encode())
        local=dict(id='job',kind='refeed',stack='B1',source_job=free['id'])
        fed={}
        def on_run(argv):
            if 'derive' in argv:fed['bytes']=Path(argv[argv.index('derive')+1]).read_bytes()
        pt.invoke_load(local,declared={'seed':free['seed']},on_run=on_run,source_sink=(str(len(recorded)),hashlib.sha256(recorded).hexdigest()))
        self.assertEqual(fed['bytes'],recorded,'the replay is fed the prefix recorded at the close, and not the unload after it')
        good=(str(len(recorded)),hashlib.sha256(recorded).hexdigest())
        # A malformed recorded sink refuses before root writes anything, so the
        # job can be retried once the state is corrected. Perturbation: move
        # source-sink-given below the mkdirs and the job's directories stand.
        for given in [None,(good[0],),('0',good[1]),('-3',good[1]),('x',good[1]),(good[0],'g'*64),(good[0],good[1].upper()),(good[0],good[1][:63])]:
            shutil.rmtree(pt.root/'sinks/job',ignore_errors=True);shutil.rmtree(pt.root/'snapshots/job',ignore_errors=True)
            with self.subTest(given=given),self.assertRaisesRegex(RuntimeError,'source-sink-given'):
                pt.invoke_load(local,declared={'seed':free['seed']},source_sink=given)
            self.assertFalse((pt.root/'sinks/job').exists(),given);self.assertFalse((pt.root/'snapshots/job').exists(),given)
        # A well-formed digest the sink no longer matches is refused after the
        # directories stand: the snapshot needs its own, and never reusing a
        # run leaves them as evidence for the review seat.
        sink.write_bytes(recorded.replace(b'r1',b'rX'))
        with self.assertRaisesRegex(RuntimeError,'snapshot-hash'):
            pt.invoke_load(local,declared={'seed':free['seed']},source_sink=good)

    # 679.2: the driver reads evidence once, against the receipts.

    def test_wait_and_coding_answer_the_receipts_they_verified(self):
        self.due('measure:B1-s451234785645-n1')
        self.assertEqual(self.o.wait('measure:B1-s451234785645-n1',timeout=0),self.state['done'])

    def test_the_driver_reads_evidence_against_its_receipt(self):
        # #683 thread 14: a result substituted after the coordinator verified it
        # is refused where the driver reads it. Perturbation: remove
        # receipt-digest and the substitute is read; remove receipt-present and
        # a missing receipt reads the path alone.
        d=DriverTests('test_assess_control_pass_and_falsifiers');d.setUp();self.addCleanup(d.doCleanups)
        p=Path(d.plan['deposit'])/'runs/B1-s7-n1/run.json';p.parent.mkdir(parents=True);order.atomic(p,dict(d.free,seed=7))
        receipts=d.receipts()
        self.assertEqual(driver.receipt(receipts,'measure:B1-s7-n1')['seed'],7)
        order.atomic(p,dict(d.free,seed=8))
        with self.assertRaisesRegex(order.Refused,'receipt-digest'):driver.receipt(receipts,'measure:B1-s7-n1')
        with self.assertRaisesRegex(order.Refused,'receipt-present'):driver.receipt(receipts,'measure:absent')
        # A local re-feed's source is the receipt, never the path alone.
        j=dict(id='own',kind='refeed',stack='B1',source_job='B1-s7-n1')
        with self.assertRaisesRegex(order.Refused,'receipt-digest'):driver.source_record(d.plan,j,d.probe,receipts)
        with self.assertRaisesRegex(order.Refused,'receipt-present'):driver.source_record(d.plan,j,d.probe,{})

    # 679.6: the interlock at the close and at the unload.

    def test_the_driver_refuses_a_reading_m1_stood_at(self):
        # #683 thread 49. Perturbation: remove m1-unloaded-at-close and a
        # measurement closed with m1 standing is recorded as a reading.
        d=DriverTests('test_free_measurement_refusals');d.setUp();self.addCleanup(d.doCleanups)
        stood=golden_reading(golden.SYSTEMCTL_SHOW_M1.replace('LoadState=not-found','LoadState=loaded').replace('ActiveState=inactive','ActiveState=active'))
        for rows,job in [(d.close(),d.job()),(d.close(True),d.job('refeed'))]:
            with patch('tb_driver.until_closed',return_value=closed_bytes(rows)),patch('tb_driver.m1_reading',return_value=stood),self.assertRaisesRegex(order.Refused,'m1-unloaded-at-close'):
                driver.measure(d.plan,job,d.probe,{})
            d.cleanup_job()
        with patch('tb_driver.until_closed',return_value=closed_bytes(d.close())):result,_=driver.measure(d.plan,d.job(),d.probe,{})
        self.assertEqual(json.loads(result.read_text())['interlock'],golden_reading(),'the reading is recorded beside the result')

    def test_an_unreadable_or_standing_m1_is_never_clear(self):
        clear=golden_reading();self.assertTrue(payload.m1_clear(clear))
        for fault in [dict(readable=False),dict(active_state='active'),dict(door=True),dict(door=None),dict(process=True)]:
            self.assertFalse(payload.m1_clear(dict(clear,**fault)),fault)

    def test_the_unload_refuses_when_m1_stands(self):
        # Perturbation: remove m1-unloaded-at-unload and the unload succeeds
        # with m1 standing, settling a reading it may have shared the card with.
        pt=PayloadTests('test_payload_entry_checks');pt.setUp();self.addCleanup(pt.doCleanups)
        p=copy.deepcopy(pt.plan);p['install_root']=str(pt.root);p['files']={};pt.planpath.write_text(json.dumps(p))
        stood=dict(golden_reading(),process=True)
        def invoke(reading):
            with pt.as_root(),patch('sys.argv',['payload','unload:B1-s7-n1',pt.stand(p)]),patch('tb_payload.os.geteuid',return_value=0),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_payload.pwd.getpwnam',return_value=pt.user),patch('tb_payload.installed'),patch('tb_payload.answer'),patch('tb_payload.m1_reading',return_value=reading),contextlib.redirect_stdout(io.StringIO()) as out:
                payload.main()
            return out.getvalue()
        self.assertIn('INTERLOCK at unload',invoke(golden_reading()))
        with self.assertRaisesRegex(RuntimeError,'m1-unloaded-at-unload'):invoke(stood)


class ReviewRoundOneTests(unittest.TestCase):
    """#693's first Codex pass: the bytes hashed are the bytes the close was
    seen in, and an interlock fact that cannot be read is unread, never
    clear, for both readers."""

    def test_the_close_is_returned_from_the_read_it_was_seen_in(self):
        # Two shapes of the one defect, a close seen in one read and another
        # read returned. The read after the one holding the close is swapped
        # for bytes with no close: perturbation `return path.read_bytes()`
        # after detecting, and the swapped bytes come back. And the first read
        # is swapped: b34f62e's tail-then-read order returns it, while a
        # function returning its own read keeps polling to the real one.
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace';closed=ndjson(event(golden.TURN_CLOSED,run='r')).encode();p.write_bytes(closed)
            swapped=ndjson(event(golden.TURN_STARTED,run='r'),event(golden.TURN_STARTED,run='r')).encode()
            real=Path.read_bytes
            for name,swap_on in [('the read after the close is swapped',2),('the first read is swapped',1)]:
                with self.subTest(name):
                    calls=[]
                    def read_bytes(path):
                        calls.append(1)
                        return swapped if len(calls)==swap_on else real(path)
                    with patch.object(Path,'read_bytes',read_bytes):
                        got=driver.until_closed(p,'turn.closed',5)
                    self.assertIn(b'turn.closed',got,'the returned bytes hold the close they were returned for')
                    self.assertEqual(got,closed,'and are the bytes the close was inspected in')

    def reading(self,**patches):
        base=dict(run=patch('tb_payload.subprocess.run',return_value=subprocess.CompletedProcess([],0,golden.SYSTEMCTL_SHOW_M1,'')),
                  door=patch('tb_payload.door_state',return_value=False),
                  iterdir=patch('tb_payload.Path.iterdir',return_value=[]),
                  user=patch('tb_payload.pwd.getpwnam',side_effect=KeyError),
                  hides=patch('tb_payload.proc_hides_processes',return_value=False),
                  euid=patch('tb_payload.os.geteuid',return_value=1000))
        base.update(patches)
        with contextlib.ExitStack() as stack:
            for p in base.values():stack.enter_context(p)
            return payload.m1_reading()

    def test_every_fact_that_cannot_be_read_is_unread(self):
        # Perturbation: catch only a vanished process, or only a refused door,
        # and the refused read escapes, or reads as clear.
        self.assertTrue(payload.m1_clear(self.reading()))
        refused_stat=[SimpleNamespace(name='42',stat=lambda:(_ for _ in ()).throw(PermissionError()))]
        for name,patches,fact,value in [
            ('systemctl unrunnable',dict(run=patch('tb_payload.subprocess.run',side_effect=OSError)),'readable',False),
            ('door refused',dict(door=patch('tb_payload.door_state',return_value=None)),'door',None),
            ('process refused',dict(iterdir=patch('tb_payload.Path.iterdir',return_value=refused_stat),user=patch('tb_payload.pwd.getpwnam',return_value=SimpleNamespace(pw_uid=1000))),'process',None),
            ('proc unlistable',dict(iterdir=patch('tb_payload.Path.iterdir',side_effect=PermissionError)),'process',None),
            ('hidepid, unprivileged',dict(hides=patch('tb_payload.proc_hides_processes',return_value=True)),'process',None)]:
            with self.subTest(name):
                r=self.reading(**patches)
                self.assertEqual(r[fact],value,r);self.assertFalse(payload.m1_clear(r))
        # A process that vanished mid-scan is absent, since it is: the one
        # failure that reads as clear rather than unread.
        vanished=[SimpleNamespace(name='42',stat=lambda:(_ for _ in ()).throw(FileNotFoundError()))]
        r=self.reading(iterdir=patch('tb_payload.Path.iterdir',return_value=vanished),user=patch('tb_payload.pwd.getpwnam',return_value=SimpleNamespace(pw_uid=1000)))
        self.assertIs(r['process'],False);self.assertTrue(payload.m1_clear(r))
        # Root sees every process whatever hidepid says, so the scan runs.
        r=self.reading(hides=patch('tb_payload.proc_hides_processes',return_value=True),euid=patch('tb_payload.os.geteuid',return_value=0))
        self.assertTrue(payload.m1_clear(r))

    def test_the_door_is_read_by_stat_and_a_refused_look_is_unread(self):
        # #693, on this box's Python 3.14: Path.exists() answers False behind
        # a denied directory, so the door is read by stat against a real
        # locked directory here, not a patched method. Perturbation: read the
        # door with Path.exists() again and the refused look reads False.
        with tempfile.TemporaryDirectory() as tmp:
            locked=Path(tmp)/'locked';locked.mkdir();door=locked/'coordination.sock';door.touch()
            # A 000 directory does not deny root, so under root this case
            # would pass without testing anything: it refuses to run instead.
            self.assertNotEqual(os.geteuid(),0,'run the suite unprivileged: root is not denied by a 000 directory')
            self.assertIs(payload.door_state(door),True)
            self.assertIs(payload.door_state(locked/'absent.sock'),False)
            locked.chmod(0)
            try:self.assertIsNone(payload.door_state(door),'a door behind a denied directory is unread')
            finally:locked.chmod(0o700)

    def test_hidepid_is_read_from_the_mount_table(self):
        for options,hidden in [('rw,nosuid,nodev,noexec,relatime',False),('rw,relatime,hidepid=2',True),
                               ('rw,hidepid=invisible',True),('rw,hidepid=0',False)]:
            with patch('tb_payload.Path.read_text',return_value=f'proc /proc proc {options} 0 0\n'):
                self.assertEqual(payload.proc_hides_processes(),hidden,options)

    def test_both_readers_refuse_an_unread_fact(self):
        unread=dict(golden_reading(),process=None)
        d=DriverTests('test_free_measurement_refusals');d.setUp();self.addCleanup(d.doCleanups)
        with patch('tb_driver.until_closed',return_value=closed_bytes(d.close())),patch('tb_driver.m1_reading',return_value=unread),self.assertRaisesRegex(order.Refused,'m1-unloaded-at-close'):
            driver.measure(d.plan,d.job(),d.probe,{})
        pt=PayloadTests('test_payload_entry_checks');pt.setUp();self.addCleanup(pt.doCleanups)
        p=copy.deepcopy(pt.plan);p['install_root']=str(pt.root);p['files']={};pt.planpath.write_text(json.dumps(p))
        with pt.as_root(),patch('sys.argv',['payload','unload:B1-s7-n1',pt.stand(p)]),patch('tb_payload.os.geteuid',return_value=0),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_payload.pwd.getpwnam',return_value=pt.user),patch('tb_payload.installed'),patch('tb_payload.answer'),patch('tb_payload.m1_reading',return_value=unread),contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'m1-unloaded-at-unload'):
            payload.main()


class JsonEqualityTests(unittest.TestCase):
    """#695's first Codex pass as a class: every equality between JSON-parsed
    values compares canonical JSON text or checks each side's type, so 7.0
    is not 7 and true is not 1 anywhere the probe judges a record."""

    def test_same_tells_json_facts_apart(self):
        for a,b in [(512,512.0),(1,True),(0,False),([3],[3.0]),({'a':1},{'a':1.0})]:
            self.assertFalse(order.same(a,b),(a,b));self.assertFalse(payload.same(a,b),(a,b))
        self.assertTrue(order.same({'b':1,'a':[2]},{'a':[2],'b':1}))

    def test_the_plan_refuses_a_coerced_version_or_seed(self):
        f=Fixture('test_plan_validation');f.setUp();self.addCleanup(f.doCleanups)
        for name,edit in [('schema',lambda p:p.update(version=True)),('schema',lambda p:p.update(version=1.0)),
                          ('control-schedule',lambda p:next(j for j in p['arms'][0]['jobs'] if j['kind']=='free').update(seed=float(p['tuple']['seeds'][0])))]:
            p=copy.deepcopy(f.plan);edit(p)
            with self.subTest(name),self.assertRaisesRegex(order.Refused,name):order.validate_plan(p)

    def test_exactness_and_the_seed_guards_refuse_a_coerced_number(self):
        d=DriverTests('test_free_measurement_refusals');d.setUp();self.addCleanup(d.doCleanups)
        a=copy.deepcopy(d.free);b=copy.deepcopy(d.free);b['output_tokens']=[float(x) for x in a['output_tokens']]
        self.assertFalse(driver.exact(d.plan['tuple'],a,b),'[3.0] is not [3]')
        d.free['declared_seed']=7.0
        with patch('tb_driver.until_closed',return_value=closed_bytes(d.close())),self.assertRaisesRegex(order.Refused,'seed-held'):
            driver.measure(d.plan,d.job(),d.probe,{})

    def test_the_derived_tuple_refuses_a_coerced_value(self):
        pt=PayloadTests('test_replay_source_must_hold_the_tuple');pt.setUp();self.addCleanup(pt.doCleanups)
        job=dict(id='job',kind='refeed',stack='B1',source_trace='x',source_run='r')
        t=pt.plan['tuple']
        good=derived(pt.model,'/sink',t)
        self.assertTrue(payload.holds_tuple(pt.plan,job,good))
        coerced=good.replace(f"context-capacity: {t['context_capacity']}",f"context-capacity: {float(t['context_capacity'])}")
        self.assertNotEqual(coerced,good)
        self.assertFalse(payload.holds_tuple(pt.plan,job,coerced),'12288.0 is not 12288')

    def test_the_operator_uid_must_be_an_integer(self):
        pt=PayloadTests('test_payload_entry_checks');pt.setUp();self.addCleanup(pt.doCleanups)
        p=copy.deepcopy(pt.plan);p['install_root']=str(pt.root);p['files']={};p['operator_uid']=1000.0;pt.planpath.write_text(json.dumps(p))
        with pt.as_root(),patch('sys.argv',['payload','provision',pt.stand(p)]),patch('tb_payload.os.geteuid',return_value=0),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_payload.pwd.getpwnam',return_value=pt.user),patch('tb_payload.provision'),contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'operator'):
            payload.main()


    def test_the_plan_refuses_a_stack_or_job_id_that_is_not_a_string(self):
        # A missing stack was str(None), truthy, and resolved to the working
        # directory. A job id of 5 reached re.fullmatch and raised.
        f=Fixture('test_plan_validation');f.setUp();self.addCleanup(f.doCleanups)
        for name,edit in [('stacks-distinct',lambda p:p['stacks'].pop('B1')),('stacks-distinct',lambda p:p['stacks'].update(B1=5)),
                          ('job-identities',lambda p:p['arms'][0]['jobs'][0].update(id=5)),('job-identities',lambda p:p['arms'][0]['jobs'][0].update(id=['a']))]:
            p=copy.deepcopy(f.plan);edit(p)
            with self.subTest(name),self.assertRaisesRegex(order.Refused,name):order.validate_plan(p)

    def test_a_lease_names_a_process_only_by_an_int_pid(self):
        # A pid of 'self' read the reader's own /proc entry as the lease holder.
        me=os.getpid()
        self.assertTrue(order.live(dict(pid=me,ticks=order.ticks(me))))
        for lease in [dict(pid='self',ticks=order.ticks('self')),dict(pid=float(me),ticks=order.ticks(me)),dict(pid=me),None]:
            with self.subTest(lease=lease):self.assertFalse(order.live(lease))

    def test_a_field_position_is_an_int_and_duplicates_are_json_facts(self):
        d=DriverTests('test_a_second_field_event_for_a_position_refuses_on_every_path');d.setUp();self.addCleanup(d.doCleanups)
        base=json.loads(golden.MODEL_FIELD)['payload'];j=d.job('free')
        cases=[[event(golden.MODEL_FIELD,run='r',payload=dict(base,position=float(base['position'])))],
               [event(golden.MODEL_FIELD,run='r',payload=dict(base,position=str(base['position'])))],
               [event(golden.MODEL_FIELD,run='r'),event(golden.MODEL_FIELD,run='r',sequence='42',payload=dict(base,position=float(base['position'])))]]
        for n,ev in enumerate(cases):
            try:
                with self.subTest(case=n),patch('tb_driver.until_closed',return_value=closed_bytes(ev+d.close())),self.assertRaisesRegex(order.Refused,'field-beyond-output'):
                    driver.measure(d.plan,j,d.probe,{})
            finally:d.cleanup_job()

    def test_exactness_compares_field_keys_as_written(self):
        # A result file holds the field's keys as JSON strings and a fresh
        # extraction as ints: both read as one record, and '03' is not 3.
        d=DriverTests('test_exact_holds_the_input_length');d.setUp();self.addCleanup(d.doCleanups)
        t=prepare.template(Path('/deposit'),'todd',1000)['tuple']
        a=copy.deepcopy(d.free);k=next(iter(a['field']))
        written=dict(copy.deepcopy(a),field={str(kk):v for kk,v in a['field'].items()})
        padded=dict(copy.deepcopy(a),field={('0'+str(kk) if kk==k else kk):v for kk,v in a['field'].items()})
        self.assertTrue(driver.exact(t,a,written))
        self.assertFalse(driver.exact(t,a,padded),'field key 03 is not 3')

    def test_the_input_length_and_divergence_position_are_ints(self):
        d=DriverTests('test_refeed_holds_the_input_and_refuses_a_divergence_inside_it');d.setUp();self.addCleanup(d.doCleanups)
        j=d.job('refeed');n=d.free['input_tokens']
        d.free['input_tokens']=float(n)
        try:
            with patch('tb_driver.until_closed',return_value=closed_bytes(d.close(True))),self.assertRaisesRegex(order.Refused,'input-held'):driver.measure(d.plan,j,d.probe,{})
        finally:d.cleanup_job()
        d.free['input_tokens']=n
        for pos in [float(n),str(n)]:
            at=run_events('r',event(golden.REPLAY_CLOSED_CERTIFIED,run='r',payload=dict(outcome=dict(kind='diverged',divergence=dict(kind='token_path',position=pos,recorded=1,recomputed=2)))))
            try:
                with self.subTest(position=pos),patch('tb_driver.until_closed',return_value=closed_bytes(at)),self.assertRaisesRegex(order.Refused,'divergence-in-input'):
                    driver.measure(d.plan,j,d.probe,{})
            finally:d.cleanup_job()

    def test_roots_sink_length_is_ascii_digits(self):
        h='0'*64
        self.assertTrue(payload.well_formed_sink(('512',h)))
        for length in ['\u0665\u0661\u0662','0512','0','',' 512','512.0']:
            with self.subTest(length=length):self.assertFalse(payload.well_formed_sink((length,h)))


class AbsenceTests(unittest.TestCase):
    """#695's second Codex pass as a class: an equality whose sides both come
    from a .get() or a read that answers None on failure holds for two
    absences, so the expected side is required present at each guard."""

    def test_a_dead_lease_with_no_ticks_is_not_live_and_refuses_driver_live(self):
        p=subprocess.Popen(['true']);p.wait();dead=p.pid
        self.assertIsNone(order.ticks(dead))
        me=os.getpid()
        for lease in [dict(pid=dead),dict(pid=dead,ticks=None),dict(pid=me),dict(pid=me,ticks=None)]:
            with self.subTest(lease=lease):self.assertFalse(order.live(lease))
        f=Fixture('test_history_order_seat_lease');f.setUp();self.addCleanup(f.doCleanups)
        f.due('load:B1-s451234785645-n1');s=copy.deepcopy(f.state);s['driver']=dict(pid=dead)
        with self.assertRaisesRegex(order.Refused,'driver-live'):f.o.guard(s,f.plan,'load:B1-s451234785645-n1','operator')

    def test_a_diverged_outcome_without_its_divergence_refuses(self):
        d=DriverTests('test_refeed_holds_the_input_and_refuses_a_divergence_inside_it');d.setUp();self.addCleanup(d.doCleanups)
        j=d.job('refeed')
        for outcome in [dict(kind='diverged'),dict(kind='diverged',divergence=None),dict(kind='diverged',divergence=dict(position=3))]:
            rows=run_events('r',event(golden.REPLAY_CLOSED_CERTIFIED,run='r',payload=dict(outcome=outcome)))
            try:
                with self.subTest(outcome=outcome),patch('tb_driver.until_closed',return_value=closed_bytes(rows)),self.assertRaisesRegex(order.Refused,'replay-completed'):
                    driver.measure(d.plan,j,d.probe,{})
            finally:d.cleanup_job()

    def test_an_absent_seed_or_weights_refuses_by_name(self):
        d=DriverTests('test_free_measurement_refusals');d.setUp();self.addCleanup(d.doCleanups)
        for key,name in [('declared_seed','seed-held'),('weights_hash','weights-held')]:
            held=d.free.pop(key)
            try:
                with self.subTest(key),patch('tb_driver.until_closed',return_value=closed_bytes(d.close())),self.assertRaisesRegex(order.Refused,name):
                    driver.measure(d.plan,d.job(),d.probe,{})
            finally:d.cleanup_job();d.free[key]=held
        # Source and replay both without a seed: two absences, refused before
        # any reading, by the source guard and, were it gone, by the replay's.
        d.free.pop('declared_seed')
        try:
            with patch('tb_driver.until_closed',return_value=closed_bytes(d.close(True))),self.assertRaisesRegex(order.Refused,'seed-held'):
                driver.measure(d.plan,d.job('refeed'),d.probe,{})
        finally:d.cleanup_job()

class AdditionalTests(unittest.TestCase):
    save = Fixture.save
    publish = Fixture.publish
    setUp = Fixture.setUp
    def test_changed_artifact_contents(self):
        self.source.write_text('changed')
        with self.assertRaises(order.Refused):self.o.approved(self.state)

    def test_operator_and_driver_entry_uid(self):
        for uid, expected in [(0,1),(1000,0)]:
            with patch('sys.argv',['operator','--state',str(self.statepath)]),patch('tb_order.os.geteuid',return_value=uid),patch('tb_order.Order.operator'),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(order.main(),expected)
            with patch('sys.argv',['driver','--state',str(self.statepath),'TB0']),patch('tb_driver.os.geteuid',return_value=uid),patch('tb_driver.drive'),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(driver.main(),expected)

class PerturbationBaselineTests(unittest.TestCase):
    def test_a_failing_baseline_refuses_before_any_mutation(self):
        # #683 finding 5: a suite that already fails would read every mutation
        # as killed. The runner must refuse instead of reporting full detection.
        with tempfile.TemporaryDirectory() as tmp:
            here=Path(__file__).resolve().parent;copy_dir=Path(tmp)
            for p in here.glob('*'):
                if p.suffix in ['.py','.sh']:(copy_dir/p.name).write_bytes(p.read_bytes())
            (copy_dir/'test_tb.py').write_text('import unittest\nclass T(unittest.TestCase):\n    def test_broken(self):self.fail("baseline broken")\n')
            result=subprocess.run([sys.executable,'-B',str(copy_dir/'perturb.py')],capture_output=True,text=True,timeout=120,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
            self.assertNotEqual(result.returncode,0)
            self.assertIn('BASELINE FAILED',result.stderr)
            self.assertEqual(result.stdout,'')

    def test_a_subject_moved_during_the_sweep_refuses_the_reading(self):
        # 679.5: an edit made during a sweep misaimed every mutation after it
        # and eight guards read as survivors. The sweep pins its subject by its
        # bytes, and a subject that moves under it refuses the whole reading.
        # This suite passes and edits the subject each time it runs.
        with tempfile.TemporaryDirectory() as tmp:
            here=Path(__file__).resolve().parent;copy_dir=Path(tmp)
            for p in here.glob('*'):
                if p.suffix in ['.py','.sh']:(copy_dir/p.name).write_bytes(p.read_bytes())
            (copy_dir/'test_tb.py').write_text('import os,unittest\nclass T(unittest.TestCase):\n    def test_moves(self):\n        with open(os.environ["TB_SUBJECT"],"a") as f:f.write("# moved\\n")\n')
            result=subprocess.run([sys.executable,'-B',str(copy_dir/'perturb.py')],capture_output=True,text=True,timeout=120,
                                  env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TB_SUBJECT=str(copy_dir/'tb_order.py')))
            self.assertEqual(result.returncode,2,result.stderr[-600:])
            self.assertIn('SUBJECT MOVED: tb_order.py',result.stderr)
            self.assertEqual(result.stdout,'')


class StagingTests(unittest.TestCase):
    def test_staging_starts_held_and_cannot_overwrite_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            command=[sys.executable,str(Path(__file__).with_name('prepare.py')),
                     '--handoffs',str(root/'handoffs'),'--deposit',str(root/'deposit')]
            staged=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(staged.returncode,0,staged.stderr)
            state=root/'handoffs/tb-evidence/tb-state.json'
            original=state.read_bytes()
            self.assertIsNone(json.loads(original)['approval'])
            self.assertNotIn('review',json.loads(original));self.assertNotIn('hold',json.loads(original))
            duplicate=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(duplicate.returncode,0)
            self.assertEqual(state.read_bytes(),original)
            wrapper=root/'handoffs/tb/tb-operator.sh'
            result=subprocess.run(['bash',str(wrapper)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('WAITING ON: review seat',result.stdout)
            named=subprocess.run(['bash',str(wrapper),'provision'],capture_output=True,text=True)
            self.assertNotEqual(named.returncode,0)
            self.assertIn('REFUSED: approval-digest',named.stderr)
            after=json.loads(state.read_text())
            self.assertEqual(after['cursor'],0)
            self.assertIsNone(after['approval'])
            self.assertIn('approval-digest',after['refusals'][-1]['reason'])



class ApprovalTests(unittest.TestCase):
    """679.5, the one privileged approval step, on the ruling of 2026-09-26 on
    #698: root snapshots the review record and every artifact it names, the
    state keeps a pointer, and every later step reads the root-owned record."""

    def setUp(self):
        self.pt=pt=PayloadTests('test_payload_entry_checks');pt.setUp();self.addCleanup(pt.doCleanups)
        shutil.rmtree(pt.root)
        staged=pt.base/'staged';staged.mkdir()
        self.code=b'# the reviewed payload\n'
        self.payload_file=staged/'tb_payload.py';self.payload_file.write_bytes(self.code)
        self.artifact=staged/'tb_order.py';self.artifact.write_text('reviewed coordinator\n')
        plan=copy.deepcopy(pt.plan);plan['install_root']=str(pt.root);plan['files']={}
        self.planfile=pt.base/'tb-plan.json';self.planfile.write_text(json.dumps(plan))
        self.record=dict(status='PASS',hold=False,seat=order.REVIEW_SEAT,
                         reference='https://github.com/toddwbucy/WeaverTools/issues/698#issuecomment-5851860966',
                         plan=str(self.planfile),payload=str(self.payload_file),
                         artifacts={str(f):order.sha(f) for f in [self.planfile,self.payload_file,self.artifact]})
        self.recordfile=pt.base/'review.json';self.write()

    def write(self,record=None):
        self.recordfile.write_text(json.dumps(record or self.record))

    def approve(self,code=None,record=None,expected=None):
        """Root's approve, handed the record digest the coordinator took
        before sudo: by default the record's own, as it stands."""
        path=record or self.recordfile
        with self.pt.as_root(code or self.code),patch('tb_root.os.geteuid',return_value=0),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_root.pwd.getpwnam',return_value=self.pt.user),contextlib.redirect_stdout(io.StringIO()) as out:
            rootprog.approve(str(path),expected or order.sha(path))
        return out.getvalue()

    def as_sudo(self,argv,stdout,**kw):
        """sudo as the coordinator calls it for approve, running root's step
        in process, a refusal answering as the payload's exit status does."""
        self.assertEqual(argv[:3],['sudo',order.ROOT_PROGRAM,'approve'])
        try:
            with self.pt.as_root(self.code),patch('tb_root.os.geteuid',return_value=0),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_root.pwd.getpwnam',return_value=self.pt.user),contextlib.redirect_stdout(stdout):
                rootprog.approve(argv[3],argv[4])
        except RuntimeError as error:
            stdout.write(f'REFUSED: {error}\n');stdout.flush()
            return subprocess.CompletedProcess(argv,1)
        return subprocess.CompletedProcess(argv,0)

    def approvals(self):
        return sorted(p.name for p in (self.pt.root/'approval').iterdir()) if (self.pt.root/'approval').exists() else None

    def test_approve_snapshots_the_record_and_prints_its_digest(self):
        out=self.approve()
        digest,=[l.split()[1] for l in out.splitlines() if l.startswith('APPROVAL: ')]
        directory=self.pt.root/'approval'/digest
        self.assertEqual(self.approvals(),[digest])
        private,public=directory/'approval.json',directory/'approval.pub.json'
        self.assertEqual(private.read_bytes(),public.read_bytes())
        self.assertEqual(hashlib.sha256(public.read_bytes()).hexdigest(),digest)
        self.assertEqual({f.name:oct(f.stat().st_mode&0o777) for f in directory.iterdir()},
                         {'approval.json':'0o600','approval.pub.json':'0o644','plan.json':'0o600','tb_payload.py':'0o600'})
        self.assertEqual((directory/'plan.json').read_bytes(),self.planfile.read_bytes())
        self.assertEqual((directory/'tb_payload.py').read_bytes(),self.code)
        approval=json.loads(public.read_bytes())
        self.assertEqual(approval['record'],self.record)
        self.assertEqual(approval['record_sha256'],order.sha(self.recordfile))
        self.assertEqual(approval['payload']['sha256'],hashlib.sha256(self.code).hexdigest())
        with self.pt.as_root():self.assertEqual(payload.read_approval(digest)[0],approval)

    def test_a_tampered_artifact_refuses_and_leaves_nothing(self):
        # Perturbation: skip the artifact loop and the tampered bytes are approved.
        self.artifact.write_text('changed after the review\n')
        with self.assertRaisesRegex(RuntimeError,'approval-artifacts'):self.approve()
        self.assertFalse(self.pt.root.exists(),'nothing is made before every digest holds')
        # With approvals already standing, a refusal adds nothing to them.
        self.artifact.write_text('reviewed coordinator\n');self.approve();before=self.approvals()
        other=dict(self.record,reference=self.record['reference']+'0');other['artifacts'][str(self.artifact)]='f'*64;self.write(other)
        with self.assertRaisesRegex(RuntimeError,'approval-artifacts'):self.approve()
        self.assertEqual(self.approvals(),before)

    def test_a_second_approve_of_the_same_record_adopts_it(self):
        # #709 round three: a record approved before is adopted, its complete
        # approval verified and its digest printed, and nothing is written.
        # Perturbation: drop the adoption and a second approval is written
        # beside the first.
        first=self.approve().split()[1];directory=self.pt.root/'approval'/first
        before={f.name:(f.read_bytes(),f.stat().st_mtime_ns) for f in directory.iterdir()}
        self.assertEqual(self.approve().split()[1],first)
        self.assertEqual(self.approvals(),[first])
        self.assertEqual({f.name:(f.read_bytes(),f.stat().st_mtime_ns) for f in directory.iterdir()},before)
        # What is adopted is complete, every file checked (#709 round four),
        # each change at the file's own mode. Perturbation: drop
        # approval-complete from the scan and each of these is adopted.
        for name,change in [('approval.pub.json',b'{}'),('plan.json',b'changed'),('tb_payload.py',b'changed')]:
            with self.subTest(name=name):
                mode=rootprog.FILES[name];kept=(directory/name).read_bytes()
                (directory/name).chmod(0o600);(directory/name).write_bytes(change);(directory/name).chmod(mode)
                with self.assertRaisesRegex(RuntimeError,'approval-complete'):self.approve()
                (directory/name).chmod(0o600);(directory/name).write_bytes(kept);(directory/name).chmod(mode)
        # Two complete approvals of one record is custody no approve made, and
        # neither is adopted. Perturbation: drop approval-once and one is.
        body=json.loads((directory/'approval.json').read_bytes());body['approved_at']=1
        data=(json.dumps(body,sort_keys=True,indent=1)+'\n').encode();twin=self.pt.root/'approval'/hashlib.sha256(data).hexdigest()
        shutil.copytree(directory,twin);(twin/'approval.json').write_bytes(data);(twin/'approval.pub.json').write_bytes(data)
        with self.assertRaisesRegex(RuntimeError,'approval-once'):self.approve()
        shutil.rmtree(twin)
        # A new review is a new record and approves beside the first.
        self.write(dict(self.record,reference=self.record['reference']+'1'));self.approve()
        self.assertEqual(len(self.approvals()),2)

    def test_a_partial_approval_refuses_by_name(self):
        # #709 round three: a crash mid-write leaves a `.pending-` directory
        # the run's own cleanup never reached. It is never adopted or written
        # past, and refuses by name. Perturbation: drop approval-complete from
        # the scan and the first refuses unnamed, the second is adopted past.
        self.approve();before=self.approvals()
        pending=self.pt.root/'approval'/('.pending-'+order.sha(self.recordfile));pending.mkdir(mode=0o700)
        (pending/'plan.json').write_bytes(self.planfile.read_bytes())
        with self.assertRaisesRegex(RuntimeError,'approval-complete'):self.approve()
        self.assertEqual(sorted(os.listdir(self.pt.root/'approval')),sorted(before+[pending.name]))
        shutil.rmtree(pending)
        # A digest-named directory whose record is missing is no approval either.
        broken=self.pt.root/'approval'/('d'*64);broken.mkdir();broken.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError,'approval-complete'):self.approve()
        broken.rmdir();self.assertEqual(self.approvals(),before)

    def test_a_record_moved_after_the_coordinator_hashed_it_refuses(self):
        # #709 round three: root holds its read to the digest the coordinator
        # took before sudo. Perturbation: drop approval-record-digest and the
        # moved record is approved under a digest the coordinator never took.
        expected=order.sha(self.recordfile)
        self.write(dict(self.record,reference=self.record['reference']+'2'))
        with self.assertRaisesRegex(RuntimeError,'approval-record-digest'):self.approve(expected=expected)
        self.assertFalse(self.pt.root.exists())

    def test_an_interrupted_approve_is_adopted_on_retry(self):
        # #709 round three, the crash window: root commits, then the
        # coordinator dies before the state learns the pointer. The retry
        # adopts root's approval and records the pointer once. The target is
        # hashed once before sudo and never read again after it.
        statefile=self.pt.base/'state.json';order.atomic(statefile,dict(cursor=0,done={},approval=None))
        log=self.pt.base/'approve.log'
        with patch.object(order,'APPROVAL_ROOT',self.pt.root/'approval'),patch.object(order,'APPROVAL_OWNER',os.getuid()):
            def dies_after_root(argv,stdout,**kw):
                self.as_sudo(argv,stdout);raise KeyboardInterrupt('the coordinator dies here')
            with patch('tb_order.subprocess.run',side_effect=dies_after_root),self.assertRaises(KeyboardInterrupt):order.approve(statefile,self.recordfile,log)
            self.assertIsNone(json.loads(statefile.read_text())['approval'])
            committed=self.approvals();self.assertEqual(len(committed),1)
            writes=[];real=order.atomic
            def counted(path,value):writes.append(value.get('approval'));real(path,value)
            with patch('tb_order.subprocess.run',side_effect=self.as_sudo),patch('tb_order.atomic',side_effect=counted):
                self.assertEqual(order.approve(statefile,self.recordfile,log),committed[0])
            self.assertEqual((writes,self.approvals()),([committed[0]],committed))
            self.assertEqual(json.loads(statefile.read_text())['approval'],committed[0])
            # The record moving on disk after root has run changes nothing:
            # the coordinator checks the approval against the digest it took
            # before sudo. Perturbation: read the target again after root and
            # this refuses under approve-record.
            order.atomic(statefile,dict(cursor=0,done={},approval=None))
            def moved_after_root(argv,stdout,**kw):
                result=self.as_sudo(argv,stdout);self.write(dict(self.record,reference=self.record['reference']+'3'));return result
            self.write()
            with patch('tb_order.subprocess.run',side_effect=moved_after_root):self.assertEqual(order.approve(statefile,self.recordfile,log),committed[0])
            # And moving before root reads it refuses at root, the state unchanged.
            order.atomic(statefile,dict(cursor=0,done={},approval=None));self.write()
            def moved_before_root(argv,stdout,**kw):
                self.write(dict(self.record,reference=self.record['reference']+'4'));return self.as_sudo(argv,stdout)
            with patch('tb_order.subprocess.run',side_effect=moved_before_root),self.assertRaisesRegex(order.Refused,'approve-exit'):order.approve(statefile,self.recordfile,log)
            self.assertIn('approval-record-digest',log.read_text())
            self.assertIsNone(json.loads(statefile.read_text())['approval'])

    def test_a_linked_or_malformed_record_refuses(self):
        link=self.pt.base/'linked.json';link.symlink_to(self.recordfile)
        with self.assertRaisesRegex(RuntimeError,'approval-record'):self.approve(record=link)
        for change in [dict(hold=True),dict(status='FAIL'),dict(seat='coding seat'),dict(reference='#698'),dict(plan='/nowhere')]:
            self.write(dict(self.record,**change))
            with self.subTest(change=change),self.assertRaisesRegex(RuntimeError,'approval-record'):self.approve()
        self.write()
        self.assertFalse(self.pt.root.exists())

    def test_a_failed_write_removes_what_the_run_made(self):
        real=rootprog.write_new;calls=[]
        def failing(path,data,mode):
            calls.append(path)
            if len(calls)==3:raise OSError('disk full')
            real(path,data,mode)
        with patch('tb_root.write_new',side_effect=failing),self.assertRaises(OSError):self.approve()
        self.assertFalse(self.pt.root.exists(),'the root this run made is removed with the partial approval')

    def test_the_coordinator_records_only_a_verified_pointer(self):
        # The state learns the digest root printed, and only once the public
        # copy it names is root's and matches.
        statefile=self.pt.base/'state.json';order.atomic(statefile,dict(cursor=0,done={},approval=None))
        log=self.pt.base/'approve.log'
        def as_sudo(argv,stdout,**kw):
            self.assertEqual(argv[:3],['sudo',order.ROOT_PROGRAM,'approve'])
            self.assertEqual(argv[3:],[str(self.recordfile.resolve()),order.sha(self.recordfile)])
            with self.pt.as_root(self.code),patch('tb_root.os.geteuid',return_value=0),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_root.pwd.getpwnam',return_value=self.pt.user),contextlib.redirect_stdout(stdout):
                rootprog.approve(argv[3],argv[4])
            return subprocess.CompletedProcess(argv,0)
        with patch.object(order,'APPROVAL_ROOT',self.pt.root/'approval'),patch.object(order,'APPROVAL_OWNER',os.getuid()):
            with patch('tb_order.subprocess.run',side_effect=as_sudo):digest=order.approve(statefile,self.recordfile,log)
            self.assertEqual(json.loads(statefile.read_text())['approval'],digest)
            self.assertEqual(order.publication(digest)['record'],self.record)
            # A printed digest naming no root-owned record is never recorded.
            order.atomic(statefile,dict(cursor=0,done={},approval=None))
            def lying(argv,stdout,**kw):stdout.write('APPROVAL: '+'0'*64+'\n');stdout.flush();return subprocess.CompletedProcess(argv,0)
            with patch('tb_order.subprocess.run',side_effect=lying),self.assertRaisesRegex(order.Refused,'approval-'):order.approve(statefile,self.recordfile,log)
            self.assertIsNone(json.loads(statefile.read_text())['approval'])
            def failed(argv,stdout,**kw):return subprocess.CompletedProcess(argv,1)
            with patch('tb_order.subprocess.run',side_effect=failed),self.assertRaisesRegex(order.Refused,'approve-exit'):order.approve(statefile,self.recordfile,log)

    def test_a_second_approve_against_a_state_refuses_with_the_pointer_unchanged(self):
        # #709 round one: a second valid approve replaced the pointer beneath a
        # run already under way, swapping its plan. A state runs under one
        # approval, so a second refuses before root is asked for anything.
        # Perturbation: drop one-approval-per-state and root is asked, and the
        # pointer moves to the second approval.
        first=stand_approval(self.pt.root/'approval',self.record)
        evidence=self.pt.base/'provision.log';evidence.write_text('SUCCESS: provision\n')
        state=dict(cursor=1,done={'provision':dict(status='SUCCESS',path=str(evidence),sha256=order.sha(evidence),approval=first)},approval=first)
        statefile=self.pt.base/'state.json';order.atomic(statefile,state);before=statefile.read_bytes()
        log=self.pt.base/'approve.log';asked=[]
        def as_sudo(argv,stdout,**kw):
            asked.append(argv)
            with self.pt.as_root(self.code),patch('tb_root.os.geteuid',return_value=0),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_root.pwd.getpwnam',return_value=self.pt.user),contextlib.redirect_stdout(stdout):
                rootprog.approve(argv[3],argv[4])
            return subprocess.CompletedProcess(argv,0)
        with patch.object(order,'APPROVAL_ROOT',self.pt.root/'approval'),patch.object(order,'APPROVAL_OWNER',os.getuid()),patch('tb_order.subprocess.run',side_effect=as_sudo):
            with self.assertRaisesRegex(order.Refused,'one-approval-per-state'):order.approve(statefile,self.recordfile,log)
        self.assertEqual((asked,statefile.read_bytes()),([],before))

    def test_the_state_file_says_nothing_about_approval(self):
        # After approval, the state's own fields flipped to FAIL and held change
        # nothing: `next` proceeds on the root-owned record (679.5).
        f=Fixture('test_approval_refusals');f.setUp();self.addCleanup(f.doCleanups)
        s=copy.deepcopy(f.state);s.update(hold=True,review=dict(status='FAIL',seat='coding seat',artifacts={}));order.atomic(f.statepath,s)
        self.assertEqual(f.o.approved(s),f.plan)
        with patch('tb_order.payload',return_value=0) as runner,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(order.Refused):
            f.o.operator()
        runner.assert_called_once()

    def test_each_approve_guard_refuses_by_name(self):
        # Every refusal here is asserted by its name, so removing one guard
        # cannot pass as a later guard catching the same case.
        plan=json.loads(self.planfile.read_text())
        for field,value,guard in [('agent','karl','fixed-root-agent'),('operator_uid',9,'operator')]:
            bad=dict(plan,**{field:value});self.planfile.write_text(json.dumps(bad))
            record=dict(self.record,artifacts={**self.record['artifacts'],str(self.planfile):order.sha(self.planfile)});self.write(record)
            with self.subTest(guard=guard),self.assertRaisesRegex(RuntimeError,guard):self.approve()
            self.assertFalse(self.pt.root.exists())
        self.planfile.write_text(json.dumps(plan));self.write()
        # The root's ancestry, before the root is made.
        self.pt.base.chmod(0o775)
        try:
            with self.assertRaisesRegex(RuntimeError,'root-chain-custody'):self.approve()
        finally:self.pt.base.chmod(0o700)
        self.assertFalse(self.pt.root.exists())
        # A standing root anyone but root could write refuses, with or without
        # approvals beneath it, and nothing is added.
        self.pt.root.mkdir();self.pt.root.chmod(0o775)
        with self.assertRaisesRegex(RuntimeError,'approval-root'):self.approve()
        self.pt.root.chmod(0o755);(self.pt.root/'approval').mkdir();(self.pt.root/'approval').chmod(0o775)
        with self.assertRaisesRegex(RuntimeError,'approval-root'):self.approve()
        self.assertEqual(self.approvals(),[])

    def test_an_approval_directory_already_standing_refuses(self):
        # The scan refuses anything standing that is not a complete approval,
        # so what the rename still finds is a name made during the run.
        (self.pt.root/'approval').mkdir(parents=True);self.pt.root.chmod(0o755);(self.pt.root/'approval').chmod(0o755)
        real=rootprog.write_new;made=[]
        def appears(path,data,mode):
            real(path,data,mode)
            if path.name=='approval.json':
                twin=path.parent.parent/hashlib.sha256(data).hexdigest();twin.mkdir();made.append(twin.name)
        with patch('tb_root.write_new',side_effect=appears),self.assertRaisesRegex(RuntimeError,'approval-new'):self.approve()
        self.assertEqual(self.approvals(),made)

    def test_root_reads_an_approval_by_name(self):
        digest=self.approve().split()[1]
        directory=self.pt.root/'approval'/digest
        with self.pt.as_root():
            with self.assertRaisesRegex(RuntimeError,'approval-digest'):payload.read_approval('not-a-digest')
            # A record whose bytes are not the pointer's digest.
            forged=self.pt.root/'approval'/('f'*64);forged.mkdir();(forged/'approval.json').write_bytes((directory/'approval.json').read_bytes())
            with self.assertRaisesRegex(RuntimeError,'approval-digest'):payload.read_approval('f'*64)
            # A record that no longer states a passed, lifted review.
            held=stand_approval(self.pt.root/'approval',dict(self.record,hold=True))
            with self.assertRaisesRegex(RuntimeError,'approval-record'):payload.read_approval(held)

    def run_root(self,*argv,uid=0):
        """The root program's main as sudo runs it, execv caught."""
        with self.pt.as_root(),patch('tb_root.os.geteuid',return_value=uid),patch.dict(os.environ,{'SUDO_UID':'1000'}),patch('tb_root.pwd.getpwnam',return_value=self.pt.user),\
             patch('sys.argv',['tb-root',*argv]),patch('tb_root.os.execv') as execv,contextlib.redirect_stdout(io.StringIO()):
            rootprog.main()
        return execv

    def test_the_root_program_takes_only_its_two_verbs(self):
        # #709 round four: every privileged step enters the hand-installed
        # program by one of two verbs, and anything else refuses by name.
        for argv in [['approve'],['approve',str(self.recordfile)],['approve',str(self.recordfile),'not-a-digest'],
                     ['approve',str(self.recordfile),order.sha(self.recordfile),'extra']]:
            with self.subTest(argv=argv),self.assertRaisesRegex(RuntimeError,'approve-arguments'):self.run_root(*argv)
        for argv in [[],['frob','provision','a'*64],['run','provision'],['python3','-I','-c','code']]:
            with self.subTest(argv=argv),self.assertRaisesRegex(RuntimeError,'known-verb'):self.run_root(*argv)
        with self.assertRaisesRegex(RuntimeError,'root-program'):self.run_root('approve',str(self.recordfile),order.sha(self.recordfile),uid=1000)
        self.assertFalse(self.pt.root.exists())

    def test_run_executes_only_a_complete_approvals_root_copy(self):
        # #709 round four: root runs the approval's root-owned copy of the
        # reviewed payload with python3 -I, and only from an approval found
        # complete. Perturbation: drop approval-complete from read_approval and
        # the tampered copy, and the partial directory, are executed.
        with self.assertRaisesRegex(RuntimeError,'approval-custody'):self.run_root('run','provision','a'*64)
        digest=self.approve().split()[1];directory=self.pt.root/'approval'/digest;copy_path=directory/'tb_payload.py'
        execv=self.run_root('run','load:own-x',digest,'512','b'*64)
        execv.assert_called_once_with('/usr/bin/python3',['/usr/bin/python3','-I',str(copy_path),'load:own-x',digest,'512','b'*64])
        # No approval of that digest: a run with no approval refuses.
        with self.assertRaisesRegex(RuntimeError,'approval-complete'):self.run_root('run','provision','c'*64)
        with self.assertRaisesRegex(RuntimeError,'approval-digest'):self.run_root('run','provision','../'+digest)
        with self.assertRaisesRegex(RuntimeError,'run-arguments'):self.run_root('run','provision',digest,'512')
        with self.assertRaisesRegex(RuntimeError,'run-arguments'):self.run_root('run','',digest)
        # The root copy tampered: never executed.
        kept=copy_path.read_bytes();copy_path.chmod(0o600);copy_path.write_bytes(b'import os\n')
        with self.assertRaisesRegex(RuntimeError,'approval-complete'):execv=self.run_root('run','provision',digest)
        copy_path.write_bytes(kept)
        self.assertEqual(self.run_root('run','provision',digest).call_count,1)
        # A complete approval whose record no longer states a passed, lifted
        # review is no approval to run. Perturbation: drop approval-record from
        # read_approval and it is executed.
        plan=copy.deepcopy(self.pt.plan);plan['install_root']=str(self.pt.root)
        for change in [dict(hold=True),dict(status='FAIL')]:
            with self.subTest(change=change):
                held=self.pt.stand(plan,**change)
                with self.pt.as_root():self.assertTrue(rootprog.complete(self.pt.root/'approval'/held))
                with self.assertRaisesRegex(RuntimeError,'approval-record'):self.run_root('run','provision',held)

    def test_complete_checks_every_file_of_an_approval(self):
        # #709 round four, P2: complete() held the directory and the private
        # record only. Each case changes one file and must refuse, and each has
        # its own perturbation in the condition that catches it.
        digest=self.approve().split()[1];directory=self.pt.root/'approval'/digest
        with self.pt.as_root():self.assertTrue(rootprog.complete(directory))
        def case(name,act,undo):
            with self.subTest(name):
                act()
                with self.pt.as_root():self.assertFalse(rootprog.complete(directory))
                undo()
                with self.pt.as_root():self.assertTrue(rootprog.complete(directory))
        for f in rootprog.FILES:
            keep=directory/f;aside=self.pt.base/('aside-'+f)
            case(f'{f} missing',lambda keep=keep,aside=aside:shutil.move(keep,aside),lambda keep=keep,aside=aside:shutil.move(aside,keep))
        extra=directory/'extra'
        case('an extra file',lambda:extra.write_text('x'),lambda:extra.unlink())
        pub=directory/'approval.pub.json';private=directory/'approval.json'
        case('the public copy widened',lambda:pub.chmod(0o666),lambda:pub.chmod(0o644))
        case('the private record opened',lambda:private.chmod(0o644),lambda:private.chmod(0o600))
        kept=pub.read_bytes()
        case('the public copy differs',lambda:(pub.chmod(0o600),pub.write_bytes(kept.replace(b'"version": 1',b'"version": 2')),pub.chmod(0o644)),
             lambda:(pub.chmod(0o600),pub.write_bytes(kept),pub.chmod(0o644)))
        # A FIFO in a copy's place, at the copy's mode: a read would block.
        # Perturbation: drop S_ISREG and this case hangs until the sweep's timeout.
        payload_copy=directory/'tb_payload.py';keep_payload=payload_copy.read_bytes()
        def to_fifo():payload_copy.unlink();os.mkfifo(payload_copy,0o600);payload_copy.chmod(0o600)
        def from_fifo():payload_copy.unlink();payload_copy.write_bytes(keep_payload);payload_copy.chmod(0o600)
        case('a FIFO in the payload copy\'s place',to_fifo,from_fifo)
        for f in ['plan.json','tb_payload.py']:
            p=directory/f;keep=p.read_bytes()
            case(f'{f} changed',lambda p=p:p.write_bytes(b'changed'),lambda p=p,keep=keep:p.write_bytes(keep))
        twin=self.pt.base/'twin'
        case('the payload copy has a second name',lambda:os.link(directory/'tb_payload.py',twin),lambda:twin.unlink())
        linked=directory/'plan.json';keep_plan=linked.read_bytes()
        def to_link():linked.unlink();(self.pt.base/'plan-target').write_bytes(keep_plan);linked.symlink_to(self.pt.base/'plan-target')
        def from_link():linked.unlink();linked.write_bytes(keep_plan);linked.chmod(0o600)
        case('a copy replaced by a link',to_link,from_link)
        # Named by a digest that is not its record's, a crash's pending
        # directory, and a directory opened to the group.
        moved=directory.with_name('e'*64);directory.rename(moved)
        with self.pt.as_root():self.assertFalse(rootprog.complete(moved))
        moved.rename(directory)
        pending=directory.with_name('.pending-'+'a'*64);pending.mkdir()
        with self.pt.as_root():self.assertFalse(rootprog.complete(pending))
        directory.chmod(0o775)
        with self.pt.as_root():self.assertFalse(rootprog.complete(directory))
        directory.chmod(0o755)

    def test_the_coordinator_refuses_what_it_cannot_verify(self):
        statefile=self.pt.base/'state.json';order.atomic(statefile,dict(cursor=0,done={},approval=None))
        log=self.pt.base/'approve.log'
        with patch.object(order,'APPROVAL_ROOT',self.pt.root/'approval'),patch.object(order,'APPROVAL_OWNER',os.getuid()):
            def silent(argv,stdout,**kw):return subprocess.CompletedProcess(argv,0)
            with patch('tb_order.subprocess.run',side_effect=silent),self.assertRaisesRegex(order.Refused,'approve-printed'):order.approve(statefile,self.recordfile,log)
            # Root printed a real approval, but of another record.
            other=stand_approval(self.pt.root/'approval',self.record)
            def elsewhere(argv,stdout,**kw):stdout.write(f'APPROVAL: {other}\n');stdout.flush();return subprocess.CompletedProcess(argv,0)
            with patch('tb_order.subprocess.run',side_effect=elsewhere),self.assertRaisesRegex(order.Refused,'approve-record'):order.approve(statefile,self.recordfile,log)
            self.assertIsNone(json.loads(statefile.read_text())['approval'])
            # A public copy whose bytes are not the pointer's digest.
            forged=self.pt.root/'approval'/('e'*64);forged.mkdir();(forged/'approval.pub.json').write_bytes((self.pt.root/'approval'/other/'approval.pub.json').read_bytes())
            with self.assertRaisesRegex(order.Refused,'approval-digest'):order.publication('e'*64)
        for argv,guard in [(['operator','--state',str(statefile),'approve'],'approve-record-named'),
                           (['operator','--state',str(statefile),'next',str(self.recordfile)],'no-record-outside-approve')]:
            with self.subTest(guard=guard),patch('sys.argv',argv),patch('tb_order.os.geteuid',return_value=1000),patch('tb_order.Order.operator') as operator,contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(order.main(),1)
            operator.assert_not_called();self.assertIn(guard,err.getvalue())

    def test_the_approval_covers_every_staged_script(self):
        f=Fixture('test_approval_refusals');f.setUp();self.addCleanup(f.doCleanups)
        driver_path=str(Path(order.__file__).resolve().with_name('tb_driver.py'))
        s=copy.deepcopy(f.state);s['approval']=stand_approval(f.approvals,dict(f.record,artifacts={k:v for k,v in f.record['artifacts'].items() if k!=driver_path}))
        with self.assertRaisesRegex(order.Refused,'approval-coverage'):f.o.approved(s)

if __name__ == '__main__':unittest.main()
