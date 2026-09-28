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

**One entry point, and the sessions it runs are data** (#716, on the
operator's ruling of 2026-09-27). `--cells` runs the config's cells, each
once, the cross-precision protocol: one artifact at one precision per
cell, served one short and one longer turn. Without it the run sweeps the
prompt-by-depth matrix until its deadline. Both are the same main, the
same session loop and the same exit, differing only in the sessions the
schedule yields.
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
# The site is the one value at spu-instruction.decoder.tunable-values.seed,
# found by where it sits in the document rather than by the text around it,
# per `base.value_sites`.


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
    """The declaration text with its one `seed = <integer>` site rewritten
    and every other byte kept. Exactly one site, reading back as the seed at
    spu-instruction.decoder.tunable-values.seed with the rest of the document
    unchanged, or the declaration is not the shape this override
    understands. A seed a TOML integer cannot carry, one past the signed
    64-bit range, is refused by name, since the stack's parser refuses the
    file it would make."""
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= base.I64_MAX:
        raise ValueError(f"the seed {seed!r} is not an integer a TOML declaration carries,"
                         f" 0 to {base.I64_MAX}")
    return base.rewrite_site(declaration, base.SEED_PATH, seed, str(seed), "seed")


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


# The declaration's seed, read as a TOML integer within the sampler's u64 by the
# one reader every session's seed is read by (#716 round eight).
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
    """The one artifact the declaration binds, read as the TOML string it is
    (#716 round five), whose bytes the run reads at both ends as the weights
    field."""
    return base.declared_artifact(declaration)


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

# The cross-precision protocol's two pinned turns, one short and one
# longer, served in every cell, as its earlier deposits served them.
CELL_TEXTS = (
    "Introduce yourself in exactly one short sentence.",
    "Write a detailed step-by-step explanation of how a binary search "
    "works, then implement it in Python with comments, then walk "
    "through an example run on a list of twenty numbers.",
)


def matrix_session(probe, depth, iteration, declared_seed=None, declaration=None):
    """One session of the prompt-by-depth matrix, as data: the labels its
    record carries, its texts, which of them is the probe, the seed it is
    declared under, and the declaration text written for it where the run
    rewrites one per session. The probe sits last, so its ordinal is the
    depth and everything before it is the state the depth exists to
    build."""
    key, character, text = probe
    return {"label": {"probe": key, "character": character, "depth": depth,
                      "iteration": iteration},
            "name": f"i{iteration} {key}/d{depth}",
            "texts": [FILLER] * (depth - 1) + [text], "probe": text,
            "declared_seed": declared_seed, "declaration": declaration}


def matrix_sessions(standing, seed, schedule):
    """The matrix's sessions, sweep after sweep without end, the run's
    deadline stopping it. Sweeps rather than repeats: every combination is
    seen once before any is seen twice, so a run cut short by the clock
    still covers the matrix rather than the front of it."""
    iteration = 0
    while True:
        iteration += 1
        cell_index = 0
        for depth in DEPTHS:
            for probe in PROMPTS:
                declared_seed = session_seed(schedule, seed, iteration, cell_index)
                cell_index += 1
                # Under a schedule the shared path writes the session's
                # declaration and holds its loads to that digest.
                yield matrix_session(probe, depth, iteration, declared_seed,
                                     with_declared_seed(standing, declared_seed)
                                     if schedule is not None else None)


def cell_sessions(standing, cells):
    """The cells' sessions, each cell once: the declaration with the cell's
    artifact and everything else as the operator wrote it, under its own
    seed, serving the protocol's two turns."""
    for cell in cells:
        declaration = base.with_artifact(standing, cell["artifact"])
        yield {"label": {"cell": cell["name"], "precision": cell["precision"],
                         "artifact": cell["artifact"], "iteration": 1},
               "name": f"cell {cell['name']}", "texts": list(CELL_TEXTS), "probe": None,
               "declared_seed": base.declaration_seed(declaration), "declaration": declaration}


def entropies_of(turn):
    e = base.pointer(turn["payload"]["model.measurement"], "/entropies")
    if not isinstance(e, list) or not e:
        return None
    # A boolean is not a number here, though Python counts it one.
    vals = [x for x in e if isinstance(x, (int, float)) and not isinstance(x, bool)]
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


def new_record(session):
    """A session's record before it runs: its labels, and every field the
    verification fills, empty."""
    return dict(session["label"], verdict=None, turns=[], declared_seed=session["declared_seed"],
                recorded_seed=None, replay_recorded_seed=None, source_run=None, replay_run=None)


def record_session(cfg, session, declaration_sha=None):
    """`run_session` with **the fault boundary around the whole of it** (#716,
    the pass on 26b93db): a raise in the verification or in formatting its
    record, a wall time that is not a number for one, is the session's
    `error: <type>: <message>` fault on the record as far as it got, and the
    run goes on to its next session and its summary. An interrupt there is
    the session's `interrupted`, on which the loop stops (#716, the pass on
    9402e08)."""
    rec = new_record(session)
    try:
        return run_session(cfg, session, declaration_sha, rec)
    except KeyboardInterrupt:
        rec["verdict"] = base.INTERRUPTED
        return rec
    except Exception as exc:  # the session's fault, never the run's end
        rec["verdict"] = f"error: {type(exc).__name__}: {exc}"
        return rec


def run_session(cfg, session, declaration_sha=None, rec=None):
    """One session, a matrix cell or a cell of the cross-precision protocol:
    serve, unload, reload, reissue, compare, by `confirm_cells.
    verify_session`, the one session verification (#716 round eight). This
    builds the session's record from its labels and formats the compared
    turns, and verifies nothing of its own. `declaration_sha` is the digest
    of the declaration the run holds, for a session that writes none of its
    own. The agent is left unloaded whichever path this takes, and a raise
    is the session's verdict, recorded by the shared path (#716 round ten).
    """
    rec = new_record(session) if rec is None else rec
    pairs, _ = base.verify_session(cfg, session["texts"], rec, session["declared_seed"],
                                   declaration_sha, declaration=session["declaration"])
    for st, rt, checks in pairs:
        # The emission's digest rides beside the verdict so a reading across
        # sessions, which is what a varied seed is read by, needs no second
        # walk of the trace.
        emission = base.pointer(st["payload"]["model.output"], "/emission")
        rec["turns"].append({
            "turn": st["turn"],
            "is_probe": st["text"] == session["probe"],
            "matched": all(c["match"] for c in checks),
            "failed_checks": [c["check"] for c in checks if not c["match"]],
            "entropy": entropies_of(st),
            "source_ms": base.whole_ms(st),
            "replay_ms": base.whole_ms(rt),
            "emission_sha256": hashlib.sha256(
                json.dumps(emission, sort_keys=True).encode()).hexdigest(),
        })
    return rec


# What a run writes into its outdir, and nothing else.
OUTPUTS = ("matrix.jsonl", "matrix.log", "summary.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--hours", type=float, default=None,
                    help="the matrix's wall-clock bound, 7 by default; a cells run takes none")
    ap.add_argument("--artifact", default=None,
                    help="override the declaration's artifact for every cell")
    ap.add_argument("--seed-schedule", default=None,
                    help="comma-separated declared seeds; the declaration's seed"
                         " line is rewritten before each session, rotating"
                         " through the list, and restored on exit")
    ap.add_argument("--cells", action="store_true",
                    help="run the config's cells, each once, in place of the"
                         " prompt-by-depth matrix")
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
        if args.seed_schedule is not None:
            schedule = parse_seed_schedule(args.seed_schedule)
        # A cell names its own artifact and runs under the declaration's
        # seed, and a cells run serves every cell, so no deadline stops it
        # short (#716, after the fold): none of the three overrides has a
        # meaning for one.
        if args.cells and (args.artifact is not None or schedule is not None or args.hours is not None):
            raise ValueError("--cells takes neither --artifact, --seed-schedule nor --hours:"
                             " each cell names its artifact, runs under the declaration's seed,"
                             " and is served whatever the clock")
        if not args.cells:
            args.hours = hours_value(7.0 if args.hours is None else args.hours)
    except ValueError as e:
        refuse(str(e))

    try:
        if not args.outdir:
            raise ValueError("--outdir is empty")
        cfg = base.read_config(args.config)
        base.config_values(cfg)
        base.loop_digest(cfg)
        if args.cells:
            base.cells_values(cfg)
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

    # The run rewrites the declaration where it overrides the artifact or
    # the seed, and only there.
    # A cells run rewrites the declaration for every cell.
    rewrites = args.cells or args.artifact is not None or schedule is not None
    try:
        # The files the run opens, the declaration among them, checked as
        # the run will use them (#716 round nine).
        # The bytes read here are the declaration the run holds: the
        # restore writes them back and the loads are held to their digest,
        # the disk never re-read and trusted (#716 round eleven).
        held = base.run_files(cfg, rewrites)
        original = held.decode()
        # `standing` is the declaration this run works from: the operator's
        # own, or the artifact-swapped one, and the seed rewrite per session
        # starts from it so the two overrides compose rather than overwrite
        # each other.
        standing = original
        if args.artifact is not None:
            standing = base.with_artifact(original, args.artifact)
        # A declaration without exactly one seed site is not one the
        # schedule can vary, refused with the operator's file untouched.
        # Every scheduled seed is written once here, so a seed the TOML
        # integer cannot carry is refused before the first session.
        if schedule is not None:
            for scheduled in schedule:
                with_declared_seed(standing, scheduled)
        # The declaration's own seed and artifact, read on every path so a
        # run without a schedule holds them too.
        seed = standing_seed(standing)
        # The artifacts the run reads as its weights window, keyed as the
        # reading carries them: the declaration's one, or each cell's by the
        # cell's name, each cell's declaration checked here as the session
        # will write it.
        if args.cells:
            artifacts = {}
            for c in cfg["cells"]:
                base.declaration_seed(base.with_artifact(standing, c["artifact"]))
                artifacts[c["name"]] = c["artifact"]
        else:
            artifacts = artifact_of(standing)
    except ValueError as e:
        refuse(str(e))

    # A run writes into a deposit no earlier run has written: an appended
    # record under a summary of the new invocation alone disagrees with it
    # (#716 round five). What the operator's shell writes beside the run,
    # the config, the box facts and the clock log, is not the run's.
    if os.path.isdir(args.outdir):
        stale = base.stale_outputs(args.outdir, OUTPUTS)
        if stale:
            refuse(f"the outdir already holds a run's output: {', '.join(stale)}."
                   " A run writes into a deposit no earlier run has written.")
    # The artifact opened and hashed, and the stack read, as the run opens
    # and before it writes anything (#716 round nine): an artifact the run
    # cannot read, or a stack reading the exit could never count held, is
    # refused here rather than failing every session or the run's exit.
    try:
        weights_open = base.weights(artifacts)(cfg)
        if not base.is_reading(weights_open):
            raise ValueError(f"the artifact cannot be read: {json.dumps(weights_open)}")
        opening = base.opening_readings(cfg)
        base.held_declaration(cfg, held)
        # **Every output the run writes is created at preflight, last**
        # (#716, after round twelve): an outdir the operator cannot write
        # passed `makedirs` and failed at the first record, after a whole
        # session had run. Each is created and removed again, so a refusal
        # still leaves no output behind.
        try:
            os.makedirs(args.outdir, exist_ok=True)
            for name in OUTPUTS:
                path = os.path.join(args.outdir, name)
                with open(path, "x"):
                    pass
                os.unlink(path)
        except OSError as e:
            raise ValueError(f"the outdir {args.outdir} cannot take the run's outputs: {base._why(e)}") from None
    except ValueError as e:
        refuse(str(e))
    libraries, binaries, tools = (opening[k] for k in base.STACK_WINDOW)

    deadline = math.inf if args.cells else time.time() + args.hours * 3600.0
    # Opened before the first load so the journal read at the summary
    # cannot reach back past this run.
    run_started = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1))
    # The closing steps a run's result rests on, where one failed.
    results, invocations, interrupted, unclosed = [], set(), False, []
    logpath = os.path.join(args.outdir, "matrix.log")

    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(logpath, "a") as fh:
            fh.write(line + "\n")

    def closing(what, step):
        """One step between the session loop and the summary, guarded
        (#716, after round twelve). An interrupt marks the run interrupted
        and the step is tried once more, since each is safe to repeat, and
        any other raise is logged, so the summary is still written. Answers
        whether the step completed and its value, apart, so a step whose
        value is None is not taken for one that failed (#716, the pass on
        7ba83d5)."""
        nonlocal interrupted
        for attempt in (1, 2):
            try:
                return True, step()
            except KeyboardInterrupt:
                interrupted = True
                log(f"interrupted during {what}" + ("" if attempt == 2 else ", trying it once more"))
            except Exception as e:  # noqa: BLE001 - the summary is still owed
                log(f"{what} failed: {base._why(e)}")
                return False, None
        return False, None

    if args.cells:
        sessions = cell_sessions(standing, cfg["cells"])
        log(f"matrix start, {len(cfg['cells'])} cells, each served once, no deadline")
    else:
        sessions = matrix_sessions(standing, seed, schedule)
        log(f"matrix start, deadline in {args.hours}h, "
            f"{len(PROMPTS)} prompts x {len(DEPTHS)} depths")
    if schedule is not None:
        log(f"declared seed schedule: {schedule}")
    if rewrites:
        # The operator's declaration, kept until the run has restored it.
        with open(pending, "xb") as fh:
            fh.write(held)
    try:
        # **The swap itself is inside the cleanup scope**: opening the file
        # for writing truncates it before the write, so a write that fails
        # outside the `try` would leave the operator's declaration empty
        # with nothing to restore it. The stack and the weights were read at
        # preflight, before anything was written.
        # The declaration the run holds, by the digest every load event
        # records: the bytes read at preflight, or the artifact override's
        # bytes as written, never a read of the file back.
        standing_sha = hashlib.sha256(held).hexdigest()
        if args.artifact is not None:
            with open(cfg["declaration"], "wb") as fh:
                fh.write(standing.encode())
            standing_sha = hashlib.sha256(standing.encode()).hexdigest()
        log(f"weights: {json.dumps(weights_open)}")
        log(f"declaration: sha256 {standing_sha}, seed {seed}")
        log(f"engine libraries: {json.dumps(libraries)}")
        log(f"weaver binaries: {json.dumps(binaries)}")
        log(f"toolchain: {json.dumps(tools)}")

        # **One session loop**, over whichever sessions the schedule yields,
        # until they end or the deadline passes.
        for session in sessions:
            if time.time() >= deadline:
                break
            started = time.time()
            rec = record_session(cfg, session, standing_sha)
            # An interrupt after the session's record exists makes it the
            # session cut short, recorded as such (#716, the pass on
            # 9402e08).
            try:
                rec["seconds"] = round(time.time() - started, 1)
                # Every load of a run is its own invocation.
                base.hold_invocations(rec, invocations)
                ent = ""
                for t in rec["turns"]:
                    if t.get("is_probe") and t.get("entropy"):
                        ent = f" H_mean={t['entropy']['mean']}"
                seed_note = f" seed={session['declared_seed']}" if schedule is not None else ""
                log(f"{session['name']}: {rec['verdict']} ({rec['seconds']}s){ent}{seed_note}")
            except KeyboardInterrupt:
                rec["verdict"] = base.INTERRUPTED
            # **The record joins the results only with its line in
            # `matrix.jsonl`**, so the summary counts the sessions the record
            # holds. The write is guarded: an interrupt in it makes the
            # session `interrupted` and the line is written again whole, and
            # a write that never lands is a closing step the result rests on.
            # The offset the line starts at is read inside the guarded step,
            # once, so an interrupt at that read is the session's too (#698).
            path = os.path.join(args.outdir, "matrix.jsonl")
            where = {}

            def append():
                if interrupted:
                    rec["verdict"] = base.INTERRUPTED
                if "offset" not in where:
                    where["offset"] = os.path.getsize(path) if os.path.exists(path) else 0
                with open(path, "a") as fh:
                    fh.truncate(where["offset"])
                    fh.write(json.dumps(rec) + "\n")
            if closing(f"{session['name']}'s record", append)[0]:
                results.append(rec)
            else:
                unclosed.append(f"{session['name']}'s record")
            # The session an interrupt cut short is recorded, and the run
            # stops on it (#716 round ten).
            if interrupted or rec["verdict"] == base.INTERRUPTED:
                raise KeyboardInterrupt
    except KeyboardInterrupt:
        interrupted = True
        log("interrupted")
    finally:
        # Restored only where this run swapped it: rewriting unconditionally
        # would turn an unrelated edit made during the run into a silent
        # revert of the operator's own declaration. The backup is removed
        # only once the restore has landed, so a restore that failed leaves
        # it standing and the next run refuses until it is resolved.
        def restore():
            with open(cfg["declaration"], "wb") as fh:
                fh.write(held)
            os.unlink(pending)
        # A restore that did not land leaves the operator's declaration
        # unrestored, and the run's result with it.
        if rewrites and not closing("the declaration's restore", restore)[0]:
            unclosed.append("the declaration's restore")
        # The run's own last unload, its answer read (#716 round twelve). A
        # note, not a verdict: no session rests on it.
        released = closing("the run's last unload", lambda: base.release(cfg))[1]
        if released:
            log(released)

    total = len(results)
    good = sum(1 for r in results if r["verdict"] == "REPRODUCED")
    diverged = [r for r in results if r["verdict"] == "DIVERGED"]
    errors = [r for r in results if r["verdict"] not in ("REPRODUCED", "DIVERGED")]

    # By prompt character for the matrix's sessions and by cell for the
    # cells', each over the records that carry the label.
    by_character, by_cell = {}, {}
    for r in results:
        for table, key in ((by_character, r.get("character")), (by_cell, r.get("cell"))):
            if key is not None:
                b = table.setdefault(key, {"n": 0, "ok": 0})
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
    # the matrix next remembers. The readers are `confirm_cells`', shared
    # by every mode of this one instrument.
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
    # **An interrupt in a closing read is `closing`'s**, below: the main
    # loop has already absorbed one Ctrl-C by this point and these reads
    # hash 142 MiB, so a second one landed in the window would otherwise
    # have killed `main` before `summary.json` was written, or been caught
    # into a note without marking the run interrupted.
    #
    # **The two reads are wrapped apart.** Together, a library failure
    # discarded a good binary reading and was then recorded under the binary
    # field, so the summary said the binaries could not be re-read when they
    # could, and the library failure was recorded nowhere.
    # The catch of an ordinary failure lives inside `base.provenance_close`,
    # where the lift carried it.
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
    # **Every closing read goes through `closing`** (#716, after the fold):
    # an interrupt in one marks the run interrupted and the read is tried
    # once more, and a read interrupted twice closes unreadable.
    def close(reader, at_start, what, essence=None):
        done, envelope = closing(f"the closing {what} reading", lambda: base.provenance_close(
            cfg, reader, at_start, what, essence=essence))
        if not done:
            envelope = {"status": "at_close_unreadable", "at_start": at_start,
                        "note": {"unreadable": f"{what}: the closing read did not complete"}}
        return envelope

    whole = base.close_whole

    # **One resolution for both collectors at each end**, so the two fields
    # cannot disagree about which SPU they measured - the same sharing the
    # opening readings do at preflight.
    # A resolution that did not complete is the note both collectors
    # return, so the binaries and the libraries close unreadable, never
    # `unchanged`.
    done, resolution = closing("the SPU's closing resolution", lambda: base.closing_resolution(cfg))
    closing_spu, spu_note = (resolution if done else
                             (None, {"unreadable": "the SPU's closing resolution did not complete"}))
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
    weights_at_close = close(base.weights(artifacts), weights_open, "weights")

    # Through `closing` too: `journalctl` over a seven-hour window is a call
    # a Ctrl-C can land in, and an interrupt caught here into an unreadable
    # window left the run unmarked, the window not being gated (#716, after
    # the fold).
    done, bindings = closing("the journal's device read", lambda: base.device_bindings(cfg, run_started))
    if not done:
        bindings = [{"unreadable": "the journal's device read did not complete"}]
    summary = {
        # Held from every session's own per-load read (#716 round three).
        # The journal window over the whole run is kept as a record and not
        # gated: a journal that keeps minutes cannot answer for hours.
        "serving_device": base.run_binding(results),
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
        "by_cell": by_cell,
        "declared_seed_schedule": schedule,
        "by_seed": by_seed,
        "diverged_detail": diverged[:20],
        "error_detail": [dict({k: r[k] for k in ("probe", "depth", "cell") if k in r},
                              verdict=r["verdict"]) for r in errors[:20]],
    }
    def write_summary():
        with open(os.path.join(args.outdir, "summary.json"), "w") as fh:
            json.dump(summary, fh, indent=1)
    # A run whose summary was not written is not a result.
    if not closing("the summary's write", write_summary)[0]:
        unclosed.append("the summary's write")

    log(f"done: {good}/{total} reproduced, {len(diverged)} diverged, "
        f"{len(errors)} errors")
    for ch, b in sorted(by_character.items()) + sorted(by_cell.items()):
        log(f"  {ch}: {b['ok']}/{b['n']}")
    # **Every held field joins the verdict at the exit** (#716 round two).
    # The window fields, the weights among them, must read unchanged, per
    # #399's review, and the serving device must be one binding for the run,
    # read and not varied: a run whose sessions all reproduce while a field
    # it claims held moved, or was never read, is not a reproduction result.
    # The verdict is `run_verdict`, the one run-wide verdict (#716 round
    # nine).
    # A cells run is finite and serves every cell, so a run short of its
    # cells is not a reproduction result, and the log names what it missed.
    expected = len(cfg["cells"]) if args.cells else None
    reproduced, failing = base.run_verdict(results, {
        "weights": weights_at_close, "engine_libraries": libraries,
        "weaver_binaries": binaries_at_close, "toolchain": tools}, interrupted, expected)
    if args.cells:
        served = {r.get("cell") for r in results}
        missed = [c["name"] for c in cfg["cells"] if c["name"] not in served]
        if missed:
            log(f"cells not served: {', '.join(missed)} - not a reproduction result")
    if interrupted:
        log("interrupted - not a reproduction result")
    if reproduced and failing:
        log("sessions reproduced but these held fields did not hold:"
            f" {', '.join(failing)} - not a reproduction result")
    # The closing steps the result rests on, the summary's write and the
    # declaration's restore, join the exit (#716, the pass on 7ba83d5).
    if unclosed:
        log(f"these closing steps did not complete: {', '.join(unclosed)} - not a reproduction result")
    sys.exit(0 if reproduced and not failing and not unclosed else 1)


if __name__ == "__main__":
    main()
