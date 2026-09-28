"""How many of run2's sessions had both loads inside the closing journal
capture, whose oldest entry is 23:39:27.769 UTC, and how many straddle it, which
RESULT-2026-09-27.md reports. The inline command run 2026-09-27 at 18:49 CDT,
verbatim."""
import json, datetime
R='/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run2/matrix.jsonl'
cut=datetime.datetime(2026,9,27,23,39,27,769000,tzinfo=datetime.timezone.utc).timestamp()
def st(run): return datetime.datetime.fromisoformat(run.split('Z-')[0]+'+00:00').timestamp()
rows=[json.loads(l) for l in open(R)]
inside=[r for r in rows if st(r['source_run'])>=cut]
print('sessions with both loads after the oldest retained entry:', len(inside), 'first', inside[0]['source_run'][:23], 'last', rows[-1]['replay_run'][:23])
straddle=[r for r in rows if st(r['source_run'])<cut<=st(r['replay_run'])]
print('straddling', len(straddle))
