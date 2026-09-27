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


CELLS = 32  # eight prompts at four depths, one sweep


def sessions(schedule, sweeps):
    """The seed of every session in run order, sweep by sweep."""
    return [seed_for(schedule, sweep, cell)
            for sweep in range(1, sweeps + 1) for cell in range(CELLS)]


def test_every_accepted_schedule_varies_every_session_and_every_cell():
    # #716 round one: the rotation repeated a seed across the sweep boundary
    # wherever the schedule's length divides 30, and a one-seed schedule
    # never varied. Every length from 1 to 40 is either refused or holds
    # both properties. Perturbation: the old rotation, `cell + sweep - 1`,
    # fails the boundary for lengths 3, 5, 6, 10, 15 and 30.
    for n in range(1, 41):
        schedule = list(range(1000, 1000 + n))
        try:
            parse_seed_schedule(",".join(map(str, schedule)))
        except ValueError:
            assert n in (1, 2), f"refused a schedule of {n} seeds"
            continue
        run = sessions(schedule, n + 1)
        assert all(a != b for a, b in zip(run, run[1:])), f"{n} seeds repeat a session"
        for cell in range(CELLS):
            met = [seed_for(schedule, sweep, cell) for sweep in range(1, n + 2)]
            assert set(met[:n]) == set(schedule), f"{n} seeds: cell {cell} met {met[:n]}"
            assert all(a != b for a, b in zip(met, met[1:])), f"{n} seeds: cell {cell} kept one"


def test_the_refused_lengths_cannot_hold_both_properties():
    # One seed never varies. Two seeds must alternate for successive sessions
    # to differ, and over an even sweep that pins every cell to one seed, so
    # no rotation of any kind can hold both. Perturbation: accept two seeds
    # and the test above fails on cell 0.
    for n in (1, 2):
        try:
            parse_seed_schedule(",".join(str(1000 + i) for i in range(n)))
        except ValueError:
            continue
        raise AssertionError(f"accepted a schedule of {n} seeds")
    alternation = [i % 2 for i in range(3 * CELLS)]
    assert all(alternation[c] == alternation[c + CELLS] for c in range(CELLS))


def test_the_rotation_is_unchanged_wherever_it_already_held():
    # Every length not dividing 30 keeps step one, the rotation the matrix
    # always used, so no run made under such a schedule reads differently.
    for n in range(3, 41):
        if 30 % n == 0:
            continue
        schedule = list(range(n))
        for sweep in range(1, 4):
            for cell in range(CELLS):
                assert seed_for(schedule, sweep, cell) == schedule[(cell + sweep - 1) % n]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
