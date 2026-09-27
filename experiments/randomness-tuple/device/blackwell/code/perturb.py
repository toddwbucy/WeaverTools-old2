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
# conforms: blackwell-probe-root-receives-bytes-never-a-path
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


def guards(path):
    return [(node.lineno, node.args[0].value) for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ['check','need']
            and len(node.args) == 2 and isinstance(node.args[0], ast.Constant)]


# The handlers whose catching is itself a rule: a read the interlock cannot
# make is unread, never clear (#693 thread 2). Each is made to catch nothing,
# and the suite must then fail, as a named guard must when removed.
HANDLERS = {'tb_payload.py': ['m1_reading', 'door_state']}


def handlers(path, functions):
    tree = ast.parse(path.read_text())
    return [(handler.lineno, function.name) for function in ast.walk(tree)
            if isinstance(function, ast.FunctionDef) and function.name in functions
            for handler in ast.walk(function) if isinstance(handler, ast.ExceptHandler)]


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
        for p in root.glob('*'):
            if p.suffix in ['.py','.sh']:shutil.copy2(p,target/p.name)
        # A kill is a failure the mutation caused. Against a suite that already
        # fails, every mutation reads as killed, so the unmodified suite must pass.
        base=suite(target)
        if base.returncode!=0:
            print('BASELINE FAILED: the unmodified suite does not pass; no mutation was run\n'+base.stderr[-1800:],file=sys.stderr)
            return 2
        for name in ['tb_order.py','tb_payload.py','tb_driver.py']:
            source=root/name
            for line, label in guards(source):
                for mode in ['removed','inverted']:
                    shutil.rmtree(target/'__pycache__',ignore_errors=True)
                    tree=ast.parse(source.read_text())
                    for node in ast.walk(tree):
                        if isinstance(node,ast.Call) and node.lineno==line and isinstance(node.func,ast.Name) and node.func.id in ['check','need']:
                            node.args[1]=ast.Constant(value=True) if mode=='removed' else ast.UnaryOp(op=ast.Not(),operand=node.args[1])
                    (target/name).write_text(ast.unparse(ast.fix_missing_locations(tree))+'\n')
                    result=suite(target)
                    records.append(dict(file=name,line=line,guard=label,mode=mode,killed=result.returncode!=0,
                                        evidence=result.stderr[-1800:]))
                    shutil.copy2(source,target/name)
        for name, functions in HANDLERS.items():
            source=root/name
            for line, function in handlers(source, functions):
                shutil.rmtree(target/'__pycache__',ignore_errors=True)
                tree=ast.parse(source.read_text())
                for node in ast.walk(tree):
                    if isinstance(node,ast.ExceptHandler) and node.lineno==line:
                        node.type=ast.Tuple(elts=[],ctx=ast.Load())
                (target/name).write_text(ast.unparse(ast.fix_missing_locations(tree))+'\n')
                result=suite(target)
                records.append(dict(file=name,line=line,guard=f'{function} handler',mode='uncaught',
                                    killed=result.returncode!=0,evidence=result.stderr[-1800:]))
                shutil.copy2(source,target/name)
        print(json.dumps(records,indent=2))
    return int(any(not r['killed'] for r in records))


if __name__=='__main__':sys.exit(main())
