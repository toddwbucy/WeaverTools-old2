"""No config names an SPU of its own (#716, the pass on 90b9a8a).

Run with `python3 test_round_seventeen.py` or under pytest.
"""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import determinism_matrix as dm  # noqa: E402
from test_recorded_seed import CFG, Reloading, cells_main, run_main  # noqa: E402

base = dm.base
WANT = "the config's spu_bin is refused: the admin launches the SPU its configuration names"


def test_a_config_naming_an_spu_is_refused_before_any_load_in_both_modes():
    # Codex's pass on 90b9a8a: `spu_bin` was hashed by both provenance
    # readers while the admin launched admin_config/spu-binary, so a
    # mismatch passed open. Perturbation: drop `spu_bin` from REFUSED_KEYS,
    # and both modes start.
    def with_spu(tmp, decl):
        path = os.path.join(tmp, "config.json")
        cfg = json.load(open(path))
        cfg["spu_bin"] = "/opt/weaver/bin/weaver-spu"
        json.dump(cfg, open(path, "w"))
    err, agent = io.StringIO(), Reloading()
    with contextlib.redirect_stderr(err):
        code, records, _ = run_main(agent, prepare=with_spu)
    assert code == 2 and records is None and agent.starts == 0 and WANT in err.getvalue(), (code, err.getvalue())
    err = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
        code, called, *_ = cells_main(tmp, dict(spu_bin="/opt/weaver/bin/weaver-spu"))
        assert code == 2 and called == [] and not os.path.exists(os.path.join(tmp, "out")), (code, called)
    assert WANT in err.getvalue(), err.getvalue()


def test_the_resolver_reads_the_admin_configuration_alone():
    # Perturbation: put the override back into _resolve_spu, and the
    # config's own path is hashed in place of the admin's.
    with tempfile.TemporaryDirectory() as tmp:
        for key, value in (("spu-binary", "/opt/weaver/bin/weaver-spu"), ("allow-list", "karl"),
                           ("worker-binary", "/opt/weaver/bin/worker"),
                           ("gate-binary", "/opt/weaver/bin/weaver-gate")):
            with open(os.path.join(tmp, key), "w") as fh:
                fh.write(value)
        cfg = dict(CFG, admin_config=tmp, spu_bin="/elsewhere/weaver-spu")
        assert base._resolve_spu(cfg) == ("/opt/weaver/bin/weaver-spu", "admin config spu-binary")
    assert "spu_bin" not in base.OPTIONAL_KEYS and "spu_bin" not in base.STACK_PATH_KEYS


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
