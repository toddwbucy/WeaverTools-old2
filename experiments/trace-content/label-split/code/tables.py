"""The split's markdown tables, from the `split.json` segment.py writes.

    python3 tables.py <split.json>

Stdlib only; it prints two tables, by level and by result set, each with the
three shares on the two weightings segment.py counts: every position of the
completions whose text is on disk, and the positions the model wrote (prose,
drafts and program steps). A set with no text on disk shows its
every-position shares, marked, since its prose was never recorded. It writes
nothing.
"""
import json
import sys

BUCKETS = ("computable", "judgmental", "unreached")


def shares(c):
    total = sum(c.get(b, 0) for b in BUCKETS)
    return total, [100.0 * c.get(b, 0) / total if total else 0.0 for b in BUCKETS]


def table(counts, prefix, title):
    print(f"\n{title}\n")
    print("| | positions | C | J | U | authored | C | J | U |")
    print("|---|---|---|---|---|---|---|---|---|")
    for group in sorted(g for g in counts if g.startswith(prefix) and "|" not in g):
        text = counts.get(f"{group}|text", {})
        marked = ""
        if not sum(text.values()):
            text, marked = counts[group], " (no text on disk)"
        total, s = shares(text)
        a_total, a = shares(counts.get(f"{group}|authored", {}))
        print(f"| {group[len(prefix):]}{marked} | {total} | {s[0]:.1f} | {s[1]:.1f} | {s[2]:.1f} "
              f"| {a_total} | {a[0]:.1f} | {a[1]:.1f} | {a[2]:.1f} |")


def main():
    split = json.load(open(sys.argv[1]))
    counts = split["counts"]
    for group, name in (("all|text", "every position, text on disk"),
                        ("all|authored", "what the model wrote")):
        total, s = shares(counts[group])
        print(f"{name}: {total} positions, computable {s[0]:.1f}%, judgmental {s[1]:.1f}%, "
              f"unreached {s[2]:.1f}%")
    table(counts, "level:", "By level")
    table(counts, "model:", "By result set")


if __name__ == "__main__":
    main()
