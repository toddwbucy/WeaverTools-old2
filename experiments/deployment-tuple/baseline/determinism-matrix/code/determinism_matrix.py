#!/usr/bin/env python3
"""The determinism matrix: does the instrument hold across conditions?

The cross-precision harness confirmed one protocol once. This one asks
the prior question, and asks it on the easiest target on purpose: with
the smallest artifact and a single precision, a cell that fails is this
apparatus failing rather than the model being unfaithful. Prove the
testing works here, then scale.

**The matrix is over what could plausibly break a replay**, not over
repetition. Repeating one prompt exercises kernel nondeterminism and the
allocator and nothing else. Three axes vary instead:

  prompt character  a confident factual answer draws far from a tie and
                    an open-ended one draws near it, and a near-tie is
                    where a float wobble flips the draw and diverges the
                    whole emission. The confident end is what the first
                    experiment measured.
  depth             a turn at position 2 meets a nearly empty resident
                    sequence, one at position 32 meets a long accumulated
                    one, and the derived seed carries the turn ordinal, so
                    depth moves the seed as well as the state.
  length            short and long generations cross different kernel
                    tile boundaries.

Each session serves its turns, unloads fully, reloads, reissues every
turn byte-exact from the record, and compares field by field. The
entropy of each turn is carried into the report beside its verdict, so a
failure can be read against how near a tie the turn's draw was rather
than guessed at.

Run:

    python3 determinism_matrix.py --config thinkpad.json \
        --outdir <deposit> --hours 7

Wall-clock bounded: it finishes the session in hand and stops, so an
overnight run ends cleanly rather than mid-cell.
"""

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "cross-precision-repro"),
)
import confirm_cells as base

# **The declared seed as a per-session condition**, for Run 1 of issue #485:
# the seed is a line in the declaration, every session loads fresh, and both
# halves of a session read the same declaration, so rewriting that line
# before a session varies the seed across sessions while holding it within
# one. The rotation offsets by sweep so that no probe is wedded to one seed:
# the matrix has as many prompts as the schedule has seeds, and a rotation
# by cell alone would hand each prompt the same seed in every sweep.
# Horizontal whitespace only: `\s` would carry the match across a newline
# and rewrite the next line's value under a `seed:` that names nothing.
SEED_LINE = re.compile(r"^([ \t]*seed:[ \t]*)\S+", re.M)


def parse_seed_schedule(text):
    """The schedule as given: comma-separated integers, at least one, no
    repeats, because a repeated seed is a session counted twice under one
    condition and read as two."""
    # Each seed as the sampler takes it, decimal and within u64, refused by
    # name at preflight rather than at every session's load (#716 round
    # seven).
    seeds = [base.seed_value(part, "a scheduled seed") for part in text.split(",") if part.strip()]
    if not seeds:
        raise ValueError("the seed schedule is empty")
    if len(set(seeds)) != len(seeds):
        raise ValueError("the seed schedule repeats a value")
    if sweep_step(len(seeds), len(PROMPTS) * len(DEPTHS)) is None:
        raise ValueError(f"a schedule of {len(seeds)} seeds cannot vary the seed between"
                         " successive sessions and move every matrix cell's seed"
                         " between sweeps at once")
    return seeds


def sweep_step(n, cells):
    """What each sweep adds to a matrix cell's seed index (#716 round one).

    Within a sweep the index advances one per cell, so successive sessions
    differ wherever the schedule holds two seeds or more. Across the sweep
    boundary the last cell, at index `cells - 1`, meets the next sweep's
    first, at index `step`, so the step must not be congruent to `cells - 1`.
    And a step sharing no factor with the schedule's length carries every
    cell through every seed over as many sweeps as there are seeds, so no
    cell keeps one seed across sweeps. One, the step this matrix always used,
    wherever it satisfies both, which is every length not dividing
    `cells - 2`, and otherwise the smallest step that does. None where no
    step can: one seed never varies, and two seeds over an even sweep cannot
    alternate across the boundary and still move each cell."""
    for step in range(1, n):
        if math.gcd(step, n) == 1 and (cells - 1 - step) % n != 0:
            return step
    return None


