//! The flow **document**: what a flow says, and the two tiny languages it is allowed to speak.
//!
//! Everything in this file is FROZEN (ADR-0283 D1/§9). The core gets one last family of
//! primitives and then stops growing; the editor, the templates and the connectors live in a
//! module. So the shape here is chosen to be small enough to keep forever, and the two languages
//! are deliberately **not** Turing-complete:
//!
//! - **Mapping** — a value is either a literal, a PATH into the run (`input.…`, `steps.<id>.…`,
//!   `event.…` inside a trigger), or a string with `{{path}}` templates. Same spirit as
//!   `ReadDef::resolve_params_from_map`, which resolves `payload.<field>` and nothing else.
//! - **Conditions** — an object `{path: {op: value}}` evaluated in AND. Nine operators, listed
//!   once, refused if unknown.
//!
//! What is fuzzy gets resolved by the `ai` step, not by growing a DSL — that was decided so that
//! the frozen half stays auditable at a glance (ADR-0283, "alternativas descartadas").
//!
//! **Unknown keys are refused, never dropped.** This is the lesson of hub#521 written into the
//! newer contract from day one: `cash_register` shipped a `protects` block nothing read, and
//! seven commands declared a `validates` guard the runtime never ran. A flow document that looks
//! like it filters and does not would be the same failure with worse consequences, because
//! nobody is watching when a flow runs.
use std::collections::BTreeMap;

use serde_json::{Map, Value as Json};

use crate::errors::{Result, RuntimeError};

/// The only document version this kernel understands. An unknown version is REFUSED, never
/// guessed: a v2 document (branching/DAG, if it ever exists) describes an execution this binary
/// cannot perform, and running "the parts it recognises" would be a flow that does half of what
/// its author wrote.
pub const SCHEMA_VERSION: i64 = 1;

/// The roots a path may start from. Frozen: adding one later is additive, removing one is not.
const ROOT_INPUT: &str = "input";
const ROOT_STEPS: &str = "steps";
const ROOT_EVENT: &str = "event";
/// Reserved for `_flow_secrets` (ADR-0283 §4, hub#662). It is refused at save time rather than
/// silently treated as a literal string — a step that thinks it is sending a secret and sends the
/// text `secret.API_KEY` is worse than one that will not save.
const ROOT_SECRET: &str = "secret";

/// Error code namespace of the kernel. Callers (and the module `flows`) program against these.
pub const ERR_UNKNOWN_SCHEMA_VERSION: &str = "flow.unknown_schema_version";
pub const ERR_INVALID_DEFINITION: &str = "flow.invalid_definition";
pub const ERR_STEP_KIND_NOT_AVAILABLE: &str = "flow.step_kind_not_available";
pub const ERR_UNKNOWN_OPERATOR: &str = "flow.unknown_operator";
pub const ERR_SECRET_NOT_AVAILABLE: &str = "flow.secret_not_available";

fn invalid(code: &str, message: impl Into<String>) -> RuntimeError {
    RuntimeError::Domain {
        code: code.to_string(),
        message: message.into(),
    }
}

// ── Steps ─────────────────────────────────────────────────────────────────────────────────────

/// The six step kinds of `schema_version: 1` (ADR-0283 §5). The VOCABULARY is frozen here even
/// though only three of them execute today, so that a document written for the finished kernel
/// parses in this one and is refused by name — not as "unknown value", which reads like a typo.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StepKind {
    Command,
    Condition,
    Delay,
    /// Reserved — hub#662 (`http` + `_flow_secrets`).
    Http,
    /// Reserved — hub#665 (server-side agent runner).
    Ai,
    /// Reserved — hub#663 part 2 (`notify` with `recipient_query`).
    Notify,
}

impl StepKind {
    pub fn as_str(self) -> &'static str {
        match self {
            StepKind::Command => "command",
            StepKind::Condition => "condition",
            StepKind::Delay => "delay",
            StepKind::Http => "http",
            StepKind::Ai => "ai",
            StepKind::Notify => "notify",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        Some(match s {
            "command" => StepKind::Command,
            "condition" => StepKind::Condition,
            "delay" => StepKind::Delay,
            "http" => StepKind::Http,
            "ai" => StepKind::Ai,
            "notify" => StepKind::Notify,
            _ => return None,
        })
    }

    /// Does this kind reach outside the runtime? Those follow the **claim → I/O → complete**
    /// contract (the tick prepares them, the server performs the I/O outside the global lock, a
    /// second locked pass persists the result) and none of them is implemented in this delivery.
    pub fn needs_io(self) -> bool {
        matches!(self, StepKind::Http | StepKind::Ai | StepKind::Notify)
    }

