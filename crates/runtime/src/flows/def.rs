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
use crate::flows::approvals::{ExpiryPolicy, RejectPolicy};
use crate::host_notify::Channel;

/// The only document version this kernel understands. An unknown version is REFUSED, never
/// guessed: a v2 document (branching/DAG, if it ever exists) describes an execution this binary
/// cannot perform, and running "the parts it recognises" would be a flow that does half of what
/// its author wrote.
pub const SCHEMA_VERSION: i64 = 1;

/// The roots a path may start from. Frozen: adding one later is additive, removing one is not.
const ROOT_INPUT: &str = "input";
const ROOT_STEPS: &str = "steps";
const ROOT_EVENT: &str = "event";
/// The run clock (hub#1694). A document could say what to do and to whom, never **when**: the
/// roots above are all facts somebody else wrote, so a `condition` had no way to ask whether a
/// timestamp was recent. Meta refuses a free WhatsApp message once the customer's last one is over
/// 24 h old, and the flow that sends it anyway pays for the call and learns nothing.
///
/// Shaped as an object with one field, `now.iso`, so it reads like every other path and so the
/// pieces a clock has (a local date, a local time) can be added later without moving anything.
const ROOT_NOW: &str = "now";
/// The instant, RFC-3339 in UTC — the same shape every timestamp this hub stores has, which is
/// what makes `gt`/`lt` order them correctly.
pub const CLOCK_ISO: &str = "iso";
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
/// hub#954 — a `query` step asking for more rows than [`MAX_QUERY_ROWS`]. Refused at save, like
/// `max_iters`: a document that says 1000 and reads 200 lies to whoever wrote it, and the silent
/// truncation is the single complaint every competitor's forum is full of.
pub const ERR_LIMIT_OUT_OF_RANGE: &str = "flow.limit_out_of_range";
/// hub#951 — a wait that would last longer than [`MAX_DELAY_HORIZON`]. Refused at save time when
/// the document says so literally (`seconds`, `max_wait`), and failed at run time when an `until`
/// resolves past it. **There was no ceiling at all**: `until` accepted the year 3000, and the run
/// slept as a `sleeping` row that every retention rule exempts on purpose.
pub const ERR_DELAY_HORIZON: &str = "flow.delay_horizon";
/// hub#951 — the instant a `delay` resolved to had already passed and the document said `fail`.
pub const ERR_DELAY_PAST_DUE: &str = "flow.delay_past_due";
/// hub#951 — a sleeping run moved more than [`MAX_RESCHEDULES`] times. A wait that keeps being
/// pushed forward by an event that keeps arriving is a run that never ends.
pub const ERR_MAX_RESCHEDULES: &str = "flow.max_reschedules";

/// **The most a single `delay` may wait: 90 days** (hub#951).
///
/// Shopify Flow's number, the most generous of the ten references studied (Zapier and Power
/// Automate kill the run at ~30 days). It is a ceiling and not a clamp, like every other limit in
/// this file: a document that says «wait two years» is refused, not quietly turned into 90 days.
pub const MAX_DELAY_HORIZON: i64 = 90 * 24 * 3600;

/// How many `cancel_on` / `reschedule_on` entries one `delay` may carry (hub#951). Small on
/// purpose: matching them runs on the hot path of **every** event delivery in the hub.
pub const MAX_WAIT_HOOKS: usize = 5;

/// How many `{event path: run path}` pairs one hook's `correlate` may carry. One is the case
/// («this appointment»); three is room for a composite key without turning the match into a join.
pub const MAX_CORRELATE_PAIRS: usize = 3;

/// How many times one sleeping run may be moved before the kernel stops it (hub#951). An event
/// that keeps arriving would otherwise push the same wait forward forever, and the run would never
/// end — the runaway guard of [`crate::flows::triggers::MAX_RUNS_PER_MINUTE`], one level down.
pub const MAX_RESCHEDULES: i64 = 20;

/// The most rows one `query` step may bring into a run (hub#954).
///
/// It is a hard ceiling and not a clamp. The reason it exists at all is that the read happens
/// inside the tick, under the runtime's global lock: a thousand rows there is every till in the
/// hub waiting. And the reason it is the DEFAULT too is the market's own lesson — Make's invisible
/// `Limit: 10` and Zapier's «only the first» are the truncations their forums are full of, so a
/// step that says nothing about how much it wants is capped, never quietly cut short.
pub const MAX_QUERY_ROWS: i64 = 200;

/// The most rows one `query` step may publish as [`QueryResult::Options`] (hub#1641).
///
/// Ten, and not [`MAX_QUERY_ROWS`], because these rows have ONE destination: the tappable list of
/// an `interactive` send (hub#1633), and Meta holds ten rows in a list. The default is the ceiling
/// for the same reason it is above — a step that says nothing about how much it wants is capped,
/// never quietly cut short — but the ceiling itself is the transport's, because a read that
/// carries 200 rows into a message that holds 10 is a document that cannot do what it says.
///
/// It is the FLOOR of the refusals, not the last word: the SaaS proxy still checks the message it
/// is handed (`whatsapp_inbox/services/interactive.py`: three buttons, ten rows TOTAL across
/// sections, each title and id within Meta's lengths). What this ceiling buys is that the common
/// mistake is refused on the screen where it was typed instead of in a tick at 3 AM.
pub const MAX_OPTION_ROWS: i64 = 10;

/// Turns of the agent loop when the document does not say (ADR-0283 §7).
pub const DEFAULT_MAX_ITERS: i64 = 6;
/// Hard ceiling, refused above rather than clamped. Every turn is a real call through the SaaS
/// proxy, which meters it (`AssistantUsage`): a runaway agent loop is money, not just latency.
pub const MAX_ITERS_CAP: i64 = 10;

/// How long an `approval` step waits when the document does not say (hub#950): **72 hours**.
///
/// The same number the `ai` tray has always used ([`crate::flows::approvals::DEFAULT_TTL_HOURS`]),
/// and it is a default rather than a fixed rule for one reason the forums make plain: 72 h fixed
/// dies over a long weekend, and a question that expired while the shop was shut is a run somebody
/// has to restart on Tuesday morning.
pub const DEFAULT_APPROVAL_TTL_SECONDS: i64 = 72 * 3600;
/// Hard ceiling, refused above rather than clamped: **30 days**, Power Automate's own number and
/// the order of magnitude of a Business Central `Due Date Formula`. A run parked for longer is a
/// standing authorisation nobody remembers giving, and it holds its `payload` past every retention
/// rule the hub has (`waiting_approval` is exempt from the prune on purpose).
pub const MAX_APPROVAL_TTL_SECONDS: i64 = 30 * 24 * 3600;

fn invalid(code: &str, message: impl Into<String>) -> RuntimeError {
    RuntimeError::Domain {
        code: code.to_string(),
        message: message.into(),
    }
}

// ── Steps ─────────────────────────────────────────────────────────────────────────────────────

/// The step kinds of `schema_version: 1` (ADR-0283 §5). The VOCABULARY is frozen here, and since
/// hub#821 every one of them EXECUTES: the list of what a document may say and the list of what
/// this kernel performs are finally the same list.
///
/// hub#954 added the seventh, `query`, and it is the one addition that took nothing new from the
/// permission model: `GrantKind::Query` and `grants::check_query_grant` have gated the `ai` step's
/// reads since hub#665. What the kernel gained is the ability to say «read this» without a model
/// in the middle — a deterministic read instead of a non-deterministic one.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StepKind {
    Command,
    /// hub#954 — a DETERMINISTIC read. The grant it goes through (`GrantKind::Query`) and the door
    /// it opens have run in production since hub#665; what was missing was a way to say «read
    /// this» without putting a language model in the middle of it.
    Query,
    Condition,
    Delay,
    /// The first way out to the internet (hub#662): allow-listed URL + `_flow_secrets`.
    Http,
    /// The server-side agent runner (hub#665).
    Ai,
    /// hub#821 — a message to a person, addressed through a `recipient_query` grant. It is the
    /// only step that can reach somebody who is not in the hub's allow-list: a CUSTOMER.
    Notify,
    /// hub#950 — the pause. The kernel already knew how to stop and wait for a person, but only as
    /// a side effect of an `ai` step: the row in `_flow_approvals` was always a WRITE a model had
    /// proposed, so «shall I carry on?» cost a metered, non-deterministic call to a language model
    /// to ask a yes/no question. This is that pause with the model taken out of it.
    Approval,
}

impl StepKind {
    pub fn as_str(self) -> &'static str {
        match self {
            StepKind::Command => "command",
            StepKind::Query => "query",
            StepKind::Condition => "condition",
            StepKind::Delay => "delay",
            StepKind::Http => "http",
            StepKind::Ai => "ai",
            StepKind::Notify => "notify",
            StepKind::Approval => "approval",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        Some(match s {
            "command" => StepKind::Command,
            "query" => StepKind::Query,
            "condition" => StepKind::Condition,
            "delay" => StepKind::Delay,
            "http" => StepKind::Http,
            "ai" => StepKind::Ai,
            "notify" => StepKind::Notify,
            "approval" => StepKind::Approval,
            _ => return None,
        })
    }

    /// Does this kind reach outside the runtime **from inside the tick**? Those follow the
    /// **claim → I/O → complete** contract: the tick prepares them, the server performs the I/O
    /// outside the global lock, and a second locked pass persists the result.
    ///
    /// `notify` is deliberately NOT one of them (hub#821). It does no I/O of its own: it resolves
    /// the recipient with a local read and QUEUES a host-notify event, and the outbox relay — which
    /// already has the retries, the backoff and the dead-letter — is what talks to the network.
    /// Crossing the seam instead would have meant reimplementing all of that beside it.
    pub fn needs_io(self) -> bool {
        matches!(self, StepKind::Http | StepKind::Ai)
    }

    /// Can this hub EXECUTE this kind? Every kind in the vocabulary runs: `http` joined with
    /// hub#662, `ai` with hub#665, `notify` with hub#821 and `query` with hub#954. The guard that
    /// used this stays where it is, because the rule it enforced is what got them here one at a
    /// time — a flow is never stored with a step nothing performs.
    pub fn is_available(self) -> bool {
        true
    }

    /// Every kind, in document order. Mirrored by `schemas/flow.schema.json`.
    pub const ALL: &'static [StepKind] = &[
        StepKind::Command,
        StepKind::Query,
        StepKind::Condition,
        StepKind::Delay,
        StepKind::Http,
        StepKind::Ai,
        StepKind::Notify,
        StepKind::Approval,
    ];
}

/// **What a FAILURE costs the run** — the value of a step's `on_error` (hub#1635).
///
/// Until this existed the answer was hard-wired: a step that failed ended the run, and the steps
/// written after it never ran. That is the right DEFAULT and it stays the default — a linear
/// document whose write did not happen has no business carrying on as if it had. What it is not is
/// the right ANSWER for every document: the steps written after a booking are the ones that TELL
/// the person who asked for it, so «stop» means the customer waits for a confirmation that will
/// never come while the salon reads the failure in its tray.
///
/// 🔴 **The vocabulary is closed at two values, and `retry` is deliberately not one of them.**
/// ADR-0283 §1 is not being reversed here: re-running a business command on the kernel's own
/// initiative is how a sale gets charged twice, and no value of this enum can ask for it.
/// [`ErrorPolicy::Continue`] runs NOTHING again — it moves to the NEXT step, which is a different
/// instruction the document already contains. That distinction is the whole decision.
pub const ON_ERROR_STOP: &str = "stop";
pub const ON_ERROR_CONTINUE: &str = "continue";

/// The parsed form of that key.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ErrorPolicy {
    /// End the run as `failed` — **the DEFAULT, and what a failure has always done**.
    #[default]
    Stop,
    /// Carry on to the next step. The step itself is still `failed` and still records why; what
    /// changes is the RUN. The next step reads how this one ended with `{{steps.<id>.status}}`
    /// (`"failed"`) and `{{steps.<id>.error}}` — the same shape `on_reject: "continue"` hands over
    /// (hub#1622), so a document that already knows how to word a refusal knows how to word this.
    Continue,
}

impl ErrorPolicy {
    /// Anything unrecognised degrades to [`ErrorPolicy::Stop`] — fail CLOSED, the same rule
    /// [`crate::flows::approvals::ExpiryPolicy::parse`] follows. Documents are validated before
    /// they are stored, so this only answers for a row written by a NEWER version of the hub, and
    /// «carry on past a failure I do not understand» is not an answer this binary may guess.
    pub fn parse(raw: &str) -> Self {
        match raw {
            ON_ERROR_CONTINUE => Self::Continue,
            _ => Self::Stop,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Stop => ON_ERROR_STOP,
            Self::Continue => ON_ERROR_CONTINUE,
        }
    }

    /// Every value, in document order. Mirrored by `schemas/flow.schema.json`.
    pub const ALL: &'static [ErrorPolicy] = &[Self::Stop, Self::Continue];
}

/// What a step does, once its kind is known. The kind-specific keys are parsed **strictly** for
/// the kinds that run; for the reserved ones nothing is parsed, because guessing the shape of a
/// step this kernel cannot execute would freeze a contract nobody has validated.
#[derive(Debug, Clone, PartialEq)]
pub enum StepSpec {
    /// `{"kind":"command","command":"sales.sale.create","params":{…}}` — the params are mapped
    /// (paths/templates) against the run before the command sees them.
    Command {
        command: String,
        params: Map<String, Json>,
    },
    /// `{"kind":"query","query":"sales.summary","params":{…},"result":"first","limit":50}` — a
    /// deterministic read (hub#954). See [`QueryStep`].
    Query(QueryStep),
    /// `{"kind":"condition","when":{…}}` — a guard. False stops the run; v1 is linear, so there
    /// is no "else" branch to go to.
    Condition { when: Condition },
    /// `{"kind":"delay","seconds":N}` or `{"kind":"delay","until":"input.when"}` — the run sleeps
    /// as a row (`wake_at`), never as a held task. See [`DelayStep`] for the rest of it (hub#951).
    Delay(DelayStep),
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
    /// `{"kind":"notify","channel":"whatsapp","to":{…},"template":…,"vars":{…}}` — a message to a
    /// person (hub#821). See [`NotifyStep`].
    Notify(NotifyStep),
    /// `{"kind":"approval","title":…,"summary":…,"assignee":{"role":…},"expires_in":N,
    /// "on_expire":…,"on_reject":…}` — the pause (hub#950). See [`ApprovalStep`].
    Approval(ApprovalStep),
}

/// **A wait, and the several ways out of it** (hub#951).
///
/// The shape is the market's (decision published on the issue, 2026-08-15), and it is three
/// references stacked, not one:
///
/// - **Salesforce Flow's *Scheduled Paths*** give [`DelayStep::until`] + [`DelayStep::offset_seconds`]:
///   a wait is expressed against a **date field of the thing** («24 h before the appointment»),
///   which is the only form a shop owner writes without typing a date.
/// - **NetSuite SuiteFlow's scheduled transition** gives [`DelayStep::cancel_on`] /
///   [`DelayStep::reschedule_on`]: the wait is a STATE with several exits — the clock is one of
///   them — and the first atomic transition takes the run out of it. That is the answer to «never
///   both», and it is a property of the UPDATE, not a lock (see [`crate::flows::waits`]).
/// - **Klaviyo's re-check before acting** is deliberately NOT a field here. A `cancel_on` can be
///   MISSED — the event was never emitted, the module was uninstalled, the hub was off — so the
///   belt-and-braces is to look again, and that composes out of primitives that already exist:
///   `delay → query (hub#954) → condition`. A fourth key promising it would be a second engine.
///
/// What the market does that we do not: Odoo cancels for free, but only because its engine knows
/// the module's table — the one option of the ten that would break our modularity. Zapier, Power
/// Automate, Make and Shopify Flow simply cannot cancel a wait at all, and their forums all
/// converge on the same workaround, which is the re-check above.
#[derive(Debug, Clone, PartialEq)]
pub struct DelayStep {
    /// A relative wait, in seconds from the moment the run reaches the step.
    pub seconds: Option<i64>,
    /// A path to an RFC-3339 instant. Alternative to [`DelayStep::seconds`]; one of the two is
    /// required.
    pub until: Option<String>,
    /// Seconds added to (or subtracted from) the resolved `until`. **Seconds and not «1 month»**:
    /// a calendar offset is an operation the frozen mapping language does not have, and inventing
    /// one here would be a DSL growing after the freeze. Salesforce offers months; we do not, and
    /// that is a conscious limit of v1.
    pub offset_seconds: i64,
    /// The ceiling this particular wait accepts, in seconds. `None` means [`MAX_DELAY_HORIZON`].
    pub max_wait: Option<i64>,
    /// What happens when the resolved instant has ALREADY passed.
    pub past_due: PastDuePolicy,
    /// Events that take the run OUT of the wait, cancelled. At most [`MAX_WAIT_HOOKS`].
    pub cancel_on: Vec<WaitHook>,
    /// Events that MOVE the wait to a new instant. At most [`MAX_WAIT_HOOKS`].
    pub reschedule_on: Vec<WaitHook>,
}

impl DelayStep {
    /// The ceiling that applies to this wait: what the document asked for, or the hub's.
    pub fn horizon_seconds(&self) -> i64 {
        self.max_wait.unwrap_or(MAX_DELAY_HORIZON)
    }

