"""Read-only: every worker line carrying a device marker, with its journal sequence
number, timestamp and PID, and each invocation's line count, plus journald's
Suppressed lines, captured every two minutes over the last five so they outlive a
journal that holds about twelve minutes. Writes only into this directory, and stops
when the matrix process whose PID it is given has exited.

Usage: python3 capture.py <matrix pid> [<since>]

The first read starts at <since>, a journalctl time, where one is given, and at the
start of the day otherwise.
"""
import json, os, subprocess, sys, time
OUT = os.path.dirname(os.path.abspath(__file__))
PID = int(sys.argv[1])
SINCE = sys.argv[2] if len(sys.argv) > 2 else "today"
MARKERS = ("ggml_cuda_init", "using device", "loaded meta data")
seen = set()
counts = {}

def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False

def read(since):
    r = subprocess.run(["journalctl", "-u", "weaver-worker@karl.service", "--since", since, "-o", "json",
                        "--output-fields=_SYSTEMD_INVOCATION_ID,MESSAGE,_PID,__SEQNUM,__SEQNUM_ID",
                        "--no-pager", "-q"], capture_output=True, text=True)
    with open(os.path.join(OUT, "markers.jsonl"), "a") as fh:
        for line in r.stdout.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            key = (e.get("__SEQNUM_ID"), e.get("__SEQNUM"))
            if key in seen:
                continue
            seen.add(key)
            inv = e.get("_SYSTEMD_INVOCATION_ID")
            counts[inv] = counts.get(inv, 0) + 1
            m = str(e.get("MESSAGE", ""))
            if any(k in m for k in MARKERS):
                fh.write(json.dumps({"invocation": inv, "seqnum": e.get("__SEQNUM"), "seqnum_id": e.get("__SEQNUM_ID"),
                                     "realtime_us": e.get("__REALTIME_TIMESTAMP"), "pid": e.get("_PID"),
                                     "message": m}) + "\n")
    s = subprocess.run(["journalctl", "-u", "systemd-journald", "--since", since, "-o", "short-iso-precise",
                        "--no-pager", "-q", "-g", "Suppressed"], capture_output=True, text=True).stdout
    with open(os.path.join(OUT, "suppressed.txt"), "a") as fh:
        fh.write(s)
    oldest = subprocess.run("journalctl -o short-iso-precise -q --no-pager | head -1", shell=True,
                            capture_output=True, text=True).stdout.split(" ")[0]
    with open(os.path.join(OUT, "reads.log"), "a") as fh:
        fh.write(f"{time.strftime('%F %T')} since={since} new_lines_total={sum(counts.values())} journal_oldest={oldest}\n")
    with open(os.path.join(OUT, "line-counts.json"), "w") as fh:
        json.dump(counts, fh)

read(SINCE)                       # from the run's first minute
while alive(PID):
    time.sleep(120)
    read("-5min")
read("-5min")                     # the run's last minutes
