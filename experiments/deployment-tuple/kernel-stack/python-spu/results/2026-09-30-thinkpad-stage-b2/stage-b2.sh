#!/usr/bin/env bash
# Stage B2: karl2, python-spu, one real turn end to end at main dc3a0f7a, on thinkpad.
#
# Run as:   sudo bash stage-b2.sh
#
# What it does, in order, stopping at the first step that fails, with that step's
# evidence in the deposit, and never retrying on its own:
#   0. checks the staged build, the prefix, the card and karl, and takes the before
#      half of the evidence that nothing else changes;
#   1. installs the dc3a0f7a worker, weaver-admin and weaver-gate into
#      /opt/weaver-stageb/bin, keeping the b62812e set beside them as <name>.b62812e,
#      and the dc3a0f7a zipapp as /opt/weaver/python-spu/python-spu.pyz, keeping
#      850720e's beside it as python-spu.pyz.850720e;
#   2. edits /etc/weaver/admin-stageb, after a backup: headroom-bytes 268435456, and
#      unit-properties without CUBLAS_WORKSPACE_CONFIG;
#   3. loads karl2, runs one turn, lists the SPU's code mappings from outside, reads
#      its command line and environment, and unloads;
#   4. runs the diagnostic replay of that turn, as the operator's account;
#   5. takes the after half of the evidence and compares it.
#
# It touches nothing of karl's, nothing under /etc/weaver/admin, /opt/weaver/bin or
# /opt/weaver/lib, and nothing of olympus's. Every file it writes in the deposit is
# written as the operator's account, since root may be squashed on the share. After
# a run, the new binaries, the new zipapp and the edited admin-stageb stay in place,
# the old files beside them for a rollback.

# Published copy: OPERATOR, WORKSPACE and AGENTS_DIR stand for one box's operator
# account, checkout directory and agent-configuration directory, which the deposit's
# copy carries.
set -Eeuo pipefail
umask 022
[ "$(id -u)" = 0 ] || { echo "run as root: sudo bash $0" >&2; exit 2; }

OP=$OPERATOR
D=/mnt/bulk-store/weaver-testing/stage-b2-thinkpad-2026-09-30-dc3a0f7
R=$D/run
WT=$WORKSPACE/stageb2-read
T=$WT/target/release
CODE=$WT/experiments/deployment-tuple/kernel-stack/python-spu/code
SRC=$WT/python-spu/src
CFG=/etc/weaver/admin-stageb
BIN=/opt/weaver-stageb/bin
PREFIX=/opt/weaver/python-spu
PYZ=$PREFIX/python-spu.pyz
AGENTS=$AGENTS_DIR
TRACE=$AGENTS/karl2/trace.ndjson
COMMIT=dc3a0f7a9b11666ed59d69363d6741869e5fabaa
OLD_PYZ_SHA=8197449fbe343760a7d16b57102ec21ba6b80cc218f3c485aec0717a85d4d0f9
PREFIX_DIGEST=1dce454a7e7f64715fe1a7ff367bd0e707dfb5f7544a9d4c19cb2a61938c145e
WEIGHTS_HASH=be1a0490e227007cb75fbc4b7a44f2a5acb2469baa25ba1a5c766ff051174019
HEADROOM=268435456
UNIT=weaver-worker@karl2.service
ADMIN=(env WEAVER_ADMIN_CONFIG=$CFG $BIN/weaver-admin)

STEP=start
JPID=
JOURNAL=
LOADED=no

as_op() { runuser -u "$OP" -- "$@"; }
put() { as_op tee "$R/$1" >/dev/null; }          # stdin to a deposit file, as the operator
log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | as_op tee -a "$R/steps.log"; }
step() { STEP=$1; log "== $1"; }
check() { local what=$1; shift; if "$@"; then log "   ok: $what"; else log "   FAILED: $what"; return 1; fi; }
card_procs() { nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c . || true; }
stop_follower() {
    if [ -n "$JPID" ]; then kill "$JPID" 2>/dev/null || true; wait "$JPID" 2>/dev/null || true; JPID=; fi
}

on_error() {
    local line=$1
    trap - ERR
    log "!! STOPPED at step '$STEP' (script line $line). Nothing is retried."
    stop_follower
    if [ -n "$JOURNAL" ]; then put worker-journal.txt < "$JOURNAL" || true; rm -f "$JOURNAL"; fi
    # Cleanup, not a retry: a karl2 left loaded would hold the card overnight.
    if [ "$LOADED" = yes ]; then
        log "   karl2 was loaded, so it is unloaded once:"
        "${ADMIN[@]}" unload karl2 2>&1 | put unload-after-failure.txt || true
    fi
    nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>&1 | put nvidia-smi-at-failure.txt || true
    exit 1
}
trap 'on_error $LINENO' ERR

