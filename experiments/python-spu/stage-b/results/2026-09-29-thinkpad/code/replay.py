"""Stage B's diagnostic replay of karl2's run through python-spu.

W4a's driver (handoffs/w4a-evidence/replay.py, 2026-09-24), adapted to b62812e:
the derived declaration is TOML, the SPU is python-spu's zipapp, the stack names
what served, and the determinism environment python-spu needs on CUDA is set.

It stands the worker and a sqlite state member on throwaway sockets, preloads
the source trace through the member's door as the operator principal, enters a
diagnostic binding, and waits for the replay's closing event. The preload door
admits uid 0 alone, so this runs inside `unshare -Ur`, where the operator's own
uid reads as 0, and needs no sudo. Nothing is written but the diagnostic sink
and the logs beside it in the deposit.

Usage, after `weaver-analysis derive ... --out <deposit>/derived.toml`:

    unshare -Ur python3 replay.py <source trace> <deposit>/derived.toml <deposit> \
        --bin <b62812e target/release> --spu /opt/weaver/python-spu/python-spu.pyz
"""
import argparse
import array
import hashlib
import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import tomllib


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source_trace", type=pathlib.Path)
    parser.add_argument("derived", type=pathlib.Path)
    parser.add_argument("deposit", type=pathlib.Path)
    parser.add_argument("--bin", type=pathlib.Path, required=True)
    parser.add_argument("--spu", type=pathlib.Path, required=True)
    parser.add_argument("--stand-only", action="store_true",
                        help="stand the worker and the member, check both sockets, tear down; "
                             "no enter, so no SPU and no GPU")
    args = parser.parse_args()
    if os.getuid() != 0:
        raise SystemExit("run inside unshare -Ur: the preload door admits uid 0 alone")
    for path in (args.source_trace, args.derived, args.spu, args.bin / "worker",
                 args.bin / "weaver-state", args.bin / "weaver-gate", args.bin / "weaver-analysis"):
        os.stat(path)  # a missing input refuses by name before anything stands

    with open(args.derived, "rb") as fh:
        config = tomllib.load(fh)
    if config.get("binding-kind") != "diagnostic":
        raise SystemExit(f"{args.derived} is not a diagnostic declaration")
    sink = pathlib.Path(config["trace-sink"]["path"])
    if sink.exists() and not args.stand_only:
        raise SystemExit(f"the diagnostic sink {sink} already exists, and nothing is overwritten")

    E = args.deposit
    directory = pathlib.Path(tempfile.mkdtemp(prefix="stageb-replay-"))
    coord, preload = directory / "coord.sock", directory / "preload.sock"
    processes, logs, entered, wire = [], [], False, None
    environment = dict(os.environ, CUBLAS_WORKSPACE_CONFIG=":4096:8")

    def spawn(argv, name, **kw):
        log = (E / name).open("w")
        logs.append(log)
        process = subprocess.Popen([str(a) for a in argv], stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, env=environment, **kw)
        processes.append(process)
        return process

    def exchange(body, ordinal, fds=None):
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as c:
            c.settimeout(600)
            c.connect(str(coord))
            envelope = {"exchange": {"opener": "admin", "ordinal": ordinal}, "position": "open",
                        "payload": {"kind": "directive", "body": body}}
            ancillary = [] if fds is None else [
                (socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))]
            c.sendmsg([json.dumps(envelope).encode()], ancillary)
            answer = json.loads(c.recv(1 << 20))
        with (E / "replay-coordination.ndjson").open("a") as fh:
            fh.write(json.dumps(answer) + "\n")
        return answer

    try:
        worker = spawn([args.bin / "worker", coord, args.spu, args.bin / "weaver-gate"],
                       "replay-worker.log")
        deadline = time.monotonic() + 15
        while not coord.exists():
            if worker.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("the worker did not bind coordination")
            time.sleep(0.02)
        wire, far = socket.socketpair()
        fd = far.fileno()
        spawn([args.bin / "weaver-state", directory, preload], "replay-state.log",
              # 3 is kept too: the child closes every descriptor outside
              # pass_fds after preexec_fn has placed the member's end there.
              pass_fds=tuple({fd, 3}), preexec_fn=lambda: os.dup2(fd, 3))
        far.close()
        if args.stand_only:
            # The member stands its preload door only once the worker's opener
            # arrives, which takes an enter, so this checks what stands before
            # one: coordination bound, and the member alive on descriptor 3,
            # which it probes and refuses by name where no stream socket is.
            time.sleep(2)
            member = processes[-1]
            print(json.dumps({"coordination": coord.exists(),
                              "worker_alive": worker.poll() is None,
                              "member_alive": member.poll() is None}), flush=True)
            return

        instruction = config["spu-instruction"]
        instruction["decoder"]["refeed-permission"] = True
        instruction["decoder"]["column-permission"] = True
        # The stack as admin's stack_digests keys it, by file name, so the
        # diagnostic record names what served as a serving record does.
        stack = {p.name: sha256(p) for p in (args.bin / "worker", args.bin / "weaver-state",
                                             args.spu, args.bin / "weaver-gate")}
        payload = {"session": config["session"], "run": "stageb-diagnostic-karl2",
                   "spu-instruction": instruction, "binding": {"kind": "diagnostic"},
                   "state-election": {"all-kinds": True, "keys": []},
                   "state-store": {"engine": "sqlite"},
                   "declaration": sha256(args.derived), "stack": stack}

        preload_errors, cancel = [], threading.Event()

        def feed():
            try:
                deadline = time.monotonic() + 180
                while not preload.exists():
                    if cancel.is_set():
                        return
                    if time.monotonic() > deadline:
                        raise RuntimeError("the preload door never stood")
                    time.sleep(0.02)
                result = subprocess.run(
                    [str(args.bin / "weaver-analysis"), "preload", str(args.source_trace),
                     str(preload), "--diagnostic", "--as", config["session"]],
                    capture_output=True, text=True, timeout=120)
                (E / "replay-preload.log").write_text(result.stdout + result.stderr)
                if result.returncode:
                    raise RuntimeError("the diagnostic preload was refused")
            except Exception as error:
                preload_errors.append(str(error))

        feeder = threading.Thread(target=feed, daemon=True)
        feeder.start()
        with sink.open("xb") as sink_file:
            answer = exchange({"kind": "enter", "payload": payload}, 0,
                              [sink_file.fileno(), wire.fileno()])
        feeder.join(150)
        if feeder.is_alive() or preload_errors:
            raise RuntimeError(f"preload incomplete: {preload_errors}")
        if answer["payload"] != {"kind": "answer", "body": {"kind": "ready"}}:
            raise RuntimeError(f"the diagnostic enter was refused: {answer}")
        entered = True
        wire.close()
        wire = None

        deadline, last = time.monotonic() + 1800, None
        while True:
            rows = [json.loads(x) for x in sink.read_text().splitlines() if x.strip()]
            terminal = [x for x in rows if x["kind"] == "replay.closed" or (
                x["kind"] == "turn.closed" and x.get("payload", {}).get("kind") == "stopped")]
            if terminal:
                (E / "replay-terminal.json").write_text(json.dumps(terminal[-1], indent=2) + "\n")
                print(json.dumps(terminal[-1]), flush=True)
                break
            progress = (len(rows), rows[-1]["kind"] if rows else None)
            if progress != last:
                print("replay progress:", progress, flush=True)
                last = progress
            if worker.poll() is not None:
                raise RuntimeError("the diagnostic worker exited")
            if time.monotonic() > deadline:
                raise RuntimeError("the replay did not close in 30 minutes")
            time.sleep(0.2)
    finally:
        if "cancel" in locals():
            cancel.set()
        if entered:
            try:
                exchange({"kind": "leave"}, 1)
            except Exception as error:
                print("leave failed:", error, flush=True)
        if wire:
            wire.close()
        for process in reversed(processes):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()
        shutil.rmtree(directory)
        (E / "replay-cleanup.json").write_text(json.dumps({
            "temporary_directory_removed": not directory.exists(),
            "process_exit_codes": [p.returncode for p in processes]}) + "\n")


if __name__ == "__main__":
    main()
