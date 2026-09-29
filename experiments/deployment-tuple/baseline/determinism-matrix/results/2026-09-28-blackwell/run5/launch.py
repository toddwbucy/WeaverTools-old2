"""Waits for run5's matrix process, found by its exact --outdir in /proc and never by
a pattern that could match this watcher, then starts capture.py in the deposit's
run5-evidence/ with the first read from one minute before the process was found."""
import os, sys, time, shutil, subprocess, datetime
D = "/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-28-39fe573-run5"
HERE = os.path.dirname(os.path.abspath(__file__))
ME = os.getpid()

def find():
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == ME:
            continue
        try:
            argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in argv if a]
        if any(a.endswith("determinism_matrix.py") for a in args) and "--outdir" in args:
            i = args.index("--outdir")
            if i + 1 < len(args) and os.path.normpath(args[i + 1]) == D:
                return int(pid)
    return None

deadline = time.time() + 6 * 3600
while time.time() < deadline:
    pid = find()
    if pid:
        found = datetime.datetime.now()
        since = (found - datetime.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        E = os.path.join(D, "run5-evidence")
        os.makedirs(E, exist_ok=True)
        shutil.copy2(os.path.join(HERE, "capture.py"), os.path.join(E, "capture.py"))
        with open(os.path.join(E, "found.txt"), "w") as fh:
            fh.write(f"matrix pid {pid} found {found:%Y-%m-%d %H:%M:%S}, first read since {since}\n")
        log = open(os.path.join(E, "capture.stderr"), "w")
        p = subprocess.Popen([sys.executable, os.path.join(E, "capture.py"), str(pid), since],
                             cwd=E, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                             start_new_session=True)
        print(f"capture pid {p.pid} for matrix pid {pid}, since {since}", flush=True)
        sys.exit(0)
    time.sleep(2)
print("no run5 matrix process within six hours", flush=True)
sys.exit(2)