def with_declared_seed(declaration, seed):
    """The declaration text with its one `seed:` line rewritten. Exactly one
    line, or the declaration is not the shape this override understands."""
    swapped, n = SEED_LINE.subn(lambda m: f"{m.group(1)}{seed}", declaration, count=2)
    if n != 1:
        raise ValueError(f"the declaration carries {n} seed lines, not one")
    return swapped


def seed_for(schedule, iteration, cell_index):
    """Which seed a cell takes: rotated by cell and offset by sweep, so
    over as many sweeps as there are seeds every cell meets every seed, and
    no two successive sessions share one, the sweep boundary included."""
    step = sweep_step(len(schedule), len(PROMPTS) * len(DEPTHS))
    if step is None:
        raise ValueError(f"a schedule of {len(schedule)} seeds has no valid rotation")
    return schedule[(cell_index + step * (iteration - 1)) % len(schedule)]


# **Every field the baseline holds is verified held**, #716 round two. The
# seed is read from the declaration on every path, not only a scheduled one,
# each load is held to the declaration and the loop the session declared, the
# artifact's bytes are read at both ends of the run, and the exit gate counts
# every field. Batch composition is one by construction and is recorded, not
# verified: the record carries nothing a second caller would change.


# The declaration's seed, read as a scalar within the sampler's u64 by the
# one reader both entry points share (#716 round eight).
standing_seed = base.declaration_seed


def hours_value(hours):
    """The run's wall-clock bound: finite, positive, and a deadline the clock
    can reach, or refused by name before anything is written (#716 round
    seven). Zero or less runs no session, and an infinite or overflowing one
    never ends."""
    if not (math.isfinite(hours) and hours > 0 and math.isfinite(time.time() + hours * 3600.0)):
        raise ValueError(f"--hours {hours} is not a finite positive bound")
    return hours


def session_seed(schedule, standing, iteration, cell_index):
    """The seed a session is declared under: the schedule's where one stands,
    and otherwise the declaration's own."""
    return seed_for(schedule, iteration, cell_index) if schedule is not None else standing


def artifact_of(declaration):
    """The one artifact the declaration binds, read as the YAML scalar it is
    (#716 round five), whose bytes the run reads at both ends as the weights
    field."""
    return base.declared_artifact(declaration)


def weights(path):
    """A provenance reader for the weights field: the artifact by sha256, or a
    note saying why it could not be read."""
    def read(cfg):
        try:
            return {"artifact": {"path": path, "sha256": base._sha256(path)}}
        except OSError as e:
            return {"artifact": {"path": path, "unreadable": base._why(e)}}
    return read


def run_binding(results):
    """The one binding every session read, or why there is none: the
    sessions' own per-load reads, not a window the journal may have lost."""
    seen = []
    for r in results:
        d = r.get("devices")
        if d is not None and d not in seen:
            seen.append(d)
    if len(seen) == 1:
        return seen[0]
    if not seen:
        return {"unreadable": "no session read its serving device"}
    return {"varied": seen}


# The fields read at both ends of a run, each held where both reads agree.
HELD_BY_WINDOW = ("weights", "engine_libraries", "weaver_binaries", "toolchain")


def unheld(summary):
    """The held fields the summary cannot show held, which the exit gate
    counts. The window fields must read `unchanged`. The serving device must
    be one binding for the whole run, read and not varied: one list of
    devices, none unreadable."""
    out = [k for k in HELD_BY_WINDOW if (summary.get(k) or {}).get("status") != "unchanged"]
    # A binary resolved by a guess, the admin configuration unread, was read
    # identically at both ends and still never shown to be the one the
    # runtime launches (#716 round three).
    binaries = ((summary.get("weaver_binaries") or {}).get("reading") or {})
    if "weaver_binaries" not in out and any(
            isinstance(e, dict) and str(e.get("resolved_by", "")).startswith("guessed")
            for e in binaries.values()):
        out.append("weaver_binaries")
    device = summary.get("serving_device")
    if not (isinstance(device, list) and device
            and all(isinstance(d, dict) and "unreadable" not in d for d in device)):
        out.append("serving_device")
    return out

