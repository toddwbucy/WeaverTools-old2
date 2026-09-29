"""The matrix reads the agent's own SPU, per weaver-admin-Spec section 9.

Perturbations, each failing a watch here: skip `_agent_spu` and read `spu-binary`
alone, and the named agent reads the default; return the map's choice for every
agent, and the unnamed agent reads the key; drop the relative-path check, and the
relative path is taken; judge spu-implementations only where agent-spu names
the run's agent, and a map admin refuses takes the default; read every OSError in
`_read_admin` as absence, and an unreadable map reads as the default; decide
presence with `os.path.exists`, and the SPU behind a directory this process may not
search reads as missing; read a required file's absence as absence, and an absent
spu-binary or allow-list passes under a map; split lines with Python's `str.split`,
and a field joined by \x1c reads as two.
"""
import os
import tempfile

import confirm_cells as g


# The four files admin's loader requires, each naming what a box would. A test
# omits one by naming it with None.
REQUIRED = {"allow-list": "karl\nada\n", "worker-binary": "/opt/weaver/bin/worker\n",
            "spu-binary": "/opt/weaver/bin/weaver-spu\n",
            "gate-binary": "/opt/weaver/bin/weaver-gate\n"}


def resolve(files, agent="karl"):
    root = tempfile.mkdtemp()
    for name, text in {**REQUIRED, **files}.items():
        if text is not None:
            with open(os.path.join(root, name), "w") as f:
                f.write(text)
    return g._resolve_spu({"admin_config": root, "agent": agent,
                           "admin_bin": "/opt/weaver/bin/weaver-admin"})


def test_without_the_map_the_default_stands():
    assert resolve({"spu-binary": "/opt/weaver/bin/weaver-spu\n"}) == (
        "/opt/weaver/bin/weaver-spu", "admin config spu-binary")


def test_a_named_agent_reads_its_key():
    files = {"spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n",
             "agent-spu": "karl python\n"}
    assert resolve(files) == ("/opt/weaver/python-spu/python-spu.pyz",
                              "admin config agent-spu key python")
    assert resolve(files, agent="ada") == ("/opt/weaver/bin/weaver-spu",
                                           "admin config spu-binary")


def test_a_map_it_cannot_follow_is_reported():
    base = {"allow-list": "karl\n"}
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
    """At each of the six paths, anything that stands and does not read is an
    unreadable resolution, never the default and never the guess beside admin_bin,
    for the agent the map names as for the one it does not."""
    base = {**REQUIRED,
            "spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n",
            "agent-spu": "karl python\n"}
    for name in base:
        probe = tempfile.mkdtemp()
        for form, make in unreadable_forms(probe, name):
            root = tempfile.mkdtemp()
            for other, text in base.items():
                if other != name:
                    with open(os.path.join(root, other), "w") as f:
                        f.write(text)
            dict(unreadable_forms(root, name))[form]()
            for agent in ("karl", "ada"):
                cfg = {"admin_config": root, "agent": agent,
                       "admin_bin": "/opt/weaver/bin/weaver-admin"}
                path, why = g._resolve_spu(cfg)
                assert path is None, (name, form, agent, path, why)
                assert name in why, (name, form, agent, why)


def test_a_required_file_absent_is_unreadable_under_any_map():
    """Admin's loader reads allow-list, worker-binary, spu-binary and gate-binary
    as required, refusing every verb where one is absent, so each one's absence is
    an unreadable resolution: under a map choosing an alternate for the run's
    agent, under a map naming another, and with no map at all. Never the map's
    choice, never the default, never the guess beside admin_bin."""
    maps = [
        {"spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n",
         "agent-spu": "karl python\n"},
        {"spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n",
         "agent-spu": "ada python\n"},
        {},
    ]
    for name in g._ADMIN_REQUIRED:
        for chosen in maps:
            path, why = resolve({**chosen, name: None})
            assert path is None, (name, chosen, path, why)
            assert name in why and "absent, and admin requires it" in why, (name, chosen, why)


def test_the_planners_two_cases():
    """An absent spu-binary with a map selecting an alternate, and an absent
    allow-list with a map present: both unreadable."""
    path, why = resolve({"spu-binary": None,
                         "spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n",
                         "agent-spu": "karl python\n"})
    assert path is None and "spu-binary" in why, (path, why)
    path, why = resolve({"allow-list": None,
                         "spu-implementations": "python /opt/weaver/python-spu/python-spu.pyz\n"})
    assert path is None and "allow-list" in why, (path, why)


def test_a_spu_binary_naming_no_path_is_unreadable_never_the_guess():
    """Admin launches the empty path where spu-binary names none, which is no SPU,
    so the guess beside admin_bin does not stand in for it."""
    for text in ("", "\n", "  \n"):
        path, why = resolve({"spu-binary": text}, agent="ada")
        assert path is None and "names no path" in why, (text, path, why)


def test_a_file_admin_does_not_class_is_refused():
    """Every name `_read_admin` reads is classed as admin's loader classes it, so a
    new reader cannot read a file without saying which it is."""
    try:
        g._read_admin(tempfile.mkdtemp(), "coordination-root")
    except ValueError:
        return
    raise AssertionError("an unclassed admin file was read")


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
    ({"spu-implementations": "python\x1c/opt/p/a.pyz"}, "expected two fields"),
    ({"spu-implementations": "python /opt/p/worker/"}, "shares its file name"),
]


def test_every_rule_of_admins_is_the_matrixs():
    for change, said in RULES:
        path, why = resolve(change)
        assert path is None and said in why, (change, path, why)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all watches held")
