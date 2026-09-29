"""Stage B's one turn through karl2's gate: one JSON line out, one back, printed.

It exits 0 only when the reply is a newline-terminated `answered` line carrying text.
A closed connection, a line cut before its newline, a line that is not JSON, or any
other kind exits 1, naming what came back.
The stage B run of 2026-09-29 predates this gate, and its reply was `answered`."""
import json, socket, sys
s = socket.socket(socket.AF_UNIX)
s.settimeout(600)
s.connect("/run/weaver-karl2/gate.sock")
s.sendall(json.dumps({"text": "What is 2 + 2? Answer in one short sentence."}).encode() + b"\n")
line = s.makefile().readline()
print(line, end="")
if not line.endswith("\n"):
    sys.exit(f"turn: the gate's reply was cut before its newline: {line!r}")
try:
    reply = json.loads(line)
except ValueError:
    sys.exit(f"turn: the gate's reply is not a JSON line: {line!r}")
if not isinstance(reply, dict) or reply.get("kind") != "answered" or not reply.get("text"):
    sys.exit(f"turn: the gate did not answer: {line.strip()!r}")
