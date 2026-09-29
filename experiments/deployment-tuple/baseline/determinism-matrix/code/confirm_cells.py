#!/usr/bin/env python3
"""The replay harness the determinism matrix imports.

It holds what every session and every run shares: the one session
verification, `verify_session`, which serves a session's turns, unloads
fully, reloads, reissues them byte-exact from the record and compares the
two runs field by field, the readers of the stack and the device, the
preflight checks, and the run-wide verdict, `run_verdict`. Stdlib only, so
any box with the runtime can run it unchanged.

**It has no entry point of its own** (#716, on the operator's ruling of
2026-09-27). The cross-precision protocol it once ran standalone, one
artifact at one precision per cell, is the matrix's `--cells` mode, with
one main, one session loop and one exit, and the matrix's README gives the
config.
"""
import copy
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import time
import tomllib

# Pinned across every box and every cell. Do not edit per box.
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
    `git` - none of which a box is obliged to carry. Raising there aborts
    the run at its preflight with a traceback rather than a refusal naming
    the reading. That is the rule `device_bindings` and
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
# The line the engine prints once its device block has ended: at the pinned
# rev `ecce255`, `llama_model_load_from_file_impl` names every device it
# binds and then constructs `llama_model_loader`, which logs this first
# (#716, after round twelve). A block is complete only once it is seen.
LOAD_COMPLETE = re.compile(r"llama_model_loader: loaded meta data")


def unit_invocation(cfg):
    """The InvocationID of the agent's worker unit as it stands now, the
    identity a device read is bound to (#716 round five). A time window is
    not an identity: a fast reload or a journal trailing its writer leaves
    the previous load inside any slack. Empty while the unit is inactive,
    and anything but 32 hex digits is refused by name."""
    unit = f"weaver-worker@{cfg['agent']}.service"
    r = sh(["systemctl", "show", "-p", "InvocationID", "--value", unit])
    said = r.stdout.strip()
    if r.returncode != 0 or re.fullmatch(r"[0-9a-f]{32}", said) is None:
        return {"unreadable": f"the unit's invocation id reads {said!r}"
                              f" (systemctl exit {r.returncode})"}
    return said


def serving_device(cfg, since, invocation=None):
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
    groups = _device_groups(cfg, since, invocation)
    if "unreadable" in groups:
        return groups
    found = groups["groups"]
    # Bound to one invocation, the read is one load's, and a second load
    # under it is not a shape this reader can attribute.
    if invocation is not None and len(found) > 1:
        return {"unreadable": f"invocation {invocation} logged {len(found)} loads"}
    if found:
        # A device this reader could not parse is no device at all, and two
        # of them would otherwise compare equal across the halves.
        if any("unreadable" in d for d in found[-1]):
            return {"unreadable": f"the load named a device this reader cannot parse: {found[-1]}"}
        return {"devices": found[-1], "complete": groups["complete"][-1]}
    return {"devices": [], "note": "the load named no CUDA device"}


def load_devices(cfg, tries=15, pause=0.2):
    """The devices the load that now stands bound, read by its unit's
    invocation, and that invocation (#716 round five). Retried briefly,
    since journald can trail the load it records, and **accepted only once
    the block is complete**, the engine's next line seen after it: a block
    of several cards can reach the journal a line at a time, and a read
    taken between two lines would record the first card alone. Answers the
    reading, a `devices` list or an `unreadable` note, and the invocation
    or None."""
    invocation = unit_invocation(cfg)
    if not isinstance(invocation, str):
        return invocation, None
    seen = None
    for _ in range(tries):
        seen = serving_device(cfg, None, invocation)
        if isinstance(seen, dict) and seen.get("devices") and seen.get("complete"):
            return seen, invocation
        time.sleep(pause)
    if isinstance(seen, dict) and seen.get("devices"):
        return {"unreadable": f"the device block under invocation {invocation} did not complete"
                              f" within {tries} reads: {json.dumps(seen['devices'])}"}, invocation
    return seen, invocation


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


def _device_groups(cfg, since, invocation=None):
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
    if invocation is not None:
        base = ["journalctl", f"_SYSTEMD_INVOCATION_ID={invocation}", "--no-pager", "-o", "cat"]
    # Grepped in the journal rather than in this process: an unfiltered read
    # spans every load in the window and llama.cpp is verbose.
    r = sh(base + ["-g", "ggml_cuda_init: found|using device CUDA|llama_model_loader: loaded meta data"])
    if r.returncode not in (0, 1):
        return {"unreadable": f"journalctl exit {r.returncode}: "
                              f"{r.stderr.strip()[:200]}"}
    groups, complete, current, done = [], [], None, False
    for line in r.stdout.splitlines():
        if LOAD_BOUNDARY.search(line):
            if current is not None:
                groups.append(current)
                complete.append(done)
            current, done = [], False
            continue
        # The block's end, which journald can deliver after the device lines
        # it follows, and a device line after it undoes it.
        if LOAD_COMPLETE.search(line):
            if current is None:
                current = []
            done = True
            continue
        # **No evidence is dropped** (#716 round three). A device line met
        # before any boundary is a load whose boundary fell before the
        # window, and it opens its own group rather than vanishing. A line
        # the grep matched and this pattern cannot read is kept as an
        # unreadable device, and a load that named no device keeps its empty
        # group, so either leaves the binding unheld rather than unread.
        if current is None:
            current = []
        done = False
        m = DEVICE_LINE.search(line)
        if m:
            current.append({"ordinal": int(m.group(1)),
                            "name": m.group(2),
                            "pci_bus_id": m.group(3)})
        else:
            current.append({"unreadable": f"a device line this reader cannot parse: {line[:200]}"})
    if current is not None:
        groups.append(current)
        complete.append(done)
    if groups:
        return {"groups": groups, "complete": complete}
    # No match. Distinguish a journal this user cannot read from a load that
    # genuinely bound no CUDA device, by asking whether the unit logged
    # anything at all. Paid only in the empty case.
    probe = sh(base + ["-n", "1"])
    if probe.returncode != 0 or not probe.stdout.strip():
        return {"unreadable": "the unit's journal read back empty; this user "
                              "is likely in neither systemd-journal nor adm"}
    return {"groups": [], "complete": []}


# **The declaration is read as the TOML document it is** (#716 round five,
# carried to TOML with weaver-types-Spec section 2's ruling of 2026-09-28).
# The value was once taken as source text, so a quoted path kept its quotes
# and an inline comment hid the key. The stdlib's `tomllib` reads the whole
# document, and each value is taken at its one path: a key of the same name
# in another table is not it, and a document that does not parse is refused
# by name.
SEED_PATH = ("spu-instruction", "decoder", "tunable-values", "seed")
ARTIFACT_PATH = ("spu-instruction", "decoder", "model-binding", "artifact")
# **A rewrite touches one value's text and nothing else**, so the comments
# and the layout of the operator's file survive byte for byte. The value is
# found by where it sits in the document, not by what the text around it looks
# like: `value_sites` reads the declaration token by token, skipping every
# string and every comment, follows the table headers, the dotted keys, the
# inline tables and the arrays, and names each scalar value by its full key
# path. Text shaped like `artifact = "..."` inside an identity string, or
# `seed = 9` inside a comment, is part of a string or a comment and names
# nothing. A site found this way is still not trusted to be the value at the
# path: the rewrite is reparsed and must differ from the original document at
# that path alone.
ARRAY = "[]"