    /// Every kind, in document order. Mirrored by `schemas/flow.schema.json`.
    pub const ALL: &'static [StepKind] = &[
        StepKind::Command,
        StepKind::Condition,
        StepKind::Delay,
        StepKind::Http,
        StepKind::Ai,
        StepKind::Notify,
    ];
}

/// What a step does, once its kind is known. The kind-specific keys are parsed **strictly** for
/// the kinds that run; for the reserved ones nothing is parsed, because guessing the shape of a
/// step this kernel cannot execute would freeze a contract nobody has validated.
#[derive(Debug, Clone, PartialEq)]
pub enum StepSpec {
    /// `{"kind":"command","command":"sales.sale.create","params":{…}}` — the params are mapped
    /// (paths/templates) against the run before the command sees them.
    Command { command: String, params: Map<String, Json> },
    /// `{"kind":"condition","when":{…}}` — a guard. False stops the run; v1 is linear, so there
    /// is no "else" branch to go to.
    Condition { when: Condition },
    /// `{"kind":"delay","seconds":N}` or `{"kind":"delay","until":"input.when"}` — the run sleeps
    /// as a row (`wake_at`), never as a held task.
    Delay { seconds: Option<i64>, until: Option<String> },
    /// `http` / `ai` / `notify`: accepted by the grammar, refused by [`FlowDefinition::validate`].
    Reserved,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StepDef {
    /// Identity of the step inside its flow — how later steps read its output (`steps.<id>.x`).
    pub id: String,
    pub kind: StepKind,
    pub spec: StepSpec,
}

// ── Triggers ──────────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TriggerKind {
    Event,
    Cron,
    At,
    Manual,
}

impl TriggerKind {
    pub fn as_str(self) -> &'static str {
        match self {
            TriggerKind::Event => "event",
            TriggerKind::Cron => "cron",
            TriggerKind::At => "at",
            TriggerKind::Manual => "manual",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        Some(match s {
            "event" => TriggerKind::Event,
            "cron" => TriggerKind::Cron,
            "at" => TriggerKind::At,
            "manual" => TriggerKind::Manual,
            _ => return None,
        })
    }
    pub const ALL: &'static [TriggerKind] = &[
        TriggerKind::Event,
        TriggerKind::Cron,
        TriggerKind::At,
        TriggerKind::Manual,
    ];
}

#[derive(Debug, Clone, PartialEq)]
pub struct TriggerDef {
    pub kind: TriggerKind,
    /// `event` only — the event name matched in the outbox relay.
    pub event: String,
    /// `event` only — declarative filter over the event payload (`event.<field>` paths).
    pub filter: Condition,
    /// `event` only — how the event payload becomes the run's `input`.
    pub input: Map<String, Json>,
    /// `cron` only — five-field expression, parsed by `scheduler::cron::next_after`.
    pub cron: String,
    /// `at` only — one-shot RFC-3339 instant.
    pub at: String,
}

// ── Conditions ────────────────────────────────────────────────────────────────────────────────

/// The nine operators. Frozen and closed: an unknown one is refused at save time, because a
/// filter that silently matches everything is how a flow ends up emailing the whole customer list.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Op {
    Eq,
    Neq,
    In,
    Exists,
    Contains,
    Gt,
    Gte,
    Lt,
    Lte,
}

impl Op {
    pub fn as_str(self) -> &'static str {
        match self {
            Op::Eq => "eq",
            Op::Neq => "neq",
            Op::In => "in",
            Op::Exists => "exists",
            Op::Contains => "contains",
            Op::Gt => "gt",
            Op::Gte => "gte",
            Op::Lt => "lt",
            Op::Lte => "lte",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        Some(match s {
            "eq" => Op::Eq,
            "neq" => Op::Neq,
            "in" => Op::In,
            "exists" => Op::Exists,
            "contains" => Op::Contains,
            "gt" => Op::Gt,
            "gte" => Op::Gte,
            "lt" => Op::Lt,
            "lte" => Op::Lte,
            _ => return None,
        })
    }
    pub const ALL: &'static [Op] = &[
        Op::Eq,
        Op::Neq,
        Op::In,
        Op::Exists,
        Op::Contains,
        Op::Gt,
        Op::Gte,
        Op::Lt,
        Op::Lte,
    ];
}

