"""The seed schedule's three pure parts, per Run 1 of issue #485.

Run with `python3 test_seed_schedule.py` or under pytest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "cross-precision-repro"))

from determinism_matrix import parse_seed_schedule, seed_for, with_declared_seed  # noqa: E402

DECLARATION = """session: s-karl-1
spu-instruction:
  decoder:
    sampling:
      seed: 451234785645
      temperature: 0.7
"""


def test_the_seed_line_is_rewritten_and_nothing_else():
    out = with_declared_seed(DECLARATION, 7)
    assert "      seed: 7\n" in out
    assert out.replace("seed: 7", "seed: 451234785645") == DECLARATION


def test_a_declaration_without_exactly_one_seed_line_refuses():
    for text in ("session: s\n", DECLARATION + "      seed: 9\n"):
        try:
            with_declared_seed(text, 1)
        except ValueError:
            continue
        raise AssertionError("refused neither zero nor two seed lines")


def test_a_seed_with_no_value_on_its_line_is_not_rewritten():
    # `seed:` followed by a newline names nothing, and the rewrite must not
    # reach across the line break to the next key's value.
    text = "sampling:\n  seed:\n  temperature: 0.7\n"
    try:
        with_declared_seed(text, 1)
    except ValueError:
        assert "temperature: 0.7" in text
        return
    raise AssertionError("a seed line with no value was matched")


def test_the_schedule_parses_and_refuses_repeats():
    assert parse_seed_schedule("1, 2,3") == [1, 2, 3]
    for bad in ("", "1,1"):
        try:
            parse_seed_schedule(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_every_cell_meets_every_seed_over_as_many_sweeps_as_seeds():
    schedule = list(range(100, 108))
    cells = 32
    for cell in range(cells):
        seen = {seed_for(schedule, sweep, cell) for sweep in range(1, 9)}
        assert seen == set(schedule), f"cell {cell} met {sorted(seen)}"
    # And within one sweep, cells 0 and 8 (one prompt, two depths) differ
    # from what a rotation by cell alone would give across sweeps.
    assert seed_for(schedule, 1, 0) != seed_for(schedule, 2, 0)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
