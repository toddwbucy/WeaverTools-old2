#!/usr/bin/python3 -I
# conforms: blackwell-probe-root-runs-no-operator-bytes
# conforms: blackwell-probe-approval-in-root-custody
"""The probe's one root program, installed by hand at a fixed root-owned path.

The operator installs this file once, with `sudo install -o root -g root -m
0755`, after checking its sha256 by eye against the file at the merged commit
(the ruling of 2026-09-27 on #698). The probe's one sudoers line names that
path and nothing else, so every privileged step enters here, and the trust
anchor is that install-time check of the one program everything goes through.

Two verbs. `approve <record> <record-sha256>` reads the review record and
every artifact it names as data, verifies each digest, and snapshots the
approval root-owned. `run <step> <approval-digest> [length digest]` reads a
complete approval by its digest and executes its root-owned copy of the
reviewed payload with `python3 -I <path>`. Nothing this program executes is
bytes the operator's uid can write.

Stdlib only, standalone: it imports nothing of the probe, and restates the
few rules it shares with the coordinator and the payload.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import sys
import time

ROOT = Path('/var/lib/weaver-tb')
APPROVAL = 'approval'
PYTHON = '/usr/bin/python3'
REVIEW_SEAT = 'thinkpad-CC-WeaverTools-ReviewSeat'
RULING = re.compile(r'https://github\.com/toddwbucy/WeaverTools/(issues|pull)/[0-9]+(#issuecomment-[0-9]+)?')
DIGEST = re.compile(r'[0-9a-f]{64}')
# Every file an approval directory holds, at the mode `approve` writes it.
FILES = {'approval.json': 0o600, 'approval.pub.json': 0o644, 'plan.json': 0o600, 'tb_payload.py': 0o600}
# The ancestor a custody walk stops at, the filesystem root.
TRUSTED = Path('/')


def need(name, condition):
    if not condition:
        raise RuntimeError(name)


def read_once(path, follow=True):
    """A file's bytes in one read, refusing a link where `follow` is off."""
    fd = os.open(path, os.O_RDONLY | (0 if follow else os.O_NOFOLLOW))
    with os.fdopen(fd, 'rb') as stream:
        return stream.read()


def locked(path):
    """Only root can change the entry: owned by this program's user, no group
    or world write, not a link."""
    entry = os.lstat(path)
    return (not stat.S_ISLNK(entry.st_mode) and entry.st_uid == os.geteuid() and
            not entry.st_mode & 0o022)


def chain_custody(path):
    """Every directory from path's parent up to TRUSTED is one the operator
    cannot rename an entry out of: a real directory, owned by this program's
    user or by root, closed to group and world writes."""
    directory = Path(path).parent
    while True:
        entry = os.lstat(directory)
        if not stat.S_ISDIR(entry.st_mode) or entry.st_uid not in (os.geteuid(), 0) or entry.st_mode & 0o022:
            return False
        if directory == TRUSTED or directory.parent == directory:
            return directory == TRUSTED
        directory = directory.parent


def well_formed_review(record):
    """The review record's fields as root holds them, the coordinator's rule
    restated: passed, the hold lifted, the named seat, a decision's URL, and
    the plan and the payload among the artifacts named."""
    files = record.get('artifacts') if isinstance(record, dict) else None
    return (isinstance(files, dict) and all(isinstance(p, str) and isinstance(h, str) and DIGEST.fullmatch(h)
                                            for p, h in files.items())
            and record.get('status') == 'PASS' and record.get('hold') is False
            and record.get('seat') == REVIEW_SEAT
            and isinstance(record.get('reference'), str) and RULING.fullmatch(record['reference']) is not None
            and isinstance(record.get('plan'), str) and record['plan'] in files
            and isinstance(record.get('payload'), str) and record['payload'] in files)


