"""run5's journal evidence, which RESULT-2026-09-29.md reports: how many worker
invocations capture.py holds and how many lines each logged, whether every
invocation the record names is among them carrying each of the three device
markers, what else it holds, and journald's Suppressed lines over the run. Reads run5-evidence/ as
capture.py left it and the record, and writes to stdout."""
import json
import os
import statistics
from collections import Counter

R = "/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run5"
E = R + "/run5-evidence"
MARKERS = ("ggml_cuda_init", "using device", "loaded meta data")

counts = json.load(open(E + "/line-counts.json"))
print("invocations captured", len(counts), "lines", sum(counts.values()))
marks = {}
for line in open(E + "/markers.jsonl"):
    d = json.loads(line)
    per = marks.setdefault(d["invocation"], Counter())
    for m in MARKERS:
        if m in d["message"]:
            per[m] += 1
recorded = [i for l in open(R + "/matrix.jsonl") for i in (json.loads(l).get("invocations") or [])]
print("record invocations", len(recorded), "distinct", len(set(recorded)))
missing = [i for i in recorded if i not in counts]
print("record invocations the capture does not hold", len(missing), missing[:5])
shapes = Counter(tuple(marks.get(i, Counter())[m] for m in MARKERS) for i in recorded)
print("marker counts (cuda_init, using_device, loaded_meta) over record invocations", dict(shapes))
lines = [counts[i] for i in recorded if i in counts]
print("lines per record invocation: min", min(lines), "median", statistics.median(lines), "max", max(lines))
# The capture's first read starts a minute before the run, so it holds the
# smoke's loads, and it keys lines journald logged without an invocation ID
# under "null".
smoke = {i for l in open(R + "-smoke/matrix.jsonl") for i in (json.loads(l).get("invocations") or [])}
extra = set(counts) - set(recorded)
print("captured keys the record does not name", len(extra), "of which the smoke's", len(extra & smoke),
      "and others", sorted(extra - smoke))
print("lines: under the record's invocations", sum(counts[i] for i in set(recorded)),
      "under the smoke's", sum(counts[i] for i in extra & smoke), "under no invocation ID", counts.get("null"))
print("suppressed.txt bytes", os.path.getsize(E + "/suppressed.txt"))