as_op mkdir -p "$R"
[ ! -e "$R/steps.log" ] || { echo "$R/steps.log exists: this deposit has a run in it already, and nothing is overwritten" >&2; exit 2; }
log "stage B2 at $COMMIT, run by $(logname 2>/dev/null || echo root) on $(hostname)"

# ---------------------------------------------------------------- 0. before anything
step "0. the staged build, the prefix, the card and karl"
check "the worktree is at $COMMIT and clean" \
    test "$(as_op git -C "$WT" rev-parse HEAD)" = "$COMMIT" -a -z "$(as_op git -C "$WT" status --porcelain)"
check "the built binaries are the recorded ones" \
    bash -c "cd '$T' && sha256sum -c --quiet '$D/build/binaries.sha256'"
check "the staged zipapp is the recorded one" \
    bash -c "cd '$D/build' && sha256sum -c --quiet python-spu.pyz.sha256"
as_op "$PREFIX/bin/python3.14" -I -B "$WT/python-spu/scripts/installed_set.py" "$WT/python-spu/requirements.lock" 2>&1 | put installed-set.txt
log "   ok: the prefix holds the lock and nothing more"
as_op python3 -B "$WT/python-spu/scripts/tree_digest.py" "$PREFIX" | put tree-digest-before.txt
check "the prefix's tree digest is stage B's" test "$(cut -d' ' -f1 "$R/tree-digest-before.txt")" = "$PREFIX_DIGEST"
check "the card is empty" test "$(card_procs)" = 0
check "karl is not loaded" bash -c '! systemctl is-active --quiet weaver-worker@karl.service'
check "karl2 is not loaded" bash -c "! systemctl is-active --quiet $UNIT"

