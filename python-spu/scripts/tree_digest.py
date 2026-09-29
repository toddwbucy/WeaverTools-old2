"""Digests an installed tree, per python-spu-Spec section 8.

A lock states what should be installed, and this reads what is. Every entry under
the root is listed by its path relative to the root, sorted: a regular file by its
sha256, a symbolic link by the text it points to and never followed, and anything
else refused. The listing's own sha256 is the tree's digest, so two trees agree on
the digest exactly where they agree on every file and every link.

Usage: python3 scripts/tree_digest.py <root> [--list]
"""
import hashlib
import os
import stat
import sys


def listing(root):
    lines = []
    for directory, subdirectories, files in os.walk(root, followlinks=False):
        subdirectories.sort()
        for name in sorted(files + [d for d in subdirectories
                                    if os.path.islink(os.path.join(directory, d))]):
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, root)
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode):
                lines.append(f"link {os.readlink(path)}  {relative}")
            elif stat.S_ISREG(mode):
                digest = hashlib.sha256()
                with open(path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        digest.update(chunk)
                lines.append(f"{digest.hexdigest()}  {relative}")
            else:
                raise ValueError(f"{relative} is neither a file nor a link")
    return sorted(lines, key=lambda line: line.split("  ", 1)[1])


def digest(root):
    text = "\n".join(listing(root)) + "\n"
    return hashlib.sha256(text.encode()).hexdigest()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    root = argv[0]
    if "--list" in argv[1:]:
        print("\n".join(listing(root)))
    print(f"{digest(root)}  {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
