#!/usr/bin/env python3
# conforms: blackwell-probe-tuple-held-field-for-field
# conforms: blackwell-probe-root-runs-no-operator-bytes
# conforms: blackwell-probe-approval-in-root-custody
# conforms: blackwell-probe-operator-input-read-once
# conforms: blackwell-probe-served-tree-locked-and-verified
# conforms: blackwell-probe-model-in-custody-on-both-paths
# conforms: blackwell-probe-installation-refuses-to-adopt
# conforms: blackwell-probe-load-stands-on-the-interlock
# conforms: blackwell-probe-refeed-completes-against-a-verified-source
"""Operator-only TB payload, run by root only from the approval's root-owned copy.

tb_root.py, the one hand-installed root program, executes this file with -I from
the approval directory it found complete, never from the operator's staging.
Stdlib only, closed stdin. Never run it directly.
All mutations belong to the isolated TB installation and the bravo account.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import grp
import re
import shutil
import stat
import subprocess
import sys
import time

ROOT = Path('/var/lib/weaver-tb')
MODEL = Path('/opt/weaver/models/Qwen3-8B-Q8_0.gguf')
# Every directory of a stack a load can execute from: the binaries, and the
# two library directories environment() puts on LD_LIBRARY_PATH. sections.py
# inventories exactly this set, so the identity verdict covers what is served;
# a directory served from outside it is a test failure, not silent drift.
STACK_ROOTS = ('bin', 'engine-lib', 'cuda-lib')
# The approvals tb_root.py's `approve` writes, each in a directory named by its digest,
# beneath the install root and outside everything provision serves (679.5).
APPROVAL = 'approval'
REVIEW_SEAT = 'thinkpad-CC-WeaverTools-ReviewSeat'
RULING = re.compile(r'https://github\.com/toddwbucy/WeaverTools/(issues|pull)/[0-9]+(#issuecomment-[0-9]+)?')
DIGEST = re.compile(r'[0-9a-f]{64}')


def same(a, b):
    """Two JSON values equal as JSON facts, compared as canonical text: Python
    equality reads 512.0 as 512 and true as 1. The coordinator's same(); this
    file runs from its own verified bytes and imports nothing of the probe."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def need(name, condition):
    if not condition:
        raise RuntimeError(name)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_once(path, follow=True):
    """A file's bytes in one read, refusing a link where `follow` is off."""
    fd = os.open(path, os.O_RDONLY | (0 if follow else os.O_NOFOLLOW))
    with os.fdopen(fd, 'rb') as stream:
        return stream.read()


def well_formed_review(record):
    """The review record's fields as root holds them, the coordinator's rule
    restated here because root runs this file alone: passed, the hold lifted,
    the named seat, a decision's URL, and the plan and the payload among the
    artifacts named."""
    files = record.get('artifacts') if isinstance(record, dict) else None
    return (isinstance(files, dict) and all(isinstance(p, str) and isinstance(h, str) and DIGEST.fullmatch(h)
                                            for p, h in files.items())
            and record.get('status') == 'PASS' and record.get('hold') is False
            and record.get('seat') == REVIEW_SEAT
            and isinstance(record.get('reference'), str) and RULING.fullmatch(record['reference']) is not None
            and isinstance(record.get('plan'), str) and record['plan'] in files
            and isinstance(record.get('payload'), str) and record['payload'] in files)


def read_approval(pointer):
    """The approval a later step runs under, read once from its root-owned
    record and held to the digest the coordinator handed over: the plan's
    digest, the payload's digest and the artifact map are this record's and
    never the operator's state file's (679.5)."""
    need('approval-digest', isinstance(pointer, str) and DIGEST.fullmatch(pointer) is not None)
    directory = ROOT / APPROVAL / pointer
    record = directory / 'approval.json'
    try:
        held = all(locked(p) for p in [ROOT, ROOT / APPROVAL, directory, record])
    except OSError:
        held = False
    need('approval-custody', held and chain_custody(ROOT))
    raw = read_once(record, follow=False)
    need('approval-digest', hashlib.sha256(raw).hexdigest() == pointer)
    approval = json.loads(raw)
    need('approval-record', well_formed_review(approval.get('record')))
    return approval, directory


