"""The matrix reads the agent's own SPU, per weaver-admin-Spec section 9.

Perturbations, each failing a watch here: skip `_agent_spu` and read `spu-binary`
alone, and the named agent reads the default; return the map's choice for every
agent, and the unnamed agent reads the key; drop the relative-path check, and the
relative path is taken.
"""
import os
import tempfile

import confirm_cells as g


def resolve(files, agent="karl"):
    root = tempfile.mkdtemp()
    for name, text in files.items():
        with open(os.path.join(root, name), "w") as f:
            f.write(text)
    return g._resolve_spu({"admin_config": root, "agent": agent})


def test_without_the_map_the_default_stands():
    assert resolve({"spu-binary": "/opt/weaver/bin/weaver-spu\n"}) == (
        "/opt/weaver/bin/weaver-spu", "admin config spu-binary")


def test_a_named_agent_reads_its_key():
    files = {"spu-binary": "/opt/weaver/bin/weaver-spu\n",
             "spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n",
             "agent-spu": "karl python\n"}
    assert resolve(files) == ("/opt/weaver/python-spu/python-spu.pyz",
                              "admin config agent-spu key python")
    assert resolve(files, agent="ada") == ("/opt/weaver/bin/weaver-spu",
                                           "admin config spu-binary")


def test_a_map_it_cannot_follow_is_reported():
    base = {"spu-binary": "/opt/weaver/bin/weaver-spu\n"}
    cases = [
        ({"agent-spu": "karl rust\n", "spu-implementations": "python /p/python-spu.pyz\n"},
         "does not hold"),
        ({"agent-spu": "karl python\n", "spu-implementations": "python p/python-spu.pyz\n"},
         "relative path"),
        ({"agent-spu": "karl\n"}, "not two fields"),
    ]
    for files, said in cases:
        path, why = resolve({**base, **files})
        assert path is None, files
        assert said in why, (files, why)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all watches held")