# **The prompt set spans the draw's confidence, which is the axis that
# matters.** Each carries the character it was chosen for, so a reader
# grading a failure can see what the turn was meant to be rather than
# inferring it from the text.
PROMPTS = [
    ("factual-short", "confident",
     "What is the capital of France? Answer with the city name alone."),
    ("arithmetic", "confident",
     "What is 17 multiplied by 23? Give the number and nothing else."),
    ("definition", "confident",
     "Define the word 'photosynthesis' in one sentence."),
    ("explain-long", "mid",
     "Explain how a hash table works, including collision handling, "
     "in about two hundred words."),
    ("code-long", "mid",
     "Write a Python function that merges two sorted lists, with "
     "comments explaining each step, then describe its complexity."),
    ("creative-short", "near-tie",
     "Invent a name for a small coastal town. Answer with the name alone."),
    ("creative-long", "near-tie",
     "Write the opening paragraph of a story about a lighthouse keeper "
     "who receives an unexpected letter."),
    ("openended", "near-tie",
     "Name three unrelated things that happen to be blue, and say why "
     "each came to mind."),
]

# **Depth is a session shape rather than a per-turn flag.** A session of
# two turns and a session of eight put the same prompt at different
# ordinals over different resident state, which is the comparison.
DEPTHS = [2, 8, 16, 32]

# Filler between the probes in a deep session. Short and confident, so
# the depth it builds costs little wall clock and adds little entropy of
# its own.
FILLER = "In one short sentence, name a colour and nothing else."


def entropies_of(turn):
    e = base.pointer(turn["payload"]["model.measurement"], "/entropies")
    if not isinstance(e, list) or not e:
        return None
    vals = [x for x in e if isinstance(x, (int, float))]
    if not vals:
        return None
    summary = {
        "count": len(vals),
        "mean": round(statistics.fmean(vals), 6),
        "max": round(max(vals), 6),
        "min": round(min(vals), 6),
    }
    # A value that is not a number is left out of the summary and counted,
    # never dropped unsaid (#716 round three). The comparison reads the
    # series whole and is not touched by this.
    if len(vals) != len(e):
        summary["non_numeric"] = len(e) - len(vals)
    return summary