def freeze(source, destination, length=None):
    """Read an operator-owned file once into a new root-owned private file.

    Every consumer after this receives the destination, never the source path:
    a check on the source followed by a second read of it binds nothing. With
    a length, only that many leading bytes are copied: a sink recorded at a
    run's close is frozen as it stood then, whatever the unload appended.
    """
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as dst, open(source, 'rb') as src:
            if length is None:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            else:
                remaining = length
                while remaining > 0:
                    block = src.read(min(remaining, 1024 * 1024))
                    if not block:
                        break
                    dst.write(block)
                    remaining -= len(block)
            dst.flush()
            os.fsync(dst.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def snapshot(source, digest, destination, length=None):
    """freeze(), then verify the frozen bytes, not the source, against the recorded digest.

    A short source fails the same check: fewer bytes than the recorded length
    never hash to the recorded digest."""
    freeze(source, destination, length)
    try:
        need('snapshot-hash', sha(destination) == digest)
    except RuntimeError:
        destination.unlink()
        raise
    return destination


def select_run(whole, run_id, destination):
    """The one run a replay names, cut from a snapshot: derive refuses a record holding two."""
    lines = [line for line in whole.read_bytes().splitlines(keepends=True)
             if line.strip() and json.loads(line)['run'] == run_id]
    need('source-run-selected', bool(lines))
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as dst:
        dst.writelines(lines)
        dst.flush()
        os.fsync(dst.fileno())
    return destination


def account_exists(name):
    try:
        pwd.getpwnam(name)
    except KeyError:
        return False
    return True


def group_exists(name):
    try:
        grp.getgrnam(name)
    except KeyError:
        return False
    return True


def make_locked(directory):
    """Every missing component of directory's chain, made one at a time and
    locked as it is made: mkdir(parents=True) would make the intermediate
    ones at the umask, and lock() reaches only the directory it is given."""
    missing = []
    while not directory.exists():
        missing.append(directory)
        directory = directory.parent
    for component in reversed(missing):
        component.mkdir(mode=0o755)
        lock(component, 0o755)


def model_chain_held():
    """The model's directory chain as it stands before this payload writes:
    from the nearest existing ancestor of MODEL up to TRUSTED. Checked before
    the first write so a renameable ancestor refuses with nothing made,
    rather than after the snapshot with ROOT already standing."""
    directory = MODEL.parent
    while not directory.exists():
        directory = directory.parent
    return chain_custody(directory / MODEL.name)


def run(argv, **kw):
    """A privileged command that exits nonzero is a named refusal, its output
    kept in the transcript first: never an unnamed exception."""
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, text=True, **kw)
    if result.returncode != 0:
        if kw.get('capture_output'):
            print(result.stdout, end='')
            print(result.stderr, end='', file=sys.stderr)
        print(f'{argv[0]} exited {result.returncode}', file=sys.stderr)
    need('command-exit', result.returncode == 0)
    return result


def m1_reading():
    """The interlock's four facts as they stand now, read without privilege, so
    the driver takes the same reading at a measurement's close that root takes
    at the load and the unload. No installed admin invocation. A missing unit
    alone is not enough: a surviving coordination door or member/worker process
    also stands. A fact that cannot be read is recorded as unread, never as
    clear.

    **Every fact maps any failure to read it to unread** (#693 thread 2): the
    unit's state to `readable` false, the door and the process scan to None,
    which m1_clear() rejects. A process that vanished mid-scan is the one
    failure that reads as absent, since it is. And a /proc mounted with
    `hidepid` hides other users' processes from an unprivileged reader
    without any error, so the scan is unread there rather than empty."""
    try:
        answer = subprocess.run(['/usr/bin/systemctl', 'show', 'weaver-worker@m1.service',
                                 '--property=ActiveState', '--property=LoadState'],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True)
        values = dict(line.split('=', 1) for line in answer.stdout.splitlines() if '=' in line)
        readable = answer.returncode == 0 and values.get('LoadState') in ['loaded', 'not-found']
    except OSError:
        values, readable = {}, False
    door = door_state(Path('/run/weaver-m1/coordination.sock'))
    try:
        uid = pwd.getpwnam('weaver-m1').pw_uid
    except KeyError:
        uid = None
    process = False
    try:
        if os.geteuid() != 0 and proc_hides_processes():
            process = None
        else:
            for entry in Path('/proc').iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    process = process or (uid is not None and entry.stat().st_uid == uid)
                except FileNotFoundError:
                    pass
    except OSError:
        process = None
    return dict(readable=readable, active_state=values.get('ActiveState'), door=door, process=process)


