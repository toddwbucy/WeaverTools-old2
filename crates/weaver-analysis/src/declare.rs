//! conforms: analysis-declaration-derives-from-the-record
//!
//! The declaration derived from the record, per `weaver-analysis-Spec`
//! section 3's third projection and the charter's section 3 as amended on
//! issue #394: every fact of the source run comes from the record, so the
//! diagnostic run is correct to the run and never to the analyst's memory.
//! Four members are the analyst's inputs - device placement, the readers'
//! elections, the diagnostic sink, and destination - and two take the fixed spellings
//! the Spec names for members the record does not carry and a run under
//! this binding never reads.

use crate::record::{Event, value_at};

/// The analyst's four inputs, the charter's exceptions each for its own
/// reason: the record deliberately names no silicon, the readers are the
/// analyst's question, the sink is the new record's home, and the destination
/// names the diagnostic session separately from the source evidence.
#[derive(Debug, Clone)]
pub struct AnalystInputs {
    pub destination: String,
    pub devices: Vec<u32>,
    pub readout: bool,
    pub field_depth: Option<u32>,
    pub surprisal: bool,
    pub sink_path: String,
    /// **The sink's shape is part of the analyst's input**, per
    /// `weaver-analysis-Spec` section 3: a pipe elects that the run
    /// retains nothing and the reading is taken as the stream drains, a
    /// file declines that licence and keeps a capture. A derivation that
    /// could write only one shape would make the election this crate's.
    pub sink_kind: SinkKind,
}

/// The shapes admin opens, of those an analyst elects here. The floor
/// carries a third, the socket, which no reading has asked for yet and
/// which this crate does not derive rather than deriving it untested.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum SinkKind {
    File,
    Pipe,
}

impl SinkKind {
    pub fn parse(text: &str) -> Option<SinkKind> {
        match text {
            "file" => Some(SinkKind::File),
            "pipe" => Some(SinkKind::Pipe),
            _ => None,
        }
    }

    fn declared(self) -> &'static str {
        match self {
            SinkKind::File => "file",
            SinkKind::Pipe => "pipe",
        }
    }
}

/// Why a derivation refused, naming the member: disagreement is a question
/// for the operator and never a pick, and absence refuses rather than
/// defaulting - completeness is claim-relative and the claim is the whole
/// declaration.
#[derive(Debug, Clone, PartialEq)]
pub enum DeriveRefusal {
    MemberAbsent {
        member: &'static str,
    },
    MemberDisagrees {
        member: &'static str,
        held: String,
        met: String,
    },
}

/// One value across the record or a refusal naming the member.
fn one_value(
    events: &[Event],
    kind: &str,
    path: &str,
    member: &'static str,
) -> Result<String, DeriveRefusal> {
    let mut held: Option<String> = None;
    for event in events.iter().filter(|e| e.envelope.kind == kind) {
        let Some(payload) = &event.payload else {
            continue;
        };
        let Some(value) = value_at(payload, path) else {
            continue;
        };
        let met = value.get().to_string();
        match &held {
            None => held = Some(met),
            Some(prior) if *prior == met => {}
            Some(prior) => {
                return Err(DeriveRefusal::MemberDisagrees {
                    member,
                    held: prior.clone(),
                    met,
                });
            }
        }
    }
    held.ok_or(DeriveRefusal::MemberAbsent { member })
}

