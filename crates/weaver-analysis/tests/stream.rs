//! conforms: analysis-summary-reports-the-record-session
//! conforms: analysis-summary-reports-the-record-digest
//! conforms: analysis-summary-reports-the-prefix-length
//! conforms: analysis-summary-reports-the-run-and-its-conditions
//! conforms: analysis-reading-drains-within-a-turn
//! conforms: analysis-signals-keep-absence
//! conforms: analysis-summary-reports-residency
//! conforms: analysis-summary-reports-the-record-identity
//!
//! The streaming reading's watches, per `weaver-analysis-Spec` section 5.
//! The fixtures are shaped like the real records the live run drained.

use weaver_analysis::capture::{Key, Streaming};
use weaver_analysis::{Drained, Signals, drain};

fn record(closed: Option<&str>, trailing: &str) -> String {
    let mut lines = vec![
        r#"{"session":"s","run":"r","sequence":"0","kind":"replay.opened","payload":{"reader_elected":false}}"#.to_string(),
        r#"{"session":"s","run":"r","turn":"t-1","sequence":"1","kind":"residual.column","payload":{"position":10,"layers":2,"width":2,"values":[[1.0,2.0],[3.0,4.0]]}}"#.to_string(),
        r#"{"session":"s","run":"r","turn":"t-1","sequence":"2","kind":"residual.column","payload":{"position":11,"layers":2,"width":2,"values":[[5.0,6.0],[7.0,8.0]]}}"#.to_string(),
        // The closing count is 107 against a three-token delta and two drawn
        // tokens, the shape of a first generation: the identity prefix is
        // resident and no member carries it, so a derived count would say 3.
        r#"{"session":"s","run":"r","turn":"t-1","sequence":"3","kind":"model.output","payload":{"emission":"ab","finish":"stop","resident":107,"capacity":8192}}"#.to_string(),
        r#"{"session":"s","run":"r","turn":"t-1","sequence":"4","kind":"model.measurement","payload":{"input_tokens":[1,2,3],"output_tokens":[100,200],"entropies":[1.5,2.5],"surprisals":[0.5,9.5],"perplexity":2.0,"weights_hash":"23dd1056"}}"#.to_string(),
    ];
    if let Some(outcome) = closed {
        lines.push(format!(
            r#"{{"session":"s","run":"r","sequence":"5","kind":"replay.closed","payload":{{"outcome":{{"kind":"{outcome}"}}}}}}"#
        ));
    }
    if !trailing.is_empty() {
        lines.push(trailing.to_string());
    }
    lines.join("\n") + "\n"
}

/// **The bracket's close ends the reading, not the stream's end.** A
/// pipe's writer is the agent, which holds it open for the run's whole
/// residency, so a reader waiting for end-of-stream waits for the unload.
/// The live run of 2026-09-02 found exactly that: the reading never
/// emitted while the worker stood.
///
/// Perturbation: answer `Continue` at `replay.closed` and this fails, the
/// drain running past the close into whatever follows. Watched under
/// exactly that change.
#[test]
fn the_close_ends_the_drain_and_the_stream_does_not() {
    let after = r#"{"session":"s","run":"r","turn":"t-2","sequence":"6","kind":"residual.column","payload":{"position":99,"layers":1,"width":1,"values":[[42.0]]}}"#;
    let text = record(Some("certified"), after);
    let mut seen: Vec<(Key, u32)> = Vec::new();
    let mut pair = |key: &Key, _column: &[f32], token: u32| seen.push((key.clone(), token));
    let mut reader = Streaming::new(vec![10], &mut pair);
    let ended = drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
    assert_eq!(ended, Drained::Stopped, "the close stops the drain");
    assert!(reader.certified());
    assert!(
        !reader.kept.keys().any(|(_, p)| *p == 99),
        "nothing past the close was read: {:?}",
        reader.kept.keys().collect::<Vec<_>>()
    );
    assert_eq!(seen.len(), 2, "both positions of the turn paired");
}

/// **What a reading holds is bounded by the analyst's named positions.**
/// The turn's final layers pass through the pairing and are dropped; only
/// the named positions' full columns stay.
///
/// Perturbation: keep every column rather than the named ones and this
/// fails, the second position appearing in what was held. Watched under
/// exactly that change.
#[test]
fn the_reading_holds_only_what_was_named() {
    let text = record(Some("certified"), "");
    let mut pair = |_: &Key, _: &[f32], _: u32| {};
    let mut reader = Streaming::new(vec![11], &mut pair);
    drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
    let held: Vec<u64> = reader.kept.keys().map(|(_, p)| *p).collect();
    assert_eq!(held, vec![11], "only the named position is held: {held:?}");
}

