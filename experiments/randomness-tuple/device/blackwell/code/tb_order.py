#!/usr/bin/env python3
# conforms: blackwell-probe-tuple-held-field-for-field
# conforms: blackwell-probe-schedule-validated-whole
# conforms: blackwell-probe-one-command-one-seat-per-step
# conforms: blackwell-probe-approval-gates-every-step
# conforms: blackwell-probe-approval-in-root-custody
# conforms: blackwell-probe-wait-verifies-when-the-state-moves
# conforms: blackwell-probe-halt-is-evidence
# conforms: blackwell-probe-root-runs-no-operator-bytes
# conforms: blackwell-probe-identity-bound-to-approved-stacks
# conforms: blackwell-probe-refeed-completes-against-a-verified-source
"""TB sequencing, adapted from the W4a flock/atomic-state/driver-lease design.

This is experiment tooling for #679, not a product or conformance assertion.
Approval is supplied by the designated review seat, never by this program.
"""
import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import sections


RULING = re.compile(r'https://github\.com/toddwbucy/WeaverTools/(issues|pull)/[0-9]+(#issuecomment-[0-9]+)?')
DIGEST = re.compile(r'[0-9a-f]{64}')
REVIEW_SEAT = 'thinkpad-CC-WeaverTools-ReviewSeat'
# **Approval lives root-owned, never in the state file** (679.5, the ruling of
# 2026-09-26 on #698). `approve` writes each approval under a directory named
# by its own digest, and the state keeps that digest alone as a pointer.
APPROVAL_ROOT = Path('/var/lib/weaver-tb/approval')
APPROVAL_OWNER = 0
# The one root program, tb_root.py installed by hand at a fixed root-owned
# path after the operator checked its sha256 against the merged commit (the
# ruling of 2026-09-27 on #698). The probe's sudoers line names this path and
# nothing else: every privileged step enters here, and root is never handed
# bytes or a path the operator's uid can write.
ROOT_PROGRAM = '/usr/local/libexec/weaver-tb/tb-root'


class Refused(RuntimeError):
    pass


class Busy(Refused):
    pass


def elected(value):
    """A plan's boolean read by identity, never by equality: 1 == True in
    Python, and an election the validator equates with True that the driver's
    series() then reads as not-True would elect nothing. validate_plan and
    series() both read through here."""
    return value is True


def declined(value):
    return value is False