/// `{"total": {"gte": "100"}, "customer.email": {"exists": true}}` — evaluated in **AND**.
///
/// A `BTreeMap` and not the raw JSON object so that evaluation order is stable and two equal
/// conditions compare equal, which is what makes trigger re-seeding idempotent.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Condition(pub BTreeMap<String, Vec<(Op, Json)>>);

impl Condition {
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    /// Parses `{path: {op: value}}`. An empty/absent condition matches everything — that is the
    /// only permissive default here, and it is explicit: no filter written, no filtering meant.
    pub fn parse(value: &Json) -> Result<Self> {
        let mut out: BTreeMap<String, Vec<(Op, Json)>> = BTreeMap::new();
        let Json::Object(fields) = value else {
            if value.is_null() {
                return Ok(Condition::default());
            }
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                "a condition is an object of `{path: {op: value}}`",
            ));
        };
        for (path, ops) in fields {
            let Json::Object(ops) = ops else {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("condition on `{path}` must be an object of operators"),
                ));
            };
            let mut parsed = Vec::new();
            for (op, expected) in ops {
                let op = Op::parse(op).ok_or_else(|| {
                    invalid(
                        ERR_UNKNOWN_OPERATOR,
                        format!(
                            "unknown operator `{op}` on `{path}`; the frozen set is {}",
                            Op::ALL
                                .iter()
                                .map(|o| o.as_str())
                                .collect::<Vec<_>>()
                                .join(", ")
                        ),
                    )
                })?;
                parsed.push((op, expected.clone()));
            }
            out.insert(path.clone(), parsed);
        }
        Ok(Condition(out))
    }

    pub fn to_json(&self) -> Json {
        let mut root = Map::new();
        for (path, ops) in &self.0 {
            let mut m = Map::new();
            for (op, expected) in ops {
                m.insert(op.as_str().to_string(), expected.clone());
            }
            root.insert(path.clone(), Json::Object(m));
        }
        Json::Object(root)
    }

    /// True when EVERY clause holds. A missing path is `Null`, and `Null` fails every comparison
    /// except `exists: false` and an explicit `eq: null` — a filter must not match by accident on
    /// a field the event does not carry.
    pub fn matches(&self, scope: &Json) -> bool {
        self.0.iter().all(|(path, ops)| {
            let actual = resolve_path(path, scope).unwrap_or(Json::Null);
            ops.iter().all(|(op, expected)| eval(*op, &actual, expected))
        })
    }

    /// Every path this condition reads — used to refuse `secret.…` at save time.
    fn paths(&self) -> impl Iterator<Item = &String> {
        self.0.keys()
    }
}

/// One operator against one pair of values.
fn eval(op: Op, actual: &Json, expected: &Json) -> bool {
    match op {
        Op::Eq => json_eq(actual, expected),
        Op::Neq => !json_eq(actual, expected),
        Op::Exists => {
            let present = !actual.is_null();
            expected.as_bool().unwrap_or(true) == present
        }
        Op::In => match expected {
            Json::Array(items) => items.iter().any(|i| json_eq(actual, i)),
            _ => false,
        },
        Op::Contains => match actual {
            Json::Array(items) => items.iter().any(|i| json_eq(i, expected)),
            Json::String(s) => match as_text(expected) {
                Some(needle) => s.contains(&needle),
                None => false,
            },
            _ => false,
        },
        Op::Gt | Op::Gte | Op::Lt | Op::Lte => match compare(actual, expected) {
            Some(ordering) => match op {
                Op::Gt => ordering == std::cmp::Ordering::Greater,
                Op::Gte => ordering != std::cmp::Ordering::Less,
                Op::Lt => ordering == std::cmp::Ordering::Less,
                _ => ordering != std::cmp::Ordering::Greater,
            },
            None => false,
        },
    }
}

/// Equality that survives this codebase's own conventions: money is a **string** (ADR-0123) and a
/// quantity may arrive as a number, so `"12.10" == 12.10` has to be true or every condition
/// written against an amount would be a silent `false`. Strict JSON equality first, text second.
fn json_eq(a: &Json, b: &Json) -> bool {
    if a == b {
        return true;
    }
    if a.is_null() || b.is_null() {
        return false;
    }
    match (as_number(a), as_number(b)) {
        (Some(x), Some(y)) => x == y,
        _ => match (as_text(a), as_text(b)) {
            (Some(x), Some(y)) => x == y,
            _ => false,
        },
    }
}

