"""The matrix reads the agent's own SPU, per weaver-admin-Spec section 9.

Perturbations, each failing a watch here: skip `_agent_spu` and read `spu-binary`
alone, and the named agent reads the default; return the map's choice for every
agent, and the unnamed agent reads the key; drop the relative-path check, and the
relative path is taken; judge spu-implementations only where agent-spu names
the run's agent, and a map admin refuses takes the default; read every OSError in `_read_admin` as absence, and an
unreadable map reads as the default; decide presence with `os.path.exists`, and the
SPU behind a directory this process may not search reads as missing.
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
    files = {"spu-binary": "/opt/weaver/bin/weaver-spu\n", "allow-list": "karl\nada\n",
             "spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n",
             "agent-spu": "karl python\n"}
    assert resolve(files) == ("/opt/weaver/python-spu/python-spu.pyz",
                              "admin config agent-spu key python")
    assert resolve(files, agent="ada") == ("/opt/weaver/bin/weaver-spu",
                                           "admin config spu-binary")


def test_a_map_it_cannot_follow_is_reported():
    base = {"spu-binary": "/opt/weaver/bin/weaver-spu\n", "allow-list": "karl\n"}
    cases = [
        ({"agent-spu": "karl rust\n", "spu-implementations": "python /p/python-spu.pyz\n"},
         "not in spu-implementations"),
        ({"agent-spu": "karl python\n", "spu-implementations": "python p/python-spu.pyz\n"},
         "is not absolute"),
        ({"agent-spu": "karl\n"}, "expected two fields"),
    ]
    for files, said in cases:
        path, why = resolve({**base, **files})
        assert path is None, files
        assert said in why, (files, why)


def unreadable_forms(root, name):
    """Each way something can stand at a path and not read: a file this process
    may not read, a directory, a dangling link, and bytes that are not UTF-8."""
    path = os.path.join(root, name)
    forms = []
    if os.geteuid() != 0:
        forms.append(("mode 000", lambda: (open(path, "w").write("karl python\n"),
                                           os.chmod(path, 0o000))))
    forms.append(("a directory", lambda: os.mkdir(path)))
    forms.append(("a dangling link", lambda: os.symlink(os.path.join(root, "gone"), path)))
    forms.append(("not UTF-8", lambda: open(path, "wb").write(b"\xff\xfe karl\n")))
    return forms


def test_an_unreadable_value_is_unreadable_never_the_default():
    """At each of the three paths, anything that stands and does not read is an
    unreadable resolution, never the default and never the guess beside admin_bin.
    Only absence falls back."""
    base = {"spu-binary": "/opt/weaver/bin/weaver-spu\n", "allow-list": "karl\nada\n",
            "spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n",
            "agent-spu": "karl python\n"}
    for name in ("agent-spu", "spu-implementations", "spu-binary"):
        probe = tempfile.mkdtemp()
        for form, make in unreadable_forms(probe, name):
            root = tempfile.mkdtemp()
            for other, text in base.items():
                if other != name:
                    with open(os.path.join(root, other), "w") as f:
                        f.write(text)
            dict(unreadable_forms(root, name))[form]()
            cfg = {"admin_config": root, "agent": "karl", "admin_bin": "/opt/weaver/bin/weaver-admin"}
            path, why = g._resolve_spu(cfg)
            if name == "spu-binary":
                # agent-spu names karl, so spu-binary is not consulted for him.
                cfg["agent"] = "ada"
                path, why = g._resolve_spu(cfg)
            assert path is None, (name, form, path, why)
            assert name in why, (name, form, why)


def test_the_spu_behind_an_unsearchable_directory_does_not_read_as_missing():
    """`os.path.exists` answers False for a path under a directory this process
    may not search. The check reads the difference, against a real 0o000
    directory."""
    if os.geteuid() == 0:
        print("skip: root searches every directory")
        return
    root = tempfile.mkdtemp()
    walled = os.path.join(root, "walled")
    os.mkdir(walled)
    spu = os.path.join(walled, "weaver-spu")
    open(spu, "w").close()
    os.chmod(walled, 0o000)
    try:
        answer = g.engine_libraries({"admin_config": root}, spu=(spu, "test"))
    finally:
        os.chmod(walled, 0o700)
    assert "does not stat" in answer["unreadable"], answer
    gone = g.engine_libraries({"admin_config": root}, spu=(os.path.join(root, "gone"), "test"))
    assert gone["unreadable"].startswith("no SPU binary at"), gone


def test_a_map_admin_refuses_is_unreadable_whoever_it_names():
    """Admin judges both maps on every invocation, so a malformed
    spu-implementations is refused whether agent-spu is absent or names someone
    else, and the matrix never hashes the default over it. Perturbation: judge
    spu-implementations only where agent-spu names the run's agent, as the first
    form did, and both cases take the default."""
    bad = "python relative/python-spu.pyz\n"
    for agents in (None, "ada python\n"):
        files = {"spu-binary": "/opt/weaver/bin/weaver-spu\n", "allow-list": "karl\nada\n",
                 "spu-implementations": bad}
        if agents:
            files["agent-spu"] = agents
        path, why = resolve(files)
        assert path is None and "not absolute" in why, (agents, path, why)


# Admin's section 9 checks, rule for rule, each case the Rust suite's
# every_contradiction_fails_naming_itself holds, with the message both say.
RULES = [
    ({"spu-implementations": "python"}, "expected two fields"),
    ({"spu-implementations": "python /a /b"}, "expected two fields"),
    ({"spu-implementations": "Python /opt/p/python-spu.pyz"}, "is not lowercase"),
    ({"spu-implementations": "py_thon /opt/p/python-spu.pyz"}, "is not lowercase"),
    ({"spu-implementations": "python opt/p/python-spu.pyz"}, "is not absolute"),
    ({"spu-implementations": "python /opt/p/a.pyz\npython /opt/p/b.pyz"}, "is named twice"),
    ({"spu-implementations": "python /opt/p/a.pyz", "agent-spu": "karl"}, "expected two fields"),
    ({"spu-implementations": "python /opt/p/a.pyz", "agent-spu": "eve python"}, "not on the allow-list"),
    ({"spu-implementations": "python /opt/p/a.pyz", "agent-spu": "karl rust"}, "not in spu-implementations"),
    ({"spu-implementations": "python /opt/p/a.pyz", "agent-spu": "karl python\nkarl python"}, "is named twice"),
    ({"spu-implementations": "python /opt/p/worker"}, "shares its file name"),
    ({"spu-implementations": "python /opt/p/weaver-gate"}, "shares its file name"),
    ({"spu-implementations": "python /opt/p/weaver-state"}, "shares its file name"),
    ({"spu-binary": "/opt/other/worker"}, "shares its file name"),
    ({"gate-binary": "/opt/other/worker"}, "share the file name"),
    ({"gate-binary": "/opt/other/weaver-state"}, "share the file name"),
]


def test_every_rule_of_admins_is_the_matrixs():
    for change, said in RULES:
        files = {"allow-list": "karl\nada\n", "spu-binary": "/opt/weaver/bin/weaver-spu\n",
                 "worker-binary": "/opt/weaver/bin/worker\n",
                 "gate-binary": "/opt/weaver/bin/weaver-gate\n", **change}
        path, why = resolve(files)
        assert path is None and said in why, (change, path, why)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all watches held")
