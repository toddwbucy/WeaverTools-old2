"""Stage B's one turn through karl2's gate: one JSON line out, one back, printed."""
import json, socket
s = socket.socket(socket.AF_UNIX)
s.settimeout(600)
s.connect("/run/weaver-karl2/gate.sock")
s.sendall(json.dumps({"text": "What is 2 + 2? Answer in one short sentence."}).encode() + b"\n")
print(s.makefile().readline(), end="")