    /// Every hook, with the kind it is armed as. The order is the one the document wrote.
    pub fn hooks(&self) -> impl Iterator<Item = (WaitKind, &WaitHook)> {
        self.cancel_on
            .iter()
            .map(|h| (WaitKind::Cancel, h))
            .chain(self.reschedule_on.iter().map(|h| (WaitKind::Reschedule, h)))
    }
}

/// Which exit of the wait a [`WaitHook`] is (hub#951).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WaitKind {
    /// The run leaves the wait `cancelled`.
    Cancel,
    /// The wait moves to a new instant and the run keeps sleeping.
    Reschedule,
}

impl WaitKind {
    pub fn as_str(self) -> &'static str {
        match self {
            WaitKind::Cancel => "cancel",
            WaitKind::Reschedule => "reschedule",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "cancel" => Some(WaitKind::Cancel),
            "reschedule" => Some(WaitKind::Reschedule),
            _ => None,
        }
    }
    pub const ALL: &'static [WaitKind] = &[WaitKind::Cancel, WaitKind::Reschedule];
}

/// **One exit of a wait**: an event, an optional filter over it, and the correlation that makes it
/// about THIS run (hub#951).
///
/// [`WaitHook::correlate`] is the load-bearing half. Without it the first cancellation of any
/// appointment would cancel every armed reminder in the hub. It maps a path **in the arriving
/// event** to a path **in the run**, both in the frozen path language and nothing else: a `{{…}}`
/// template on the event side would be a correlation key whoever emits the event gets to write,
/// and a literal on the run side would correlate on a constant.
#[derive(Debug, Clone, PartialEq)]
pub struct WaitHook {
    /// The public event name, matched in the outbox relay exactly like a trigger's.
    pub event: String,
    /// An optional declarative filter over the event payload (`event.<field>` paths).
    pub filter: Condition,
    /// `{<path in the event>: <path in the run>}`. 1..=[`MAX_CORRELATE_PAIRS`] entries, all of
    /// which must agree for the hook to fire.
    pub correlate: BTreeMap<String, String>,
    /// [`WaitKind::Reschedule`] only — the path, **in the arriving event**, to the new instant.
    /// Required there, and refused on a `cancel_on` where nobody would ever read it.
    pub until: Option<String>,
}

/// **What a `delay` does when the instant it resolved to has already passed** (hub#951).
///
/// The default is `skip`, and that is deliberately NOT what Salesforce does (it runs the scheduled
/// path immediately). The rule that wins here is the kernel's own — the default is the restrictive
/// one, the same reason [`AiPolicy::Manual`] is the default — because the literal case is a
/// reminder whose hour went by, and sending it late is worse than not sending it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PastDuePolicy {
    /// Do not sleep: carry on with the next step now. Salesforce's behaviour, available to whoever
    /// writes it down.
    ContinueNow,
    /// The run ENDS, `done` — like a `condition` that said no. The default.
    Skip,
    /// The run ends `failed`, with [`ERR_DELAY_PAST_DUE`]. For the flow where a missed instant is a
    /// problem somebody has to see.
    Fail,
}

impl PastDuePolicy {
    pub fn as_str(self) -> &'static str {
        match self {
            PastDuePolicy::ContinueNow => "continue_now",
            PastDuePolicy::Skip => "skip",
            PastDuePolicy::Fail => "fail",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "continue_now" => Some(PastDuePolicy::ContinueNow),
            "skip" => Some(PastDuePolicy::Skip),
            "fail" => Some(PastDuePolicy::Fail),
            _ => None,
        }
    }
    pub const ALL: &'static [PastDuePolicy] = &[
        PastDuePolicy::ContinueNow,
        PastDuePolicy::Skip,
        PastDuePolicy::Fail,
    ];
}

impl Default for PastDuePolicy {
    fn default() -> Self {
        PastDuePolicy::Skip
    }
}

/// **A question, and what happens to the run depending on how it is answered** (hub#950).
///
/// The shape is the market's, not ours (decision published on the issue, 2026-08-15): the
/// **object** of Power Automate's *Start and wait for an approval* — the approval is a persisted
/// thing with a life of its own, which is what lets a decision taken two days later still mean
/// something — corrected by the **explicit due date** of Business Central's `Due Date Formula`,
/// which is precisely the half Power Automate is documented to do badly.
///
/// The three branches the original contract asked for (`approved` / `rejected` / `expired`) are
/// **policies of outcome**, not branches, because v1 of the document is LINEAR. That is n8n's
/// answer (`Limit Wait Time` continues down one path) rather than Salesforce's (a whole approval
/// subsystem the flow submits to, which would mean a second engine). With `continue` plus a
/// `condition`, the three branches compose out of primitives that are already frozen — the same
/// move the `query` step of hub#954 made.
#[derive(Debug, Clone, PartialEq)]
pub struct ApprovalStep {
    /// The question, in words. Mapped against the run like any other value, and rendered ONCE —
    /// when the question is asked — so editing the flow afterwards cannot change what the person
    /// looking at the tray is agreeing to.
    pub title: String,
    /// A second line of the same question. Optional; mapped the same way.
    pub summary: String,
    /// **The role that may answer** — Odoo's `Allowed Group`. A role and never a person: naming
    /// somebody in a document breaks the day they leave, which is the hole Business Central had to
    /// invent a "substitute" for. Empty (the default) means whoever administers the hub, which is
    /// what the tray has always required.
    pub assignee_role: String,
    /// How long it stays decidable. Default 72 h — a fixed deadline dies over a long weekend —
    /// with a ceiling of 30 days, which is Power Automate's own number and the order of magnitude
    /// of a `Due Date Formula`.
    pub expires_in_seconds: i64,
    pub on_expire: ExpiryPolicy,
    pub on_reject: RejectPolicy,
}

/// **A message, and the only way a flow may address one** (hub#821, ADR-0283 §5).
///
/// The recipient is not a value: it is a QUERY and a FIELD, both named in a live
/// `recipient_query` grant. There is deliberately no literal form — not even a template — because
/// the whole hole this closes is a flow (or a template installed from the marketplace) putting an
/// address from the event payload into `to` and mailing it. What an author writes is «the phone
/// column of the customer this run is about»; the hub reads it, and the owner can revoke that
/// sentence.
#[derive(Debug, Clone, PartialEq)]
pub struct NotifyStep {
    /// `email` or `whatsapp`. Needs its own live `notify` grant — see [`crate::flows::grants`].
    pub channel: Channel,
    /// The read the recipient comes out of. Executed read-only with the flow's own context.
    pub query: String,
    /// Its params, mapped against the run like any other value.
    pub params: Map<String, Json>,
    /// The column of the returned row that IS the recipient.
    pub field: String,
    /// The template NAME. There is no catalogue in the hub (flows.md §5): for WhatsApp it is
    /// Meta's approved template, for email it doubles as the subject when `vars` gives none.
    pub template: String,
    /// The copy, mapped against the run. `vars.text` is what an email or a free WhatsApp message
    /// says; the transport refuses an intent with nothing to say rather than inventing it.
    pub vars: Map<String, Json>,
    /// **Options the customer TAPS** (hub#1633): Meta's own `interactive` object, mapped against
    /// the run like the copy and carried to the proxy unchanged. `None` is the ordinary message.
    pub interactive: Option<Map<String, Json>>,
}

/// **A read a flow performs itself** (hub#954), shaped after Salesforce Flow's *Get Records* —
/// the form the market converged on, and the only one of the ten references studied that makes
/// «how many rows» an explicit choice of the author with a hard ceiling behind it.
///
/// It adds NO permission surface: the door is [`crate::flows::grants::check_query_grant`], the
/// same one the `ai` step's reads have gone through since hub#665. What changes is that a read no
/// longer needs a language model in front of it.
#[derive(Debug, Clone, PartialEq)]
pub struct QueryStep {
    /// The read, by name. It must exist in the registry at SAVE time (`flows::store`), the same
    /// rule a `query` grant follows: a grant naming nothing reads like a permission and is not
    /// one, and a step naming nothing reads like a read and is not one either.
    pub query: String,
    /// Its params, mapped against the run like any other value.
    pub params: Map<String, Json>,
    /// What lands in `steps.<id>`.
    pub result: QueryResult,
    /// The ceiling of rows this read may bring into the tick. `1..=`[`MAX_QUERY_ROWS`], refused
    /// above it at save time, and defaulting to the ceiling itself. A read that publishes
    /// [`QueryResult::Options`] is held to the smaller [`MAX_OPTION_ROWS`] instead.
    pub limit: i64,
    /// Which COLUMNS of each row make up the option the customer taps. Present exactly when
    /// `result` is [`QueryResult::Options`] — required there because a list of table columns is
    /// not something the transport can send, and refused elsewhere because a mapping nothing reads
    /// is a promise the kernel does not keep.
    pub options: Option<OptionShape>,
}

/// **The shape of one tappable option, read off the row** (hub#1641).
///
/// Column NAMES, not paths and not templates — the same idiom as [`NotifyStep::field`], which has
/// picked the recipient out of a row by column name since hub#821. Composing a title out of two
/// columns is a shape that belongs in the query, which is the same answer [`resolve_path`] gives
/// to «the third line of the ticket»: the flow document maps fields, the module writes the SELECT.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OptionShape {
    /// The column whose value comes back as `event.reply_id` when she taps the row.
    pub id: String,
    /// The column she reads on the row.
    pub title: String,
    /// The optional second line. Absent here, or empty on a row, and the key is simply not sent —
    /// Meta refuses a `description: null`.
    pub description: Option<String>,
}

/// **What a `query` step leaves behind** — and, deliberately, still not a bag of raw rows.
///
/// `rows` is NOT in v1 because [`resolve_path`] does not index arrays: a document could write
/// `steps.week.rows.0.total` and the kernel would resolve it to nothing, silently. That refusal
/// stands. What hub#1641 adds is the case it was standing in the way of, and it adds it WITHOUT
/// opening the array: a list can travel WHOLE, as one value, to the one place that reads a whole
/// list — the `rows` of an `interactive` send (hub#1633). So the third shape is not «the rows»,
/// it is [`QueryResult::Options`]: rows already in the form the transport receives.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QueryResult {
    /// The fields of the FIRST row, at the root of `steps.<id>`, plus `found` and `count`. The
    /// default, and Salesforce's *Only the first record*.
    First,
    /// Only `count` and `found`. «Are there any, and how many» without carrying the rows.
    Count,
    /// `steps.<id>.options` — the whole list, as `[{id, title, description}]`, plus `found` and
    /// `count`. Meta's own row shape, by the same criterion as [`AiOutputKind::Options`]
    /// (hub#1639) and [`NotifyStep::interactive`] (hub#1633): the kernel grows the shape the
    /// transport already knows, so a document reads the same whether the list came from a model
    /// or from the database. The array is addressed as ONE value (`steps.free.options`) and never
    /// indexed, which is why this needs nothing from [`resolve_path`].
    Options,
}

impl QueryResult {
    pub fn as_str(self) -> &'static str {
        match self {
            QueryResult::First => "first",
            QueryResult::Count => "count",
            QueryResult::Options => "options",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "first" => Some(QueryResult::First),
            "count" => Some(QueryResult::Count),
            "options" => Some(QueryResult::Options),
            _ => None,
        }
    }
    /// The ceiling this shape holds its `limit` to, and the default when the document is silent.
    pub fn row_ceiling(self) -> i64 {
        match self {
            QueryResult::Options => MAX_OPTION_ROWS,
            QueryResult::First | QueryResult::Count => MAX_QUERY_ROWS,
        }
    }
    pub const ALL: &'static [QueryResult] =
        &[QueryResult::First, QueryResult::Count, QueryResult::Options];
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
    /// **What a SILENCE costs the run** (hub#1634). The sister of [`AiStep::on_reject`], and
    /// reachable under the same policy: a proposal nobody ever answers expires at 72 h, and until
    /// this key existed that always ended the run — so the step written to tell the customer
    /// nobody got back to her went unrun, which is the whole bug.
    ///
    /// Same closed vocabulary as [`ApprovalStep::on_expire`] and the same default,
    /// [`ExpiryPolicy::Reject`]: every document already deployed says nothing here, and a silence
    /// is read as a refusal because the steps after a proposal assumed it acted.
    ///
    /// Read from the flow at PROPOSE time and copied into the row, exactly like `on_reject`; from
    /// then on the sweep reads the ROW (see [`crate::flows::approvals::ExpiryPolicy`]), so editing
    /// the document while a question is sitting in the tray does not change what its silence costs.
    pub on_expire: ExpiryPolicy,
    /// **What a «no» costs the run** (hub#1622). Only reachable under [`AiPolicy::Manual`], which
    /// is the only policy that asks anybody: an `auto` step proposes nothing and there is nothing
    /// to refuse.
    ///
    /// It exists here for the same reason it exists on [`ApprovalStep`], and it is the same
    /// vocabulary: [`RejectPolicy::Cancel`] — the default, and what a rejection has always done —
    /// or [`RejectPolicy::Continue`], which carries on to the next step so that a document can
    /// answer the person who is waiting. Without it every step written after the proposal went
    /// unrun on a refusal, including the one that says «we could not fit you in after all».
    ///
    /// Read from the flow at PROPOSE time and copied into the row; from then on the decision reads
    /// the ROW (see [`crate::flows::approvals::RejectPolicy`]), so editing the document while
    /// somebody is looking at the tray does not change what their refusal costs.
    pub on_reject: RejectPolicy,
    /// **The data the turn leaves behind, declared by the author** (hub#1639). Empty — the default
    /// and what every flow in production is written against — means the step publishes what it
    /// always has: `{text, tool_calls}`.
    ///
    /// A declared field becomes `steps.<id>.<name>` next to those two, so the options the model
    /// found mid-conversation can be the rows of the list the customer taps
    /// ([`NotifyStep::interactive`], hub#1633) and a later step can branch on what the turn
    /// actually did.
    ///
    /// A `Vec` and not a map because the runner turns it into a SEQUENCE the model is asked for,
    /// and that sequence has to be the same on every save: the kernel's JSON object is ordered by
    /// key, so parsing the same document twice asks for the same fields in the same order.
    pub output: Vec<AiOutputField>,
}

/// One field an [`AiStep`] promises to leave behind (hub#1639).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AiOutputField {
    /// Addressable by the mapping language: letters, digits and `_`, starting with a letter.
    /// [`resolve_path`] splits on `.`, so a dotted name would address a level that does not exist
    /// and resolve to nothing — silently, which is why `rows` was kept out of v1 in the first
    /// place.
    pub name: String,
    pub kind: AiOutputKind,
    /// What the model is told this field is for. Required, because it is the ONLY thing it reads
    /// about the field: a field with nothing to read is a field filled with whatever the model
    /// likes.
    pub describe: String,
}

/// **What shape a declared output field may be** (hub#1639).
///
/// Closed, and deliberately short. This is not a schema language: it is the three shapes the hub
/// can answer for on the way out. `Options` is Meta's own row shape for the same reason
/// [`NotifyStep::interactive`] is Meta's own object (hub#1633) — the kernel grows the shape the
/// transport already knows instead of a general one it would then have to translate.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AiOutputKind {
    /// One line of prose.
    Text,
    /// A number, as a number — so a later `condition` compares it as one.
    Number,
    /// The tappable list: `[{id, title, description}]`, ready to be the `rows` of an
    /// `interactive` send without anything in between reshaping it.
    Options,
}

impl AiOutputKind {
    pub fn as_str(self) -> &'static str {
        match self {
            AiOutputKind::Text => "text",
            AiOutputKind::Number => "number",
            AiOutputKind::Options => "options",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "text" => Some(AiOutputKind::Text),
            "number" => Some(AiOutputKind::Number),
            "options" => Some(AiOutputKind::Options),
            _ => None,
        }
    }
    pub const ALL: &'static [AiOutputKind] = &[
        AiOutputKind::Text,
        AiOutputKind::Number,
        AiOutputKind::Options,
    ];
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
    /// What a FAILURE of this step costs the run (hub#1635). Only the kinds that CAN fail accept
    /// the key; for the rest it is an unknown key, refused like any other — a `condition` that
    /// does not match is the flow working, not an error, and offering a policy for a failure that
    /// cannot happen is a guard nobody executes.
    pub on_error: ErrorPolicy,
}