def write_new(path, data, mode):
    """A file root creates and nobody held a name for: O_EXCL and O_NOFOLLOW,
    so the write lands in a new regular file or not at all."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, mode)


def complete(held):
    """An approval directory exactly as `approve` leaves it at its rename,
    every file of it checked (#709 round four): named by the digest of its own
    `approval.json`, locked, no link, holding the four files and nothing else,
    each a regular locked file of one name at its written mode, the public
    copy the private record's bytes, and both copies hashing as the record
    says. A `.pending-` directory a crash left, a file missing, added,
    widened or changed, is not an approval."""
    try:
        if held.is_symlink() or not held.is_dir() or not locked(held):
            return False
        if sorted(os.listdir(held)) != sorted(FILES):
            return False
        for name, mode in FILES.items():
            entry = os.lstat(held / name)
            # A regular file, never a FIFO or a device, which a read would
            # block on or reach through.
            if not (stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1 and locked(held / name)
                    and stat.S_IMODE(entry.st_mode) == mode):
                return False
        body = read_once(held / 'approval.json', follow=False)
        approval = json.loads(body)
        return (hashlib.sha256(body).hexdigest() == held.name
                and read_once(held / 'approval.pub.json', follow=False) == body
                and approval['plan']['copy'] == 'plan.json' and approval['payload']['copy'] == 'tb_payload.py'
                and hashlib.sha256(read_once(held / 'plan.json', follow=False)).hexdigest() == approval['plan']['sha256']
                and hashlib.sha256(read_once(held / 'tb_payload.py', follow=False)).hexdigest()
                == approval['payload']['sha256'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def approve(record_path, expected):
    """**The one approval step** (679.5, the rulings of 2026-09-26 and
    2026-09-27 on #698). Root reads the review record once, refusing a link,
    holds it to the digest the coordinator took before sudo, and reads every
    artifact it names once, each held to its digest before the first write.
    It copies the reviewed payload and the plan root-owned and writes
    `approval.json` (0600) and `approval.pub.json` (0644), the same bytes,
    into a directory named by their digest, which it prints. Everything it
    reads is data: this program executes none of it. A refusal leaves nothing
    behind.

    **A record approved before is adopted, not approved again**: its complete
    approval is found and its digest printed, and nothing is written, which is
    what makes the step safe to retry when the coordinator died after root
    committed and before the state learned the pointer. Anything in the
    approvals that is not a complete approval refuses by name and is never
    adopted, since an interrupted step is never silently resumed."""
    try:
        raw = read_once(record_path, follow=False)
        record = json.loads(raw)
    except (OSError, ValueError):
        record = None
    need('approval-record', well_formed_review(record))
    record_sha = hashlib.sha256(raw).hexdigest()
    need('approval-record-digest', record_sha == expected)
    approvals = ROOT / APPROVAL
    matches = []
    if approvals.exists():
        need('approval-root', locked(ROOT) and locked(approvals))
        for held in sorted(approvals.iterdir()):
            need('approval-complete', complete(held))
            if json.loads(read_once(held / 'approval.json', follow=False)).get('record_sha256') == record_sha:
                matches.append(held)
        need('approval-once', len(matches) <= 1)
    elif ROOT.exists():
        need('approval-root', locked(ROOT))
    need('root-chain-custody', chain_custody(ROOT))
    if matches:
        # The approval this record already has, finished and renamed before
        # whatever interrupted the run that made it, every file of it checked
        # by complete() above: adopted whole, and nothing written.
        print(f'APPROVAL: {matches[0].name}', flush=True)
        return matches[0].name
    kept = {}
    for path, digest in record['artifacts'].items():
        data = Path(path).read_bytes()
        need('approval-artifacts', hashlib.sha256(data).hexdigest() == digest)
        if path in (record['plan'], record['payload']):
            kept[path] = data
    plan = json.loads(kept[record['plan']])
    need('fixed-root-agent', plan['install_root'] == str(ROOT) and plan['agent'] == 'bravo')
    need('operator', type(plan['operator_uid']) is int and
         pwd.getpwnam(plan['operator']).pw_uid == plan['operator_uid'] == int(os.environ['SUDO_UID']))
    # Everything is verified. From here each directory made is recorded, so a
    # failed write removes exactly what this run made and nothing else.
    made = []
    pending = approvals / f'.pending-{record_sha}'
    try:
        for directory in [ROOT, approvals]:
            if not directory.exists():
                directory.mkdir(mode=0o755)
                os.chmod(directory, 0o755)
                made.append(directory)
        pending.mkdir(mode=0o700)
        made.append(pending)
        write_new(pending / 'plan.json', kept[record['plan']], FILES['plan.json'])
        write_new(pending / 'tb_payload.py', kept[record['payload']], FILES['tb_payload.py'])
        body = (json.dumps(dict(
            version=1, record_sha256=record_sha, record=record,
            plan=dict(path=record['plan'], sha256=record['artifacts'][record['plan']], copy='plan.json'),
            payload=dict(path=record['payload'], sha256=record['artifacts'][record['payload']], copy='tb_payload.py'),
            approved_by_uid=int(os.environ['SUDO_UID']), approved_at=time.time()), sort_keys=True, indent=1) + '\n').encode()
        digest = hashlib.sha256(body).hexdigest()
        write_new(pending / 'approval.json', body, FILES['approval.json'])
        write_new(pending / 'approval.pub.json', body, FILES['approval.pub.json'])
        os.chmod(pending, 0o755)
        final = approvals / digest
        need('approval-new', not final.exists() and not final.is_symlink())
        os.rename(pending, final)
    except BaseException:
        for directory in reversed(made):
            shutil.rmtree(directory, ignore_errors=True)
        raise
    print(f'APPROVAL: {digest}', flush=True)
    return digest


def read_approval(pointer):
    """The approval a step runs under, named by the digest the coordinator
    handed over: a complete approval directory in root custody, every file of
    it checked, whose record still states a passed, lifted review."""
    need('approval-digest', isinstance(pointer, str) and DIGEST.fullmatch(pointer) is not None)
    approvals = ROOT / APPROVAL
    directory = approvals / pointer
    try:
        held = all(locked(p) for p in [ROOT, approvals])
    except OSError:
        held = False
    need('approval-custody', held and chain_custody(ROOT))
    need('approval-complete', complete(directory))
    approval = json.loads(read_once(directory / 'approval.json', follow=False))
    need('approval-record', well_formed_review(approval.get('record')))
    return approval, directory


def run(step, pointer, source_sink):
    """Execute the approved payload for one step: the root-owned copy the
    approval holds, found complete, never a file the operator's uid can write.
    The payload is handed the step, the approval's digest and a local
    re-feed's recorded sink, and reads the plan from the same approval."""
    need('run-arguments', isinstance(step, str) and step != '' and len(source_sink) in (0, 2))
    _, directory = read_approval(pointer)
    copy = directory / 'tb_payload.py'
    os.execv(PYTHON, [PYTHON, '-I', str(copy), step, pointer, *source_sink])


def main():
    need('root-program', os.geteuid() == 0)
    verb = sys.argv[1:2]
    if verb == ['approve']:
        need('approve-arguments', len(sys.argv) == 4 and DIGEST.fullmatch(sys.argv[3]) is not None)
        approve(sys.argv[2], sys.argv[3])
        print('SUCCESS: approve', flush=True)
        return
    need('known-verb', verb == ['run'] and len(sys.argv) >= 4)
    run(sys.argv[2], sys.argv[3], sys.argv[4:])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'REFUSED: {error}; NEXT: review seat - inspect partial state, do not retry blindly', file=sys.stderr)
        sys.exit(1)
