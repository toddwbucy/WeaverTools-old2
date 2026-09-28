"""run2's counts from its per-session record, which run2-close/stats.txt holds
and RESULT-2026-09-27.md reports: sessions, sweeps, turns compared and
unmatched, turns of more than one token, and the seeds recorded. Verbatim from
the inline command run 2026-09-27 18:49 CDT, its output redirected to
run2-close/stats.txt."""
import json, collections
R='/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run2/matrix.jsonl'
n=turns=multi=unmatched=0; iters=set(); seeds=collections.Counter(); keys=set(); steps=0
for l in open(R):
    r=json.loads(l); n+=1; iters.add(r['iteration']); seeds[(r.get('declared_seed'),r.get('recorded_seed'),r.get('replay_recorded_seed'))]+=1
    keys|=set(r)
    for t in r['turns']:
        turns+=1; unmatched+= not t['matched']
        e=t.get('entropy') or {}
        multi+= (e.get('count',0) or 0)>1
print('sessions',n,'sweeps',min(iters),max(iters),'turns',turns,'unmatched',unmatched,'multi-token turns',multi)
print('seeds',dict(seeds)); print('record keys',sorted(keys))
