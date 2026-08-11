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
/// `_flow_secrets` (ADR-0283 §4, hub#662). Legal ONLY inside an `http` step: that is the one place
/// a credential has a reason to exist, and anywhere else it is refused at save time rather than
/// silently treated as a literal string — a step that thinks it is sending a secret and sends the
/// text `secret.API_KEY` is worse than one that will not save.
const ROOT_SECRET: &str = "secret";

/// The methods an `http` step may use. Frozen and small: the point of the step is to call a
/// business API, and `CONNECT`/`TRACE` are how an allow-listed URL becomes a tunnel.
const METHODS: &[&str] = &["GET", "POST", "PUT", "PATCH", "DELETE"];

/// Timeout of an `http` step when it does not say (ADR-0283 §4).
pub const DEFAULT_TIMEOUT_SECONDS: u64 = 10;

/// The most a single `http` step may wait. The run sits `running` with its lease held for that
/// long, so this is also how long a mistake costs.
pub const MAX_TIMEOUT_SECONDS: u64 = 30;

/// Error code namespace of the kernel. Callers (and the module `flows`) program against these.
pub const ERR_UNKNOWN_SCHEMA_VERSION: &str = "flow.unknown_schema_version";
pub const ERR_INVALID_DEFINITION: &str = "flow.invalid_definition";
pub const ERR_STEP_KIND_NOT_AVAILABLE: &str = "flow.step_kind_not_available";
pub const ERR_UNKNOWN_OPERATOR: &str = "flow.unknown_operator";
pub const ERR_SECRET_NOT_AVAILABLE: &str = "flow.secret_not_available";
/// hub#730. A `cron` the engine cannot resolve used to be stored as an ACTIVE trigger with a NULL
/// `next_run` — armed on the screen, invisible to the claim query, silent forever. It is refused
/// here, at the door the author knocks on, like every other thing this kernel cannot execute.
pub const ERR_INVALID_CRON: &str = "flow.invalid_cron";
/// Same family: `at: "manana por la tarde"` was copied straight into `next_run`.
pub const ERR_INVALID_AT: &str = "flow.invalid_at";

/// Turns of the agent loop when the document does not say (ADR-0283 §7).
pub const DEFAULT_MAX_ITERS: i64 = 6;
/// Hard ceiling, refused above rather than clamped. Every turn is a real call through the SaaS
/// proxy, which meters it (`AssistantUsage`): a runaway agent loop is money, not just latency.
pub const MAX_ITERS_CAP: i64 = 10;

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
    /// The first way out to the internet (hub#662): allow-listed URL + `_flow_secrets`.
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
    /// contract: the tick prepares them, the server performs the I/O outside the global lock, and a
    /// second locked pass persists the result.
    pub fn needs_io(self) -> bool {
        matches!(self, StepKind::Http | StepKind::Ai | StepKind::Notify)
    }

    /// Can this hub EXECUTE this kind today? The vocabulary is frozen at six; what grows is this
    /// list — `http` joined it with hub#662 and `ai` with hub#665, leaving only `notify`
    /// (hub#663 part 2). A document using what is left is refused **at save time** naming its
    /// issue: a flow stored with a step nothing performs would park a run forever at 3 AM.
    pub fn is_available(self) -> bool {
        !matches!(self, StepKind::Notify)
    }

    /// The issue that brings the kinds that are not here yet, so the refusal is actionable.
    fn pending_issue(self) -> &'static str {
        match self {
            StepKind::Notify => "hub#663",
            _ => "",
        }
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
    /// `{"kind":"http","method":"POST","url":"https://…","headers":{…},"body":{…},"timeout":10}`
    /// — the first way out to the internet (hub#662). Every field except `url` has a default, and
    /// each one is a mapping expression: the URL is templated against the run and matched against
    /// the flow's `http` grants **after** templating, because the allow-list has to judge the URL
    /// that would actually be called.
    Http {
        /// Upper-case, one of [`METHODS`].
        method: String,
        url: String,
        headers: Map<String, Json>,
        /// An object becomes a JSON body; a string is sent verbatim.
        body: Option<Json>,
        timeout_seconds: u64,
    },
    /// `{"kind":"ai","prompt":…,"tools":{…},"policy":…,"max_iters":N}` — an agent turn performed
    /// by the server (hub#665). The only step whose behaviour is not fully written in the
    /// document: what it decides comes from a model. That is exactly why [`AiStep::policy`]
    /// exists, and why its default is `manual`.
    Ai(AiStep),
    /// `notify`: accepted by the grammar, refused by [`FlowDefinition::validate`].
    Reserved,
}