/// **The outcome the record states is what a reading is gated on.**
#[test]
fn the_outcome_is_read_from_the_close() {
    for (closed, want) in [
        (Some("certified"), Some("certified")),
        (Some("diverged"), Some("diverged")),
        (Some("abandoned"), Some("abandoned")),
        (None, None),
    ] {
        let text = record(closed, "");
        let mut pair = |_: &Key, _: &[f32], _: u32| {};
        let mut reader = Streaming::new(vec![], &mut pair);
        drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
        assert_eq!(reader.outcome.as_deref(), want, "closed {closed:?}");
        assert_eq!(reader.certified(), want == Some("certified"));
    }
}

/// **The signals reader rides the same drain and needs nothing else**: no
/// lens, no weights, no tap. The entropies ride every generation and the
/// surprisals ride their election, and an absent vector stays absent.
///
/// Perturbation: fill an absent surprisal with zero in the reader and this
/// fails, the bare record's points carrying a surprisal the election never
/// produced. Watched under exactly that change.
#[test]
fn the_signals_series_pairs_and_keeps_absence() {
    let text = record(Some("certified"), "");
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
    let series = &reader.series;
    assert_eq!(series.points.len(), 2);
    assert_eq!(series.points[0].token, 100);
    assert_eq!(series.points[0].entropy, Some(1.5));
    assert_eq!(series.points[1].surprisal, Some(9.5));
    assert_eq!(series.generations.len(), 1);
    assert_eq!(series.generations[0].turn.as_deref(), Some("t-1"));
    assert_eq!(series.generations[0].perplexity, Some(2.0));

    // A record whose surprisal election did not stand carries entropies
    // and no surprisals, and the reading says so rather than inventing.
    let bare = text.replace(r#","surprisals":[0.5,9.5]"#, "");
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(bare.as_bytes()), &mut reader);
    assert!(reader.series.points.iter().all(|p| p.surprisal.is_none()));
    assert!(reader.series.points.iter().all(|p| p.entropy.is_some()));
    assert!(
        reader.series.spikes(2.0).is_empty(),
        "no surprisal, no spike"
    );
}

/// **The summary reports the residency and derives nothing**, per
/// `weaver-analysis-Spec` section 5 as of 2026-09-05: the resident count is
/// the one `model.output` carried as the generation closed, the output
/// count is the drawn tokens, and a generation whose record holds no
/// `model.output` carries no resident count rather than a derived one.
///
/// Perturbation: report the previous closing count plus the delta's length
/// in the resident's place and this fails, the fixture's first generation
/// answering 3 where the record says 107, the identity prefix being resident
/// and in no member. Watched under exactly that change.
#[test]
fn the_summary_reports_the_residency_and_derives_nothing() {
    let text = record(Some("certified"), "");
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
    let generation = &reader.series.generations[0];
    assert_eq!(
        generation.resident,
        Some(107),
        "the closing count as reported"
    );
    assert_eq!(
        generation.output_count, 2,
        "the drawn tokens, terminator outside"
    );

    // No `model.output` for the generation: absent, never derived.
    let without = text
        .lines()
        .filter(|l| !l.contains("\"kind\":\"model.output\""))
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(without.as_bytes()), &mut reader);
    assert_eq!(reader.series.generations[0].resident, None);
    assert_eq!(reader.series.generations[0].output_count, 2);
}

/// **The summary reports the record's identity as spelled**, per
/// `weaver-analysis-Spec` section 5 as of 2026-09-06: the weights hash
/// crosses verbatim, the sentinel crosses as the empty string it is, and a
/// measurement carrying no member crosses absent, so a reader tells a
/// failed identity from an older record.
///
/// Perturbation: fold the empty string into `None` and this fails on the
/// sentinel case. Watched under exactly that change.
#[test]
fn the_summary_reports_the_record_identity_as_spelled() {
    let text = record(Some("certified"), "");
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
    assert_eq!(
        reader.series.generations[0].weights_hash.as_deref(),
        Some("23dd1056"),
        "the hash crosses as the record spelled it"
    );

    let sentinel = text.replace("\"weights_hash\":\"23dd1056\"", "\"weights_hash\":\"\"");
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(sentinel.as_bytes()), &mut reader);
    assert_eq!(
        reader.series.generations[0].weights_hash.as_deref(),
        Some(""),
        "the sentinel is the record's fact and crosses as the empty string"
    );

    let without = text.replace(",\"weights_hash\":\"23dd1056\"", "");
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(without.as_bytes()), &mut reader);
    assert_eq!(
        reader.series.generations[0].weights_hash, None,
        "no member crosses absent"
    );
}

/// **A spike is a position that clears the caller's bar**, stated in
/// deviations because what counts as a spike depends on the series.
#[test]
fn the_spikes_are_the_positions_that_clear_the_bar() {
    let mut text = record(Some("certified"), "");
    text = text.replace(
        r#""output_tokens":[100,200],"entropies":[1.5,2.5],"surprisals":[0.5,9.5]"#,
        r#""output_tokens":[1,2,3,4],"entropies":[1.0,1.0,1.0,1.0],"surprisals":[1.0,1.0,1.0,20.0]"#,
    );
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
    let spikes = reader.series.spikes(1.5);
    assert_eq!(spikes.len(), 1, "one position turned");
    assert_eq!(spikes[0].ordinal, 3);
    assert_eq!(spikes[0].token, 4);
}

