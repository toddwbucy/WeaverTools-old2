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
    seeds = [int(part.strip()) for part in text.split(",") if part.strip()]
    if not seeds:
        raise ValueError("the seed schedule is empty")
    if len(set(seeds)) != len(seeds):
        raise ValueError("the seed schedule repeats a value")
    return seeds


def with_declared_seed(declaration, seed):
    """The declaration text with its one `seed:` line rewritten. Exactly one
    line, or the declaration is not the shape this override understands."""
    swapped, n = SEED_LINE.subn(lambda m: f"{m.group(1)}{seed}", declaration, count=2)
    if n != 1:
        raise ValueError(f"the declaration carries {n} seed lines, not one")
    return swapped


def seed_for(schedule, iteration, cell_index):
    """Which seed a cell takes: rotated by cell and offset by sweep, so
    over as many sweeps as there are seeds every cell meets every seed."""
    return schedule[(cell_index + iteration - 1) % len(schedule)]

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
    return {
        "count": len(vals),
        "mean": round(statistics.fmean(vals), 6),
        "max": round(max(vals), 6),
        "min": round(min(vals), 6),
    }


def run_session(cfg, probe, depth, iteration, declared_seed=None):
    """One matrix cell: serve, unload, reload, reissue, compare.

    The agent is left unloaded whichever path this takes, so a cell that
    fails does not hold the device against the next one. Where a seed
    schedule stands, `declared_seed` is what the declaration was rewritten
    to before this cell, and the record's own `sampling.seed` is read back
    beside it: a session whose record does not carry the seed it was
    declared under is an apparatus fault and never a result.
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
        base.admin(cfg, "unload")
        if base.admin(cfg, "load").get("kind") != "state":
            rec["verdict"] = "load refused"
            return rec
        if not base.wait_socket(cfg):
            rec["verdict"] = "gate socket never stood"
            return rec

        source_runs = set()
        for t in texts:
            close = base.gate_turn(cfg, t)
            if close.get("kind") != "answered":
                rec["verdict"] = f"source turn not answered: {close.get('kind')}"
                return rec
            source_runs.add(close.get("run"))

        # The closes name the run, so the wait is on that run rather than on
        # whichever is newest: a wait on the newest is satisfied by the
        # previous cell's run, which carries the same turn count at this
        # depth, and the reissue would compare against a stale record.
        if len(source_runs) != 1 or None in source_runs:
            rec["verdict"] = "the source turns did not share one run"
            return rec
        source_run = source_runs.pop()
        rec["source_run"] = source_run
        source_turns, _ = base.await_turns(cfg["trace"], depth, source_run)
        if len(source_turns) != depth:
            rec["verdict"] = f"expected {depth} source turns, found {len(source_turns)}"
            return rec
        # **The seed the record carries is read back, never assumed.** The
        # declared seed rides every `model.request` as `sampling.seed`, per
        # the trace's shape, and the falsifier of Run 1 is about whether
        # that value reaches the sampler, which is a question the deposit
        # can only ask if the value it declared is the value it recorded.
        recorded = {base.pointer(t["payload"]["model.request"], "/sampling/seed")
                    for t in source_turns}
        if len(recorded) != 1:
            # One run, one declared seed: turns recorded under different
            # seeds are the apparatus, schedule or no schedule.
            rec["recorded_seed"] = sorted(recorded, key=str)
            rec["verdict"] = (f"the source turns were recorded under"
                              f" {len(recorded)} seeds: {rec['recorded_seed']}")
            return rec
        rec["recorded_seed"] = recorded.pop()
        if declared_seed is not None and rec["recorded_seed"] != declared_seed:
            rec["verdict"] = (f"the declared seed did not reach the record:"
                              f" declared {declared_seed},"
                              f" recorded {rec['recorded_seed']}")
            return rec

        base.admin(cfg, "unload")
        if base.admin(cfg, "load").get("kind") != "state":
            rec["verdict"] = "reload refused"
            return rec
        if not base.wait_socket(cfg):
            rec["verdict"] = "gate socket never stood after reload"
            return rec

        # Reissued from the record rather than from this script's
        # constants, because the record is the artifact under test.
        runs_seen = set()
        for st in source_turns:
            close = base.gate_turn(cfg, st["text"])
            if close.get("kind") != "answered":
                rec["verdict"] = f"reissue {st['turn']} closed {close.get('kind')}"
                return rec
            runs_seen.add(close.get("run"))
        if len(runs_seen) != 1 or None in runs_seen or source_run in runs_seen:
            rec["verdict"] = "reissues did not land in one fresh run"
            return rec
        replay_run = runs_seen.pop()
        rec["replay_run"] = replay_run

        replay_all, _ = base.await_turns(
            cfg["trace"], len(source_turns), replay_run)
        if not replay_all:
            rec["verdict"] = f"the closes named run {replay_run}, absent from the trace"
            return rec
        # **A short replay read is the sink, not the model.** It reaches its
        # own verdict rather than DIVERGED, which is the strongest negative
        # this harness emits and means the model did not reproduce. The two
        # must not share a word in an unattended run, and a sink one turn
        # behind is exactly the shape this harness was fixed for.
        if len(replay_all) < len(source_turns):
            rec["verdict"] = (
                f"replay read short: expected {len(source_turns)} turns,"
                f" found {len(replay_all)} - the record is incomplete"
            )
            return rec
        # **The replay's seed is read back like the source's.** Both halves
        # load from one declaration, so a replay recorded under another seed
        # is the apparatus and not the model, and the sampling-knobs check
        # below would otherwise report it as DIVERGED.
        replay_seeds = {base.pointer(t["payload"]["model.request"], "/sampling/seed")
                        for t in replay_all}
        rec["replay_recorded_seed"] = (replay_seeds.pop() if len(replay_seeds) == 1
                                       else sorted(replay_seeds, key=str))
        if rec["replay_recorded_seed"] != rec["recorded_seed"]:
            rec["verdict"] = (f"the replay was recorded under another seed:"
                              f" source {rec['recorded_seed']},"
                              f" replay {rec['replay_recorded_seed']}")
            return rec
        replay_by = {t["turn"]: t for t in replay_all}

        # A replay carrying surplus turns is interleaved traffic and is
        # never a match, however well the turns it shares agree.
        all_match = len(replay_all) == len(source_turns)
        for st in source_turns:
            rt = replay_by.get(st["turn"])
            if rt is None:
                all_match = False
                rec["turns"].append({"turn": st["turn"], "missing": True})
                continue
            checks = base.compare_turn(st, rt)
            matched = all(c["match"] for c in checks)
            all_match = all_match and matched
            # The emission's digest rides beside the verdict so a reading
            # across sessions, which is what a varied seed is read by, needs
            # no second walk of the trace: two sessions of one probe under
            # two seeds diverged or did not by their digests alone.
            emission = base.pointer(st["payload"]["model.output"], "/emission")
            rec["turns"].append({
                "turn": st["turn"],
                "is_probe": st["text"] == text,
                "matched": matched,
                "failed_checks": [c["check"] for c in checks if not c["match"]],
                "entropy": entropies_of(st),
                "source_ms": base.whole_ms(st),
                "replay_ms": base.whole_ms(rt),
                "emission_sha256": hashlib.sha256(
                    json.dumps(emission, sort_keys=True).encode()).hexdigest(),
            })
        rec["verdict"] = "REPRODUCED" if all_match else "DIVERGED"
        return rec
    except Exception as exc:  # an unattended run records rather than dies
        rec["verdict"] = f"error: {type(exc).__name__}: {exc}"
        return rec
    finally:
        base.admin(cfg, "unload")


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
    # `is not None` rather than truthiness: an explicitly empty schedule is
    # refused by the parser, an omitted one is no schedule.
    schedule = None
    if args.seed_schedule is not None:
        try:
            schedule = parse_seed_schedule(args.seed_schedule)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)

    with open(args.config) as f:
        cfg = json.load(f)
    os.makedirs(args.outdir, exist_ok=True)

    with open(cfg["declaration"]) as f:
        original = f.read()
    # `standing` is the declaration this run works from: the operator's own,
    # or the artifact-swapped one, and the seed rewrite per session starts
    # from it so the two overrides compose rather than overwrite each other.
    standing = original
    if args.artifact:
        swapped, n = re.subn(r"(artifact:\s*).*", r"\g<1>" + args.artifact,
                             original, count=1)
        if n != 1:
            print("no artifact line in the declaration", file=sys.stderr)
            sys.exit(2)
        standing = swapped
    if schedule:
        # Refused before any load and before anything is written: a
        # declaration without exactly one seed line is not one this override
        # can vary, and the refusal leaves the operator's file untouched.
        try:
            with_declared_seed(standing, schedule[0])
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)

    deadline = time.time() + args.hours * 3600.0
    # Opened before the first load so the journal read at the summary
    # cannot reach back past this run.
    run_started = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1))
    results, iteration = [], 0
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
    if schedule:
        log(f"declared seed schedule: {schedule}")
    try:
        # **The swap itself is inside the cleanup scope**: opening the file
        # for writing truncates it before the write, so a write that fails
        # outside the `try` would leave the operator's declaration empty
        # with nothing to restore it. Everything after it is here for the
        # same reason: `ldd` missing raises, hashing 142 MiB can be
        # interrupted, and either one outside the `try` would leave the
        # declaration holding this run's artifact.
        if args.artifact:
            with open(cfg["declaration"], "w") as fh:
                fh.write(standing)
        opening_spu = base._resolve_spu(cfg)
        libraries = base.engine_libraries(cfg, opening_spu)
        binaries = base.weaver_binaries(cfg, opening_spu)
        tools = base.toolchain(cfg)
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
                    declared_seed = None
                    if schedule:
                        declared_seed = seed_for(schedule, iteration, cell_index)
                        with open(cfg["declaration"], "w") as fh:
                            fh.write(with_declared_seed(standing, declared_seed))
                    cell_index += 1
                    started = time.time()
                    rec = run_session(cfg, probe, depth, iteration, declared_seed)
                    rec["seconds"] = round(time.time() - started, 1)
                    results.append(rec)
                    ent = ""
                    for t in rec["turns"]:
                        if t.get("is_probe") and t.get("entropy"):
                            ent = f" H_mean={t['entropy']['mean']}"
                    seed_note = f" seed={declared_seed}" if schedule else ""
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
        if args.artifact or schedule:
            with open(cfg["declaration"], "w") as fh:
                fh.write(original)
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
    # By seed where a schedule stood: the within-session verdict per
    # condition, so a seed that fails to reproduce is visible on its own.
    by_seed = {}
    if schedule:
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

    try:
        bindings = base.device_bindings(cfg, run_started)
    except (Exception, KeyboardInterrupt) as e:  # noqa: BLE001 - degrades to a note
        # `_why` here too: widening this catch to include `KeyboardInterrupt`
        # opened the empty-reason path, `journalctl` over a seven-hour window
        # being a call a Ctrl-C can land in.
        bindings = [{"unreadable": f"the device read failed: {base._why(e)}"}]
    summary = {
        "serving_device": (bindings[0] if len(bindings) == 1
                           else {"varied": bindings}),
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
    # **The window joins the verdict here too**, per #399's review: the
    # confirm and trace-gen drivers already exit 1 over green sessions when
    # the provenance moved, and one seam answering the same question two
    # ways at the exit code is #379's opening defect relocated. The
    # serving-device envelope is not in the gate: it is not a two-read
    # close, and a multi-device report is its own field rather than a
    # moved window.
    window_held = all(
        (summary[k] or {}).get("status") == "unchanged"
        for k in ("engine_libraries", "weaver_binaries", "toolchain"))
    if total and good == total and not window_held:
        log("sessions reproduced but the provenance window did not hold"
            " quiet - not a reproduction result")
    sys.exit(0 if total and good == total and window_held else 1)


if __name__ == "__main__":
    main()
