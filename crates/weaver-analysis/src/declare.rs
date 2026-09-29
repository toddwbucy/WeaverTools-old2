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
    /// A member the record carries and the declaration cannot: a `null`,
    /// which TOML has no spelling for, or a number outside the range the
    /// declaration's integer holds, a seed past `i64::MAX` among them, per
    /// `determinism-matrix-Spec` section 4's declared-seed domain.
    MemberUncarried {
        member: &'static str,
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

/// The derived declaration, as the TOML the operator loads, per
/// `weaver-types-Spec` section 2. It is built as a typed value and written by
/// the `toml` crate, which does every string's escaping, so no member crosses
/// as hand-written text. The identity messages cross from the record's own
/// `message.system` payloads value for value: each string and number is the
/// value the record carries, decoded from its JSON and written as TOML.
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
    let seed = number(
        &one_value(
            events,
            "model.request",
            "sampling.seed",
            "tunable-values.seed",
        )?,
        "tunable-values.seed",
    )?;
    if !matches!(seed, toml::Value::Integer(n) if n >= 0) {
        return Err(DeriveRefusal::MemberUncarried {
            member: "tunable-values.seed",
            met: seed.to_string(),
        });
    }
    let max_tokens = number(
        &one_value(
            events,
            "model.request",
            "stop.max_tokens",
            "tunable-values.max-tokens-per-turn",
        )?,
        "tunable-values.max-tokens-per-turn",
    )?;
    let capacity = number(
        &one_value(
            events,
            "model.output",
            "capacity",
            "tunable-values.context-capacity",
        )?,
        "tunable-values.context-capacity",
    )?;
    // The seated prefix: the turnless message.system events at the run's
    // opening, in landing order, each payload carried value for value.
    let prefix: Vec<&str> = events
        .iter()
        .filter(|e| e.envelope.kind == "message.system" && e.envelope.turn.is_none())
        .filter_map(|e| e.payload.as_deref().map(|p| p.get()))
        .collect();
    if prefix.is_empty() {
        return Err(DeriveRefusal::MemberAbsent { member: "identity" });
    }
    let identity = prefix
        .iter()
        .map(|payload| {
            let value: serde_json::Value = serde_json::from_str(payload)
                .map_err(|_| DeriveRefusal::MemberAbsent { member: "identity" })?;
            carried(value).map_err(|met| DeriveRefusal::MemberUncarried {
                member: "identity",
                met,
            })
        })
        .collect::<Result<Vec<_>, _>>()?;

    let mut model_binding = toml::Table::new();
    model_binding.insert("artifact".into(), artifact.into());
    model_binding.insert(
        "devices".into(),
        toml::Value::Array(
            inputs
                .devices
                .iter()
                .map(|&d| i64::from(d).into())
                .collect(),
        ),
    );
    let mut tunable = toml::Table::new();
    tunable.insert("seed".into(), seed);
    tunable.insert("context-capacity".into(), capacity);
    tunable.insert("max-tokens-per-turn".into(), max_tokens);
    let mut decoder = toml::Table::new();
    decoder.insert("model-binding".into(), model_binding.into());
    decoder.insert("residual-readout-election".into(), inputs.readout.into());
    if let Some(depth) = inputs.field_depth {
        let mut field = toml::Table::new();
        field.insert("depth".into(), i64::from(depth).into());
        decoder.insert("field-election".into(), field.into());
    }
    decoder.insert("surprisal-election".into(), inputs.surprisal.into());
    decoder.insert("identity".into(), toml::Value::Array(identity));
    decoder.insert("tunable-values".into(), tunable.into());
    let mut spu = toml::Table::new();
    spu.insert("decoder".into(), decoder.into());
    let mut sink = toml::Table::new();
    sink.insert("kind".into(), inputs.sink_kind.declared().into());
    sink.insert("path".into(), inputs.sink_path.clone().into());
    sink.insert("create".into(), true.into());

    let mut declaration = toml::Table::new();
    declaration.insert("session".into(), inputs.destination.clone().into());
    declaration.insert("binding-kind".into(), "diagnostic".into());
    // The fixed spellings, per the Spec: members the record does not carry
    // and a run under this binding never reads take a spelling rather than
    // a guess.
    declaration.insert("tool-set".into(), toml::Value::Array(Vec::new()));
    declaration.insert("permission-mode".into(), "ask".into());
    declaration.insert("spu-instruction".into(), spu.into());
    declaration.insert("trace-sink".into(), sink.into());
    Ok(toml::to_string(&declaration).expect("a table of strings, numbers and tables writes"))
}

/// A number the record spells as JSON text, as the TOML value the declaration
/// carries, refused by name where it is not a number or the declaration's
/// integer cannot hold it.
fn number(json: &str, member: &'static str) -> Result<toml::Value, DeriveRefusal> {
    let value: serde_json::Value =
        serde_json::from_str(json).map_err(|_| DeriveRefusal::MemberUncarried {
            member,
            met: json.to_string(),
        })?;
    match carried(value) {
        Ok(number @ (toml::Value::Integer(_) | toml::Value::Float(_))) => Ok(number),
        _ => Err(DeriveRefusal::MemberUncarried {
            member,
            met: json.to_string(),
        }),
    }
}

/// A decoded JSON value as the TOML value that carries it: each string and
/// number the value the record carries. `Err` names what TOML cannot carry:
/// a `null`, and an integer past `i64::MAX`, which would otherwise cross as a
/// float and change the value.
fn carried(value: serde_json::Value) -> Result<toml::Value, String> {
    Ok(match value {
        serde_json::Value::Null => return Err("null".into()),
        serde_json::Value::Bool(b) => b.into(),
        serde_json::Value::Number(n) => match n.as_i64() {
            Some(i) => i.into(),
            None if n.is_f64() => n.as_f64().expect("an f64 number").into(),
            None => return Err(n.to_string()),
        },
        serde_json::Value::String(s) => s.into(),
        serde_json::Value::Array(items) => {
            toml::Value::Array(items.into_iter().map(carried).collect::<Result<_, _>>()?)
        }
        serde_json::Value::Object(members) => {
            let mut table = toml::Table::new();
            for (key, member) in members {
                table.insert(key, carried(member)?);
            }
            table.into()
        }
    })
}
