"""The TOML 1.0 grammar declarations are written in, per weaver-types-Spec
section 2: the subset every reader in the suite shares, admin's toml crate
reading 1.1 and this harness and the deploy script reading with tomllib,
which reads 1.0.

Run with `python3 test_declaration_grammar.py` or under pytest.
"""
import os
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "cross-precision-repro"))

import confirm_cells as base  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
DERIVED = os.path.join(REPO, "crates", "weaver-analysis", "tests", "fixtures",
                       "derived-surrogate.toml")

# A declaration only TOML 1.1 reads: its inline table spans two lines.
MULTILINE_INLINE = """session = "s-karl-1"

[spu-instruction.decoder]
tunable-values = {
  seed = 451234785645 }
"""


def test_the_declaration_weaver_analysis_writes_is_toml_1_0():
    # The one declaration the suite writes by serializer, pinned byte for
    # byte by weaver-analysis's driver and parsed by weaver-types's config
    # tests, read here by the 1.0 reader too. Perturbation: write an inline
    # table across two lines into the file and this refuses.
    with open(DERIVED, "rb") as fh:
        document = tomllib.load(fh)
    text = document["spu-instruction"]["decoder"]["identity"][0]["content"][0]["text"]
    assert text.startswith("You are Karl \U0001F600"), text


def test_a_toml_1_1_declaration_is_diagnosed_by_name():
    # Admin's parser takes a multiline inline table and tomllib does not, so
    # the harness names the grammar rather than refusing without a reason,
    # and at preflight names the file. Perturbation: drop the grammar from
    # the refusal and the message loses it.
    try:
        base.declaration_seed(MULTILINE_INLINE)
    except ValueError as e:
        assert "not a TOML 1.0 document" in str(e), e
    else:
        raise AssertionError("a TOML 1.1 declaration read")
    with tempfile.TemporaryDirectory() as tmp:
        decl = os.path.join(tmp, "karl.toml")
        with open(decl, "w") as fh:
            fh.write(MULTILINE_INLINE)
        cfg = dict(declaration=decl, admin_bin="/bin/true", repo=tmp)
        try:
            base.run_files(cfg, rewrites=False)
        except ValueError as e:
            assert "not a TOML 1.0 document" in str(e) and decl in str(e), e
        else:
            raise AssertionError("preflight read a TOML 1.1 declaration")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
