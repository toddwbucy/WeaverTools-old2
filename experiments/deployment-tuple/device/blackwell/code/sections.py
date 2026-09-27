#!/usr/bin/env python3
# conforms: blackwell-probe-inventory-covers-every-served-file
# conforms: blackwell-probe-comparison-takes-b1-then-b2
"""Inventory ELF sections and extracted CUDA members without loading libraries."""
import argparse
import collections
import hashlib
import json
import pathlib
import struct

from tb_payload import STACK_ROOTS


def digest(data):
    return hashlib.sha256(data).hexdigest()


def elf_sections(path):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x02\x01':
        raise ValueError(f'{path}: expected ELF64 little-endian')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    offset, size, count, string_index = header[6], header[11], header[12], header[13]
    def section(index):
        return struct.unpack_from('<IIQQQQIIQQ', data, offset + size * index)
    # The entry point, segment mappings and permissions live outside every
    # section payload, so they are inventoried here rather than inferred.
    elf_header = dict(zip(['ident', 'type', 'machine', 'version', 'entry', 'phoff', 'shoff', 'flags',
                           'ehsize', 'phentsize', 'phnum', 'shentsize', 'shnum', 'shstrndx'],
                          (header[0].hex(),) + header[1:]))
    segments = header[10]
    if segments == 0xffff:
        segments = section(0)[7]
    program_headers = []
    for index in range(segments):
        fields = struct.unpack_from('<IIQQQQQQ', data, header[5] + header[9] * index)
        record = dict(zip(['type', 'flags', 'offset', 'vaddr', 'paddr', 'filesz', 'memsz', 'align'], fields))
        record['sha256'] = digest(data[record['offset']:record['offset'] + record['filesz']])
        program_headers.append(record)
    if count == 0:
        count = section(0)[5]
    if string_index == 0xffff:
        string_index = section(0)[6]
    strings_header = section(string_index)
    strings = data[strings_header[4]:strings_header[4] + strings_header[5]]
    result = []
    for index in range(1, count):
        name_offset, kind, flags, address, start, length, link, info, align, entry_size = section(index)
        name = strings[name_offset:strings.index(b'\0', name_offset)].decode()
        payload = None if kind == 8 else data[start:start + length]
        if payload is not None and len(payload) != length:
            raise ValueError(f'{path}: truncated section {name}')
        result.append(dict(name=name, type=kind, flags=flags, executable=bool(flags & 4),
                           allocated=bool(flags & 2), size=length,
                           sha256=None if payload is None else digest(payload)))
    return dict(file_sha256=digest(data), elf_header=elf_header, program_headers=program_headers,
                sections=result)


def inventory():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deposit', type=pathlib.Path)
    parser.add_argument('stack', choices=['B1', 'B2'])
    args = parser.parse_args()
    root = args.deposit
    stack = root / 'stacks' / args.stack
    output = root / 'sections' / args.stack
    # Every file a load can reach: bin and engine-lib, and cuda-lib, which
    # tb_payload puts on LD_LIBRARY_PATH; not only ELF files, since the worker
    # runs bin/basic_loop.py. ELF files carry sections and headers, every file
    # its whole-file hash, which the identity verdict requires to match. A
    # link is refused, as provisioning refuses one: skipping it would vouch
    # for bytes nobody read.
    hosts = {}
    for folder in STACK_ROOTS:
        for path in sorted((stack / folder).rglob('*')):
            if path.is_symlink():
                raise ValueError(f'{path}: a link in a stack is not inventoried; the stack is copied by bytes')
            if path.is_file():
                with path.open('rb') as stream:
                    magic = stream.read(4)
                name = str(path.relative_to(stack))
                hosts[name] = elf_sections(path) if magic == b'\x7fELF' else dict(
                    file_sha256=digest(path.read_bytes()), sections=[])
    members = {}
    for kind in ['cubin', 'ptx']:
        files = sorted((output / kind).glob('*'))
        members[kind] = {path.name: dict(size=path.stat().st_size, sha256=digest(path.read_bytes()))
                         for path in files if path.is_file()}
        if kind == 'cubin':
            for path in files:
                if path.is_file():
                    members[kind][path.name]['sections'] = elf_sections(path)['sections']
        if not members[kind]:
            raise ValueError(f'No {kind} extracted for {args.stack}')
    if not hosts:
        raise ValueError('No host files found')
    result = dict(stack=args.stack, hosts=hosts, members=members,
                  scope=f'Every file under {", ".join(STACK_ROOTS)}, ELF files by section and header and every file by whole-file hash; every extracted cubin and PTX member. No GPU code executed.')
    destination = output / 'section-manifest.json'
    destination.write_text(json.dumps(result, indent=2) + '\n')
    architectures = collections.Counter(name.split('.')[-2] for name in members['cubin'])
    print(json.dumps(dict(manifest=str(destination), host_elfs=len(hosts),
                          cubins=len(members['cubin']), ptx=len(members['ptx']),
                          architectures=dict(architectures))))