def run_session(cfg, probe, depth, iteration, declared_seed=None, declaration_sha=None):
    """One matrix cell: serve, unload, reload, reissue, compare, by the one
    session verification both entry points share (`confirm_cells.
    verify_session`, #716 round eight). This builds the matrix cell's texts
    and its record and formats the compared turns, and verifies nothing of
    its own. The agent is left unloaded whichever path this takes, and an
    unattended run records a raise as the session's verdict rather than
    dying on it.
    """
    key, character, text = probe
    rec = {"probe": key, "character": character, "depth": depth,
           "iteration": iteration, "verdict": None, "turns": [],
           "declared_seed": declared_seed, "recorded_seed": None,
           "replay_recorded_seed": None, "source_run": None, "replay_run": None}

    # The probe sits last, so its ordinal is the depth and everything
    # before it is the state the depth exists to build.
    texts = [FILLER] * (depth - 1) + [text]
    try:
        pairs, _ = base.verify_session(cfg, texts, rec, declared_seed, declaration_sha)
    except Exception as exc:  # an unattended run records rather than dies
        rec["verdict"] = f"error: {type(exc).__name__}: {exc}"
        return rec
    for st, rt, checks in pairs:
        # The emission's digest rides beside the verdict so a reading across
        # sessions, which is what a varied seed is read by, needs no second
        # walk of the trace.
        emission = base.pointer(st["payload"]["model.output"], "/emission")
        rec["turns"].append({
            "turn": st["turn"],
            "is_probe": st["text"] == text,
            "matched": all(c["match"] for c in checks),
            "failed_checks": [c["check"] for c in checks if not c["match"]],
            "entropy": entropies_of(st),
            "source_ms": base.whole_ms(st),
            "replay_ms": base.whole_ms(rt),
            "emission_sha256": hashlib.sha256(
                json.dumps(emission, sort_keys=True).encode()).hexdigest(),
        })
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--hours", type=float, default=7.0)
    ap.add_argument("--artifact", default=None,
                    help="override the declaration's artifact for every cell")
    ap.add_argument("--seed-schedule", default=None,
                    help="comma-separated declared seeds; the declaration's seed"
                         " line is rewritten before each session, rotating"
                         " through the list, and restored on exit")
    args = ap.parse_args()
    # **Preflight, whole, before the run writes or loads anything** (#716
    # round seven): every value checked against its consumer's domain, the
    # declaration read and checked, and only then the outdir made.
    def refuse(message):
        print(message, file=sys.stderr)
        sys.exit(2)

    # `is not None` rather than truthiness: an explicitly empty schedule is
    # refused by the parser, an omitted one is no schedule.
    schedule = None
    try:
        hours_value(args.hours)
        if args.seed_schedule is not None:
            schedule = parse_seed_schedule(args.seed_schedule)
    except ValueError as e:
        refuse(str(e))

    with open(args.config) as f:
        cfg = json.load(f)
    try:
        if not args.outdir:
            raise ValueError("--outdir is empty")
        base.config_values(cfg)
        base.loop_digest(cfg)
    except ValueError as e:
        refuse(str(e))
    # A run that rewrites the declaration leaves this backup until it has
    # restored it, so one standing now is a run that never did, and the file
    # on disk is not the operator's: a seed a killed schedule left would be
    # read as the declaration's own.
    pending = cfg["declaration"] + ".pre-matrix"
    if os.path.lexists(pending):
        refuse(f"a previous run left the declaration unrestored: its backup stands at"
               f" {pending}. Restore the declaration from it and remove it first.")

    with open(cfg["declaration"]) as f:
        original = f.read()
    # `standing` is the declaration this run works from: the operator's own,
    # or the artifact-swapped one, and the seed rewrite per session starts
    # from it so the two overrides compose rather than overwrite each other.
    standing = original
    try:
        if args.artifact is not None:
            standing = base.with_artifact(original, args.artifact)
        # A declaration without exactly one seed line is not one the
        # schedule can vary, refused with the operator's file untouched.
        if schedule is not None:
            with_declared_seed(standing, schedule[0])
        # The declaration's own seed and artifact, read on every path so a
        # run without a schedule holds them too.
        seed = standing_seed(standing)
        artifact = artifact_of(standing)
    except ValueError as e:
        refuse(str(e))

    # A run writes into a deposit no earlier run has written: an appended
    # record under a summary of the new invocation alone disagrees with it
    # (#716 round five). What the operator's shell writes beside the run,
    # the config, the box facts and the clock log, is not the run's.
    if os.path.isdir(args.outdir):
        stale = base.stale_outputs(args.outdir, ["matrix.jsonl", "matrix.log", "summary.json"])
        if stale:
            refuse(f"the outdir already holds a run's output: {', '.join(stale)}."
                   " A run writes into a deposit no earlier run has written.")
    os.makedirs(args.outdir, exist_ok=True)

    deadline = time.time() + args.hours * 3600.0
    # Opened before the first load so the journal read at the summary
    # cannot reach back past this run.
    run_started = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1))
    results, iteration, invocations = [], 0, set()
    # **Bound before the try, because the interrupt is caught rather than
    # fatal.** `except KeyboardInterrupt` below swallows the interrupt so a
    # run cut short still deposits its summary, which means the summary path
    # runs even when the library read never finished. Left unbound, a Ctrl-C
    # during the 142 MiB hash would reach the summary as a `NameError` and
    # lose every session the run had already recorded. The placeholder says
    # why it is empty rather than reading as "nothing to record", per the
    # same rule the reader itself follows.
    libraries = {"unreadable": "the run ended before the libraries were read"}
    binaries = {"unreadable": "the run ended before the binaries were read"}
    tools = {"unreadable": "the run ended before the toolchain was read"}
    weights_open = {"unreadable": "the run ended before the weights were read"}
    standing_sha = None
    # The placeholders above are not readings, which is what `base.is_reading`
    # tests at the close: an interrupted at-start read and a failed one leave
    # the same shape, and neither may be compared against a good closing read.
    logpath = os.path.join(args.outdir, "matrix.log")

    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(logpath, "a") as fh:
            fh.write(line + "\n")

    log(f"matrix start, deadline in {args.hours}h, "
        f"{len(PROMPTS)} prompts x {len(DEPTHS)} depths")
    if schedule is not None:
        log(f"declared seed schedule: {schedule}")
    if args.artifact is not None or schedule is not None:
        # The operator's declaration, kept until the run has restored it.
        with open(pending, "x") as fh:
            fh.write(original)
    try:
        # **The swap itself is inside the cleanup scope**: opening the file
        # for writing truncates it before the write, so a write that fails
        # outside the `try` would leave the operator's declaration empty
        # with nothing to restore it. Everything after it is here for the
        # same reason: `ldd` missing raises, hashing 142 MiB can be
        # interrupted, and either one outside the `try` would leave the
        # declaration holding this run's artifact.
        if args.artifact is not None:
            with open(cfg["declaration"], "w") as fh:
                fh.write(standing)
        opening_spu = base._resolve_spu(cfg)
        libraries = base.engine_libraries(cfg, opening_spu)
        binaries = base.weaver_binaries(cfg, opening_spu)
        tools = base.toolchain(cfg)
        weights_open = weights(artifact)(cfg)
        # The declaration as it stands on disk, by the digest every load
        # event records, once the run's own artifact override is written.
        standing_sha = base._sha256(cfg["declaration"])
        log(f"weights: {json.dumps(weights_open)}")
        log(f"declaration: sha256 {standing_sha}, seed {seed}")
        log(f"engine libraries: {json.dumps(libraries)}")
        log(f"weaver binaries: {json.dumps(binaries)}")
        log(f"toolchain: {json.dumps(tools)}")

        # Sweeps rather than repeats: every combination is seen once
        # before any is seen twice, so a run cut short by the clock still
        # covers the matrix rather than the front of it.
        while time.time() < deadline:
            iteration += 1
            cell_index = 0
            for depth in DEPTHS:
                for probe in PROMPTS:
                    if time.time() >= deadline:
                        break
                    declared_seed = session_seed(schedule, seed, iteration, cell_index)
                    declaration_sha = standing_sha
                    if schedule is not None:
                        with open(cfg["declaration"], "w") as fh:
                            fh.write(with_declared_seed(standing, declared_seed))
                        declaration_sha = base._sha256(cfg["declaration"])
                    cell_index += 1
                    started = time.time()
                    rec = run_session(cfg, probe, depth, iteration, declared_seed,
                                      declaration_sha)
                    rec["seconds"] = round(time.time() - started, 1)
                    # Every load of a run is its own invocation: one an
                    # earlier session read is a load that did not happen.
                    reused = [i for i in rec.get("invocations") or [] if i in invocations]
                    if reused:
                        rec["verdict"] = f"a load read invocation {reused[0]}, which an earlier session read"
                    invocations.update(rec.get("invocations") or [])
                    results.append(rec)
                    ent = ""
                    for t in rec["turns"]:
                        if t.get("is_probe") and t.get("entropy"):
                            ent = f" H_mean={t['entropy']['mean']}"
                    seed_note = f" seed={declared_seed}" if schedule is not None else ""
                    log(f"i{iteration} {probe[0]}/d{depth}: "
                        f"{rec['verdict']} ({rec['seconds']}s){ent}{seed_note}")
                    with open(os.path.join(args.outdir, "matrix.jsonl"), "a") as fh:
                        fh.write(json.dumps(rec) + "\n")
    except KeyboardInterrupt:
        log("interrupted")
    finally:
        # Restored only where this run swapped it: rewriting unconditionally
        # would turn an unrelated edit made during the run into a silent
        # revert of the operator's own declaration.
        if args.artifact is not None or schedule is not None:
            with open(cfg["declaration"], "w") as fh:
                fh.write(original)
            os.unlink(pending)
        base.admin(cfg, "unload")

    total = len(results)
    good = sum(1 for r in results if r["verdict"] == "REPRODUCED")
    diverged = [r for r in results if r["verdict"] == "DIVERGED"]
    errors = [r for r in results if r["verdict"] not in ("REPRODUCED", "DIVERGED")]

    by_character = {}
    for r in results:
        b = by_character.setdefault(r["character"], {"n": 0, "ok": 0})
        b["n"] += 1
        b["ok"] += 1 if r["verdict"] == "REPRODUCED" else 0
    # By seed: the within-session verdict per declared seed, so a seed that
    # fails to reproduce is visible on its own. Every session carries one
    # since #716, a run without a schedule reading the declaration's own.
    by_seed = {}
    for r in results:
        b = by_seed.setdefault(str(r["declared_seed"]), {"n": 0, "ok": 0})
        b["n"] += 1
        b["ok"] += 1 if r["verdict"] == "REPRODUCED" else 0

    # **The box facts ride the summary rather than a sidecar**, per issue
    # #370's third ask. The olympus deposit of 2026-08-27 carried its
    # serving device and engine libraries in a hand-written `box-facts.txt`
    # beside this file, which works exactly once and only if whoever runs
    # the matrix next remembers. The readers are the confirm driver's, so
    # the two instruments answer this question the same way or not at all.
    #
    # **Every binding in the window is checked rather than the last one**,
    # per finding 6 of the olympus seat. An earlier draft recorded the last
    # load on the reasoning that every session binds the same device, which
    # is the assumption #370 falsified: `run_session` loads and unloads per
    # session, a seven-hour window holds hundreds of loads, and a mid-run
    # session binding differently would be recorded nowhere. The summary
    # says what was seen and says plainly when it was not one thing, which
    # is what a reader needs to know before trusting a rate over the run.
    # Guarded for the same reason: these facts exist to make the deposit
    # worth trusting, so they must never be the reason there is no deposit.
    # A box without `journalctl` on PATH raises here, and losing a
    # seven-hour matrix over a missing box fact would be the wrong trade.
    # **The binaries are read twice and compared**, per finding 7 of the
    # olympus seat. `--hours` lets a run reach seven and `run_session` loads
    # and unloads per session, so a build swapped mid-matrix would be
    # recorded nowhere and one hash asserted over the whole window - the
    # shape #370 falsified and the one this summary already rejects for
    # device bindings. One extra hash makes the claim checkable rather than
    # assumed. The libraries carry the same exposure and are read with them.
    # Guarded like the device read below, and for the same reason: a closing
    # read that raised would lose the run it was added to describe.
    # **`KeyboardInterrupt` is caught by name**, because it is not an
    # `Exception` and `except Exception` let it past. The main loop has
    # already absorbed one Ctrl-C by this point and these reads hash 142 MiB,
    # so a second one landed in the window would have killed `main` before
    # `summary.json` was written - losing every session, which is the loss
    # the placeholders above exist to prevent.
    #
    # **The two reads are wrapped apart.** Together, a library failure
    # discarded a good binary reading and was then recorded under the binary
    # field, so the summary said the binaries could not be re-read when they
    # could, and the library failure was recorded nowhere.
    # The catch, `KeyboardInterrupt` included, now lives inside
    # `base.provenance_close`, where the lift carried it.
    # **`varied` is claimed only where both sides are readings.** These
    # readers report failure by returning a note rather than by raising, so
    # the `except` below catches almost nothing and a failed closing read
    # would otherwise fall into the `!=` branch - asserting the build changed
    # mid-run out of a transient failure to look. `base.is_reading` is the
    # test, and a flag recording whether the read ran was not it: a read
    # that ran and failed leaves the same shape as one that never ran.
    # **Lifted to `confirm_cells` per #379** - these helpers were local here
    # while the confirm driver compared with a raw `!=`, two answers to one
    # question. The matrix now calls the shared implementation it donated.
    def close(reader, at_start, what, essence=None):
        return base.provenance_close(cfg, reader, at_start, what,
                                     essence=essence)

    whole = base.close_whole

    # **One resolution for both collectors at each end**, so the two fields
    # cannot disagree about which SPU they measured - the same sharing the
    # confirm driver does at its own two reads.
    closing_spu, spu_note = base.closing_resolution(cfg)
    binaries_at_close = close(
        lambda c: spu_note or base.weaver_binaries(c, closing_spu), binaries, "weaver_binaries"
    )
    libraries = close(
        lambda c: spu_note or base.engine_libraries(c, closing_spu), libraries, "engine_libraries"
    )
    # **Read twice like the other two.** It was the one reader left on a
    # single read, which is what made the invariant break in `toolchain`
    # latent rather than visible. Compared whole rather than by hash, its
    # values being strings, and a difference here is a difference in what
    # built the binaries rather than in the binaries - the hashes above are
    # what would catch a swap, and this catches the pin moving under a run.
    tools = close(base.toolchain, tools, "toolchain", essence=whole)
    # The weights field, the artifact's bytes, read like the stack at both
    # ends (#716 round two).
    weights_at_close = close(weights(artifact), weights_open, "weights")

    try:
        bindings = base.device_bindings(cfg, run_started)
    except (Exception, KeyboardInterrupt) as e:  # noqa: BLE001 - degrades to a note
        # `_why` here too: widening this catch to include `KeyboardInterrupt`
        # opened the empty-reason path, `journalctl` over a seven-hour window
        # being a call a Ctrl-C can land in.
        bindings = [{"unreadable": f"the device read failed: {base._why(e)}"}]
    summary = {
        # Held from every session's own per-load read (#716 round three).
        # The journal window over the whole run is kept as a record and not
        # gated: a journal that keeps minutes cannot answer for hours.
        "serving_device": run_binding(results),
        "serving_device_journal_window": (bindings[0] if len(bindings) == 1
                                          else {"varied": bindings}),
        "weights": weights_at_close,
        "engine_libraries": libraries,
        "weaver_binaries": binaries_at_close,
        "toolchain": tools,
        "sessions": total,
        "reproduced": good,
        "diverged": len(diverged),
        "errors": len(errors),
        "by_character": by_character,
        "declared_seed_schedule": schedule,
        "by_seed": by_seed,
        "diverged_detail": diverged[:20],
        "error_detail": [{"probe": r["probe"], "depth": r["depth"],
                          "verdict": r["verdict"]} for r in errors[:20]],
    }
    with open(os.path.join(args.outdir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)

    log(f"done: {good}/{total} reproduced, {len(diverged)} diverged, "
        f"{len(errors)} errors")
    for ch, b in sorted(by_character.items()):
        log(f"  {ch}: {b['ok']}/{b['n']}")
    # **Every held field joins the verdict at the exit** (#716 round two).
    # The window fields, the weights among them, must read unchanged, per
    # #399's review, and the serving device must be one binding for the run,
    # read and not varied: a run whose sessions all reproduce while a field
    # it claims held moved, or was never read, is not a reproduction result.
    failing = unheld(summary)
    if total and good == total and failing:
        log("sessions reproduced but these held fields did not hold:"
            f" {', '.join(failing)} - not a reproduction result")
    sys.exit(0 if total and good == total and not failing else 1)


if __name__ == "__main__":
    main()
