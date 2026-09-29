//! conforms: analysis-summary-reports-the-run-and-its-conditions
//! conforms: analysis-reconstruction-follows-recorded-election
//! conforms: analysis-preload-validates-before-opener
//! conforms: analysis-diagnostic-requires-distinct-destination
//! conforms: analysis-derive-uses-explicit-destination
//! conforms: analysis-preload-reports-effective-selection
//! conforms: analysis-parse-skips-the-unknown
//! conforms: analysis-derives-no-absent-member
//! conforms: analysis-election-declares-what-follows
//! conforms: analysis-projection-splices-verbatim
//! conforms: analysis-sequence-order-preserved
//! conforms: analysis-seal-ends-the-preload
//! conforms: analysis-declaration-derives-from-the-record
//!
//! The driver half's watches, per `weaver-analysis-Spec` section 6, each
//! naming its perturbation. The fixtures are real records: the smoke-loop1
//! cell-q8 serving trace the null replay of 2026-08-31 certified against,
//! carried verbatim.

use weaver_analysis::{AnalystInputs, DeriveRefusal, parse_record, project, render_opener};

const SOURCE: &str = include_str!("fixtures/serving-source.ndjson");

/// A derived declaration read back as the TOML value it is, so an assertion
/// reads a member's value rather than one spelling of it.
fn declared(text: &str) -> toml::Table {
    text.parse().expect("the derived declaration is TOML")
}

fn at<'a>(table: &'a toml::Table, path: &str) -> &'a toml::Value {
    let mut parts = path.split('.');
    let mut value = &table[parts.next().expect("a path")];
    for part in parts {
        value = match part.parse::<usize>() {
            Ok(index) => &value[index],
            Err(_) => &value[part],
        };
    }
    value
}

fn inputs() -> AnalystInputs {
    AnalystInputs {
        destination: "s-diagnostic".to_string(),
        devices: vec![0],
        readout: false,
        field_depth: None,
        surprisal: false,
        sink_path: "/tmp/diag.ndjson".to_string(),
        sink_kind: weaver_analysis::SinkKind::File,
    }
}

