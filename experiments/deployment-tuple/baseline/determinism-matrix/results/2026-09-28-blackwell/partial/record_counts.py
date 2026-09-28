"""The partial run's counts from its per-session record: sessions and their
verdicts, turns compared and unmatched, turns of more than one token, and the
sweeps, which PARTIAL-2026-09-27.md reports. Verbatim from the inline command
run 2026-09-27 11:45 CDT, with the shell's $OUT written out."""
import json
from collections import Counter
recs=[json.loads(l) for l in open("/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573/matrix.jsonl")]
v=Counter(r["verdict"] for r in recs)
t=sum(len(r["turns"]) for r in recs); um=sum(1 for r in recs for x in r["turns"] if not x["matched"])
multi=sum(1 for r in recs for x in r["turns"] if x.get("entropy",{}).get("count",0)>1)
print(len(recs),"sessions",dict(v),"turns",t,"unmatched",um,"multi-token turns",multi,"iterations",max(r["iteration"] for r in recs))
print("last record iteration/probe/depth:",recs[-1]["iteration"],recs[-1]["probe"],recs[-1]["depth"])
