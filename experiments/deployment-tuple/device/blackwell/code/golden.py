# conforms: blackwell-probe-stubs-are-captures
"""Ground-truth samples the test doubles in test_tb.py are built from.

Each constant was captured from the real tool on this box, unprivileged, or
copied from a real trace, and carries its provenance beside it: the command
or file, the sha256 of the raw bytes, and any normalization. A double built
from its own code's assumption instead of from the tool is how #683 finding
13 reached the device: derive quotes the artifact and the fake did not.
Nothing here ran privileged, loaded a model or touched the device.
"""

# nvidia-smi on this box, 2026-09-25, as tb_payload.load() invokes it:
#   /usr/bin/nvidia-smi --query-gpu=index,name,driver_version --format=csv,noheader
# raw sha256 3b616b116b66d3b0c42f6bca29b446c3419f1bb57b8ba6fecebafb52a77dad98; verbatim.
NVIDIA_SMI = '0, NVIDIA RTX PRO 5000 Blackwell Generation Laptop GPU, 615.71.09\n'

# systemctl on this box, 2026-09-25, as tb_payload.m1_unloaded() invokes it:
#   /usr/bin/systemctl show weaver-worker@m1.service --property=ActiveState --property=LoadState
# raw sha256 0346f0ff3043eecac3e566c78a7798a6369c1053b7e673ad4f0e86c7889dc435; verbatim. systemctl prints the
# properties in its own order whatever the argument order (the reverse-order
# capture had the same sha256).
SYSTEMCTL_SHOW_M1 = 'LoadState=not-found\nActiveState=inactive\n'

# ldd of B1's engine library from the preserved Olympus stack (weaver-probe
# deposit, B1 = e69916a), unprivileged:
#   LD_LIBRARY_PATH=$DEPOSIT/stacks/B1/engine-lib /usr/bin/ldd $DEPOSIT/stacks/B1/engine-lib/libggml-cuda.so
# raw sha256 b8fab4b0eab58552117bbd21095b2d9ed90761ef98a7450021222d3e233626d0; the deposit path is replaced
# by {DEPOSIT}. B1 has no cuda-lib yet, so the CUDA libraries resolve to the
# host toolkit: a real negative for the cuda-local guard. The format (tab,
# soname.13, " => ", path, load address) is what a positive case reuses.
LDD_B1_LIBGGML_CUDA = '\tlinux-vdso.so.1 (0x00007f4c637f1000)\n\tlibggml-base.so.0 => {DEPOSIT}/stacks/B1/engine-lib/libggml-base.so.0 (0x00007f4c5af37000)\n\tlibcudart.so.13 => /opt/cuda/lib64/libcudart.so.13 (0x00007f4c5ac00000)\n\tlibcublas.so.13 => /opt/cuda/lib64/libcublas.so.13 (0x00007f4c57200000)\n\tlibcuda.so.1 => /usr/lib/libcuda.so.1 (0x00007f4c50600000)\n\tlibcublasLt.so.13 => /opt/cuda/lib64/libcublasLt.so.13 (0x00007f4c28e00000)\n\tlibstdc++.so.6 => /usr/lib/libstdc++.so.6 (0x00007f4c28a00000)\n\tlibm.so.6 => /usr/lib/libm.so.6 (0x00007f4c504f8000)\n\tlibgcc_s.so.1 => /usr/lib/libgcc_s.so.1 (0x00007f4c5af01000)\n\tlibc.so.6 => /usr/lib/libc.so.6 (0x00007f4c28600000)\n\tlibdl.so.2 => /usr/lib/libdl.so.2 (0x00007f4c637b2000)\n\tlibpthread.so.0 => /usr/lib/libpthread.so.0 (0x00007f4c637ab000)\n\tlibrt.so.1 => /usr/lib/librt.so.1 (0x00007f4c637a6000)\n\t/usr/lib64/ld-linux-x86-64.so.2 (0x00007f4c637f3000)\n'

# B1's own weaver-analysis (sha256 99e7cfbf...2fae), unprivileged, on the W4a
# reconstruction source (handoffs/w4a-evidence/reconstruction-source-closed.ndjson,
# sha256 23e683aa...ee97), with the payload's flags:
#   weaver-analysis derive <trace> --devices 0 --sink <sink> --field-depth 200 --surprisal --out <yaml>
# raw sha256 09f4df0bd70d8c2ed271e9767465b2526ab17f744944f6316b85e3bba5b7707b; the sink path is replaced by
# {SINK}. The artifact is a JSON string (declare.rs at e69916a, 183-185).
DERIVE_DECLARATION = 'session: "m1-002"\nbinding-kind: diagnostic\nspu-instruction:\n  decoder:\n    model-binding:\n      artifact: "/opt/weaver/models/qwen2.5-0.5b-instruct-q6_k.gguf"\n      devices: [0]\n    residual-readout-election: false\n    field-election:\n      depth: 200\n    surprisal-election: true\n    identity: [{"role":"system","content":[{"type":"text","text":"You are a careful assistant. Answer from what you know, say\\nplainly when you do not know, and keep answers as short as the\\nquestion allows.\\n"}]}]\n    tunable-values:\n      seed: 451234785645\n      context-capacity: 32768\n      max-tokens-per-turn: 4096\ntool-set: []\npermission-mode: ask\ntrace-sink:\n  kind: file\n  path: "{SINK}"\n  create: true\n'
DERIVE_ARTIFACT = '/opt/weaver/models/qwen2.5-0.5b-instruct-q6_k.gguf'

