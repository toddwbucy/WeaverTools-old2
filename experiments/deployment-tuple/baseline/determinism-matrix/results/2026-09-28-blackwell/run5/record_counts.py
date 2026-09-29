"""run5's counts from its summary and per-session record, which
RESULT-2026-09-29.md reports: the summary's counts, windows and binding, any
record not reproduced, the sweeps, turns compared and unmatched, turns of more
than one token, the invocations and how many are distinct, the device bindings,
and the seeds. run3's script, with only this header and the deposit changed."""
import json
R="/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run5"
s=json.load(open(R+"/summary.json"))
print({k:s[k] for k in ('sessions','reproduced','diverged','errors')})
print({k:v.get('status') for k,v in s.items() if isinstance(v,dict) and 'status' in v})
print("serving_device", s['serving_device']); print("journal window", json.dumps(s['serving_device_journal_window'])[:200])
print("error_detail", s['error_detail'])
recs=[json.loads(l) for l in open(R+"/matrix.jsonl")]
bad=[r for r in recs if r['verdict']!='REPRODUCED']
for r in bad: print(json.dumps({k:r.get(k) for k in ('probe','depth','iteration','verdict','source_run','replay_run','invocations','seconds')})[:600])
print("records", len(recs), "sweeps", max(r['iteration'] for r in recs))
turns=sum(len(r['turns']) for r in recs); multi=sum(1 for r in recs for t in r['turns'] if (t.get('entropy') or {}).get('count',0)>1)
print("turns", turns, "multi", multi, "unmatched", sum(1 for r in recs for t in r['turns'] if not t['matched']))
inv=[i for r in recs for i in (r.get('invocations') or [])]; print("invocations", len(inv), len(set(inv)))
dev={json.dumps(r.get('devices'),sort_keys=True) for r in recs if r.get('devices')}; print("device bindings", len(dev), [d[:120] for d in dev])
print("seeds", {(r['declared_seed'], r['recorded_seed'], r['replay_recorded_seed']) for r in recs if r['verdict']=='REPRODUCED'})
