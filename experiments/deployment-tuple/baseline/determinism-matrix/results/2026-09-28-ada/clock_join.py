# Carried from experiments/deployment-tuple/baseline/determinism-matrix/results/2026-09-28-blackwell/run3/clock_join.py
# as landed on main by 0f105bd3 in #719 and unchanged through 52d6da8e, byte for byte below this
# comment. Run as: python3 clock_join.py <deposit> [<deposit> ...]
# It backs the clock paragraph of README.md and of the RESULT note beside it. Its session
# bounds are approximate, per issue #721, and the per-clock-state counts it gives are
# approximate with them, which the note says where it uses them.
"""Join clock.log's 5 s dmon samples to matrix.jsonl's sessions.

A session spans from its source run's start to its replay run's start plus
the replay's own turns. The run IDs carry UTC starts, dmon's samples carry
local time (-0500 on 2026-09-27). Each session takes every sample inside
[source start, replay start + replay turn time + 2 s]. A session shorter
than the 5 s cadence may take one sample or none, and is reported as such
rather than given a borrowed reading.

Usage: python3 clock_join.py <deposit> [<deposit> ...]
"""
import datetime
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

LOCAL = datetime.timezone(datetime.timedelta(hours=-5))


def samples(path):
    out = []
    for line in Path(path).read_text().splitlines():
        if line.startswith('#') or not line.strip():
            continue
        date, time, _gpu, pwr, gtemp, _mtemp, mclk, pclk = line.split()
        at = datetime.datetime.strptime(date + time, '%Y%m%d%H:%M:%S').replace(tzinfo=LOCAL)
        out.append((at.timestamp(), int(pwr), int(gtemp), int(mclk), int(pclk)))
    return out


def start(run):
    return datetime.datetime.fromisoformat(run.split('Z-')[0] + '+00:00').timestamp()


def join(deposit):
    clock = samples(Path(deposit) / 'clock.log')
    rows = []
    for line in open(Path(deposit) / 'matrix.jsonl'):
        r = json.loads(line)
        # A session that faulted before its replay has no replay run and no
        # span to join, and is left out of the join (run3's copy).
        if not r.get('replay_run'):
            continue
        replay_ms = sum(t.get('replay_ms') or 0 for t in r['turns'])
        lo, hi = start(r['source_run']), start(r['replay_run']) + replay_ms / 1000 + 2
        inside = [s for s in clock if lo <= s[0] <= hi]
        rows.append(dict(verdict=r['verdict'], probe=r['probe'], depth=r['depth'],
                         n=len(inside), mclk=sorted({s[3] for s in inside}),
                         pclk=[s[4] for s in inside], gtemp=[s[2] for s in inside]))
    return clock, rows


def report(deposit):
    clock, rows = join(deposit)
    seen = [r for r in rows if r['n']]
    busy = [s for s in clock if s[4] > 600]
    print(f'== {deposit}')
    print(f'  samples {len(clock)}, sessions {len(rows)}, sessions with a sample inside {len(seen)}')
    print(f'  verdicts {dict(Counter(r["verdict"] for r in rows))}')
    print(f'  mclk states across all samples {dict(sorted(Counter(s[3] for s in clock).items()))}')
    if busy:
        pc = [s[4] for s in busy]
        print(f'  pclk under load (>600 MHz): min {min(pc)} median {statistics.median(pc)} max {max(pc)}')
    print(f'  gtemp range {min(s[2] for s in clock)} to {max(s[2] for s in clock)} C')
    spans = [r for r in seen if len(r['mclk']) > 1]
    print(f'  sessions whose samples saw more than one mclk: {len(spans)}, '
          f'all reproduced: {all(r["verdict"] == "REPRODUCED" for r in spans)}')
    by = Counter(tuple(r['mclk']) for r in seen)
    print('  sessions by the mclk set their samples saw:')
    for k, v in by.most_common(8):
        print(f'    {list(k)}: {v}')
    pmin = min((min(r['pclk']) for r in seen), default=None)
    pmax = max((max(r['pclk']) for r in seen), default=None)
    print(f'  pclk inside sessions: {pmin} to {pmax} MHz')


if __name__ == '__main__':
    for d in sys.argv[1:]:
        report(d)