# The same binary on the four-run W4a trace (trace-closed.ndjson, sha256
# a8417f90...0c5d) refuses, exit 1, writing no declaration: the premise of
# #683 finding 10. After tb_payload.select_run() cut one run from that trace,
# the same derive exited 0 with a declaration identical to DERIVE_DECLARATION
# apart from the sink path.
DERIVE_MULTIRUN_REFUSAL = ''

# Real trace events, one per kind the tooling consumes, verbatim lines from the
# W4a diagnostic replay (handoffs/w4a-evidence/diagnostic-m1-002.ndjson,
# sha256 0827d862...fdb7), written by the stack W4a ran: the envelope is
# flattened, so session, run, turn, sequence, kind, subsystem, wall_ms and
# monotonic_ns are top-level, sequence and monotonic_ns as strings.
# turn.started: line 3.
TURN_STARTED = '{"session":"w4a-replay-m1-002","run":"w4a-diagnostic-m1-002","turn":"t-1","sequence":"2","kind":"turn.started","subsystem":"harness","wall_ms":1790296337438,"monotonic_ns":"742257429"}'
# model.measurement: line 6.
MODEL_MEASUREMENT = '{"session":"w4a-replay-m1-002","run":"w4a-diagnostic-m1-002","turn":"t-1","sequence":"5","kind":"model.measurement","subsystem":"spu_decoder","wall_ms":1790296337468,"monotonic_ns":"772651931","payload":{"blocks":[{"end":399,"label":"turn-delta","start":0}],"entropies":[0.3382319509983063,0.006305493414402008,0.0065399715676903725,0.0808117687702179],"input_tokens":[151644,8948,198,2610,525,264,16585,17847,13,21806,504,1128,498,1414,11,1977,64295,979,498,653,537,1414,11,323,2506,11253,438,2805,438,279,3405,6147,13,151645,198,151644,872,198,5501,14060,1493,13064,369,419,10435,25,279,2390,829,374,42540,95233,26,279,34679,1372,374,220,22,18,16,26,279,11457,7987,525,94607,11,67605,11,79736,13,17841,1172,25,44983,3949,13,151645,198,151644,77091,198],"model":"/opt/weaver/models/qwen2.5-0.5b-instruct-q6_k.gguf","output_tokens":[37,11359,3949,13],"perplexity":1.0104428164959163,"surprisals":[0.045071717351675034,0.0005667434888891876,0.0005064000142738223,0.013805852271616459],"timings":{"decode_ns":"26542347","prefill_ns":"3060338"},"weights_hash":"ae0c67f9cd2fc774b49d082821218587776df3e708eb41f9565334826ed14402"}}'
# turn.closed: line 8.
TURN_CLOSED = '{"session":"w4a-replay-m1-002","run":"w4a-diagnostic-m1-002","turn":"t-1","sequence":"7","kind":"turn.closed","subsystem":"harness","wall_ms":1790296337468,"monotonic_ns":"772675299","payload":{"close":"clean"}}'
# replay.closed: line 225.
REPLAY_CLOSED = '{"session":"w4a-replay-m1-002","run":"w4a-diagnostic-m1-002","sequence":"224","kind":"replay.closed","subsystem":"harness","wall_ms":1790296339389,"monotonic_ns":"2693365790","payload":{"outcome":{"kind":"diverged","divergence":{"kind":"token_path","position":27196,"recorded":1513,"recomputed":1079}}}}'

# A certified replay close, verbatim: line 15 of the analysis crate's own
# fixture at e69916a (crates/weaver-analysis/tests/fixtures/diagnostic-certified.ndjson,
# sha256 4611fdc8...126f). replay.* kinds are weaver-diagnostic's
# (crates/weaver-diagnostic/src/event.rs:57-93); the outcome is tagged on kind,
# one of certified, diverged, abandoned (:143-149), and the close has no turn.
REPLAY_CLOSED_CERTIFIED = '{"session":"s-karl-1","run":"2026-09-01T01:29:13.421Z-karl-098198ee15c3580f","sequence":"14","kind":"replay.closed","subsystem":"harness","wall_ms":1788226164286,"monotonic_ns":"10864473103","payload":{"outcome":{"kind":"certified"}}}'

