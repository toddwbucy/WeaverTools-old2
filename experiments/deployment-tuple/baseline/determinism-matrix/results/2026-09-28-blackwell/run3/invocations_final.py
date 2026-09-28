"""Writes invocations-final.jsonl, one row per invocation keeping its longest
read, from capture.py's raw invocations.jsonl. The inline command run
2026-09-28 at 04:57 CDT, verbatim but for its directory, which was under the
operator's home and is written here as the current one. The raw file is not kept, so this does not rerun, and
invocations-final.jsonl on the share is its output."""
import json
E="."
rows={}
for l in open(E+"/invocations.jsonl"):
    d=json.loads(l); i=d["invocation"]
    if i not in rows or d["lines"]>rows[i]["lines"]: rows[i]=d
with open(E+"/invocations-final.jsonl","w") as fh:
    for i,d in sorted(rows.items(), key=lambda kv: kv[1]["first_us"] or ""):
        fh.write(json.dumps(d)+"\n")
print(len(rows))