/// Ordering for `gt/gte/lt/lte`: numeric when both sides are numbers (or numeric strings — money
/// again), otherwise lexicographic, which is what makes RFC-3339 timestamps compare correctly.
/// `None` means "not comparable", and every ordering operator then answers **false**.
fn compare(a: &Json, b: &Json) -> Option<std::cmp::Ordering> {
    if a.is_null() || b.is_null() {
        return None;
    }
    if let (Some(x), Some(y)) = (as_number(a), as_number(b)) {
        return x.partial_cmp(&y);
    }
    match (as_text(a), as_text(b)) {
        (Some(x), Some(y)) => Some(x.cmp(&y)),
        _ => None,
    }
}

fn as_number(v: &Json) -> Option<f64> {
    match v {
        Json::Number(n) => n.as_f64(),
        Json::String(s) => s.trim().parse::<f64>().ok(),
        _ => None,
    }
}

fn as_text(v: &Json) -> Option<String> {
    match v {
        Json::String(s) => Some(s.clone()),
        Json::Number(n) => Some(n.to_string()),
        Json::Bool(b) => Some(b.to_string()),
        _ => None,
    }
}

// ── The mapping language ──────────────────────────────────────────────────────────────────────

/// Is `s` a bare path into the run (`input.…`, `steps.…`, `event.…`, `secret.…`)?
pub fn is_path(s: &str) -> bool {
    matches!(s.split('.').next(), Some(root)
        if (root == ROOT_INPUT || root == ROOT_STEPS || root == ROOT_EVENT || root == ROOT_SECRET)
            && s.len() > root.len() + 1)
}

/// Walks `a.b.c` through an object scope. Array indexing is deliberately absent: v1 maps fields,
/// and "the third line of the ticket" is a shape that belongs in a query, not in a flow document.
pub fn resolve_path(path: &str, scope: &Json) -> Option<Json> {
    let mut cursor = scope;
    for segment in path.split('.') {
        cursor = cursor.get(segment)?;
    }
    Some(cursor.clone())
}

/// Resolves one mapped value against the run scope.
///
/// - a bare path → the value AT that path, with its type intact (a number stays a number);
/// - a string with `{{path}}` → the string with each template substituted, always a string;
/// - anything else → itself, recursing into objects and arrays.
///
/// A path that resolves to nothing becomes `null` (and `{{…}}` becomes the empty string): the
/// step then fails on its own schema validation, which is a better place to notice than here.
pub fn resolve(expr: &Json, scope: &Json) -> Json {
    match expr {
        Json::String(s) => {
            if is_path(s) {
                resolve_path(s, scope).unwrap_or(Json::Null)
            } else if s.contains("{{") {
                Json::String(render_template(s, scope))
            } else {
                expr.clone()
            }
        }
        Json::Object(map) => Json::Object(
            map.iter()
                .map(|(k, v)| (k.clone(), resolve(v, scope)))
                .collect(),
        ),
        Json::Array(items) => Json::Array(items.iter().map(|v| resolve(v, scope)).collect()),
        other => other.clone(),
    }
}

/// Resolves a whole `{name: expr}` map (a step's `params`, a trigger's `input`).
pub fn resolve_map(map: &Map<String, Json>, scope: &Json) -> Map<String, Json> {
    map.iter()
        .map(|(k, v)| (k.clone(), resolve(v, scope)))
        .collect()
}

/// `"Hola {{input.name}}"` → `"Hola Marta"`. An unclosed `{{` is left verbatim: it is text the
/// author wrote, and inventing a value for it would be worse than showing the braces.
fn render_template(s: &str, scope: &Json) -> String {
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(start) = rest.find("{{") {
        out.push_str(&rest[..start]);
        let after = &rest[start + 2..];
        let Some(end) = after.find("}}") else {
            out.push_str(&rest[start..]);
            return out;
        };
        let path = after[..end].trim();
        let value = resolve_path(path, scope).unwrap_or(Json::Null);
        out.push_str(&stringify(&value));
        rest = &after[end + 2..];
    }
    out.push_str(rest);
    out
}

/// How a value reads inside a template. A string is itself (never re-quoted), a null is empty,
/// and a structure falls back to compact JSON so nothing ever renders as `[object Object]`.
fn stringify(v: &Json) -> String {
    match v {
        Json::String(s) => s.clone(),
        Json::Null => String::new(),
        other => other.to_string(),
    }
}

/// Every `{{path}}` inside a value, for the save-time checks.
fn template_paths(expr: &Json, out: &mut Vec<String>) {
    match expr {
        Json::String(s) => {
            if is_path(s) {
                out.push(s.clone());
                return;
            }
            let mut rest = s.as_str();
            while let Some(start) = rest.find("{{") {
                let after = &rest[start + 2..];
                let Some(end) = after.find("}}") else { return };
                out.push(after[..end].trim().to_string());
                rest = &after[end + 2..];
            }
        }
        Json::Object(map) => map.values().for_each(|v| template_paths(v, out)),
        Json::Array(items) => items.iter().for_each(|v| template_paths(v, out)),
        _ => {}
    }
}