/// What an `ai` step may do, and how far it is trusted (ADR-0283 §7 / D3).
#[derive(Debug, Clone, PartialEq)]
pub struct AiStep {
    /// The task, in words. Mapped against the run like any other value, so a turn can talk about
    /// the message that triggered it (`{{input.text}}`).
    pub prompt: String,
    /// Reads the model may perform. Intersected with what the flow was granted — declaring a tool
    /// here does not authorise it.
    pub queries: Vec<String>,
    /// Writes the model may PROPOSE. Whether a proposal executes is [`AiStep::policy`].
    pub commands: Vec<String>,
    pub policy: AiPolicy,
    pub max_iters: i64,
}

/// **What happens to a write the model proposes** (ADR-0283 D3).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AiPolicy {
    /// It runs, in the turn, through the automation gate. The owner said so in writing.
    Auto,
    /// It becomes a row in `_flow_approvals` and the turn ends. **The default**: the permissive
    /// option is the one nobody writes down and everybody assumes, and here it would mean an
    /// unattended model writing to the business database at 3 AM.
    Manual,
}

impl AiPolicy {
    pub fn as_str(self) -> &'static str {
        match self {
            AiPolicy::Auto => "auto",
            AiPolicy::Manual => "manual",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "auto" => Some(AiPolicy::Auto),
            "manual" => Some(AiPolicy::Manual),
            _ => None,
        }
    }
    pub fn is_auto(self) -> bool {
        self == AiPolicy::Auto
    }
    pub const ALL: &'static [AiPolicy] = &[AiPolicy::Auto, AiPolicy::Manual];
}

#[derive(Debug, Clone, PartialEq)]
pub struct StepDef {
    /// Identity of the step inside its flow — how later steps read its output (`steps.<id>.x`).
    pub id: String,
    pub kind: StepKind,
    pub spec: StepSpec,
}

impl StepDef {
    /// Every mapping expression this step evaluates, in document order.
    fn expressions(&self) -> Vec<Json> {
        match &self.spec {
            StepSpec::Command { params, .. } => vec![Json::Object(params.clone())],
            StepSpec::Condition { when } => {
                vec![Json::Array(when.paths().map(|p| json_str(p)).collect())]
            }
            StepSpec::Delay { until, .. } => {
                until.iter().map(|u| json_str(u)).collect::<Vec<_>>()
            }
            StepSpec::Http {
                url, headers, body, ..
            } => {
                let mut out = vec![json_str(url), Json::Object(headers.clone())];
                out.extend(body.clone());
                out
            }
            // An `ai` prompt is a mapping expression like any other, so it is listed here for
            // the same two reasons the rest are: its `{{…}}` resolve against the run, and the
            // `secret.…` refusal of hub#662 has to reach it — a prompt is precisely where a
            // credential must never be interpolated, because it would be sent to the model.
            StepSpec::Ai(ai) => vec![json_str(&ai.prompt)],
            StepSpec::Reserved => Vec::new(),
        }
    }

    /// The `_flow_secrets` this step names, deduplicated and sorted.
    ///
    /// The executor loads **exactly** these: a hub with fifty credentials decrypts the one the step
    /// about to run asked for, so a step can never carry a secret it does not mention.
    pub fn secret_names(&self) -> Vec<String> {
        let mut paths = Vec::new();
        for expr in self.expressions() {
            template_paths(&expr, &mut paths);
        }
        let mut names: Vec<String> = paths
            .iter()
            .filter_map(|p| p.strip_prefix("secret."))
            .map(|n| n.to_string())
            .collect();
        names.sort();
        names.dedup();
        names
    }
}

