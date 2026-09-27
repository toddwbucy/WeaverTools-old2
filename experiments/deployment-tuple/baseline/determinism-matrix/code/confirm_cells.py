#!/usr/bin/env python3
"""Cross-precision / cross-architecture reproducibility cells.

For each cell (one artifact at one precision): load the agent on that
artifact, serve one short and one longer turn at the gate socket,
unload fully, reload, read the request texts back from the record's
own message.user events, reissue them byte-exact in order, and compare
the two runs field by field. Stdlib only, so any box with the runtime
can run it unchanged.

The pinning discipline is the point: same commit, same declaration
apart from the artifact path, same declared seed, same turn texts. A
box needing its own build records that build as an arm, not a
nuisance.

Usage:  confirm_cells.py --config <box>.json [--outdir DIR]

Config (JSON):
{
  "box":          "thinkpad",
  "agent":        "karl",
  "declaration":  "/home/todd/.weaveragents/karl.yaml",
  "gate_socket":  "/run/weaver-karl/gate.sock",
  "trace":        "/home/todd/.weaveragents/karl/trace.ndjson",
  "admin_bin":    "/opt/weaver/bin/weaver-admin",
  "admin_config": "/etc/weaver/admin",
  "repo":         "/home/todd/Projects/WeaverTools_Project/WeaverTools",
  "spu_bin":      "optional; overrides the spu-binary named in admin_config",
  "build_flags":  "cargo build --release --workspace --features weaver-spu/cuda",
  "loop_sha256":  "optional; the sha256 of the loop file the box composes with",
  "cells": [
    {"name": "q8",   "precision": "q8_0", "artifact": "/opt/weaver/models/qwen2.5-0.5b-instruct-q8_0.gguf"},
    {"name": "bf16", "precision": "bf16", "artifact": "/opt/weaver/models/qwen2.5-0.5b-instruct-bf16.gguf"}
  ]
}
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

# Pinned across every box and every cell. Do not edit per box.
SHORT_TEXT = "Introduce yourself in exactly one short sentence."
LONG_TEXT = (
    "Write a detailed step-by-step explanation of how a binary search "
    "works, then implement it in Python with comments, then walk "
    "through an example run on a list of twenty numbers."
)

CHECKS = [
    ("rendered prompt", "model.request", "/rendered"),
    ("derived generation seed", "model.request", "/sampling/generation_seed"),
    ("effective sampling knobs", "model.request", "/sampling"),
    ("emission bytes", "model.output", "/emission"),
    ("finish kind", "model.output", "/finish"),
    ("resident count", "model.output", "/resident"),
    ("input token ids", "model.measurement", "/input_tokens"),
    ("per-token entropies", "model.measurement", "/entropies"),
]


def sh(args, **kw):
    """Run a command and always come back with a result.

    **A metadata reader must not be the reason a run does not happen.**
    `subprocess.run` raises when the binary is absent or `cwd` does not
    exist, and the provenance readers below call it for `rustup`, `ldd`, and
    `git` - none of which a box is obliged to carry. Raising there aborts a
    seven-hour matrix before its first session, or dies in the confirm
    driver ahead of the `try` that restores the declaration, leaving a
    `.pre-cells` backup behind. That is the rule `device_bindings` and
    `engine_libraries` already state, applied to the primitive they share:
    these facts exist to make a deposit worth trusting, so none may be the
    reason there is no deposit.

    An absent command comes back as exit 127 with the reason on stderr, the
    shell's own convention, so a caller reads a failure rather than catching
    one and the account still says which failure it was.
    """
    try:
        return subprocess.run(args, capture_output=True, text=True, **kw)
    except OSError as error:
        return subprocess.CompletedProcess(args, 127, "", str(error))


DEVICE_LINE = re.compile(
    r"using device CUDA(\d+) \(([^)]*)\) \(([0-9a-fA-F:.]+)\)")
# One per load, printed ahead of the device block, so it marks the boundary
# that grepping the journal would otherwise destroy.
LOAD_BOUNDARY = re.compile(r"ggml_cuda_init: found \d+ CUDA device")


def serving_device(cfg, since):
    """The devices that actually answered, read from the worker's own load.

    `nvidia-smi` reports the machine, not the run. On a box holding more
    than one card its output names every device and the one that served
    appears nowhere, which is how the first olympus Ada arm ran to
    completion on an A6000 and reported REPRODUCED - the error was caught
    by reading the journal and by nothing in the record.

    **The engine logs one line per device it bound, not one per load.** At
    the pinned rev `ecce255`, `llama.cpp:1081` is
    `for (const auto & dev : model->devices)` around the `using device`
    line, and `ResidentModel::load` sets `LlamaSplitMode::Layer` with
    `with_devices` whenever admission binds more than one GPU. So a paired
    binding emits two lines in one load and a single scalar answer would
    name a device that never served alone. Every line of the most recent
    load is kept, and the most recent load is the last contiguous run of
    them: the engine emits the block from one loop with nothing
    interleaved.

    **An unreadable journal is not an absent device.** `journalctl` exits 0
    with empty output when the invoking user is in neither `systemd-journal`
    nor `adm`, and this script runs it unprivileged while running admin
    under `sudo -n`. Reporting that as "no CUDA device" would hide the
    wrong-device defect this reader exists to catch, on exactly the boxes
    whose provisioning is least careful. The unit logged copiously during a
    load that succeeded, so zero lines of any kind means the read failed,
    and that is recorded as its own answer.
    """
    groups = _device_groups(cfg, since)
    if "unreadable" in groups:
        return groups
    found = groups["groups"]
    if found:
        return {"devices": found[-1]}
    return {"devices": [], "note": "the load named no CUDA device"}


def device_bindings(cfg, since):
    """Every distinct binding seen in the window, in first-seen order.

    `serving_device` answers for one load. A run that loads repeatedly needs
    to know whether the answer held, which is the assumption issue #370
    falsified, so this reports the set rather than a representative.
    """
    groups = _device_groups(cfg, since)
    if "unreadable" in groups:
        return [groups]
    seen = []
    for g in groups["groups"]:
        if g not in seen:
            seen.append(g)
    return seen


def _device_groups(cfg, since):
    """The window's `using device` blocks, one list of devices per load.

    **The load boundary is read explicitly and not inferred from adjacency.**
    An earlier draft grouped on contiguity, which is correct against the raw
    journal and wrong the moment the read is grepped: `-g` drops every
    non-matching line, so four single-device loads arrive as four adjacent
    lines and read as one four-device binding. The engine prints
    `ggml_cuda_init: found N CUDA devices` once per load ahead of the block,
    so that line is matched too and starts a new group.

    **Exit 1 is "no matches" and not a failure.** `journalctl -g` exits 1
    when its pattern matches nothing, which is the ordinary answer for a
    window holding no load.
    """
    unit = f"weaver-worker@{cfg['agent']}.service"
    base = ["journalctl", "-u", unit, "--since", since, "--no-pager", "-o", "cat"]
    # Grepped in the journal rather than in this process: an unfiltered read
    # spans every load in the window and llama.cpp is verbose.
    r = sh(base + ["-g", "ggml_cuda_init: found|using device CUDA"])
    if r.returncode not in (0, 1):
        return {"unreadable": f"journalctl exit {r.returncode}: "
                              f"{r.stderr.strip()[:200]}"}
    groups, current = [], None
    for line in r.stdout.splitlines():
        if LOAD_BOUNDARY.search(line):
            if current is not None:
                groups.append(current)
            current = []
            continue
        m = DEVICE_LINE.search(line)
        if m and current is not None:
            current.append({"ordinal": int(m.group(1)),
                            "name": m.group(2),
                            "pci_bus_id": m.group(3)})
    if current is not None:
        groups.append(current)
    groups = [g for g in groups if g]
    if groups:
        return {"groups": groups}
    # No match. Distinguish a journal this user cannot read from a load that
    # genuinely bound no CUDA device, by asking whether the unit logged
    # anything at all. Paid only in the empty case.
    probe = sh(base + ["-n", "1"])
    if probe.returncode != 0 or not probe.stdout.strip():
        return {"unreadable": "the unit's journal read back empty; this user "
                              "is likely in neither systemd-journal nor adm"}
    return {"groups": []}


def spu_binary(cfg):
    """The SPU binary path, from the authority that already holds it.

    `weaver-admin` reads `spu-binary` from its config directory, required
    rather than defaulted, on the stated ground that a missing one refuses
    and names itself rather than being searched for
    (`weaver-admin/src/main.rs`, per Spec section 9). Guessing it beside
    `admin_bin` would re-introduce the search that rule exists to forbid,
    and the crate's own default is `/usr/libexec/weaver-spu` while the
    deploy material uses `/usr/local/libexec/weaver/`, so the two are not
    reliably co-located. The config is read first, an explicit `spu_bin`
    overrides it, and the sibling guess is the last resort rather than the
    first.
    """
    return _resolve_spu(cfg)[0]


def _resolve_spu(cfg):
    """The SPU path and how it was arrived at.

    **The source travels because the last resort is a guess.** With the admin
    config unreadable the other two binaries record `unreadable` naming the
    config, while this one falls back beside `admin_bin` - and a stale binary
    from an older deploy sitting there would be hashed confidently under the
    field whose whole purpose is to say whether two boxes run one build.
    """
    if cfg.get("spu_bin"):
        return cfg["spu_bin"], "config spu_bin"
    # **Skipped rather than joined against nothing.** `os.path.join("", name)`
    # is a bare relative name read against the launch directory, so a file
    # called `spu-binary` sitting there would be taken for the admin config
    # and reported as an authoritative reading - a cwd artifact wearing the
    # source that the `resolved_by` marker suppresses.
    directory = cfg.get("admin_config")
    if directory:
        stated = os.path.join(directory, "spu-binary")
        try:
            with open(stated) as f:
                named = f.read().strip()
            if named:
                return named, "admin config spu-binary"
        except OSError:
            pass
    admin_bin = cfg.get("admin_bin")
    if not admin_bin:
        # `.get`, as `toolchain` uses beside it: a config omitting this raised
        # `KeyError` here, and this reader runs before the `try` that restores
        # the operator's declaration.
        return None, "the config names neither spu_bin, admin_config, nor admin_bin"
    return (
        os.path.join(os.path.dirname(admin_bin), "weaver-spu"),
        "guessed beside admin_bin, the admin config naming none",
    )


def _why(error):
    """An exception's reason, or its name where it carries none.

    `str(KeyboardInterrupt())` is empty, so a record templated straight over
    it reads `engine_libraries: ` - a failure naming no failure, which is the
    absence this file keeps removing.
    """
    said = str(error).strip()
    return said if said else type(error).__name__


def is_reading(value):
    """True where a reader came back with a reading rather than a note.

    **These readers report failure by returning, not by raising**, so a
    caller that only guards against exceptions has not guarded at all. A
    closing re-read that failed would otherwise compare unequal to a good
    opening read and be recorded as `varied` - a positive claim that the
    build changed mid-run, made out of a transient failure to look.

    `weaver_binaries` and `engine_libraries` report per entry rather than as a
    whole, so any unreadable entry makes the set unsafe to compare: two sides
    differing only in which entry could not be read say nothing about the
    build.

    **Every reader in this file marks failure with `unreadable` and with no
    other key**, which is what makes this test total rather than a list of
    the failure shapes its author knew. An earlier form knew one of three -
    `engine_libraries` also wrote `unresolved` and `error` - so a library that
    resolved and failed to hash passed as a reading and was then reported as
    a changed build. A test that enumerates failure keys falls behind the next
    reader; one failure key cannot.
    """
    if not isinstance(value, dict) or not value or "unreadable" in value:
        return False
    return not any(
        isinstance(entry, dict) and "unreadable" in entry
        for entry in value.values()
    )


def close_hashes(reading):
    """The sha256 of each entry, which is what a build comparison is about.
    `path` and `resolved_by` can differ while the bytes agree."""
    return {name: entry.get("sha256")
            for name, entry in reading.items() if isinstance(entry, dict)}


def close_whole(reading):
    """The reading itself, for a reader whose values are not hashes -
    `close_hashes` would answer `{}` for the toolchain and two different
    toolchains would compare equal."""
    return reading


def close_resolution(reading):
    """Which files a reading looked at, as against what it found in them."""
    return {name: (entry.get("path"), entry.get("resolved_by"))
            for name, entry in reading.items() if isinstance(entry, dict)}


def closing_resolution(cfg):
    """The close's shared SPU resolution, or the note a failed one becomes.

    The resolution is the one step of the close that ran outside
    `provenance_close`'s catch, so a raise there - a second interrupt
    landing in the window the matrix documents, or an unanticipated
    failure - lost the entire close, and in the matrix the summary with
    it. Resolved once so the two collectors cannot disagree about which
    SPU they measured, and a failure becomes the reading both collectors
    return, closing as `at_close_unreadable` instead of as a lost run.
    """
    try:
        return _resolve_spu(cfg), None
    except (Exception, KeyboardInterrupt) as e:  # noqa: BLE001
        return None, {"unreadable": f"the SPU resolution raised: {_why(e)}"}


def provenance_close(cfg, reader, at_start, what, essence=None):
    """Read again at the close and say how the two readings relate.

    Lifted from the matrix driver per #379: `close()` and its helpers were
    local to `determinism_matrix.main` while this driver compared with a raw
    `!=`, so the two drivers answered one question differently - the matrix
    would not claim a change it could not support and this driver would.
    One implementation, every driver a caller.

    **One envelope on every branch.** `status` says which case it is and the
    readings sit in named fields beside it, so a consumer reads the status
    rather than testing which keys are present.

    **Resolution is compared before content.** Two readings that looked at
    different files say nothing about whether a build moved, so `varied` is
    claimed only where both readings looked at the same places.
    """
    essence = close_hashes if essence is None else essence
    try:
        at_close = reader(cfg)
    except (Exception, KeyboardInterrupt) as e:  # noqa: BLE001
        at_close = {"unreadable": f"{what}: {_why(e)}"}
    if not is_reading(at_close):
        return {"status": "at_close_unreadable",
                "at_start": at_start, "note": at_close}
    if not is_reading(at_start):
        return {"status": "at_start_unreadable",
                "at_close": at_close, "note": at_start}
    if close_resolution(at_close) != close_resolution(at_start):
        return {"status": "resolved_differently",
                "at_start": at_start, "at_close": at_close}
    if essence(at_close) != essence(at_start):
        return {"status": "varied",
                "at_start": at_start, "at_close": at_close}
    return {"status": "unchanged", "reading": at_start}


def _said_or_unreadable(result, what):
    """A command's output, or a note saying why there is none.

    The readers below all carry their reason rather than a bare empty value,
    and the fields that predate them must too now that `sh` answers instead
    of raising.
    """
    if result.returncode != 0:
        # A command can fail silently, and `exit 1: ` names no failure - the
        # absence this file keeps removing, one call site at a time.
        said = result.stderr.strip()[:200] or "no stderr"
        return {"unreadable": f"{what} exit {result.returncode}: {said}"}
    said = result.stdout.strip()
    return said if said else {"unreadable": f"{what} said nothing"}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def weaver_binaries(cfg, spu=None):
    """sha256 of the organ binaries this box will run.

    **The field that answers "are the two boxes on the same build".** A
    commit is not that answer: Rust and CUDA embed absolute paths and build
    state, so two boxes compiling one commit produce different bytes, and
    `commit` alone cannot distinguish a shared build from two local ones.
    The hashes can, and they are what a build-once-and-distribute
    arrangement is verified by.

    Olympus carried these in a hand-written `binary-shas.txt` beside its
    2026-08-27 deposit, which is the same sidecar the serving device and the
    engine libraries were carried in before issue #370's third ask. Read
    from the admin config, which already names all three, so the report
    names what the runtime is configured to launch rather than what
    a config file for this script believed.
    """
    out = {}
    for key in ("worker-binary", "spu-binary", "gate-binary"):
        # **The SPU goes through its own resolver**, which honours the
        # documented `spu_bin` override and falls back beside `admin_bin`.
        # Reading it straight from the config here would let one report hash
        # a real SPU under `engine_libraries` while recording `unreadable`
        # for the same binary under this key - two fields disagreeing about
        # which build was measured, on exactly the boxes whose provisioning
        # differs, which is what this field exists to compare.
        source = None
        if key == "spu-binary":
            path, source = spu if spu is not None else _resolve_spu(cfg)
            if path is None:
                out[key] = {"path": None, "sha256": None, "unreadable": source}
                continue
        else:
            directory = cfg.get("admin_config")
            if not directory:
                # Not a bare relative name read against this process's cwd:
                # `_resolve_spu` and `toolchain` both refuse rather than
                # guessing when their directory is unnamed, and three readers
                # in one file may not disagree about that.
                out[key] = {"path": None, "sha256": None,
                            "unreadable": "the config names no admin_config"}
                continue
            stated = os.path.join(directory, key)
            try:
                with open(stated) as f:
                    path = f.read().strip()
            except OSError as e:
                out[key] = {"path": None, "sha256": None,
                            "unreadable": f"{stated}: {e}"}
                continue
            # An empty config file is an unset value, not a binary at the
            # empty path, and `_sha256("")` would report it as a missing file.
            if not path:
                out[key] = {"path": None, "sha256": None,
                            "unreadable": f"{stated}: names no path"}
                continue
        try:
            out[key] = {"path": path, "sha256": _sha256(path)}
        except OSError as e:
            out[key] = {"path": path, "sha256": None, "unreadable": str(e)}
        # Recorded only where it is not the plain reading, so a report says
        # "guessed" exactly when it guessed.
        if source and not source.startswith("admin config"):
            out[key]["resolved_by"] = source
    return out


def toolchain(cfg):
    """The Rust toolchain in force at the repository, not the ambient one.

    **`rustc --version` answers differently depending on where it is run.**
    `rust-toolchain.toml` overrides per directory, so a driver launched
    outside the repository reports the box's default compiler while the
    binaries were built with the pin. That is not hypothetical: of the three
    olympus arms of 2026-08-27, all running one installed binary set at
    `experiment-a9634c0`, two recorded `1.95.0-nightly` and the Ada arm
    recorded `1.97.1`. One build, two claimed compilers, the difference
    being the launch directory.

    Read with `cwd` at the repository so the pin applies, and the active
    toolchain recorded beside it so an override is visible rather than
    silent.
    """
    repo = cfg.get("repo")
    if not repo:
        # **Not `.`, which is the defect this reader exists to end.** The
        # matrix driver reads only `trace` and `declaration` from its config,
        # so a config omitting `repo` is valid today and a fallback to the
        # launch directory would read the ambient compiler again with nothing
        # saying the pin was not applied.
        return {"unreadable": "the config names no repo, so the pin's"
                              " directory is unknown"}
    version = sh(["rustc", "--version"], cwd=repo)
    if version.returncode != 0:
        return {"unreadable": f"rustc exit {version.returncode} at {repo}: "
                              f"{version.stderr.strip()[:200]}"}
    active = sh(["rustup", "show", "active-toolchain"], cwd=repo)
    out = {"rustc": version.stdout.strip()}
    # The toolchain marker is the part that distinguishes a pin in force from
    # a box default, so its absence is named rather than left as a bare null.
    #
    # **The note rides the entry rather than a key beside it.** An earlier
    # form wrote `active_toolchain_unreadable` at the top level, which
    # `is_reading` does not look at - so a half-failed toolchain passed as a
    # reading and broke the one-failure-key invariant that test rests on. It
    # was latent only because this reader is not read twice; the moment it is,
    # a `rustup` that fails once and succeeds once reports the toolchain as
    # having changed mid-run.
    if active.returncode == 0 and active.stdout.strip():
        out["active_toolchain"] = active.stdout.strip().splitlines()[0]
    else:
        # Named for the condition rather than templated over it: a clean exit
        # with nothing on either stream would read as `rustup exit 0:`, a
        # failure record naming no failure, which is the silent absence the
        # rest of this act removes.
        if active.returncode == 127:
            # **Absent is a reading, not a failure.** A distro `rust` with no
            # rustup is an ordinary box, stable across both reads, and the
            # `rustc` string above is still the comparison's meat. Marking it
            # unreadable made the whole toolchain permanently incomparable on
            # such a box and threw the good half away - defect 3 of #379.
            out["active_toolchain"] = {"absent": "no rustup on this box"}
        elif active.returncode == 0:
            out["active_toolchain"] = {
                "unreadable": "rustup exited cleanly and said nothing"}
        else:
            said = active.stderr.strip()[:200]
            out["active_toolchain"] = {"unreadable":
                f"rustup exit {active.returncode}" + (f": {said}" if said else "")}
    return out


def engine_libraries(cfg, spu=None):
    """sha256 of the libraries the serving binary actually links.

    Read through `ldd` rather than from a configured list, so the answer is
    what the loader resolves rather than what an operator believed. **The SPU
    is resolved once by the caller and passed**, both collectors having
    resolved it independently until 2026-08-28: a config read blipping between
    the two calls put a guessed path under one field and a stated path under
    the other, two fields in one report disagreeing about which binary they
    measured. The
    decode math lives in `libggml-cuda` and `libllama`, and issue #370
    established that a Blackwell figure cannot be attributed while these
    are unrecorded: a cross-box divergence is silicon, libraries, or both,
    and a report that omits them cannot say which.

    **Every failure says which failure it was.** A bare empty result would
    read as "recorded, nothing to record", which is the same silent absence
    the `device` retirement exists to end.
    """
    spu = (spu[0] if spu is not None else spu_binary(cfg))
    if spu is None:
        return {"unreadable": "the config names no route to the SPU binary"}
    if not os.path.exists(spu):
        return {"unreadable": f"no SPU binary at {spu}"}
    r = sh(["ldd", spu])
    if r.returncode != 0:
        return {"unreadable": f"ldd exit {r.returncode} on {spu}: "
                              f"{r.stderr.strip()[:200]}"}
    out = {}
    for line in r.stdout.splitlines():
        m = re.search(r"(lib(?:ggml[\w-]*|llama)\.so[\w.]*)\s+=>\s+(\S+)", line)
        if not m:
            continue
        name, path = m.group(1), m.group(2)
        # `ldd` prints `=> not found` for an unresolved library, whose
        # second field is the bare word `not`. Recorded as unresolved
        # rather than hashed as a path.
        if not path.startswith("/"):
            out[name] = {"path": None, "sha256": None,
                         "unreadable": "ldd reports it not found"}
            continue
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            out[name] = {"path": path, "sha256": h.hexdigest()}
        except OSError as e:
            out[name] = {"path": path, "sha256": None, "unreadable": _why(e)}
    if not out:
        return {"unreadable": f"{spu} links no ggml or llama library"}
    return out


def admin(cfg, verb):
    r = sh(["sudo", "-n", f"WEAVER_ADMIN_CONFIG={cfg['admin_config']}",
            cfg["admin_bin"], verb, cfg["agent"]])
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"kind": "unparsed", "stdout": r.stdout, "stderr": r.stderr,
                "exit": r.returncode}


def wait_socket(cfg, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(cfg["gate_socket"]):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(cfg["gate_socket"])
                s.close()
                return True
            except OSError:
                pass
        time.sleep(0.5)
    return False


def gate_turn(cfg, text, timeout=600):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(cfg["gate_socket"])
    s.sendall((json.dumps({"text": text}) + "\n").encode())
    line = s.makefile().readline()
    s.close()
    return json.loads(line)


def read_runs(trace_path, keep=None):
    """Run -> its events, in first-appearance order.

    **`keep` reads the tail rather than the file**, and a caller wanting the
    most recent runs should pass it. The trace is append-only and grows
    without bound, so a full parse costs the whole history to answer a
    question about its end: measured 2026-08-27 against a 251 MiB trace, the
    full scan took 4.0 s and ran twice per cell, which is the harness
    charging a run for every run before it. With `keep` the cost follows the
    tail instead.

    The scan walks backward in chunks and stops one run past the `keep`th, so
    the `keep` newest runs are whole rather than cut at a chunk edge. A
    partial line at a chunk boundary is held for the next block for the same
    reason. `keep=None` reads everything, which is the original behaviour.

    **The oldest run returned is a boundary fragment and carries one event.**
    The stop fires on the first line of the `keep`-plus-first run met going
    backward, so `keep=k` answers k+1 runs and `order[0]` is a stub. Every
    caller here takes `order[-1]` or indexes by a run it already names, so
    the stub is inert, and it is described rather than trimmed because a
    caller that iterated `runs` would otherwise meet it unwarned.

    **A run's events are assumed contiguous**, which holds by construction:
    a run is one load-to-unload cycle against a sequentially served agent, so
    no second run interleaves it. Were they interleaved the backward stop
    could fall inside a run and truncate it, and the interleaving checks
    elsewhere in this harness guard the reissue rather than this scan.
    """
    lines = open(trace_path) if keep is None else _tail_lines(trace_path, keep)
    runs = {}
    order = []
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        r = e.get("run")
        if r is None:
            continue
        if r not in runs:
            runs[r] = []
            order.append(r)
        runs[r].append(e)
    return order, runs


def _tail_lines(trace_path, keep, chunk=1 << 20):
    """The trailing lines covering the last `keep` runs, in file order."""
    with open(trace_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        held = b""
        out = []
        seen = []
        done = False
        while pos > 0 and not done:
            step = min(chunk, pos)
            pos -= step
            f.seek(pos)
            block = f.read(step) + held
            parts = block.split(b"\n")
            # The first element may be the tail of a line beginning further
            # back, so it is held for the next block rather than parsed here.
            held = parts[0]
            for raw in reversed(parts[1:]):
                if not raw.strip():
                    continue
                out.append(raw)
                try:
                    r = json.loads(raw).get("run")
                except json.JSONDecodeError:
                    continue
                if r is not None and r not in seen:
                    seen.append(r)
                    # One past `keep`: the `keep`th run is whole only once a
                    # newer boundary has been crossed.
                    if len(seen) > keep:
                        done = True
                        break
        if not done and held.strip():
            out.append(held)
    return [raw.decode("utf-8", "replace") for raw in reversed(out)]


def newest_load(trace_path, keep=2):
    """The newest run carrying a `load` event, and that event.

    Answers `(None, None)` where the trace does not exist or holds no load in
    its tail, so a caller on a fresh box reads an absence rather than
    catching one.
    """
    try:
        order, runs = read_runs(trace_path, keep=keep)
    except OSError:
        return None, None
    for run in reversed(order):
        for e in runs[run]:
            if e.get("kind") == "load":
                return run, e
    return None, None


def assert_loop(cfg, trace_path, before=None, timeout=15.0):
    """Refuse a load composed by a loop other than the one the config declares.

    **The digest is the identity and the name is not**, per issue #426. Every
    `load` event carries `payload.composer`, the loop that composed the run's
    prompts, with `sha256` present where the loop is a file the pyworker read
    and absent where it is compiled in. `dev_loop.py` and `basic_loop.py`
    were byte-identical when this was measured, as were `alpha_loop.py` and
    `bravo_loop.py`, so a criterion written against a name passes a box
    running either, and a box that silently changed loops would deposit a
    comparable-looking run. The config's `loop_sha256` is compared to the
    recorded digest and nothing else.

    **A config declaring no loop is unchecked**, so the configs that predate
    the key keep running, and a deposit made under one carries no
    `loop_refused` field either way - absence of the key means the question
    was not asked, and the README says so.

    Answers `None` where the load's composer carries the declared digest, and
    otherwise the refusal, carrying both digests so the report names what
    was declared and what was found. A composer with no digest - a compiled
    loop, or a build from before #419 that recorded no composer - is refused
    where a digest is declared, because it cannot be shown to be the one
    declared. The newest load is awaited rather than read once: the harness
    writes the trace behind the close, and `before` names the newest run
    that stood ahead of this load so the previous cell's load cannot answer
    for it.
    """
    declared = cfg.get("loop_sha256")
    if declared is None:
        return None
    end = time.time() + timeout
    delay = 0.02
    while True:
        run, event = newest_load(trace_path)
        if run is not None and run != before:
            break
        if time.time() >= end:
            return {"declared": declared, "recorded": None, "run": None,
                    "composer": None,
                    "note": "no load event for a new run reached the trace "
                            f"within {timeout:g}s, so the loop cannot be shown "
                            "to be the declared one"}
        time.sleep(delay)
        delay = min(delay * 1.5, 1.0)
    composer = (event.get("payload") or {}).get("composer")
    recorded = composer.get("sha256") if isinstance(composer, dict) else None
    if recorded == declared:
        return None
    return {"declared": declared, "recorded": recorded, "run": run,
            "composer": composer}


def loop_refusal(report, refused, half, log):
    """Land a refusal in the cell's report, loudly and typed.

    One field, `loop_refused`, beside a verdict that names it, so a consumer
    reads the field rather than parsing the verdict, and the driver's summary
    line cannot read as a reproduction result.
    """
    report["loop_refused"] = dict(refused, half=half)
    report["verdict"] = (
        f"loop refused at the {half} load: declared "
        f"{refused['declared']}, recorded {refused['recorded']}")
    log(f"LOOP REFUSED: {json.dumps(report['loop_refused'])}")
    return report


def await_turns(trace_path, want, run_id, keep=4, timeout=None):
    """`run_id` once it carries `want` turns, or once time runs out.

    **The run is named by the caller rather than taken as the newest**, per
    the seat's finding of 2026-08-27. A wait on whichever run is newest is
    satisfied by the wrong run when the sink is dead rather than slow: the
    cell before this one left a run of the same length, `want` is met on the
    first read, and the caller reissues against a stale record and reports a
    match that never happened. The close already carries the run it opened,
    so the identity is in hand and is passed.

    **The sink writes after the close answers**, so a read taken the instant
    a turn closes can miss the events that turn produced. This was invisible
    while `read_runs` scanned the whole trace, because the scan itself took
    seconds and the sink caught up inside it. The tail read of 2026-08-27
    removed that accidental delay and the race surfaced as a run one turn
    short, every time, the missing turn always the last. Waiting for the
    record is what the harness meant to do, and an accidental sleep is not a
    way to do it.

    Answers `(turns, events)` with whatever stands when the count is reached
    or the timeout expires, and the caller reports the shortfall - a wait
    that raised would turn a slow sink into a failed cell. **The events come
    back beside the turns** so a caller depositing the run needs no second
    read and holds no `runs` dict of its own.
    """
    # **The bound follows the work.** A deep session flushes many times the
    # events of a shallow one behind a sink that has just spent a minute
    # generating, so a fixed bound is generous for one and tight for the
    # other.
    if timeout is None:
        timeout = 30.0 + 0.5 * want
    end = time.time() + timeout
    turns, events = [], []
    delay = 0.02
    while True:
        _, runs = read_runs(trace_path, keep=keep)
        if run_id in runs:
            events = runs[run_id]
            turns = cut_turns(events)
            if len(turns) >= want:
                return turns, events
        if time.time() >= end:
            return turns, events
        time.sleep(delay)
        # Backing off rather than polling flat: the scan has a one mebibyte
        # floor, so a wait that runs to its bound reads on the order of a
        # gigabyte to learn nothing.
        delay = min(delay * 1.5, 1.0)


def cut_turns(events):
    """Turn -> its events, in first-appearance order. The request text
    is the turn's last message.user event, identity messages preceding
    the request in render order."""
    order, by = [], {}
    for e in events:
        t = e.get("turn")
        if not t:
            continue
        if t not in by:
            by[t] = {}
            order.append(t)
        by[t].setdefault(e["kind"], []).append(e)
    turns = []
    for t in order:
        k = by[t]
        users = k.get("message.user", [])
        text = None
        if users:
            c = users[-1].get("payload", {}).get("content", [])
            if c and c[0].get("type") == "text":
                text = c[0]["text"]
        payload = {kind: (k[kind][0].get("payload") if kind in k else None)
                   for kind in ("model.request", "model.output",
                                "model.measurement")}
        wall = {kind: (k[kind][0].get("wall_ms") if kind in k else None)
                for kind in ("turn.started", "turn.closed")}
        turns.append({"turn": t, "text": text, "payload": payload,
                      "wall": wall})
    return [t for t in turns
            if t["text"] is not None
            and all(t["payload"][x] is not None for x in t["payload"])]


def pointer(value, ptr):
    cur = value
    for part in ptr.strip("/").split("/"):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def compare_turn(src, rep):
    out = []
    for name, kind, ptr in CHECKS:
        a = pointer(src["payload"][kind], ptr)
        b = pointer(rep["payload"][kind], ptr)
        out.append({"check": name, "match": a == b})
    return out


def whole_ms(t):
    a, b = t["wall"]["turn.started"], t["wall"]["turn.closed"]
    return (b - a) if a is not None and b is not None else None


def cell_metadata(cfg, cell, libraries, binaries, tools, texts=None):
    # **The artifact's hash degrades rather than raising.** A missing or
    # unreadable artifact would otherwise abort `run_cell` before its report
    # exists and take every remaining cell with it, which is the class of
    # defect the rest of this act removes: a metadata read is not a reason a
    # run does not happen.
    try:
        artifact_sha = _sha256(cell["artifact"])
    except OSError as error:
        artifact_sha = {"unreadable": _why(error)}
    # **Both read the returncode, because `sh` no longer raises.** Softening
    # `sh` to answer 127 rather than throw fixed the readers that could abort
    # a run and broke these two, which took `.stdout` blind: on a box without
    # `nvidia-smi` or `git` on PATH the driver used to die loudly and would
    # now deposit `""` and report REPRODUCED. An empty string that does not
    # say it is empty is the absence the `device` retirement exists to end.
    gpu = _said_or_unreadable(
        sh(["nvidia-smi", "--query-gpu=name,driver_version",
            "--format=csv,noheader"]),
        "nvidia-smi",
    )
    # `.get`, as `toolchain` and `_resolve_spu` both use: a config naming no
    # repository is a config error rather than a crash, and `git -C` against
    # `None` would not survive the call anyway.
    repo = cfg.get("repo")
    commit = (
        _said_or_unreadable(sh(["git", "-C", repo, "rev-parse", "HEAD"]), "git rev-parse")
        if repo
        else {"unreadable": "the config names no repo"}
    )
    return {
        "box": cfg["box"],
        "precision": cell["precision"],
        "artifact": cell["artifact"],
        "artifact_sha256": artifact_sha,
        # **`device` is retired rather than redefined**, per issue #370. It
        # held this whole-machine listing, so every GPU present appeared in
        # every report and the one that answered appeared nowhere. Reusing
        # the key for the serving device would leave old and new reports
        # disagreeing in meaning under one name, which is worse than either
        # meaning: the reader cannot tell which they hold. The listing keeps
        # a name that says what it is, and `serving_device` is filled in
        # after the load by the party that knows.
        "machine_gpus": gpu,
        # Filled in after each load by the party that knows. `source` and
        # `replay` are recorded apart because they are two loads and may
        # not bind the same devices, per finding 3 of the olympus seat.
        "serving_device": {"source": None, "replay": None},
        # Hoisted: the libraries cannot change during a run and
        # `libggml-cuda` built for four architectures is 142 MiB to hash.
        "engine_libraries": libraries,
        # **What a reader compares to answer "same build".** The commit
        # cannot answer it: two boxes compiling one commit produce different
        # bytes, so `commit` distinguishes source, and these distinguish
        # builds.
        "weaver_binaries": binaries,
        "build_flags": cfg["build_flags"],
        # `rustc` reports the toolchain in force at the repository rather
        # than on the ambient PATH, and `active_toolchain` makes an override
        # visible. The olympus arms of 2026-08-27 recorded two compilers for
        # one binary set because the old field followed the launch
        # directory.
        "toolchain": tools,
        "commit": commit,
        # **The texts recorded are the texts served.** With `texts` supplied
        # the pinned pair below is wrong by construction - a caller passing
        # its own turn list would deposit metadata naming prompts the record
        # does not carry, which is the misstating-provenance defect this
        # repository keeps paying for. The two constant keys stay for the
        # default so existing deposits keep their schema.
        **({"short_text": SHORT_TEXT, "long_text": LONG_TEXT}
           if texts is None else {"turn_texts": list(texts)}),
    }


def run_cell(cfg, cell, outdir, libraries, binaries, tools,
             texts=None, require_completed=False, turn_timeout=600):
    """One session under the serve-unload-reload-reissue protocol.

    `texts` is the turn list, defaulted to the two pinned constants so the
    cross-precision cells read as they always did. The trace-generation
    driver passes its own list - the protocol is one and the sessions are
    not, which is issue #379's ruling applied before the second
    implementation exists rather than after.

    `require_completed` makes a cap-hit a verdict rather than a recorded
    field: a capped turn is a defective specimen for a trace whose purpose
    is source material, per the 8B sketch's parameter section, so the cell
    fails loudly instead of depositing a truncation that reads as an answer.
    """
    # **Materialized once, sentinel preserved.** The caller's value is
    # listed exactly one time, so an iterator cannot be consumed by the
    # serving loop and then re-listed empty into the metadata - the
    # misstating-provenance defect this parameter exists to close, reachable
    # by input shape. `None` still selects the short_text/long_text schema
    # the existing confirm deposits carry.
    texts = None if texts is None else list(texts)
    name = cell["name"]
    log = lambda m: print(f"[{name}] {m}", flush=True)
    report = {"cell": name,
              "metadata": cell_metadata(cfg, cell, libraries, binaries, tools,
                                        texts=texts),
              "steps": [], "turns": [], "verdict": None}
    if texts is None:
        texts = [SHORT_TEXT, LONG_TEXT]

    # The declaration with this cell's artifact, everything else as
    # the operator wrote it.
    with open(cfg["declaration"]) as f:
        decl = f.read()
    swapped, n = re.subn(r"(artifact:\s*).*", r"\g<1>" + cell["artifact"],
                         decl, count=1)
    if n != 1:
        report["verdict"] = "no artifact line in the declaration"
        return report
    with open(cfg["declaration"], "w") as f:
        f.write(swapped)

    def step(verb):
        a = admin(cfg, verb)
        report["steps"].append({verb: a})
        log(f"{verb}: {json.dumps(a)}")
        return a

    # The finally below guarantees the cell never leaves an agent
    # holding the device, whichever return path it takes.
    try:
        step("unload")  # whatever held the device before this cell
        # The window opens before the load so the journal read below cannot
        # reach back to a previous cell's load, and a second of slack
        # absorbs the clock skew between this process and the journal's
        # own timestamps.
        since = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1))
        before = newest_load(cfg["trace"])[0]
        if step("load").get("kind") != "state":
            report["verdict"] = "load refused"
            return report
        if not wait_socket(cfg):
            report["verdict"] = "gate socket never stood"
            return report
        # **The loop that composed this load is checked before a turn is
        # served through it**, per issue #426. A cell refused here deposits
        # no runs and no turns, only the refusal, so the report cannot be
        # read as a comparison.
        refused = assert_loop(cfg, cfg["trace"], before)
        if refused:
            return loop_refusal(report, refused, "source", log)

        # **What served is read from the worker and not from the machine**,
        # per issue #370's third ask. Read after the socket stands, so the
        # load has reached the point of binding a device rather than merely
        # having been asked to.
        report["metadata"]["serving_device"]["source"] = serving_device(cfg, since)
        log(f"source devices: "
            f"{json.dumps(report['metadata']['serving_device']['source'])}")

        log("serving the source turns")
        source_runs = set()
        for text in texts:
            close = gate_turn(cfg, text, timeout=turn_timeout)
            log(f"close {close.get('kind')} turn {close.get('turn')}")
            if close.get("kind") != "answered":
                report["verdict"] = f"source turn not answered: {close}"
                return report
            source_runs.add(close.get("run"))

        # The closes name the run, so the wait is on that run and not on
        # whichever is newest, per the seat's finding of 2026-08-27.
        if len(source_runs) != 1 or None in source_runs:
            report["verdict"] = (
                "the source turns did not share one run: "
                f"{sorted(map(str, source_runs))}"
            )
            return report
        source_run = source_runs.pop()
        source_turns, source_events = await_turns(
            cfg["trace"], len(texts), source_run)
        if len(source_turns) != len(texts):
            report["verdict"] = (
                f"expected {len(texts)} source turns, found {len(source_turns)}")
            return report
        if require_completed:
            for st in source_turns:
                finish = pointer(st["payload"].get("model.output"), "/finish")
                if finish != "completed":
                    report["verdict"] = (
                        f"source {st['turn']} finished {finish!r} rather than"
                        " completed - a capped turn is a defective specimen"
                        " and the cell fails rather than records")
                    return report

        step("unload")
        replay_since = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1))
        before = source_run
        if step("load").get("kind") != "state":
            report["verdict"] = "reload refused"
            return report
        if not wait_socket(cfg):
            report["verdict"] = "gate socket never stood after reload"
            return report
        # The reload is a second load and is checked as one: the loop file
        # can move between the two halves as easily as before the first.
        refused = assert_loop(cfg, cfg["trace"], before)
        if refused:
            return loop_refusal(report, refused, "replay", log)

        # **The reissue half binds its own devices and they are read too.**
        # A cell that compared a source on one card against a replay on
        # another and called it REPRODUCED would be the olympus A6000 error
        # relocated to the second half, per finding 3 of the olympus seat.
        # A disagreement fails the cell rather than being recorded and
        # passed over: the comparison the cell exists to make is not
        # between these two runs.
        report["metadata"]["serving_device"]["replay"] = serving_device(
            cfg, replay_since)
        src = report["metadata"]["serving_device"]["source"]
        rep = report["metadata"]["serving_device"]["replay"]
        log(f"replay devices: {json.dumps(rep)}")
        # **Equality is not enough, because absence is equal to itself.** An
        # earlier draft compared the two and passed when they matched, so a
        # box whose journal this user cannot read produced `unreadable`
        # twice, compared equal, and sailed through the gate - the
        # wrong-device defect invisible again on exactly the boxes the gate
        # was added for. The gate asks for positive evidence from both
        # halves first and compares only then.
        #
        # A cell that names no device is failed rather than recorded. This
        # driver exists to compare runs across silicon, and per issue #370 a
        # run record omitting the device cannot support that comparison, so
        # a CPU-only box gets a plain refusal here rather than a deposit
        # that looks complete and answers nothing.
        for half, seen in (("source", src), ("replay", rep)):
            if not isinstance(seen, dict) or "unreadable" in seen:
                report["verdict"] = (
                    f"the {half} load's serving device could not be read: "
                    f"{json.dumps(seen)}")
                return report
            if not seen.get("devices"):
                report["verdict"] = (
                    f"the {half} load named no CUDA device, so this cell "
                    "cannot support a cross-silicon comparison: "
                    f"{json.dumps(seen)}")
                return report
        if src != rep:
            report["verdict"] = (
                "source and replay did not bind the same devices: "
                f"{json.dumps(src)} against {json.dumps(rep)}")
            return report

        # Reissue byte-exact, from the record rather than from this
        # script's constants: the record is the artifact under test.
        # Every close must be answered and every close must name one
        # fresh run - a refusal or a split across runs ends the cell
        # rather than comparing against the wrong record.
        log("reissuing from the record")
        runs_seen = set()
        for st in source_turns:
            close = gate_turn(cfg, st["text"], timeout=turn_timeout)
            log(f"reissue {st['turn']} -> {close.get('kind')}")
            if close.get("kind") != "answered":
                report["verdict"] = f"reissue {st['turn']} closed {close.get('kind')}"
                return report
            runs_seen.add(close.get("run"))
        if len(runs_seen) != 1 or None in runs_seen or source_run in runs_seen:
            report["verdict"] = f"reissues did not land in one fresh run: {sorted(map(str, runs_seen))}"
            return report
        replay_run = runs_seen.pop()

        replay_all, replay_events = await_turns(
            cfg["trace"], len(source_turns), replay_run)
        if not replay_all:
            report["verdict"] = (
                f"the closes named run {replay_run} but the trace does not carry"
                " it - sink lag or a different sink"
            )
            return report
        replay_turns = {t["turn"]: t for t in replay_all}
        if len(replay_all) != len(source_turns):
            log(f"turn count differs: source {len(source_turns)} replay {len(replay_all)}")

        # A replay with surplus turns is interleaved traffic and is
        # never a match, even when every source turn agrees.
        # A short replay read is the sink rather than the model, and it
        # reaches its own verdict rather than being folded into a mismatch.
        if len(replay_all) < len(source_turns):
            report["verdict"] = (
                f"replay read short: expected {len(source_turns)} turns,"
                f" found {len(replay_all)} - the record is incomplete"
            )
            return report
        all_match = len(replay_all) == len(source_turns)
        for st in source_turns:
            rt = replay_turns.get(st["turn"])
            checks = (compare_turn(st, rt) if rt else
                      [{"check": c[0], "match": False} for c in CHECKS])
            ok = all(c["match"] for c in checks)
            all_match &= ok
            m = st["payload"]["model.measurement"]
            report["turns"].append({
                "turn": st["turn"],
                "reproduced": ok,
                "checks": checks,
                "tokens_in": len(m.get("input_tokens", [])),
                "tokens_out": len(m.get("entropies", [])),
                "source_ms": whole_ms(st),
                "replay_ms": whole_ms(rt) if rt else None,
            })
            log(f"{st['turn']}: {'MATCH' if ok else 'DIVERGED: ' + ', '.join(c['check'] for c in checks if not c['match'])}")

        report["source_run"] = source_run
        report["replay_run"] = replay_run
        report["verdict"] = "REPRODUCED" if all_match else "NOT REPRODUCED"

        # **Deposited from a fresh read rather than from the snapshots the
        # comparison used.** Those were taken the moment `cut_turns` was
        # satisfied, which on the source side is before its unload, so a
        # deposit made from them holds a run with no closing event and a
        # consumer cannot tell from the file that the run ended cleanly. The
        # comparison is unaffected either way and this costs one read a cell.
        _, whole = read_runs(cfg["trace"], keep=6)
        for label, run in (("source", source_run), ("replay", replay_run)):
            run_events = whole.get(run) or (
                source_events if label == "source" else replay_events)
            with open(os.path.join(outdir, f"cell-{name}-{label}.ndjson"), "w") as f:
                for e in run_events:
                    f.write(json.dumps(e) + "\n")
        return report
    finally:
        # Whichever path returned, the cell never leaves its artifact
        # holding the device. After an ordinary finish this answers
        # no_residency, which is harmless and recorded.
        step("unload")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()
    with open(args.config) as f:
        cfg = json.load(f)
    os.makedirs(args.outdir, exist_ok=True)

    backup = cfg["declaration"] + ".pre-cells"
    shutil.copy2(cfg["declaration"], backup)
    # Read once for the run: the libraries cannot change under it, and
    # `libggml-cuda` built for four architectures is 142 MiB to hash.
    reports = []
    out = os.path.join(args.outdir, f"report-{cfg['box']}.json")

    def deposit():
        # **Written after every cell and after the closing read**, so a raise
        # anywhere past the first cell costs the tail and never the record -
        # defect 2 of #379. The old single write sat after the try and a
        # seven-hour arm dying in the closing block would have left a
        # restored declaration and no deposit.
        with open(out, "w") as f:
            json.dump(reports, f, indent=1)

    try:
        # **Inside the scope that restores the declaration.** The backup is
        # already taken by this point, and a reader raising above the `try`
        # leaves a `.pre-cells` file beside the operator's own. `sh` no longer
        # raises, but it was never the only raiser in the window and this act
        # added two more readers into it.
        # One resolution for both collectors, so the two fields cannot
        # disagree about which SPU they measured.
        spu = _resolve_spu(cfg)
        libraries = engine_libraries(cfg, spu)
        binaries = weaver_binaries(cfg, spu)
        tools = toolchain(cfg)
        print(f"engine libraries: {json.dumps(libraries)}", flush=True)
        print(f"weaver binaries: {json.dumps(binaries)}", flush=True)
        print(f"toolchain: {json.dumps(tools)}", flush=True)
        for cell in cfg["cells"]:
            reports.append(
                run_cell(cfg, cell, args.outdir, libraries, binaries, tools))
            deposit()

        # **The provenance is read again after the cells have run**, the way
        # the matrix reads it at its close. A run unloads and reloads the
        # agent several times and can span an operator installing over it, so
        # a build swapped mid-run would otherwise be recorded nowhere and the
        # opening read asserted across the whole window.
        # **Guarded rather than raw**, per defect 1 of #379: the old `!=`
        # compared a failed closing read against a good opening one and
        # printed PROVENANCE MOVED out of a transient failure to look. The
        # lifted close claims `varied` only where both readings are sound
        # and looked at the same places.
        closing_spu, spu_note = closing_resolution(cfg)
        closings = {
            "engine_libraries": provenance_close(
                cfg, lambda c: spu_note or engine_libraries(c, closing_spu),
                libraries, "engine_libraries"),
            "weaver_binaries": provenance_close(
                cfg, lambda c: spu_note or weaver_binaries(c, closing_spu),
                binaries, "weaver_binaries"),
            "toolchain": provenance_close(
                cfg, toolchain, tools, "toolchain", essence=close_whole),
        }
        # Carried on every cell rather than beside them, the reports being a
        # list of cells and a reader of any one of them needing to know the
        # window did not hold. **One envelope on every branch** - defect 4's
        # shape half: a consumer reads `status`, never type-tests the field.
        for report in reports:
            report["metadata"]["provenance_at_close"] = closings
        unquiet = {k: v["status"] for k, v in closings.items()
                   if v["status"] != "unchanged"}
        if unquiet:
            print(f"PROVENANCE DID NOT HOLD QUIET: {json.dumps(unquiet)}",
                  flush=True)
        deposit()
    finally:
        shutil.copy2(backup, cfg["declaration"])
        os.unlink(backup)
        print("declaration restored", flush=True)

    deposit()
    print(f"\nreport: {out}")
    for r in reports:
        print(f"  cell {r['cell']}: {r['verdict']}")
    refused = [r["cell"] for r in reports if r.get("loop_refused")]
    if refused:
        print(f"LOOP REFUSED on {len(refused)} cell(s): {', '.join(refused)}"
              " - the box composed with a loop other than the one the config"
              " declares, and those cells deposited no comparison", flush=True)
    # **The window is part of the verdict** - defect 4's consequence half: a
    # detected mid-run swap, or a close that could not certify the window,
    # is not a reproduction result and must not exit 0. `closings` is bound
    # only when every cell ran, so an early abort exits nonzero through the
    # reproduced check alone.
    #
    # **A stably unreadable reader fails the gate, and that is a decision
    # rather than an inheritance**, named per #399's review: a box whose
    # config names no repo cannot read its toolchain at either end, and a
    # run that cannot read its toolchain cannot certify that its window
    # held. Every committed config names a repo. The alternative #379
    # sketched - is_reading distinguishing a partial reading from an
    # unusable one - stays open there for the reader that earns it.
    reproduced = all(r["verdict"] == "REPRODUCED" for r in reports) and reports
    window_held = all(
        v.get("status") == "unchanged"
        for r in reports
        for v in (r["metadata"].get("provenance_at_close") or {}).values()
        if isinstance(v, dict)
    )
    if reproduced and not window_held:
        print("cells reproduced but the provenance window did not hold quiet"
              " - not a reproduction result", flush=True)
    sys.exit(0 if reproduced and window_held else 1)


if __name__ == "__main__":
    main()
