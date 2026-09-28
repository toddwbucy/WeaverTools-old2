"""run3's invocation counts, which RESULT-2026-09-28.md reports: how many
invocations the capture holds, the faulted invocation's line count and markers,
and which invocations lack any of the three device markers. The inline command
run 2026-09-28 at 04:56 CDT, verbatim but for its input. It read capture.py's
raw invocations.jsonl from a directory under the operator's home, which is not
kept. It reads here invocations-final.jsonl on the share, which
invocations_final.py wrote from that file one invocation per row, keeping each
one's longest read, the same reduction this script makes, so the output is the
same."""
import json
E="/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run3/run3-evidence"
rows={}
for l in open(E+"/invocations-final.jsonl"):
    d=json.loads(l); i=d["invocation"]
    if i not in rows or d["lines"]>rows[i]["lines"]: rows[i]=d
print("invocations captured", len(rows))
t="4b97c4b024044c1aa765d5feea628a55"
print("the faulted invocation:", rows.get(t))
full=[d for d in rows.values() if d["cuda_init"]==1 and d["using_device"]==1 and d["loaded_meta"]==1]
print("with all three markers", len(full), "without", [ (i, d["lines"], d["cuda_init"], d["using_device"], d["loaded_meta"]) for i,d in rows.items() if not (d["cuda_init"] and d["using_device"] and d["loaded_meta"])][:12])