def door_state(path):
    """Whether a path stands, read by stat so a refused look stays refused:
    True where it stands, False only where the kernel says there is no such
    file, and None for any other failure. `Path.exists()` is not used because
    on Python 3.14 it answers False for a path behind a denied directory
    (#693), which would read an unreadable m1 door as absent and clear."""
    try:
        os.stat(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return None


def proc_hides_processes():
    """Whether /proc is mounted with a hidepid option that hides other users'
    processes, read from this process's own mount table."""
    for line in Path('/proc/self/mounts').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[1] == '/proc' and fields[2] == 'proc':
            for option in fields[3].split(','):
                if option.startswith('hidepid=') and option.split('=', 1)[1] not in ('0', 'off'):
                    return True
    return False


def m1_clear(reading):
    """Whether a reading shows m1 absent on all four facts."""
    return (reading['readable'] is True and reading['active_state'] == 'inactive' and
            reading['door'] is False and reading['process'] is False)


def m1_unloaded(when='load'):
    """The interlock at a load, each fact refusing by its own name, and the
    reading printed to the transcript that is this step's receipt."""
    reading = m1_reading()
    print(f'INTERLOCK at {when}: {json.dumps(reading, sort_keys=True)}', flush=True)
    need('m1-state-readable', reading['readable'])
    need('m1-inactive', reading['active_state'] == 'inactive')
    need('m1-no-door', reading['door'] is False)
    need('m1-no-process', reading['process'] is False)
    return reading


def config(stack):
    return ROOT / 'config' / stack


def environment(stack):
    return dict(PATH='/usr/bin:/bin', WEAVER_ADMIN_CONFIG=str(config(stack)),
                LD_LIBRARY_PATH=f'{ROOT}/stacks/{stack}/engine-lib:{ROOT}/stacks/{stack}/cuda-lib')


def admin(stack, verb):
    return [str(ROOT / 'stacks' / stack / 'bin/weaver-admin'), verb, 'bravo']


def answer(stack, verb, expected):
    result = run(admin(stack, verb), env=environment(stack), capture_output=True, timeout=600)
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    need('admin-answer', bool(rows) and rows[-1].get('kind') == 'state' and rows[-1].get('state') == expected)
    return rows[-1]


def save(path, text, mode=0o644):
    """A file root writes beneath a held chain: refused by name if its name is a
    link, and opened O_NOFOLLOW so the write is pinned to a regular file at
    that name whatever changes between the check and the open. O_TRUNC, not
    O_EXCL, because the declaration is rewritten at every load."""
    need('no-symlink-destination', not path.is_symlink())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(mode)


def locked(path):
    """Only this payload's user can change the entry: owned by it, no group or
    world write, not a link. A hash binds bytes only where nobody else can
    replace them, and for a directory that means its entries too."""
    entry = os.lstat(path)
    return (not stat.S_ISLNK(entry.st_mode) and entry.st_uid == os.geteuid() and
            not entry.st_mode & 0o022)


def lock(path, mode):
    """Set the served mode on path, a directory or a file, and every entry
    beneath a directory, the root included: rglob yields descendants only."""
    path.chmod(mode)
    if path.is_dir():
        for p in path.rglob('*'):
            if not p.is_symlink():
                p.chmod(0o755 if p.is_dir() or p.parent.name == 'bin' else 0o644)


def served_directories():
    """Every directory root serves the agent from, outside the stack trees."""
    return [ROOT, ROOT / 'stacks', ROOT / 'config', ROOT / 'agents',
            *(config(s) for s in ['B1', 'B2']), *(ROOT / 'agents' / s for s in ['B1', 'B2'])]


def verify_stack(plan, stack, root):
    """The installed copy holds exactly the reviewed files, by bytes, and no
    link, in a tree nobody but this payload's user can change."""
    source = Path(plan['stacks'][stack])
    entries = list(root.rglob('*'))
    need('installed-no-symlinks', not root.is_symlink() and not any(p.is_symlink() for p in entries))
    need('installed-stack-custody', locked(root) and all(locked(p) for p in entries))
    expected = {Path(p).relative_to(source): d for p, d in plan['files'].items() if Path(p).is_relative_to(source)}
    need('installed-stack-coverage', {p.relative_to(root) for p in entries if p.is_file()} == expected.keys())
    need('installed-stack-hash', all(sha(root / r) == d for r, d in expected.items()))


def provision(plan, plan_sha256):
    # The install root stands before provision now, made by `approve` to hold
    # the approval it runs under and nothing else (679.5), so fresh means that.
    need('fresh-install-root', ROOT.is_dir() and locked(ROOT) and sorted(os.listdir(ROOT)) == [APPROVAL])
    # An existing account is custody this payload did not take and will not
    # adopt; the review seat rules on it before provisioning.
    need('no-bravo-account', not account_exists('weaver-bravo'))
    need('no-bravo-group', not group_exists('weaver-bravo'))
    # Every precondition a later command asserts is held here, before the
    # first write: an interrupted provision otherwise leaves ROOT standing and
    # every retry refusing under fresh-install-root. The operator's group is
    # what the sinks are chowned to, and the model's chain is what the
    # snapshot's custody rests on.
    need('operator-group', group_exists(plan['operator']))
    need('model-chain-custody', model_chain_held())
    # The model's missing directories are made here, each locked as it is
    # made, before ROOT exists: a failure among them leaves no root standing.
    if not MODEL.exists():
        make_locked(MODEL.parent)
    # ROOT's own ancestry, held before ROOT is made: a renameable ancestor lets
    # a same-UID process move the new root out from under the writes that
    # follow. installed() holds it again before every later step.
    need('root-chain-custody', chain_custody(ROOT))
    need('model-source', sha(plan['model_source']) == plan['tuple']['weights_sha256'])
    if MODEL.exists() or MODEL.is_symlink():
        # Accepted only as a file already in custody; a link or a shared name
        # to operator-writable bytes would pass the hash and change after it.
        need('existing-model-custody', model_custody())
        need('existing-model', sha(MODEL) == plan['tuple']['weights_sha256'])
    # Verify every input before the first write; an interrupted provision is
    # retained as a refusal for the seat, never silently resumed or removed.
    for stack in ['B1', 'B2']:
        source = Path(plan['stacks'][stack])
        # B1 is copied by bytes. rglob does not descend a linked directory and
        # a linked file is hashed at its target, so a link anywhere in a stack
        # would carry unreviewed or mutable bytes into the root-owned install.
        need('stack-no-symlinks', not any(p.is_symlink() for p in [source, *source.rglob('*')]))
        need('stack-libraries', all((source / x).is_dir() for x in STACK_ROOTS))
        files = [p for p in source.rglob('*') if p.is_file()]
        need('stack-file-coverage', bool(files) and all(str(p) in plan['files'] for p in files))
    # mkdir's mode is masked by the umask, so every served directory is set
    # explicitly as it is made. ROOT itself is set alone: lock() would walk
    # into the approvals and open their private records to the world.
    ROOT.chmod(0o755)
    save(ROOT / 'plan-sha256', plan_sha256 + '\n')
    if not MODEL.exists():
        # The model-source check above refuses early; what root serves is the
        # copy, verified here before provisioning can report success, and held
        # in custody like an existing one: a writable parent lets another
        # process replace the new file after its hash.
        snapshot(plan['model_source'], plan['tuple']['weights_sha256'], MODEL)
        MODEL.chmod(0o644)
        need('new-model-custody', model_custody())
    run(['/usr/bin/groupadd', '--system', 'weaver-bravo'])
    run(['/usr/bin/useradd', '--system', '--gid', 'weaver-bravo', '--home-dir', str(ROOT / 'home'),
         '--create-home', '--shell', '/usr/bin/nologin', 'weaver-bravo'])
    run(['/usr/bin/usermod', '-aG', 'weaver-bravo', plan['operator']])
    for directory in [ROOT / 'stacks', ROOT / 'config', ROOT / 'agents']:
        directory.mkdir()
        lock(directory, 0o755)
    for stack in ['B1', 'B2']:
        dst = ROOT / 'stacks' / stack
        shutil.copytree(plan['stacks'][stack], dst, symlinks=True)
        # copytree copies the source root's mode onto dst; lock the whole tree,
        # dst included, before the copy is verified as what root serves.
        lock(dst, 0o755)
        verify_stack(plan, stack, dst)
        cfg = config(stack)
        cfg.mkdir()
        lock(cfg, 0o755)
        (ROOT / 'agents' / stack).mkdir()
        lock(ROOT / 'agents' / stack, 0o755)
        values = {'allow-list': 'bravo', 'coordination-root': '/run',
                  'log-path': str(ROOT / f'admin-{stack}.log'),
                  'agent-config-directory': str(ROOT / 'agents' / stack),
                  'run-tool': '/usr/bin/systemd-run', 'control-tool': '/usr/bin/systemctl',
                  'worker-binary': str(dst / 'bin/pyworker'),
                  'spu-binary': str(dst / 'bin/weaver-spu'), 'gate-binary': str(dst / 'bin/weaver-gate'),
                  'unit-properties': 'Environment=LD_LIBRARY_PATH=' + environment(stack)['LD_LIBRARY_PATH']}
        for name, value in values.items():
            save(cfg / name, value + '\n')
    sink = ROOT / 'sinks'
    sink.mkdir()
    os.chown(sink, 0, grp.getgrnam(plan['operator']).gr_gid)
    sink.chmod(0o2750)
    print('Provisioned bravo only. Start a fresh operator shell with the weaver-bravo group before the driver.')


# The ancestor a custody walk stops at, the filesystem root: everything a load
# reads sits under it, and nothing above it exists to be renamed.
TRUSTED = Path('/')


def chain_custody(path):
    """Every directory from path's parent up to TRUSTED, inclusive, is one the
    operator cannot rename an entry out of: a real directory, not a link, owned
    by this payload's user or by root, closed to group and world writes. A
    verified file under a renameable ancestor is a file the operator can swap
    whole between the hash and the load; the model and the isolated root are
    both held to this, and every served directory sits beneath one of them."""
    directory = Path(path).parent
    while True:
        entry = os.lstat(directory)
        if not stat.S_ISDIR(entry.st_mode) or entry.st_uid not in (os.geteuid(), 0) or entry.st_mode & 0o022:
            return False
        if directory == TRUSTED or directory.parent == directory:
            return directory == TRUSTED
        directory = directory.parent


def model_custody():
    """The served model is a regular file only this payload's user can change:
    not a link, one name, not group- or world-writable, in a directory held the
    same way, under a chain of directories none of which the operator can
    rename an entry out of. A hash only binds bytes nobody else can rewrite,
    or swap whole, before load."""
    entry, parent = os.lstat(MODEL), os.stat(MODEL.parent)
    return (stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1 and entry.st_uid == os.geteuid() and
            not entry.st_mode & 0o022 and parent.st_uid == os.geteuid() and not parent.st_mode & 0o022 and
            chain_custody(MODEL))


def installed(plan, plan_sha256):
    need('installation-plan', (ROOT / 'plan-sha256').read_text().strip() == plan_sha256)
    need('installed-model-custody', model_custody())
    need('served-directory-custody', all(locked(p) for p in served_directories()) and chain_custody(ROOT))
    need('installed-model', sha(MODEL) == plan['tuple']['weights_sha256'])
    for stack in ['B1', 'B2']:
        verify_stack(plan, stack, ROOT / 'stacks' / stack)


def declared(text, key):
    """Every value a derived declaration gives key. derive renders each of the
    keys read here as JSON (weaver-analysis declare.rs at e69916a: artifact
    183-186, identity 197, the tunable values 199-201), so each is parsed as
    JSON; a value that is not JSON names nothing."""
    found = []
    for line in text.splitlines():
        name, _, value = line.strip().partition(':')
        if name == key:
            try:
                found.append(json.loads(value))
            except ValueError:
                found.append(None)
    return found


def declared_artifacts(text):
    return declared(text, 'artifact')


def holds_tuple(plan, job, text):
    """derive carries the source run's own seed, identity, context capacity and
    token cap into the replay, so a source recorded under another tuple would
    replay another experiment under this one's name. A local source holds its
    free job's seed; an external one, one of the tuple's seeds."""
    t = plan['tuple']
    own = [j['seed'] for arm in plan['arms'] for j in arm['jobs'] if j['id'] == job.get('source_job')]
    identity = [{'role': 'system', 'content': [{'type': 'text', 'text': t['identity']}]}]
    seeds = declared(text, 'seed')
    return (len(seeds) == 1 and any(same(seeds[0], s) for s in (own or t['seeds'])) and
            same(declared(text, 'context-capacity'), [t['context_capacity']]) and
            same(declared(text, 'max-tokens-per-turn'), [t['max_tokens']]) and
            same(declared(text, 'identity'), [identity]))


def declaration(plan, job, sink):
    t = plan['tuple']
    return (f'session: tb-{job["id"]}\nspu-instruction:\n  decoder:\n    model-binding:\n'
            f'      artifact: {MODEL}\n      devices: [0]\n    residual-readout-election: false\n'
            '    surprisal-election: true\n    field-election:\n      depth: 200\n    identity:\n'
            '      - role: system\n        content:\n          - type: text\n'
            f'            text: {json.dumps(t["identity"])}\n    tunable-values:\n'
            f'      seed: {job["seed"]}\n      context-capacity: 12288\n      max-tokens-per-turn: 8192\n'
            f'loop-file: {ROOT}/stacks/{job["stack"]}/bin/basic_loop.py\n'
            'tool-set: []\npermission-mode: ask\ngate-instruction:\n  access-rule:\n'
            f'    allowed-uids: [{plan["operator_uid"]}]\n    allowed-gids: []\n    denied-uids: []\n'
            f'trace-sink:\n  kind: file\n  path: {sink}\n  create: true\n')


def well_formed_sink(source_sink):
    """A local re-feed's recorded sink as root receives it: two arguments, a
    positive decimal length and a 64-lowercase-hex digest. Root judges the
    shape itself rather than trusting the coordinator's argv."""
    if source_sink is None or len(source_sink) != 2:
        return False
    length, digest = source_sink
    # ASCII digits only: str.isdecimal() admits every script's digits, and
    # int() reads them as the same length.
    return (length[:1] in tuple('123456789') and all(c in '0123456789' for c in length) and len(digest) == 64
            and all(c in '0123456789abcdef' for c in digest))


def load(plan, job, source_sink=None):
    # **Every refusal that needs no read of the card or the stack comes before
    # the first write**: a malformed recorded sink creates no directory, so
    # correcting the state lets the job be retried without recovery.
    if job.get('source_job'):
        need('source-sink-given', well_formed_sink(source_sink))
    m1_unloaded('load')
    stack = job['stack']
    answer(stack, 'show', 'unloaded')
    # Every load checks the driver version as well as declared device ordinal.
    gpu = run(['/usr/bin/nvidia-smi', '--query-gpu=index,name,driver_version', '--format=csv,noheader'],
              capture_output=True).stdout.strip().splitlines()
    need('gpu-tuple', len(gpu) == 1 and gpu[0].split(', ')[0] == '0' and
         'RTX PRO 5000 Blackwell' in gpu[0] and gpu[0].endswith(plan['tuple']['driver']))
    # Fail if ELF resolution falls back to the host toolkit for B1 or B2.
    lib = ROOT / 'stacks' / stack / 'engine-lib/libggml-cuda.so'
    resolved = run(['/usr/bin/ldd', str(lib)], env=environment(stack), capture_output=True).stdout
    need('resolved-libraries', 'not found' not in resolved)
    for name in ['libcudart.so', 'libcublas.so', 'libcublasLt.so']:
        lines = [line for line in resolved.splitlines() if name in line]
        need('cuda-local', len(lines) == 1 and f'{ROOT}/stacks/{stack}/cuda-lib/' in lines[0])
    print(resolved)
    directory = ROOT / 'sinks' / job['id']
    # Never truncate or reuse a run, even after refusal. A load whose sink
    # stands was run before, perhaps by a coordinator that died before its
    # receipt was written, and it refuses by name rather than loading twice.
    need('fresh-sink', not directory.exists() and not directory.is_symlink())
    directory.mkdir()
    os.chown(directory, 0, grp.getgrnam(plan['operator']).gr_gid)
    directory.chmod(0o2750)
    sink = directory / 'trace.ndjson'
    target = ROOT / 'agents' / stack / 'bravo.yaml'
    if job['kind'] == 'free':
        save(target, declaration(plan, job, sink))
        answer(stack, 'load', 'idle')
        return
    # derive and preload each read their input again, so both receive one
    # root-owned private file cut from a single verified read.
    frozen = ROOT / 'snapshots' / job['id']
    frozen.mkdir(mode=0o700, parents=True)
    if job.get('source_job'):
        # Our own sink, written by the agent and root-owned: frozen as it stood
        # at its run's turn.closed, the length and digest the driver recorded
        # in the coordinator's state then, which the coordinator hands here.
        # What the unload appended after that close lies past the length.
        source = snapshot(ROOT / 'sinks' / job['source_job'] / 'trace.ndjson', source_sink[1],
                          frozen / 'source.ndjson', length=int(source_sink[0]))
    else:
        whole = snapshot(job['source_trace'], plan['files'][str(job['source_trace'])], frozen / 'whole.ndjson')
        source = select_run(whole, job['source_run'], frozen / 'source.ndjson')
    analysis = str(ROOT / 'stacks' / stack / 'bin/weaver-analysis')
    run([analysis, 'derive', str(source), '--devices', '0', '--sink', str(sink),
         '--field-depth', '200', '--surprisal', '--out', str(target)], env=environment(stack))
    # Derive preserves the recorded artifact; never rewrite it to evade identity.
    need('derived-artifact', declared_artifacts(target.read_text()) == [str(MODEL)])
    need('derived-tuple', holds_tuple(plan, job, target.read_text()))
    with (directory / 'load.log').open('w') as log:
        loader = subprocess.Popen(admin(stack, 'load'), stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT, env=environment(stack))
        try:
            door = directory / 'state/preload.sock'
            deadline = time.monotonic() + 120
            while not door.exists() and loader.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            need('preload-door', door.exists() and stat.S_ISSOCK(door.stat().st_mode))
            run([analysis, 'preload', str(source), str(door)], env=environment(stack), timeout=600)
            need('diagnostic-load', loader.wait(timeout=600) == 0)
        finally:
            if loader.poll() is None:
                loader.kill()
                loader.wait()
    print((directory / 'load.log').read_text())


def main():
    need('root-payload', os.geteuid() == 0)
    step, pointer, *source_sink = sys.argv[1:]
    approval, directory = read_approval(pointer)
    # This file is the approval's own root-owned copy, found complete by
    # tb_root.py before it ran it, and the plan is the copy beside it, one
    # snapshot held to its digest, then parsed.
    expected = approval['plan']['sha256']
    data = read_once(directory / approval['plan']['copy'], follow=False)
    need('plan-hash', hashlib.sha256(data).hexdigest() == expected)
    plan = json.loads(data)
    need('fixed-root-agent', plan['install_root'] == str(ROOT) and plan['agent'] == 'bravo')
    need('operator', type(plan['operator_uid']) is int and
         pwd.getpwnam(plan['operator']).pw_uid == plan['operator_uid'] == int(os.environ['SUDO_UID']))
    for path, digest in plan['files'].items():
        need('source-file-hash', sha(path) == digest)
    if step == 'provision':
        provision(plan, expected)
    else:
        installed(plan, expected)
        verb, identity = step.split(':', 1)
        jobs = [j for arm in plan['arms'] for j in arm['jobs'] if j['id'] == identity]
        need('job-found', len(jobs) == 1)
        job = jobs[0]
        need('known-step', verb in ('load', 'unload'))
        if verb == 'load':
            load(plan, job, source_sink or None)
        else:
            answer(job['stack'], 'unload', 'unloaded')
            answer(job['stack'], 'show', 'unloaded')
            # The interlock again at the unload, with the card now free: m1
            # standing here means it may have stood during the reading, so the
            # step refuses and the reading is never settled.
            reading = m1_reading()
            print(f'INTERLOCK at unload: {json.dumps(reading, sort_keys=True)}', flush=True)
            need('m1-unloaded-at-unload', m1_clear(reading))
    print(f'SUCCESS: {step}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'REFUSED: {error}; NEXT: review seat - inspect partial state, do not retry blindly', file=sys.stderr)
        sys.exit(1)
