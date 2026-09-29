"""Where a word occurs across files and directories, gzip included, with a
bounded context for each match.

    python3 specimen.py <word> <path> [<path> ...]

Stdlib only, and it writes nothing. Each `.gz` file is read decompressed. Each
file with a match prints its match count, then every match with 120
characters each side, the JSON escapes of the file left as they stand. It
reports where a word is and what surrounds it, and interprets nothing.
"""
import gzip
import os
import re
import sys


def read(path):
    try:
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError as exc:
        print(f"UNREADABLE {path}: {exc.strerror}")
        return ""


def files(root):
    if os.path.isfile(root):
        yield root
        return
    for directory, _, names in os.walk(root):
        for name in sorted(names):
            yield os.path.join(directory, name)


def main():
    word, roots = sys.argv[1], sys.argv[2:]
    pattern = re.compile(re.escape(word), re.I)
    for root in roots:
        total = 0
        for path in files(root):
            text = read(path)
            found = list(pattern.finditer(text))
            if not found:
                continue
            total += len(found)
            print(f"== {path}  matches={len(found)}")
            for m in found:
                context = text[max(0, m.start() - 120):m.end() + 120].replace("\n", "\\n")
                print(f"   @{m.start()}: ...{context}...")
        print(f"-- {root}: {total} matches")


if __name__ == "__main__":
    main()