def compare(first, second):
    # One inventory named twice, by any spelling, is identical to itself; a
    # hand-run comparison must not be able to produce the identity report the
    # elected kernel branch reads.
    if pathlib.Path(first).resolve() == pathlib.Path(second).resolve():
        raise ValueError(f'compare takes two inventories, not {first} twice')
    raw = [pathlib.Path(p).read_bytes() for p in [first, second]]
    a, b = [json.loads(r) for r in raw]
    inputs = {m['stack']: dict(manifest=str(p), sha256=digest(r)) for m, p, r in zip([a, b], [first, second], raw)}
    return comparison(a, b, inputs)


def comparison(a, b, inputs):
    """The pure verdict over two parsed inventories, with the inputs record the
    caller vouches for: compare() reads the files and passes their paths and
    digests, and the coordinator passes the manifests it has already verified
    against the approved digests, so recomputing the verdict at approval
    reads nothing twice."""
    # A verdict about B1 against B2 needs B1 then B2: the same inventory twice
    # is identical to itself, and an empty scope makes every all() vacuous.
    if (a.get('stack'), b.get('stack')) != ('B1', 'B2'):
        raise ValueError(f"compare takes the B1 inventory then the B2 inventory, not {a.get('stack')} and {b.get('stack')}")
    for m in (a, b):
        if not m.get('hosts') or not all(m.get('members', {}).get(kind) for kind in ['cubin', 'ptx']):
            raise ValueError(f"the {m['stack']} inventory has no hosts, cubins or PTX, and vouches for nothing")
    # The verdict names the inventories it read, by path and digest, so a
    # reader can bind it to the stack bytes those inventories describe.
    report = {"stacks": ['B1', 'B2'], "inputs": inputs, "host": {}, "cuda": {}}
    for name in sorted(a['hosts'].keys() | b['hosts'].keys()):
        sa = {s['name']: s for s in a['hosts'].get(name, {}).get('sections', [])}
        sb = {s['name']: s for s in b['hosts'].get(name, {}).get('sections', [])}
        changes = []
        for section in sorted(sa.keys() | sb.keys()):
            if sa.get(section) != sb.get(section):
                changes.append(dict(section=section, B1=sa.get(section), B2=sb.get(section)))
        ha, hb = a['hosts'].get(name, {}), b['hosts'].get(name, {})
        headers = [dict(part=part, B1=ha.get(part), B2=hb.get(part))
                   for part in ['elf_header', 'program_headers'] if ha.get(part) != hb.get(part)]
        report['host'][name] = dict(text_equal=sa.get('.text') == sb.get('.text') and '.text' in sa,
                                   file_equal=ha.get('file_sha256') is not None and
                                              ha.get('file_sha256') == hb.get('file_sha256'),
                                   header_changes=headers, changes=changes)
    for kind in ['cubin', 'ptx']:
        ma, mb = a['members'][kind], b['members'][kind]
        groups = {}
        for name in sorted(ma.keys() | mb.keys()):
            arch = name.split('.')[-2]
            group = groups.setdefault(arch, dict(equal=0, code_equal=0, changed=[], missing=[]))
            if name not in ma or name not in mb:
                group['missing'].append(name)
            elif ma[name] == mb[name]:
                group['equal'] += 1
            else:
                group['changed'].append(name)
            if kind == 'cubin' and name in ma and name in mb:
                ca = [s for s in ma[name]['sections'] if s['executable']]
                cb = [s for s in mb[name]['sections'] if s['executable']]
                if ca and ca == cb:
                    group['code_equal'] += 1
        report['cuda'][kind] = groups
    # Conservative: relocations/read-only data also affect execution. Never
    # conclude held identity from .text alone or hide missing members. A host
    # counts only when its whole file is byte-identical: headers, segments and
    # bytes no section or header record explains can change execution, and a
    # manifest that did not record them cannot vouch for them. No hosts, no claim.
    report['executable_identity'] = (bool(report['host']) and all(not h['changes'] and not h['header_changes'] and h['file_equal']
                                         for h in report['host'].values()) and
        all(not g['changed'] and not g['missing'] for groups in report['cuda'].values() for g in groups.values()))
    return report


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 5 and sys.argv[1] == 'compare':
        report = compare(sys.argv[2], sys.argv[3])
        pathlib.Path(sys.argv[4]).write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(dict(host_text_equal=sum(h['text_equal'] for h in report['host'].values()),
                             host_file_equal=sum(h['file_equal'] for h in report['host'].values()),
                             host_header_changed=sum(bool(h['header_changes']) for h in report['host'].values()),
                             host_files=len(report['host']), cuda={k:{arch:dict(equal=g['equal'], code_equal=g['code_equal'], changed=len(g['changed']), missing=len(g['missing'])) for arch,g in v.items()} for k,v in report['cuda'].items()},
                             executable_identity=report['executable_identity'])))
    else:
        inventory()
