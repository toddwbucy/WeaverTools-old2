"""Where a word occurs across files and directories, gzip included, with a
bounded context for each match.

    python3 specimen.py <word> <path> [<path> ...]

Stdlib only, and it writes nothing. Each `.gz` file is read decompressed. Each
file with a match prints its match count, then every match with 120
characters each side, the JSON escapes of the file left as they stand. It
reports where a word is and what surrounds it, and interprets nothing.

**A place it could not read is never a place with no match.** Every root must
exist and be readable, and a directory traversable, before the search starts,
and a directory the walk cannot enter or a file it cannot open is printed and
counted, so the run exits 1 where any of them occurred and a count of zero
means zero.
"""
import gzip
import os
import re
import sys


FAULTS = []


def fault(path, why):
    FAULTS.append(path)
    print(f"UNREADABLE {path}: {why}")


def read(path):
    try:
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError as exc:
        fault(path, exc.strerror or repr(exc))
        return ""


def files(root):
    if os.path.isfile(root):
        yield root
        return
    for directory, _, names in os.walk(root, onerror=lambda e: fault(e.filename, e.strerror)):
        for name in sorted(names):
            yield os.path.join(directory, name)


def readable(root):
    """The root exists, and is a readable file or a traversable directory."""
    if not os.path.exists(root):
        return "does not exist"
    if os.path.isdir(root):
        return None if os.access(root, os.R_OK | os.X_OK) else "is not traversable"
    return None if os.access(root, os.R_OK) else "is not readable"


def main():
    word, roots = sys.argv[1], sys.argv[2:]
    pattern = re.compile(re.escape(word), re.I)
    refused = [(root, why) for root in roots if (why := readable(root))]
    for root, why in refused:
        print(f"REFUSED {root}: {why}")
    if refused:
        sys.exit(1)
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
    if FAULTS:
        print(f"-- {len(FAULTS)} places could not be read, so the counts above are not complete")
        sys.exit(1)


if __name__ == "__main__":
    main()