def same(a, b):
    """Two JSON values equal as JSON facts, compared as canonical text (#695):
    Python equality reads 512.0 as 512 and true as 1, so two records holding
    different facts would compare equal. validate_plan's tuple check compares
    this way for the same reason, and every equality between JSON-parsed
    values in the probe goes through here or checks each side's type."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def check(name, condition):
    if not condition:
        raise Refused(name)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.tb-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def ticks(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def live(lease):
    # A pid that is not an int names no process of its own: /proc/self is
    # the reader, and 1234.0 reads nothing. Both start ticks must be present,
    # since a dead pid reads None and a lease with no ticks holds None, and
    # two absences are not one process.
    if not (isinstance(lease, dict) and type(lease.get('pid')) is int and isinstance(lease.get('ticks'), str)):
        return False
    observed = ticks(lease['pid'])
    return observed is not None and observed == lease['ticks']


def leases(step):
    """Steps a fresh coding-seat process takes: an arm's start, and the report
    after the last arm's driver has exited. Every other coding-seat step must
    come from the process holding the lease."""
    return step.startswith('start:') or step == 'report'


def schedule(plan):
    steps = [('provision', 'operator')]
    for arm in plan['arms']:
        steps.append((f'start:{arm["name"]}', 'coding seat'))
        for job in arm['jobs']:
            steps.extend((f'{verb}:{job["id"]}', seat) for verb, seat in
                         [('load', 'operator'), ('measure', 'coding seat'), ('unload', 'operator'), ('settle', 'coding seat')])
        steps.append((f'finish:{arm["name"]}', 'coding seat'))
    return steps + [('report', 'coding seat'), ('review', 'review seat')]


def validate_plan(plan):
    check('schema', same(plan.get('version'), 1))
    check('agent', plan.get('agent') == 'bravo')
    # Two stacks are two roots: resolved, distinct, and neither inside the
    # other, since a B2 nested under B1 would put its bytes in the B1 install.
    # Each named as a nonempty string before a path is made of it: str(None)
    # is 'None', and a missing stack resolves to the working directory.
    stacks = [plan.get('stacks', {}).get(s) for s in ['B1', 'B2']]
    check('stacks-distinct', all(isinstance(r, str) and r for r in stacks))
    roots = [Path(r).resolve() for r in stacks]
    check('stacks-distinct', roots[0] != roots[1] and
          not roots[0].is_relative_to(roots[1]) and not roots[1].is_relative_to(roots[0]))
    check('isolated-root', plan.get('install_root') == '/var/lib/weaver-tb')
    # Compared as JSON, not as Python values: dict equality reads 1 as True and
    # 7.0 as 7, and series() elects on `is True`, so a tuple that equals this
    # one by value could still elect nothing.
    check('tuple', json.dumps(plan.get('tuple'), sort_keys=True) == json.dumps({
        'artifact': '/opt/weaver/models/Qwen3-8B-Q8_0.gguf',
        'weights_sha256': '0cfbf745760f07a76ddeb358dd025a27f2e11d1ca9c9a4169a373d52990fe86e',
        'devices': [0], 'context_capacity': 12288, 'max_tokens': 8192,
        'field_depth': 200, 'surprisal': True, 'residual': False,
        'identity': 'You are Karl, a careful writer. Answer plainly and at length when asked, and do not stop early.',
        'seeds': [451234785645, 1156316220, 7, 1000003, 123456789, 987654321, 2718281828, 3141592653],
        'runs_per_seed': 2, 'driver': '615.71.09'}, sort_keys=True))
    # Each ruling is the URL of the decision on this repository, an issue or
    # pull request, optionally one comment of it; a placeholder is refused.
    check('rulings', all(isinstance(plan.get('rulings', {}).get(k), str) and RULING.fullmatch(plan['rulings'][k])
                         for k in ['hold_lifted', 'cuda_provenance', 'control_count']))
    arms = plan['arms']
    check('arm-order', [a['name'] for a in arms] == ['TB0', 'TB-d', 'TB-k'])
    jobs = [j for a in arms for j in a['jobs']]
    import re
    check('job-identities', all(isinstance(j.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]+', j['id']) for j in jobs)
          and len({j['id'] for j in jobs}) == len(jobs))
    check('job-types', all(j['kind'] in ['free', 'refeed'] and j['stack'] in ['B1', 'B2'] for j in jobs))
    control = arms[0]['jobs']
    free = [j for j in control if j['kind'] == 'free']
    check('control-schedule', all(type(j.get('seed')) is int for j in free) and
          sorted(j['seed'] for j in free) == sorted(plan['tuple']['seeds'] * 2)
          and all(j['stack'] == 'B1' for j in control))
    own = [j for j in control if j['kind'] == 'refeed']
    check('own-refeeds', sorted(j['source_job'] for j in own) == sorted(j['id'] for j in free))
    prior = set()
    for j in jobs:
        check('source-order', j['kind'] == 'free' or
              (j.get('source_job') in prior) or (bool(j.get('source_trace')) and bool(j.get('source_run'))))
        prior.add(j['id'])
    check('device-sources', bool(arms[1]['jobs']) and
          {j.get('source_cell') for j in arms[1]['jobs']} == {'ampere', 'ada'} and
          all(j['kind'] == 'refeed' and j['stack'] == 'B1' for j in arms[1]['jobs']))
    # A TB-d job replays another device's reviewed trace. The loader and the
    # driver both prefer source_job, so one here would replay a local B1 run
    # under an ampere or ada label.
    check('device-traces', all(not j.get('source_job') and j.get('source_run') and
                               j.get('source_trace') in plan.get('files', {}) for j in arms[1]['jobs']))
    # Each job measures a different source record, and a trace file is one
    # device's: a selection repeated, or a trace shared between the cells,
    # would complete the arm without measuring one of them.
    selections = [(j.get('source_trace'), j.get('source_run')) for j in arms[1]['jobs']]
    cells = {cell: {j.get('source_trace') for j in arms[1]['jobs'] if j.get('source_cell') == cell}
             for cell in ['ampere', 'ada']}
    check('device-selections-distinct', len(set(selections)) == len(selections) and
          not cells['ampere'] & cells['ada'])
    # An emptied kernel arm names the comparison that empties it, hashed in the
    # manifest; approved() reads that report and requires its verdict.
    check('kernel-schedule', (elected(arms[2].get('executable_identity')) and not arms[2]['jobs'] and
                              arms[2].get('identity_report') in plan.get('files', {})) or
          (declined(arms[2].get('executable_identity', False)) and
           sorted(j.get('source_job') for j in arms[2]['jobs']) == sorted(j['id'] for j in free) and
           all(j['kind'] == 'refeed' and j['stack'] == 'B2' for j in arms[2]['jobs'])))


def well_formed_review(record):
    """The review record's own fields, the shape root holds at `approve` and
    the coordinator holds again at every step: the review passed, the hold is
    lifted, the seat is the named one, the reference is a decision's URL, and
    the plan and the payload are among the artifacts it names."""
    files = record.get('artifacts') if isinstance(record, dict) else None
    return (isinstance(files, dict) and all(isinstance(p, str) and isinstance(h, str) and DIGEST.fullmatch(h)
                                            for p, h in files.items())
            and record.get('status') == 'PASS' and record.get('hold') is False
            and record.get('seat') == REVIEW_SEAT
            and isinstance(record.get('reference'), str) and RULING.fullmatch(record['reference']) is not None
            and isinstance(record.get('plan'), str) and record['plan'] in files
            and isinstance(record.get('payload'), str) and record['payload'] in files)


def root_held(path):
    """Written by root and by nobody else since: owned by the approval's owner,
    closed to group and world writes, and not a link."""
    entry = os.lstat(path)
    return (not os.path.islink(path) and entry.st_uid == APPROVAL_OWNER and not entry.st_mode & 0o022)


def publication(pointer):
    """The approval the state's pointer names, read once from its root-owned
    public copy and held to the pointer's digest: the state says which
    approval, the record root wrote says what it approved. A pointer naming a
    file anyone but root could have written names nothing."""
    check('approval-digest', isinstance(pointer, str) and DIGEST.fullmatch(pointer) is not None)
    directory = APPROVAL_ROOT / pointer
    public = directory / 'approval.pub.json'
    try:
        held = all(root_held(p) for p in [APPROVAL_ROOT, directory, public])
    except OSError:
        held = False
    check('approval-custody', held)
    data = public.read_bytes()
    check('approval-digest', hashlib.sha256(data).hexdigest() == pointer)
    approval = json.loads(data)
    check('approval-record', isinstance(approval, dict) and well_formed_review(approval.get('record')))
    return approval


class Order:
    def __init__(self, state):
        self.path = Path(state).resolve()
        self.directory = self.path.parent

    def read(self):
        return json.loads(self.path.read_text())

    @contextlib.contextmanager
    def locked(self):
        with self.path.with_suffix('.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise Busy('another step is running') from error
            yield

    def approved(self, s):
        # **Approval is read from the record root wrote, never from the state**
        # (679.5): the state's `approval` is a pointer, and the hold, the
        # review's status, seat and reference, the plan's path and every
        # artifact's digest are the root-owned record's. `halt` and `cursor`
        # stay the operator's by design: a halt is the operator's right, and
        # the cursor selects a step whose every earlier receipt is verified.
        self.approval = approval = publication(s.get('approval'))
        record = approval['record']
        files = record['artifacts']
        required = {str(Path(__file__).resolve().parent / name) for name in
                    ['tb_order.py', 'tb_payload.py', 'tb_root.py', 'tb_driver.py', 'tb-operator.sh',
                     'test_tb.py', 'golden.py', 'perturb.py', 'sections.py', 'prepare.py']}
        check('approval-coverage', required <= files.keys())
        check('artifact-hashes', all(Path(p).is_file() and sha(p) == h for p, h in files.items()))
        check('halt', not s.get('halt'))
        # One snapshot: parse the bytes that matched the approved digest, never a re-read.
        data = Path(record['plan']).read_bytes()
        check('plan-snapshot', same(hashlib.sha256(data).hexdigest(), approval.get('plan', {}).get('sha256'))
              and same(approval['plan']['sha256'], files[record['plan']]))
        plan = json.loads(data)
        validate_plan(plan)
        check('manifest-coverage', bool(plan.get('files')) and set(plan['files']) <= files.keys())
        check('manifest-hashes', all(files[p] == h for p, h in plan['files'].items()))
        kernel = plan['arms'][2]
        if not kernel['jobs']:
            # One read of the approved report, hashed and parsed: it must be
            # sections.compare's verdict on B1 against B2, and that verdict true.
            data = Path(kernel['identity_report']).read_bytes()
            report = json.loads(data) if hashlib.sha256(data).hexdigest() == files[kernel['identity_report']] else {}
            check('identity-evidence', report.get('stacks') == ['B1', 'B2'] and report.get('executable_identity') is True)
            # A verdict is about the inventories it read, and those about the
            # stack bytes they hashed: each inventory is a reviewed artifact at
            # the digest the report names, and its host hashes are exactly the
            # approved hashes of every file under that stack.
            manifests = {}
            for stack in ['B1', 'B2']:
                named = (report.get('inputs') or {}).get(stack) or {}
                check('identity-inputs', named.get('manifest') in files and files[named['manifest']] == named.get('sha256'))
                raw = Path(named['manifest']).read_bytes()
                manifest = json.loads(raw) if hashlib.sha256(raw).hexdigest() == named['sha256'] else {}
                source = Path(plan['stacks'][stack])
                described = {str(source / rel): host.get('file_sha256') for rel, host in (manifest.get('hosts') or {}).items()}
                approved = {p: h for p, h in plan['files'].items() if Path(p).is_relative_to(source)}
                check('identity-binds-stacks', bool(described) and same(described, approved))
                manifests[stack] = manifest
                inputs = (report.get('inputs') or {})
            # The verdict is what the comparison says of those two verified
            # inventories now, not what the report claims: an approved report
            # that is not the comparison's own output over them empties
            # nothing. The manifests are the parsed bytes verified above, so
            # nothing is read twice.
            try:
                recomputed = sections.comparison(manifests['B1'], manifests['B2'], inputs)
            except ValueError:
                recomputed = None
            check('identity-recomputed', same(recomputed, report))
        return plan

    def due(self, s, plan):
        steps = schedule(plan)
        check('cursor', type(s.get('cursor')) is int and 0 <= s['cursor'] < len(steps))
        return steps[s['cursor']]

    def previous(self, s, plan):
        for step, _ in schedule(plan)[:s['cursor']]:
            done = s.get('done', {}).get(step, {})
            check('prior-success', done.get('status') == 'SUCCESS')
            # Every receipt names the approval it ran under, and a state runs
            # under one: a receipt of another approval is no step of this run.
            # Two absences compare equal, so the state's own is required here
            # rather than trusted to every caller having run approved() first.
            check('prior-approval', s.get('approval') is not None and same(done.get('approval'), s.get('approval')))
            check('prior-evidence', Path(done['path']).is_file() and sha(done['path']) == done['sha256'])

    def guard(self, s, plan, requested, seat):
        due, owner = self.due(s, plan)
        check('step-order', requested == due)
        check('seat', owner == seat)
        check('not-repeated', requested not in s.get('done', {}))
        self.previous(s, plan)
        if requested.startswith(('load:', 'measure:', 'unload:', 'settle:')):
            check('driver-live', live(s.get('driver')))
        if seat == 'coding seat' and not leases(requested):
            check('driver-owner', same(s.get('driver', {}).get('pid'), os.getpid()))

    def finish(self, s, step, evidence, sink=None):
        done = dict(status='SUCCESS', path=str(evidence), sha256=sha(evidence), approval=s['approval'])
        # A free run's measure receipt also holds its sink as it stood at the
        # run's turn.closed: the prefix through that line, by length and
        # digest, which a later re-feed of that run is snapshotted against.
        if sink is not None:
            done['sink'] = sink
        s.setdefault('done', {})[step] = done
        s['cursor'] += 1
        atomic(self.path, s)

    def fail(self, error):
        with self.locked():
            s = self.read()
            s['halt'] = str(error)
            s.setdefault('refusals', []).append(dict(at=time.time(), reason=str(error)))
            atomic(self.path, s)

    def operator(self, requested='next', runner=None):
        try:
            return self._operator(requested, runner)
        except Busy:
            raise
        except (Refused, OSError, ValueError, KeyError) as error:
            with self.locked():
                s = self.read()
                s.setdefault('refusals', []).append(dict(at=time.time(), reason=str(error), requested=requested))
                atomic(self.path, s)
            raise

    def _operator(self, requested, runner):
        with self.locked():
            s = self.read()
            if requested == 'next' and s.get('approval') is None:
                print('WAITING ON: review seat - publish the review record, then the operator runs approve')
                return
            plan = self.approved(s)
            if requested == 'next' and same(s.get('cursor'), len(schedule(plan))):
                # Completion is a claim about every receipt, so every receipt is
                # verified before it is made.
                self.previous(s, plan)
                print('COMPLETE: every step is recorded, the review seat\'s review included')
                return
            due, seat = self.due(s, plan)
            if requested == 'next' and seat != 'operator':
                print(f'WAITING ON: {seat} - {due}')
                return
            step = due if requested == 'next' else requested
            self.guard(s, plan, step, 'operator')
            extra = self.source_sink(s, plan, step)
            fd, name = tempfile.mkstemp(prefix='scheduled-', suffix='.log', dir=self.directory)
            os.close(fd)
            log = Path(name)
            try:
                result = (runner or payload)(s, step, log, *extra)
                check('payload-exit', result == 0)
                check('payload-receipt', log.read_text().splitlines()[-1:] == [f'SUCCESS: {step}'])
                self.finish(s, step, log)
                print(f'DONE: {step} (transcript {log})')
                nxt, owner = self.due(s, plan)
                print(f'NEXT: {owner} - {nxt}')
            except BaseException as error:
                s['halt'] = f'{step}: {error}; transcript {log}'
                atomic(self.path, s)
                raise

    def source_sink(self, s, plan, step):
        """What root is handed beside a local re-feed's load: the length and
        digest its source run's sink was recorded at, from that run's measure
        receipt. Nothing for any other step."""
        if not step.startswith('load:'):
            return ()
        job = next(j for arm in plan['arms'] for j in arm['jobs'] if j['id'] == step.split(':', 1)[1])
        if not job.get('source_job'):
            return ()
        done = s.get('done', {}).get(f'measure:{job["source_job"]}', {})
        sink = done.get('sink') or {}
        expected = str(Path(plan['install_root']) / 'sinks' / job['source_job'] / 'trace.ndjson')
        # **The state's copy is checked against evidence this step verifies
        # itself** (#690 C2.11, the custody rule of section 5): the measure
        # result is read once and parsed only after its bytes match the
        # receipt's digest, and the sink it recorded at the run's close must
        # be the state's copy. Refused here, before root is invoked, so a
        # malformed or substituted state creates nothing under the install
        # root: a digest is 64 lowercase hex.
        try:
            data = Path(done['path']).read_bytes()
            recorded = json.loads(data).get('sink') if hashlib.sha256(data).hexdigest() == done.get('sha256') else None
        except (KeyError, OSError, ValueError, AttributeError):
            recorded = None
        check('source-sink-recorded', sink.get('path') == expected and type(sink.get('length')) is int
              and sink['length'] > 0 and isinstance(sink.get('sha256'), str)
              and re.fullmatch(r'[0-9a-f]{64}', sink['sha256']) is not None and same(recorded, sink))
        return (str(sink['length']), sink['sha256'])

    def coding(self, step, evidence, sink=None):
        """Record a coding-seat step, and answer the receipts as they now
        stand, so the driver reads each evidence file once against the digest
        the coordinator holds rather than by path alone."""
        with self.locked():
            s = self.read()
            plan = self.approved(s)
            self.guard(s, plan, step, 'coding seat')
            if leases(step):
                check('no-live-driver', not live(s.get('driver')))
                s['driver'] = dict(pid=os.getpid(), ticks=ticks(os.getpid()))
            if step == 'report':
                check('report-evidence', Path(evidence).is_file())
            self.finish(s, step, evidence, sink)
            return copy.deepcopy(s['done'])

    def wait(self, step, timeout=14400, poll=1):
        deadline = time.monotonic() + timeout
        verified = None
        while True:
            try:
                with self.locked():
                    raw = self.path.read_bytes()
                    s = json.loads(raw)
                    check('wait-owner', live(s.get('driver')) and same(s['driver']['pid'], os.getpid()))
                    # approved() hashes every reviewed artifact, the model and both
                    # stacks included, under the lock that next needs. Only a state
                    # change can make the step due, so the full verification runs
                    # when the state moves, and always before returning.
                    if raw != verified:
                        plan = self.approved(s)
                        if self.due(s, plan)[0] == step:
                            self.previous(s, plan)
                            # The receipts previous() has just verified,
                            # handed to the driver so what it reads next it
                            # reads against these digests.
                            return copy.deepcopy(s.get('done', {}))
                        check('wait-order', self.due(s, plan)[1] == 'operator')
                        verified = raw
            except Busy:
                pass
            check('wait-deadline', time.monotonic() < deadline)
            time.sleep(min(poll, max(0, deadline - time.monotonic())))


def notice(step):
    message = f'WAITING ON OPERATOR: TB {step}; run handoffs/tb/tb-operator.sh next only after HOLD is lifted and approval recorded.'
    print(message, flush=True)
    try:
        subprocess.run(['gh', 'issue', 'comment', '679', '--repo', 'toddwbucy/WeaverTools', '--body', message],
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def payload(state, step, log, *sink):
    with log.open('w') as out:
        # Root is handed no bytes and no path the operator's uid can write:
        # the step, the approval's digest and, for a local re-feed's load, its
        # source sink's recorded length and digest. The root program finds that
        # approval complete in root custody and executes its root-owned copy of
        # the reviewed payload (#709 round four), which takes the plan and the
        # artifact map from the same record, never from this state file.
        return subprocess.run(['sudo', ROOT_PROGRAM, 'run', step, state['approval'], *sink],
                              stdin=subprocess.DEVNULL,
                              stdout=out, stderr=subprocess.STDOUT).returncode


def approve(state_path, record, log):
    """`tb-operator.sh approve <record>`, the one privileged approval step
    (679.5): sudo runs the hand-installed root program, which reads the review
    record and every artifact it names once, as data, verifies each digest
    before its first write, and snapshots the approval root-owned. The trust
    anchor is the operator's hash check of that program at install time, so
    this step checks nothing root does not check again. The state learns only the digest root
    printed, and only once the public copy it names is root's and matches it
    and the record digest taken before sudo.

    **Safe to retry after an interruption.** Dying after root commits and
    before the state is written leaves an approval the state does not name.
    The retry hands root the same record, root adopts the approval it already
    made, and the pointer is recorded then, once."""
    order = Order(state_path)
    with order.locked():
        s = order.read()
        # A state runs under one approval. A second, once steps may have run
        # under the first, would swap the plan beneath them, so a new approval
        # is a new state, refused here before root writes anything.
        check('one-approval-per-state', s.get('approval') is None)
        target = Path(record).resolve()
        # The record is hashed once, here, and that digest is what root holds
        # its own read to and what the approval is checked against after:
        # the target is never read again once root has run.
        record_sha = sha(target)
        with log.open('w') as out:
            code = subprocess.run(['sudo', ROOT_PROGRAM, 'approve', str(target), record_sha],
                                  stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT).returncode
        check('approve-exit', code == 0)
        printed = [line.split(' ', 1)[1] for line in log.read_text().splitlines() if line.startswith('APPROVAL: ')]
        check('approve-printed', len(printed) == 1)
        approval = publication(printed[0])
        check('approve-record', same(approval.get('record_sha256'), record_sha))
        s['approval'] = printed[0]
        atomic(order.path, s)
        return printed[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True)
    parser.add_argument('step', nargs='?', default='next')
    parser.add_argument('record', nargs='?')
    args = parser.parse_args()
    try:
        check('operator-not-root', os.geteuid() != 0)
        if args.step == 'approve':
            check('approve-record-named', args.record is not None)
            state = Path(args.state).resolve()
            fd, name = tempfile.mkstemp(prefix='approve-', suffix='.log', dir=state.parent)
            os.close(fd)
            digest = approve(state, args.record, Path(name))
            print(f'APPROVED: {digest} (transcript {name}); NEXT: operator - next')
            return 0
        check('no-record-outside-approve', args.record is None)
        Order(args.state).operator(args.step)
    except (Refused, OSError, ValueError, KeyError) as error:
        print(f'REFUSED: {error}; NEXT: review seat - rule on refusal', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
