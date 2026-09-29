"""Builds python-spu as one file, per python-spu-Spec section 2.

The file is a zip archive of src/python_spu behind a first line naming the pinned
interpreter by absolute path, so the digest admin takes of it covers every line of
python-spu's own code and fixes which interpreter runs it. The classifier stays out,
section 1 scoping the classify role out of this implementation. Entries are sorted and
dated 1980-01-01 with fixed modes, so one tree always builds one file and the digest
names the code rather than the moment of the build.

Usage: python3 scripts/build_zipapp.py [--interpreter PATH] [--output PATH]
"""
import argparse
import io
import os
import sys
import zipfile
from pathlib import Path

INTERPRETER = "/opt/weaver/python-spu/bin/python3.14"
LEFT_OUT = {"classifier.py"}
MAIN = "import sys\nfrom python_spu.server import main\nsys.exit(main())\n"


def entry(name):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.external_attr = 0o644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build(source, output, interpreter=INTERPRETER):
    package = Path(source) / "python_spu"
    files = sorted(
        p for p in package.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.name not in LEFT_OUT
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in files:
            archive.writestr(entry(path.relative_to(source).as_posix()), path.read_bytes())
        archive.writestr(entry("__main__.py"), MAIN)
    output = Path(output)
    output.write_bytes(b"#!" + interpreter.encode() + b"\n" + buffer.getvalue())
    os.chmod(output, 0o755)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--interpreter", default=INTERPRETER)
    parser.add_argument("--output", default="python-spu.pyz")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    print(build(root / "src", args.output, args.interpreter))
    return 0


if __name__ == "__main__":
    sys.exit(main())