impl StepDef {
    /// Every mapping expression this step evaluates, in document order.
    fn expressions(&self) -> Vec<Json> {
        match &self.spec {
            StepSpec::Command { params, .. } => vec![Json::Object(params.clone())],
            // The params of a read are mapped like a command's, so the `secret.…` refusal of
            // hub#662 has to reach them for the same reason: a credential interpolated into a
            // `WHERE` is one handed to a module's table and written to its query log.
            StepSpec::Query(q) => vec![Json::Object(q.params.clone())],
            // Both sides of every clause (hub#828): the paths it reads and the values it compares
            // against. Scanning only the paths left `{"input.x": {"eq": "{{secret.K}}"}}` saving
            // as literal text — a guard that never matches and never says so.
            StepSpec::Condition { when } => when.expressions(),
            // The instant, and everything the hooks of hub#951 say. The scan has to reach INSIDE
            // them for the same reason it reaches both sides of a condition (hub#828): a filter
            // comparing against `{{secret.K}}` is a guard that never matches and never says so,
            // and a hook's `until` naming one is a credential parsed as a date.
            StepSpec::Delay(d) => {
                let mut out: Vec<Json> = d.until.iter().map(|u| json_str(u)).collect();
                for (_, hook) in d.hooks() {
                    out.extend(hook.filter.expressions());
                    out.extend(hook.until.iter().map(|u| json_str(u)));
                    for (event_path, run_path) in &hook.correlate {
                        out.push(json_str(event_path));
                        out.push(json_str(run_path));
                    }
                }
                out
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
            // Everything a `notify` step maps: the params of the recipient read and the copy. The
            // `secret.…` refusal of hub#662 has to reach both — a credential interpolated into a
            // message would be sent to a customer, and one interpolated into the params of the read
            // would be handed to a module's table.
            // …and INSIDE the tappable options (hub#1633), for the most literal reason of all:
            // a credential interpolated into a button's title is printed on a customer's phone.
            // `resolve` recurses, so the scan has to as well or a secret hides two objects deep.
            StepSpec::Notify(n) => {
                let mut out = vec![
                    Json::Object(n.params.clone()),
                    Json::Object(n.vars.clone()),
                    json_str(&n.template),
                ];
                out.extend(n.interactive.clone().map(Json::Object));
                out
            }
            // The question a person reads. The `secret.…` refusal has to reach it for the most
            // literal reason of all: the tray is a SCREEN, and a credential interpolated into a
            // title would be printed on it for anybody who can open the approvals list.
            StepSpec::Approval(a) => vec![json_str(&a.title), json_str(&a.summary)],
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
    /// «Is this instant at most N seconds old?» (hub#1694). The tenth, and the only one whose
    /// answer depends on the clock instead of on two values the document already has: a window is
    /// the one comparison a frozen language cannot express by naming both sides, because one of
    /// them does not exist until the run reaches the step.
    WithinLast,
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
            Op::WithinLast => "within_last",
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
            "within_last" => Op::WithinLast,
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
        Op::WithinLast,
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
                check_comparand(path, op, expected)?;
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
        // One instant for the whole condition: two clauses about the same window must not land on
        // either side of a tick.
        let now = scope
            .get(ROOT_NOW)
            .and_then(|c| c.get(CLOCK_ISO))
            .and_then(|v| v.as_str());
        self.0.iter().all(|(path, ops)| {
            let actual = resolve_path(path, scope).unwrap_or(Json::Null);
            ops.iter()
                .all(|(op, expected)| eval(*op, &actual, expected, now))
        })
    }

    /// **Everything this condition names**, as expressions for the save-time scan: the paths it
    /// READS (the left of each clause) *and* the values it compares against (the right of every
    /// operator, including each item of an `in` array).
    ///
    /// The two halves are here for two different reasons, and only the first one was ever scanned:
    ///
    /// - the **left** is resolved against the run, so `secret.API_KEY` there is a real read — and
    ///   with `lt`/`contains` a machine that guesses the credential byte by byte. That is the
    ///   dangerous shape, and it has been refused since hub#662.
    /// - the **right** is never resolved: it is literal text. `{"input.x": {"eq":
    ///   "{{secret.K}}"}}` compared the answer against the eighteen characters `{{secret.K}}`, so
    ///   the guard its author wrote never matched and no error, run status or log said why
    ///   (hub#828). It is not a leak; it is a flow that does something other than what its
    ///   document says, which §13.2 refuses at save time rather than storing.
    fn expressions(&self) -> Vec<Json> {
        let mut out: Vec<Json> = self.0.keys().map(|p| json_str(p)).collect();
        for ops in self.0.values() {
            out.extend(ops.iter().map(|(_, expected)| expected.clone()));
        }
        out
    }
}

/// What the right of an operator is allowed to be.
///
/// Two refusals, both of the same family: a clause that would be stored meaning something other
/// than what it says.
///
/// - **The clock on the right.** The right is never resolved (hub#828), so `{"gte": "now.iso"}`
///   would compare a timestamp against the seven characters `now.iso` — `false` for ever, no error
///   and nothing in the run's history saying why. [`Op::WithinLast`] is what a window is written
///   with, and the message says so.
/// - **A window that is not a number of seconds.** `"24h"` is the shape everybody reaches for and
///   the kernel has no duration grammar (durations are seconds here: `delay.seconds`, `max_wait`).
///   Read as «not comparable», a window answers `false` and the guard silently stops letting
///   anything through; read as zero, it lets everything. Both are worse than not saving.
fn check_comparand(path: &str, op: Op, expected: &Json) -> Result<()> {
    let mut paths = Vec::new();
    template_paths(expected, &mut paths);
    if let Some(named) = paths
        .iter()
        .find(|p| p.split('.').next() == Some(ROOT_NOW))
    {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "condition on `{path}`: the right of `{}` is literal text, so `{named}` there \
                 would be compared as the characters `{named}` and never match. A window \
                 on the clock is written `{{\"within_last\": <seconds>}}`.",
                op.as_str()
            ),
        ));
    }
    if op == Op::WithinLast && !expected.as_i64().is_some_and(|s| s > 0) {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "condition on `{path}`: `within_last` is a whole number of SECONDS greater \
                 than zero (86400 is a day), not {expected}"
            ),
        ));
    }
    Ok(())
}

/// One operator against one pair of values. `now` is the run clock the whole condition is being
/// judged at, absent when the scope carries none.
fn eval(op: Op, actual: &Json, expected: &Json, now: Option<&str>) -> bool {
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
        // A scope with no clock, a left that is not an instant, a window that is not a number:
        // every way of not knowing answers **no**. This is the clause of an AND that guards a
        // message going out, and a guard that cannot judge must not be the one that waves it
        // through.
        Op::WithinLast => match (as_instant(actual), now.and_then(as_instant_str), expected.as_i64())
        {
            (Some(at), Some(now), Some(seconds)) if seconds > 0 => {
                match now.checked_sub_signed(chrono::Duration::seconds(seconds)) {
                    Some(floor) => at >= floor,
                    // A window so wide the arithmetic leaves the calendar contains everything.
                    None => true,
                }
            }
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

/// An RFC-3339 instant, as UTC. Only a string is one: a number here is an amount of something,
/// and guessing it is an epoch is how a total became a date.
fn as_instant(v: &Json) -> Option<chrono::DateTime<chrono::Utc>> {
    v.as_str().and_then(as_instant_str)
}

fn as_instant_str(s: &str) -> Option<chrono::DateTime<chrono::Utc>> {
    chrono::DateTime::parse_from_rfc3339(s.trim())
        .ok()
        .map(|t| t.with_timezone(&chrono::Utc))
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
        if (root == ROOT_INPUT
            || root == ROOT_STEPS
            || root == ROOT_EVENT
            || root == ROOT_SECRET
            || root == ROOT_NOW)
            && s.len() > root.len() + 1)
}

/// The run clock as the mapping language addresses it, ready to be merged into a scope.
///
/// Read **once per evaluation** and carried in the scope rather than read from the system clock
/// deep inside [`Condition::matches`]: every clause of one condition then judges the same instant,
/// and a test can say what time it is.
pub fn clock() -> Json {
    clock_at(&crate::registry::now_rfc3339())
}

/// [`clock`] at a given instant. Public so the sites that already have the instant they are
/// working with (a step's `now`, the moment an event was delivered) hand it the same one.
pub fn clock_at(instant: &str) -> Json {
    let mut m = Map::new();
    m.insert(CLOCK_ISO.to_string(), Json::String(instant.to_string()));
    Json::Object(m)
}

/// The scope an ARRIVING event is judged against: a trigger's `filter` and a wait hook's are the
/// same language and must see the same world, so both get it from here rather than each building
/// its own object — that is how one of the two ends up without a clock.
pub fn event_scope(payload: &Map<String, Json>) -> Json {
    let mut m = Map::new();
    m.insert(ROOT_EVENT.to_string(), Json::Object(payload.clone()));
    m.insert(ROOT_NOW.to_string(), clock());
    Json::Object(m)
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

/// **Text a PERSON reads, with its templates filled in** (hub#950).
///
/// Deliberately not [`resolve`]: that one treats a bare `a.b` as a path, which is right for a
/// value and wrong for prose — a title like `Revisar stock.mínimo` would resolve to `null` and
/// come out empty. Here the only thing that substitutes is an explicit `{{…}}`, and everything
/// else is the author's own words.
pub fn render(text: &str, scope: &Json) -> String {
    render_template(text, scope)
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
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                "a flow definition is an object",
            ));
        };

        // Version FIRST: everything below is the grammar of v1, and applying it to a document
        // that says v2 would be reading a language we do not speak.
        let schema_version = match root.get("schema_version") {
            Some(Json::Number(n)) => n.as_i64().unwrap_or(-1),
            Some(_) | None => {
                return Err(invalid(
                    ERR_UNKNOWN_SCHEMA_VERSION,
                    format!(
                        "`schema_version` is required and must be the integer {SCHEMA_VERSION}"
                    ),
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
            if !matches!(
                key.as_str(),
                "schema_version" | "name" | "triggers" | "steps"
            ) {
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
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    "`triggers` must be an array",
                ))
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
                        "step `{}` is of kind `{}`, which this hub cannot execute. Refused at save \
                         time so a flow never stalls forever at 3 AM.",
                        step.id,
                        step.kind.as_str(),
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
            // Both sides of the filter, for the same reason a `condition` step gets both (hub#828):
            // a filter is that same language, and a secret on either side of it is either a read
            // nothing may do or a comparison that silently means its own source text.
            for expr in trigger.filter.expressions() {
                template_paths(&expr, &mut paths);
            }
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

    let allowed: &[&str] = match kind {
        StepKind::Command => &["id", "kind", "command", "params", "on_error"],
        StepKind::Query => &[
            "id", "kind", "query", "params", "result", "limit", "options", "on_error",
        ],
        StepKind::Condition => &["id", "kind", "when"],
        StepKind::Delay => &[
            "id",
            "kind",
            "seconds",
            "until",
            "offset_seconds",
            "max_wait",
            "past_due_policy",
            "cancel_on",
            "reschedule_on",
            "on_error",
        ],
        StepKind::Http => &[
            "id", "kind", "method", "url", "headers", "body", "timeout", "on_error",
        ],
        StepKind::Ai => &[
            "id",
            "kind",
            "prompt",
            "tools",
            "policy",
            "max_iters",
            "on_expire",
            "on_reject",
            "on_error",
            "output",
        ],
        StepKind::Notify => &[
            "id",
            "kind",
            "channel",
            "to",
            "template",
            "vars",
            "interactive",
            "on_error",
        ],
        StepKind::Approval => &[
            "id",
            "kind",
            "title",
            "summary",
            "assignee",
            "expires_in",
            "on_expire",
            "on_reject",
        ],
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

    // **What a FAILURE costs the run** (hub#1635), read where it was typed rather than where it is
    // obeyed. Same closed vocabulary and same fail-closed default as `on_expire`/`on_reject`:
    // absent means [`ErrorPolicy::Stop`] — what a failure has always done — and a value outside the
    // vocabulary is refused at SAVE time naming both, so nobody discovers at 3 AM that the word
    // they wrote (`retry`, the one this kernel will never have) was read as «stop».
    //
    // Only for the kinds that can actually fail: the allow-list above leaves it off `condition`
    // (which stops the run by DESIGN when it does not match, and never fails) and off `approval`
    // (whose own outcomes are `on_reject`/`on_expire`, and whose failures are not the step's).
    let on_error = match map.get("on_error") {
        None | Some(Json::Null) => ErrorPolicy::Stop,
        Some(Json::String(s)) if ErrorPolicy::ALL.iter().any(|p| p.as_str() == s) => {
            ErrorPolicy::parse(s)
        }
        _ => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `on_error` is one of {}",
                    joined(ErrorPolicy::ALL.iter().map(|p| p.as_str()))
                ),
            ))
        }
    };

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
        StepKind::Query => StepSpec::Query(parse_query(&id, map)?),
        StepKind::Condition => StepSpec::Condition {
            when: Condition::parse(map.get("when").unwrap_or(&Json::Null))?,
        },
        StepKind::Delay => StepSpec::Delay(parse_delay(&id, map)?),
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
        StepKind::Notify => StepSpec::Notify(parse_notify(&id, map)?),
        StepKind::Approval => StepSpec::Approval(parse_approval(&id, map)?),
    };

    Ok(StepDef {
        id,
        kind,
        spec,
        on_error,
    })
}

/// The keys of a `delay` step (hub#951).
///
/// Every refusal here is the same rule as the rest of this file — what the kernel cannot execute
/// is refused on the screen where it was typed — but two of them are worth naming:
///
/// - **`seconds` + `offset_seconds` together.** Today `seconds` wins in the executor and the offset
///   is silently dropped, so a document saying «in an hour, minus a day» waits an hour. It is a
///   contradiction, not a precedence question, and it is refused as one.
/// - **The horizon.** There was no ceiling on a wait at all: `until` accepted the year 3000 and
///   the run slept as a `sleeping` row that every retention rule exempts. Only the literal halves
///   can be judged here (`seconds`, `max_wait`); a resolved `until` is judged in the executor,
///   with the same code.
fn parse_delay(id: &str, map: &Map<String, Json>) -> Result<DelayStep> {
    let seconds = match map.get("seconds") {
        None | Some(Json::Null) => None,
        Some(Json::Number(n)) => Some(n.as_i64().ok_or_else(|| {
            invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `seconds` is a whole number of seconds"),
            )
        })?),
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `seconds` is a whole number of seconds"),
            ))
        }
    };
    let until = map
        .get("until")
        .and_then(|v| v.as_str())
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());
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

    let offset_seconds = match map.get("offset_seconds") {
        None | Some(Json::Null) => 0,
        Some(Json::Number(n)) => n.as_i64().ok_or_else(|| {
            invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `offset_seconds` is a whole number of seconds"),
            )
        })?,
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `offset_seconds` is a whole number of seconds"),
            ))
        }
    };
    if offset_seconds != 0 && seconds.is_some() {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "step `{id}`: `offset_seconds` only ever shifts an `until`. With `seconds` it is a \
                 contradiction — «in an hour, minus a day» — and the executor would keep the hour \
                 and drop the day without saying so."
            ),
        ));
    }
    if seconds.is_some_and(|s| s > MAX_DELAY_HORIZON) {
        return Err(horizon_refusal(id, "seconds", seconds.unwrap_or_default()));
    }

    let max_wait = match map.get("max_wait") {
        None | Some(Json::Null) => None,
        Some(Json::Number(n)) => {
            let v = n.as_i64().unwrap_or(-1);
            if v <= 0 {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("step `{id}`: `max_wait` is a whole number of seconds above zero"),
                ));
            }
            if v > MAX_DELAY_HORIZON {
                return Err(horizon_refusal(id, "max_wait", v));
            }
            Some(v)
        }
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `max_wait` is a whole number of seconds"),
            ))
        }
    };

    let past_due = match map.get("past_due_policy") {
        None | Some(Json::Null) => PastDuePolicy::default(),
        Some(Json::String(s)) => PastDuePolicy::parse(s.trim()).ok_or_else(|| {
            invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `past_due_policy` is one of {} (default `{}`: a reminder whose \
                     hour already went by is not sent)",
                    PastDuePolicy::ALL
                        .iter()
                        .map(|p| p.as_str())
                        .collect::<Vec<_>>()
                        .join(", "),
                    PastDuePolicy::default().as_str()
                ),
            )
        })?,
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `past_due_policy` is a name, not a value"),
            ))
        }
    };

    let cancel_on = parse_hooks(id, map.get("cancel_on"), WaitKind::Cancel)?;
    let reschedule_on = parse_hooks(id, map.get("reschedule_on"), WaitKind::Reschedule)?;

    Ok(DelayStep {
        seconds,
        until,
        offset_seconds,
        max_wait,
        past_due,
        cancel_on,
        reschedule_on,
    })
}

fn horizon_refusal(id: &str, key: &str, value: i64) -> RuntimeError {
    invalid(
        ERR_DELAY_HORIZON,
        format!(
            "step `{id}`: `{key}` is {value} s, past the {MAX_DELAY_HORIZON} s (90 day) horizon a \
             single wait may cover. It is refused rather than shortened: a `sleeping` run is \
             exempt from every retention rule the hub has, so a wait nobody meant is a row that \
             outlives the business reason for it."
        ),
    )
}