/// **The parse skips a kind and a payload member it does not know, and
/// neither decides a grouping.** An invented kind and an invented member
/// land in the record and the projection is byte-identical to the
/// projection without them.
///
/// Perturbation: refuse a payload member the parse does not know and the
/// salted request line vanishes from the projection, the count moving.
/// Watched under exactly that addition.
#[test]
fn an_invented_kind_and_member_move_no_grouping() {
    let clean: Vec<String> = project(&parse_record(SOURCE))
        .iter()
        .map(|d| d.frame().to_string())
        .collect();
    let salted = format!(
        "{}{}{}",
        r#"{"session":"s-karl-1","run":"r-x","sequence":"90","kind":"invented.kind","subsystem":"harness","payload":{"who":"knows"}}"#,
        "\n",
        SOURCE.replacen(
            r#""payload": {"rendered"#,
            r#""payload": {"invented_member": 7, "rendered"#,
            1
        ),
    );
    assert!(
        salted.contains(r#""invented_member": 7"#),
        "the salt landed in the source"
    );
    let salted: Vec<String> = project(&parse_record(&salted))
        .iter()
        .map(|d| d.frame().to_string())
        .collect();
    assert_eq!(clean, salted, "the unknown decides nothing");
}

/// **No absent member is derived.** A record whose `model.output` carries
/// no capacity refuses the derivation naming the member, rather than
/// computing one from the members beside it or defaulting.
///
/// Perturbation: default the absent capacity in `derive` and the refusal
/// disappears. Watched under exactly that change.
#[test]
fn an_absent_member_refuses_rather_than_derives() {
    let without: String = SOURCE
        .lines()
        .filter(|l| !l.contains(r#""kind": "model.output""#))
        .collect::<Vec<_>>()
        .join("\n");
    let refused = weaver_analysis::derive(&parse_record(&without), &inputs());
    assert_eq!(
        refused,
        Err(DeriveRefusal::MemberAbsent {
            member: "tunable-values.context-capacity"
        }),
        "absence refuses naming the member"
    );
}

/// **A member the record spells two ways refuses naming the member**,
/// disagreement being the operator's question and never a pick.
#[test]
fn a_disagreeing_member_refuses_rather_than_picks() {
    let salted = format!(
        "{}\n{}",
        SOURCE.trim_end(),
        r#"{"session":"s-karl-1","run":"2026-08-29T21:50:19.925Z-karl-93ebb51980edc046","sequence":"90","kind":"model.measurement","subsystem":"spu.decoder","payload":{"model":"/other/artifact.gguf","input_tokens":[],"output_tokens":[1],"weights_hash":"x"}}"#,
    );
    let refused = weaver_analysis::derive(&parse_record(&salted), &inputs());
    assert!(
        matches!(
            refused,
            Err(DeriveRefusal::MemberDisagrees {
                member: "model-binding.artifact",
                ..
            })
        ),
        "disagreement refuses naming the member: {refused:?}"
    );
}

/// **The sink's shape is the analyst's, and the derivation writes what was
/// elected.** A pipe elects that the run retains nothing, a file declines
/// that licence, and a derivation that could write only one shape would
/// make the election this crate's.
///
/// Perturbation: hardcode the file spelling and this fails on the pipe
/// case. Watched under exactly that change.
#[test]
fn the_derived_sink_carries_the_shape_the_analyst_elected() {
    let piped = AnalystInputs {
        sink_kind: weaver_analysis::SinkKind::Pipe,
        ..inputs()
    };
    let declaration =
        weaver_analysis::derive(&parse_record(SOURCE), &piped).expect("the record is whole");
    assert_eq!(
        at(&declared(&declaration), "trace-sink.kind").as_str(),
        Some("pipe")
    );
    assert_eq!(
        at(&declared(&declaration), "trace-sink.create").as_bool(),
        Some(true),
        "a pipe is created where absent"
    );

    let filed =
        weaver_analysis::derive(&parse_record(SOURCE), &inputs()).expect("the record is whole");
    assert_eq!(
        at(&declared(&filed), "trace-sink.kind").as_str(),
        Some("file")
    );
}

/// **A record holding two sessions or two runs refuses before any member
/// is read**: two sessions are two records concatenated, and a second run
/// seats its prefix again, so a derivation over either would compose a
/// declaration from a mixture no run declared.
#[test]
fn a_mixed_record_refuses_on_the_envelope() {
    let two_runs = format!(
        "{}\n{}",
        SOURCE.trim_end(),
        r#"{"session":"s-karl-1","run":"r-2","sequence":"0","kind":"load","subsystem":"harness","payload":{"tee":{"all_kinds":true}}}"#,
    );
    let refused = weaver_analysis::derive(&parse_record(&two_runs), &inputs());
    assert!(
        matches!(
            refused,
            Err(DeriveRefusal::MemberDisagrees { member: "run", .. })
        ),
        "a second run refuses on the envelope: {refused:?}"
    );
    let two_sessions = SOURCE.replacen("s-karl-1", "s-other", 1);
    let refused = weaver_analysis::derive(&parse_record(&two_sessions), &inputs());
    assert!(
        matches!(
            refused,
            Err(DeriveRefusal::MemberDisagrees {
                member: "session",
                ..
            })
        ),
        "a second session refuses on the envelope: {refused:?}"
    );
}

/// **The election declares what follows**: the stream carries no kind the
/// opener did not name, read against a record that holds plenty of others.
///
/// Perturbation: project every kind and the set widens past the opener.
/// Watched under exactly that change.
#[test]
fn no_kind_crosses_past_the_election() {
    let opener: serde_json::Value = serde_json::from_str(&render_opener("s-karl-1")).unwrap();
    let elected: Vec<&str> = opener["election"]["keys"]
        .as_array()
        .unwrap()
        .iter()
        .map(|k| k["kind"].as_str().unwrap())
        .collect();
    for distillate in project(&parse_record(SOURCE)) {
        let frame: serde_json::Value = serde_json::from_str(distillate.frame()).unwrap();
        let kind = frame["envelope"]["kind"].as_str().unwrap();
        assert!(elected.contains(&kind), "{kind} crossed past the election");
    }
    assert_eq!(
        project(&parse_record(SOURCE)).len(),
        10,
        "one load, the prefix, two turns' messages, two requests, two measurements"
    );
}

/// **The projection splices verbatim.** Values a re-encoding would change -
/// an exponent spelling, a float at full precision, an integer past 2^53 -
/// cross byte-identical into the distillate's frame.
///
/// Perturbation: re-encode a parsed value in `project` and the exponent
/// spelling collapses. Watched under exactly that change.
#[test]
fn the_projection_splices_the_records_own_bytes() {
    let record = concat!(
        r#"{"session":"s-1","run":"r-1","turn":"t-1","sequence":"4","kind":"model.request","subsystem":"spu.decoder","#,
        r#""payload":{"rendered":"x","template":"y","sampling":{"seed":14458752852352082704,"temperature":0.699999988079071,"odd":1e3}}}"#,
    );
    let distillates = project(&parse_record(record));
    let frame = distillates[0].frame();
    assert!(
        frame.contains(
            r#""sampling":{"seed":14458752852352082704,"temperature":0.699999988079071,"odd":1e3}"#
        ),
        "the record's own spellings cross: {frame}"
    );
}

/// **Sequence order is preserved**: distillates leave in the record's
/// landing order, never sorted and never grouped before sending.
///
/// Perturbation: sort the projection by kind and the interleaving of
/// requests and measurements collapses. Watched under exactly that change.
#[test]
fn distillates_leave_in_landing_order() {
    let kinds: Vec<String> = project(&parse_record(SOURCE))
        .iter()
        .map(|d| {
            let frame: serde_json::Value = serde_json::from_str(d.frame()).unwrap();
            frame["envelope"]["kind"].as_str().unwrap().to_string()
        })
        .collect();
    // The election carries the four message kinds since 2026-09-06, per
    // Spec section 3, so the interleaving holds the prefix and the turns'
    // messages beside the requests and measurements, in landing order.
    assert_eq!(
        kinds,
        vec![
            "load",
            "message.system",
            "message.user",
            "model.request",
            "model.measurement",
            "message.assistant",
            "message.user",
            "model.request",
            "model.measurement",
            "message.assistant",
        ],
        "the record's own interleaving"
    );
}

/// **The seal ends the preload**: one empty JSON object on its own line
/// after the last distillate, `{}` canonically and never a blank line.
///
/// Perturbation: substitute a blank line for the seal and this fails, a
/// blank line being framing residue the custodian does not read as a seal.
/// Watched under exactly that change.
#[test]
fn the_seal_is_an_empty_object_on_its_own_line() {
    let events = parse_record(SOURCE);
    let mut wire: Vec<u8> = Vec::new();
    {
        let mut sender = weaver_analysis::preload::open(&mut wire, "s-karl-1").unwrap();
        for distillate in &project(&events) {
            sender.send(distillate).unwrap();
        }
        sender.seal().unwrap();
    }
    let text = String::from_utf8(wire).unwrap();
    let lines: Vec<&str> = text.lines().collect();
    assert_eq!(lines.len(), 12, "opener, ten distillates, the seal");
    assert_eq!(*lines.last().unwrap(), "{}", "the seal's one spelling");
    let opener: serde_json::Value = serde_json::from_str(lines[0]).unwrap();
    assert_eq!(opener["session"], "s-karl-1", "the election opens the flow");
}

/// **The declaration derives from the record, correct to the run and never
/// to the analyst's memory.** Every source-run fact of the real record
/// lands in the derived declaration: the artifact, the seed the run
/// declared, the bounds, and the seated prefix verbatim.
///
/// Perturbation: fill the seed from a constant instead of the record and
/// the assertion fails on the recorded value. Watched under exactly that
/// change.
#[test]
fn the_declaration_derives_every_source_run_fact() {
    let declaration =
        weaver_analysis::derive(&parse_record(SOURCE), &inputs()).expect("the record is whole");
    let d = declared(&declaration);
    assert_eq!(
        at(&d, "spu-instruction.decoder.model-binding.artifact").as_str(),
        Some("/bulk-store/weaver-testing/cross-precision-repro/qwen2.5-0.5b-instruct-q8_0.gguf")
    );
    let tunable = "spu-instruction.decoder.tunable-values";
    assert_eq!(
        at(&d, &format!("{tunable}.seed")).as_integer(),
        Some(451234785645)
    );
    assert_eq!(
        at(&d, &format!("{tunable}.context-capacity")).as_integer(),
        Some(16384)
    );
    assert_eq!(
        at(&d, &format!("{tunable}.max-tokens-per-turn")).as_integer(),
        Some(1024)
    );
    assert_eq!(at(&d, "binding-kind").as_str(), Some("diagnostic"));
    assert!(
        at(&d, "spu-instruction.decoder.identity.0.content.0.text")
            .as_str()
            .is_some_and(|t| t.starts_with("You are Karl")),
        "the seated prefix crosses value for value"
    );
    assert!(
        !d.contains_key("gate-instruction"),
        "a diagnostic declaration carries no gate"
    );

    // A sink path holding TOML-significant characters crosses as the value
    // it is rather than as markup.
    let hostile = AnalystInputs {
        sink_path: "/tmp/x = \"{y}\" [z]".to_string(),
        ..inputs()
    };
    let declaration =
        weaver_analysis::derive(&parse_record(SOURCE), &hostile).expect("the record is whole");
    assert_eq!(
        at(&declared(&declaration), "trace-sink.path").as_str(),
        Some("/tmp/x = \"{y}\" [z]"),
        "a TOML-significant path stays a value: {declaration}"
    );
}

/// **A character the record escapes as a surrogate pair crosses as that
/// character**, the declaration being written by the toml crate rather than
/// respelled from the JSON: a respelling copied `\ud83d\ude00` as two escapes
/// TOML refuses. The derived text is pinned byte for byte in
/// `fixtures/derived-surrogate.toml`, and `weaver-types`'s config tests parse
/// that same file with `weaver_types::parse`, this crate linking no
/// `weaver-*` crate to do it itself.
///
/// Perturbation: carry each payload string as its JSON text rather than its
/// decoded value and the pinned bytes and the character both fail. Watched
/// under exactly that change.
#[test]
fn a_surrogate_pair_crosses_as_its_character() {
    let source = SOURCE.replace("You are Karl", "You are Karl \\ud83d\\ude00");
    assert_ne!(source, SOURCE, "the escape landed in the record");
    let declaration =
        weaver_analysis::derive(&parse_record(&source), &inputs()).expect("the record is whole");
    assert_eq!(declaration, include_str!("fixtures/derived-surrogate.toml"));
    assert!(
        at(
            &declared(&declaration),
            "spu-instruction.decoder.identity.0.content.0.text"
        )
        .as_str()
        .is_some_and(|t| t.starts_with("You are Karl \u{1F600}")),
        "{declaration}"
    );
}

/// **A recorded seed the declaration's integer cannot hold refuses the
/// derivation, naming the member**, per `determinism-matrix-Spec` section 4's
/// declared-seed domain of 0 to `i64::MAX`: written as it stands it is a
/// declaration the stack's parser refuses, and derive answered it as whole.
///
/// Perturbation: let `carried` cross an integer past `i64::MAX` as a float
/// and drop the seed's integer check, and this derives. Watched under exactly
/// that change.
#[test]
fn a_seed_past_the_declarations_integer_refuses() {
    let source = SOURCE.replace("451234785645", "9223372036854775808");
    assert_ne!(source, SOURCE, "the seed landed in the record");
    match weaver_analysis::derive(&parse_record(&source), &inputs()) {
        Err(DeriveRefusal::MemberUncarried { member, met }) => {
            assert_eq!(member, "tunable-values.seed");
            assert_eq!(met, "9223372036854775808");
        }
        other => panic!("a seed past i64::MAX refuses naming the member, got {other:?}"),
    }
}

// A real CLI process and a listening preload door. Refusals must not even
// connect: a custodian's prior holdings therefore cannot meet a new opener.
struct Door {
    dir: std::path::PathBuf,
    listener: std::os::unix::net::UnixListener,
}

impl Door {
    fn new() -> Self {
        static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let dir = std::env::temp_dir().join(format!(
            "e1-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        std::fs::create_dir(&dir).unwrap();
        let listener = std::os::unix::net::UnixListener::bind(dir.join("door")).unwrap();
        listener.set_nonblocking(true).unwrap();
        Self { dir, listener }
    }

    fn invoke(&self, record: &str, args: &[&str]) -> std::process::Output {
        std::fs::write(self.dir.join("record"), record).unwrap();
        std::process::Command::new(env!("CARGO_BIN_EXE_weaver-analysis"))
            .arg("preload")
            .arg(self.dir.join("record"))
            .arg(self.dir.join("door"))
            .args(args)
            .output()
            .unwrap()
    }

    fn loaded(record: &str, args: &[&str]) -> (Vec<String>, serde_json::Value) {
        use std::io::Read;
        let door = Self::new();
        let result = door.invoke(record, args);
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let (mut stream, _) = door.listener.accept().expect("the validated driver dials");
        stream
            .set_read_timeout(Some(std::time::Duration::from_secs(2)))
            .unwrap();
        let mut wire = String::new();
        stream.read_to_string(&mut wire).unwrap();
        (
            wire.lines().map(str::to_string).collect(),
            serde_json::from_slice(&result.stdout).unwrap(),
        )
    }

    fn refuses(record: &str, args: &[&str], reason: &str) {
        let door = Self::new();
        let result = door.invoke(record, args);
        assert!(!result.status.success(), "refusal required: {args:?}");
        let error = String::from_utf8_lossy(&result.stderr);
        assert!(
            error.contains(reason),
            "{args:?}: {error}, expected {reason}"
        );
        assert!(
            matches!(door.listener.accept(), Err(error) if error.kind() == std::io::ErrorKind::WouldBlock),
            "a refusal connected to the custodian; existing holdings could be retired: {args:?}"
        );
    }
}

impl Drop for Door {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.dir);
    }
}

fn line(run: &str, sequence: u64, kind: &str, turn: Option<&str>, payload: &str) -> String {
    format!(
        "{{\"session\":\"source\",\"run\":{run:?},\"sequence\":\"{sequence}\",\"kind\":{kind:?},\"turn\":{},\"subsystem\":\"harness\",\"wall_ms\":0,\"monotonic_ns\":0,\"payload\":{payload}}}\n",
        serde_json::json!(turn)
    )
}

fn selection_record(rule: &str, run: &str) -> String {
    [
        line(run, 0, "load", None, &format!("{{\"tee\":{rule}}}")),
        line(
            run,
            1,
            "message.system",
            None,
            r#"{"role":"system","future":{"z":1.00, "a":1e3},"content":"identity"}"#,
        ),
        line(
            run,
            2,
            "future.kind",
            Some("t-1"),
            r#"{"future":{"raw":{"z":1.00, "a":1e3},"null":null,"empty":""},"other":42}"#,
        ),
        line(
            run,
            3,
            "message.user",
            Some("t-1"),
            r#"{"role":"user","content":"hello"}"#,
        ),
        line(run, 4, "turn.closed", Some("t-1"), "{}"),
    ]
    .concat()
}

const RAW_RULE: &str = r#"{"all_kinds":false,"keys":[{"kind":"future.kind","paths":["future.raw","future.null","future.empty","future.absent"]},{"kind":"future.kind","paths":["other"]}]}"#;

/// Perturbations: restore the fixed default, drop unknown elected material,
/// suppress the system exception, or merge/sort duplicate-kind entries.
/// Each changes a separately asserted reading of the actual CLI wire.
#[test]
fn recorded_selection_preserves_unknown_raw_values_and_first_match() {
    let record = selection_record(RAW_RULE, "r-one");
    let (wire, _) = Door::loaded(&record, &[]);
    assert_eq!(wire.len(), 4, "opener, turnless system, future kind, seal");
    let opener: serde_json::Value = serde_json::from_str(&wire[0]).unwrap();
    assert_eq!(
        opener["election"],
        serde_json::from_str::<serde_json::Value>(RAW_RULE).unwrap()
    );
    let system: serde_json::Value = serde_json::from_str(&wire[1]).unwrap();
    assert_eq!(system["envelope"]["kind"], "message.system");
    assert!(
        wire[1].contains(r#""future":{"z":1.00, "a":1e3}"#),
        "whole system payload crosses under every rule"
    );
    let future: serde_json::Value = serde_json::from_str(&wire[2]).unwrap();
    assert_eq!(future["envelope"]["kind"], "future.kind");
    assert_eq!(future["envelope"]["session"], "source");
    let pairs = future["pairs"].as_object().unwrap();
    assert_eq!(pairs.len(), 3);
    assert!(!pairs.contains_key("future.absent"));
    assert_eq!(pairs.get("future.null"), Some(&serde_json::Value::Null));
    assert_eq!(pairs.get("future.empty"), Some(&serde_json::json!("")));
    assert!(
        !pairs.contains_key("other"),
        "later duplicate kind is shadowed"
    );
    assert!(wire[2].contains(r#""future.raw":{"z":1.00, "a":1e3}"#));
    assert_eq!(wire[3], "{}");

    // Reverse conflicting duplicate kinds: first-match must reverse too.
    let reversed = r#"{"all_kinds":false,"keys":[{"kind":"future.kind","paths":["other"]},{"kind":"future.kind","paths":["future.raw"]}]}"#;
    let (wire, _) = Door::loaded(&selection_record(reversed, "r-one"), &[]);
    let future: serde_json::Value = serde_json::from_str(&wire[2]).unwrap();
    assert_eq!(future["pairs"], serde_json::json!({"other":42}));
}

#[test]
fn all_kinds_and_empty_restrictive_rules_keep_the_system_exception() {
    for (all, expected) in [(true, 5), (false, 1)] {
        let rule = format!(r#"{{"all_kinds":{all},"keys":[]}}"#);
        let (wire, report) = Door::loaded(&selection_record(&rule, "r-one"), &[]);
        assert_eq!(wire.len(), expected + 2);
        assert_eq!(report["preloaded"], expected);
        let mut systems = 0;
        for frame in &wire[1..wire.len() - 1] {
            let frame: serde_json::Value = serde_json::from_str(frame).unwrap();
            if frame["envelope"]["kind"] == "message.system" {
                systems += 1;
                assert_eq!(frame["pairs"].as_object().unwrap().len(), 3);
            } else {
                assert_eq!(frame["pairs"], serde_json::json!({}));
            }
        }
        assert_eq!(systems, 1);
    }
}

/// Refusal coverage is against a live listening socket, including every
/// evidence class, not an unavailable pathname that could hide an early dial.
/// Perturbations: validate after opening, default missing evidence, or accept
/// a source-named cut / diagnostic destination.
#[test]
fn every_preflight_refusal_leaves_the_door_untouched() {
    let good = selection_record(RAW_RULE, "r-one");
    for (args, reason) in [
        (vec!["--unknown"], "unknown"),
        (vec!["--diagnostic", "--diagnostic"], "repeated"),
        (vec!["--as", ""], "nonempty"),
        (vec!["--as"], "takes"),
        (vec!["--through"], "takes"),
        (vec!["--through", "bad"], "colon"),
        (vec!["--through", "r-one:bad"], "number"),
        (vec!["--through", "absent:1", "--as", "branch"], "no run"),
        (vec!["--through", "r-one:9", "--as", "branch"], "no turn"),
        (vec!["--through", "r-one:1"], "distinct"),
        (vec!["--through", "r-one:1", "--as", "source"], "distinct"),
        (vec!["--diagnostic"], "distinct"),
        (vec!["--diagnostic", "--as", "source"], "distinct"),
        (vec!["--diagnostic", "--as", ""], "nonempty"),
    ] {
        Door::refuses(&good, &args, reason);
    }
    Door::refuses("", &[], "no event");
    Door::refuses(
        &good.replace("turn.closed", "turn.started"),
        &["--through", "r-one:1", "--as", "branch"],
        "without its close",
    );
    Door::refuses(
        &good.replacen("source", "another", 1),
        &[],
        "one nonempty source",
    );
    Door::refuses(&good.replace("source", ""), &[], "one nonempty source");
    Door::refuses(
        &good.lines().skip(1).collect::<Vec<_>>().join("\n"),
        &[],
        "governing load",
    );
    for bad in [
        "null",
        "{}",
        r#"{"all_kinds":false}"#,
        r#"{"keys":[]}"#,
        r#"{"all_kinds":"true","keys":[]}"#,
        r#"{"all_kinds":false,"keys":[{"kind":"x"}]}"#,
        r#"{"all_kinds":false,"keys":[{"paths":[]}]}"#,
        r#"{"all_kinds":false,"keys":[{"kind":"x","paths":[1]}]}"#,
    ] {
        Door::refuses(&selection_record(bad, "r-one"), &[], "malformed");
    }
    Door::refuses(
        &good.replacen(&format!(r#""tee":{RAW_RULE}"#), "", 1),
        &[],
        "lacks tee",
    );
    let changed = selection_record(r#"{"all_kinds":true,"keys":[]}"#, "r-two");
    Door::refuses(&format!("{good}{changed}"), &[], "different effective");
    Door::refuses(
        &format!("{good}{}", changed.replace("r-two", "r-one")),
        &[],
        "conflicting duplicate",
    );
    let reversed = r#"{"all_kinds":false,"keys":[{"kind":"future.kind","paths":["other"]},{"kind":"future.kind","paths":["future.raw","future.null","future.empty","future.absent"]}]}"#;
    Door::refuses(
        &format!("{good}{}", selection_record(reversed, "r-two")),
        &[],
        "different effective",
    );
}

#[test]
fn effective_rules_ignore_only_irrelevant_order_and_the_cut_bounds_evidence() {
    let rule = r#"{"all_kinds":false,"keys":[{"kind":"future.kind","paths":["future.raw","future.null"]},{"kind":"message.user","paths":["content","role"]}]}"#;
    let equivalent = r#"{"all_kinds":false,"keys":[{"kind":"message.user","paths":["role","content","role"]},{"kind":"future.kind","paths":["future.null","future.raw"]},{"kind":"future.kind","paths":["shadow"]}]}"#;
    let first = selection_record(rule, "r-one");
    let (wire, _) = Door::loaded(
        &format!("{first}{}", selection_record(equivalent, "r-two")),
        &[],
    );
    assert_eq!(wire.len(), 8, "three events per run");
    let changed = selection_record(r#"{"all_kinds":true,"keys":[]}"#, "r-two");
    let (wire, _) = Door::loaded(
        &format!("{first}{changed}"),
        &["--through", "r-one:1", "--as", "branch"],
    );
    assert_eq!(wire.len(), 5);
    for frame in &wire[1..wire.len() - 1] {
        let value: serde_json::Value = serde_json::from_str(frame).unwrap();
        assert_eq!(value["envelope"]["session"], "branch");
        assert_eq!(value["envelope"]["run"], "r-one");
    }
    // Diagnostic selection can cross differing source elections, without
    // claiming those holdings reproduce the original session's state.
    let (_, report) = Door::loaded(
        &format!("{first}{changed}"),
        &["--diagnostic", "--as", "diagnostic"],
    );
    assert_eq!(report["preloaded"], 6);
}

/// Report assertions use independently stated expectations for BOTH modes;
/// falsifying any member fails here even if the wire is otherwise valid.
#[test]
fn the_report_names_the_selection_that_crossed() {
    let recorded: serde_json::Value = serde_json::from_str(RAW_RULE).unwrap();
    let diagnostic = serde_json::json!({"all_kinds":false,"keys":[
        {"kind":"load","paths":["tee"]},
        {"kind":"model.request","paths":["rendered","template","sampling"]},
        {"kind":"model.measurement","paths":["input_tokens","output_tokens","model","weights_hash"]},
        {"kind":"message.system","paths":["role","content"]},
        {"kind":"message.user","paths":["role","content"]},
        {"kind":"message.assistant","paths":["role","content"]},
        {"kind":"message.tool_result","paths":["role","content"]},
        {"kind":"flush","paths":["resident_before","resident_after"]},
        {"kind":"elision","paths":["from","to","resident_before","resident_after"]},
        {"kind":"fault","paths":["case"]},
        {"kind":"recall","paths":["ask","returned","count"]}
    ]});
    for (args, mode, destination, election, count) in [
        (vec![], "recorded", "source", recorded.clone(), 2),
        (vec!["--as", "branch"], "recorded", "branch", recorded, 2),
        (
            vec!["--diagnostic", "--as", "diagnostic"],
            "diagnostic",
            "diagnostic",
            diagnostic,
            3,
        ),
    ] {
        let (wire, report) = Door::loaded(&selection_record(RAW_RULE, "r-one"), &args);
        assert_eq!(
            report,
            serde_json::json!({"mode":mode,"source_session":"source","destination_session":destination,"session":destination,"election":election,"preloaded":count,"sealed":true})
        );
        let opener: serde_json::Value = serde_json::from_str(&wire[0]).unwrap();
        assert_eq!(
            opener,
            serde_json::json!({"session":destination,"election":election})
        );
        assert_eq!(wire.len(), count + 2);
        for frame in &wire[1..wire.len() - 1] {
            let event: serde_json::Value = serde_json::from_str(frame).unwrap();
            assert_eq!(event["envelope"]["session"], destination);
        }
        assert_eq!(wire.last().unwrap(), "{}");
    }
}

/// The CLI must require and render the analyst's destination. Source facts
/// remain watched by the existing declaration test, not redefined here.
#[test]
fn derive_requires_and_renders_a_distinct_destination() {
    let door = Door::new();
    std::fs::write(door.dir.join("record"), SOURCE).unwrap();
    for (as_args, succeeds) in [
        (vec![], false),
        (vec!["--as", ""], false),
        (vec!["--as", "s-karl-1"], false),
        (vec!["--as", "diagnostic"], true),
    ] {
        let result = std::process::Command::new(env!("CARGO_BIN_EXE_weaver-analysis"))
            .arg("derive")
            .arg(door.dir.join("record"))
            .args(["--devices", "0", "--sink", "/tmp/diagnostic.ndjson"])
            .args(as_args)
            .output()
            .unwrap();
        assert_eq!(
            result.status.success(),
            succeeds,
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        if succeeds {
            assert_eq!(
                at(
                    &declared(&String::from_utf8_lossy(&result.stdout)),
                    "session"
                )
                .as_str(),
                Some("diagnostic")
            );
        } else {
            assert!(String::from_utf8_lossy(&result.stderr).contains("destination"));
        }
    }
}

/// **A sink path carrying a control character refuses before anything is
/// written**, per `weaver-types-Spec` section 2: a declared path carries none,
/// and admin refuses the declaration that would otherwise be written.
///
/// Perturbation: remove the control-character check from `run_derive` and the
/// derivation writes its declaration. Watched under exactly that removal.
#[test]
fn a_sink_path_carrying_a_control_character_refuses_and_writes_nothing() {
    let door = Door::new();
    std::fs::write(door.dir.join("record"), SOURCE).unwrap();
    let out = door.dir.join("derived.toml");
    for sink in ["/tmp/trace\n", "/tmp/tr\u{7}ace"] {
        let result = std::process::Command::new(env!("CARGO_BIN_EXE_weaver-analysis"))
            .arg("derive")
            .arg(door.dir.join("record"))
            .args([
                "--as",
                "diagnostic",
                "--devices",
                "0",
                "--sink",
                sink,
                "--out",
            ])
            .arg(&out)
            .output()
            .unwrap();
        assert!(!result.status.success(), "{sink:?} derived");
        assert!(
            String::from_utf8_lossy(&result.stderr).contains("control character"),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert!(!out.exists(), "{sink:?} wrote a declaration");
        assert!(result.stdout.is_empty(), "{sink:?} printed a declaration");
    }
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

struct SignalsFiles(std::path::PathBuf);

impl SignalsFiles {
    fn new() -> Self {
        use std::sync::atomic::{AtomicUsize, Ordering};
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let path = std::env::temp_dir().join(format!(
            "weaver-signals-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&path).unwrap();
        Self(path)
    }

    fn run(&self, deposit: Option<&str>, pipe: bool) -> std::process::Output {
        use std::process::{Command, Stdio};
        let path = self.0.join("a-path-that-is-not-the-record-run.ndjson");
        std::fs::write(&path, SIGNALS_RECORD).unwrap();
        let mut command = Command::new(env!("CARGO_BIN_EXE_weaver-analysis"));
        command.args(["signals", if pipe { "-" } else { path.to_str().unwrap() }]);
        if let Some(path) = deposit {
            command.args(["--deposit", path]);
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let input = child.stdin.take().unwrap();
        if pipe {
            write_signals_input(input, SIGNALS_RECORD.as_bytes());
        } else {
            drop(input);
        }
        child.wait_with_output().unwrap()
    }
}

impl Drop for SignalsFiles {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

const SIGNALS_RECORD: &str = concat!(
    "{\"session\":\"record-session\",\"run\":\"record-run\",\"sequence\":\"0\",\"kind\":\"load\",\"payload\":{\"stack\":{\"gate\":\"record-sha\"}}}\n",
    "{\"session\":\"record-session\",\"run\":\"record-run\",\"turn\":\"one\",\"sequence\":\"1\",\"kind\":\"model.measurement\",\"payload\":{\"output_tokens\":[3],\"weights_hash\":\"\"}}\n",
    "{\"session\":\"record-session\",\"run\":\"record-run\",\"sequence\":\"2\",\"kind\":\"unload\",\"payload\":{}}\n",
);

fn signal_entry(out: std::process::Output) -> serde_json::Value {
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let summary: serde_json::Value =
        serde_json::from_slice(out.stdout.split(|b| *b == b'\n').next().unwrap()).unwrap();
    summary["generations"][0].clone()
}

/// The explicit deposit reaches the same members for a file and a pipe;
/// source binary identity wins, and each deposit member is independently absent.
#[test]
fn the_deposit_is_explicit_and_its_members_are_never_inferred() {
    let files = SignalsFiles::new();
    let deposit = serde_json::json!({
        "device_model":"observed GPU", "commit":"commit-hash", "toolchain":"pinned-rust",
        "driver":"pinned-driver", "engine_libraries":{"engine.so":"library-sha"},
        "stack":{"gate":"deposit-must-not-win"}
    });
    let path = files.0.join("named.json");
    std::fs::write(&path, deposit.to_string()).unwrap();
    let mut expected = signal_entry(files.run(Some(path.to_str().unwrap()), false));
    assert_eq!(
        signal_entry(files.run(Some(path.to_str().unwrap()), true)),
        expected
    );
    assert_eq!(expected["run"], "record-run");
    assert_eq!(expected["session"], "record-session");
    assert_eq!(expected["device_model"], "observed GPU");
    assert_eq!(expected["weights_hash"], "");
    assert_eq!(
        expected["code_identity"],
        serde_json::json!({
            "stack":{"gate":"record-sha"}, "commit":"commit-hash", "toolchain":"pinned-rust",
            "driver":"pinned-driver", "engine_libraries":{"engine.so":"library-sha"}
        })
    );
    assert!(expected.get("verdict").is_none());
    for member in [
        "device_model",
        "commit",
        "toolchain",
        "driver",
        "engine_libraries",
    ] {
        let mut missing = deposit.clone();
        missing.as_object_mut().unwrap().remove(member);
        std::fs::write(&path, missing.to_string()).unwrap();
        let actual = signal_entry(files.run(Some(path.to_str().unwrap()), true));
        let mut wanted = expected.clone();
        if member == "device_model" {
            wanted.as_object_mut().unwrap().remove(member);
        } else {
            wanted["code_identity"]
                .as_object_mut()
                .unwrap()
                .remove(member);
        }
        assert_eq!(actual, wanted, "only {member} is omitted");
    }
    // Candidate sibling names must not supply a deposit without an argument.
    for name in [
        "deposit.json",
        "a-path-that-is-not-the-record-run.json",
        "a-path-that-is-not-the-record-run.deposit.json",
    ] {
        std::fs::write(files.0.join(name), deposit.to_string()).unwrap();
    }
    expected.as_object_mut().unwrap().remove("device_model");
    expected["code_identity"] = serde_json::json!({"stack":{"gate":"record-sha"}});
    for pipe in [false, true] {
        assert_eq!(signal_entry(files.run(None, pipe)), expected);
    }
}

#[test]
fn named_missing_or_unreadable_deposits_refuse_instead_of_becoming_absent() {
    let files = SignalsFiles::new();
    let path = files.0.join("bad.json");
    for contents in [None, Some("{broken"), Some(r#"{"device_model":4}"#)] {
        if let Some(contents) = contents {
            std::fs::write(&path, contents).unwrap();
        }
        let out = files.run(Some(path.to_str().unwrap()), true);
        assert!(!out.status.success());
        assert!(out.stdout.is_empty());
        assert!(String::from_utf8_lossy(&out.stderr).contains("deposit"));
    }
}
