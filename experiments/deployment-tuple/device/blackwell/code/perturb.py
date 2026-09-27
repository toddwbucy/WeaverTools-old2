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
"""Remove and invert each named guard in disposable copies; never edit the subject."""
import ast
import json
import os
import signal
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def guards(text):
    return [(node.lineno, node.args[0].value) for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ['check','need']
            and len(node.args) == 2 and isinstance(node.args[0], ast.Constant)]


# The handlers whose catching is itself a rule: a read the interlock cannot
# make is unread, never clear (#693 thread 2). Each is made to catch nothing,
# and the suite must then fail, as a named guard must when removed.
HANDLERS = {'tb_payload.py': ['m1_reading', 'door_state']}


def handlers(text, functions):
    tree = ast.parse(text)
    return [(handler.lineno, function.name) for function in ast.walk(tree)
            if isinstance(function, ast.FunctionDef) and function.name in functions
            for handler in ast.walk(function) if isinstance(handler, ast.ExceptHandler)]


# An edit made during a sweep once misaimed every mutation after it, each guard's
# line having been read before the edit and its mutation made after, so eight
# guards read as survivors (679.5). A misaimed mutation can as easily read as a
# kill of a guard it never touched. The subject is pinned by its bytes when the
# sweep begins, every mutation is made from those bytes, and a sweep the subject
# moved under refuses whole.
def moved(root, pinned):
    return sorted(name for name, data in pinned.items() if (root/name).read_bytes() != data)


def suite(target):
    child=subprocess.Popen([sys.executable,'-B','-m','unittest','test_tb'],cwd=target,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    try:
        out,err=child.communicate(timeout=5)
        return subprocess.CompletedProcess(child.args,child.returncode,out,err)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL)
        out,err=child.communicate()
        return subprocess.CompletedProcess(child.args,124,out,err+'\nTIMEOUT: mutation prevented bounded completion')


def main():
    root=Path(__file__).resolve().parent
    records=[]
    with tempfile.TemporaryDirectory(prefix='tb-mutations-') as temporary:
        target=Path(temporary)
        pinned={}
        for p in root.glob('*'):
            if p.suffix in ['.py','.sh']:
                pinned[p.name]=p.read_bytes();(target/p.name).write_bytes(pinned[p.name])
        # A kill is a failure the mutation caused. Against a suite that already
        # fails, every mutation reads as killed, so the unmodified suite must pass.
        base=suite(target)
        if base.returncode!=0:
            print('BASELINE FAILED: the unmodified suite does not pass; no mutation was run\n'+base.stderr[-1800:],file=sys.stderr)
            return 2
        for name in ['tb_order.py','tb_payload.py','tb_root.py','tb_driver.py']:
            for line, label in guards(pinned[name].decode()):
                for mode in ['removed','inverted']:
                    shutil.rmtree(target/'__pycache__',ignore_errors=True)
                    tree=ast.parse(pinned[name].decode())
                    for node in ast.walk(tree):
                        if isinstance(node,ast.Call) and node.lineno==line and isinstance(node.func,ast.Name) and node.func.id in ['check','need']:
                            node.args[1]=ast.Constant(value=True) if mode=='removed' else ast.UnaryOp(op=ast.Not(),operand=node.args[1])
                    (target/name).write_text(ast.unparse(ast.fix_missing_locations(tree))+'\n')
                    result=suite(target)
                    records.append(dict(file=name,line=line,guard=label,mode=mode,killed=result.returncode!=0,
                                        evidence=result.stderr[-1800:]))
                    if moved(root,pinned):
                        print(f'SUBJECT MOVED: {", ".join(moved(root,pinned))} changed during the sweep; no reading is taken',file=sys.stderr)
                        return 2
                    (target/name).write_bytes(pinned[name])
        for name, functions in HANDLERS.items():
            for line, function in handlers(pinned[name].decode(), functions):
                shutil.rmtree(target/'__pycache__',ignore_errors=True)
                tree=ast.parse(pinned[name].decode())
                for node in ast.walk(tree):
                    if isinstance(node,ast.ExceptHandler) and node.lineno==line:
                        node.type=ast.Tuple(elts=[],ctx=ast.Load())
                (target/name).write_text(ast.unparse(ast.fix_missing_locations(tree))+'\n')
                result=suite(target)
                records.append(dict(file=name,line=line,guard=f'{function} handler',mode='uncaught',
                                    killed=result.returncode!=0,evidence=result.stderr[-1800:]))
                if moved(root,pinned):
                    print(f'SUBJECT MOVED: {", ".join(moved(root,pinned))} changed during the sweep; no reading is taken',file=sys.stderr)
                    return 2
                (target/name).write_bytes(pinned[name])
        print(json.dumps(records,indent=2))
    return int(any(not r['killed'] for r in records))


if __name__=='__main__':sys.exit(main())