/// **A close from another run ends no reading of this one.** A record may
/// hold several brackets, and one pass's outcome vouching for another's
/// columns would be a certification borrowed rather than earned.
///
/// Perturbation: take any close as this reading's and this fails, the
/// foreign certified close licensing columns whose own bracket never
/// closed. Watched under exactly that change.
#[test]
fn a_close_from_another_run_certifies_nothing() {
    let mut text = record(None, "");
    text.push_str(
        "{\"session\":\"s\",\"run\":\"other\",\"sequence\":\"9\",\"kind\":\"replay.closed\",\"payload\":{\"outcome\":{\"kind\":\"certified\"}}}\n",
    );
    let mut pair = |_: &Key, _: &[f32], _: u32| {};
    let mut reader = Streaming::new(vec![], &mut pair);
    let ended = drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
    assert_eq!(ended, Drained::Exhausted, "no close of this run arrived");
    assert!(!reader.certified(), "another run's close certifies nothing");
    assert_eq!(reader.outcome, None);
}

/// **A turn whose columns and drawn tokens disagree refuses.** A zip would
/// pair a prefix and drop the rest without saying so, where the count's
/// disagreement is the 13.10 fault the SPU refuses on its own side.
///
/// Perturbation: restore the truncating zip and this fails, the reading
/// pairing one position and reporting nothing wrong. Watched under
/// exactly that change.
#[test]
fn a_turn_whose_counts_disagree_refuses() {
    let text = record(Some("certified"), "")
        .replace(r#""output_tokens":[100,200]"#, r#""output_tokens":[100]"#);
    let mut pair = |_: &Key, _: &[f32], _: u32| {};
    let mut reader = Streaming::new(vec![], &mut pair);
    match drain(std::io::Cursor::new(text.as_bytes()), &mut reader) {
        Drained::Refused(why) => assert!(why.contains("2 columns against 1"), "{why}"),
        other => panic!("the counts must refuse: {other:?}"),
    }
}

/// **A serving record's series has no gate, and a diagnostic record's
/// does.** A serving record is an account of what happened rather than a
/// claim that something was reproduced, so nothing gates it; a diagnostic
/// record carries a bracket, and a series from an uncertified replay is a
/// picture of an unknown run exactly as a readout is.
#[test]
fn the_series_is_gated_only_where_a_bracket_exists() {
    let serving = concat!(
        r#"{"session":"s","run":"r","sequence":"0","kind":"load","payload":{"tee":{}}}"#,
        "\n",
        r#"{"session":"s","run":"r","turn":"t-1","sequence":"1","kind":"model.measurement","payload":{"output_tokens":[7],"entropies":[1.0]}}"#,
        "\n",
    );
    let mut reader = Signals::default();
    drain(std::io::Cursor::new(serving.as_bytes()), &mut reader);
    assert!(!reader.diagnostic(), "a load opens a serving record");
    assert!(reader.licensed(), "a serving record needs no certificate");
    assert_eq!(reader.series.points.len(), 1);

    for (closed, licensed) in [
        (Some("certified"), true),
        (Some("diverged"), false),
        (None, false),
    ] {
        let mut reader = Signals::default();
        drain(
            std::io::Cursor::new(record(closed, "").as_bytes()),
            &mut reader,
        );
        assert!(
            reader.diagnostic(),
            "replay.opened opens a diagnostic record"
        );
        assert_eq!(reader.licensed(), licensed, "closed {closed:?}");
    }
}

/// **A malformed line is skipped rather than fatal**, per section 2's
/// reader rules carried into the drain.
///
/// **Both readers stop where their record's bracket closes**, and a
/// serving record - which carries no bracket - is read to its end. That
/// is a property of what is read rather than of the drain.
#[test]
fn a_malformed_line_does_not_end_the_stream() {
    let text = record(Some("certified"), "").replace(
        r#"{"session":"s","run":"r","turn":"t-1","sequence":"2","#,
        r#"{ this is not an event "#,
    );
    let mut reader = Signals::default();
    let ended = drain(std::io::Cursor::new(text.as_bytes()), &mut reader);
    assert_eq!(ended, Drained::Stopped, "the record's own close ends it");
    assert_eq!(reader.series.points.len(), 2, "the measurement still read");
}

/// **The default spread is first, last, and evenly between**, per Spec
/// section 5 as of 2026-09-04. Perturbation: index by `i * len / count`
/// and the last position drops out of the eight; skip the dedup and a
/// record of nine positions yields a repeated one at the join.
#[test]
fn the_default_spread_is_first_last_and_evenly_between() {
    use weaver_analysis::capture::spread;
    let record: Vec<u64> = (100..=170).collect();
    let eight = spread(&record, 8);
    assert_eq!(eight, vec![100, 110, 120, 130, 140, 150, 160, 170]);
    assert_eq!(
        spread(&[5, 6, 7], 8),
        vec![5, 6, 7],
        "eight or fewer is every position"
    );
    assert_eq!(
        spread(&[7, 5, 6, 5], 8),
        vec![5, 6, 7],
        "ordered and deduplicated"
    );
    let nine = spread(&(0..9).collect::<Vec<u64>>(), 8);
    assert_eq!(nine.first(), Some(&0));
    assert_eq!(nine.last(), Some(&8));
    assert_eq!(
        nine.len(),
        nine.iter().collect::<std::collections::BTreeSet<_>>().len()
    );
    assert!(spread(&[], 8).is_empty());
    assert_eq!(spread(&[3, 4], 1), vec![3]);
}

/// **The positions read ends at the bracket's own close**, the record
/// boundary the reading keeps, so a trailing bracket in the same file adds
/// nothing to the spread. Perturbation: drop the `replay.closed` arm of
/// `Positions::event` and the trailing position joins the held list.
#[test]
fn the_positions_read_stops_at_the_close() {
    use weaver_analysis::capture::Positions;
    let trailing = concat!(
        r#"{"session":"s","run":"r-2","kind":"replay.opened","sequence":"9"}"#,
        "\n",
        r#"{"session":"s","run":"r-2","turn":"t-1","kind":"residual.column","sequence":"10","#,
        r#""payload":{"position":99,"layer":0,"values":[[1.0]]}}"#,
        "\n",
    );
    let mut held = Positions::default();
    let drained = drain(record(Some("certified"), trailing).as_bytes(), &mut held);
    assert!(matches!(drained, Drained::Stopped), "{drained:?}");
    assert!(
        !held.held.contains(&99),
        "the trailing bracket's position is not held"
    );
    assert!(!held.held.is_empty(), "the bracket's own positions are");
}

/// **An absent member is omitted at the wire and never rendered null**,
/// the wire half of the identity rule, per `weaver-analysis-Spec`
/// section 5. The reader's `Option` is a fact about the record, and a
/// `null` on the wire would say the record carried the member and the
/// member carried nothing. This runs the `signals` verb through the
/// binary because the rendering is the composition root's and no library
/// call reaches it, which is what left this half unwatched until now.
///
/// Perturbation: in `main.rs`, render the option directly - insert
/// `serde_json::json!(g.turn)` in `render_generation`'s first arm rather
/// than inserting the string only under `Some` - and the summary carries
/// `"turn": null`. Watched under exactly that change.
#[test]
fn an_absent_member_is_omitted_at_the_wire_and_never_rendered_null() {
    let dir = std::env::temp_dir().join(format!("weaver-analysis-wire-{}", std::process::id()));
    std::fs::create_dir_all(&dir).expect("temp dir");
    // Removed when the test ends, pass or fail: the guard drops on the
    // unwind a failed assertion takes as on a clean return (#690 item C2.9).
    struct Guard(std::path::PathBuf);
    impl Drop for Guard {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    let _guard = Guard(dir.clone());
    let binary = env!("CARGO_BIN_EXE_weaver-analysis");

    let summary = |text: &str, name: &str| -> serde_json::Value {
        let path = dir.join(name);
        std::fs::write(&path, text).expect("the record writes");
        let out = std::process::Command::new(binary)
            .args(["signals", path.to_str().unwrap()])
            .output()
            .expect("runs");
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        let stdout = String::from_utf8(out.stdout).expect("utf8");
        let first = stdout.lines().next().expect("a summary line");
        serde_json::from_str(first).expect("json")
    };

    // The record as the fixture spells it: every member the summary
    // carries is present, together with its run and session.
    let whole = summary(&record(Some("certified"), ""), "whole.ndjson");
    let generation = whole["generations"][0].as_object().expect("an object");
    let mut members: Vec<&str> = generation.keys().map(String::as_str).collect();
    members.sort_unstable();
    assert_eq!(
        members,
        vec![
            "output_count",
            "perplexity",
            "resident",
            "run",
            "session",
            "turn",
            "weights_hash"
        ]
    );
    assert_eq!(generation["turn"], "t-1");

    // The same record with no turn on any envelope and no hash on the
    // measurement: the two members are gone from the object rather than
    // standing in it as null.
    let text = record(Some("certified"), "")
        .replace(r#""turn":"t-1","#, "")
        .replace(r#","weights_hash":"23dd1056""#, "");
    let bare = summary(&text, "bare.ndjson");
    let generation = bare["generations"][0].as_object().expect("an object");
    for absent in ["turn", "weights_hash"] {
        assert!(
            !generation.contains_key(absent),
            "{absent} is omitted rather than rendered: {generation:?}"
        );
    }
    assert!(
        generation.contains_key("output_count"),
        "what the record held still crosses: {generation:?}"
    );

    std::fs::remove_dir_all(&dir).ok();
}

// The first E2 watch: neither a later generation nor a suffix can stand in
// for the first generation of a whole run.
#[test]
fn the_prefix_comes_only_from_the_first_generation_of_a_whole_run() {
    let full = prefix_record();
    for (record, expected) in [
        (full.clone(), Some(100)),
        (
            full.lines().skip(1).collect::<Vec<_>>().join("\n") + "\n",
            None,
        ),
        (full.replace("\"resident\":107", "\"unrelated\":107"), None),
        (
            full.lines()
                .filter(|l| !l.contains("unload"))
                .collect::<Vec<_>>()
                .join("\n")
                + "\n",
            None,
        ),
        (
            full.lines()
                .filter(|l| !(l.contains("model.measurement") && l.contains("t1")))
                .collect::<Vec<_>>()
                .join("\n")
                + "\n",
            None,
        ),
    ] {
        let out = signals_from_pipe(&record, &[]);
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        let summary: serde_json::Value =
            serde_json::from_slice(out.stdout.split(|b| *b == b'\n').next().unwrap()).unwrap();
        let generations = summary["generations"].as_array().unwrap();
        assert!(!generations.is_empty());
        for generation in generations {
            assert_eq!(
                generation.get("prefix_length").and_then(|v| v.as_u64()),
                expected,
                "only the first generation after load can supply the prefix: {generation}"
            );
        }
    }
}

fn prefix_record() -> String {
    [
        r#"{"session":"source","run":"r","sequence":"0","kind":"load","payload":{}}"#,
        r#"{"session":"source","run":"r","turn":"t1","sequence":"1","kind":"model.request","payload":{"sampling":{"generation_seed":11,"seed":7,"temperature":0.50}}}"#,
        r#"{"session":"source","run":"r","turn":"t1","sequence":"2","kind":"model.output","payload":{"resident":107}}"#,
        r#"{"session":"source","run":"r","turn":"t1","sequence":"3","kind":"model.measurement","payload":{"input_tokens":[1,2,3,4],"output_tokens":[8,9]}}"#,
        r#"{"session":"source","run":"r","turn":"t2","sequence":"4","kind":"model.request","payload":{"sampling":{"generation_seed":22,"seed":7,"temperature":0.50}}}"#,
        r#"{"session":"source","run":"r","turn":"t2","sequence":"5","kind":"model.output","payload":{"resident":215}}"#,
        r#"{"session":"source","run":"r","turn":"t2","sequence":"6","kind":"model.measurement","payload":{"input_tokens":[5,6],"output_tokens":[10,11,12]}}"#,
        r#"{"session":"source","run":"r","sequence":"7","kind":"unload","payload":{}}"#,
    ].join("\n") + "\n"
}

// A child may refuse before reading stdin. Its status and stderr still decide
// the result; only the resulting broken pipe is an expected write failure.
fn write_signals_input(mut input: std::process::ChildStdin, record: &[u8]) {
    use std::io::{ErrorKind, Write};
    if let Err(error) = input.write_all(record) {
        assert_eq!(error.kind(), ErrorKind::BrokenPipe, "{error}");
    }
}

/// Wait for an actual early refusal before writing, making the pipe failure
/// deterministic. Restoring write_all(...).unwrap() must fail this watch.
#[test]
fn signals_input_tolerates_a_child_that_already_refused() {
    use std::process::{Command, Stdio};
    let mut child = Command::new(env!("CARGO_BIN_EXE_weaver-analysis"))
        .args(["signals", "-", "not-a-number"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let input = child.stdin.take().unwrap();
    assert!(!child.wait().unwrap().success());
    write_signals_input(input, b"record the refusing child never reads\n");
    let result = child.wait_with_output().unwrap();
    assert!(!result.status.success());
    assert!(result.stdout.is_empty());
    assert!(
        String::from_utf8_lossy(&result.stderr)
            .contains("the spike bar is not a finite number: not-a-number")
    );
}

fn signals_from_pipe(record: &str, arguments: &[&str]) -> std::process::Output {
    use std::process::{Command, Stdio};
    let mut child = Command::new(env!("CARGO_BIN_EXE_weaver-analysis"))
        .args(["signals", "-"])
        .args(arguments)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    write_signals_input(child.stdin.take().unwrap(), record.as_bytes());
    child.wait_with_output().unwrap()
}

fn summary_value(text: &str, arguments: &[&str]) -> serde_json::Value {
    let out = signals_from_pipe(text, arguments);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(out.stdout.split(|b| *b == b'\n').next().unwrap()).unwrap()
}

/// Each run hashes its own raw lines, unknown kinds included, without
/// re-encoding, borrowing another run's bytes, or normalizing delimiters.
#[test]
fn the_digest_is_independently_recomputed_per_run_over_drained_bytes() {
    use sha2::{Digest, Sha256};
    for ending in ["\n", "\r\n"] {
        let first = prefix_record().replace("\n", ending).replace(
            "\"sequence\":\"7\",\"kind\":\"unload\"",
            "\"sequence\":\"8\",\"kind\":\"unload\"",
        );
        let unknown = format!(
            "  {{\"session\":\"source\",\"run\":\"r\",\"sequence\":\"7\",\"kind\":\"future.kind\",\"payload\":{{\"z\":1.00, \"a\":null}}}}{ending}"
        );
        let mut lines: Vec<_> = first.split_inclusive('\n').map(str::to_string).collect();
        lines.insert(lines.len() - 1, unknown);
        let first = lines.concat();
        let second = first
            .replace("\"run\":\"r\"", "\"run\":\"other\"")
            .replace("\"session\":\"source\"", "\"session\":\"second\"")
            .replace("\"resident\":107", "\"resident\":57");
        let mixed: String = first
            .split_inclusive('\n')
            .zip(second.split_inclusive('\n'))
            .flat_map(|(a, b)| [a, b])
            .collect();
        let summary = summary_value(&mixed, &[]);
        let entries = summary["generations"].as_array().unwrap();
        assert_eq!(entries.len(), 4);
        for (entry, (run, session, prefix, bytes)) in entries.iter().zip([
            ("r", "source", 100, &first),
            ("other", "second", 50, &second),
            ("r", "source", 100, &first),
            ("other", "second", 50, &second),
        ]) {
            assert_eq!(entry["run"], run);
            assert_eq!(entry["session"], session);
            assert_eq!(entry["prefix_length"], prefix);
            assert_eq!(
                entry["digest"],
                format!("{:x}", Sha256::digest(bytes.as_bytes()))
            );
        }
    }
}

#[test]
fn incomplete_runs_never_vouch_for_a_digest_or_a_prefix() {
    let full = prefix_record();
    for text in [
        full.lines().skip(1).collect::<Vec<_>>().join("\n") + "\n",
        full.lines()
            .filter(|l| !l.contains("unload"))
            .collect::<Vec<_>>()
            .join("\n")
            + "\n",
    ] {
        let summary = summary_value(&text, &[]);
        for entry in summary["generations"].as_array().unwrap() {
            assert!(entry.get("digest").is_none());
            assert!(entry.get("prefix_length").is_none());
            assert_eq!(entry["run"], "r");
        }
    }
}

#[test]
fn missing_first_inputs_or_unreadable_measurements_never_borrow_a_later_prefix() {
    let full = prefix_record();
    for text in [
        full.replace("\"input_tokens\":[1,2,3,4]", "\"unrelated\":[1,2,3,4]"),
        full.replace("\"output_tokens\":[8,9]", "\"output_tokens\":null"),
        full.replace("\"resident\":107", "\"resident\":1"),
    ] {
        let summary = summary_value(&text, &[]);
        for entry in summary["generations"].as_array().unwrap() {
            assert!(entry.get("prefix_length").is_none());
            assert!(
                entry.get("digest").is_some(),
                "prefix absence does not cost a whole run its digest"
            );
        }
    }
}

#[test]
fn summaries_keep_run_conditions_raw_and_each_absence_independent() {
    let full = prefix_record().replacen("\"payload\":{}", r#""payload":{"field":4,"lineage":{"through":7, "run":"parent-run","parent":"parent-session"},"stack":{"z":"sha-z", "a":"sha-a"}}"#, 1);
    let out = signals_from_pipe(&full, &[]);
    assert!(out.status.success());
    let raw = String::from_utf8(out.stdout).unwrap();
    assert!(
        raw.contains(r#""effective_sampling":{"generation_seed":11,"seed":7,"temperature":0.50}"#)
    );
    assert!(
        raw.contains(r#""lineage":{"through":7, "run":"parent-run","parent":"parent-session"}"#)
    );
    assert!(raw.contains(r#""stack":{"z":"sha-z", "a":"sha-a"}"#));
    let complete = summary_value(&full, &[]);
    for entry in complete["generations"].as_array().unwrap() {
        assert_eq!(entry["run"], "r");
        assert_eq!(entry["session"], "source");
        assert_eq!(entry["field_depth"], 4);
        assert_eq!(entry["lineage"]["through"], 7);
        assert_eq!(entry["code_identity"]["stack"]["z"], "sha-z");
        for absent in ["device_model", "verdict", "weights_hash", "perplexity"] {
            assert!(
                entry.get(absent).is_none(),
                "{absent} must not be defaulted"
            );
        }
    }
    for (before, after, absent) in [
        ("\"session\":\"source\",", "", "session"),
        ("\"field\":4,", "", "field_depth"),
        ("\"lineage\":", "\"unrelated\":", "lineage"),
        ("\"stack\":", "\"unrelated\":", "code_identity"),
        ("\"sampling\":", "\"unrelated\":", "effective_sampling"),
    ] {
        let summary = summary_value(&full.replace(before, after), &[]);
        for (index, entry) in summary["generations"]
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
        {
            assert!(entry.get(absent).is_none(), "{absent}: {entry}");
            let mut expected = complete["generations"][index].clone();
            expected.as_object_mut().unwrap().remove(absent);
            expected.as_object_mut().unwrap().remove("digest");
            let mut actual = entry.clone();
            actual.as_object_mut().unwrap().remove("digest");
            assert_eq!(actual, expected, "every other member stays independent");
        }
    }
}

/// **The task's verdict crosses once, on the entry for the generation the
/// run's close names**, per `weaver-analysis-web-contract` section 2.2 and
/// #523: a scored run's summary carries it on its last generation's entry
/// and on no other, spelled as the record's `score` spelled it, the ratio as
/// its two terms. A score taken before the run's last turn still crosses on
/// the last entry, the close being the run's and not the score's. A verdict
/// with no denominator crosses with no ratio, an unscored run's summary
/// carries none, and a record holding a second score refuses, the trace
/// having refused to write one (#707). **Where the closing generation
/// produced no entry**, its measurement unreadable or never landed, or the
/// run holds no generation at all, the scored run refuses naming it rather
/// than moving the verdict to an earlier entry (#708 round one), and a scored
/// record that ends before its unload refuses naming the run (round two).
///
/// Perturbations: drop the `score` arm and the verdict never crosses; place
/// it on every entry of the run and the first entry carries one; fall back to
/// the run's last entry where the closing generation has none and the
/// malformed-last case crosses on turn t1; ignore a verdict still held when
/// the drain ends and the truncated scored record reads as unscored. Watched
/// under each.
#[test]
fn the_verdict_crosses_once_on_the_closing_generation() {
    let unload = r#"{"session":"source","run":"r","sequence":"7","kind":"unload","payload":{}}"#;
    let score = |sequence: &str, ratio: &str| {
        format!(
            r#"{{"session":"source","run":"r","sequence":"{sequence}","kind":"score","payload":{{"predicate":"reached-the-goal","passed":true{ratio}}}}}"#
        )
    };
    let terms = r#","ratio":{"measured":14,"denominator":11}"#;
    let scored = prefix_record().replace(unload, &format!("{}\n{unload}", score("7", terms)));
    let summary = summary_value(&scored, &[]);
    let entries = summary["generations"].as_array().unwrap();
    assert_eq!(entries.len(), 2);
    assert!(
        entries[0].get("verdict").is_none(),
        "no verdict on an earlier generation"
    );
    assert_eq!(
        entries[1]["verdict"],
        serde_json::json!({
            "predicate": "reached-the-goal",
            "passed": true,
            "ratio": {"measured": 14, "denominator": 11}
        }),
        "the verdict and its terms on the closing generation"
    );

    let t2 = r#"{"session":"source","run":"r","turn":"t2","sequence":"4""#;
    let early = prefix_record().replace(t2, &format!("{}\n{t2}", score("3b", terms)));
    let summary = summary_value(&early, &[]);
    let entries = summary["generations"].as_array().unwrap();
    assert!(
        entries[0].get("verdict").is_none() && entries[1].get("verdict").is_some(),
        "a score before the last turn still crosses on the close's entry: {summary}"
    );

    let bare = prefix_record().replace(unload, &format!("{}\n{unload}", score("7", "")));
    let summary = summary_value(&bare, &[]);
    assert_eq!(
        summary["generations"][1]["verdict"],
        serde_json::json!({"predicate": "reached-the-goal", "passed": true}),
        "no denominator, no ratio, never a default"
    );

    let unscored = summary_value(&prefix_record(), &[]);
    for entry in unscored["generations"].as_array().unwrap() {
        assert!(
            entry.get("verdict").is_none(),
            "an unscored run carries none"
        );
    }

    let twice = prefix_record().replace(
        unload,
        &format!("{}\n{}\n{unload}", score("6b", terms), score("6c", terms)),
    );
    let out = signals_from_pipe(&twice, &[]);
    assert!(
        !out.status.success(),
        "a record holding a second score refuses rather than choosing one"
    );

    // The close names the run's last generation, and where that generation
    // produced no entry the scored run refuses naming it, rather than the
    // verdict dropping or landing on an earlier generation (#708 round one).
    let malformed_last = scored.replace("\"output_tokens\":[10,11,12]", "\"output_tokens\":null");
    let out = signals_from_pipe(&malformed_last, &[]);
    assert!(
        !out.status.success() && String::from_utf8_lossy(&out.stderr).contains("turn t2"),
        "a closing generation with no readable draws refuses naming its turn: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    let measurement_t2 = r#"{"session":"source","run":"r","turn":"t2","sequence":"6","kind":"model.measurement","payload":{"input_tokens":[5,6],"output_tokens":[10,11,12]}}"#;
    assert!(scored.contains(measurement_t2));
    let unmeasured_last = scored.replace(&format!("{measurement_t2}\n"), "");
    assert!(
        !signals_from_pipe(&unmeasured_last, &[]).status.success(),
        "a closing generation begun and never measured refuses"
    );
    let unmeasured_run = [
        r#"{"session":"source","run":"r","sequence":"0","kind":"load","payload":{}}"#.to_string(),
        score("1", terms),
        r#"{"session":"source","run":"r","sequence":"2","kind":"unload","payload":{}}"#.to_string(),
    ]
    .join("\n")
        + "\n";
    assert!(
        !signals_from_pipe(&unmeasured_run, &[]).status.success(),
        "a scored run with no generation refuses"
    );
    // The end of the stream is the reader's other exit: a scored record that
    // stops before its unload refuses naming the run, where the verdict
    // would otherwise vanish into a summary reporting it absent (#708 round
    // two). An unscored truncated record still reads, its digest and prefix
    // absent as `incomplete_runs_never_vouch_for_a_digest_or_a_prefix` holds.
    let truncated = scored.replace(&format!("{unload}\n"), "");
    assert!(!truncated.contains("unload"));
    let out = signals_from_pipe(&truncated, &[]);
    assert!(
        !out.status.success() && String::from_utf8_lossy(&out.stderr).contains("run r"),
        "a scored record ending before its unload refuses naming the run: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    let unscored_truncated = prefix_record().replace(&format!("{unload}\n"), "");
    assert!(
        signals_from_pipe(&unscored_truncated, &[]).status.success(),
        "an unscored truncated record still reads"
    );
    let malformed_first = scored.replace("\"output_tokens\":[8,9]", "\"output_tokens\":null");
    let summary = summary_value(&malformed_first, &[]);
    let entries = summary["generations"].as_array().unwrap();
    assert_eq!(
        entries.len(),
        1,
        "the malformed first generation produced no entry"
    );
    assert_eq!(
        entries[0]["turn"], "t2",
        "the one entry is the closing generation's"
    );
    assert!(
        entries[0].get("verdict").is_some(),
        "and carries the verdict: {summary}"
    );
}

#[test]
fn sampling_agrees_on_declared_members_and_not_the_generation_seed() {
    let full = prefix_record();
    assert!(signals_from_pipe(&full, &[]).status.success());
    for text in [
        full.replacen("\"seed\":7", "\"seed\":8", 1),
        full.replacen("\"temperature\":0.50", "\"temperature\":0.75", 1),
    ] {
        let out = signals_from_pipe(&text, &[]);
        assert!(!out.status.success());
        assert!(String::from_utf8_lossy(&out.stderr).contains("disagrees on declared sampling"));
    }
}

#[test]
fn a_summary_without_a_run_names_the_older_emitter() {
    use weaver_analysis::signals::GenerationSummary;
    let summary = summary_value(&prefix_record(), &[]);
    for entry in summary["generations"].as_array().unwrap() {
        let valid = serde_json::to_string(entry).unwrap();
        assert_eq!(GenerationSummary::read(&valid).unwrap().run, "r");
        let mut older = entry.clone();
        older.as_object_mut().unwrap().remove("run");
        let refused = GenerationSummary::read(&older.to_string()).unwrap_err();
        assert!(refused.contains("emitter older than 2026-09-09"));
        assert!(refused.contains("run identity absent"));
    }
}

#[test]
fn a_measured_generation_with_no_draws_still_has_a_summary() {
    let text = prefix_record()
        .replace("\"output_tokens\":[8,9]", "\"output_tokens\":[]")
        .replace("\"resident\":107", "\"resident\":5");
    let summary = summary_value(&text, &[]);
    assert_eq!(summary["generations"][0]["output_count"], 0);
    assert_eq!(summary["generations"][0]["prefix_length"], 0);
    let only_empty = text
        .lines()
        .filter(|l| !l.contains("t2"))
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    let summary = summary_value(&only_empty, &[]);
    assert_eq!(summary["positions"], 0);
    assert_eq!(summary["generations"].as_array().unwrap().len(), 1);
}

#[test]
fn repeated_turn_keys_do_not_make_a_later_generation_the_first() {
    let summary = summary_value(&prefix_record().replace("t2", "t1"), &[]);
    for entry in summary["generations"].as_array().unwrap() {
        assert_eq!(entry["prefix_length"], 100);
    }
}

#[test]
fn malformed_envelopes_cannot_close_a_whole_run() {
    let incomplete = prefix_record()
        .lines()
        .filter(|l| !l.contains("unload"))
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    let text = incomplete + "{\"session\":\"source\",\"run\":\"r\",\"kind\":\"unload\"}\n";
    let summary = summary_value(&text, &[]);
    for entry in summary["generations"].as_array().unwrap() {
        assert!(entry.get("digest").is_none());
        assert!(entry.get("prefix_length").is_none());
    }
}