date '+%F %T %Z' | put capture-before-time.txt
{ systemctl is-active weaver-worker@karl.service || true; ls /run/weaver-karl 2>&1 || true; } | put karl-before.txt
{ sha256sum /etc/weaver/admin/* /opt/weaver/bin/* /opt/weaver/lib/* "$AGENTS/karl.yaml"
  stat -c '%s %Y %n' "$AGENTS/karl/trace.ndjson"; } 2>&1 | put untouched-before.sha256
sha256sum /var/log/weaver/admin-operations.ndjson | put admin-log-before.sha256
{ nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total --format=csv,noheader
  uname -r; } | put box.txt

# ---------------------------------------------------------------- 1. install
step "1. install the dc3a0f7a binaries and zipapp, the old ones kept beside"
for name in worker weaver-admin weaver-gate; do
    if [ ! -e "$BIN/$name.b62812e" ]; then
        want=$(awk -v n="$name" '$2 == n {print $1}' "$D/build/binaries-b62812e.sha256")
        check "$BIN/$name is the b62812e build before it moves aside" \
            test "$(sha256sum "$BIN/$name" | cut -d' ' -f1)" = "$want"
        mv "$BIN/$name" "$BIN/$name.b62812e"
    fi
    install -o root -g root -m 0755 "$T/$name" "$BIN/$name"
done
if [ ! -e "$PYZ.850720e" ]; then
    check "the installed zipapp is 850720e's before it moves aside" \
        test "$(sha256sum "$PYZ" | cut -d' ' -f1)" = "$OLD_PYZ_SHA"
    mv "$PYZ" "$PYZ.850720e"
fi
install -o root -g root -m 0755 "$D/build/python-spu.pyz" "$PYZ"
sha256sum "$BIN"/* "$PYZ" "$PYZ.850720e" | put installed.sha256
check "the installed binaries are the built ones" \
    bash -c "cd '$T' && for n in worker weaver-admin weaver-gate; do cmp -s \$n '$BIN'/\$n || exit 1; done"
check "the installed zipapp is the built one" cmp -s "$D/build/python-spu.pyz" "$PYZ"

# ---------------------------------------------------------------- 2. admin-stageb
step "2. admin-stageb: headroom-bytes, and no CUBLAS_WORKSPACE_CONFIG"
BACKUP=/etc/weaver/admin-stageb.bak-b62812e
[ -e "$BACKUP" ] || cp -a "$CFG" "$BACKUP"
cat "$BACKUP"/unit-properties | put unit-properties-before.txt
printf '%s\n' "$HEADROOM" > "$CFG/headroom-bytes"
grep -v '^Environment=CUBLAS_WORKSPACE_CONFIG=' "$BACKUP/unit-properties" > "$CFG/unit-properties"
for f in "$CFG"/*; do printf '%s: %s\n' "$(basename "$f")" "$(tr '\n' '|' < "$f")"; done | put admin-stageb-after.txt
check "headroom-bytes reads $HEADROOM" test "$(cat "$CFG/headroom-bytes")" = "$HEADROOM"
check "unit-properties carries no CUBLAS_WORKSPACE_CONFIG" bash -c "! grep -q CUBLAS_WORKSPACE_CONFIG '$CFG/unit-properties'"
check "unit-properties keeps UMask" grep -qx 'UMask=0000' "$CFG/unit-properties"
"${ADMIN[@]}" validate karl2 2>&1 | put validate.txt
log "   ok: admin validates karl2 under the edited admin-stageb: $(tr '\n' ' ' < "$R/validate.txt")"

# ---------------------------------------------------------------- 3. load, turn, unload
step "3. load karl2, one turn, the SPU read from outside, unload"
if systemctl is-failed --quiet "$UNIT"; then systemctl reset-failed "$UNIT"; log "   reset a failed $UNIT"; fi
check "karl2's unit is not active" bash -c "! systemctl is-active --quiet $UNIT"
check "the card is empty" test "$(card_procs)" = 0
JOURNAL=$(mktemp /run/stage-b2-journal.XXXXXX)
journalctl -u "$UNIT" -f -n 0 -o short-iso-precise > "$JOURNAL" 2>&1 &
JPID=$!
sleep 1
BEFORE=$(wc -l < "$TRACE")
echo "$BEFORE" | put trace-lines-before.txt
LOADED=yes
"${ADMIN[@]}" load karl2 2>&1 | put load.txt
check "the load answered idle" \
    python3 -c "
import json, sys
def answer(line):
    try: return json.loads(line)
    except ValueError: return {}
sys.exit(not any(answer(l).get('state') == 'idle' for l in open('$R/load.txt')))"
"${ADMIN[@]}" show karl2 2>&1 | put show.txt
sudo -u "$OP" -g weaver-karl2 python3 "$CODE/turn.py" | put turn.txt
log "   ok: the turn answered: $(cat "$R/turn.txt")"

P=$(pgrep -u weaver-karl2 -f "^$PREFIX/bin/python3.14 " || true)
echo "$P" | put spu-pid.txt
check "exactly one SPU process is selected" test "$(echo "$P" | wc -w)" = 1
tr '\0' ' ' < "/proc/$P/cmdline" | put spu-cmdline.txt
tr '\0' '\n' < "/proc/$P/environ" | put spu-environ.txt
awk '$2 ~ /x/ && $6 ~ /^\//' "/proc/$P/maps" | put maps-code.txt
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv | put nvidia-smi-loaded.txt
systemctl show -p Environment "$UNIT" | put unit-environment.txt
check "the SPU's command line names the zipapp" grep -qF "$PYZ" "$R/spu-cmdline.txt"
check "the SPU's command line carries --headroom-bytes $HEADROOM" grep -qF -- "--headroom-bytes $HEADROOM" "$R/spu-cmdline.txt"
check "the SPU started with no CUBLAS_WORKSPACE_CONFIG" bash -c "! grep -q '^CUBLAS_WORKSPACE_CONFIG=' '$R/spu-environ.txt'"
check "the unit's environment has no CUBLAS_WORKSPACE_CONFIG" bash -c "! grep -q CUBLAS_WORKSPACE_CONFIG '$R/unit-environment.txt'"
check "the code listing is not empty" test -s "$R/maps-code.txt"
as_op python3 -B - "$SRC" "$R/maps-code.txt" "$PREFIX" <<'EOF' | put maps-judged.json
import json, sys
sys.path.insert(0, sys.argv[1])
from python_spu.loaded_code import foreign
listing = open(sys.argv[2]).read()
print(json.dumps({"objects": len(listing.splitlines()), "foreign": foreign(listing, (sys.argv[3],))}))
EOF
check "every mapped code object is admitted by python-spu's own rule" \
    python3 -c "import json,sys; sys.exit(json.load(open('$R/maps-judged.json'))['foreign'] != [])"

"${ADMIN[@]}" unload karl2 2>&1 | put unload.txt
LOADED=no
for _ in 1 2 3 4 5 6 7 8 9 10; do [ "$(card_procs)" = 0 ] && break; sleep 1; done
nvidia-smi --query-compute-apps=pid --format=csv,noheader | put nvidia-smi-after-unload.txt
check "the card is empty after the unload" test "$(card_procs)" = 0
check "karl2's unit is inactive" bash -c "! systemctl is-active --quiet $UNIT"
tail -n 3 /var/log/weaver/admin-operations-stageb.ndjson | put admin-stageb-log-tail.txt
sleep 1
stop_follower
put worker-journal.txt < "$JOURNAL"
rm -f "$JOURNAL"
check "the journal shows the worker started with --headroom-bytes $HEADROOM" \
    grep -qF -- "--headroom-bytes $HEADROOM" "$R/worker-journal.txt"
check "the journal carries no violation, fault or refusal line" \
    bash -c "! grep -qE 'loaded_code_violation|import_violation|python_spu_fault|bad_environment|bad_parameter|admission_refused' '$R/worker-journal.txt'"

# The run's own lines of karl2's trace, and what they record.
tail -n +"$((BEFORE + 1))" "$TRACE" | put karl2-trace-run.ndjson
cat "$TRACE" | put karl2-trace-full.ndjson
as_op python3 -B - "$R/karl2-trace-run.ndjson" "$PYZ" "$BIN" "$WEIGHTS_HASH" <<'EOF' | put trace-judged.json
import hashlib, json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
load = [r for r in rows if r["kind"] == "load"]
measurement = [r for r in rows if r["kind"] == "model.measurement"]
stack = load[0]["payload"]["stack"] if load else {}
print(json.dumps({
    "runs": sorted({r["run"] for r in rows}),
    "kinds": [r["kind"] for r in rows],
    "stack": stack,
    "stack_is_installed": stack == {"python-spu.pyz": sha(sys.argv[2]),
                                    "worker": sha(sys.argv[3] + "/worker"),
                                    "weaver-gate": sha(sys.argv[3] + "/weaver-gate")},
    "weights_hash": [m["payload"].get("weights_hash") for m in measurement],
    "weights_hash_is_expected": [m["payload"].get("weights_hash") for m in measurement] == [sys.argv[4]],
}, indent=2))
EOF
check "the new lines are one run" python3 -c "import json,sys; sys.exit(len(json.load(open('$R/trace-judged.json'))['runs']) != 1)"
check "the load event's stack is the installed dc3a0f7a zipapp, worker and gate" \
    python3 -c "import json,sys; sys.exit(not json.load(open('$R/trace-judged.json'))['stack_is_installed'])"
check "the turn's measurement carries the expected weights hash" \
    python3 -c "import json,sys; sys.exit(not json.load(open('$R/trace-judged.json'))['weights_hash_is_expected'])"

# ---------------------------------------------------------------- 4. replay
step "4. the diagnostic replay, as the operator's account"
as_op "$T/weaver-analysis" derive "$R/karl2-trace-run.ndjson" --as s-karl2-1-replay --devices 0 \
    --sink "$R/replay-trace.ndjson" --surprisal --out "$R/derived.toml" 2>&1 | put derive.out
as_op unshare -Ur python3 "$CODE/replay.py" "$R/karl2-trace-run.ndjson" "$R/derived.toml" "$R" \
    --bin "$T" --spu "$PYZ" 2>&1 | put replay-driver.log
log "   ok: replay.py exited 0, which it does only for certified and a clean teardown"
check "replay.closed reads certified" \
    python3 -c "import json,sys; sys.exit(json.load(open('$R/replay-terminal.json'))['payload']['outcome']['kind'] != 'certified')"
for _ in 1 2 3 4 5 6 7 8 9 10; do [ "$(card_procs)" = 0 ] && break; sleep 1; done
check "the card is empty after the replay" test "$(card_procs)" = 0

# ---------------------------------------------------------------- 5. after
step "5. the after half of the evidence"
date '+%F %T %Z' | put capture-after-time.txt
{ systemctl is-active weaver-worker@karl.service || true; ls /run/weaver-karl 2>&1 || true; } | put karl-after.txt
{ sha256sum /etc/weaver/admin/* /opt/weaver/bin/* /opt/weaver/lib/* "$AGENTS/karl.yaml"
  stat -c '%s %Y %n' "$AGENTS/karl/trace.ndjson"; } 2>&1 | put untouched-after.sha256
sha256sum /var/log/weaver/admin-operations.ndjson | put admin-log-after.sha256
check "karl's state is unchanged" cmp -s "$R/karl-before.txt" "$R/karl-after.txt"
check "admin's, the stack's and karl's files are unchanged" cmp -s "$R/untouched-before.sha256" "$R/untouched-after.sha256"
check "admin's own log is unchanged" cmp -s "$R/admin-log-before.sha256" "$R/admin-log-after.sha256"
as_op python3 -B "$WT/python-spu/scripts/tree_digest.py" "$PREFIX" | put tree-digest-after.txt

trap - ERR
log "== DONE: every step passed"