fn json_str(s: &str) -> Json {
    Json::String(s.to_string())
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

/// Is this an absolute `http(s)` URL? **Syntax only.** Whether the hub may talk to that host is the
/// allow-list's question (`grants::Authority::allows_http`), and whether its address is one that
/// would reach back inside the network is `flow_io`'s (anti-SSRF). Three separate questions, asked
/// by three separate gates, because each of them fails differently.
pub fn is_http_url(url: &str) -> bool {
    let lower = url.trim().to_ascii_lowercase();
    ["http://", "https://"].iter().any(|scheme| {
        lower
            .strip_prefix(scheme)
            .is_some_and(|rest| !rest.is_empty() && !rest.starts_with('/'))
    })
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

            if !step.kind.is_available() {
                return Err(invalid(
                    ERR_STEP_KIND_NOT_AVAILABLE,
                    format!(
                        "step `{}` is of kind `{}`, which this hub cannot execute yet ({}). \
                         Refused at save time so a flow never stalls forever at 3 AM.",
                        step.id,
                        step.kind.as_str(),
                        step.kind.pending_issue()
                    ),
                ));
            }

            // A `secret.…` outside an `http` step is refused. Inside one it is the credential of
            // the API being called; outside it there is no legitimate reader — a `command` step
            // would hand it to a module's table, and a `condition` could compare it byte by byte
            // until it had guessed it.
            if step.kind != StepKind::Http {
                let mut paths = Vec::new();
                for expr in step.expressions() {
                    template_paths(&expr, &mut paths);
                }
                if let Some(path) = paths.iter().find(|p| p.starts_with("secret.")) {
                    return Err(invalid(
                        ERR_SECRET_NOT_AVAILABLE,
                        format!(
                            "step `{}`: `{path}` — a flow secret is only readable from an `http` \
                             step (ADR-0283 §4), which is the one place a credential has to go out.",
                            step.id
                        ),
                    ));
                }
            }
        }
        // A trigger runs before any step and its scope is the EVENT, so there is nothing a secret
        // could mean there.
        let mut paths: Vec<String> = Vec::new();
        for trigger in &self.triggers {
            template_paths(&Json::Object(trigger.input.clone()), &mut paths);
            paths.extend(trigger.filter.paths().cloned());
        }
        if let Some(path) = paths.iter().find(|p| p.starts_with("secret.")) {
            return Err(invalid(
                ERR_SECRET_NOT_AVAILABLE,
                format!("`{path}`: a trigger cannot read a flow secret (ADR-0283 §4)"),
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
        // hub#730: "not empty" is not the same as "runnable". The engine is asked BEFORE storing,
        // because everything it cannot resolve ends up as `next_run = NULL` — a trigger the
        // screen calls active and the claim query never sees again. Same rule as an unknown
        // operator or an `ai` step: refused at save time, naming what is wrong.
        TriggerKind::Cron => match crate::scheduler::cron::validate(&trigger.cron) {
            Ok(()) => Ok(trigger),
            Err(why) => Err(invalid(ERR_INVALID_CRON, why)),
        },
        TriggerKind::At if trigger.at.trim().is_empty() => Err(invalid(
            ERR_INVALID_DEFINITION,
            "an `at` trigger needs an RFC-3339 instant",
        )),
        TriggerKind::At if chrono::DateTime::parse_from_rfc3339(trigger.at.trim()).is_err() => {
            Err(invalid(
                ERR_INVALID_AT,
                format!(
                    "`{}` is not an instant. An `at` trigger takes RFC-3339 with its offset \
                     (e.g. `2026-08-11T09:00:00+02:00`); the text was being copied into \
                     `next_run` as-is and the trigger never fired.",
                    trigger.at.trim()
                ),
            ))
        }
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

    // The kinds that do not run yet are parsed no further ON PURPOSE: their keys are the contract
    // of hub#663, and inventing it here would freeze a shape nobody has run.
    if !kind.is_available() {
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
        StepKind::Http => &["id", "kind", "method", "url", "headers", "body", "timeout"],
        StepKind::Ai => &["id", "kind", "prompt", "tools", "policy", "max_iters"],
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
        StepKind::Http => {
            let url = map
                .get("url")
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .trim()
                .to_string();
            if url.is_empty() {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("step `{id}`: an `http` step needs a `url`"),
                ));
            }
            // Only a LITERAL url can be judged here; a templated one is only known at run time and
            // is checked again in `flow_io` before the call leaves. Checking the literal half at
            // save time puts the refusal on the screen where the author typed it.
            if !url.contains("{{") && !is_http_url(&url) {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!(
                        "step `{id}`: `{url}` — an `http` step only ever calls an absolute \
                         `http://` or `https://` URL"
                    ),
                ));
            }

            let method = map
                .get("method")
                .and_then(|v| v.as_str())
                .unwrap_or("GET")
                .trim()
                .to_uppercase();
            if !METHODS.contains(&method.as_str()) {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!(
                        "step `{id}`: `{method}` is not one of {}",
                        METHODS.join(", ")
                    ),
                ));
            }

            let headers = match map.get("headers") {
                Some(Json::Object(m)) => m.clone(),
                None | Some(Json::Null) => Map::new(),
                Some(_) => {
                    return Err(invalid(
                        ERR_INVALID_DEFINITION,
                        format!("step `{id}`: `headers` is an object of mappings"),
                    ))
                }
            };

            let timeout_seconds = match map.get("timeout") {
                None | Some(Json::Null) => DEFAULT_TIMEOUT_SECONDS,
                Some(Json::Number(n)) => match n.as_i64() {
                    Some(s) if (1..=MAX_TIMEOUT_SECONDS as i64).contains(&s) => s as u64,
                    _ => {
                        return Err(invalid(
                            ERR_INVALID_DEFINITION,
                            format!(
                                "step `{id}`: `timeout` is a whole number of seconds between 1 and \
                                 {MAX_TIMEOUT_SECONDS} — the run holds its lease for that long"
                            ),
                        ))
                    }
                },
                Some(_) => {
                    return Err(invalid(
                        ERR_INVALID_DEFINITION,
                        format!("step `{id}`: `timeout` is a number of seconds"),
                    ))
                }
            };

            StepSpec::Http {
                method,
                url,
                headers,
                body: map.get("body").filter(|b| !b.is_null()).cloned(),
                timeout_seconds,
            }
        }
        StepKind::Ai => StepSpec::Ai(parse_ai(&id, map)?),
        _ => StepSpec::Reserved,
    };

    Ok(StepDef { id, kind, spec })
}

