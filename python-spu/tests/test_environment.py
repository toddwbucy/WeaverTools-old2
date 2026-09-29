"""The environment's rules, per python-spu-Spec sections 2, 5 and 8."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from python_spu.client import LocalProcess
from python_spu.transport import ChannelFault, Closed

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_zipapp  # noqa: E402
import tree_digest  # noqa: E402


def rust_spu():
    """The Rust SPU this box serves, from admin's configuration."""
    stated = os.environ.get("WEAVER_RUST_SPU")
    if stated:
        return stated
    try:
        return Path("/etc/weaver/admin/spu-binary").read_text().strip()
    except OSError:
        return None


def test_expf_resolves_to_the_libm_the_rust_spu_links():
    """Section 5's bit-for-bit claim rests on the port's expf being the one the Rust
    SPU's f32::exp calls. The port loads libm through ctypes, and this reads the
    library the process mapped against the one the Rust binary links."""
    spu = rust_spu()
    if not spu or not os.path.exists(spu):
        pytest.skip("no Rust SPU on this box to compare against")
    from python_spu import candle_chain
    assert candle_chain.expf(0.0) == 1.0
    mapped = {os.path.realpath(line.split()[-1]) for line in open("/proc/self/maps")
              if re.search(r"/libm[.-][^/]*$", line.strip())}
    linked = [line for line in subprocess.run(["ldd", spu], capture_output=True, text=True,
                                              check=True).stdout.splitlines()
              if line.strip().startswith("libm.so")]
    assert len(linked) == 1, linked
    assert mapped == {os.path.realpath(linked[0].split("=>")[1].split()[0])}, (mapped, linked)


def serve_once(tmp_path, tiny_model, extra_environment=None):
    """A real server process through admission and one generation, with the import
    set judged as main() judges it. Answers the process's exit and stderr where it
    died, and None where it answered the generation."""
    environment = dict(os.environ, **(extra_environment or {}))
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(environment)
    try:
        process = LocalProcess(tmp_path / "stderr.txt")
    finally:
        os.environ.clear()
        os.environ.update(saved)
    identity = [{"role": "system", "content": [{"type": "text", "text": "be precise"}]}]
    instruction = {"decoder": {
        "model-binding": {"artifact": str(tiny_model), "devices": [0]},
        "residual-readout-election": False, "surprisal-election": True, "identity": identity,
        "tunable-values": {"seed": 11, "context-capacity": 256, "max-tokens-per-turn": 4}}}
    try:
        answer = process.ask({"kind": "admit", "instruction": instruction})
        assert answer["payload"] == {"kind": "answer", "body": {"kind": "admitted"}}
        decode = process.channels[1]
        decode.send({"kind": "open", "session": "import-set", "messages": identity})
        assert decode.receive() == {"kind": "opened"}
        decode.send({"kind": "append_and_generate", "turn": "import-set-turn", "delta": [
            {"role": "user", "content": [{"type": "text", "text": "hello world"}]}]})
        while True:
            frame = decode.receive()
            if frame["kind"] == "generated":
                return None
    except (Closed, ChannelFault, ConnectionError, AssertionError, OSError, ValueError):
        pass
    _, status = os.waitpid(process.pid, 0)
    return os.waitstatus_to_exitcode(status), (tmp_path / "stderr.txt").read_text()


def test_the_import_set_holds_through_admission_and_generation(tmp_path, tiny_model):
    """The CPU half of the declared list covers a clean serving run. Where this fails
    the list is stale, and scripts/declare_imports.py regenerates it for review."""
    assert serve_once(tmp_path, tiny_model) is None, (tmp_path / "stderr.txt").read_text()


def test_an_extra_import_faults_the_process(tmp_path, tiny_model):
    """The perturbation section 8 names: a module the list does not declare, here
    imported at startup through sitecustomize, faults the process at admission,
    naming the module, and it never answers."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text("import xml.dom.minidom\n")
    path = os.pathsep.join([str(site), os.environ.get("PYTHONPATH", "")])
    died = serve_once(tmp_path, tiny_model, {"PYTHONPATH": path})
    assert died is not None, "the undeclared module was served past"
    code, stderr = died
    assert code == 3, (code, stderr)
    fault = json.loads(stderr.strip().splitlines()[-1])
    assert fault["import_set_violation"] == "admission"
    assert "xml.dom.minidom" in fault["undeclared"]


def test_the_zipapp_is_reproducible_and_launches(tmp_path):
    first = build_zipapp.build(ROOT / "src", tmp_path / "a.pyz", sys.executable)
    second = build_zipapp.build(ROOT / "src", tmp_path / "b.pyz", sys.executable)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().startswith(b"#!" + sys.executable.encode() + b"\n")
    shown = subprocess.run([str(first), "--help"], capture_output=True, text=True, timeout=120)
    assert shown.returncode == 0, shown.stderr
    assert "--declare-imports" in shown.stdout
    import zipfile
    names = zipfile.ZipFile(first).namelist()
    assert "python_spu/imports.txt" in names and "python_spu/classifier.py" not in names


def test_the_tree_digest_reads_files_and_links_and_refuses_the_rest(tmp_path):
    tree = tmp_path / "tree"
    (tree / "lib").mkdir(parents=True)
    (tree / "lib" / "a.py").write_text("a\n")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    (tree / "bin").mkdir()
    os.symlink(outside, tree / "bin" / "link")
    first = tree_digest.digest(tree)
    assert tree_digest.digest(tree) == first
    outside.write_text("changed\n")
    assert tree_digest.digest(tree) == first, "a link is read by its text and never followed"
    (tree / "lib" / "a.py").write_text("b\n")
    assert tree_digest.digest(tree) != first
    os.mkfifo(tree / "lib" / "pipe")
    with pytest.raises(ValueError):
        tree_digest.digest(tree)
