"""Stage B's diagnostic replay of karl2's run through python-spu.

W4a's driver (handoffs/w4a-evidence/replay.py, 2026-09-24), adapted to b62812e:
the derived declaration is TOML, the SPU is python-spu's zipapp, the stack names
what served, and the determinism environment python-spu needs on CUDA is set.

It stands the worker and a sqlite state member on throwaway sockets, preloads
the source trace through the member's door as the operator principal, enters a
diagnostic binding, and waits for the replay's closing event. The preload door
admits uid 0 alone, so this runs inside `unshare -Ur`, where the operator's own
uid reads as 0, and needs no sudo. Nothing is written but the diagnostic sink, the
declaration it serves (`replay-declaration.toml`) and the logs beside it in the
deposit. The enter records that declaration's sha256, since it is the one that
produced the instruction served.

Usage, after `weaver-analysis derive ... --out <deposit>/derived.toml`:

    unshare -Ur python3 replay.py <source trace> <deposit>/derived.toml <deposit> \
        --bin <b62812e target/release> --spu /opt/weaver/python-spu/python-spu.pyz

It exits 0 only when `replay.closed` reads certified and the teardown is clean: the
leave answered `left`, the worker and the member exited 0 on their own within the grace
after it and the temporary directory is gone. Anything else exits 1, each reason named
on stderr: another closing outcome, a turn stopped before the close, a leave refused or
unanswered, a process that had to be signalled, a process that exited non-zero, a
directory left behind. `--stand-only` exits 1 unless coordination bound and both processes stood.
The stage B run of 2026-09-29 predates this gate, and its record reads certified.
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
import sys
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


class Lines:
    """The records of a file another process is still writing, one poll at a time.

    Only newline-terminated lines are parsed. The unterminated tail is carried to the
    next poll, so a poll that lands mid-write reads the record whole once it is
    finished. A complete line that is not JSON raises, naming its number, since it is
    malformed evidence rather than a record still being written."""

    def __init__(self, path):
        self.path, self.offset, self.tail, self.rows = path, 0, b"", []

    def poll(self):
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            data = fh.read()
        self.offset += len(data)
        *complete, self.tail = (self.tail + data).split(b"\n")
        for line in complete:
            if line.strip():
                try:
                    self.rows.append(json.loads(line))
                except ValueError:
                    raise ValueError(f"{self.path} line {len(self.rows) + 1} is not "
                                     f"JSON: {line[:200]!r}") from None
        return self.rows


PERMISSIONS = ("refeed-permission", "column-permission")
DECODER = "[spu-instruction.decoder]\n"


def effective_declaration(derived, destination):
    """Writes the declaration the replay serves, and answers its sha256 and its parsed
    form, both read from the written file.

    The replay needs the decoder's re-feed and column permissions, which the derived
    declaration does not carry. So the served declaration is the derived text with
    those two keys set under its decoder table. The written file is parsed back and must
    equal the derived declaration with exactly those two keys set, which is what makes a
    text edit safe. A derived declaration that already carries either key, or has no
    decoder table, refuses. The digest the enter records is this file's, so it names
    the declaration that produced the instruction served."""
    text = pathlib.Path(derived).read_text()
    if text.count("\n" + DECODER) != 1:
        raise SystemExit(f"{derived} does not hold one {DECODER.strip()} table")
    expected = tomllib.loads(text)
    decoder = expected["spu-instruction"]["decoder"]
    if any(key in decoder for key in PERMISSIONS):
        raise SystemExit(f"{derived} already sets a permission the replay sets")
    for key in PERMISSIONS:
        decoder[key] = True
    written = text.replace("\n" + DECODER, "\n" + DECODER
                           + "".join(f"{key} = true\n" for key in PERMISSIONS), 1)
    with open(destination, "x") as fh:
        fh.write(written)
    with open(destination, "rb") as fh:
        served = tomllib.load(fh)
    if served != expected:
        raise SystemExit(f"{destination} does not parse to the declaration the replay "
                         f"serves: the derived one with {', '.join(PERMISSIONS)} set")
    return sha256(destination), served


def receive_one(sock, limit=1 << 20):
    """One packet from a SOCK_SEQPACKET socket. A packet longer than `limit` is cut
    silently unless MSG_TRUNC is read, so a cut packet refuses rather than parsing."""
    data, _, flags, _ = sock.recvmsg(limit)
    if flags & socket.MSG_TRUNC:
        raise RuntimeError(f"a coordination answer was longer than {limit} bytes and cut")
    return data


LEFT = {"kind": "answer", "body": {"kind": "left"}}
GRACE = 10  # seconds each process has to exit on its own after a clean leave


def leave_failure(answer):
    """None where the leave was answered `left`, and otherwise what was answered."""
    payload = answer.get("payload") if isinstance(answer, dict) else answer
    if payload == LEFT:
        return None
    return f"the leave was answered {json.dumps(payload)}"


def stop(processes, grace):
    """Waits up to `grace` seconds for every process to exit on its own, then signals
    only those still running, the group first and a kill after ten more seconds.
    Answers the pids it had to signal."""
    deadline = time.monotonic() + grace
    for process in processes:
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    signalled = []
    for process in reversed(processes):
        if process.poll() is not None:
            continue
        signalled.append(process.pid)
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    return signalled


def verdict(result, teardown, stand_only):
    """Every reason the run is not a certified replay torn down cleanly, as lines."""
    failures = []
    if stand_only:
        failures += [f"{name} is false" for name, held in result["standing"].items()
                     if not held]
    else:
        closing = result["closing"]
        if closing["kind"] != "replay.closed":
            failures.append(f"the replay stopped before it closed: {closing['kind']} "
                            f"{json.dumps(closing.get('payload'))}")
        else:
            kind = (closing.get("payload") or {}).get("outcome", {}).get("kind")
            if kind != "certified":
                failures.append(f"the replay closed {kind}, not certified")
        if teardown.get("leave_error") is not None:
            failures.append(f"the leave failed: {teardown['leave_error']}")
        if teardown.get("signalled"):
            failures.append(f"a process did not exit on its own after the leave and was "
                            f"signalled: {teardown['signalled']}")
        if any(code != 0 for code in teardown["codes"]):
            failures.append(f"a process exited non-zero: {teardown['codes']}")
    if not teardown["directory_removed"]:
        failures.append("the temporary directory was left behind")
    return failures


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
    teardown = {}
    result = run(args, teardown)
    failures = verdict(result, teardown, args.stand_only)
    for failure in failures:
        print(f"replay: {failure}", file=sys.stderr, flush=True)
    return 1 if failures else 0


def run(args, teardown):
    """Stands, preloads, enters and waits, filling `teardown` as it tears down, and
    answers what stood or how the replay closed. Judging either is `verdict`'s."""
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
    declaration = args.deposit / "replay-declaration.toml"
    if declaration.exists() and not args.stand_only:
        raise SystemExit(f"{declaration} already exists, and nothing is overwritten")

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
            answer = json.loads(receive_one(c))
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
            standing = {"coordination": coord.exists(),
                        "worker_alive": worker.poll() is None,
                        "member_alive": member.poll() is None}
            print(json.dumps(standing), flush=True)
            return {"standing": standing}

        # The instruction served is the written declaration's, and the digest the
        # enter records is that file's, never the derived file's.
        digest, served = effective_declaration(args.derived, declaration)
        instruction = served["spu-instruction"]
        # The stack as admin's stack_digests keys it, by file name, so the
        # diagnostic record names what served as a serving record does.
        stack = {p.name: sha256(p) for p in (args.bin / "worker", args.bin / "weaver-state",
                                             args.spu, args.bin / "weaver-gate")}
        payload = {"session": served["session"], "run": "stageb-diagnostic-karl2",
                   "spu-instruction": instruction, "binding": {"kind": "diagnostic"},
                   "state-election": {"all-kinds": True, "keys": []},
                   "state-store": {"engine": "sqlite"},
                   "declaration": digest, "stack": stack}

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

        deadline, last, sink_lines = time.monotonic() + 1800, None, Lines(sink)
        while True:
            rows = sink_lines.poll()
            terminal = [x for x in rows if x["kind"] == "replay.closed" or (
                x["kind"] == "turn.closed" and x.get("payload", {}).get("kind") == "stopped")]
            if terminal:
                (E / "replay-terminal.json").write_text(json.dumps(terminal[-1], indent=2) + "\n")
                print(json.dumps(terminal[-1]), flush=True)
                return {"closing": terminal[-1]}
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
        left = False
        if entered:
            try:
                teardown["leave_error"] = leave_failure(exchange({"kind": "leave"}, 1))
            except Exception as error:
                teardown["leave_error"] = str(error)
            left = teardown["leave_error"] is None
            if not left:
                print("leave failed:", teardown["leave_error"], flush=True)
        if wire:
            wire.close()
        # Only after a clean leave is a process expected to exit on its own, so only
        # then is there a grace to wait out. Otherwise each is signalled at once.
        signalled = stop(processes, GRACE if left else 0)
        teardown["signalled"] = signalled if left else []
        for log in logs:
            log.close()
        shutil.rmtree(directory)
        teardown["codes"] = [p.returncode for p in processes]
        teardown["directory_removed"] = not directory.exists()
        (E / "replay-cleanup.json").write_text(json.dumps({
            "temporary_directory_removed": teardown["directory_removed"],
            "process_exit_codes": teardown["codes"],
            "signalled": signalled}) + "\n")


if __name__ == "__main__":
    sys.exit(main())