/// The keys of an `ai` step (hub#665). Parsed as strictly as every other kind: a `tools` block
/// silently dropped would hand the model everything the flow was granted instead of the two tools
/// its author chose, and nobody would be watching when it did.
fn parse_ai(id: &str, map: &Map<String, Json>) -> Result<AiStep> {
    let prompt = map
        .get("prompt")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();
    if prompt.trim().is_empty() {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!("step `{id}`: an `ai` step needs a `prompt` saying what to do"),
        ));
    }

    let mut queries = Vec::new();
    let mut commands = Vec::new();
    match map.get("tools") {
        None | Some(Json::Null) => {}
        Some(Json::Object(tools)) => {
            for key in tools.keys() {
                if !matches!(key.as_str(), "queries" | "commands") {
                    return Err(invalid(
                        ERR_INVALID_DEFINITION,
                        format!("step `{id}`: unknown key `{key}` in `tools`"),
                    ));
                }
            }
            queries = string_list(id, tools.get("queries"), "tools.queries")?;
            commands = string_list(id, tools.get("commands"), "tools.commands")?;
        }
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `tools` is `{{queries: [], commands: []}}`"),
            ))
        }
    }

    // Absent means MANUAL (ADR-0283 D3). An unknown value is refused rather than defaulted:
    // `"atuo"` silently becoming "manual" would be merciful, and `"atuo"` silently becoming
    // "auto" would be a hub writing unattended because of a typo. Neither is acceptable, so it
    // does not save.
    let policy = match map.get("policy") {
        None | Some(Json::Null) => AiPolicy::Manual,
        Some(Json::String(s)) => AiPolicy::parse(s).ok_or_else(|| {
            invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `policy` is one of {}",
                    AiPolicy::ALL
                        .iter()
                        .map(|p| p.as_str())
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            )
        })?,
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `policy` is a string"),
            ))
        }
    };

    let max_iters = match map.get("max_iters") {
        None | Some(Json::Null) => DEFAULT_MAX_ITERS,
        Some(v) => v.as_i64().unwrap_or(-1),
    };
    if !(1..=MAX_ITERS_CAP).contains(&max_iters) {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "step `{id}`: `max_iters` must be between 1 and {MAX_ITERS_CAP} (got \
                 {max_iters}). Refused rather than clamped: every turn is a real call through \
                 the SaaS proxy, and a document that says one number and runs another is lying \
                 to whoever wrote it."
            ),
        ));
    }

    Ok(AiStep {
        prompt,
        queries,
        commands,
        policy,
        max_iters,
    })
}