def toml_tokens(text):
    """The declaration's tokens, each (kind, start, end): `str` for any of the
    four string forms, `word` for a run a bare key, number, boolean or date
    is spelled with, `nl` for a line end, and the punctuation `[ ] { } , =`
    as itself. Comments and horizontal whitespace are skipped. A string that
    does not close raises, since the document then does not parse either."""
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r":
            i += 1
        elif c == "\n":
            tokens.append(("nl", i, i + 1))
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "[]{},=":
            tokens.append((c, i, i + 1))
            i += 1
        elif c in "\"'":
            quote, start = c, i
            if text.startswith(quote * 3, i):
                i += 3
                while True:
                    j = text.find(quote * 3, i)
                    if j < 0:
                        raise ValueError("a multiline string in the declaration does not close")
                    backslashes = len(text[i:j]) - len(text[i:j].rstrip("\\")) if quote == '"' else 0
                    if backslashes % 2:
                        i = j + 1
                        continue
                    i = j + 3
                    while i < n and text[i] == quote and i < j + 5:
                        i += 1
                    break
            else:
                i += 1
                while i < n and text[i] != quote and text[i] != "\n":
                    i += 2 if quote == '"' and text[i] == "\\" else 1
                if i >= n or text[i] != quote:
                    raise ValueError("a string in the declaration does not close on its line")
                i += 1
            tokens.append(("str", start, i))
        else:
            start = i
            while i < n and text[i] not in " \t\r\n#[]{},=\"'":
                i += 1
            tokens.append(("word", start, i))
    return tokens


def value_sites(text):
    """Every scalar value in the declaration, as {key path: [(start, end)]},
    the path a tuple of keys with `ARRAY` for an array's element. The
    document is read as TOML reads it, strings and comments included, so
    only a value names a site."""
    tokens = toml_tokens(text)
    sites, i = {}, 0

    def peek(skip_nl=False):
        j = i
        while skip_nl and j < len(tokens) and tokens[j][0] == "nl":
            j += 1
        return j

    def key_part(kind, start, end):
        raw = text[start:end]
        return tomllib.loads(f"k = {raw}")["k"] if kind == "str" else raw

    def parse_key():
        nonlocal i
        parts = []
        while i < len(tokens) and tokens[i][0] in ("word", "str"):
            kind, start, end = tokens[i]
            if kind == "word":
                parts += [p for p in text[start:end].split(".") if p]
            else:
                parts.append(key_part(kind, start, end))
            i += 1
        if not parts:
            raise ValueError("the declaration has a key this reader cannot follow")
        return tuple(parts)

    def parse_value(path):
        nonlocal i
        i = peek(skip_nl=True) if tokens[i][0] == "nl" else i
        kind, start, end = tokens[i]
        if kind == "{":
            i += 1
            while True:
                i = peek(skip_nl=True)
                if tokens[i][0] == "}":
                    i += 1
                    return
                key = parse_key()
                if tokens[i][0] != "=":
                    raise ValueError("the declaration has an inline table this reader cannot follow")
                i += 1
                parse_value(path + key)
                i = peek(skip_nl=True)
                if tokens[i][0] == ",":
                    i += 1
        elif kind == "[":
            i += 1
            while True:
                i = peek(skip_nl=True)
                if tokens[i][0] == "]":
                    i += 1
                    return
                parse_value(path + (ARRAY,))
                i = peek(skip_nl=True)
                if tokens[i][0] == ",":
                    i += 1
        elif kind in ("str", "word"):
            i += 1
            # A date and time spelled with a space is one value in two words.
            while i < len(tokens) and tokens[i][0] == "word":
                end = tokens[i][2]
                i += 1
            sites.setdefault(path, []).append((start, end))
        else:
            raise ValueError("the declaration has a value this reader cannot follow")

    table = ()
    while i < len(tokens):
        kind = tokens[i][0]
        if kind == "nl":
            i += 1
        elif kind == "[":
            array_table = i + 1 < len(tokens) and tokens[i + 1][0] == "["
            i += 2 if array_table else 1
            table = parse_key() + ((ARRAY,) if array_table else ())
            i += 2 if array_table else 1
        else:
            key = parse_key()
            if i >= len(tokens) or tokens[i][0] != "=":
                raise ValueError("the declaration has a line this reader cannot follow")
            i += 1
            parse_value(table + key)
    return sites


# **Every value a run takes is checked against its consumer's domain before
# the run writes or loads anything** (#716 round seven). A value outside it
# otherwise starts a run that fails every session.
# The sampler's seed is a u64 (weaver-spu/src/sampling.rs).
U64_MAX = 2 ** 64 - 1
# A TOML integer is a signed 64-bit value, so the largest seed a declaration
# can carry is below the sampler's range. `tomllib` reads a larger integer
# without complaint where the stack's parser refuses it, so the rewrite holds
# the bound itself.
I64_MAX = 2 ** 63 - 1
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def seed_value(text, where):
    """A seed as the sampler takes it: decimal digits within u64. Anything
    else, a sign, a base prefix, an underscore or a value past u64, is
    refused by name."""
    text = text.strip()
    if re.fullmatch(r"[0-9]+", text) is None:
        raise ValueError(f"{where} {text!r} is not a decimal integer")
    value = int(text)
    if value > U64_MAX:
        raise ValueError(f"{where} {value} is past the sampler's u64 range, 0 to {U64_MAX}")
    return value


