"""An interrupt at the record's offset read is the session's (#698, from
Codex's pass on #716 at 7f35452).

Run with `python3 test_record_offset.py` or under pytest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_round_eighteen import both, held  # noqa: E402


def test_an_interrupt_at_the_offset_read_is_recorded_in_both_files():
    # The offset read sat outside both the loop body's interrupt clause and
    # `closing`, so a Ctrl-C there dropped the cut-short session from both
    # files. Perturbation: read the offset before the guarded step again,
    # and the second session is missing from both.
    real, calls = os.path.getsize, []

    def getsize(path):
        if str(path).endswith("matrix.jsonl"):
            calls.append(1)
            if len(calls) == 1:
                raise KeyboardInterrupt
        return real(path)

    def patch():
        calls.clear()
        dm.os.path.getsize = getsize

    def restore():
        dm.os.path.getsize = real
    matrix, cells = both(patch, restore)
    held(matrix, 2)
    held(cells, 2)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