// ── The document ──────────────────────────────────────────────────────────────────────────────

/// A parsed, validated flow document.
#[derive(Debug, Clone, PartialEq)]
pub struct FlowDefinition {
    pub schema_version: i64,
    pub triggers: Vec<TriggerDef>,
    pub steps: Vec<StepDef>,
}

impl FlowDefinition {
    /// Parses AND validates. The two are one call on purpose: there is no useful state between
    /// "this is syntactically an object" and "this is a flow", and offering the half-parsed form
    /// is how a caller ends up storing a document that never runs.
    pub fn parse(value: &Json) -> Result<Self> {
        let Json::Object(root) = value else {
            return Err(invalid(ERR_INVALID_DEFINITION, "a flow definition is an object"));
        };

        // Version FIRST: everything below is the grammar of v1, and applying it to a document
        // that says v2 would be reading a language we do not speak.
        let schema_version = match root.get("schema_version") {
            Some(Json::Number(n)) => n.as_i64().unwrap_or(-1),
            Some(_) | None => {
                return Err(invalid(
                    ERR_UNKNOWN_SCHEMA_VERSION,
                    format!("`schema_version` is required and must be the integer {SCHEMA_VERSION}"),
                ))
            }
        };
        if schema_version != SCHEMA_VERSION {
            return Err(invalid(
                ERR_UNKNOWN_SCHEMA_VERSION,
                format!(
                    "`schema_version: {schema_version}` is not understood by this hub (it speaks \
                     {SCHEMA_VERSION}). Refused instead of run half-way."
                ),
            ));
        }

        for key in root.keys() {
            if !matches!(key.as_str(), "schema_version" | "name" | "triggers" | "steps") {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("unknown key `{key}` in the flow document"),
                ));
            }
        }

        let triggers = match root.get("triggers") {
            None | Some(Json::Null) => Vec::new(),
            Some(Json::Array(items)) => items
                .iter()
                .map(parse_trigger)
                .collect::<Result<Vec<_>>>()?,
            Some(_) => {
                return Err(invalid(ERR_INVALID_DEFINITION, "`triggers` must be an array"))
            }
        };
        let steps = match root.get("steps") {
            None | Some(Json::Null) => Vec::new(),
            Some(Json::Array(items)) => items.iter().map(parse_step).collect::<Result<Vec<_>>>()?,
            Some(_) => return Err(invalid(ERR_INVALID_DEFINITION, "`steps` must be an array")),
        };

        let def = FlowDefinition {
            schema_version,
            triggers,
            steps,
        };
        def.validate()?;
        Ok(def)
    }

    /// The checks that are about MEANING rather than shape, and every one of them is a failure
    /// that would otherwise happen at 3 AM with nobody looking.
    fn validate(&self) -> Result<()> {
        if self.steps.is_empty() {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                "a flow with no steps does nothing; it is refused instead of stored",
            ));
        }
        let mut seen: Vec<&str> = Vec::new();
        for step in &self.steps {
            if step.id.trim().is_empty() {
                return Err(invalid(ERR_INVALID_DEFINITION, "every step needs an `id`"));
            }
            if seen.contains(&step.id.as_str()) {
                // Two steps with one id makes `steps.<id>.x` ambiguous — the mapping language
                // would read one of them and nobody could say which.
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("duplicate step id `{}`", step.id),
                ));
            }
            seen.push(&step.id);

            if step.kind.needs_io() {
                return Err(invalid(
                    ERR_STEP_KIND_NOT_AVAILABLE,
                    format!(
                        "step `{}` is of kind `{}`, which this hub cannot execute yet: the I/O \
                         steps follow the claim → I/O → complete contract and land with their own \
                         issues (http: hub#662, ai: hub#665, notify: hub#663). Refused at save \
                         time so a flow never stalls forever at 3 AM.",
                        step.id,
                        step.kind.as_str()
                    ),
                ));
            }
        }
        // No `secret.…` anywhere: `_flow_secrets` does not exist yet (ADR-0283 §4), and a step
        // that believes it is sending a secret must not send the literal text of its name.
        let mut paths: Vec<String> = Vec::new();
        for step in &self.steps {
            match &step.spec {
                StepSpec::Command { params, .. } => {
                    template_paths(&Json::Object(params.clone()), &mut paths)
                }
                StepSpec::Condition { when } => {
                    paths.extend(when.paths().cloned());
                }
                StepSpec::Delay { until, .. } => paths.extend(until.clone()),
                StepSpec::Reserved => {}
            }
        }
        for trigger in &self.triggers {
            template_paths(&Json::Object(trigger.input.clone()), &mut paths);
            paths.extend(trigger.filter.paths().cloned());
        }
        if let Some(path) = paths.iter().find(|p| p.starts_with("secret.")) {
            return Err(invalid(
                ERR_SECRET_NOT_AVAILABLE,
                format!("`{path}`: flow secrets are not available yet (ADR-0283 §4, hub#662)"),
            ));
        }
        Ok(())
    }
}