# weaver-admin prints exactly one compact JSON line per invocation, the answer
# with exit 0 or the refusal with exit 1 (crates/weaver-admin/src/main.rs:101-108;
# surface.rs:18, 71-80, at e69916a). The answer is LifecycleAnswer, tagged on
# kind (crates/weaver-types/src/wire.rs:246-296); state is one of absent,
# unloaded, idle, active (:451-462). load answers idle (main.rs:566-569),
# unload answers unloaded (:945-952), and unload with no residency refuses
# (:888-902). Derived from source: a capture needs the admin and its socket.
ADMIN_STATE = '{{"kind":"state","state":"{}"}}'
ADMIN_NO_RESIDENCY = '{"kind":"no_residency"}'

# The gate relays the harness's close line unchanged (weaver-gate relay.rs:237-273
# at e69916a); the harness renders it as a JSON map, keys alphabetical
# (weaver-harness lifecycle.rs:110-140, 915-921), pinned whole at :4118-4121.
# The instrument's gate_turn returns json.loads of that line
# (confirm_cells.py:610-617, sha256 d17475de...b602). Derived from source.
GATE_ANSWERED = '{"kind":"answered","run":"r-1","text":"one word","turn":"t-1"}'
GATE_REFUSED = '{"kind":"refused","reason":"the line is not a request"}'

# The instrument's extract_run(events) returns exactly these keys
# (weaver-probe/weaver_probe.py:174-200, sha256 92d9a400...5130); input_tokens
# is a count (:192), field maps int positions to {ranked, realized} from
# model.field events. Derived from source.
EXTRACT_RUN_KEYS = ('emission', 'output_tokens', 'entropies', 'surprisals', 'field', 'finish',
                    'declared_seed', 'generation_seed', 'timings', 'weights_hash', 'model', 'input_tokens')

# A model.field event, derived from source: no W4a trace carries one (the field
# election was off there), so the envelope is MODEL_MEASUREMENT's with the kind
# and the next sequence, and the payload is the shape weaver-trace renders at
# e69916a (crates/weaver-trace/src/event.rs:370-383): position as a number,
# ranked as [{token, probability}], realized as the token drawn. One such
# event per output position is what a run's field is; a second for the same
# position is what extract_run would silently overwrite.
MODEL_FIELD = '{"session":"w4a-replay-m1-002","run":"w4a-diagnostic-m1-002","turn":"t-1","sequence":"6","kind":"model.field","subsystem":"spu_decoder","wall_ms":1790296337468,"monotonic_ns":"772651931","payload":{"position":0,"ranked":[{"token":9707,"probability":0.5},{"token":11,"probability":0.25}],"realized":9707}}'

# model.request and model.output, verbatim lines from the same W4a diagnostic
# replay (lines 4 and 5), the two other singular kinds the
# pinned extractor reads per run.
MODEL_REQUEST = '{"session":"w4a-replay-m1-002","run":"w4a-diagnostic-m1-002","turn":"t-1","sequence":"3","kind":"model.request","subsystem":"spu_decoder","wall_ms":1790296337468,"monotonic_ns":"772630948","payload":{"rendered":"<|im_start|>system\\nYou are a careful assistant. Answer from what you know, say plainly when you do not know, and keep answers as short as the question allows.<|im_end|>\\n<|im_start|>user\\nPlease retain these facts for this conversation: the project name is Copper Finch; the locker number is 731; the ordered colors are teal, amber, violet. Reply only: Facts received.<|im_end|>\\n<|im_start|>assistant\\n","sampling":{"generation_seed":14458752852352082704,"repetition_penalty":1.100000023841858,"repetition_window":64,"seed":451234785645,"temperature":0.699999988079071,"top_k":40,"top_p":0.949999988079071},"stop":{"max_tokens":4096,"stop_tokens":[151645],"terminator":151645},"template":"<|im_start|>{role}\\n{message}<|im_end|>\\n"}}'
MODEL_OUTPUT = '{"session":"w4a-replay-m1-002","run":"w4a-diagnostic-m1-002","turn":"t-1","sequence":"4","kind":"model.output","subsystem":"spu_decoder","wall_ms":1790296337468,"monotonic_ns":"772648352","payload":{"emission":"Facts received.","finish":"completed","resident":126,"capacity":32768}}'

# Which event kind each extract_run key is read from, per
# weaver-probe/weaver_probe.py:174-200 (sha256 92d9a400...5130): the pinned
# extractor keeps the LAST event of each kind for a run, and the last field
# event per position, so a run's selected events must carry exactly one of
# each singular kind, and one field event per output position, before
# anything is extracted. The driver's SINGULAR_KINDS is pinned to this.
EXTRACT_RUN_SOURCES = {
    'model.request': ('declared_seed', 'generation_seed'),
    'model.output': ('emission', 'finish'),
    'model.measurement': ('output_tokens', 'input_tokens', 'entropies', 'surprisals', 'timings', 'weights_hash', 'model'),
    'model.field': ('field',),
}
