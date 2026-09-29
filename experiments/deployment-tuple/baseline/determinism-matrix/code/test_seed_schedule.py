"""The seed schedule's three pure parts, per Run 1 of issue #485.

Run with `python3 test_seed_schedule.py` or under pytest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "cross-precision-repro"))

from determinism_matrix import parse_seed_schedule, seed_for, with_declared_seed  # noqa: E402
import confirm_cells as base  # noqa: E402

DECLARATION = """session = "s-karl-1"
tool-set = []

[spu-instruction.decoder]
# the seed below is the operator's
tunable-values = { seed = 451234785645, context-capacity = 16384, max-tokens-per-turn = 1024 }

[spu-instruction.decoder.model-binding]
artifact = "/opt/weaver/models/m.gguf"
"""

TABLE = """[spu-instruction.decoder.tunable-values]
seed = 451234785645  # the operator's
context-capacity = 16384
"""


def test_the_seed_line_is_rewritten_and_nothing_else():
    for declaration in (DECLARATION, TABLE):
        out = with_declared_seed(declaration, 7)
        assert "seed = 7," in out or "seed = 7  #" in out, out
        assert out.replace("seed = 7", "seed = 451234785645") == declaration


def test_a_declaration_without_exactly_one_seed_line_refuses():
    for text in ('session = "s"\n', TABLE + "seed = 9\n",
                 'seed = 9\n' + DECLARATION.replace("seed = 451234785645, ", "")):
        try:
            with_declared_seed(text, 1)
        except ValueError:
            continue
        raise AssertionError(f"rewrote a seed in {text!r}")


# A declaration whose strings and comments carry text shaped like the two
# keys, which a text-matching locator counted as more sites.
DECOYS = """session = "s-karl-1"
tool-set = []
permission-mode = "ask"

[spu-instruction.decoder]
residual-readout-election = false
tunable-values = { seed = 451234785645, context-capacity = 16384 } # { seed = 9 }

[spu-instruction.decoder.model-binding]
artifact = "/opt/weaver/models/m.gguf"  # { artifact = "/decoy" }
devices = [0]

[[spu-instruction.decoder.identity]]
role = "system"

[[spu-instruction.decoder.identity.content]]
type = "text"
text = '''
artifact = "/decoy"
tunable-values = { seed = 9 }
'''
note = "a, seed = 1, artifact = '/decoy'"

[spu-instruction.decoder.other]
seed = 9
artifact = "/other.gguf"
"""


def test_text_shaped_like_a_key_is_not_a_site():
    # Key-like text inside a string or a comment, and the same key in
    # another table, name no site: the seed and the artifact each rewrite
    # alone and read back with every other byte where it stood.
    # Perturbation: restore the text-matching locator, and the decoys count
    # as more sites and both rewrites refuse. Watched under exactly that.
    out = with_declared_seed(DECOYS, 7)
    assert out == DECOYS.replace("seed = 451234785645,", "seed = 7,"), out
    assert base.declaration_seed(out) == 7
    out = base.with_artifact(DECOYS, "/opt/weaver/models/n.gguf")
    assert out == DECOYS.replace('artifact = "/opt/weaver/models/m.gguf"', 'artifact = "/opt/weaver/models/n.gguf"'), out
    assert base.declared_artifact(out) == "/opt/weaver/models/n.gguf"


def test_a_seed_with_no_value_on_its_line_is_not_rewritten():
    # `seed =` followed by a newline names nothing, and the rewrite must not
    # reach across the line break to the next key's value. In TOML such a
    # line is not a document at all, so the declaration is refused by its
    # parse before any site is sought, and a site pattern crossing the line
    # end is not reachable here: the reparse is what would catch it.
    text = "[spu-instruction.decoder.tunable-values]\nseed =\ntemperature = 0.7\n"
    try:
        with_declared_seed(text, 1)
    except ValueError as e:
        assert "not a TOML 1.0 document" in str(e), e
        return
    raise AssertionError("a seed line with no value was matched")


def test_a_seed_a_toml_integer_cannot_carry_is_refused():
    # The sampler's seed is a u64 and a TOML integer an i64. Perturbation:
    # drop the bound in with_declared_seed, and the rewrite writes a file the
    # stack's parser refuses while tomllib reads it.
    assert "seed = 9223372036854775807," in with_declared_seed(DECLARATION, 2 ** 63 - 1)
    for seed in (2 ** 63, 2 ** 64 - 1, -1, True):
        try:
            with_declared_seed(DECLARATION, seed)
        except ValueError:
            continue
        raise AssertionError(f"wrote the seed {seed!r}")


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