fn parse_trigger(value: &Json) -> Result<TriggerDef> {
    let Json::Object(map) = value else {
        return Err(invalid(ERR_INVALID_DEFINITION, "a trigger is an object"));
    };
    for key in map.keys() {
        if !matches!(
            key.as_str(),
            "kind" | "event" | "filter" | "input" | "cron" | "at"
        ) {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("unknown key `{key}` in a trigger"),
            ));
        }
    }
    let kind = map
        .get("kind")
        .and_then(|k| k.as_str())
        .and_then(TriggerKind::parse)
        .ok_or_else(|| {
            invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "a trigger `kind` is one of {}",
                    TriggerKind::ALL
                        .iter()
                        .map(|k| k.as_str())
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            )
        })?;
    let text = |k: &str| {
        map.get(k)
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string()
    };
    let trigger = TriggerDef {
        kind,
        event: text("event"),
        filter: Condition::parse(map.get("filter").unwrap_or(&Json::Null))?,
        input: match map.get("input") {
            Some(Json::Object(m)) => m.clone(),
            None | Some(Json::Null) => Map::new(),
            Some(_) => {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    "a trigger `input` is an object of mappings",
                ))
            }
        },
        cron: text("cron"),
        at: text("at"),
    };
    // Each kind needs exactly the field that makes it fireable; without it the trigger is a row
    // that can never match, which looks armed and is not.
    match trigger.kind {
        TriggerKind::Event if trigger.event.trim().is_empty() => Err(invalid(
            ERR_INVALID_DEFINITION,
            "an `event` trigger needs the event name",
        )),
        TriggerKind::Cron if trigger.cron.trim().is_empty() => Err(invalid(
            ERR_INVALID_DEFINITION,
            "a `cron` trigger needs a cron expression",
        )),
        TriggerKind::At if trigger.at.trim().is_empty() => Err(invalid(
            ERR_INVALID_DEFINITION,
            "an `at` trigger needs an RFC-3339 instant",
        )),
        _ => Ok(trigger),
    }
}