/// The derived declaration, rendered as the TOML the operator loads, per
/// `weaver-types-Spec` section 2. The identity messages cross from the
/// record's own `message.system` payloads by [`toml_inline`], which keeps
/// every string and number exactly as the record spelled it and changes only
/// the punctuation between them, so the seated prefix is the record's rather
/// than a re-rendering.
pub fn derive(events: &[Event], inputs: &AnalystInputs) -> Result<String, DeriveRefusal> {
    let session = events
        .first()
        .map(|e| e.envelope.session.clone())
        .ok_or(DeriveRefusal::MemberAbsent { member: "session" })?;
    // **One session and one run, judged before any member is read.** A
    // record holding two sessions is two records concatenated, and one
    // holding two runs seats its prefix once per run, so a derivation over
    // either would compose a declaration from a mixture no run declared -
    // the disagreement refusal's own case, judged on the envelope first.
    let run = events[0].envelope.run.clone();
    for event in events {
        if event.envelope.session != session {
            return Err(DeriveRefusal::MemberDisagrees {
                member: "session",
                held: session,
                met: event.envelope.session.clone(),
            });
        }
        if event.envelope.run != run {
            return Err(DeriveRefusal::MemberDisagrees {
                member: "run",
                held: run,
                met: event.envelope.run.clone(),
            });
        }
    }
    if inputs.destination.is_empty() {
        return Err(DeriveRefusal::MemberAbsent {
            member: "destination",
        });
    }
    if inputs.destination == session {
        return Err(DeriveRefusal::MemberDisagrees {
            member: "destination",
            held: session,
            met: inputs.destination.clone(),
        });
    }
    let artifact: String = serde_json::from_str(&one_value(
        events,
        "model.measurement",
        "model",
        "model-binding.artifact",
    )?)
    .map_err(|_| DeriveRefusal::MemberAbsent {
        member: "model-binding.artifact",
    })?;
    let seed = one_value(
        events,
        "model.request",
        "sampling.seed",
        "tunable-values.seed",
    )?;
    let max_tokens = one_value(
        events,
        "model.request",
        "stop.max_tokens",
        "tunable-values.max-tokens-per-turn",
    )?;
    let capacity = one_value(
        events,
        "model.output",
        "capacity",
        "tunable-values.context-capacity",
    )?;
    // The seated prefix: the turnless message.system events at the run's
    // opening, in landing order, each payload carried verbatim.
    let prefix: Vec<&str> = events
        .iter()
        .filter(|e| e.envelope.kind == "message.system" && e.envelope.turn.is_none())
        .filter_map(|e| e.payload.as_deref().map(|p| p.get()))
        .collect();
    if prefix.is_empty() {
        return Err(DeriveRefusal::MemberAbsent { member: "identity" });
    }
    // A payload TOML cannot spell - one holding `null` - is a prefix the
    // declaration cannot carry, and refuses as the member it would have been.
    let prefix: Vec<String> = prefix
        .iter()
        .map(|payload| toml_inline(payload))
        .collect::<Option<_>>()
        .ok_or(DeriveRefusal::MemberAbsent { member: "identity" })?;

    // Every interpolated string scalar is serialized as a JSON string, which
    // is a TOML basic string as it stands: a session, artifact, or sink path
    // holding a quote, a bracket, or any other TOML-significant character
    // crosses as the value it is rather than as markup. Top-level keys come
    // first and each section follows as its own table, TOML reading a bare
    // key after a table header as that table's.
    let mut declaration = String::new();
    declaration.push_str(&format!(
        "session = {}\n",
        serde_json::json!(inputs.destination)
    ));
    declaration.push_str("binding-kind = \"diagnostic\"\n");
    // The fixed spellings, per the Spec: members the record does not carry
    // and a run under this binding never reads take a spelling rather than
    // a guess.
    declaration.push_str("tool-set = []\n");
    declaration.push_str("permission-mode = \"ask\"\n");
    declaration.push_str("\n[spu-instruction.decoder]\n");
    declaration.push_str(&format!("residual-readout-election = {}\n", inputs.readout));
    if let Some(depth) = inputs.field_depth {
        declaration.push_str(&format!("field-election = {{ depth = {depth} }}\n"));
    }
    declaration.push_str(&format!("surprisal-election = {}\n", inputs.surprisal));
    declaration.push_str(&format!("identity = [{}]\n", prefix.join(", ")));
    declaration.push_str(&format!(
        "tunable-values = {{ seed = {seed}, context-capacity = {capacity}, max-tokens-per-turn = {max_tokens} }}\n"
    ));
    declaration.push_str("\n[spu-instruction.decoder.model-binding]\n");
    declaration.push_str(&format!("artifact = {}\n", serde_json::json!(artifact)));
    let devices: Vec<String> = inputs.devices.iter().map(|d| d.to_string()).collect();
    declaration.push_str(&format!("devices = [{}]\n", devices.join(", ")));
    declaration.push_str("\n[trace-sink]\n");
    declaration.push_str(&format!("kind = \"{}\"\n", inputs.sink_kind.declared()));
    declaration.push_str(&format!("path = {}\n", serde_json::json!(inputs.sink_path)));
    declaration.push_str("create = true\n");
    Ok(declaration)
}

/// A JSON value's text respelled as a TOML inline value: every string and
/// every number is copied as the record spelled it, and only the punctuation
/// between them changes, `:` becoming ` = ` and the whitespace between tokens
/// dropping so the value stays on one line. A JSON string is a TOML basic
/// string as it stands except for the escaped solidus, which TOML does not
/// admit and which means the solidus itself. `None` where the value holds
/// `null`, which TOML has no spelling for.
fn toml_inline(json: &str) -> Option<String> {
    let mut out = String::with_capacity(json.len() + 16);
    let mut chars = json.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '"' => {
                out.push('"');
                while let Some(c) = chars.next() {
                    match c {
                        '\\' => match chars.next()? {
                            '/' => out.push('/'),
                            escaped => {
                                out.push('\\');
                                out.push(escaped);
                            }
                        },
                        '"' => {
                            out.push('"');
                            break;
                        }
                        other => out.push(other),
                    }
                }
            }
            ':' => out.push_str(" = "),
            ',' => out.push_str(", "),
            '{' => {
                while chars.peek().is_some_and(|c| c.is_whitespace()) {
                    chars.next();
                }
                if chars.peek() == Some(&'}') {
                    chars.next();
                    out.push_str("{}");
                } else {
                    out.push_str("{ ");
                }
            }
            '}' => out.push_str(" }"),
            'n' => return None,
            c if c.is_whitespace() => {}
            other => out.push(other),
        }
    }
    Some(out)
}
