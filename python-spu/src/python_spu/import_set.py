"""The import set, per python-spu-Spec section 8.

Every module the process holds after admission, and again after its first
generation, must be one the declared list names, imports.txt beside this file. A
module outside it faults the process: one line on standard error naming the modules
and the stage, then an exit, which the harness meets as the SPU gone, since the
lifecycle vocabulary has no case for an environment that loaded what it did not
declare and a refusal would need one. Loaded is a subset of declared and not equal
to it, because torch imports different modules on the CPU and on CUDA and some
lazily, so the declared list is the union of a clean run of each.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _read_declared():
    # Read through the loader, so the list reads the same from the source tree and
    # from inside the zipapp, and read once, at import, so reading it adds nothing
    # the check itself would then have to allow.
    loader = __loader__
    data = loader.get_data(os.path.join(_HERE, "imports.txt"))
    return frozenset(
        line.strip() for line in data.decode().splitlines()
        if line.strip() and not line.startswith("#")
    )


DECLARED = _read_declared()


def undeclared(loaded=None):
    loaded = set(sys.modules) if loaded is None else set(loaded)
    return sorted(loaded - DECLARED)


def enforce(stage, declare=None):
    """Judges the process's modules at a stage, or, where the server was started
    with --declare-imports, records them instead. Declaring never serves past the
    first generation: the process exits once that stage is recorded, so the mode
    cannot stand in for a judged process."""
    if declare is not None:
        with open(declare, "a") as fh:
            fh.write("".join(f"{name}\n" for name in sorted(sys.modules)))
        if stage == "first generation":
            os._exit(0)
        return
    extra = undeclared()
    if extra:
        print(json.dumps({"import_set_violation": stage, "undeclared": extra}),
              file=sys.stderr, flush=True)
        os._exit(3)