/// One `cancel_on` / `reschedule_on` list (hub#951).
fn parse_hooks(id: &str, value: Option<&Json>, kind: WaitKind) -> Result<Vec<WaitHook>> {
    let list = kind.as_str();
    let items = match value {
        None | Some(Json::Null) => return Ok(Vec::new()),
        Some(Json::Array(items)) => items,
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `{list}_on` is an array of `{{event, filter?, correlate}}`"),
            ))
        }
    };
    if items.len() > MAX_WAIT_HOOKS {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "step `{id}`: `{list}_on` carries {} hooks, more than the {MAX_WAIT_HOOKS} a wait \
                 may have. They are matched on the hot path of EVERY event delivered in this hub.",
                items.len()
            ),
        ));
    }

    let mut out = Vec::with_capacity(items.len());
    for item in items {
        let Json::Object(hook) = item else {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: every entry of `{list}_on` is an object"),
            ));
        };
        for key in hook.keys() {
            if !matches!(key.as_str(), "event" | "filter" | "correlate" | "until") {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!(
                        "step `{id}`, `{list}_on`: unknown key `{key}`. A hook never arms with a \
                         key the hub does not understand."
                    ),
                ));
            }
        }

        let event = hook
            .get("event")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .trim()
            .to_string();
        if event.is_empty() {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: every entry of `{list}_on` needs the name of an event"),
            ));
        }

        let filter = Condition::parse(hook.get("filter").unwrap_or(&Json::Null))?;
        let correlate = parse_correlate(id, list, hook.get("correlate"))?;

        // The new instant belongs to a `reschedule_on` and to nothing else: required there, and
        // refused on a `cancel_on` where the kernel would never read it. A key nobody reads is
        // hub#521's lesson — `cash_register` shipped a `protects` block the runtime ignored.
        let until = hook
            .get("until")
            .and_then(|v| v.as_str())
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        match (kind, &until) {
            (WaitKind::Reschedule, None) => {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!(
                        "step `{id}`, `reschedule_on` for `{event}`: an `until` path into the \
                         ARRIVING event is required — moving a wait without saying where to is \
                         not moving it anywhere."
                    ),
                ))
            }
            (WaitKind::Cancel, Some(_)) => {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!(
                        "step `{id}`, `cancel_on` for `{event}`: `until` belongs to a \
                         `reschedule_on`. A cancelled wait has no new instant, so the key would be \
                         read by nobody."
                    ),
                ))
            }
            _ => {}
        }
        if let Some(path) = &until {
            if !is_path(path) {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!(
                        "step `{id}`, `reschedule_on` for `{event}`: `until` is a PATH into the \
                         arriving event (`event.<field>`), not `{path}`"
                    ),
                ));
            }
        }

        out.push(WaitHook {
            event,
            filter,
            correlate,
            until,
        });
    }
    Ok(out)
}

/// `{<path in the event>: <path in the run>}` — the frozen path language on both sides.
fn parse_correlate(id: &str, list: &str, value: Option<&Json>) -> Result<BTreeMap<String, String>> {
    let complain = |why: String| invalid(ERR_INVALID_DEFINITION, why);
    let Some(Json::Object(map)) = value else {
        return Err(complain(format!(
            "step `{id}`, `{list}_on`: `correlate` is required — it is what makes the hook about \
             THIS run. Without it the first `cancel` of anything would take out every armed wait \
             in the hub."
        )));
    };
    if map.is_empty() || map.len() > MAX_CORRELATE_PAIRS {
        return Err(complain(format!(
            "step `{id}`, `{list}_on`: `correlate` carries 1 to {MAX_CORRELATE_PAIRS} pairs; it \
             has {}",
            map.len()
        )));
    }

    let mut out = BTreeMap::new();
    for (event_path, run_path) in map {
        let Some(run_path) = run_path.as_str() else {
            return Err(complain(format!(
                "step `{id}`, `{list}_on`: `correlate` maps a path to a PATH, and `{event_path}` \
                 maps to {run_path}"
            )));
        };
        let run_path = run_path.trim();
        // Only paths, both sides, and each on its own side of the seam. A `{{…}}` template on the
        // event side is a correlation key whoever emits the event gets to write; a literal on the
        // run side correlates on a constant, which is the uncorrelated case with extra steps.
        if !event_path.starts_with("event.") || !is_path(event_path) {
            return Err(complain(format!(
                "step `{id}`, `{list}_on`: the left of `correlate` is a path into the ARRIVING \
                 event (`event.<field>`), not `{event_path}`"
            )));
        }
        if !is_path(run_path) || !(run_path.starts_with("input.") || run_path.starts_with("steps."))
        {
            return Err(complain(format!(
                "step `{id}`, `{list}_on`: the right of `correlate` is a path into THIS run \
                 (`input.<field>` or `steps.<id>.<field>`), not `{run_path}`"
            )));
        }
        out.insert(event_path.clone(), run_path.to_string());
    }
    Ok(out)
}

/// The keys of a `query` step (hub#954).
///
/// The refusals here are all the same refusal — that a document never quietly means something
/// smaller than it says. `limit` above the ceiling is refused instead of clamped (`max_iters`'s
/// precedent), and `result: "rows"` is STILL refused instead of accepted-and-ignored, because the
/// mapping language cannot index an array and a step whose output nobody can read is a promise the
/// kernel does not keep. hub#1641 answers what people reach for `rows` FOR — `result: "options"`,
/// where the list travels whole to the one thing that reads a whole list — so the refusal now
/// points at it by name instead of leaving the author with nowhere to go.
fn parse_query(id: &str, map: &Map<String, Json>) -> Result<QueryStep> {
    let query = map
        .get("query")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .trim()
        .to_string();
    if query.is_empty() {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!("step `{id}`: a `query` step needs the name of the read it performs"),
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

    let result = match map.get("result") {
        None | Some(Json::Null) => QueryResult::First,
        Some(Json::String(s)) => QueryResult::parse(s.trim()).ok_or_else(|| {
            invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `result` is one of {} — `rows` is deliberately absent from v1, \
                     because the mapping language cannot index an array and `steps.{id}.rows.0.x` \
                     would resolve to nothing without saying so. To show a list to someone, that \
                     is `options`: it travels whole into the `rows` of a tappable message, so \
                     nobody has to index it",
                    QueryResult::ALL
                        .iter()
                        .map(|r| r.as_str())
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            )
        })?,
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `result` is a name, not a value"),
            ))
        }
    };

    // The ceiling depends on WHERE the rows are going. `options` feeds a tappable list and Meta
    // holds ten of those, so a document asking for two hundred cannot do what it says.
    let ceiling = result.row_ceiling();
    let limit = match map.get("limit") {
        None | Some(Json::Null) => ceiling,
        Some(Json::Number(n)) => match n.as_i64() {
            Some(v) if (1..=ceiling).contains(&v) => v,
            _ => {
                let because = if result == QueryResult::Options {
                    "A read that publishes `options` is capped at what a tappable message can \
                     carry, not at what the tick can read: the send would be refused by the proxy \
                     anyway, and a refusal on the screen where it was typed beats one in a tick \
                     at 3 AM."
                } else {
                    "It is refused above the ceiling rather than cut down to it: the read happens \
                     inside the tick, under the runtime's global lock, and a document that says \
                     more than it reads is how a report comes out wrong with nobody noticing."
                };
                return Err(invalid(
                    ERR_LIMIT_OUT_OF_RANGE,
                    format!(
                        "step `{id}`: `limit` is a whole number of rows between 1 and {ceiling} \
                         for `result: \"{}\"`. {because}",
                        result.as_str()
                    ),
                ));
            }
        },
        Some(_) => {
            return Err(invalid(
                ERR_LIMIT_OUT_OF_RANGE,
                format!("step `{id}`: `limit` is a number of rows"),
            ))
        }
    };

    let options = parse_option_shape(id, map.get("options"), result)?;

    Ok(QueryStep {
        query,
        params,
        result,
        limit,
        options,
    })
}

/// **Which columns of a row become the option she taps** (hub#1641).
///
/// Present exactly when `result` is `options`, and both halves of that «exactly» are refusals the
/// author wants at save time. Declared without the result, the mapping would be dead text nobody
/// reads. Asked for without the mapping, the step would publish whatever columns the module's
/// SELECT happens to have — and a row that is not `{id, title}` is refused by the proxy at send
/// time, in a background tick, with the customer already waiting.
fn parse_option_shape(
    id: &str,
    raw: Option<&Json>,
    result: QueryResult,
) -> Result<Option<OptionShape>> {
    let map = match raw {
        None | Some(Json::Null) => {
            if result == QueryResult::Options {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!(
                        "step `{id}`: `result: \"options\"` needs an `options` block saying which \
                         columns make up each row — `id` (what comes back when she taps it) and \
                         `title` (what she reads), plus an optional `description`. Table columns \
                         are not something a message can send."
                    ),
                ));
            }
            return Ok(None);
        }
        Some(Json::Object(m)) => m,
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `options` is an object of column names"),
            ))
        }
    };

    if result != QueryResult::Options {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "step `{id}`: `options` shapes the rows of `result: \"options\"`, and this step \
                 says `result: \"{}\"`. A mapping nothing reads is a promise the kernel does not \
                 keep.",
                result.as_str()
            ),
        ));
    }

    for key in map.keys() {
        if !["id", "title", "description"].contains(&key.as_str()) {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `options` takes `id`, `title` and `description` — the three a \
                     tappable row has — and `{key}` is not one of them."
                ),
            ));
        }
    }

    // A column NAME — not a path and not a template. Both would be looked up verbatim and fail at
    // RUN time naming a column nobody wrote, which is a worse place to learn it than here. And the
    // answer to «I want the title to say two things» is the same one `resolve_path` gives to «the
    // third line of the ticket»: that shape belongs in the query.
    let column = |key: &str| -> Result<Option<String>> {
        let refuse = || {
            Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `options.{key}` is the NAME of one column of the read, not a \
                     value, not a path and not a `{{{{…}}}}` template. Composing one out of two \
                     columns is a shape that belongs in the query."
                ),
            ))
        };
        match map.get(key) {
            None | Some(Json::Null) => Ok(None),
            Some(Json::String(s)) => {
                let name = s.trim();
                if name.is_empty() || name.contains("{{") || name.contains('.') {
                    return refuse();
                }
                Ok(Some(name.to_string()))
            }
            Some(_) => refuse(),
        }
    };

    let (id_col, title_col, description) =
        (column("id")?, column("title")?, column("description")?);
    let (Some(id_col), Some(title_col)) = (id_col, title_col) else {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "step `{id}`: every option needs an `id` (what comes back as `event.reply_id` \
                 when she taps it) and a `title` (what she reads). `description` is the optional \
                 second line."
            ),
        ));
    };

    Ok(Some(OptionShape {
        id: id_col,
        title: title_col,
        description,
    }))
}

/// The keys of a `notify` step (hub#821).
///
/// The one that matters is `to`: it is an OBJECT of `{query, params, field}` and nothing else. A
/// string there — a literal address, or `"{{input.email}}"` — is refused, and that refusal is the
/// feature. It is what makes «a flow never messages an address out of the event payload» a
/// property of the grammar instead of a rule somebody has to remember.
fn parse_notify(id: &str, map: &Map<String, Json>) -> Result<NotifyStep> {
    let channel_text = map
        .get("channel")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .trim();
    let channel = Channel::parse(channel_text)
        .filter(|c| c.is_deliverable())
        .ok_or_else(|| {
            invalid(
                ERR_INVALID_DEFINITION,
                format!(
                "step `{id}`: `channel` is one of {} (`sms` is in ADR-0012's vocabulary and this \
                 hub has no transport for it, so a step naming it would only ever dead-letter)",
                Channel::DELIVERABLE
                    .iter()
                    .map(|c| c.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            )
        })?;

    let Some(Json::Object(to)) = map.get("to") else {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!(
                "step `{id}`: `to` is `{{query, params, field}}` — a recipient is one field of one \
                 granted read, never an address. A flow that could write one down could mail \
                 whatever the event carried."
            ),
        ));
    };
    for key in to.keys() {
        if !matches!(key.as_str(), "query" | "params" | "field") {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: unknown key `{key}` in `to`"),
            ));
        }
    }
    let text = |key: &str| {
        to.get(key)
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .trim()
            .to_string()
    };
    let query = text("query");
    let field = text("field");
    if query.is_empty() || field.is_empty() {
        return Err(invalid(
            ERR_INVALID_DEFINITION,
            format!("step `{id}`: `to` needs the `query` to read and the `field` to take from it"),
        ));
    }

    let object = |key: &str, what: &str| match map.get(key) {
        Some(Json::Object(m)) => Ok(m.clone()),
        None | Some(Json::Null) => Ok(Map::new()),
        Some(_) => Err(invalid(
            ERR_INVALID_DEFINITION,
            format!("step `{id}`: `{what}` is an object of mappings"),
        )),
    };
    let params = match to.get("params") {
        Some(Json::Object(m)) => m.clone(),
        None | Some(Json::Null) => Map::new(),
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `to.params` is an object of mappings"),
            ))
        }
    };
    let vars = object("vars", "vars")?;
    let template_name = map
        .get("template")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .trim()
        .to_string();

    // **Options the customer TAPS** (hub#1633). Meta's own object, carried to the proxy unchanged:
    // the SaaS checks it against Meta's limits before a paid call leaves the building
    // (`too_many_options`, `duplicate_option_id`…), so what belongs here is only what the hub can
    // answer for — the channel it is sent on, and that it is not competing with other copy.
    let interactive = match map.get("interactive") {
        None | Some(Json::Null) => None,
        Some(Json::Object(m)) => Some(m.clone()),
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `interactive` is an object of Meta's own shape \
                     (`{{type, body, action}}`), not a bare value"
                ),
            ))
        }
    };
    if interactive.is_some() {
        if channel != Channel::Whatsapp {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `interactive` is a whatsapp shape — an email has nothing to tap, \
                     so options on `{}` would be dropped on the way out",
                    channel.as_str()
                ),
            ));
        }
        // Meta's message has ONE type, and the proxy answers a request with two by name
        // (`conflicting_message_type`). Refusing here says it where it was typed instead of eight
        // retries later, and resolving it by precedence would send a message nobody wrote.
        let competing = if !template_name.is_empty() {
            Some("template")
        } else if vars.contains_key("text") {
            Some("vars.text")
        } else if vars.contains_key("body") {
            Some("vars.body")
        } else {
            None
        };
        if let Some(other) = competing {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `interactive` and `{other}` are two messages and one send. The \
                     copy of a tappable message lives in `interactive.body.text`; keeping both \
                     would silently drop one of them"
                ),
            ));
        }
    }

    Ok(NotifyStep {
        interactive,
        channel,
        query,
        params,
        field,
        template: template_name,
        vars,
    })
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

    // **What a silence costs, said by the step that proposes** (hub#1634). The sister of
    // `on_reject` below, and parsed the same way: absent means [`ExpiryPolicy::Reject`], which is
    // what an unanswered proposal has always done, and an unrecognised value is refused where it
    // was typed rather than read as one of the three.
    let on_expire = match map.get("on_expire") {
        None | Some(Json::Null) => ExpiryPolicy::Reject,
        Some(Json::String(s)) if ExpiryPolicy::ALL.iter().any(|p| p.as_str() == s) => {
            ExpiryPolicy::parse(s)
        }
        _ => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `on_expire` is one of {}",
                    joined(ExpiryPolicy::ALL.iter().map(|p| p.as_str()))
                ),
            ))
        }
    };

    // **What a refusal costs, said by the step that proposes** (hub#1622). Same closed vocabulary
    // and same default as the `approval` step's: absent means [`RejectPolicy::Cancel`], which is
    // what a rejection has always done, and an unrecognised value is refused where it was typed
    // rather than read as either half of the choice.
    let on_reject = match map.get("on_reject") {
        None | Some(Json::Null) => RejectPolicy::Cancel,
        Some(Json::String(s)) if RejectPolicy::ALL.iter().any(|p| p.as_str() == s) => {
            RejectPolicy::parse(s)
        }
        _ => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `on_reject` is one of {}",
                    joined(RejectPolicy::ALL.iter().map(|p| p.as_str()))
                ),
            ))
        }
    };

    let output = parse_ai_output(id, map.get("output"))?;

    Ok(AiStep {
        prompt,
        queries,
        commands,
        policy,
        max_iters,
        on_expire,
        on_reject,
        output,
    })
}

/// **What the turn promises to leave behind** (hub#1639), in declaration order.
///
/// Absent is the default and means «what an `ai` step has always published»: every flow already in
/// production is written against `{text, tool_calls}` and must keep resolving the same way.
///
/// Everything here is refused at SAVE time rather than discovered at 3 AM. The whole reason a
/// document declares its output instead of the runner guessing it is that a mapping which resolves
/// to nothing does so *silently* — the same failure that kept `rows` out of v1.
fn parse_ai_output(id: &str, raw: Option<&Json>) -> Result<Vec<AiOutputField>> {
    let fields = match raw {
        None | Some(Json::Null) => return Ok(Vec::new()),
        Some(Json::Object(m)) => m,
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `output` is `{{<name>: {{type, describe}}}}` — the fields this \
                     turn leaves behind, each with words saying what goes in it"
                ),
            ))
        }
    };

    let mut parsed = Vec::with_capacity(fields.len());
    for (name, spec) in fields {
        // The turn's own two keys. `{{steps.<id>.text}}` means «the sentence the model wrote» in
        // every flow already written; letting a document take that name would change what an
        // existing mapping resolves to without anybody touching the mapping.
        if matches!(name.as_str(), "text" | "tool_calls") {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `output.{name}` is what the turn itself publishes, so it is not \
                     the document's to redefine. Give the field another name."
                ),
            ));
        }
        // `steps.<id>.<name>` is walked by `resolve_path`, which splits on `.`: a dotted or spaced
        // name would address a level that is not there and resolve to null with no complaint.
        if !is_addressable_name(name) {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `output` field `{name}` cannot be addressed by the mapping \
                     language. A name is a letter followed by letters, digits or `_` — anything \
                     else makes `steps.{id}.{name}` resolve to nothing without saying so."
                ),
            ));
        }

        let Json::Object(spec) = spec else {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `output.{name}` is `{{type, describe}}`"),
            ));
        };
        for key in spec.keys() {
            if !matches!(key.as_str(), "type" | "describe") {
                return Err(invalid(
                    ERR_INVALID_DEFINITION,
                    format!("step `{id}`: unknown key `{key}` in `output.{name}`"),
                ));
            }
        }

        let kind = match spec.get("type") {
            Some(Json::String(s)) => AiOutputKind::parse(s),
            _ => None,
        }
        .ok_or_else(|| {
            invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `output.{name}.type` is one of {}",
                    joined(AiOutputKind::ALL.iter().map(|k| k.as_str()))
                ),
            )
        })?;

        // The description is the ONLY thing the model is told about the field. Empty means a field
        // filled with whatever it likes, which is precisely the silent wrong answer this
        // vocabulary exists to prevent — so it is required, not defaulted to the field name.
        let describe = spec
            .get("describe")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .trim()
            .to_string();
        if describe.is_empty() {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `output.{name}` needs `describe` — words telling the model what \
                     goes in this field. It is the only thing it reads about it."
                ),
            ));
        }

        parsed.push(AiOutputField {
            name: name.clone(),
            kind,
            describe,
        });
    }
    Ok(parsed)
}

