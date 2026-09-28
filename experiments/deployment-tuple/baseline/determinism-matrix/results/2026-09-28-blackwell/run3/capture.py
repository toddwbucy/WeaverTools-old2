"""Read-only: journald's Suppressed lines and, per worker invocation, its line
count and device markers, captured every few minutes so they outlive the
journal's retention. Writes only into this directory."""
import json, subprocess, sys, time, os
OUT = os.path.dirname(os.path.abspath(__file__))
since = sys.argv[1]
while True:
    s = subprocess.run(["journalctl", "-u", "systemd-journald", "--since", since, "-o", "short-iso-precise",
                        "--no-pager", "-q", "-g", "Suppressed"], capture_output=True, text=True).stdout
    with open(os.path.join(OUT, "suppressed.txt"), "a") as fh:
        fh.write(s)
    r = subprocess.run(["journalctl", "-u", "weaver-worker@karl.service", "--since", "-7min", "-o", "json",
                        "--output-fields=_SYSTEMD_INVOCATION_ID,MESSAGE,__REALTIME_TIMESTAMP", "--no-pager", "-q"],
                       capture_output=True, text=True).stdout
    inv = {}
    for line in r.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        i = e.get("_SYSTEMD_INVOCATION_ID")
        m = str(e.get("MESSAGE", ""))
        d = inv.setdefault(i, {"first_us": e.get("__REALTIME_TIMESTAMP"), "lines": 0, "cuda_init": 0, "using_device": 0, "loaded_meta": 0})
        d["lines"] += 1
        d["cuda_init"] += "ggml_cuda_init: found" in m
        d["using_device"] += "using device CUDA" in m
        d["loaded_meta"] += "llama_model_loader: loaded meta data" in m
    with open(os.path.join(OUT, "invocations.jsonl"), "a") as fh:
        for i, d in inv.items():
            fh.write(json.dumps(dict(d, invocation=i, read_at=time.strftime("%H:%M:%S"))) + "\n")
    alive = subprocess.run(["pgrep", "-f", "[d]eterminism_matrix.py --config"], capture_output=True).returncode == 0
    if not alive:
        break
    time.sleep(300)