fn parse_step(value: &Json) -> Result<StepDef> {
    let Json::Object(map) = value else {
        return Err(invalid(ERR_INVALID_DEFINITION, "a step is an object"));
    };
    let id = map
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();
    let kind_text = map.get("kind").and_then(|v| v.as_str()).unwrap_or_default();
    let kind = StepKind::parse(kind_text).ok_or_else(|| {
        invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "step `{id}`: `kind` is one of {}",
                StepKind::ALL
                    .iter()
                    .map(|k| k.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
        )
    })?;

    // The reserved kinds are parsed no further ON PURPOSE: their keys are the contract of hub#662
    // and hub#665, and inventing it here would freeze a shape nobody has run.
    if kind.needs_io() {
        return Ok(StepDef {
            id,
            kind,
            spec: StepSpec::Reserved,
        });
    }

    let allowed: &[&str] = match kind {
        StepKind::Command => &["id", "kind", "command", "params"],
        StepKind::Condition => &["id", "kind", "when"],
        StepKind::Delay => &["id", "kind", "seconds", "until"],
        _ => &["id", "kind"],
    };
    for key in map.keys() {
        if !allowed.contains(&key.as_str()) {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}` (`{}`): unknown key `{key}`. A flow never runs with a key the \
                     hub does not understand — that is how a guard nobody executes gets written.",
                    kind.as_str()
                ),
            ));
        }
    }

    let spec = match kind {
        StepKind::Command => {
            let command = map
                .get("command")
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string();
            if command.trim().is_empty() {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("step `{id}`: a `command` step needs the command name"),
                ));
            }
            let params = match map.get("params") {
                Some(Json::Object(m)) => m.clone(),
                None | Some(Json::Null) => Map::new(),
                Some(_) => {
                    return Err(invalid(
                        ERR_INVALID_DEFINITION,
                        format!("step `{id}`: `params` is an object of mappings"),
                    ))
                }
            };
            StepSpec::Command { command, params }
        }
        StepKind::Condition => StepSpec::Condition {
            when: Condition::parse(map.get("when").unwrap_or(&Json::Null))?,
        },
        StepKind::Delay => {
            let seconds = map.get("seconds").and_then(|v| v.as_i64());
            let until = map
                .get("until")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            if seconds.is_none() && until.is_none() {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("step `{id}`: a `delay` needs `seconds` or `until`"),
                ));
            }
            if seconds.is_some_and(|s| s < 0) {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("step `{id}`: `seconds` cannot be negative"),
                ));
            }
            StepSpec::Delay { seconds, until }
        }
        _ => StepSpec::Reserved,
    };

    Ok(StepDef { id, kind, spec })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn scope() -> Json {
        json!({
            "input": { "customer": { "email": "marta@example.com" }, "total": "120.50" },
            "steps": { "create": { "id": "sale-1", "lines": 3 } }
        })
    }

    // ── the document ──────────────────────────────────────────────────────────────────────────

    #[test]
    fn an_unknown_schema_version_is_refused_not_guessed() {
        let err = FlowDefinition::parse(&json!({ "schema_version": 2, "steps": [] }))
            .expect_err("a v2 document describes an execution this binary cannot perform");
        assert!(
            format!("{err}").contains("schema_version"),
            "the refusal names the version: {err}"
        );
        // Missing is the same answer: the version is not optional.
        assert!(FlowDefinition::parse(&json!({ "steps": [] })).is_err());
    }

    #[test]
    fn an_unknown_key_is_refused_rather_than_dropped() {
        // hub#521's lesson, applied from day one: a document that looks like it filters and does
        // not is worse than one that will not save.
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "a", "kind": "condition", "when": {}, "unless": { "x": 1 } }]
        }))
        .expect_err("`unless` reads exactly like a guard");
        assert!(format!("{err}").contains("unless"), "{err}");
    }

    #[test]
    fn an_io_step_is_refused_by_name_with_the_issue_that_brings_it() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "call", "kind": "http" }]
        }))
        .expect_err("this kernel cannot perform I/O steps yet");
        let text = format!("{err}");
        assert!(text.contains("http") && text.contains("hub#662"), "{text}");
    }

    #[test]
    fn two_steps_cannot_share_an_id() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [
                { "id": "a", "kind": "delay", "seconds": 1 },
                { "id": "a", "kind": "delay", "seconds": 2 }
            ]
        }))
        .expect_err("`steps.a.x` would be ambiguous");
        assert!(format!("{err}").contains("duplicate step id"), "{err}");
    }

    #[test]
    fn a_secret_reference_is_refused_while_flow_secrets_do_not_exist() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "a", "kind": "command", "command": "m.c",
                "params": { "key": "{{secret.API_KEY}}" }
            }]
        }))
        .expect_err("sending the literal text `secret.API_KEY` is worse than not saving");
        assert!(format!("{err}").contains("secret"), "{err}");
    }

    #[test]
    fn a_full_v1_document_round_trips() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "name": "Welcome",
            "triggers": [{
                "kind": "event",
                "event": "sale.completed",
                "filter": { "event.total": { "gte": "100" } },
                "input": { "customer_id": "event.customer_id" }
            }],
            "steps": [
                { "id": "guard", "kind": "condition", "when": { "input.customer_id": { "exists": true } } },
                { "id": "wait", "kind": "delay", "seconds": 60 },
                { "id": "note", "kind": "command", "command": "customers.note.add",
                  "params": { "customer_id": "input.customer_id", "text": "Gracias {{input.name}}" } }
            ]
        }))
        .expect("the shape the module `flows` will write");
        assert_eq!(def.triggers.len(), 1);
        assert_eq!(def.steps.len(), 3);
        assert_eq!(def.steps[2].kind, StepKind::Command);
    }

    #[test]
    fn a_trigger_without_what_makes_it_fire_is_refused() {
        for trigger in [
            json!({ "kind": "event" }),
            json!({ "kind": "cron" }),
            json!({ "kind": "at" }),
        ] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "triggers": [trigger],
                "steps": [{ "id": "a", "kind": "delay", "seconds": 1 }]
            }))
            .expect_err("a trigger that can never match looks armed and is not");
            assert!(format!("{err}").contains("trigger"), "{err}");
        }
        // `manual` needs nothing: it fires from `POST /api/hub/flows/{id}/run`.
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "triggers": [{ "kind": "manual" }],
            "steps": [{ "id": "a", "kind": "delay", "seconds": 1 }]
        }))
        .is_ok());
    }

    // ── the mapping language ──────────────────────────────────────────────────────────────────

    #[test]
    fn a_bare_path_keeps_the_type_of_what_it_points_at() {
        let scope = scope();
        assert_eq!(resolve(&json!("steps.create.lines"), &scope), json!(3));
        assert_eq!(resolve(&json!("steps.create.id"), &scope), json!("sale-1"));
        // Not a path: a literal string with a dot in it stays exactly what the author typed.
        assert_eq!(resolve(&json!("sales.sale.create"), &scope), json!("sales.sale.create"));
    }

    #[test]
    fn a_template_renders_into_a_string_and_a_missing_path_renders_empty() {
        let scope = scope();
        assert_eq!(
            resolve(&json!("Hola {{input.customer.email}} ({{steps.create.lines}})"), &scope),
            json!("Hola marta@example.com (3)")
        );
        assert_eq!(resolve(&json!("[{{input.nope}}]"), &scope), json!("[]"));
        // An unclosed template is text the author wrote, not a value to invent.
        assert_eq!(resolve(&json!("{{input.a"), &scope), json!("{{input.a"));
    }

    #[test]
    fn mapping_recurses_into_objects_and_arrays() {
        let scope = scope();
        assert_eq!(
            resolve(&json!({ "a": ["input.total", 7], "b": { "c": "steps.create.id" } }), &scope),
            json!({ "a": ["120.50", 7], "b": { "c": "sale-1" } })
        );
    }

    #[test]
    fn a_path_that_resolves_to_nothing_is_null_not_the_path_text() {
        assert_eq!(resolve(&json!("input.missing.deep"), &scope()), Json::Null);
    }

    // ── conditions ────────────────────────────────────────────────────────────────────────────

    #[test]
    fn every_frozen_operator_answers() {
        let scope = json!({
            "event": { "total": "120.50", "channel": "web", "tags": ["vip", "new"], "note": "urgent order" }
        });
        let cases: &[(&str, &str, Json, bool)] = &[
            ("event.channel", "eq", json!("web"), true),
            ("event.channel", "eq", json!("shop"), false),
            ("event.channel", "neq", json!("shop"), true),
            ("event.channel", "in", json!(["web", "app"]), true),
            ("event.missing", "exists", json!(true), false),
            ("event.total", "exists", json!(true), true),
            ("event.tags", "contains", json!("vip"), true),
            ("event.note", "contains", json!("urgent"), true),
            // Money is a STRING in this codebase (ADR-0123) — comparing it must still be numeric.
            ("event.total", "gt", json!(100), true),
            ("event.total", "gte", json!("120.50"), true),
            ("event.total", "lt", json!(100), false),
            ("event.total", "lte", json!(200), true),
        ];
        for (path, op, expected, want) in cases {
            let cond = Condition::parse(&json!({ *path: { *op: expected } })).unwrap();
            assert_eq!(cond.matches(&scope), *want, "{path} {op} {expected}");
        }
    }

    #[test]
    fn clauses_are_anded_and_an_empty_condition_matches() {
        let scope = json!({ "event": { "a": 1, "b": 2 } });
        assert!(Condition::default().matches(&scope));
        assert!(Condition::parse(&json!({ "event.a": { "eq": 1 }, "event.b": { "eq": 2 } }))
            .unwrap()
            .matches(&scope));
        assert!(!Condition::parse(&json!({ "event.a": { "eq": 1 }, "event.b": { "eq": 9 } }))
            .unwrap()
            .matches(&scope));
    }

    #[test]
    fn an_unknown_operator_is_refused_instead_of_matching_everything() {
        let err = Condition::parse(&json!({ "event.total": { "greater_than": 100 } }))
            .expect_err("a filter that silently matches everything emails the whole customer list");
        assert!(format!("{err}").contains("greater_than"), "{err}");
    }

    #[test]
    fn a_missing_field_never_matches_by_accident() {
        let scope = json!({ "event": {} });
        for op in ["eq", "gt", "gte", "lt", "lte", "in", "contains"] {
            let cond = Condition::parse(&json!({ "event.total": { op: json!(0) } })).unwrap();
            assert!(!cond.matches(&scope), "`{op}` must not match a missing field");
        }
        assert!(Condition::parse(&json!({ "event.total": { "exists": false } }))
            .unwrap()
            .matches(&scope));
    }
}