/// A list of operation names, refused if it is anything else. An entry that is not a string would
/// otherwise be dropped, and a tool the author believes they declared would not be offered.
fn string_list(id: &str, value: Option<&Json>, what: &str) -> Result<Vec<String>> {
    match value {
        None | Some(Json::Null) => Ok(Vec::new()),
        Some(Json::Array(items)) => items
            .iter()
            .map(|v| {
                v.as_str().map(str::to_string).ok_or_else(|| {
                    invalid(
                        ERR_INVALID_DEFINITION,
                        format!("step `{id}`: `{what}` is a list of operation names"),
                    )
                })
            })
            .collect(),
        Some(_) => Err(invalid(
            ERR_INVALID_DEFINITION,
            format!("step `{id}`: `{what}` is a list of operation names"),
        )),
    }
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

    /// The list shrinks one issue at a time, and what is LEFT must keep naming the issue that
    /// brings it. `http` left with hub#662 and `ai` with hub#665; `notify` is the last one, and a
    /// document using it must still be refused at save time rather than parked forever at 3 AM.
    #[test]
    fn the_io_steps_this_hub_still_cannot_run_are_refused_by_name() {
        for (kind, issue) in [("notify", "hub#663")] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{ "id": "call", "kind": kind }]
            }))
            .expect_err("this kernel cannot perform this I/O step yet");
            let text = format!("{err}");
            assert!(text.contains(kind) && text.contains(issue), "{text}");
        }
        // …and the two that DID land are no longer refused for being unavailable: they are parsed
        // strictly, so what they now complain about is their own missing keys.
        for (kind, complaint) in [("http", "url"), ("ai", "prompt")] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{ "id": "call", "kind": kind }]
            }))
            .expect_err("an empty step of either kind is still invalid, but for its OWN reason");
            let text = format!("{err}");
            assert!(
                text.contains(complaint) && !text.contains("cannot execute yet"),
                "`{kind}` must be refused for its own missing key, not as unavailable: {text}"
            );
        }
    }

    // ── the `http` step (hub#662) ─────────────────────────────────────────────────────────────

    #[test]
    fn an_http_step_carries_its_method_url_headers_body_and_timeout() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "call", "kind": "http", "method": "post",
                "url": "https://api.example.com/v1/send?to={{input.phone}}",
                "headers": { "Authorization": "Bearer {{secret.API_KEY}}" },
                "body": { "text": "input.text" },
                "timeout": 5
            }]
        }))
        .expect("the shape a connector template writes");
        let StepSpec::Http {
            method,
            url,
            headers,
            body,
            timeout_seconds,
        } = &def.steps[0].spec
        else {
            panic!("an http step parses as one");
        };
        assert_eq!(method, "POST", "the method is normalised, not echoed");
        assert_eq!(url, "https://api.example.com/v1/send?to={{input.phone}}");
        assert_eq!(headers.len(), 1);
        assert_eq!(*timeout_seconds, 5);
        assert!(body.is_some());
    }

    #[test]
    fn an_http_step_defaults_to_a_get_with_the_ten_second_timeout() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "call", "kind": "http", "url": "https://api.example.com/ping" }]
        }))
        .unwrap();
        let StepSpec::Http { method, timeout_seconds, body, .. } = &def.steps[0].spec else {
            panic!()
        };
        assert_eq!(method, "GET");
        assert_eq!(*timeout_seconds, DEFAULT_TIMEOUT_SECONDS);
        assert!(body.is_none(), "a GET with no body declared sends none");
    }

    #[test]
    fn an_http_step_without_a_url_is_refused() {
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "call", "kind": "http" }]
        }))
        .is_err());
    }

    #[test]
    fn a_literal_url_that_is_not_http_is_refused_at_save_time() {
        // The authoritative check runs again before the call leaves (`flow_io`), because a
        // templated URL is only known then. This one is the early half: a scheme typed by hand is
        // refused on the screen where it was typed, not at 3 AM.
        for url in ["file:///etc/passwd", "ftp://example.com/x", "/relative"] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{ "id": "call", "kind": "http", "url": url }]
            }))
            .expect_err("only http(s) ever leaves the hub");
            assert!(format!("{err}").contains("http"), "{err}");
        }
    }

    #[test]
    fn a_timeout_beyond_the_cap_and_an_unknown_method_are_refused() {
        let over = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "c", "kind": "http", "url": "https://a.example.com/x", "timeout": 120 }]
        }))
        .expect_err("a 2-minute step is a run nobody can explain");
        assert!(format!("{over}").contains(&MAX_TIMEOUT_SECONDS.to_string()), "{over}");

        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "c", "kind": "http", "url": "https://a.example.com/x", "method": "TRACE" }]
        }))
        .is_err());
    }

    #[test]
    fn a_secret_is_reachable_from_an_http_step_and_from_nowhere_else() {
        // Where it belongs: the one step that talks to somebody who needs a credential.
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "call", "kind": "http", "url": "https://api.example.com/x",
                "headers": { "Authorization": "Bearer {{secret.API_KEY}}" }
            }]
        }))
        .is_ok());

        // Everywhere else it is refused, and that is the containment: a command step could hand a
        // credential to a module's table, and a condition could compare it byte by byte until it
        // had guessed it.
        for step in [
            json!({ "id": "a", "kind": "command", "command": "m.c", "params": { "k": "{{secret.API_KEY}}" } }),
            json!({ "id": "a", "kind": "condition", "when": { "secret.API_KEY": { "eq": "x" } } }),
            json!({ "id": "a", "kind": "delay", "until": "secret.API_KEY" }),
        ] {
            let err = FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [step] }))
                .expect_err("a secret only leaves the hub through an http step");
            assert!(format!("{err}").contains("secret"), "{err}");
        }
    }

    #[test]
    fn the_secret_names_a_step_needs_are_known_before_it_runs() {
        // The executor loads exactly these and nothing else: a hub with fifty secrets decrypts the
        // one this step names.
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "call", "kind": "http",
                "url": "https://api.example.com/x?k={{secret.KEY}}",
                "headers": { "Authorization": "Bearer {{secret.TOKEN}}" },
                "body": { "sig": "{{secret.KEY}}" }
            }]
        }))
        .unwrap();
        assert_eq!(
            def.steps[0].secret_names(),
            vec!["KEY".to_string(), "TOKEN".to_string()]
        );
    }

    // ── the `ai` step (hub#665, ADR-0283 K5/D3) ───────────────────────────────────────────────

    /// The step saves now, and it saves with its keys parsed strictly — the same treatment
    /// `command`/`condition`/`delay` get. A step whose `tools` block were silently dropped would
    /// hand the model every tool the flow was granted instead of the two its author chose.
    #[test]
    fn an_ai_step_parses_its_prompt_its_tools_and_its_policy() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "agent",
                "kind": "ai",
                "prompt": "Answer {{input.from}} and book the appointment",
                "tools": {
                    "queries": ["appointments.slots.list"],
                    "commands": ["appointments.appointment.create"]
                },
                "policy": "auto",
                "max_iters": 4
            }]
        }))
        .expect("the shape the module `flows` writes for an agent step");

        let StepSpec::Ai(ai) = &def.steps[0].spec else {
            panic!("an `ai` step must parse into its own spec, not into Reserved");
        };
        assert_eq!(ai.prompt, "Answer {{input.from}} and book the appointment");
        assert_eq!(ai.queries, vec!["appointments.slots.list".to_string()]);
        assert_eq!(
            ai.commands,
            vec!["appointments.appointment.create".to_string()]
        );
        assert_eq!(ai.policy, AiPolicy::Auto);
        assert_eq!(ai.max_iters, 4);
    }

    /// ADR-0283 D3 in one assertion: an `ai` step that says nothing about its policy is
    /// **manual**. The permissive default is the one nobody writes down and everybody assumes,
    /// and here it would mean an unattended model writing to the business database.
    #[test]
    fn an_ai_step_without_a_policy_is_manual_and_bounded() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi" }]
        }))
        .unwrap();
        let StepSpec::Ai(ai) = &def.steps[0].spec else {
            panic!("ai spec");
        };
        assert_eq!(
            ai.policy,
            AiPolicy::Manual,
            "writes wait for a person unless the owner opted out IN WRITING"
        );
        assert_eq!(ai.max_iters, DEFAULT_MAX_ITERS);
        assert!(ai.queries.is_empty() && ai.commands.is_empty());
    }

    /// Every turn of the loop costs a call through the SaaS proxy, which meters real money
    /// (`AssistantUsage`). The cap is refused rather than clamped: a document that says 50 and
    /// runs 10 is a document lying to the person who wrote it.
    #[test]
    fn max_iters_above_the_cap_is_refused_not_silently_clamped() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi", "max_iters": 50 }]
        }))
        .expect_err("a runaway agent loop is real money");
        let text = format!("{err}");
        assert!(text.contains("max_iters") && text.contains("10"), "{text}");
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi", "max_iters": 0 }]
        }))
        .is_err());
    }

    #[test]
    fn an_ai_step_without_a_prompt_or_with_an_unknown_key_is_refused() {
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai" }]
        }))
        .is_err());
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi", "temperature": 0.9 }]
        }))
        .expect_err("hub#521's lesson: a key nobody reads must not look like a setting");
        assert!(format!("{err}").contains("temperature"), "{err}");
        // And an unknown policy is a typo that would otherwise read as "auto" or as nothing.
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi", "policy": "atuo" }]
        }))
        .is_err());
    }

    /// The prompt is mapped against the run like any other value, so an agent turn can talk about
    /// the sale that triggered it. Templates render to text — a prompt is text.
    #[test]
    fn the_prompt_is_resolved_against_the_run_like_any_other_mapping() {
        assert_eq!(
            resolve(&json!("Reply to {{input.customer.email}}"), &scope()),
            json!("Reply to marta@example.com")
        );
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

    /// hub#730. The gate is HERE, at the door the person knocks on. Everything below used to be
    /// `201 Created` + `enabled: true` + a `next_run` of NULL: a flow the screen calls «activo»
    /// and that was never going to run. An engine that promises and says nothing is worse than
    /// one that says no.
    #[test]
    fn a_cron_the_engine_cannot_run_is_refused_at_save_time() {
        for (expr, needle) in [
            ("esto no es un cron", "esto"),
            ("0 0 9 * * *", "5 fields"),
            ("* * *", "5 fields"),
            ("70 * * * *", "70"),
            ("0 9 * * FUNDAY", "FUNDAY"),
            ("*/0 * * * *", "step"),
            ("5-1 * * * *", "5-1"),
            ("@reboot", "@reboot"),
            ("0 0 30 2 *", "never"),
        ] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "triggers": [{ "kind": "cron", "cron": expr }],
                "steps": [{ "id": "a", "kind": "delay", "seconds": 1 }]
            }))
            .expect_err("`{expr}` would be stored armed and never fire");
            let RuntimeError::Domain { code, message } = &err else {
                panic!("`{expr}`: expected a domain error, got {err}");
            };
            assert_eq!(code, ERR_INVALID_CRON, "`{expr}`");
            assert!(
                message.contains(needle),
                "`{expr}`: the author has to be told WHAT is wrong; expected `{needle}` in `{message}`"
            );
            // …and the same message tells them what they CAN write.
            assert!(message.contains("*/N"), "`{expr}`: no syntax help in `{message}`");
        }
    }

    /// The other half of hub#730: what a person writes coming from crontab/Zapier/n8n has to
    /// WORK, not just be refused politely.
    #[test]
    fn the_cron_shapes_a_person_actually_writes_are_accepted() {
        for expr in [
            "1-5 * * * *",
            "1,15 * * * *",
            "0 9 * * MON",
            "0 9 * * MON-FRI",
            "30 8,20 * * *",
            "0-30/10 * * * *",
            "*/15 * * * *",
            "@daily",
            "0 0 29 2 *",
        ] {
            FlowDefinition::parse(&json!({
                "schema_version": 1,
                "triggers": [{ "kind": "cron", "cron": expr }],
                "steps": [{ "id": "a", "kind": "delay", "seconds": 1 }]
            }))
            .unwrap_or_else(|e| panic!("`{expr}` is a cron anybody would write: {e}"));
        }
    }

    /// Same family, same silence: `at: "manana por la tarde"` was copied straight into `next_run`.
    #[test]
    fn an_at_trigger_that_is_not_an_instant_is_refused() {
        for at in ["manana por la tarde", "2026-13-45", "tomorrow"] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "triggers": [{ "kind": "at", "at": at }],
                "steps": [{ "id": "a", "kind": "delay", "seconds": 1 }]
            }))
            .expect_err("`{at}` is not an instant");
            let RuntimeError::Domain { code, message } = &err else {
                panic!("`{at}`: expected a domain error, got {err}");
            };
            assert_eq!(code, ERR_INVALID_AT, "`{at}`");
            assert!(message.contains("RFC-3339"), "`{at}`: {message}");
        }
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "triggers": [{ "kind": "at", "at": "2026-08-11T09:00:00+02:00" }],
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