# **A decoded record value is compared by its type as well as its value**
# (#716 round nine). Python's `==` takes 1, 1.0 and true for one value, so a
# seed recorded as true matched a declared 1, and a replay recording 1.0
# where its source recorded 1 read as a reproduction.
def recorded_seed(value, where):
    """A seed as a record carries it: an integer within the sampler's u64,
    never a boolean or a float, refused by name before any comparison."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
        raise ValueError(f"{where} {canonical(value)} is not an integer within the sampler's u64")
    return value


def canonical(value):
    """Decoded JSON as canonical text, which is what two record values are
    compared by: equal only where they are the same JSON."""
    return json.dumps(value, sort_keys=True)


def declaration_document(declaration, what="declaration"):
    """The declaration parsed as TOML 1.0, or the refusal naming why not.
    Declarations are written in the TOML 1.0 grammar, the subset every reader
    in the suite shares, per weaver-types-Spec section 2, and tomllib reads
    exactly that, so a file using TOML 1.1 syntax admin's parser also takes is
    diagnosed here rather than refused without a reason."""
    try:
        return tomllib.loads(declaration)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"the {what} is not a TOML 1.0 document, the grammar every"
                         f" reader in the suite shares (weaver-types-Spec section 2): {e}") from None


def declared_value(document, path):
    """The value at `path` in a parsed declaration, or the refusal naming the
    first key it lacks."""
    node = document
    for depth, key in enumerate(path):
        if not isinstance(node, dict):
            raise ValueError(f"the declaration's {'.'.join(path[:depth])} is not a table")
        if key not in node:
            raise ValueError(f"the declaration carries no {'.'.join(path[:depth + 1])}")
        node = node[key]
    return node


def declaration_seed(declaration):
    """The one seed the declaration holds, at spu-instruction.decoder.
    tunable-values.seed, read as a TOML integer and held to the range a
    declaration carries, whichever caller reads it (#716 round eight). A boolean, a float or
    a string is refused by name, a quoted number included."""
    value = declared_value(declaration_document(declaration), SEED_PATH)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"the declaration's seed {value!r} is a TOML"
                         f" {type(value).__name__}, not an integer")
    # The sampler takes a u64, and the declaration's TOML integer is an i64
    # that the stack's own parser refuses past, so the seed a declaration can
    # carry is the narrower of the two. Python's tomllib reads past i64 where
    # the stack does not, and this reader holds to what the stack loads.
    if not 0 <= value <= I64_MAX:
        raise ValueError(f"the declaration's seed {value} is outside what the declaration"
                         f" carries, 0 to {I64_MAX}, the sampler's u64 narrowed by TOML's i64")
    return value


def rewrite_site(declaration, path, value, text, what):
    """The declaration with the one value at `path` replaced by `text`, every
    other byte kept. Refused by name where the declaration does not parse,
    where it carries other than one value at the path, or where the rewrite
    does not read back `value` at `path` with the rest of the document
    unchanged."""
    before = declaration_document(declaration)
    found = value_sites(declaration).get(tuple(path), [])
    if len(found) != 1:
        raise ValueError(f"the declaration carries {len(found)} {what} sites, not one")
    start, end = found[0]
    swapped = declaration[:start] + text + declaration[end:]
    after = declaration_document(swapped, f"declaration rewritten with {what} {text}")
    try:
        declared_value(before, path)
        read = declared_value(after, path)
    except ValueError as e:
        raise ValueError(f"the {what} site the rewrite found is not the declared {what}: {e}") from None
    expected = copy.deepcopy(before)
    node = expected
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    if (type(read) is not type(value) or read != value
            or after != expected):
        raise ValueError(f"the rewritten declaration does not read back {what} {value!r}"
                         " with the rest of the document unchanged")
    return swapped


# The config keys a run reads, and the optional ones. A key is a value or
# absent: an empty string reads as neither, and a test of its truth would
# take it for absent and guess in its place (#716 round eight). A cells run
# also reads `cells`, checked by `cells_values`.
CONFIG_KEYS = ("agent", "declaration", "gate_socket", "trace", "admin_bin", "admin_config", "repo")
OPTIONAL_KEYS = ("loop_sha256", "build_flags")
# Keys a config may not carry, each with why. `spu_bin` named an SPU for the
# harness to hash while the admin launches the one its configuration names,
# so the two could differ and the run hash the one that did not serve
# (#716, the pass on 90b9a8a).
REFUSED_KEYS = {"spu_bin": "the admin launches the SPU its configuration names,"
                           " admin_config/spu-binary, and the run reads it there"}
# **A path the stack resolves is absolute** (#716 round ten). The worker and
# the admin's units resolve a relative path against their own working
# directory and this harness against its launch directory, so one spelling
# names two files, and the run records the bytes of the one it opened while
# the stack serves the other. These keys name what the stack reads or
# writes: its trace, its gate socket and the admin's configuration.
STACK_PATH_KEYS = ("trace", "gate_socket", "admin_config")


def stack_path(path, what):
    """`path` where it is absolute, or the refusal naming it."""
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError(f"the {what} {path!r} is not an absolute path, and the stack"
                         " resolves a relative one against its own directory")
    return path


def config_values(cfg, required=CONFIG_KEYS):
    """Every required key a non-empty string, every optional key, where
    present, the same, and no refused key present, refused by name at
    preflight."""
    for key, why in REFUSED_KEYS.items():
        if key in cfg:
            raise ValueError(f"the config's {key} is refused: {why}")
    for key in required:
        if not isinstance(cfg.get(key), str) or not cfg[key]:
            raise ValueError(f"the config's {key} {cfg.get(key)!r} is not a non-empty string")
    for key in OPTIONAL_KEYS:
        if key in cfg and (not isinstance(cfg[key], str) or not cfg[key]):
            raise ValueError(f"the config's optional {key} {cfg[key]!r} is present and empty or not a string")
    for key in STACK_PATH_KEYS:
        if key in cfg:
            stack_path(cfg[key], f"config's {key}")
    return cfg


def loop_digest(cfg):
    """The config's `loop_sha256`, absent or 64 lowercase hex digits: a
    digest of another shape can match no load, and every session would be
    refused at its first load."""
    declared = cfg.get("loop_sha256")
    if declared is not None and (not isinstance(declared, str)
                                 or re.fullmatch(r"[0-9a-f]{64}", declared) is None):
        raise ValueError(f"the config's loop_sha256 {declared!r} is not 64 lowercase hex digits")
    return declared


# **Every file a run opens is opened at preflight** (#716 round nine), as
# every value is checked there, so an unreadable file is refused before the
# outdir stands rather than at its first use after it, which could be every
# session of a seven-hour run.
def read_config(path):
    """The config, a JSON object, or the refusal naming why not."""
    try:
        with open(path) as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"the config {path} cannot be read: {_why(e)}") from None
    if not isinstance(cfg, dict):
        raise ValueError(f"the config {path} is not a JSON object")
    return cfg


def cell_values(cell):
    """A cell as the run reads it, its name, precision and artifact each a
    non-empty string, or the refusal naming the key."""
    if not isinstance(cell, dict):
        raise ValueError(f"the config's cell {cell!r} is not an object")
    for key in ("name", "precision", "artifact"):
        if not isinstance(cell.get(key), str) or not cell[key]:
            raise ValueError(f"the cell's {key} {cell.get(key)!r} is not a non-empty string")
    return cell


def cells_values(cfg):
    """A cells run's `cells`: a non-empty list of cells, each checked by
    `cell_values`, whose names are labels a record and the weights reading
    carry, so each is a plain name and none repeats (#716 rounds seven and
    ten)."""
    cells = cfg.get("cells")
    if not isinstance(cells, list) or not cells:
        raise ValueError(f"the config's cells {cells!r} is not a non-empty list")
    for c in cells:
        cell_values(c)
        if SAFE_NAME.fullmatch(c["name"]) is None:
            raise ValueError(f"the cell name {c['name']!r} is not a plain name")
    names = [c["name"] for c in cells]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise ValueError(f"the cell names {repeated} repeat, and each cell's record and"
                         " weights reading carry its name")
    return cells


def openable(path, what, mode="rb"):
    """`path` opened as the run will open it and closed again, nothing read
    or written, or the refusal naming why it cannot be."""
    try:
        with open(path, mode):
            pass
    except OSError as e:
        raise ValueError(f"the {what} {path} cannot be opened: {_why(e)}") from None


def run_files(cfg, rewrites):
    """The files a run opens outside its provenance readings, each checked
    as the run will use it, and the declaration's text. The declaration is
    read, and where the run rewrites it, opened for writing with its
    backup's directory writable. The admin binary is a regular file with an
    execute bit, since it runs under `sudo`, and the repository is a
    directory. The trace and the gate socket stand only once a load has, and
    each is awaited where it is read. Answers the declaration's bytes, which
    the run keeps and holds the disk to."""
    decl = cfg["declaration"]
    openable(decl, "declaration", "r+b" if rewrites else "rb")
    directory = os.path.dirname(os.path.abspath(decl))
    if rewrites and not os.access(directory, os.W_OK | os.X_OK):
        raise ValueError(f"the declaration's directory {directory} is not writable,"
                         " and the run keeps its backup there")
    try:
        st = os.stat(cfg["admin_bin"])
    except OSError as e:
        raise ValueError(f"the config's admin_bin {cfg['admin_bin']} cannot be read: {_why(e)}") from None
    if not stat.S_ISREG(st.st_mode) or not st.st_mode & 0o111:
        raise ValueError(f"the config's admin_bin {cfg['admin_bin']} is not an executable file")
    if not os.path.isdir(cfg["repo"]):
        raise ValueError(f"the config's repo {cfg['repo']} is not a directory")
    with open(decl, "rb") as f:
        held = f.read()
    declaration_document(held.decode("utf-8", "replace"), f"declaration {decl}")
    return held


def held_declaration(cfg, held):
    """The declaration on disk is still the bytes the run read at preflight,
    or the refusal (#716 round eleven). The run keeps what it read and holds
    the disk to it, never re-reading and trusting the file."""
    if _sha256(cfg["declaration"]) != hashlib.sha256(held).hexdigest():
        raise ValueError(f"the declaration {cfg['declaration']} changed on disk after the"
                         " run read it at preflight")


def opening_readings(cfg):
    """The stack as the run opens, read at preflight:
    the SPU resolved once for both collectors, the engine libraries, the
    binaries and the toolchain. Every file the run reads for provenance is
    opened here, the admin configuration's entries, the binaries they name,
    the SPU and each library it links. A reading the exit could never count
    held, one that is not a reading or that resolved a binary by a guess, is
    refused by name."""
    spu = _resolve_spu(cfg)
    readings = {"engine_libraries": engine_libraries(cfg, spu),
                "weaver_binaries": weaver_binaries(cfg, spu),
                "toolchain": toolchain(cfg)}
    for field, reading in readings.items():
        if not is_reading(reading):
            raise ValueError(f"the opening {field} is not a reading: {json.dumps(reading)}")
        if guessed(reading):
            raise ValueError(f"the opening {field} resolved a binary by a guess,"
                             f" which the exit never counts held: {json.dumps(reading)}")
    return readings


def declared_artifact(declaration):
    """The one artifact the declaration binds, at spu-instruction.decoder.
    model-binding.artifact, read as a TOML string and held to an absolute
    path, since the worker resolves it."""
    value = declared_value(declaration_document(declaration), ARTIFACT_PATH)
    if not isinstance(value, str):
        raise ValueError(f"the declaration's artifact {value!r} is a TOML"
                         f" {type(value).__name__}, not a string")
    return stack_path(value, "declaration's artifact")


def with_artifact(declaration, path):
    """The declaration with its one artifact line set to `path`, written as a
    TOML basic string, which a JSON string literal is. A declaration without
    exactly one artifact site is refused, the old rewrite's `\\s*` having
    once run past a line end into the next key, as is a rewrite that does not
    read back `path` with the rest unchanged. The path is absolute, since the
    worker resolves it."""
    stack_path(path, "artifact path")
    return rewrite_site(declaration, ARTIFACT_PATH, path,
                        json.dumps(path, ensure_ascii=False), "artifact")


def spu_binary(cfg):
    """The SPU binary path, from the authority that already holds it.

    `weaver-admin` reads `spu-binary` from its config directory, required
    rather than defaulted, on the stated ground that a missing one refuses
    and names itself rather than being searched for
    (`weaver-admin/src/main.rs`, per Spec section 9). Guessing it beside
    `admin_bin` would re-introduce the search that rule exists to forbid,
    and the crate's own default is `/usr/libexec/weaver-spu` while the
    deploy material uses `/usr/local/libexec/weaver/`, so the two are not
    reliably co-located. The admin configuration is the one source, the
    config's own `spu_bin` override being refused (#716, the pass on
    90b9a8a), and the sibling guess stands only where the config names no
    admin configuration at all, which preflight refuses too.
    """
    return _resolve_spu(cfg)[0]


def _resolve_spu(cfg):
    """The SPU path and how it was arrived at.

    **The source travels because the last resort is a guess.** With no admin
    configuration named, the other two binaries record `unreadable` naming its
    absence, while this one falls back beside `admin_bin` - and a stale binary
    from an older deploy sitting there would be hashed confidently under the
    field whose whole purpose is to say whether two boxes run one build. With
    one named, nothing falls back: `spu-binary` is required there as admin
    requires it.
    """
    # **Skipped rather than joined against nothing.** `os.path.join("", name)`
    # is a bare relative name read against the launch directory, so a file
    # called `spu-binary` sitting there would be taken for the admin config
    # and reported as an authoritative reading - a cwd artifact wearing the
    # source that the `resolved_by` marker suppresses.
    directory = cfg.get("admin_config")
    if directory:
        # **The agent's own SPU first**, per weaver-admin-Spec section 9: where
        # `agent-spu` names the run's agent, the key it gives chooses the path
        # in `spu-implementations`, and `spu-binary` stands only where the map
        # does not name the agent. A map this reader cannot follow is reported
        # rather than passed over, admin itself failing every verb on it.
        chosen = _agent_spu(directory, cfg.get("agent"))
        if chosen is not None:
            return chosen
        stated = os.path.join(directory, "spu-binary")
        text, why = _read_admin(directory, "spu-binary")
        # **Nothing falls through to the guess once the directory is named.**
        # `spu-binary` is required, so its absence is admin refusing every
        # verb, and a file that stands and does not read, or names no path, is
        # an unreadable resolution the exit gates, never the guess beside
        # `admin_bin` standing in for what admin launches.
        if why is not None:
            return None, why
        named = _trim(text)
        if not named:
            return None, f"{stated} names no path"
        # A relative path is refused rather than resolved here, the stack
        # resolving it against another directory (#716 round ten).
        if not os.path.isabs(named):
            return None, f"{stated} names a relative path {named!r}"
        return named, "admin config spu-binary"
    admin_bin = cfg.get("admin_bin")
    if not admin_bin:
        # `.get`, as `toolchain` uses beside it: a config omitting this raised
        # `KeyError` here, and this reader runs before the `try` that restores
        # the operator's declaration.
        return None, "the config names neither admin_config nor admin_bin"
    return (
        os.path.join(os.path.dirname(admin_bin), "weaver-spu"),
        "guessed beside admin_bin, the admin config naming none",
    )


# **Admin's class of every file this module reads**, as `load_service_config_from`
# in `crates/weaver-admin/src/main.rs` classes it: required ones through its
# `read`, whose absence refuses every verb, and optional ones through its
# `optional`, whose absence stands a default. A name in neither is refused by
# `_read_admin`, so a new reader classes its file before it can read it.
_ADMIN_REQUIRED = ("allow-list", "worker-binary", "spu-binary", "gate-binary")
_ADMIN_OPTIONAL = ("spu-implementations", "agent-spu")


def _read_admin(directory, name):
    """A value of admin's configuration, as `(text, None)`, `(None, None)` where
    an optional file is absent, or `(None, why)` where something stands and does
    not read or a required file is absent, per weaver-admin-Spec section 9.

    **A required file's absence is a failure, never an absence**, admin's loader
    refusing every verb without it: reading it as absent passed a preflight on a
    configuration admin launches nothing on (#734, the pass on 9d1853a).

    **Presence is `lstat`'s answer and nothing else's.** Only nothing at the path
    is absence: a dangling link, a directory, a file this process may not read,
    or bytes that are not UTF-8 stand there and fail, since reading any of them as
    absent would stand a default admin does not launch. `os.path.exists` is not
    used, Python 3.14 answering False for a path it may not look at.
    """
    if name not in _ADMIN_REQUIRED + _ADMIN_OPTIONAL:
        raise ValueError(f"{name} is not classed as admin's loader classes it")
    path = os.path.join(directory, name)
    try:
        os.lstat(path)
    except FileNotFoundError:
        if name in _ADMIN_REQUIRED:
            return None, f"{path}: absent, and admin requires it"
        return None, None
    except OSError as e:
        return None, f"{path}: {_why(e)}"
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(), None
    except (OSError, UnicodeDecodeError) as e:
        return None, f"{path}: {_why(e)}"


_KEY = re.compile(r"[a-z0-9-]+")

# Rust's `char::is_whitespace`, which `trim`, `split_whitespace` and admin's
# every read use. Python's `str.strip` and `str.split` also take \x1c-\x1f,
# which Rust does not, so they are not used where admin's reading is mirrored.
_WS = "\t\n\x0b\x0c\r \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000"
_WHITESPACE = re.compile(f"[{_WS}]+")
_EDGES = re.compile(f"^[{_WS}]+|[{_WS}]+$")


def _trim(text):
    """`str::trim`."""
    return _EDGES.sub("", text)


def _lines(text):
    """Admin's `lines` in `spu_choice.rs` and its allow-list reading: `str::lines`,
    each trimmed, blank ones dropped, numbered from one."""
    for number, line in enumerate(text.split("\n"), 1):
        line = _trim(line)
        if line:
            yield number, line


def _judge_spu_map(directory):
    """Admin's section 9 judgment of its SPU map, rule for rule
    (`crates/weaver-admin/src/spu_choice.rs`), as `(agents, implementations,
    None)` or `(None, None, why)`.

    **Judged whole on every call, before any default is taken**, as admin judges
    it before any verb: a map admin would refuse is an unreadable resolution here,
    whether or not it names the run's agent, since admin launches nothing on it.
    The rules, each admin's: a line of two fields in either file, a key of
    lowercase letters, digits and hyphens, an absolute path, no key named twice, an
    agent on the allow-list, a key `spu-implementations` holds, no agent named
    twice, and no file name shared by two binaries the stack records, the worker,
    the state member and the gate pairwise and each SPU against those three.
    """
    # **Admin's order**: the four required files first, each refusing where it
    # is absent, then the two optional maps read, then every line of
    # `spu-implementations` judged before any of `agent-spu`, so the failure
    # named here is the one admin names.
    required = {}
    for name in _ADMIN_REQUIRED:
        text, why = _read_admin(directory, name)
        if why is not None:
            return None, None, why
        required[name] = _trim(text)
    texts = {}
    for name in _ADMIN_OPTIONAL:
        text, why = _read_admin(directory, name)
        if why is not None:
            return None, None, why
        texts[name] = _trim(text or "")

    def rows_of(name):
        for number, line in _lines(texts[name]):
            fields = _WHITESPACE.split(line)
            yield number, fields if len(fields) == 2 else None, (
                f"{name} line {number}: expected two fields")

    chosen = {}
    for number, fields, malformed in rows_of("spu-implementations"):
        if fields is None:
            return None, None, malformed
        key, path = fields
        if not _KEY.fullmatch(key):
            return None, None, f"spu-implementations line {number}: the key {key!r} is not lowercase letters, digits and hyphens"
        if not os.path.isabs(path):
            return None, None, f"spu-implementations line {number}: the path {path!r} is not absolute"
        if key in chosen:
            return None, None, f"spu-implementations line {number}: the key {key!r} is named twice"
        chosen[key] = path
    allowed = {line for _, line in _lines(required["allow-list"])}
    agents = {}
    for number, fields, malformed in rows_of("agent-spu"):
        if fields is None:
            return None, None, malformed
        agent, key = fields
        if agent not in allowed:
            return None, None, f"agent-spu line {number}: the agent {agent!r} is not on the allow-list"
        if key not in chosen:
            return None, None, f"agent-spu line {number}: the key {key!r} is not in spu-implementations"
        if agent in agents:
            return None, None, f"agent-spu line {number}: the agent {agent!r} is named twice"
        agents[agent] = key
    fixed = [("the worker", _file_name(required["worker-binary"])),
             ("the state member", "weaver-state"),
             ("the gate", _file_name(required["gate-binary"]))]
    for i, (one, name) in enumerate(fixed):
        for other, other_name in fixed[i + 1:]:
            if name == other_name:
                return None, None, f"{one} and {other} share the file name {name!r}"
    for spu in [required["spu-binary"]] + list(chosen.values()):
        clash = [one for one, name in fixed if name == _file_name(spu)]
        if clash:
            return None, None, f"the SPU binary {spu} shares its file name with {clash[0]}"
    return agents, chosen, None


def _file_name(path):
    """A path's file name as Rust's `Path::file_name` answers it, the empty
    string where that answers None: the last component after separators
    repeated or trailing and `.` components are dropped, and none where it is
    `..` or the root. `os.path.basename` answers "" for a trailing separator,
    where admin keys the stack by the name before it."""
    parts = [p for p in path.split("/") if p not in ("", ".")]
    return parts[-1] if parts and parts[-1] != ".." else ""


def _agent_spu(directory, agent):
    """The SPU `agent-spu` chooses for the agent, as `_resolve_spu`'s pair, or
    None where the map does not name the agent, the whole map having been judged
    first as admin judges it."""
    agents, chosen, why = _judge_spu_map(directory)
    if why is not None:
        return None, why
    if agent not in agents:
        return None
    key = agents[agent]
    return chosen[key], f"admin config agent-spu key {key}"


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
    return, closing as `at_close_unreadable` instead of as a lost run. An
    interrupt is not caught here: it reaches the caller's guarded close,
    which marks the run interrupted (#716, after the fold).
    """
    try:
        return _resolve_spu(cfg), None
    except Exception as e:  # noqa: BLE001
        return None, {"unreadable": f"the SPU resolution raised: {_why(e)}"}


def provenance_close(cfg, reader, at_start, what, essence=None):
    """Read again at the close and say how the two readings relate.

    Lifted from the matrix driver per #379: `close()` and its helpers were
    local to `determinism_matrix.main` while this file's own driver, folded
    into the matrix since, compared with a raw
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
    # An ordinary failure degrades to a note. An interrupt is not caught
    # here: it reaches the caller's guarded close, which marks the run
    # interrupted (#716, after the fold).
    try:
        at_close = reader(cfg)
    except Exception as e:  # noqa: BLE001
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


def weights(paths):
    """A provenance reader for the weights field: each artifact by sha256, or
    a note saying why it could not be read, read at the two ends of the
    run's window. One path is keyed `artifact`, as every earlier summary
    keys it, and a mapping keys each artifact by its name, a cells run by
    the cell's."""
    named = {"artifact": paths} if isinstance(paths, str) else dict(paths)

    def read(cfg):
        out = {}
        for key, path in named.items():
            try:
                out[key] = {"path": path, "sha256": _sha256(path)}
            except OSError as e:
                out[key] = {"path": path, "unreadable": _why(e)}
        return out
    return read


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
        # **The SPU goes through its own resolver**, which reads the admin
        # configuration and falls back beside `admin_bin` only where none is
        # named, a guess preflight refuses.
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
            text, why = _read_admin(directory, key)
            if why is not None or text is None:
                out[key] = {"path": None, "sha256": None,
                            "unreadable": why or f"{stated}: absent"}
                continue
            path = _trim(text)
            # An empty config file is an unset value, not a binary at the
            # empty path, and `_sha256("")` would report it as a missing file.
            if not path:
                out[key] = {"path": None, "sha256": None,
                            "unreadable": f"{stated}: names no path"}
                continue
            # The admin launches this path, and a relative one resolves
            # against its unit's directory, not this process's (#716 round
            # ten).
            if not os.path.isabs(path):
                out[key] = {"path": path, "sha256": None,
                            "unreadable": f"{stated}: names a relative path"}
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


def _stat_spu(path):
    """The SPU binary's presence, by `os.stat`: FileNotFoundError where nothing
    stands, another OSError where something stands and may not be looked at. One
    function, so a test fixing the SPU's presence replaces this and not
    `os.stat` for the whole process."""
    os.stat(path)


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
    # `os.stat` and not `os.path.exists`, which reads a path this process may not
    # look at as absent on Python 3.14: nothing there and there-but-unreadable
    # are two findings and each names itself.
    try:
        _stat_spu(spu)
    except FileNotFoundError:
        return {"unreadable": f"no SPU binary at {spu}"}
    except OSError as e:
        return {"unreadable": f"the SPU binary at {spu} does not stat: {_why(e)}"}
    r = sh(["ldd", spu])
    if r.returncode != 0:
        return {"unreadable": f"ldd exit {r.returncode} on {spu}: "
                              f"{r.stderr.strip()[:200]}"}
    out = {}
    for line in r.stdout.splitlines():
        # The path runs to ldd's load address, not to the first space, so a
        # path holding a space is read whole rather than cut (#716 round five).
        m = re.search(r"(lib(?:ggml[\w-]*|llama)\.so[\w.]*)\s+=>\s+(.+?)(?:\s+\(0x[0-9a-fA-F]+\))?\s*$", line)
        if not m:
            # A line naming an engine library that this pattern cannot read
            # is unreadable evidence, kept as such (#716 round three).
            if re.search(r"lib(?:ggml|llama)", line):
                out[f"unparsed: {line.strip()[:120]}"] = {
                    "path": None, "sha256": None,
                    "unreadable": "ldd named an engine library this reader cannot parse"}
            continue
        name, path = m.group(1), m.group(2)
        # `ldd` prints `=> not found` for an unresolved library, whose
        # second field is the bare word `not`. Recorded as unresolved
        # rather than hashed as a path, and any other path that is not
        # absolute is unreadable too, never resolved against this process's
        # directory (#716 round ten).
        if not path.startswith("/"):
            out[name] = {"path": None, "sha256": None,
                         "unreadable": "ldd reports it not found" if path.startswith("not found")
                         else f"ldd names a path that is not absolute: {path}"}
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
    """The admin's answer to `verb`, its last stdout line as a JSON object,
    with the process's exit status beside it as `exit` (#716 round twelve).
    The admin prints its answer and exits 0, or prints its refusal and exits
    1 (`weaver-admin/src/surface.rs`), and an answer is read only where the
    two agree, by `admin_answered`."""
    r = sh(["sudo", "-n", f"WEAVER_ADMIN_CONFIG={cfg['admin_config']}",
            cfg["admin_bin"], verb, cfg["agent"]])
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        answer = json.loads(line)
    except json.JSONDecodeError:
        answer = None
    if not isinstance(answer, dict):
        return {"kind": "unparsed", "stdout": r.stdout, "stderr": r.stderr,
                "exit": r.returncode}
    return dict(answer, exit=r.returncode)


def admin_answered(answer, states=(), refusals=()):
    """True where the admin's answer is one this step accepts: exit 0 with a
    `state` answer in `states`, or exit 1 with a refusal whose kind is in
    `refusals`. A load answers `idle` and an unload `unloaded`
    (`weaver-admin/src/main.rs`), and a kind the exit status does not bear
    out is no answer (#716 round twelve)."""
    if not isinstance(answer, dict):
        return False
    if answer.get("exit") == 0 and answer.get("kind") == "state":
        return answer.get("state") in states
    return answer.get("exit") == 1 and answer.get("kind") in refusals


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


def run_named(value):
    """True where `value` names a run as the trace and the gate name one: a
    non-empty string (#716 round nine)."""
    return isinstance(value, str) and bool(value)


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
        # A run is named by a string. An event naming anything else is of
        # no run the harness can name, and as keys 1 and true are one run.
        if not run_named(r):
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
                if run_named(r) and r not in seen:
                    seen.append(r)
                    # One past `keep`: the `keep`th run is whole only once a
                    # newer boundary has been crossed.
                    if len(seen) > keep:
                        done = True
                        break
        if not done and held.strip():
            out.append(held)
    return [raw.decode("utf-8", "replace") for raw in reversed(out)]


def run_load(trace_path, run, keep=4):
    """The `load` event of `run`, or None where the trace does not hold one,
    or does not exist.

    **A load is read by its run, never as the newest** (#716, the pass on
    26b93db). The newest load event after a snapshot is whichever the sink
    wrote next, and a sink trailing its writer can hand back the previous
    load's. The run is the identity: the gate's closes name the run a half's
    turns were served in, and its load event is that load's.
    """
    try:
        _, runs = read_runs(trace_path, keep=keep)
    except OSError:
        return None
    return next((e for e in runs.get(run, []) if e.get("kind") == "load"), None)


def assert_loop(cfg, event, run):
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
    declared. `event` is the load event of `run`, the run the half's turns
    were served in, read by `load_held`, and None where none reached the
    trace, which cannot be shown to be the declared loop either.
    """
    declared = cfg.get("loop_sha256")
    if declared is None:
        return None
    if event is None:
        return {"declared": declared, "recorded": None, "run": run, "composer": None,
                "note": f"no load event for run {run} reached the trace, so the loop"
                        " cannot be shown to be the declared one"}
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


def load_held(cfg, run, declaration_sha, half, rec, log=None, timeout=15.0):
    """The loop that composed a half's load and the declaration it served
    are the session's, read from the load event of `run`, the run the half's
    gate closes named (#716, the pass on 26b93db). The loop is checked by
    `assert_loop` against the config's `loop_sha256`. The declaration is
    checked by the digest the load event records, which is the declaration
    file's sha256, so the artifact path, the seed, the sampling knobs and
    every other declared field are held per load. The event is awaited,
    since the sink writes behind the close, and its absence is a fault.
    Answers True where both hold, and otherwise sets the verdict and answers
    False. Every load a session makes is held here, one way (#716 rounds two
    and six)."""
    if cfg.get("loop_sha256") is None and declaration_sha is None:
        return True
    end, delay = time.time() + timeout, 0.02
    event = run_load(cfg["trace"], run)
    while event is None and time.time() < end:
        time.sleep(delay)
        delay = min(delay * 1.5, 1.0)
        event = run_load(cfg["trace"], run)
    refused = assert_loop(cfg, event, run)
    if refused:
        loop_refusal(rec, refused, half, log or (lambda m: None))
        return False
    if declaration_sha is None:
        return True
    if event is None:
        rec["verdict"] = f"no load event reached the trace for the {half} run {run}"
        return False
    served = (event.get("payload") or {}).get("declaration")
    if served != declaration_sha:
        rec["verdict"] = (f"the {half} load served another declaration:"
                          f" declared {declaration_sha}, served {served}")
        return False
    return True


# The verdict of a session an interrupt cut short, on which both loops stop.
INTERRUPTED = "interrupted"


def verify_session(cfg, texts, rec, declared_seed, declaration_sha,
                   step=None, log=None, turn_timeout=600, declaration=None):
    """**The one session verification**: the matrix's `run_session` calls
    it for every session, a matrix cell or a cell of the cross-precision
    protocol, and verifies nothing outside it (#716 round eight). Three
    checks the matrix made had each gone missing from a standalone path in
    turn, the declaration digest, then the recorded seed, and one function,
    and since the fold one entry point, is what stops a fourth.

    It serves `texts`, unloads, reloads, reissues the turns from the record
    and compares them. It holds each half's load to the session's
    declaration, loop and device, the recorded seed to `declared_seed`, the
    replay's seed to the source's, absence as a named fault, and every
    CHECKS field. It sets `rec["verdict"]`, a named fault or REPRODUCED or
    DIVERGED, and the run, seed, device and invocation fields it read, and
    answers the compared turns as `(source, replay, checks)` with the
    evidence the caller deposits or records.

    `declaration`, where given, is written to the declaration file before
    the first load, and its digest is the one both loads are held to.
    **Every exception is a verdict here, on both paths** (#716 round ten): a
    raise is the apparatus fault `error: <type>: <message>`, and an interrupt
    is the fault `interrupted`, on which the caller's loop stops. The agent
    is unloaded whichever way it leaves, and a raise from that unload is
    recorded the same way."""
    step = step or (lambda verb: admin(cfg, verb))
    log = log or (lambda m: None)
    pairs = []
    evidence = {"source_events": [], "replay_events": [], "source_read": None, "replay_read": None}

    def fault(message):
        rec["verdict"] = message
        log(message)
        return pairs, evidence

    def hold_load(half):
        """One half's load: the load itself, its socket, and its device read
        by its own unit invocation. Its declaration and loop are held once
        the half's closes name its run."""
        loaded = step("load")
        if not admin_answered(loaded, states=("idle",)):
            return f"{'load' if half == 'source' else 'reload'} refused: {canonical(loaded)}"
        if not wait_socket(cfg):
            return "gate socket never stood" if half == "source" else "gate socket never stood after reload"
        seen, invocation = load_devices(cfg)
        evidence[f"{half}_read"] = seen
        log(f"{half} devices: {json.dumps(seen)}")
        if invocation is None:
            return f"the {half} load's unit invocation could not be read: {json.dumps(seen)}"
        if not (isinstance(seen, dict) and seen.get("devices")):
            return (f"the {half} load's serving device could not be read under"
                    f" invocation {invocation}: {json.dumps(seen)}")
        return seen["devices"], invocation

    def seed_of(turns, half):
        """The one seed `turns` were recorded under and no fault, or what
        they carry and the fault. Each seed is held to the sampler's u64
        before any comparison, so true cannot stand for 1."""
        seeds = []
        for t in turns:
            value = pointer(t["payload"]["model.request"], "/sampling/seed")
            if value is not None:
                try:
                    recorded_seed(value, f"the {half} {t['turn']} recorded seed")
                except ValueError as e:
                    return value, str(e)
            if value not in seeds:
                seeds.append(value)
        if len(seeds) > 1:
            return seeds, f"the {half} turns were recorded under {len(seeds)} seeds: {seeds}"
        if seeds in ([], [None]):
            return None, f"the {half} turns carry no recorded seed"
        return seeds[0], None

    try:
        # The loads are held to the digest of the bytes written, never to a
        # read of the file back (#716 round eleven).
        if declaration is not None:
            data = declaration.encode()
            with open(cfg["declaration"], "wb") as fh:
                fh.write(data)
            declaration_sha = hashlib.sha256(data).hexdigest()
        # Whatever held the device before this session: nothing resident is
        # as good as unloaded here, and anything else is not a clean start.
        opened = step("unload")
        if not admin_answered(opened, states=("unloaded",), refusals=("no_residency",)):
            return fault(f"the opening unload was refused: {canonical(opened)}")
        held = hold_load("source")
        if isinstance(held, str):
            return fault(held)
        source_devices, source_invocation = held

        log("serving the source turns")
        source_runs = []
        for text in texts:
            close = gate_turn(cfg, text, timeout=turn_timeout)
            if close.get("kind") != "answered":
                return fault(f"source turn not answered: {close.get('kind')}")
            source_runs.append(close.get("run"))
        # The closes name the run, so the wait is on that run rather than on
        # whichever is newest, which the previous session's run can satisfy.
        # A run is named by a string, as the trace names it: anything else
        # names no run, and a set would take 1 and true for one.
        if not all(run_named(r) for r in source_runs) or len(set(source_runs)) != 1:
            return fault("the source turns did not share one run")
        source_run = source_runs[0]
        rec["source_run"] = source_run
        # The load held by its run, the one the closes name, never by
        # whichever load event the sink wrote next.
        if not load_held(cfg, source_run, declaration_sha, "source", rec, log):
            return fault(rec["verdict"])
        source_turns, evidence["source_events"] = await_turns(cfg["trace"], len(texts), source_run)
        if len(source_turns) != len(texts):
            return fault(f"expected {len(texts)} source turns, found {len(source_turns)}")
        broken = next((st for st in source_turns if st["incomplete"]), None)
        if broken:
            return fault(f"source {broken['turn']} is incomplete: {', '.join(broken['incomplete'])}")
        # **The texts served are the texts the record carries** (#716, after
        # the fold): the source's requests, in order and byte-exact, are the
        # session's texts, or the record is of another session, and a replay
        # reissued from it would measure that one under this one's labels.
        for i, (st, text) in enumerate(zip(source_turns, texts), start=1):
            if st["text"] != text:
                return fault(f"source {st['turn']} carries a request other than turn {i} of the"
                             " texts served")
        # **The seed the record carries is read back, never assumed**: one
        # seed, present, and the one the session was declared under.
        recorded, why = seed_of(source_turns, "source")
        rec["recorded_seed"] = recorded
        if why:
            return fault(why)
        if declared_seed is not None and recorded != declared_seed:
            return fault(f"the declared seed did not reach the record:"
                         f" declared {declared_seed}, recorded {recorded}")

        # Unloaded fully, Spec section 3 step 3, or the reload is not cold.
        between = step("unload")
        if not admin_answered(between, states=("unloaded",)):
            return fault(f"the unload between the halves was refused: {canonical(between)}")
        held = hold_load("replay")
        if isinstance(held, str):
            return fault(held)
        replay_devices, replay_invocation = held
        rec["invocations"] = [source_invocation, replay_invocation]
        # The reload is its own unit invocation, or it never happened and the
        # replay's device read is the source's.
        if replay_invocation == source_invocation:
            return fault(f"the reload is the load's own invocation {source_invocation}")
        # Both halves on one binding, or the comparison is across silicon.
        if replay_devices != source_devices:
            return fault(f"source and replay did not bind the same devices:"
                         f" {json.dumps(source_devices)} against {json.dumps(replay_devices)}")
        rec["devices"] = source_devices

        # Reissued from the record rather than from the caller's texts,
        # because the record is the artifact under test.
        log("reissuing from the record")
        runs_seen = []
        for st in source_turns:
            close = gate_turn(cfg, st["text"], timeout=turn_timeout)
            if close.get("kind") != "answered":
                return fault(f"reissue {st['turn']} closed {close.get('kind')}")
            runs_seen.append(close.get("run"))
        if (not all(run_named(r) for r in runs_seen) or len(set(runs_seen)) != 1
                or runs_seen[0] == source_run):
            return fault("reissues did not land in one fresh run")
        replay_run = runs_seen[0]
        rec["replay_run"] = replay_run
        if not load_held(cfg, replay_run, declaration_sha, "replay", rec, log):
            return fault(rec["verdict"])
        replay_all, evidence["replay_events"] = await_turns(cfg["trace"], len(source_turns), replay_run)
        if not replay_all:
            return fault(f"the closes named run {replay_run}, absent from the trace")
        # A short replay read is the sink one turn behind, not the model, and
        # never shares a word with DIVERGED.
        if len(replay_all) < len(source_turns):
            return fault(f"replay read short: expected {len(source_turns)} turns,"
                         f" found {len(replay_all)} - the record is incomplete")
        broken = next((rt for rt in replay_all if rt["incomplete"]), None)
        if broken:
            return fault(f"replay {broken['turn']} is incomplete: {', '.join(broken['incomplete'])}")
        # The replay's requests are the source's, in the source's order, as
        # the record carries them.
        for st, rt in zip(source_turns, replay_all):
            if rt["text"] != st["text"]:
                return fault(f"replay {rt['turn']} carries a request other than source {st['turn']}'s")
        # Both halves load one declaration, so a replay under another seed is
        # the apparatus, which the knobs check would otherwise read DIVERGED.
        rec["replay_recorded_seed"], why = seed_of(replay_all, "replay")
        if why:
            return fault(why)
        if rec["replay_recorded_seed"] != recorded:
            return fault(f"the replay was recorded under another seed:"
                         f" source {recorded}, replay {rec['replay_recorded_seed']}")

        replay_by = {t["turn"]: t for t in replay_all}
        all_match = True
        for st in source_turns:
            rt = replay_by.get(st["turn"])
            # A source turn the replay does not carry is the record, and so is
            # a check either side carries no value for.
            if rt is None:
                return fault(f"the replay carries no {st['turn']}")
            checks = compare_turn(st, rt)
            why = unobserved(checks)
            if why:
                return fault(f"{st['turn']}: {why}")
            pairs.append((st, rt, checks))
            all_match = all_match and all(c["match"] for c in checks)
        # A replay carrying turns the source did not is interleaved traffic.
        surplus = sorted({t["turn"] for t in replay_all} - {st["turn"] for st in source_turns})
        if len(replay_all) != len(source_turns) or surplus:
            return fault(f"the replay carries {len(replay_all) - len(source_turns)} turns"
                         f" the source did not: {', '.join(surplus)}")
        rec["verdict"] = "REPRODUCED" if all_match else "DIVERGED"
        return pairs, evidence
    except KeyboardInterrupt:
        return fault(INTERRUPTED)
    except Exception as exc:  # an unattended run records rather than dies
        return fault(f"error: {type(exc).__name__}: {exc}")
    finally:
        # **The closing unload is guarded too** (#716 round eleven): a raise
        # here left `verify_session` past both clauses above and lost the
        # session's record. An interrupt makes the session `interrupted`,
        # and any other raise is a fault, as is an answer other than
        # `unloaded` (#716 round twelve), the first fault standing where the
        # session already had one.
        said = None
        try:
            closed = step("unload")
            if not admin_answered(closed, states=("unloaded",)):
                said = f"the closing unload was refused: {canonical(closed)}"
        except KeyboardInterrupt:
            rec["verdict"] = INTERRUPTED
            log(f"{INTERRUPTED} at the closing unload")
        except Exception as exc:  # the device may still be held
            said = f"error: {type(exc).__name__}: {exc} (the closing unload)"
        if said:
            if rec.get("verdict") in ("REPRODUCED", "DIVERGED", None):
                rec["verdict"] = said
            log(said)


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
            if sum(1 for t in turns if not t["incomplete"]) >= want:
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
    order, by, names = [], {}, {}
    for e in events:
        t = e.get("turn")
        if t is None:
            continue
        # Keyed by canonical JSON rather than by the value, so 1 and true
        # stay two turns, and a kind that is not a string is no kind (#716
        # round nine).
        key = canonical(t)
        if key not in by:
            by[key], names[key] = {}, t
            order.append(key)
        kind = e.get("kind")
        by[key].setdefault(kind if isinstance(kind, str) else None, []).append(e)
    turns = []
    for key in order:
        t, k = names[key], by[key]
        users = k.get("message.user", [])
        text = None
        # The request is exactly one text part. A request of several parts
        # would be reissued as its first alone and read as a divergence, so
        # any other shape is incomplete by name (#716 round five).
        request_shape = None
        if users:
            c = users[-1].get("payload", {}).get("content", [])
            if (isinstance(c, list) and len(c) == 1 and isinstance(c[0], dict)
                    and c[0].get("type") == "text" and isinstance(c[0].get("text"), str)):
                text = c[0]["text"]
            else:
                request_shape = "the request is not one text part"
        payload = {kind: (k[kind][0].get("payload") if kind in k else None)
                   for kind in ("model.request", "model.output",
                                "model.measurement")}
        wall = {kind: (k[kind][0].get("wall_ms") if kind in k else None)
                for kind in ("turn.started", "turn.closed")}
        # **An incomplete turn is kept and named, never dropped** (#716
        # round three). A turn missing its request text or a payload kind,
        # or carrying a compared kind twice, is evidence the harness cannot
        # compare whole, and dropping it could hide surplus traffic in a
        # replay. Callers wait on complete turns and refuse incomplete ones.
        incomplete = []
        if not (isinstance(t, str) and t):
            incomplete.append(f"the turn id {canonical(t)} is not a string")
        if request_shape:
            incomplete.append(request_shape)
        elif text is None:
            incomplete.append("no request text")
        if None in k:
            incomplete.append(f"{len(k[None])} events with no string kind")
        # `turn.closed` is the turn's last event, so a turn is whole only
        # once it stands: a wait that took the compared kinds alone could
        # read a turn before the sink had written all of it (#716, after
        # round twelve).
        for kind in ("model.request", "model.output", "model.measurement", "turn.closed"):
            n = len(k.get(kind, []))
            if n == 0:
                incomplete.append(f"no {kind}")
            elif n > 1:
                incomplete.append(f"{n} {kind} events")
        turns.append({"turn": t, "text": text, "payload": payload,
                      "wall": wall, "incomplete": incomplete})
    return turns


# **Absence is its own answer and never a value** (#716 round three). A
# field missing from both records compared equal as None and passed as a
# match, so the comparator reads through a sentinel and names the side that
# carries nothing, and a caller refuses the session rather than reading it.
ABSENT = object()


def pointer(value, ptr, absent=None):
    cur = value
    for part in ptr.strip("/").split("/"):
        if not isinstance(cur, dict) or part not in cur:
            return absent
        cur = cur[part]
    return cur


def compare_turn(src, rep):
    """Each of the eight CHECKS on one turn, compared as canonical JSON, so
    a value of another type is not a match (#716 round nine). A check a side
    carries no value for, missing or null, is never a match and names the
    side under `absent`, which is an apparatus fault for the caller, not a
    verdict."""
    out = []
    for name, kind, ptr in CHECKS:
        a = pointer(src["payload"][kind], ptr, ABSENT)
        b = pointer(rep["payload"][kind], ptr, ABSENT)
        absent = [side for side, v in (("source", a), ("replay", b))
                  if v is ABSENT or v is None]
        check = {"check": name, "match": not absent and canonical(a) == canonical(b)}
        if absent:
            check["absent"] = absent
        out.append(check)
    return out


def unobserved(checks):
    """The first check a turn's comparison could not observe, or None."""
    for c in checks:
        if c.get("absent"):
            return f"{c['check']} absent from the {' and '.join(c['absent'])} record"
    return None


def whole_ms(t):
    a, b = t["wall"]["turn.started"], t["wall"]["turn.closed"]
    return (b - a) if a is not None and b is not None else None


def stale_outputs(outdir, names):
    """The outputs a run writes that already stand in `outdir`: a run
    writes into a deposit no earlier run has written, so its record and its
    summary are of one invocation (#716 round five)."""
    return [n for n in names if os.path.lexists(os.path.join(outdir, n))]


def run_binding(records):
    """The one binding every session read, or why there is none: the
    sessions' own per-load reads, not a window the journal may have lost."""
    seen = []
    for r in records:
        d = r.get("devices")
        if d is not None and d not in seen:
            seen.append(d)
    if len(seen) == 1:
        return seen[0]
    if not seen:
        return {"unreadable": "no session read its serving device"}
    return {"varied": seen}


# The stack a run reads at both ends, and the windows every run's verdict
# requires: the weights and the stack (#716 round eleven). A caller that
# passes no weights window fails it.
STACK_WINDOW = ("engine_libraries", "weaver_binaries", "toolchain")
REQUIRED_WINDOWS = ("weights",) + STACK_WINDOW


def guessed(reading):
    """True where the reading resolved a binary by a guess, the admin
    configuration naming none. It reads identically at both ends and is
    still never shown to be the one the runtime launches (#716 round
    three)."""
    return isinstance(reading, dict) and any(
        isinstance(e, dict) and str(e.get("resolved_by", "")).startswith("guessed")
        for e in reading.values())


def release(cfg):
    """The unload a run makes as it ends, after every session's own, and a
    note where the admin did not answer unloaded or nothing resident: no
    session's verdict rests on it, and the note says the agent may still be
    loaded (#716 round twelve)."""
    answer = admin(cfg, "unload")
    if admin_answered(answer, states=("unloaded",), refusals=("no_residency",)):
        return None
    return f"the run's closing unload was refused, the agent may still be loaded: {canonical(answer)}"


def run_verdict(records, windows, interrupted=False, expected=None):
    """**The run-wide verdict**, which the matrix exits on and only formats
    (#716 round nine), as `verify_session` is the one session verification.
    `records` are the run's session records, and `windows` the closing
    envelopes it read, the weights, the stack's and any more. `expected` is
    a finite schedule's session count, and a run short of it did not
    reproduce (#716, after the fold). Answers whether every session
    reproduced, one at least having run, every expected one run, and no
    interrupt having cut the run short, and the held fields the run cannot
    show held:

    - every window field, the weights and each of the stack's among them,
      reads `unchanged`;
    - no binary was resolved by a guess;
    - the sessions that read a serving device read one binding, and at
      least one did.
    """
    reproduced = (not interrupted and bool(records)
                  and (expected is None or len(records) >= expected)
                  and all(r.get("verdict") == "REPRODUCED" for r in records))
    fields = list(REQUIRED_WINDOWS) + [k for k in windows if k not in REQUIRED_WINDOWS]
    unheld = [k for k in fields
              if not (isinstance(windows.get(k), dict) and windows[k].get("status") == "unchanged")]
    if "weaver_binaries" not in unheld and guessed(windows["weaver_binaries"].get("reading")):
        unheld.append("weaver_binaries")
    device = run_binding(records)
    if not (isinstance(device, list) and device
            and all(isinstance(d, dict) and "unreadable" not in d for d in device)):
        unheld.append("serving_device")
    return reproduced, unheld


def hold_invocations(rec, seen):
    """Every load of a run is its own unit invocation: one an earlier
    session read is a load that did not happen, and the session's verdict
    says so. The matrix holds each record to it as it closes (#716 round
    nine), `seen` carrying the run's invocations so far."""
    reused = [i for i in rec.get("invocations") or [] if i in seen]
    if reused:
        rec["verdict"] = f"a load read invocation {reused[0]}, which an earlier session read"
    seen.update(rec.get("invocations") or [])
    return rec