/// Can `resolve_path` reach `steps.<id>.<name>`? A letter, then letters, digits or `_`.
fn is_addressable_name(name: &str) -> bool {
    let mut chars = name.chars();
    chars.next().is_some_and(|c| c.is_ascii_alphabetic())
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// The keys of an `approval` step (hub#950).
///
/// Three refusals, and each one is about a document never quietly meaning something other than it
/// says: a question with no title, an assignee that names a PERSON, and a wait longer than this
/// kernel will park for. The two policies are closed vocabularies for the same reason `policy` is
/// on the `ai` step — `"cancle"` silently becoming `continue` would carry a run past a refusal.
fn parse_approval(id: &str, map: &Map<String, Json>) -> Result<ApprovalStep> {
    let title = match map.get("title") {
        Some(Json::String(s)) if !s.trim().is_empty() => s.clone(),
        _ => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: an `approval` step needs a `title` — that string IS the \
                     question, and a tray that showed an opaque id would be a button people press \
                     without reading"
                ),
            ))
        }
    };
    let summary = match map.get("summary") {
        None | Some(Json::Null) => String::new(),
        Some(Json::String(s)) => s.clone(),
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `summary` is a string"),
            ))
        }
    };

    // **A role, and there is deliberately no shape in which a person can be named.** Same refusal
    // as a `notify` recipient (hub#821) and for the same kind of reason: the absence IS the
    // guarantee. A document that could say `{"user": "hub_user:7"}` would be a flow that stops
    // working the day that person leaves — and the marketplace template that shipped with it would
    // name somebody else's employee.
    let assignee_role = match map.get("assignee") {
        None | Some(Json::Null) => String::new(),
        Some(Json::Object(a)) => {
            for key in a.keys() {
                if key != "role" {
                    return Err(invalid(
                        ERR_INVALID_DEFINITION,
                        format!(
                            "step `{id}`: unknown key `{key}` in `assignee`. An approval names a \
                             ROLE, never a person: somebody named in a document is gone the day \
                             they leave."
                        ),
                    ));
                }
            }
            match a.get("role") {
                Some(Json::String(s)) if !s.trim().is_empty() => s.trim().to_string(),
                _ => {
                    return Err(invalid(
                        ERR_INVALID_DEFINITION,
                        format!("step `{id}`: `assignee` is `{{\"role\": \"<rol>\"}}`"),
                    ))
                }
            }
        }
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!("step `{id}`: `assignee` is `{{\"role\": \"<rol>\"}}`, not a name"),
            ))
        }
    };

    let expires_in_seconds = match map.get("expires_in") {
        None | Some(Json::Null) => DEFAULT_APPROVAL_TTL_SECONDS,
        Some(v) => v.as_i64().unwrap_or(-1),
    };
    if !(1..=MAX_APPROVAL_TTL_SECONDS).contains(&expires_in_seconds) {
        return Err(invalid(
            ERR_LIMIT_OUT_OF_RANGE,
            format!(
                "step `{id}`: `expires_in` must be between 1 second and \
                 {MAX_APPROVAL_TTL_SECONDS} (30 days), got {expires_in_seconds}. Refused rather \
                 than clamped, like `limit` and `max_iters`: a run parked for longer is a standing \
                 authorisation nobody remembers giving, and while it waits it is exempt from the \
                 90-day prune."
            ),
        ));
    }

    let on_expire = match map.get("on_expire") {
        None | Some(Json::Null) => ExpiryPolicy::Reject,
        Some(Json::String(s)) if ExpiryPolicy::ALL.iter().any(|p| p.as_str() == s) => {
            ExpiryPolicy::parse(s)
        }
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `on_expire` is one of {}",
                    joined(ExpiryPolicy::ALL.iter().map(|p| p.as_str()))
                ),
            ))
        }
    };
    let on_reject = match map.get("on_reject") {
        None | Some(Json::Null) => RejectPolicy::Cancel,
        Some(Json::String(s)) if RejectPolicy::ALL.iter().any(|p| p.as_str() == s) => {
            RejectPolicy::parse(s)
        }
        Some(_) => {
            return Err(invalid(
                ERR_INVALID_DEFINITION,
                format!(
                    "step `{id}`: `on_reject` is one of {}",
                    joined(RejectPolicy::ALL.iter().map(|p| p.as_str()))
                ),
            ))
        }
    };

    Ok(ApprovalStep {
        title,
        summary,
        assignee_role,
        expires_in_seconds,
        on_expire,
        on_reject,
    })
}

