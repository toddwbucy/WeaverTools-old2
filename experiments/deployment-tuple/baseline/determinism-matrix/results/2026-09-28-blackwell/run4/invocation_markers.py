"""run4's journal evidence, which RESULT-2026-09-28.md reports: how many worker
invocations capture.py holds from 14:27:40, when each carries one of each of
the three device markers, whether the 13:24 fault's two invocations are among
them, and journald's Suppressed lines. Reads run4-evidence/ as capture.py left
it and writes to stdout."""
import json
import os
from collections import Counter

E = "/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run4/run4-evidence"
MARKERS = ("ggml_cuda_init", "using device", "loaded meta data")
FAULT = ("a7453f83c71a4974aa3f7d693a3efec9", "3dc5b2cbe7e448b9963cecedcfe353ef")

counts = json.load(open(E + "/line-counts.json"))
marks = {}
for line in open(E + "/markers.jsonl"):
    d = json.loads(line)
    per = marks.setdefault(d["invocation"], Counter())
    for m in MARKERS:
        if m in d["message"]:
            per[m] += 1
invocations = [i for i in counts if i != "null"]
print("invocations captured", len(invocations), "lines", sum(counts.values()),
      "under no invocation ID", counts.get("null"))
print("marker counts (cuda_init, using_device, loaded_meta)",
      dict(Counter(tuple(marks.get(i, Counter())[m] for m in MARKERS) for i in invocations)))
print("the 13:24 fault's invocations captured", [i in counts for i in FAULT])
print("suppressed.txt bytes", os.path.getsize(E + "/suppressed.txt"))
print(open(E + "/reads.log").read(), end="")