fn joined<'a>(values: impl Iterator<Item = &'a str>) -> String {
    values.collect::<Vec<_>>().join(", ")
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

    /// The list emptied one issue at a time — `http` with hub#662, `ai` with hub#665, `notify` with
    /// hub#821 — and now there is nothing left in it. Every kind is parsed STRICTLY, so an empty
    /// step of any of them is refused for its OWN missing key and never as "not implemented".
    #[test]
    fn every_step_kind_runs_now_and_an_empty_one_is_refused_for_its_own_reason() {
        for (kind, complaint) in [("http", "url"), ("ai", "prompt"), ("notify", "channel")] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{ "id": "call", "kind": kind }]
            }))
            .expect_err("an empty step of any kind is invalid, but for its OWN reason");
            let text = format!("{err}");
            assert!(
                text.contains(complaint) && !text.contains("cannot execute"),
                "`{kind}` must be refused for its own missing key, not as unavailable: {text}"
            );
        }
        assert!(StepKind::ALL.iter().all(|k| k.is_available()));
    }

    // ── the `notify` step (hub#821) ───────────────────────────────────────────────────────────

    #[test]
    fn a_notify_step_carries_its_channel_its_recipient_read_and_its_copy() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "remind", "kind": "notify", "channel": "whatsapp",
                "to": {
                    "query": "crm.customer.get",
                    "params": { "id": "input.customer_id" },
                    "field": "phone"
                },
                "template": "appointment_reminder",
                "vars": { "text": "Te esperamos el {{input.when}}" }
            }]
        }))
        .expect("the shape the appointment reminder is written in");
        let StepSpec::Notify(step) = &def.steps[0].spec else {
            panic!("a notify step parses as one");
        };
        assert_eq!(step.channel, Channel::Whatsapp);
        assert_eq!(step.query, "crm.customer.get");
        assert_eq!(step.field, "phone");
        assert_eq!(step.template, "appointment_reminder");
        assert_eq!(step.params.len(), 1);
        assert_eq!(step.vars.len(), 1);
    }

    /// **The refusal that IS the feature.** There is no shape in which an author — or a template
    /// installed from the marketplace — can write an address down, so there is no path by which one
    /// out of the event payload becomes a recipient. `to` is a read and a column, or it does not
    /// save.
    #[test]
    fn a_notify_step_cannot_name_a_recipient_by_hand() {
        for to in [
            json!("cliente@ejemplo.com"),
            json!("{{input.email}}"),
            json!("input.email"),
            json!(["cliente@ejemplo.com"]),
            json!({ "address": "cliente@ejemplo.com" }),
            json!({ "query": "crm.customer.get", "field": "phone", "address": "x@y.z" }),
            json!({ "query": "crm.customer.get" }),
            json!({ "field": "phone" }),
        ] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{ "id": "r", "kind": "notify", "channel": "email", "to": to }]
            }))
            .expect_err("a recipient is one field of one granted read, never an address");
            assert!(
                format!("{err}").contains("to") || format!("{err}").contains("query"),
                "{err}"
            );
        }
    }

    /// A channel with no transport is refused where it was typed. `sms` is in ADR-0012's
    /// vocabulary and nothing can send it, so a step naming it would only ever dead-letter.
    #[test]
    fn a_notify_step_on_a_channel_with_no_transport_is_refused_at_save_time() {
        for channel in ["sms", "pigeon", ""] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "r", "kind": "notify", "channel": channel,
                    "to": { "query": "q.x", "field": "phone" }
                }]
            }))
            .expect_err("this hub cannot send on that channel");
            assert!(format!("{err}").contains("channel"), "{err}");
        }
    }

    /// A `secret.…` in a message or in the params of the recipient read is refused like anywhere
    /// else outside an `http` step: interpolated into the copy it would be SENT to a customer.
    #[test]
    fn a_notify_step_cannot_read_a_flow_secret() {
        for step in [
            json!({
                "id": "r", "kind": "notify", "channel": "email",
                "to": { "query": "q.x", "field": "email" },
                "vars": { "text": "clave {{secret.API_KEY}}" }
            }),
            json!({
                "id": "r", "kind": "notify", "channel": "email",
                "to": { "query": "q.x", "params": { "k": "secret.API_KEY" }, "field": "email" }
            }),
        ] {
            let err = FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [step] }))
                .expect_err("a credential must never be interpolated into a message");
            assert!(format!("{err}").contains("API_KEY"), "{err}");
        }
    }

    /// **Options the customer TAPS instead of a number they retype** (hub#1633).
    ///
    /// The step carries Meta's own `interactive` object and it is mapped against the run like the
    /// rest of the copy, so the slots a previous step read become the rows of the list.
    #[test]
    fn a_notify_step_can_offer_options_to_tap_and_maps_them_against_the_run() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "crm.customer.get", "field": "phone" },
                "interactive": {
                    "type": "button",
                    "body": { "text": "¿Confirmas la cita del {{input.when}}?" },
                    "action": { "buttons": [
                        { "type": "reply", "reply": { "id": "confirm", "title": "Sí" } },
                        { "type": "reply", "reply": { "id": "cancel", "title": "No" } }
                    ] }
                }
            }]
        }))
        .expect("the shape the appointment confirmation is written in");
        let StepSpec::Notify(step) = &def.steps[0].spec else {
            panic!("a notify step parses as one");
        };
        let interactive = step.interactive.as_ref().expect("the options travel with the step");
        assert_eq!(interactive["type"], json!("button"));

        // Mapped like `vars`: the templates inside resolve against the run, however deep they sit.
        let scope = json!({ "input": { "when": "martes a las 10:30" } });
        let resolved = resolve(&Json::Object(interactive.clone()), &scope);
        assert_eq!(
            resolved["body"]["text"],
            json!("¿Confirmas la cita del martes a las 10:30?")
        );
        assert_eq!(resolved["action"]["buttons"][0]["reply"]["id"], json!("confirm"));
    }

    /// A tappable option is a WhatsApp shape. Email has no buttons, so a step asking for them on
    /// that channel is refused where it was typed — the same criterion `sms` gets.
    #[test]
    fn options_to_tap_are_refused_on_a_channel_that_has_none() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask", "kind": "notify", "channel": "email",
                "to": { "query": "q.x", "field": "email" },
                "interactive": { "type": "button", "body": { "text": "¿Sí o no?" } }
            }]
        }))
        .expect_err("email has no tappable options");
        let text = format!("{err}");
        // Refused for having no buttons, NOT for being a key the step vocabulary never heard of:
        // the second reason would make this test pass before the feature existed.
        assert!(text.contains("interactive") && text.contains("whatsapp"), "{text}");
        assert!(!text.contains("unknown key"), "{text}");
    }

    /// Meta's message has ONE type. Asking for two is named rather than resolved by precedence:
    /// picking one silently would send a message nobody wrote — the SaaS answers the same request
    /// with `conflicting_message_type`, and finding out at save time is cheaper than at send time.
    #[test]
    fn options_to_tap_next_to_other_copy_are_refused_instead_of_one_being_dropped() {
        for extra in [
            json!({ "template": "appointment_reminder" }),
            json!({ "vars": { "text": "Te esperamos" } }),
            json!({ "vars": { "body": "Te esperamos" } }),
        ] {
            let mut step = json!({
                "id": "ask", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "q.x", "field": "phone" },
                "interactive": { "type": "button", "body": { "text": "¿Sí o no?" } }
            });
            for (k, v) in extra.as_object().unwrap() {
                step[k] = v.clone();
            }
            let err = FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [step] }))
                .expect_err("one message carries one kind of content");
            let text = format!("{err}");
            assert!(text.contains("interactive"), "{text}");
            assert!(!text.contains("unknown key"), "{text}");
        }

        // …and what is NOT copy still travels next to the options: `phone_number_id` picks which
        // of this hub's numbers sends, and it is not something the customer ever reads.
        FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "q.x", "field": "phone" },
                "vars": { "phone_number_id": "123" },
                "interactive": { "type": "button", "body": { "text": "¿Sí o no?" } }
            }]
        }))
        .expect("a transport hint is not copy");
    }

    /// The `secret.…` refusal of hub#662 reaches INSIDE the options for the same reason it reaches
    /// `vars`: a credential interpolated into a button's title would be printed on a customer's
    /// phone. Scanning only the top level would let one hide two objects deep.
    #[test]
    fn a_notify_step_cannot_read_a_flow_secret_from_inside_its_options() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "ask", "kind": "notify", "channel": "whatsapp",
                "to": { "query": "q.x", "field": "phone" },
                "interactive": {
                    "type": "button",
                    "body": { "text": "Confirma" },
                    "action": { "buttons": [
                        { "type": "reply", "reply": { "id": "ok", "title": "{{secret.API_KEY}}" } }
                    ] }
                }
            }]
        }))
        .expect_err("a credential must never be interpolated into a message");
        assert!(format!("{err}").contains("API_KEY"), "{err}");
    }

    /// `interactive` is an object of Meta's own shape. A string or a list is a typo that would
    /// otherwise reach the proxy and come back as an opaque refusal.
    #[test]
    fn options_to_tap_have_to_be_an_object() {
        for bad in [json!("button"), json!(["confirm"]), json!(3)] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "ask", "kind": "notify", "channel": "whatsapp",
                    "to": { "query": "q.x", "field": "phone" },
                    "interactive": bad
                }]
            }))
            .expect_err("the options are an object");
            let text = format!("{err}");
            assert!(text.contains("interactive") && text.contains("object"), "{text}");
            assert!(!text.contains("unknown key"), "{text}");
        }
    }

    // ── the `approval` step (hub#950) ─────────────────────────────────────────────────────────

    /// The eighth kind, and the shape the market converged on: the **object** of Power Automate's
    /// *Start and wait for an approval* (a question with a title, a summary and an assignee) plus
    /// the **explicit due date** of Business Central, which is the half Power Automate does badly.
    #[test]
    fn an_approval_step_carries_its_question_its_assignee_and_its_two_outcome_policies() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "approve", "kind": "approval",
                "title": "Aprobar compra a {{steps.po.supplier_name}}",
                "summary": "Importe {{input.total}} €",
                "assignee": { "role": "owner" },
                "expires_in": 86400,
                "on_expire": "continue",
                "on_reject": "continue"
            }]
        }))
        .expect("the shape the purchase approval is written in");
        let StepSpec::Approval(step) = &def.steps[0].spec else {
            panic!("an approval step parses as one");
        };
        assert_eq!(step.title, "Aprobar compra a {{steps.po.supplier_name}}");
        assert_eq!(step.summary, "Importe {{input.total}} €");
        assert_eq!(step.assignee_role, "owner");
        assert_eq!(step.expires_in_seconds, 86400);
        assert_eq!(step.on_expire, ExpiryPolicy::Continue);
        assert_eq!(step.on_reject, RejectPolicy::Continue);
    }

    /// The defaults are the conservative ones, and each is a decision. 72 h because a fixed
    /// deadline dies over a long weekend and 30 days is Power Automate's own ceiling; `reject` and
    /// `cancel` because the steps written after an approval assumed it was granted.
    #[test]
    fn an_approval_defaults_to_seventy_two_hours_and_to_not_carrying_on() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "approve", "kind": "approval", "title": "¿Seguimos?" }]
        }))
        .unwrap();
        let StepSpec::Approval(step) = &def.steps[0].spec else {
            panic!("an approval step parses as one");
        };
        assert_eq!(step.expires_in_seconds, DEFAULT_APPROVAL_TTL_SECONDS);
        assert_eq!(step.expires_in_seconds, 72 * 3600);
        assert_eq!(step.on_expire, ExpiryPolicy::Reject);
        assert_eq!(step.on_reject, RejectPolicy::Cancel);
        assert_eq!(
            step.assignee_role, "",
            "no role named means the hub's own admin gate, which is what decides approvals today"
        );
        assert_eq!(step.summary, "");
    }

    /// Refused, not clamped — the precedent of `max_iters` and `limit`. A run parked for longer
    /// than a month is a standing authorisation nobody remembers giving, and a document that says
    /// a year while the hub silently means thirty days is lying to whoever wrote it.
    #[test]
    fn a_wait_longer_than_a_month_is_refused_at_save_time_instead_of_being_clamped() {
        for expires_in in [MAX_APPROVAL_TTL_SECONDS + 1, 0, -1, 365 * 24 * 3600] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "approve", "kind": "approval", "title": "¿Seguimos?",
                    "expires_in": expires_in
                }]
            }))
            .expect_err("`expires_in` {expires_in} is outside what this kernel will park for");
            assert!(
                matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_LIMIT_OUT_OF_RANGE),
                "{err}"
            );
        }
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "approve", "kind": "approval", "title": "¿Seguimos?",
                "expires_in": MAX_APPROVAL_TTL_SECONDS
            }]
        }))
        .is_ok());
    }

    /// A question nobody can read is not a question. The title is what a person decides against at
    /// 9 AM, so a step without one does not save.
    #[test]
    fn an_approval_step_without_a_question_is_refused() {
        for title in [json!(""), json!("   "), json!(null), json!(7)] {
            assert!(
                FlowDefinition::parse(&json!({
                    "schema_version": 1,
                    "steps": [{ "id": "approve", "kind": "approval", "title": title }]
                }))
                .is_err(),
                "a title of {title} is not something a person can decide against"
            );
        }
    }

    /// **A role, never a person.** Naming somebody in a document breaks the day they leave — the
    /// hole Business Central had to invent a "substitute" for — and Odoo's `Allowed Group` is what
    /// the market settled on instead. There is no shape in which a user id can be written down.
    #[test]
    fn an_approval_is_assigned_to_a_role_and_there_is_no_way_to_name_a_person() {
        for assignee in [
            json!("owner"),
            json!({ "user": "hub_user:7" }),
            json!({ "role": "owner", "user": "hub_user:7" }),
            json!({ "role": 7 }),
            json!(["owner"]),
        ] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "approve", "kind": "approval", "title": "¿Seguimos?",
                    "assignee": assignee
                }]
            }))
            .expect_err("an assignee is `{role: …}` and nothing else");
            assert!(format!("{err}").contains("assignee"), "{err}");
        }
    }

    /// Both policies are closed vocabularies, refused rather than defaulted: `"cancle"` quietly
    /// becoming `cancel` would be merciful and `"cancle"` quietly becoming `continue` would carry
    /// a run past a refusal. Neither is acceptable, so it does not save.
    #[test]
    fn the_outcome_policies_are_closed_vocabularies_and_a_typo_does_not_save() {
        for (key, value) in [
            ("on_expire", "rejct"),
            ("on_expire", "carry_on"),
            ("on_reject", "cancle"),
            ("on_reject", "reject"),
        ] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "approve", "kind": "approval", "title": "¿Seguimos?", key: value
                }]
            }))
            .expect_err("a policy this kernel cannot obey is refused where it was typed");
            assert!(format!("{err}").contains(key), "{err}");
        }
    }

    /// hub#521's lesson, applied to the newest kind: a key the runtime does not read is refused
    /// instead of dropped. `command` and `payload` are the tempting ones — this step deliberately
    /// executes NOTHING, and accepting them would read like a promise it does not keep.
    #[test]
    fn an_approval_step_refuses_a_key_it_does_not_understand() {
        for key in ["command", "payload", "params", "assignee_role", "prompt"] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "approve", "kind": "approval", "title": "¿Seguimos?",
                    key: json!("x")
                }]
            }))
            .expect_err("a flow never runs with a key the hub does not understand");
            assert!(format!("{err}").contains(key), "{err}");
        }
    }

    /// The title and the summary are mapping expressions like any other, so the `secret.…` refusal
    /// has to reach them: a credential interpolated there would be printed in the tray, which is
    /// the one screen the whole hub is invited to read.
    #[test]
    fn a_secret_cannot_be_interpolated_into_the_question_a_person_reads() {
        for step in [
            json!({ "id": "a", "kind": "approval", "title": "clave {{secret.API_KEY}}" }),
            json!({
                "id": "a", "kind": "approval", "title": "¿Seguimos?",
                "summary": "clave {{secret.API_KEY}}"
            }),
        ] {
            let err = FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [step] }))
                .expect_err("a credential must never be interpolated into the tray");
            assert!(
                matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_SECRET_NOT_AVAILABLE),
                "{err}"
            );
        }
    }

    /// It parks the run rather than crossing the claim → I/O → complete seam: there is no call to
    /// make outside the lock, only a row to write and a run to stop.
    #[test]
    fn an_approval_does_no_io_of_its_own() {
        assert!(!StepKind::Approval.needs_io());
        assert!(StepKind::Approval.is_available());
        assert_eq!(StepKind::parse("approval"), Some(StepKind::Approval));
    }

    // ── the `delay` step, extended (hub#951) ──────────────────────────────────────────────────
    //
    // The decision is the market's (published on hub#951, 2026-08-15): Salesforce's **Scheduled
    // Paths** (a date field of the record plus an offset), NetSuite SuiteFlow's **state with
    // several exits** (the wait is a state; the scheduled exit and the event exits race and the
    // first atomic transition takes the record out) and Klaviyo's **re-check before acting**. What
    // is refused here is refused at SAVE time for the reason the whole of this file is: everything
    // this kernel cannot execute is refused on the screen where it was typed, never at 3 AM.

    fn delay_of(step: Json) -> Result<DelayStep> {
        FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [step] })).map(|d| {
            let StepSpec::Delay(delay) = d.steps[0].spec.clone() else {
                panic!("a delay step parses as one");
            };
            delay
        })
    }

    #[test]
    fn a_bare_delay_keeps_meaning_exactly_what_it_meant_before() {
        // The extension is additive. Everything already stored has to keep parsing to the same
        // behaviour, and the defaults are what says so.
        let delay = delay_of(json!({ "id": "w", "kind": "delay", "seconds": 3600 })).unwrap();
        assert_eq!(delay.seconds, Some(3600));
        assert_eq!(delay.offset_seconds, 0);
        assert_eq!(delay.max_wait, None);
        assert_eq!(delay.horizon_seconds(), MAX_DELAY_HORIZON);
        assert_eq!(
            delay.past_due,
            PastDuePolicy::Skip,
            "the default is the restrictive one"
        );
        assert!(delay.cancel_on.is_empty() && delay.reschedule_on.is_empty());
    }

    /// **An instant of the event, shifted** — Salesforce's `Time Source` + `Offset`. In SECONDS and
    /// not «1 month»: a calendar offset is an operation the frozen mapping language does not have.
    #[test]
    fn an_until_can_be_shifted_by_an_offset_in_seconds() {
        let delay = delay_of(json!({
            "id": "w", "kind": "delay",
            "until": "input.appointment_at", "offset_seconds": -86400
        }))
        .expect("«24 h before the appointment» is the whole point of the step");
        assert_eq!(delay.until.as_deref(), Some("input.appointment_at"));
        assert_eq!(delay.offset_seconds, -86400);
    }

    /// `seconds` + `offset_seconds` is refused instead of one of them quietly winning. Today
    /// `seconds` wins in the executor and the offset is dropped — a document that says «in an hour,
    /// minus a day» and waits an hour.
    #[test]
    fn seconds_and_an_offset_together_are_refused_rather_than_one_of_them_winning() {
        let err = delay_of(json!({
            "id": "w", "kind": "delay", "seconds": 3600, "offset_seconds": -86400
        }))
        .expect_err("an offset only ever shifts an `until`");
        assert!(format!("{err}").contains("offset_seconds"), "{err}");
    }

    /// **There was no ceiling at all**: `until` accepted the year 3000, and the run slept forever
    /// as a row exempt from every retention rule. 90 days is Shopify Flow's number, the most
    /// generous of the ten references studied.
    #[test]
    fn a_wait_longer_than_the_horizon_is_refused_at_save_time() {
        for step in [
            json!({ "id": "w", "kind": "delay", "until": "input.at",
                    "max_wait": MAX_DELAY_HORIZON + 1 }),
            json!({ "id": "w", "kind": "delay", "seconds": MAX_DELAY_HORIZON + 1 }),
        ] {
            let err = delay_of(step).expect_err("a wait past the horizon never saves");
            assert!(
                matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_DELAY_HORIZON),
                "{err:?}"
            );
        }
        // And the horizon itself still saves: refused ABOVE, not at.
        assert!(
            delay_of(json!({ "id": "w", "kind": "delay", "seconds": MAX_DELAY_HORIZON })).is_ok()
        );
    }

    #[test]
    fn the_three_past_due_policies_are_the_only_ones_and_an_unknown_one_is_refused() {
        for (text, policy) in [
            ("continue_now", PastDuePolicy::ContinueNow),
            ("skip", PastDuePolicy::Skip),
            ("fail", PastDuePolicy::Fail),
        ] {
            let delay = delay_of(json!({
                "id": "w", "kind": "delay", "until": "input.when", "past_due_policy": text
            }))
            .unwrap();
            assert_eq!(delay.past_due, policy);
        }
        assert!(delay_of(json!({
            "id": "w", "kind": "delay", "until": "input.when", "past_due_policy": "run_anyway"
        }))
        .is_err());
    }

    /// The two exits of the state. `correlate` is a map `{<path in the event>: <path in the run>}`
    /// in the frozen language — PATHS and nothing else, because a template resolved against an
    /// arriving event is a correlation key an attacker writes.
    #[test]
    fn a_delay_carries_the_events_that_cancel_it_and_the_events_that_move_it() {
        let delay = delay_of(json!({
            "id": "w", "kind": "delay",
            "until": "input.appointment_at", "offset_seconds": -86400,
            "cancel_on": [{
                "event": "appointment.cancelled",
                "correlate": { "event.id": "input.appointment_id" }
            }],
            "reschedule_on": [{
                "event": "appointment.rescheduled",
                "filter": { "event.status": { "eq": "confirmed" } },
                "correlate": { "event.id": "input.appointment_id" },
                "until": "event.appointment_at"
            }]
        }))
        .expect("the contract published on the issue");

        assert_eq!(delay.cancel_on.len(), 1);
        assert_eq!(delay.cancel_on[0].event, "appointment.cancelled");
        assert!(delay.cancel_on[0].filter.is_empty());
        assert_eq!(
            delay.cancel_on[0]
                .correlate
                .get("event.id")
                .map(String::as_str),
            Some("input.appointment_id")
        );
        assert_eq!(
            delay.reschedule_on[0].until.as_deref(),
            Some("event.appointment_at")
        );
        assert!(!delay.reschedule_on[0].filter.is_empty());
    }

    #[test]
    fn a_reschedule_without_a_new_instant_is_refused_and_a_cancel_with_one_too() {
        let missing = delay_of(json!({
            "id": "w", "kind": "delay", "until": "input.at",
            "reschedule_on": [{ "event": "a.b", "correlate": { "event.id": "input.id" } }]
        }))
        .expect_err("moving a wait without saying where to is not moving it anywhere");
        assert!(format!("{missing}").contains("until"), "{missing}");

        let pointless = delay_of(json!({
            "id": "w", "kind": "delay", "until": "input.at",
            "cancel_on": [{ "event": "a.b", "correlate": { "event.id": "input.id" },
                            "until": "event.at" }]
        }))
        .expect_err("a cancelled wait has no new instant; the key would be read by nobody");
        assert!(format!("{pointless}").contains("until"), "{pointless}");
    }

    /// The correlation is what makes «this appointment» mean this one. Without it the first
    /// cancellation of ANY appointment would cancel every armed reminder in the hub.
    #[test]
    fn a_hook_without_a_correlation_is_refused() {
        let err = delay_of(json!({
            "id": "w", "kind": "delay", "until": "input.at",
            "cancel_on": [{ "event": "appointment.cancelled" }]
        }))
        .expect_err("an uncorrelated cancel cancels everybody's reminder");
        assert!(format!("{err}").contains("correlate"), "{err}");
    }

    /// Only PATHS, both sides. A `{{…}}` template on the event side is a correlation key whoever
    /// emits the event gets to write; a literal on the run side correlates on a constant.
    #[test]
    fn a_correlation_speaks_only_the_frozen_path_language() {
        for correlate in [
            json!({ "{{event.id}}": "input.id" }),
            json!({ "event.id": "{{input.id}}" }),
            json!({ "id": "input.id" }),
            json!({ "event.id": "42" }),
            json!({ "event.id": "secret.API_KEY" }),
        ] {
            let err = delay_of(json!({
                "id": "w", "kind": "delay", "until": "input.at",
                "cancel_on": [{ "event": "a.b", "correlate": correlate }]
            }))
            .expect_err("only `event.<path>` → `input|steps.<path>` correlates");
            let text = format!("{err}");
            assert!(
                text.contains("correlate") || text.contains("secret"),
                "{text}"
            );
        }
    }

    #[test]
    fn a_list_of_more_than_five_hooks_is_refused() {
        let hooks: Vec<Json> = (0..=MAX_WAIT_HOOKS)
            .map(|i| json!({ "event": format!("a.b{i}"), "correlate": { "event.id": "input.id" } }))
            .collect();
        let err = delay_of(json!({
            "id": "w", "kind": "delay", "until": "input.at", "cancel_on": hooks
        }))
        .expect_err("the match runs on the hot path of every event delivery");
        assert!(
            format!("{err}").contains(&MAX_WAIT_HOOKS.to_string()),
            "{err}"
        );
    }

    #[test]
    fn an_unknown_key_on_a_delay_or_inside_a_hook_is_still_refused() {
        assert!(delay_of(json!({ "id": "w", "kind": "delay", "seconds": 1, "grace": 5 })).is_err());
        assert!(delay_of(json!({
            "id": "w", "kind": "delay", "until": "input.at",
            "cancel_on": [{ "event": "a.b", "correlate": { "event.id": "input.id" },
                            "unless": { "x": 1 } }]
        }))
        .is_err());
    }

    /// The secret scan has to reach INSIDE the hooks for the same reason it reaches a condition's
    /// right-hand side: a filter comparing against `{{secret.K}}` is a guard that never matches and
    /// never says so, and an `until` naming one is a credential parsed as a date.
    #[test]
    fn a_secret_inside_a_hook_is_refused_like_anywhere_else_outside_http() {
        for hook in [
            json!({ "event": "a.b", "correlate": { "event.id": "input.id" },
                    "filter": { "event.ref": { "eq": "{{secret.API_KEY}}" } } }),
            json!({ "event": "a.b", "correlate": { "event.id": "input.id" },
                    "until": "secret.API_KEY" }),
        ] {
            let list = if hook["until"].is_null() {
                "cancel_on"
            } else {
                "reschedule_on"
            };
            let err = delay_of(json!({
                "id": "w", "kind": "delay", "until": "input.at", list: [hook]
            }))
            .expect_err("a flow secret is only readable from an `http` step");
            assert!(format!("{err}").contains("API_KEY"), "{err}");
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
        let StepSpec::Http {
            method,
            timeout_seconds,
            body,
            ..
        } = &def.steps[0].spec
        else {
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
        assert!(
            format!("{over}").contains(&MAX_TIMEOUT_SECONDS.to_string()),
            "{over}"
        );

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

    /// **Both sides of a condition** (hub#828). The scan read the paths a condition READS — the
    /// left of each clause — and never the values it compares AGAINST, so
    /// `{"input.x": {"eq": "{{secret.K}}"}}` saved with a `201` and then meant the literal text
    /// `{{secret.K}}`: the guard its author wrote («only continue if the answer carries my key»)
    /// never matched, the run ended `done` like any guard that stops, and nothing anywhere said
    /// so. `command`, `notify` and `ai` all refused the same string. §13.2 is the rule that was
    /// missing here: what this hub cannot execute is refused at save time instead of stored and
    /// stalled forever.
    #[test]
    fn a_condition_cannot_name_a_secret_on_either_side_of_a_clause() {
        for when in [
            json!({ "input.x": { "eq": "{{secret.API_KEY}}" } }),
            json!({ "input.x": { "contains": "{{secret.API_KEY}}" } }),
            json!({ "input.x": { "in": ["ok", "{{secret.API_KEY}}"] } }),
            json!({ "input.x": { "neq": "secret.API_KEY" } }),
        ] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{ "id": "c", "kind": "condition", "when": when }]
            }))
            .expect_err("a flow that does not do what its author wrote must not save");
            assert!(format!("{err}").contains("API_KEY"), "{err}");
        }

        // A trigger's filter is the same document in the same language, and its scope is the EVENT:
        // there is nothing a secret could mean there either, on either side.
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "triggers": [{ "kind": "event", "event": "sale.completed",
                           "filter": { "event.ref": { "eq": "{{secret.API_KEY}}" } } }],
            "steps": [{ "id": "c", "kind": "condition", "when": { "input.x": { "eq": "1" } } }]
        }))
        .expect_err("a trigger cannot read a flow secret either");
        assert!(format!("{err}").contains("API_KEY"), "{err}");
    }

    /// **The oracle stays closed.** This is the regression guard for the fix above, not a new
    /// rule: the DANGEROUS shape is the secret as the PATH — the left of the clause — because
    /// `lt`/`contains` over a value the hub resolves is a byte-by-byte guessing machine. It was
    /// already refused (that is why hub#828 is a P2 and not a leak), and widening the scan to the
    /// right-hand values must not cost it.
    #[test]
    fn a_secret_as_the_path_of_a_condition_is_still_refused() {
        for when in [
            json!({ "secret.API_KEY": { "exists": true } }),
            json!({ "secret.API_KEY": { "lt": "m" } }),
            json!({ "secret.API_KEY": { "contains": "sk-" } }),
        ] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{ "id": "c", "kind": "condition", "when": when }]
            }))
            .expect_err("the oracle: a condition must never resolve a secret");
            assert!(
                matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_SECRET_NOT_AVAILABLE),
                "{err:?}"
            );
        }
    }

    /// The other half of the rule: a condition that names no secret still saves. A scan that
    /// refuses every string with a dot in it would close the oracle by making conditions useless.
    #[test]
    fn a_condition_that_names_no_secret_still_saves() {
        FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "c", "kind": "condition", "when": {
                "input.total": { "gte": "100" },
                "event.status": { "in": ["paid", "sent"] },
                "steps.a.ok": { "eq": true }
            } }]
        }))
        .expect("an ordinary guard must keep saving");
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
        assert_eq!(
            ai.on_reject,
            RejectPolicy::Cancel,
            "a «no» has always ended the run, and a document that says nothing must not change that"
        );
        assert!(ai.queries.is_empty() && ai.commands.is_empty());
    }

    /// **The refusal stops being a dead end** (hub#1622). Under `manual` the write the model
    /// proposes waits for a person, and until now saying «no» killed the run wherever it stood —
    /// so every step written after it went unrun, including the one that tells the customer what
    /// happened. `approval` steps have been able to say otherwise since hub#950; this is the same
    /// sentence, in the step that actually proposes.
    #[test]
    fn an_ai_step_can_say_that_a_refusal_lets_the_run_carry_on() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "propose_appointment",
                "kind": "ai",
                "prompt": "Book what she asked for",
                "tools": { "commands": ["appointments.appointments.create"] },
                "policy": "manual",
                "on_reject": "continue"
            }]
        }))
        .expect("the shape the WhatsApp template writes so a rejection still answers the customer");
        let StepSpec::Ai(ai) = &def.steps[0].spec else {
            panic!("ai spec");
        };
        assert_eq!(ai.on_reject, RejectPolicy::Continue);
        assert_eq!(ai.policy, AiPolicy::Manual);
    }

    /// Same closed vocabulary as the `approval` step's, and refused for the same reason: `"reject"`
    /// quietly reading as `cancel` would be merciful, and anything quietly reading as `continue`
    /// would carry a run past a refusal — which is the one thing an approval exists to prevent.
    #[test]
    fn an_ai_steps_reject_policy_is_a_closed_vocabulary_and_a_typo_does_not_save() {
        for value in ["cancle", "reject", "continu", ""] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "agent", "kind": "ai", "prompt": "hi", "on_reject": value
                }]
            }))
            .expect_err("a policy this kernel cannot obey is refused where it was typed");
            assert!(format!("{err}").contains("on_reject"), "{err}");
        }
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi", "on_reject": true }]
        }))
        .expect_err("a policy is a string, not a flag");
        assert!(format!("{err}").contains("on_reject"), "{err}");
    }

    /// **The silence stops being a dead end** (hub#1634 — the half deliberately NOT shipped with
    /// hub#1622). A proposal nobody answers expires at 72 h, and until now that killed the run
    /// wherever it stood: every step written after it went unrun, including the one that tells the
    /// customer nobody got back to her. `approval` steps have been able to say otherwise since
    /// hub#950; this is the same sentence, in the step that actually proposes.
    #[test]
    fn an_ai_step_can_say_that_a_silence_lets_the_run_carry_on() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "propose_appointment",
                "kind": "ai",
                "prompt": "Book what she asked for",
                "tools": { "commands": ["appointments.appointments.create"] },
                "policy": "manual",
                "on_expire": "continue"
            }]
        }))
        .expect("the shape the WhatsApp template writes so an expiry still answers the customer");
        let StepSpec::Ai(ai) = &def.steps[0].spec else {
            panic!("ai spec");
        };
        assert_eq!(ai.on_expire, ExpiryPolicy::Continue);
        assert_eq!(ai.policy, AiPolicy::Manual);
    }

    /// The DEFAULT is the one that must not move: every document already deployed says nothing
    /// here, and reading that silence as anything but `reject` would change what a proposal
    /// nobody answered does — on hubs that never asked for it.
    #[test]
    fn an_ai_step_that_says_nothing_still_dies_on_an_expiry() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi" }]
        }))
        .expect("the shape every deployed document has");
        let StepSpec::Ai(ai) = &def.steps[0].spec else {
            panic!("ai spec");
        };
        assert_eq!(
            ai.on_expire,
            ExpiryPolicy::Reject,
            "silence is read as a refusal, because the steps after a proposal assumed it acted"
        );
    }

    /// Same closed vocabulary as the `approval` step's, and refused for the same reason as
    /// `on_reject`: anything quietly reading as `continue` would carry a run past a proposal
    /// nobody ever agreed to.
    #[test]
    fn an_ai_steps_expiry_policy_is_a_closed_vocabulary_and_a_typo_does_not_save() {
        for value in ["cancle", "continu", "rejected", ""] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "agent", "kind": "ai", "prompt": "hi", "on_expire": value
                }]
            }))
            .expect_err("a policy this kernel cannot obey is refused where it was typed");
            assert!(format!("{err}").contains("on_expire"), "{err}");
        }
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi", "on_expire": true }]
        }))
        .expect_err("a policy is a string, not a flag");
        assert!(format!("{err}").contains("on_expire"), "{err}");
    }

    /// **The turn can leave DATA behind, not only a sentence** (hub#1639). Until now an `ai` step
    /// published `{text, tool_calls}` and nothing else, so the three free slots it had just found
    /// while talking to the customer could not become the list she taps — the options had to be
    /// written by hand in the document, which is exactly what they existed to avoid.
    #[test]
    fn an_ai_step_can_declare_the_data_its_turn_leaves_behind() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "pick",
                "kind": "ai",
                "prompt": "Find her three slots",
                "tools": { "queries": ["appointments.free_slots"] },
                "output": {
                    "slots": { "type": "options", "describe": "the free slots you found" },
                    "action": { "type": "text", "describe": "booked, cancelled or asking" }
                }
            }]
        }))
        .expect(
            "the shape the WhatsApp recipe needs to offer slots it discovered mid-conversation",
        );
        let StepSpec::Ai(ai) = &def.steps[0].spec else {
            panic!("ai spec");
        };
        assert_eq!(ai.output.len(), 2);
        let slots = ai.output.iter().find(|f| f.name == "slots").expect("slots");
        assert_eq!(slots.kind, AiOutputKind::Options);
        assert_eq!(slots.describe, "the free slots you found");
        let action = ai
            .output
            .iter()
            .find(|f| f.name == "action")
            .expect("action");
        assert_eq!(action.kind, AiOutputKind::Text);
        // The runner asks the model for these as a SEQUENCE, so the sequence must not move between
        // saves. The kernel's JSON object is ordered by key, so the order is that one — the point
        // of the assertion is that it is FIXED, not which end `slots` lands on.
        let order: Vec<&str> = ai.output.iter().map(|f| f.name.as_str()).collect();
        assert_eq!(order, ["action", "slots"]);
        let again = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "pick", "kind": "ai", "prompt": "Find her three slots",
                "output": {
                    "action": { "type": "text", "describe": "booked, cancelled or asking" },
                    "slots": { "type": "options", "describe": "the free slots you found" }
                }
            }]
        }))
        .expect("the same fields written in the other order");
        let StepSpec::Ai(reordered) = &again.steps[0].spec else {
            panic!("ai spec");
        };
        assert_eq!(
            reordered
                .output
                .iter()
                .map(|f| f.name.as_str())
                .collect::<Vec<_>>(),
            order,
            "the model is asked for the same fields in the same order however they were typed"
        );
    }

    /// A step that declares nothing keeps the output it has always had. The absent case is the one
    /// every flow already in production is written against.
    #[test]
    fn an_ai_step_that_declares_no_output_is_unchanged() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "agent", "kind": "ai", "prompt": "hi" }]
        }))
        .expect("the shape every flow in production is written against");
        let StepSpec::Ai(ai) = &def.steps[0].spec else {
            panic!("ai spec");
        };
        assert!(ai.output.is_empty());
    }

    /// Same discipline as `policy` and `on_reject`: a closed vocabulary, refused where it was
    /// typed. A `"type": "list"` quietly read as `options` would publish Meta's row shape for a
    /// field the author meant as prose, and the customer would get a message nobody wrote.
    #[test]
    fn an_ai_outputs_type_is_a_closed_vocabulary_and_a_typo_does_not_save() {
        for value in ["list", "string", "array", "rows", ""] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "pick", "kind": "ai", "prompt": "hi",
                    "output": { "slots": { "type": value, "describe": "d" } }
                }]
            }))
            .expect_err("a shape this kernel cannot publish is refused where it was typed");
            assert!(format!("{err}").contains("type"), "{err}");
        }
    }

    /// `describe` is not decoration: it is the only thing the model is told about the field. A
    /// field with nothing to read is a field the model fills with whatever it likes, which is the
    /// silent-wrong-answer this vocabulary exists to prevent.
    #[test]
    fn an_ai_output_field_needs_words_saying_what_goes_in_it() {
        for bad in [
            json!({ "type": "text" }),
            json!({ "type": "text", "describe": "  " }),
        ] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "pick", "kind": "ai", "prompt": "hi", "output": { "action": bad }
                }]
            }))
            .expect_err("the description IS the instruction the model reads");
            assert!(format!("{err}").contains("describe"), "{err}");
        }
    }

    /// The turn's own two keys are not available to redefine. `{{steps.pick.text}}` means the
    /// sentence the model wrote in every flow already written; a document that could take that
    /// name would change what an existing mapping resolves to without touching the mapping.
    #[test]
    fn an_ai_output_cannot_take_the_name_of_what_the_turn_already_publishes() {
        for reserved in ["text", "tool_calls"] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "pick", "kind": "ai", "prompt": "hi",
                    "output": { reserved: { "type": "text", "describe": "d" } }
                }]
            }))
            .expect_err("the turn's own keys are not the author's to redefine");
            let text = format!("{err}");
            assert!(text.contains(reserved), "{text}");
        }
    }

    /// A field name travels into `steps.<id>.<name>`, and [`resolve_path`] splits on `.`. A name
    /// with a dot in it would address a level that does not exist and resolve to nothing —
    /// silently, which is the failure mode `rows` was kept out of v1 to avoid.
    #[test]
    fn an_ai_output_name_must_be_addressable_by_the_mapping_language() {
        for bad in ["my.slots", "", " ", "slots-a", "1st"] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "pick", "kind": "ai", "prompt": "hi",
                    "output": { bad: { "type": "text", "describe": "d" } }
                }]
            }))
            .unwrap_err();
            assert!(format!("{err}").contains("output"), "name `{bad}`: {err}");
        }
        FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "pick", "kind": "ai", "prompt": "hi",
                "output": { "free_slots2": { "type": "text", "describe": "d" } }
            }]
        }))
        .expect("letters, digits and `_` are what the mapping language can address");
    }

    /// The whole point of the change, checked where it lands: a bare path inside `interactive`
    /// resolves to the ARRAY the turn published, with its type intact — so the rows of the list
    /// are the slots the model found, not a string that looks like one.
    #[test]
    fn the_options_an_ai_turn_published_become_the_rows_of_a_tappable_list() {
        let scope = json!({
            "steps": {
                "pick": {
                    "text": "Estos son los huecos",
                    "slots": [
                        { "id": "s1", "title": "10:00", "description": "con Ana" },
                        { "id": "s2", "title": "12:30", "description": "con Ana" }
                    ]
                }
            }
        });
        let interactive = json!({
            "type": "list",
            "body": { "text": "{{steps.pick.text}}" },
            "action": { "sections": [{ "title": "Huecos", "rows": "steps.pick.slots" }] }
        });
        let filled = resolve(&interactive, &scope);
        let rows = &filled["action"]["sections"][0]["rows"];
        assert!(rows.is_array(), "the rows keep their type: {filled}");
        assert_eq!(rows.as_array().expect("array").len(), 2);
        assert_eq!(rows[1]["id"], json!("s2"));
        assert_eq!(filled["body"]["text"], json!("Estos son los huecos"));
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
            assert!(
                message.contains("*/N"),
                "`{expr}`: no syntax help in `{message}`"
            );
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
        assert_eq!(
            resolve(&json!("sales.sale.create"), &scope),
            json!("sales.sale.create")
        );
    }

    #[test]
    fn a_template_renders_into_a_string_and_a_missing_path_renders_empty() {
        let scope = scope();
        assert_eq!(
            resolve(
                &json!("Hola {{input.customer.email}} ({{steps.create.lines}})"),
                &scope
            ),
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
            resolve(
                &json!({ "a": ["input.total", 7], "b": { "c": "steps.create.id" } }),
                &scope
            ),
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
        assert!(
            Condition::parse(&json!({ "event.a": { "eq": 1 }, "event.b": { "eq": 2 } }))
                .unwrap()
                .matches(&scope)
        );
        assert!(
            !Condition::parse(&json!({ "event.a": { "eq": 1 }, "event.b": { "eq": 9 } }))
                .unwrap()
                .matches(&scope)
        );
    }

    #[test]
    fn an_unknown_operator_is_refused_instead_of_matching_everything() {
        let err = Condition::parse(&json!({ "event.total": { "greater_than": 100 } }))
            .expect_err("a filter that silently matches everything emails the whole customer list");
        assert!(format!("{err}").contains("greater_than"), "{err}");
    }

    // ── the run clock (hub#1694) ──────────────────────────────────────────────────────────────

    /// The scope every step, trigger and wait hook is evaluated against carries the instant the
    /// engine is looking at, so a document can say something about WHEN it is running.
    #[test]
    fn the_run_clock_is_a_root_of_the_mapping_language_hub1694() {
        let scope = json!({
            "input": {}, "steps": {}, "now": { "iso": "2026-09-09T12:00:00Z" }
        });
        assert!(is_path("now.iso"));
        assert_eq!(
            resolve(&json!("now.iso"), &scope),
            json!("2026-09-09T12:00:00Z")
        );
        assert_eq!(
            render("enviado {{now.iso}}", &scope),
            "enviado 2026-09-09T12:00:00Z"
        );
    }

    /// Both doors an arriving event knocks on — a trigger's `filter` and a wait hook's — read the
    /// clock from the SAME builder. Two objects built by hand is how one of them ends up without
    /// it, and a `within_last` there would answer `false` for ever, silently.
    #[test]
    fn the_scope_an_arriving_event_is_judged_against_carries_the_clock_hub1694() {
        let Json::Object(payload) = json!({ "total": "9.90" }) else {
            unreachable!()
        };
        let scope = event_scope(&payload);
        assert_eq!(resolve(&json!("event.total"), &scope), json!("9.90"));
        let instant = resolve(&json!("now.iso"), &scope);
        assert!(
            instant
                .as_str()
                .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
                .is_some(),
            "`now.iso` is an RFC-3339 instant, not {instant}"
        );
    }

    /// The case this root was added for: Meta refuses a free WhatsApp message when the last one
    /// the customer sent is older than 24 h, and the flow could not tell.
    #[test]
    fn a_window_on_the_clock_is_written_with_within_last_hub1694() {
        let scope = |last: &str| {
            json!({
                "steps": { "thread": { "last_message_at": last } },
                "now": { "iso": "2026-09-09T12:00:00Z" },
            })
        };
        let day = Condition::parse(&json!({
            "steps.thread.last_message_at": { "within_last": 86400 }
        }))
        .unwrap();
        assert!(day.matches(&scope("2026-09-08T12:00:01Z")), "a second inside");
        assert!(!day.matches(&scope("2026-09-08T11:59:59Z")), "a second outside");
        // An instant still to come is recent by any reading of the word, and the clock of whoever
        // wrote the row is not ours: skew must not turn into a message the customer never gets.
        assert!(day.matches(&scope("2026-09-09T12:00:01Z")), "clock skew ahead");
    }

    /// Every way of not knowing answers **no**. A window that cannot be evaluated must not be the
    /// one clause of an AND that quietly passes.
    #[test]
    fn a_window_that_cannot_be_evaluated_does_not_match_hub1694() {
        let day = Condition::parse(&json!({ "steps.t.at": { "within_last": 86400 } })).unwrap();
        let now = json!({ "iso": "2026-09-09T12:00:00Z" });
        // the field is absent
        assert!(!day.matches(&json!({ "steps": { "t": {} }, "now": now })));
        // the field is not an instant
        assert!(!day.matches(&json!({ "steps": { "t": { "at": "ayer" } }, "now": now })));
        // the scope carries no clock at all
        assert!(!day.matches(&json!({ "steps": { "t": { "at": "2026-09-09T11:00:00Z" } } })));
    }

    /// The window is a number of SECONDS, like every other duration in this document
    /// (`delay.seconds`, `max_wait`). Anything else is refused at save time: a window nobody can
    /// evaluate is a guard that would let every message through.
    #[test]
    fn a_window_is_a_positive_number_of_seconds_or_it_is_refused_hub1694() {
        for bad in [json!("24h"), json!(0), json!(-1), json!(1.5), json!(true)] {
            let err = Condition::parse(&json!({ "steps.t.at": { "within_last": bad } }))
                .expect_err("a window that cannot be read is refused, not guessed");
            assert!(
                matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_INVALID_DEFINITION),
                "{bad}: {err}"
            );
        }
        assert!(Condition::parse(&json!({ "steps.t.at": { "within_last": 86400 } })).is_ok());
    }

    /// The right of an operator is LITERAL text (hub#828), so `{"gte": "now.iso"}` would compare a
    /// timestamp against the seven characters `now.iso` and answer `false` for ever, with nothing
    /// saying why. Refused at save time, naming the operator that does mean it.
    #[test]
    fn the_clock_on_the_right_of_an_operator_is_refused_hub1694() {
        let err = Condition::parse(&json!({ "steps.t.at": { "gte": "now.iso" } }))
            .expect_err("a comparison against the literal text `now.iso` never matches");
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_INVALID_DEFINITION),
            "{err}"
        );
        assert!(format!("{err}").contains("within_last"), "{err}");
        // The left is resolved, so the clock is legitimate there.
        assert!(Condition::parse(&json!({ "now.iso": { "gte": "2026-01-01" } })).is_ok());
    }

    // ── the `query` step (hub#954) ────────────────────────────────────────────────────────────

    /// The whitelist of the kind, which is the whole shape of the step: eight keys, and a ninth
    /// is a document the editor accepts and the hub refuses.
    #[test]
    fn a_query_step_takes_its_eight_keys_and_refuses_a_ninth() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "week", "kind": "query", "query": "sales.summary",
                "params": { "from": "input.from" }, "result": "first", "limit": 50
            }]
        }))
        .expect("the keys of the contract");
        let StepSpec::Query(step) = &def.steps[0].spec else {
            panic!("a query step parses into a query spec");
        };
        assert_eq!(step.query, "sales.summary");
        assert_eq!(step.result, QueryResult::First);
        assert_eq!(step.limit, 50);
        assert_eq!(step.params["from"], json!("input.from"));

        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "week", "kind": "query", "query": "sales.summary", "sort": "date" }]
        }))
        .expect_err("a key the hub does not understand is a promise nobody keeps");
        assert!(format!("{err}").contains("sort"), "{err}");
    }

    /// `result` defaults to `first`, and `limit` to the ceiling — never to a small hidden number.
    /// The failure every forum of every competitor is full of is a default that truncates without
    /// saying so (Make's invisible `Limit: 10`), so the default here is the maximum.
    #[test]
    fn a_query_step_defaults_to_the_first_row_and_to_the_ceiling() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "week", "kind": "query", "query": "sales.summary" }]
        }))
        .unwrap();
        let StepSpec::Query(step) = &def.steps[0].spec else {
            panic!("a query step parses into a query spec");
        };
        assert_eq!(step.result, QueryResult::First);
        assert_eq!(step.limit, MAX_QUERY_ROWS);
    }

    /// Refused above the ceiling instead of clamped — the `max_iters` precedent (§14.10). A
    /// document that says 1000 and reads 200 lies to whoever wrote it.
    #[test]
    fn a_limit_beyond_the_ceiling_is_refused_at_save_time() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "w", "kind": "query", "query": "sales.summary", "limit": 1000 }]
        }))
        .expect_err(
            "a run that quietly reads a fifth of what was asked for is worse than a refusal",
        );
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_LIMIT_OUT_OF_RANGE),
            "{err}"
        );
        assert!(
            format!("{err}").contains(&MAX_QUERY_ROWS.to_string()),
            "{err}"
        );

        // Zero and a negative are the same refusal: a read of no rows is not a read.
        for limit in [0, -1] {
            let err = FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{ "id": "w", "kind": "query", "query": "sales.summary", "limit": limit }]
            }))
            .expect_err("a limit below one asks for nothing");
            assert!(
                matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_LIMIT_OUT_OF_RANGE),
                "{err}"
            );
        }
    }

    #[test]
    fn a_query_step_needs_the_name_of_the_read_and_a_result_the_hub_knows() {
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "w", "kind": "query" }]
        }))
        .is_err());

        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "w", "kind": "query", "query": "sales.summary", "result": "rows" }]
        }))
        .expect_err("`rows` is not in v1: the mapping language cannot index an array");
        assert!(format!("{err}").contains("rows"), "{err}");
    }

    // ── a read that serves a LIST (hub#1641) ──────────────────────────────────────────────────

    /// **The symptom of hub#1641, written as the document that fails.**
    ///
    /// The free slots are ALREADY in the database. The only way to put them in front of the
    /// customer was to have a language model read them out loud (hub#1639), because a read could
    /// not say «I return a list» — `result` knew `first` and `count` and nothing else.
    #[test]
    fn a_read_can_serve_the_list_a_tappable_message_shows() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [
                {
                    "id": "free", "kind": "query", "query": "appointments.free_slots",
                    "params": { "day": "input.day" }, "limit": 3,
                    "result": "options",
                    "options": { "id": "slot_id", "title": "label", "description": "staff" }
                },
                {
                    "id": "ask", "kind": "notify", "channel": "whatsapp",
                    "to": { "query": "crm.customer.get", "field": "phone" },
                    "interactive": {
                        "type": "list",
                        "body": { "text": "¿Cuál te viene bien?" },
                        "action": {
                            "button": "Ver huecos",
                            "sections": [{ "title": "Mañana", "rows": "steps.free.options" }]
                        }
                    }
                }
            ]
        }))
        .expect("a read that returns options, and a message that shows them");

        let StepSpec::Query(step) = &def.steps[0].spec else {
            panic!("a query step parses into a query spec");
        };
        assert_eq!(step.result.as_str(), "options");
        assert_eq!(step.limit, 3);
    }

    /// The two halves of «exactly when», both refused at SAVE time. Asking for options without
    /// saying which columns they are made of would publish whatever the module's SELECT happens to
    /// have; declaring the columns without asking for options is dead text nobody reads.
    #[test]
    fn the_shape_of_an_option_and_the_result_that_uses_it_travel_together() {
        let step = |extra: Json| {
            let mut base = json!({
                "id": "free", "kind": "query", "query": "appointments.free_slots"
            });
            let map = base.as_object_mut().unwrap();
            for (k, v) in extra.as_object().unwrap() {
                map.insert(k.clone(), v.clone());
            }
            FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [base] }))
        };

        let err = step(json!({ "result": "options" }))
            .expect_err("table columns are not something a message can send");
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_INVALID_DEFINITION),
            "{err}"
        );
        assert!(format!("{err}").contains("options"), "{err}");

        let err = step(json!({ "options": { "id": "slot_id", "title": "label" } }))
            .expect_err("a mapping nothing reads is a promise the kernel does not keep");
        assert!(
            format!("{err}").contains("first"),
            "it names the result it got: {err}"
        );

        // And `id` and `title` are what a tappable row cannot be sent without.
        for shape in [json!({ "id": "slot_id" }), json!({ "title": "label" })] {
            let err = step(json!({ "result": "options", "options": shape }))
                .expect_err("a row with no id or no title is a row nobody can tap");
            assert!(format!("{err}").contains("title"), "{err}");
        }

        // A fourth key is a document the editor accepts and the hub refuses.
        let err = step(json!({
            "result": "options",
            "options": { "id": "slot_id", "title": "label", "footer": "x" }
        }))
        .expect_err("a tappable row has three parts");
        assert!(format!("{err}").contains("footer"), "{err}");

        // A column NAME, never a template, a path or a value: all three would be looked up
        // verbatim and fail at RUN time naming a column nobody wrote.
        for bad in [
            json!("{{steps.x.y}} con {{steps.x.z}}"),
            json!("slot.id"),
            json!(3),
            json!(""),
        ] {
            let err = step(json!({
                "result": "options",
                "options": { "id": "slot_id", "title": bad }
            }))
            .expect_err("`options.title` is the name of one column");
            assert!(format!("{err}").contains("column"), "{err}");
        }
    }

    /// A read that publishes options is capped at what a tappable message can CARRY — ten, Meta's
    /// list — and not at what the tick can read. Refused, never clamped: the same reason `limit`
    /// is refused above 200, one destination further along.
    #[test]
    fn an_options_read_is_capped_at_what_a_tappable_message_holds() {
        let step = |limit: i64| {
            FlowDefinition::parse(&json!({
                "schema_version": 1,
                "steps": [{
                    "id": "free", "kind": "query", "query": "appointments.free_slots",
                    "result": "options", "limit": limit,
                    "options": { "id": "slot_id", "title": "label" }
                }]
            }))
        };
        assert!(step(MAX_OPTION_ROWS).is_ok());

        let err = step(MAX_OPTION_ROWS + 1)
            .expect_err("a read of 11 rows for a message that holds 10 cannot do what it says");
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_LIMIT_OUT_OF_RANGE),
            "{err}"
        );
        assert!(
            format!("{err}").contains(&MAX_OPTION_ROWS.to_string()),
            "it says the number that applies: {err}"
        );
        // The wider ceiling is still there for the reads that are not going into a message.
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "week", "kind": "query", "query": "sales.summary",
                "result": "first", "limit": MAX_QUERY_ROWS
            }]
        }))
        .is_ok());

        // And silence defaults to the ceiling that applies, never to a smaller hidden number.
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "free", "kind": "query", "query": "appointments.free_slots",
                "result": "options", "options": { "id": "slot_id", "title": "label" }
            }]
        }))
        .unwrap();
        let StepSpec::Query(step) = &def.steps[0].spec else {
            panic!("a query step parses into a query spec");
        };
        assert_eq!(step.limit, MAX_OPTION_ROWS);
    }

    /// `rows` stays refused, and the refusal now says where to go: the reason it was kept out of
    /// v1 has not changed — `resolve_path` still does not index arrays — but the case people
    /// reached for it FOR has an answer, and an error that only says «no» sends them looking for
    /// a way around it.
    #[test]
    fn rows_is_still_refused_and_the_refusal_points_at_options() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "w", "kind": "query", "query": "sales.summary", "result": "rows" }]
        }))
        .expect_err("the mapping language still cannot index an array");
        let text = format!("{err}");
        assert!(text.contains("rows"), "{text}");
        assert!(
            text.contains("options"),
            "the refusal names the shape that does work: {text}"
        );
        assert_eq!(
            resolve_path(
                "steps.free.options.0.title",
                &json!({
                    "steps": { "free": { "options": [{ "id": "a", "title": "10:00" }] } }
                })
            ),
            None,
            "and the frozen surface is untouched: an array is still not walkable"
        );
    }

    /// The params of a read are mapped like any other value, so the `secret.…` refusal has to
    /// reach them: a credential handed to a module's `WHERE` is one written to its query log.
    #[test]
    fn a_secret_cannot_be_interpolated_into_the_params_of_a_query_step() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{
                "id": "w", "kind": "query", "query": "sales.summary",
                "params": { "token": "{{secret.API_KEY}}" }
            }]
        }))
        .expect_err("a secret is readable from an `http` step and from nowhere else");
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_SECRET_NOT_AVAILABLE),
            "{err}"
        );
    }

    #[test]
    fn a_missing_field_never_matches_by_accident() {
        let scope = json!({ "event": {} });
        for op in ["eq", "gt", "gte", "lt", "lte", "in", "contains"] {
            let cond = Condition::parse(&json!({ "event.total": { op: json!(0) } })).unwrap();
            assert!(
                !cond.matches(&scope),
                "`{op}` must not match a missing field"
            );
        }
        assert!(
            Condition::parse(&json!({ "event.total": { "exists": false } }))
                .unwrap()
                .matches(&scope)
        );
    }

    // ── what a FAILURE costs the run (hub#1635) ────────────────────────────────────────────────

    /// The opt-in, parsed where it was typed. Every kind that can fail accepts it, because the
    /// message that tells somebody «no pudo ser» is written after whichever of them broke.
    #[test]
    fn a_step_that_can_fail_may_say_what_a_failure_costs() {
        for step in [
            json!({ "id": "s", "kind": "command", "command": "crm.note.add", "on_error": "continue" }),
            json!({ "id": "s", "kind": "query", "query": "crm.note.list", "on_error": "continue" }),
            json!({ "id": "s", "kind": "delay", "seconds": 60, "on_error": "continue" }),
            json!({ "id": "s", "kind": "http", "url": "https://x.example/y", "on_error": "continue" }),
            json!({ "id": "s", "kind": "ai", "prompt": "book it", "on_error": "continue" }),
            json!({ "id": "s", "kind": "notify", "channel": "email", "template": "t",
                    "to": { "query": "crm.customer.get", "field": "email" },
                    "on_error": "continue" }),
        ] {
            let kind = step["kind"].as_str().unwrap().to_string();
            let def = FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [step] }))
                .unwrap_or_else(|e| panic!("`{kind}` may declare `on_error`: {e}"));
            assert_eq!(
                def.steps[0].on_error,
                ErrorPolicy::Continue,
                "kind `{kind}`"
            );
        }
    }

    /// The DEFAULT, which is the half that must not move: every document already deployed says
    /// nothing here, and silence has to keep meaning what a failure has always meant.
    #[test]
    fn a_step_that_says_nothing_about_failure_still_stops_the_run() {
        let def = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "s", "kind": "command", "command": "crm.note.add" }]
        }))
        .unwrap();
        assert_eq!(def.steps[0].on_error, ErrorPolicy::Stop);
        assert_eq!(ErrorPolicy::default(), ErrorPolicy::Stop);
    }

    /// 🔴 The value the vocabulary deliberately does not have. Refused at SAVE time and naming what
    /// may be written instead, so nobody discovers at 3 AM that the word they typed was read as
    /// «stop» — and so no document can ever ask this kernel to re-run a business command by itself
    /// (ADR-0283 §1).
    #[test]
    fn asking_the_hub_to_retry_a_failed_step_is_refused_naming_the_vocabulary() {
        let err = FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "s", "kind": "command", "command": "sales.sale.create",
                        "on_error": "retry" }]
        }))
        .expect_err("`retry` is not a policy this kernel has");
        let text = format!("{err}");
        assert!(
            text.contains("`on_error` is one of stop, continue"),
            "the refusal names the vocabulary: {text}"
        );
    }

    /// …and a value of the wrong TYPE is refused too, rather than degrading to the default. A
    /// `true` read as «stop» is a document whose author believes they said something.
    #[test]
    fn a_failure_policy_that_is_not_even_a_word_is_refused() {
        assert!(FlowDefinition::parse(&json!({
            "schema_version": 1,
            "steps": [{ "id": "s", "kind": "command", "command": "crm.note.add",
                        "on_error": true }]
        }))
        .is_err());
    }

    /// The kinds that CANNOT fail do not accept the key, and the refusal is the ordinary
    /// unknown-key one. A `condition` that does not match is the flow working exactly as written —
    /// offering it a failure policy would be a guard nobody ever executes — and an `approval`
    /// answers with `on_reject`/`on_expire`, which are about a PERSON and not about a breakage.
    #[test]
    fn a_step_that_cannot_fail_does_not_accept_a_failure_policy() {
        for step in [
            json!({ "id": "s", "kind": "condition", "when": { "input.x": { "eq": 1 } },
                    "on_error": "continue" }),
            json!({ "id": "s", "kind": "approval", "title": "¿Seguimos?", "on_error": "continue" }),
        ] {
            let kind = step["kind"].as_str().unwrap().to_string();
            let err = FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [step] }))
                .expect_err(&format!("`{kind}` must refuse `on_error`"));
            let text = format!("{err}");
            assert!(
                text.contains("unknown key `on_error`"),
                "`{kind}` refuses it as an unknown key: {text}"
            );
        }
    }

    /// A row written by a NEWER hub degrades to the conservative answer instead of being guessed
    /// at. `parse` is fail-closed for the same reason `ExpiryPolicy::parse` is: «carry on past a
    /// failure whose instructions I cannot read» is not an answer this binary may invent.
    #[test]
    fn a_failure_policy_this_binary_does_not_know_reads_as_stop() {
        assert_eq!(ErrorPolicy::parse("continue"), ErrorPolicy::Continue);
        assert_eq!(ErrorPolicy::parse("stop"), ErrorPolicy::Stop);
        for unknown in ["retry", "", "CONTINUE", "skip"] {
            assert_eq!(
                ErrorPolicy::parse(unknown),
                ErrorPolicy::Stop,
                "`{unknown}` must not talk this hub into carrying on"
            );
        }
    }
}
