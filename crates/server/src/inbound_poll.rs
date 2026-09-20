//! Inbound WhatsApp: the hub POLLS its own inbox and turns each message into a core event
//! (ADR-0283 K1c, `architecture/hub/flows.md` §6).
//!
//! This is the last missing link of the inbound chain. Meta's webhook has always reached the
//! SaaS, but what the SaaS did with it was enqueue to SQS for a Lambda from the Python-hub era
//! that POSTed to a route the Rust runtime no longer serves — with `USE_SQS=False` on the live
//! infra, an incoming WhatsApp message went nowhere at all. saas#1353 replaced that with a row
//! (`WhatsAppInboundMessage`) and two endpoints; this is the half that drains them.
//!
//! ## Why the hub pulls instead of the SaaS pushing
//!
//! ADR-0213 fixes the direction of travel — the SaaS declares, the hub acts — and there is no
//! SaaS→hub credential to push with. Hubs also sit behind NAT, so there is frequently nothing to
//! push *to*. A persistent channel is a possible optimisation later; polling is what works today
//! with the pieces that exist.
//!
//! ## The order: write the event, THEN acknowledge
//!
//! This is the one decision that cannot be got wrong, and it is forced by which failure is
//! recoverable:
//!
//!  - **Insert, crash, no ack** → the SaaS still has the message pending, the next poll fetches
//!    it again, and the primary key refuses the second write. One event. Recovered.
//!  - **Ack, crash, no insert** → the SaaS has marked it delivered and will never serve it again.
//!    The message is **gone**, and nothing in the system can notice.
//!
//! So the ack is deliberately the LAST thing that happens, and a failed ack is not a failed poll:
//! the messages are already durable, and the redelivery that follows costs one duplicate insert
//! that the database throws away. Delivery is at-least-once; ingestion is exactly-once because
//! `_event_outbox.id = "wa-<wa_message_id>"` makes Meta's own message id the primary key
//! ([`erplora_runtime::outbox::insert_core_event_once`]).
//!
//! A message that was ingested on an earlier tick but whose ack never landed is **acked anyway**
//! on the next one. Skipping it as "already seen" would leave it pending on the SaaS for ever,
//! re-served on every single poll.
//!
//! ## What it costs
//!
//! One `GET` every [`DEFAULT_INTERVAL_SECS`] = **720 requests/hour per hub**, plus one `POST` per
//! poll that actually found something (a real inbox is idle nearly all the time, so the ack is
//! noise). That is why the gate below matters more than it looks: the poll only runs for a hub
//! that has `whatsapp_inbox` installed, active AND entitled, so the fleet-wide cost tracks the
//! number of hubs that bought the module, not the number of hubs.
//!
//! ## When the SaaS says no: auth backoff (hub#733)
//!
//! The gate above is **local** — module installed, some token present. The SaaS's answer is the
//! other half: a `401`/`403` means "this credential does not work", and that is not transient the
//! way a network error is. A hub with a rotated/revoked token used to retry every 5 s for ever,
//! one WARN per attempt (354 identical lines in 35 minutes, burying every real error). So a
//! refused credential opens an exponential backoff — [`BACKOFF_INITIAL_SECS`] doubling up to
//! [`BACKOFF_MAX_SECS`] — with exactly **one** WARN when it opens, silence while it lasts, and an
//! INFO when the first accepted probe closes it. Recovery needs no restart: the probe that
//! succeeds resumes the normal tick at once. Any other failure (timeouts, 5xx) keeps the plain
//! retry-next-tick behaviour — transient trouble is exactly what a fixed tick handles well.

use std::collections::BTreeSet;
use std::time::{Duration, Instant};

use cloud_client::{Auth, CloudClient};
use erplora_runtime::outbox;
use serde::Deserialize;
use serde_json::{json, Map, Value};

use crate::entitlement::SharedRevalidation;
use crate::state::{HubId, MachineToken, SharedRuntime};

/// The module whose presence turns this poller on. It is the product half of ADR-0283 K1c: the
/// core ingests, the module owns the inbox screen and the flows that react to it.
pub const MODULE_ID: &str = "whatsapp_inbox";

/// The **core** event every inbound message becomes. A declarative flow trigger is just
/// `kind:"event"` on this name — no new concept for a module to learn.
pub const EVENT_NAME: &str = "hub.whatsapp.message_received";

/// Namespace of the outbox primary key, so `wa-<wa_message_id>` can never collide with the
/// random ids the command path mints.
pub const EVENT_ID_PREFIX: &str = "wa-";

/// What a message means when the SaaS says nothing about it. Both mirror the defaults of
/// `apps/whatsapp_inbox/api/inbox.py`, and for the same reason: before saas#1883/#1884 every row
/// the endpoint could serve was a customer's, live. A row without the columns IS that row, so
/// nothing downstream ever has to interpret an empty string.
pub const DEFAULT_DIRECTION: &str = "inbound";
pub const DEFAULT_SOURCE: &str = "live";

/// The values the contract defines. Anything else is reported rather than normalised — see
/// [`InboundMessage::unexpected`].
const DIRECTIONS: [&str; 2] = ["inbound", "outbound"];
const SOURCES: [&str; 2] = ["live", "history"];

/// Tick of the poller (ADR-0283 K1c). Five seconds is the latency a person waiting for an answer
/// on WhatsApp will not notice.
pub const DEFAULT_INTERVAL_SECS: u64 = 5;

/// Env var that overrides [`DEFAULT_INTERVAL_SECS`] (ops escape hatch; not used in production).
pub const INTERVAL_ENV: &str = "HUB_WHATSAPP_POLL_SECS";

/// How much of a rejection is worth carrying into the log line. Enough for `{"error": "..."}`.
const MAX_DETAIL: usize = 300;

/// First wait after the SaaS refuses the hub's credential: two ticks. A 401/403 is not "the
/// network hiccuped", it is "do not come back until something changes" (hub#733).
pub const BACKOFF_INITIAL_SECS: u64 = 2 * DEFAULT_INTERVAL_SECS;

/// Ceiling of the auth backoff. Five minutes keeps a mis-enrolled hub down to 12 requests/hour
/// (from 720) while still converging within minutes of a token rotation landing.
pub const BACKOFF_MAX_SECS: u64 = 300;

/// What recording an auth rejection decided (see [`AuthBackoff::on_rejection`]).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AuthRejection {
    /// `true` only for the rejection that OPENED the backoff — the one worth a WARN. Every
    /// consecutive rejection after it is the same incident and must not add a log line.
    pub entered_backoff: bool,
    /// How long no request will leave the hub before the next probe.
    pub retry_in: Duration,
}

/// Backoff state for a credential the SaaS refuses (401/403), hub#733.
///
/// Same shape as [`erplora_sync::Backoff`] (initial → ×2 → cap, reset on success) — carried here
/// because this crate does not depend on `erplora-sync`, and because this one also has to remember
/// *until when* the poller must stay quiet and whether the incident is new (one WARN) or ongoing
/// (silence).
#[derive(Debug)]
pub struct AuthBackoff {
    initial: Duration,
    max: Duration,
    /// The delay the NEXT rejection will apply. Doubles per consecutive rejection, capped.
    next_delay: Duration,
    /// While `now` is before this instant, no request leaves the hub.
    suppressed_until: Option<Instant>,
    /// Between the first rejection and the first success.
    in_backoff: bool,
}

impl AuthBackoff {
    pub fn new(initial: Duration, max: Duration) -> Self {
        Self {
            initial,
            max,
            next_delay: initial,
            suppressed_until: None,
            in_backoff: false,
        }
    }

    /// Whether a tick at `now` must be skipped without opening a socket.
    pub fn is_suppressed(&self, now: Instant) -> bool {
        self.suppressed_until.is_some_and(|until| now < until)
    }

    /// Record a 401/403 at `now`: suppress the next window and grow the one after it.
    pub fn on_rejection(&mut self, now: Instant) -> AuthRejection {
        let entered_backoff = !self.in_backoff;
        self.in_backoff = true;
        let retry_in = self.next_delay;
        self.suppressed_until = Some(now + retry_in);
        self.next_delay = retry_in.saturating_mul(2).min(self.max);
        AuthRejection {
            entered_backoff,
            retry_in,
        }
    }

    /// Record a successful round trip. Returns `true` when it ends a backoff (worth an INFO);
    /// a success while healthy is just Tuesday and returns `false`.
    pub fn on_success(&mut self) -> bool {
        let recovered = self.in_backoff;
        self.in_backoff = false;
        self.suppressed_until = None;
        self.next_delay = self.initial;
        recovered
    }
}

impl Default for AuthBackoff {
    fn default() -> Self {
        Self::new(
            Duration::from_secs(BACKOFF_INITIAL_SECS),
            Duration::from_secs(BACKOFF_MAX_SECS),
        )
    }
}

/// Tick interval in seconds: [`INTERVAL_ENV`] if it parses to a positive integer, else the
/// default. A `0` would turn the tick into a busy loop against the SaaS, so it is rejected like
/// every sibling job here ([`crate::entitlement::interval_secs`]).
pub fn interval_secs(env_value: Option<&str>) -> u64 {
    env_value
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(DEFAULT_INTERVAL_SECS)
}

/// One inbound message, as `apps/whatsapp_inbox/api/inbox.py::_serialize` writes it.
#[derive(Debug, Clone, Deserialize)]
pub struct InboundMessage {
    /// Meta's `wamid.…`. **Required**: it is the idempotency key, and a page the hub cannot
    /// deduplicate is worth failing loudly over rather than ingesting twice.
    pub wa_message_id: String,
    /// Sender's phone number as Meta reports it (no `+` prefix).
    #[serde(default, rename = "from")]
    pub from_number: String,
    /// Who spoke: `inbound` (the customer) or `outbound` (the owner, from their own phone on a
    /// coexistence number — saas#1883). Raw, straight off the wire: read it through
    /// [`Self::direction`], which applies the meaning an empty value has.
    #[serde(default)]
    direction: String,
    /// The number at the OTHER end, whichever way the message went. On an echo Meta's `from` is
    /// the shop itself, so threading a conversation by `from` would file every reply the owner
    /// ever wrote under the shop's own number. Read it through [`Self::contact`].
    #[serde(default)]
    contact: String,
    /// `live`, or `history` for the 180-day backlog Meta pushes after a coexistence connect
    /// (saas#1884). Read it through [`Self::source`].
    #[serde(default)]
    source: String,
    /// The id of the option the customer TAPPED, as the SaaS lifted it out of Meta's shape
    /// (saas#1894). Empty when the SaaS is older than that field, or when nothing was tapped —
    /// read it through [`Self::reply`], which falls back to the verbatim payload.
    #[serde(default)]
    reply_id: String,
    /// The LABEL of that option, the words the customer actually saw on the button. Same rules as
    /// [`Self::reply_id`].
    #[serde(default)]
    reply_title: String,
    /// **WHICH question this message answers**: the `wamid` of the message being replied to, as
    /// the SaaS lifted it out of Meta's `context` (saas#1919). Empty when the SaaS is older than
    /// that field, or when nothing is being answered — read it through [`Self::answers`], which
    /// falls back to the verbatim payload.
    #[serde(default)]
    reply_to: String,
    /// The message object from Meta's webhook, verbatim.
    #[serde(default)]
    pub payload: Value,
    /// When the SaaS stored it (ISO-8601).
    #[serde(default)]
    pub received_at: String,
    /// **Everything else the SaaS served.** The three fields above arrived precisely because
    /// nobody could see them arrive: this struct named its fields one by one, so serde dropped
    /// the new ones without an error, without a log and without a trace — the SaaS believed it
    /// had delivered a feature that did not exist downstream (hub#1612). Whatever the SaaS grows
    /// next lands here instead of in the bin, and [`InboundMessage::unexpected`] names it.
    #[serde(flatten)]
    unknown: Map<String, Value>,
}

impl InboundMessage {
    /// Outbox primary key derived from Meta's id — the whole exactly-once guarantee.
    pub fn event_id(&self) -> String {
        format!("{EVENT_ID_PREFIX}{}", self.wa_message_id)
    }

    /// Payload of the core event.
    ///
    /// `from` and `text` are lifted out of Meta's nested shape because that is what a declarative
    /// flow condition reads; `message` keeps the original object so anything the two convenience
    /// fields do not cover (media, interactive replies, referrals) is still reachable without a
    /// new runtime release.
    ///
    /// `direction`, `contact` and `source` are what let the module show a whole conversation
    /// instead of half of one (hub#1612): who spoke, whose conversation it is, and whether this
    /// is live traffic or the coexistence backlog. `from` stays exactly what Meta said — on an
    /// echo that is the shop's own number — so a consumer that needs Meta's word still has it.
    pub fn event_payload(&self) -> Map<String, Value> {
        let mut payload = Map::new();
        payload.insert("wa_message_id".into(), json!(self.wa_message_id));
        payload.insert("from".into(), json!(self.from_number));
        payload.insert("direction".into(), json!(self.direction()));
        payload.insert("contact".into(), json!(self.contact()));
        payload.insert("source".into(), json!(self.source()));
        payload.insert("text".into(), json!(self.text()));
        let (reply_id, reply_title) = self.reply();
        payload.insert("reply_id".into(), json!(reply_id));
        payload.insert("reply_title".into(), json!(reply_title));
        payload.insert("reply_to".into(), json!(self.answers()));
        payload.insert("received_at".into(), json!(self.received_at));
        payload.insert("message".into(), self.payload.clone());
        payload
    }

    /// Who spoke, with the meaning an empty value carries: a SaaS that predates the column only
    /// ever stored what the customer sent.
    pub fn direction(&self) -> &str {
        non_empty(&self.direction).unwrap_or(DEFAULT_DIRECTION)
    }

    /// Whose conversation this is — the number at the other end. Falls back to the sender, which
    /// is what `contact` means for every message a pre-saas#1883 SaaS could serve (all inbound).
    pub fn contact(&self) -> &str {
        non_empty(&self.contact).unwrap_or(&self.from_number)
    }

    /// Live traffic, or the coexistence backlog.
    pub fn source(&self) -> &str {
        non_empty(&self.source).unwrap_or(DEFAULT_SOURCE)
    }

    /// **What this runtime did not understand about the SaaS's answer** — field names it has no
    /// place for, and `direction`/`source` values outside the contract.
    ///
    /// Nothing here is dropped in silence, which is the whole point (hub#1612): an unknown field
    /// is named in the log instead of vanishing, and an unknown VALUE travels to the event as-is
    /// rather than being normalised into `inbound` — painting the owner's own reply as the
    /// customer's is the exact harm the SaaS's default exists to prevent, so guessing is worse
    /// than passing it through. Unknown fields are reported but NOT forwarded: a key the SaaS
    /// invents must never be able to overwrite `text` or `message` in the event payload.
    ///
    /// Each gap is spelled `field:<name>` for a field this runtime has no place for, or
    /// `<field>=<value>` for a value outside the contract — what precedes the `=` is what
    /// [`ContractDrift`] remembers it by, so the value only ever rides in the log line.
    pub fn unexpected(&self) -> Vec<String> {
        let mut gaps: Vec<String> = self
            .unknown
            .keys()
            .map(|field| format!("field:{}", detail(field)))
            .collect();
        if !self.direction.is_empty() && !DIRECTIONS.contains(&self.direction.as_str()) {
            gaps.push(format!("direction={}", detail(&self.direction)));
        }
        if !self.source.is_empty() && !SOURCES.contains(&self.source.as_str()) {
            gaps.push(format!("source={}", detail(&self.source)));
        }
        gaps
    }

    /// **The option the customer TAPPED**: `(id, title)`, or two empty strings for anything else
    /// (hub#1633).
    ///
    /// What the SaaS lifted wins: that is where the shape is checked and where Meta's next nesting
    /// gets taught first, so overriding it here would pin the fleet to whichever side was staler.
    /// When it says nothing — a SaaS older than saas#1894, or a row parked before it shipped,
    /// including the coexistence backlog — the same answer is read off the verbatim payload, the
    /// way [`Self::text`] has always read the body. Empty and never an `Option`, for the reason
    /// `text` is: a flow comparing `reply_id` against something should simply not match a photo.
    fn reply(&self) -> (String, String) {
        if !self.reply_id.is_empty() {
            return (self.reply_id.clone(), self.reply_title.clone());
        }
        for (path, id_key, title_key) in REPLY_SHAPES {
            let Some(reply) = dig(&self.payload, path) else {
                continue;
            };
            let Some(id) = reply.get(id_key).and_then(Value::as_str).filter(|s| !s.is_empty())
            else {
                continue;
            };
            let title = reply.get(title_key).and_then(Value::as_str).unwrap_or_default();
            return (id.to_string(), title.to_string());
        }
        (String::new(), String::new())
    }

    /// **WHICH question this message answers** — the `wamid` of the message being replied to, or
    /// an empty string when it answers nothing (hub#1673).
    ///
    /// `reply_id` alone is ambiguous the moment a business asks twice without waiting for an
    /// answer: two questions may perfectly well offer the same option id — a template's approved
    /// «Sí» is the same «Sí» every time — and the automation then confirms whichever it guessed.
    /// Meta already says which one, in `context.id`.
    ///
    /// Same two rules as [`Self::reply`]. What the SaaS lifted WINS, because that is where Meta's
    /// shape is checked and where its next change gets taught first; when it says nothing — a
    /// SaaS older than saas#1919, or a row parked before it shipped, including the coexistence
    /// backlog — the same answer is read off the verbatim payload. Empty and never an `Option`:
    /// a flow comparing `reply_to` against the question it asked should simply not match an
    /// unprompted message, not have to test for absence first. Anything that is not a non-empty
    /// string is not a `wamid` — a forward's `context` carries no `id` at all.
    fn answers(&self) -> String {
        if !self.reply_to.is_empty() {
            return self.reply_to.clone();
        }
        self.payload
            .get(ANSWERS_PATH.0)
            .and_then(|context| context.get(ANSWERS_PATH.1))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string()
    }

    /// The body of a text message, or an empty string for any other kind. Deliberately not an
    /// `Option`: a flow comparing `text` against something should simply not match a photo.
    fn text(&self) -> String {
        self.payload
            .get("text")
            .and_then(|t| t.get("body"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string()
    }
}

/// **Where Meta puts the option a customer tapped, and under which keys.** Three shapes for one
/// idea: a list row, a reply button of an interactive message, and a quick-reply button of a
/// TEMPLATE — the last one names the id `payload` and the label `text`. The SaaS knows the same
/// three (`apps/whatsapp_inbox/api/inbox.py`); this is the half that keeps working against a SaaS
/// that has not shipped them yet.
const REPLY_SHAPES: [(&[&str], &str, &str); 3] = [
    (&["interactive", "list_reply"], "id", "title"),
    (&["interactive", "button_reply"], "id", "title"),
    (&["button"], "payload", "text"),
];

/// **Where Meta puts the message an answer answers**: `context.id`, the `wamid` of the message
/// being replied to. One shape, unlike the tap's three, and no [`dig`]: `Value::get` already
/// answers `None` for every non-object `context` a payload stored verbatim can hold — a
/// forward's, a null, a list — so the walk would only be an untested way of saying the same
/// thing. The SaaS reads the same path (`apps/whatsapp_inbox/api/inbox.py::_reply_to`); this is
/// the half that keeps working against a SaaS that has not shipped the field yet.
const ANSWERS_PATH: (&str, &str) = ("context", "id");

/// Walks `path` through nested objects, or `None` the moment the shape is not that.
///
/// Meta's payload is stored verbatim, so anything it sends is a shape this may meet: a list where
/// an object was expected, a null, a number. An unexpected shape is simply not a reply.
fn dig<'a>(payload: &'a Value, path: &[&str]) -> Option<&'a Value> {
    let mut cursor = payload;
    for key in path {
        cursor = cursor.as_object()?.get(*key)?;
    }
    cursor.as_object().map(|_| cursor)
}

/// One page of the inbox. `cursor` is deliberately not read — see [`InboundPoller::poll_once`].
#[derive(Debug, Clone, Deserialize)]
struct InboxPage {
    #[serde(default)]
    messages: Vec<InboundMessage>,
}

/// What one tick did. All zeros means nothing happened — either the tick was gated off and no
/// request left the hub at all, or the inbox was simply empty, which is the normal case.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct PollReport {
    /// Messages the SaaS served (including ones already ingested on an earlier tick). The SaaS
    /// caps a page at 100; a bigger backlog drains over the following ticks.
    pub fetched: usize,
    /// Messages that became a NEW core event on this tick.
    pub ingested: usize,
    /// Messages the SaaS confirmed it will not serve again.
    pub acked: usize,
    /// Things in the SaaS's answer this runtime did not understand — unknown field names and
    /// `direction`/`source` values outside the contract (hub#1612). Never zero because the page
    /// was fine and unnoticed at the same time: the tick counts them, names the new ones in the
    /// log and carries the number to its caller, so the drift shows up in the ordinary tick line
    /// as well as in the one-off warning.
    pub unexpected: usize,
}

/// Why a tick could not complete. An ack that fails is **not** one of these: the events are
/// already durable and the next tick re-acks.
#[derive(Debug, thiserror::Error)]
pub enum PollError {
    #[error("whatsapp inbox unreachable: {0}")]
    Unreachable(String),
    #[error("whatsapp inbox answered {0}")]
    Rejected(String),
    /// The SaaS refused the hub's credential (401/403). Unlike every other variant this one never
    /// leaves [`InboundPoller::poll_once`]: it is what feeds [`AuthBackoff`], because a refused
    /// credential is not transient and retrying it every tick is the bug (hub#733).
    #[error("whatsapp inbox refused the hub's credential: {0}")]
    AuthRejected(String),
    #[error("whatsapp inbox answer does not match the contract: {0}")]
    Malformed(String),
    #[error("the inbound event could not be written to the outbox: {0}")]
    Outbox(String),
}

/// Drains this hub's inbound WhatsApp inbox into the event outbox.
///
/// Hub id and machine token are read **live** on every tick rather than captured at boot, so a
/// hub that enrols (or rotates its token) after startup starts polling without a restart — the
/// same hot-reload [`crate::notify_transport::CloudNotifyTransport`] relies on.
pub struct InboundPoller {
    http: reqwest::Client,
    cloud: CloudClient,
    hub_id: HubId,
    machine_token: MachineToken,
    /// Quiet-down state for a refused credential (hub#733). `std::sync::Mutex` on purpose: it is
    /// only ever held for a few field reads/writes, never across an `.await`.
    auth_backoff: std::sync::Mutex<AuthBackoff>,
    /// What this poller has already said out loud about a SaaS answer it does not fully
    /// understand (hub#1612). Same lock discipline as `auth_backoff`.
    drift: std::sync::Mutex<ContractDrift>,
}

/// Hand-written so the machine token can never reach a log line: a failing tick prints the poller.
impl std::fmt::Debug for InboundPoller {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("InboundPoller")
            .field("machine_token", &"<redacted>")
            .finish()
    }
}

impl InboundPoller {
    pub fn new(
        http: reqwest::Client,
        cloud_base_url: &str,
        hub_id: HubId,
        machine_token: MachineToken,
    ) -> Self {
        Self {
            http,
            cloud: CloudClient::new(cloud_base_url),
            hub_id,
            machine_token,
            auth_backoff: std::sync::Mutex::new(AuthBackoff::default()),
            drift: std::sync::Mutex::new(ContractDrift::default()),
        }
    }

    /// Test hook: shrink the backoff windows so a test does not wait real minutes.
    #[cfg(test)]
    fn with_auth_backoff(self, backoff: AuthBackoff) -> Self {
        Self {
            auth_backoff: std::sync::Mutex::new(backoff),
            ..self
        }
    }

    /// The hub's machine credential, or `None` if this hub is not enrolled yet.
    fn machine_auth(&self) -> Option<Auth> {
        let hub_id = self.hub_id.read().ok().map(|g| g.clone())?;
        let token = self.machine_token.read().ok().and_then(|g| g.clone())?;
        Some(Auth::HubToken { hub_id, token })
    }

    /// One tick: gate → fetch → write → acknowledge.
    ///
    /// **No cursor is ever sent.** `after` asks the SaaS to skip everything at or before an
    /// instant, and the SaaS already excludes what this hub acked, so a remembered cursor could
    /// only ever *hide* a message — Meta redelivers out of order, and `received_at` is the SaaS's
    /// clock, not the sender's. The ack is what terminates the loop; the cursor exists for a
    /// deliberate replay, which is not what a tick is doing.
    ///
    /// The runtime lock is held only for the gate and for the writes — **never across the
    /// network**. The relay and the scheduler share that lock on a 1 s tick; a poll that held it
    /// through a slow HTTP round trip would stall event delivery for the whole hub.
    pub async fn poll_once(
        &self,
        runtime: &SharedRuntime,
        entitlement: &SharedRevalidation,
    ) -> Result<PollReport, PollError> {
        // ── Gate, before anything opens a socket ────────────────────────────────────────────
        // A hub that does not run the module must not hammer the SaaS 720 times an hour for an
        // inbox that will always be empty, and one that is not entitled must not be served at all.
        {
            let rt = runtime.read().await;
            if !rt.registry().is_active(MODULE_ID) {
                return Ok(PollReport::default());
            }
        }
        let blocked = entitlement
            .read()
            .map(|state| state.is_blocked(MODULE_ID, crate::entitlement::now_unix()))
            .unwrap_or(false);
        if blocked {
            return Ok(PollReport::default());
        }
        // Not enrolled = no credential to sign with. Silence is right here: nothing is lost yet
        // (the messages stay pending on the SaaS) and every tick would otherwise be a 403.
        let Some(auth) = self.machine_auth() else {
            return Ok(PollReport::default());
        };
        // A credential the SaaS refused (hub#733): stay quiet until the backoff window elapses.
        // Checked BEFORE opening a socket, like the gates above — while suppressed, a tick costs
        // the SaaS nothing and the log nothing.
        if self
            .auth_backoff
            .lock()
            .expect("auth backoff lock poisoned")
            .is_suppressed(Instant::now())
        {
            return Ok(PollReport::default());
        }

        // ── Fetch, with no lock held ────────────────────────────────────────────────────────
        let messages = match self.fetch(&auth).await {
            Ok(messages) => {
                // First success after a refusal: the incident is over, resume the normal tick.
                let recovered = self
                    .auth_backoff
                    .lock()
                    .expect("auth backoff lock poisoned")
                    .on_success();
                if recovered {
                    tracing::info!(
                        "inbound whatsapp: the SaaS accepts the credential again, resuming the normal tick"
                    );
                }
                messages
            }
            // A 401/403 is not "the network hiccuped", it is "do not come back until something
            // changes" (a token rotation landing, an entitlement renewed). Absorbed here — an
            // `Err` would make the caller's loop WARN once per tick, which is the bug — with
            // exactly ONE warn when the backoff opens; the consecutive refusals only escalate
            // the window in silence.
            Err(PollError::AuthRejected(detail)) => {
                let rejection = self
                    .auth_backoff
                    .lock()
                    .expect("auth backoff lock poisoned")
                    .on_rejection(Instant::now());
                if rejection.entered_backoff {
                    tracing::warn!(
                        retry_in_secs = rejection.retry_in.as_secs(),
                        "inbound whatsapp: the SaaS refused this hub's credential, backing off: {detail}"
                    );
                } else {
                    tracing::debug!(
                        retry_in_secs = rejection.retry_in.as_secs(),
                        "inbound whatsapp: credential still refused: {detail}"
                    );
                }
                return Ok(PollReport::default());
            }
            Err(e) => return Err(e),
        };
        if messages.is_empty() {
            return Ok(PollReport::default());
        }
        let fetched = messages.len();
        let unexpected = self.report_contract_drift(&messages);

        // ── Write FIRST (see the module docs on why the order is not negotiable) ────────────
        //
        // `acknowledge` collects every message this hub now holds — the ones written on this tick
        // AND the ones a previous tick already wrote but could not ack. Both are safe to ack; only
        // a message that failed to reach the outbox is left pending, so it comes back.
        let mut ingested = 0usize;
        let mut acknowledge: Vec<String> = Vec::with_capacity(fetched);
        {
            let rt = runtime.read().await;
            let hub_id = rt.hub_id().to_string();
            for message in &messages {
                let payload = message.event_payload();
                match outbox::insert_core_event_once(
                    rt.db(),
                    &message.event_id(),
                    &hub_id,
                    EVENT_NAME,
                    &payload,
                )
                .await
                {
                    Ok(fresh) => {
                        if fresh {
                            ingested += 1;
                        }
                        acknowledge.push(message.wa_message_id.clone());
                    }
                    // One bad row must not strand the rest of the page: this message simply is
                    // not acked, so the SaaS serves it again on the next tick.
                    Err(e) => tracing::warn!(
                        wa_message_id = %message.wa_message_id,
                        "inbound whatsapp: the event could not be written, it will be redelivered: {e}"
                    ),
                }
            }
        }

        // ── ...and only THEN acknowledge ────────────────────────────────────────────────────
        let acked = match self.ack(&auth, &acknowledge).await {
            Ok(acked) => acked,
            // Not an error of this tick. The events are durable; the SaaS will serve the same
            // messages again and the primary key will throw the duplicates away.
            Err(e) => {
                tracing::warn!("inbound whatsapp: ack failed, the messages will come back: {e}");
                0
            }
        };

        Ok(PollReport {
            fetched,
            ingested,
            acked,
            unexpected,
        })
    }

    /// **Say out loud what this runtime did not understand** (hub#1612).
    ///
    /// This is the guard for the class of bug, not just its first instance: the SaaS grew
    /// `direction`, `contact` and `source`, and the runtime dropped all three without an error,
    /// without a log and without a trace — the feature looked delivered from the other side while
    /// the person in front of the hub still saw half a conversation. A gap that nobody can see is
    /// a gap nobody fixes, so each distinct one earns exactly one WARN (and DEBUG from then on:
    /// the tick runs every 5 s and 720 identical lines an hour are as good as silence).
    ///
    /// Nothing is thrown away here. The messages are ingested either way; what the line says is
    /// that part of the answer needs a runtime release before anything can act on it.
    fn report_contract_drift(&self, messages: &[InboundMessage]) -> usize {
        let gaps: Vec<String> = messages.iter().flat_map(InboundMessage::unexpected).collect();
        if gaps.is_empty() {
            return 0;
        }
        let count = gaps.len();
        // A poisoned lock must never silence the warning nor take the tick down: the tracker is
        // a noise filter, not correctness, so a poisoned one just means everything looks new.
        let fresh = match self.drift.lock() {
            Ok(mut drift) => drift.observe(gaps),
            Err(poisoned) => poisoned.into_inner().observe(gaps),
        };
        if fresh.is_empty() {
            tracing::debug!("inbound whatsapp: the SaaS answer still carries fields this runtime does not know");
        } else {
            tracing::warn!(
                unknown = %fresh.join(", "),
                "inbound whatsapp: the SaaS answer carries things this runtime does not know; an unknown VALUE reaches the event as-is, an unknown FIELD does not travel at all — the runtime needs a release to use it"
            );
        }
        count
    }

    /// `GET /api/v1/hub/device/whatsapp/inbox/` — everything still pending for this hub.
    async fn fetch(&self, auth: &Auth) -> Result<Vec<InboundMessage>, PollError> {
        let request = self.cloud.whatsapp_inbox(auth, None);
        let mut builder = self.http.get(&request.url);
        for (name, value) in &request.headers {
            builder = builder.header(*name, value);
        }
        let response = builder
            .send()
            .await
            .map_err(|e| PollError::Unreachable(e.to_string()))?;

        let status = response.status();
        let body = response
            .text()
            .await
            .map_err(|e| PollError::Unreachable(e.to_string()))?;
        if !status.is_success() {
            return Err(rejection(status, &body));
        }
        let page: InboxPage =
            serde_json::from_str(&body).map_err(|e| PollError::Malformed(e.to_string()))?;
        Ok(page.messages)
    }

    /// `POST …/inbox/ack/` — the messages this hub now holds. Returns how many rows the SaaS
    /// actually changed (a repeat ack answers `0`, which is why retrying is free).
    async fn ack(&self, auth: &Auth, wa_message_ids: &[String]) -> Result<usize, PollError> {
        if wa_message_ids.is_empty() {
            return Ok(0);
        }
        let request = self.cloud.whatsapp_inbox_ack(auth);
        let mut builder = self
            .http
            .post(&request.url)
            .json(&json!({ "wa_message_ids": wa_message_ids }));
        for (name, value) in &request.headers {
            builder = builder.header(*name, value);
        }
        let response = builder
            .send()
            .await
            .map_err(|e| PollError::Unreachable(e.to_string()))?;

        let status = response.status();
        let body = response
            .text()
            .await
            .map_err(|e| PollError::Unreachable(e.to_string()))?;
        if !status.is_success() {
            return Err(rejection(status, &body));
        }
        Ok(serde_json::from_str::<Value>(&body)
            .ok()
            .and_then(|v| v["acked"].as_u64())
            .unwrap_or(0) as usize)
    }
}

/// `Some(value)` for anything but the empty string — the shape every default in
/// [`InboundMessage`] is built on.
fn non_empty(value: &str) -> Option<&str> {
    Some(value).filter(|v| !v.is_empty())
}

/// What makes two gaps THE SAME gap: the field, never the value. `field:reactions` is its own
/// identity; `source=history-42` is the gap `source`, whatever came after the `=`. An
/// out-of-contract value is remote data, so keying on it would hand [`ContractDrift`] a brand-new
/// gap on every tick — and, once full, mute the first warning of anything that came after it.
fn gap_identity(gap: &str) -> &str {
    gap.split_once('=').map_or(gap, |(field, _)| field)
}

/// What the runtime has already complained about, so a SaaS that grew a field costs ONE log line
/// and not 720 an hour.
///
/// Same shape as [`AuthBackoff`] and for the same reason: the tick runs every 5 s, and a warning
/// repeated on every one of them is a warning nobody reads. Hard-bounded at
/// [`ContractDrift::MAX_TRACKED`] distinct gaps: what it remembers comes off the wire, so
/// "the SaaS would never serve that many" is an assumption and not a limit.
#[derive(Debug, Default)]
pub struct ContractDrift {
    seen: BTreeSet<String>,
}

impl ContractDrift {
    /// Ceiling on how many distinct gaps are remembered. Sixty-four is far past the point where a
    /// human has read the warnings and opened an issue. A gap is identified by its FIELD (see
    /// [`gap_identity`]), so a value that changes on every tick cannot fill this up — but a field
    /// name is remote data too, and "the SaaS would never serve that many" is an assumption, not
    /// a limit.
    pub const MAX_TRACKED: usize = 64;

    /// Record what a page carried and return only what is NEW — what is worth saying out loud.
    ///
    /// Two gaps are the same gap when [`gap_identity`] says so: the field, never the value. That
    /// is what keeps the cap from ever muting a genuinely new gap — a SaaS stamping an id into an
    /// out-of-contract value (`source=history-<batch>`) costs ONE line, whereas keyed by value it
    /// would have filled the tracker in 64 ticks (five minutes) and silenced the first warning of
    /// every field that came after it, for the life of the process.
    ///
    /// Once [`Self::MAX_TRACKED`] distinct gaps are remembered nothing else earns a line. That is
    /// the safe way round: the drift has already been warned about that many times, and
    /// [`PollReport::unexpected`] keeps counting every gap into the ordinary tick line, so the
    /// number never goes mute — only the repetition does.
    pub fn observe<I: IntoIterator<Item = String>>(&mut self, gaps: I) -> Vec<String> {
        gaps.into_iter()
            .filter(|gap| {
                let identity = gap_identity(gap);
                self.seen.len() < Self::MAX_TRACKED && self.seen.insert(identity.to_string())
            })
            .collect()
    }

    /// How many distinct gaps are being remembered.
    pub fn tracked(&self) -> usize {
        self.seen.len()
    }
}

/// A rejection body, trimmed to what is worth logging.
fn detail(body: &str) -> String {
    body.trim().chars().take(MAX_DETAIL).collect()
}

/// Classify a non-2xx answer: a refused credential (401/403) is its own kind of failure, because
/// it is the one the poller must stop retrying every tick (hub#733).
fn rejection(status: reqwest::StatusCode, body: &str) -> PollError {
    if status == reqwest::StatusCode::UNAUTHORIZED || status == reqwest::StatusCode::FORBIDDEN {
        PollError::AuthRejected(format!("{status}: {}", detail(body)))
    } else {
        PollError::Rejected(format!("{status}: {}", detail(body)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::extract::{Query, State};
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::{get, post};
    use axum::{Json, Router};
    use erplora_db::testutil::fresh_db;
    use erplora_db::Params;
    use erplora_runtime::Runtime;
    use serde_json::{json, Value};
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex, RwLock};
    use tokio::sync::RwLock as RuntimeLock;

    const HUB: &str = "hub-wa-7";

    // ── A faithful fake of the SaaS inbox ────────────────────────────────────────────────────
    //
    // Not a stub that replays a canned page: it keeps the same PENDING list the real endpoint
    // keeps (`delivered_to_hub_at IS NULL`), so an un-acked message really does come back on the
    // next poll — which is the whole reason the ingestion has to be idempotent.

    #[derive(Clone)]
    struct FakeInbox {
        pending: Arc<Mutex<Vec<Value>>>,
        inbox_status: Arc<Mutex<StatusCode>>,
        ack_status: Arc<Mutex<StatusCode>>,
        calls: Arc<Mutex<Vec<(String, HeaderMap, Option<Value>)>>>,
    }

    struct FakeCloud {
        base_url: String,
        inbox: FakeInbox,
        server: tokio::task::JoinHandle<()>,
    }

    impl Drop for FakeCloud {
        fn drop(&mut self) {
            self.server.abort();
        }
    }

    impl FakeCloud {
        /// Paths hit so far, in arrival order.
        fn paths(&self) -> Vec<String> {
            self.inbox
                .calls
                .lock()
                .unwrap()
                .iter()
                .map(|(path, _, _)| path.clone())
                .collect()
        }

        fn calls(&self) -> Vec<(String, HeaderMap, Option<Value>)> {
            self.inbox.calls.lock().unwrap().clone()
        }

        fn pending_ids(&self) -> Vec<String> {
            self.inbox
                .pending
                .lock()
                .unwrap()
                .iter()
                .map(|m| m["wa_message_id"].as_str().unwrap_or_default().to_string())
                .collect()
        }

        fn fail_the_ack_with(&self, status: StatusCode) {
            *self.inbox.ack_status.lock().unwrap() = status;
        }

        fn answer_the_inbox_with(&self, status: StatusCode) {
            *self.inbox.inbox_status.lock().unwrap() = status;
        }
    }

    /// How one poll shows up in [`FakeCloud::paths`]. That the filters are there at all is
    /// asserted where the URL is built (`cloud_client::whatsapp_inbox`) and, end to end, by
    /// `the_owners_own_reply_reaches_the_hub_and_says_who_spoke`; here what matters is the ORDER.
    const GET_INBOX: &str = "GET inbox?direction=all&source=all";

    /// The customer's number, and the salon's own — the one Meta puts in `from` when it echoes
    /// back what the owner typed on their own phone.
    const CUSTOMER: &str = "34600999888";
    const SHOP: &str = "34911222333";

    /// One message as `apps/whatsapp_inbox/api/inbox.py::_serialize` writes it TODAY: since
    /// saas#1883/#1884 every row also says who spoke, whose number the conversation is with, and
    /// whether it is live traffic or the backlog Meta pushed after a coexistence connect.
    fn message(wa_message_id: &str, text: &str) -> Value {
        let mut message = legacy_message(wa_message_id, text);
        message["direction"] = json!("inbound");
        message["contact"] = json!(CUSTOMER);
        message["source"] = json!("live");
        message
    }

    /// The same message as a SaaS that predates those columns served it (saas#1353): no
    /// `direction`, no `contact`, no `source`. A hub meets this shape for as long as it takes the
    /// SaaS half to reach its own deployment.
    fn legacy_message(wa_message_id: &str, text: &str) -> Value {
        json!({
            "wa_message_id": wa_message_id,
            "from": CUSTOMER,
            "payload": {
                "id": wa_message_id,
                "from": CUSTOMER,
                "timestamp": "1785153600",
                "type": "text",
                "text": {"body": text},
            },
            "received_at": "2026-08-09T10:00:00+00:00",
        })
    }

    /// What the OWNER typed on their own phone, echoed back by Meta on a coexistence number
    /// (saas#1883). `from` is the shop itself — threading by it would file every reply the owner
    /// ever wrote under the shop's own number — and `contact` is the customer at the other end.
    fn echo(wa_message_id: &str, text: &str) -> Value {
        let mut message = message(wa_message_id, text);
        message["from"] = json!(SHOP);
        message["payload"]["from"] = json!(SHOP);
        message["direction"] = json!("outbound");
        message
    }

    /// A message out of the 180-day backlog Meta pushes after a coexistence connect (saas#1884).
    fn from_history(mut message: Value) -> Value {
        message["source"] = json!("history");
        message
    }

    async fn fake_cloud(messages: Vec<Value>) -> FakeCloud {
        async fn inbox(
            State(st): State<FakeInbox>,
            Query(params): Query<HashMap<String, String>>,
            headers: HeaderMap,
        ) -> (StatusCode, Json<Value>) {
            let mut query: Vec<String> =
                params.iter().map(|(k, v)| format!("{k}={v}")).collect();
            query.sort();
            let path = if query.is_empty() {
                "GET inbox".to_string()
            } else {
                format!("GET inbox?{}", query.join("&"))
            };
            st.calls.lock().unwrap().push((path, headers, None));
            let status = *st.inbox_status.lock().unwrap();
            if !status.is_success() {
                // The shape DRF answers a bad credential with.
                return (
                    status,
                    Json(json!({"detail": "Authentication credentials were not provided."})),
                );
            }

            // ── The two filters of `api/inbox.py`, defaults included ────────────────────────
            //
            // A caller that does not name them gets exactly what the endpoint served before
            // saas#1883/#1884: the customer's live messages and nothing else. That default is
            // deliberate on the SaaS side, so a fake that ignored it would let a poller which
            // asks for nothing look like one that asks for everything — which is the bug.
            let filter = |name: &str, fallback: &str| -> String {
                params
                    .get(name)
                    .map(|v| v.trim())
                    .filter(|v| !v.is_empty())
                    .unwrap_or(fallback)
                    .to_string()
            };
            let direction = filter("direction", DEFAULT_DIRECTION);
            let source = filter("source", DEFAULT_SOURCE);
            if !["inbound", "outbound", "all"].contains(&direction.as_str()) {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"error": "invalid_direction"})),
                );
            }
            if !["live", "history", "all"].contains(&source.as_str()) {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"error": "invalid_source"})),
                );
            }

            let pending: Vec<Value> = st
                .pending
                .lock()
                .unwrap()
                .iter()
                .filter(|m| {
                    let served_direction =
                        m["direction"].as_str().unwrap_or(DEFAULT_DIRECTION).to_string();
                    let served_source = m["source"].as_str().unwrap_or(DEFAULT_SOURCE).to_string();
                    (direction == "all" || direction == served_direction)
                        && (source == "all" || source == served_source)
                })
                .cloned()
                .collect();
            let cursor = pending
                .last()
                .map(|m| m["received_at"].clone())
                .unwrap_or(Value::Null);
            (
                StatusCode::OK,
                Json(json!({"messages": pending, "cursor": cursor})),
            )
        }

        async fn ack(
            State(st): State<FakeInbox>,
            headers: HeaderMap,
            body: String,
        ) -> (StatusCode, Json<Value>) {
            let parsed: Value = serde_json::from_str(&body).unwrap_or(Value::Null);
            st.calls
                .lock()
                .unwrap()
                .push(("POST ack".to_string(), headers, Some(parsed.clone())));

            let status = *st.ack_status.lock().unwrap();
            if !status.is_success() {
                return (status, Json(json!({"error": "boom"})));
            }

            let ids: Vec<String> = parsed["wa_message_ids"]
                .as_array()
                .map(|a| {
                    a.iter()
                        .filter_map(|v| v.as_str().map(str::to_string))
                        .collect()
                })
                .unwrap_or_default();
            let mut pending = st.pending.lock().unwrap();
            let before = pending.len();
            pending
                .retain(|m| !ids.contains(&m["wa_message_id"].as_str().unwrap_or("").to_string()));
            let acked = before - pending.len();
            (StatusCode::OK, Json(json!({"acked": acked})))
        }

        let inbox_state = FakeInbox {
            pending: Arc::new(Mutex::new(messages)),
            inbox_status: Arc::new(Mutex::new(StatusCode::OK)),
            ack_status: Arc::new(Mutex::new(StatusCode::OK)),
            calls: Arc::new(Mutex::new(Vec::new())),
        };
        let app = Router::new()
            .route("/api/v1/hub/device/whatsapp/inbox/", get(inbox))
            .route("/api/v1/hub/device/whatsapp/inbox/ack/", post(ack))
            .with_state(inbox_state.clone());
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        FakeCloud {
            base_url: format!("http://{addr}"),
            inbox: inbox_state,
            server,
        }
    }

    // ── The hub side ─────────────────────────────────────────────────────────────────────────

    /// A hub whose registry really does carry `whatsapp_inbox`, installed through the one door
    /// that registers anything (`install_from_dir`) — not a status map poked by hand.
    async fn hub_with_module(installed: bool) -> SharedRuntime {
        let db = fresh_db().await;
        let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
        rt.ensure_system_tables().await.unwrap();
        if installed {
            let dir = std::env::temp_dir().join(format!(
                "erplora-wa-inbox-{}-{:?}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            std::fs::create_dir_all(&dir).unwrap();
            std::fs::write(
                dir.join("module.json"),
                json!({"id": MODULE_ID, "name": "WhatsApp Inbox", "version": "1.0.0"}).to_string(),
            )
            .unwrap();
            rt.install_from_dir(&dir).await.unwrap();
            let _ = std::fs::remove_dir_all(&dir);
        }
        Arc::new(RuntimeLock::new(rt))
    }

    fn poller(base_url: &str, token: Option<&str>) -> InboundPoller {
        InboundPoller::new(
            reqwest::Client::new(),
            base_url,
            Arc::new(RwLock::new(HUB.to_string())),
            Arc::new(RwLock::new(token.map(str::to_string))),
        )
    }

    /// Entitlement state with nothing known yet — fail-open, which is the live default for a hub
    /// that has not managed a refresh (`crate::entitlement`).
    fn entitled() -> crate::entitlement::SharedRevalidation {
        crate::entitlement::new_shared()
    }

    async fn outbox_rows(runtime: &SharedRuntime) -> Vec<Value> {
        runtime
            .read()
            .await
            .db()
            .query(
                "SELECT id, hub_id, event_name, payload, status, user_id, module_id \
                 FROM _event_outbox ORDER BY id",
                &Params::new(),
            )
            .await
            .unwrap()
            .rows
    }

    /// Every event this hub wrote, keyed by its outbox id, with the payload already parsed.
    async fn payloads_by_id(runtime: &SharedRuntime) -> HashMap<String, Value> {
        outbox_rows(runtime)
            .await
            .into_iter()
            .map(|row| {
                let id = row["id"].as_str().unwrap_or_default().to_string();
                let payload: Value =
                    serde_json::from_str(row["payload"].as_str().unwrap()).unwrap();
                (id, payload)
            })
            .collect()
    }

    // ── Tests ────────────────────────────────────────────────────────────────────────────────

    /// The whole point: a message that reached the SaaS reaches the hub, as ONE core event a
    /// declarative flow can trigger on — carrying THIS hub's tenant, because everything the relay
    /// does downstream is scoped by it.
    #[tokio::test]
    async fn one_inbound_message_becomes_exactly_one_core_event_in_this_hub() {
        let cloud = fake_cloud(vec![message("wamid.1", "is the table free?")]).await;
        let runtime = hub_with_module(true).await;

        let report = poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitled())
            .await
            .unwrap();
        assert_eq!(report.ingested, 1);
        assert_eq!(report.acked, 1);

        let rows = outbox_rows(&runtime).await;
        assert_eq!(rows.len(), 1);
        assert_eq!(
            rows[0]["id"],
            json!("wa-wamid.1"),
            "the id IS the dedup key"
        );
        assert_eq!(rows[0]["event_name"], json!(EVENT_NAME));
        assert_eq!(
            rows[0]["hub_id"],
            json!(HUB),
            "the event belongs to this hub"
        );
        assert_eq!(rows[0]["status"], json!("pending"));

        let payload: Value = serde_json::from_str(rows[0]["payload"].as_str().unwrap()).unwrap();
        assert_eq!(payload["wa_message_id"], json!("wamid.1"));
        assert_eq!(payload["from"], json!("34600999888"));
        assert_eq!(
            payload["text"],
            json!("is the table free?"),
            "a flow reads this"
        );
        assert_eq!(payload["received_at"], json!("2026-08-09T10:00:00+00:00"));
        assert_eq!(
            payload["message"]["type"],
            json!("text"),
            "Meta's object travels verbatim for anything the convenience fields do not cover"
        );

        // Machine credential on both calls: the poller runs with nobody logged in.
        for (path, headers, _) in cloud.calls() {
            assert_eq!(headers["x-hub-token"], "machine-tok", "{path}");
            assert_eq!(headers["x-hub-id"], HUB, "{path}");
            assert!(!headers.contains_key("authorization"), "{path}");
        }
    }

    /// Redelivery is the SaaS's contract, not an anomaly: anything this hub has not acked comes
    /// back. Two polls of the same message must leave ONE event — proved against a fake that
    /// really re-serves it, not by trusting the code path.
    #[tokio::test]
    async fn the_same_message_delivered_twice_is_still_one_event() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        // An ack that never lands: the message stays pending on the SaaS side forever.
        cloud.fail_the_ack_with(StatusCode::INTERNAL_SERVER_ERROR);
        let runtime = hub_with_module(true).await;
        let poller = poller(&cloud.base_url, Some("machine-tok"));

        for _ in 0..2 {
            let _ = poller.poll_once(&runtime, &entitled()).await;
        }

        assert_eq!(
            cloud.pending_ids(),
            vec!["wamid.1".to_string()],
            "the fake really did re-serve it"
        );
        assert_eq!(
            outbox_rows(&runtime).await.len(),
            1,
            "the primary key deduplicates the redelivery"
        );
    }

    /// **The order is insert-then-ack, and this is what proves it.** With an ack that always
    /// fails, an implementation that acked first would abort before writing and the message would
    /// be gone; here the event has to be durable anyway, because the redelivery that follows is
    /// the only thing that can recover it.
    #[tokio::test]
    async fn the_event_is_written_before_the_ack_so_a_lost_ack_never_loses_a_message() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        cloud.fail_the_ack_with(StatusCode::BAD_GATEWAY);
        let runtime = hub_with_module(true).await;

        let report = poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitled())
            .await
            .expect("a failed ack is not a failed ingestion");
        assert_eq!(report.ingested, 1);
        assert_eq!(report.acked, 0, "the SaaS refused the ack");

        assert_eq!(
            outbox_rows(&runtime).await.len(),
            1,
            "the event survives an ack that never lands"
        );
        assert_eq!(
            cloud.paths(),
            vec![GET_INBOX.to_string(), "POST ack".to_string()],
            "fetch, then ack — and the write happened in between"
        );
    }

    /// **Nothing is acknowledged that was not written.** This is what actually pins the order: an
    /// implementation that acked first would send the ack regardless of whether the event ever
    /// reached the outbox, and the SaaS — which never serves an acked message again — would be the
    /// only copy of a message that no longer exists anywhere.
    ///
    /// The failure is forced the bluntest way there is: no `_event_outbox` to write into.
    #[tokio::test]
    async fn a_message_that_could_not_be_written_is_never_acked() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        let runtime = hub_with_module(true).await;
        runtime
            .read()
            .await
            .db()
            .execute_batch("DROP TABLE _event_outbox;")
            .await
            .unwrap();

        let report = poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitled())
            .await
            .unwrap();
        assert_eq!(report.fetched, 1);
        assert_eq!(report.ingested, 0, "there was nowhere to write it");
        assert_eq!(report.acked, 0);

        assert_eq!(
            cloud.paths(),
            vec![GET_INBOX.to_string()],
            "the ack must not even be attempted for a message the hub does not hold"
        );
        assert_eq!(
            cloud.pending_ids(),
            vec!["wamid.1".to_string()],
            "it stays pending, so the next tick can still save it"
        );
    }

    /// The retry after a failed ack must ACK AGAIN (not just skip the duplicate): otherwise the
    /// message it already ingested would come back on every poll, for ever.
    #[tokio::test]
    async fn a_retry_after_a_failed_ack_acks_without_duplicating() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        cloud.fail_the_ack_with(StatusCode::BAD_GATEWAY);
        let runtime = hub_with_module(true).await;
        let poller = poller(&cloud.base_url, Some("machine-tok"));

        poller.poll_once(&runtime, &entitled()).await.unwrap();
        cloud.fail_the_ack_with(StatusCode::OK);
        let second = poller.poll_once(&runtime, &entitled()).await.unwrap();

        assert_eq!(second.fetched, 1, "the SaaS served it again");
        assert_eq!(second.ingested, 0, "already ingested — no second event");
        assert_eq!(
            second.acked, 1,
            "an already-ingested message must still be acked, or it comes back for ever"
        );
        assert!(cloud.pending_ids().is_empty(), "the loop terminated");
        assert_eq!(outbox_rows(&runtime).await.len(), 1);
    }

    /// A hub that does not run the module must not hammer the SaaS: the gate is checked BEFORE
    /// the socket, and the proof is that the fake never sees a request at all.
    #[tokio::test]
    async fn an_inactive_module_never_calls_the_saas() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        let runtime = hub_with_module(false).await;

        let report = poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitled())
            .await
            .unwrap();
        assert_eq!(report, PollReport::default());
        assert!(cloud.paths().is_empty(), "no module, no poll");
        assert!(outbox_rows(&runtime).await.is_empty());
    }

    /// Same door for the entitlement: a module the SaaS says is not paid for is not polled for
    /// either — the calls it would make are billable work on somebody else's plan.
    #[tokio::test]
    async fn a_blocked_entitlement_never_calls_the_saas() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        let runtime = hub_with_module(true).await;

        // The SaaS's last verified word: this hub has no `whatsapp_inbox` → blocked at once,
        // whatever its tier (`RevalidationState::is_blocked`, branch (a)).
        let entitlement = entitled();
        {
            let mut state = entitlement.write().unwrap();
            state.apply_success(
                cloud_client::EntitlementClaims {
                    hub_id: HUB.to_string(),
                    modules: Vec::new(),
                    iat: 0,
                    exp: i64::MAX,
                    grace_until: i64::MAX,
                    paid_grace_until: None,
                    plan: None,
                    max_devices: 0,
                    max_database_size_gb: 0,
                    max_users: 0,
                },
                0,
            );
        }

        let report = poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitlement)
            .await
            .unwrap();
        assert_eq!(report, PollReport::default());
        assert!(cloud.paths().is_empty(), "not entitled, not polled");
    }

    /// An un-enrolled hub has no credential to sign the call with. Quietly doing nothing is right
    /// here (unlike `host.notify`, where silence would hide a message that never went out): there
    /// is nothing to lose yet, and the SaaS would answer 403 to every single tick.
    #[tokio::test]
    async fn without_a_machine_token_nothing_is_polled() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        let runtime = hub_with_module(true).await;

        let report = poller(&cloud.base_url, None)
            .poll_once(&runtime, &entitled())
            .await
            .unwrap();
        assert_eq!(report, PollReport::default());
        assert!(cloud.paths().is_empty(), "no credential, no request");
    }

    /// 🔴 **The symptom of hub#1612**: the owner keeps answering from their own phone, as they
    /// always did, and the hub shows HALF a conversation — the customer's questions, none of the
    /// owner's replies. Two separate things had to be true for that, and this test holds both:
    /// the poller has to ASK for the other direction (the SaaS serves inbound only unless told
    /// otherwise, on purpose) and the runtime has to CARRY the fields home (it declares them one
    /// by one, so serde dropped the new ones without a word).
    #[tokio::test]
    async fn the_owners_own_reply_reaches_the_hub_and_says_who_spoke() {
        let cloud = fake_cloud(vec![
            message("wamid.1", "do you have a slot at five?"),
            echo("wamid.2", "yes, see you at five"),
        ])
        .await;
        let runtime = hub_with_module(true).await;

        let report = poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitled())
            .await
            .unwrap();
        assert_eq!(
            report.ingested, 2,
            "both halves of the conversation, not just the customer's"
        );

        let payloads = payloads_by_id(&runtime).await;
        let question = &payloads["wa-wamid.1"];
        assert_eq!(question["direction"], json!("inbound"));
        assert_eq!(question["contact"], json!(CUSTOMER));

        let reply = &payloads["wa-wamid.2"];
        assert_eq!(
            reply["direction"],
            json!("outbound"),
            "the module has to be able to tell who spoke"
        );
        assert_eq!(
            reply["contact"],
            json!(CUSTOMER),
            "threaded by the OTHER number, never by the shop's own"
        );
        assert_eq!(
            reply["from"],
            json!(SHOP),
            "Meta's `from` still travels verbatim"
        );
        assert_eq!(reply["source"], json!("live"));
    }

    /// The 180-day backlog Meta pushes after a coexistence connect (saas#1884) reaches the hub
    /// too — an inbox that opens on a blank chat for a number the salon has used for years is
    /// not an inbox — but it arrives LABELLED, so the module can paint it without letting the
    /// automation answer a question from March.
    #[tokio::test]
    async fn the_coexistence_backlog_reaches_the_hub_labelled_as_history() {
        let cloud = fake_cloud(vec![
            from_history(message("wamid.old", "are you open on sunday?")),
            message("wamid.1", "do you have a slot at five?"),
        ])
        .await;
        let runtime = hub_with_module(true).await;

        let report = poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitled())
            .await
            .unwrap();
        assert_eq!(report.ingested, 2, "the backlog is not left behind");

        let payloads = payloads_by_id(&runtime).await;
        assert_eq!(payloads["wa-wamid.old"]["source"], json!("history"));
        assert_eq!(payloads["wa-wamid.1"]["source"], json!("live"));
    }

    /// A SaaS that predates the three columns says nothing about direction, contact or source.
    /// The runtime must not hand the module an empty string to interpret: what such a SaaS
    /// serves IS the customer's live message — which is exactly what the endpoint's own defaults
    /// say — so that is what travels.
    #[tokio::test]
    async fn a_message_without_the_new_fields_means_what_it_has_always_meant() {
        let cloud = fake_cloud(vec![legacy_message("wamid.1", "is the table free?")]).await;
        let runtime = hub_with_module(true).await;

        poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitled())
            .await
            .unwrap();

        let payload = payloads_by_id(&runtime).await["wa-wamid.1"].clone();
        assert_eq!(payload["direction"], json!(DEFAULT_DIRECTION));
        assert_eq!(payload["source"], json!(DEFAULT_SOURCE));
        assert_eq!(
            payload["contact"],
            json!(CUSTOMER),
            "with everything inbound, the conversation IS the sender"
        );
    }

    /// 🔴 **The class of the bug, not just this instance.** The SaaS grew three fields and the
    /// runtime dropped them *without a word* — no error, no log, the data simply did not exist
    /// downstream, and the feature looked delivered from the SaaS side. Whatever the SaaS grows
    /// NEXT gets named instead of vanishing.
    #[test]
    fn a_field_this_runtime_does_not_know_is_named_not_dropped_in_silence() {
        let message: InboundMessage = serde_json::from_value(json!({
            "wa_message_id": "wamid.1",
            "from": CUSTOMER,
            "direction": "inbound",
            "contact": CUSTOMER,
            "source": "live",
            "payload": {"type": "text", "text": {"body": "hi"}},
            "received_at": "2026-08-09T10:00:00+00:00",
            "reactions": [{"emoji": "👍"}],
        }))
        .expect("an unknown field must never fail the whole page");

        assert_eq!(message.unexpected(), vec!["field:reactions".to_string()]);
        assert!(
            !message.event_payload().contains_key("reactions"),
            "reported, not forwarded: a key from the SaaS must not be able to overwrite `text`"
        );
    }

    /// And the message it rides on is still ingested WHOLE: naming the gap must not cost the
    /// customer their message.
    #[tokio::test]
    async fn a_message_carrying_an_unknown_field_is_still_ingested() {
        let mut unknown = message("wamid.1", "is the table free?");
        unknown["reactions"] = json!([{"emoji": "👍"}]);
        let cloud = fake_cloud(vec![unknown]).await;
        let runtime = hub_with_module(true).await;

        let report = poller(&cloud.base_url, Some("machine-tok"))
            .poll_once(&runtime, &entitled())
            .await
            .unwrap();
        assert_eq!(report.ingested, 1);
        assert_eq!(report.acked, 1);
        assert_eq!(
            report.unexpected, 1,
            "the tick has to COUNT what it did not understand, or the gap is only visible to \
             whoever happens to be reading the log at that second"
        );
        assert_eq!(
            payloads_by_id(&runtime).await["wa-wamid.1"]["text"],
            json!("is the table free?")
        );
    }

    /// **What the customer TAPPED reaches the flow as a field with a name** (hub#1633).
    ///
    /// The tap always travelled — `payload` is verbatim — but a declarative flow condition reads
    /// ONE path, and finding it inside `message` would make every recipe know the three different
    /// nestings Meta uses for the same idea. Lifted here, `reply_id` is a condition a person can
    /// read: «si tocó *Confirmar* → confirma la cita».
    #[test]
    fn what_the_customer_tapped_is_lifted_out_of_metas_shape_like_the_text_is() {
        let message: InboundMessage = serde_json::from_value(json!({
            "wa_message_id": "wamid.1",
            "from": CUSTOMER,
            "direction": "inbound",
            "contact": CUSTOMER,
            "source": "live",
            "reply_id": "slot:2026-09-09T10:30",
            "reply_title": "martes 10:30",
            "payload": {"type": "interactive", "interactive": {
                "type": "list_reply",
                "list_reply": {"id": "slot:2026-09-09T10:30", "title": "martes 10:30"}
            }},
            "received_at": "2026-09-07T10:00:00+00:00",
        }))
        .expect("the shape the SaaS serves since saas#1894");

        let payload = message.event_payload();
        assert_eq!(payload["reply_id"], json!("slot:2026-09-09T10:30"));
        assert_eq!(payload["reply_title"], json!("martes 10:30"));
        // Named fields now, so they stop being reported as drift the runtime cannot place.
        assert!(
            message.unexpected().is_empty(),
            "a field this runtime understands is not a gap: {:?}",
            message.unexpected()
        );
        // The verbatim object is still there for anything the two convenience fields miss.
        assert_eq!(
            payload["message"]["interactive"]["list_reply"]["id"],
            json!("slot:2026-09-09T10:30")
        );
    }

    /// **The three nestings Meta uses for one idea**, read off the verbatim payload when the SaaS
    /// says nothing — which is every hub polling a SaaS that predates saas#1894, and every row
    /// parked before it shipped, including the coexistence backlog. The hub already owns this kind
    /// of knowledge for `text()`; owning it here is what makes the feature work on the day the hub
    /// ships instead of the day the SaaS does.
    #[test]
    fn a_tap_is_understood_from_metas_own_payload_when_the_saas_does_not_name_it() {
        let cases = [
            (
                json!({"type": "interactive", "interactive": {
                    "type": "list_reply",
                    "list_reply": {"id": "slot:1", "title": "martes 10:30"}
                }}),
                "slot:1",
                "martes 10:30",
            ),
            (
                json!({"type": "interactive", "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "confirm", "title": "Sí"}
                }}),
                "confirm",
                "Sí",
            ),
            // A template's quick-reply button: Meta calls the id `payload` and the label `text`.
            (
                json!({"type": "button", "button": {"payload": "cancel", "text": "Anular"}}),
                "cancel",
                "Anular",
            ),
        ];
        for (payload, id, title) in cases {
            let message: InboundMessage = serde_json::from_value(json!({
                "wa_message_id": "wamid.1",
                "from": CUSTOMER,
                "payload": payload,
                "received_at": "2026-09-07T10:00:00+00:00",
            }))
            .unwrap();
            let event = message.event_payload();
            assert_eq!(event["reply_id"], json!(id), "{payload}");
            assert_eq!(event["reply_title"], json!(title), "{payload}");
        }
    }

    /// **Empty and never absent**, exactly like `text()`: a flow comparing `reply_id` against
    /// something should simply not match a photo, not have to test for absence first. And a shape
    /// Meta never promised — a list where an object was expected, a null — is simply not a reply:
    /// one odd row must not take a whole page down with it.
    #[test]
    fn anything_that_is_not_a_tap_reads_as_empty_rather_than_missing() {
        for payload in [
            json!({"type": "text", "text": {"body": "hola"}}),
            json!({"type": "image", "image": {"id": "123"}}),
            json!({"type": "interactive", "interactive": {"list_reply": ["not", "an", "object"]}}),
            json!({"type": "interactive", "interactive": {"button_reply": {"id": 7}}}),
            json!({"button": {"payload": "", "text": "Anular"}}),
            json!(null),
        ] {
            let message: InboundMessage = serde_json::from_value(json!({
                "wa_message_id": "wamid.1",
                "from": CUSTOMER,
                "payload": payload,
                "received_at": "2026-09-07T10:00:00+00:00",
            }))
            .unwrap();
            let event = message.event_payload();
            assert_eq!(event["reply_id"], json!(""), "{payload}");
            assert_eq!(event["reply_title"], json!(""), "{payload}");
        }
    }

    /// **WHICH question the tap answers reaches the flow as a field with a name** (hub#1673).
    ///
    /// `reply_id` alone is ambiguous the moment a business asks twice without waiting: two
    /// questions may perfectly well offer the same option id — a template's approved «Sí» is the
    /// same «Sí» every time it is sent — and the automation then confirms whichever it guessed.
    /// Meta already says which one: an answer carries `context.id`, the `wamid` of the message
    /// being replied to. Lifted here for the same reason `reply_id` is: a declarative condition
    /// reads ONE path, not a nesting.
    #[test]
    fn which_question_a_tap_answers_is_lifted_like_the_tap_itself_is() {
        let message: InboundMessage = serde_json::from_value(json!({
            "wa_message_id": "wamid.2",
            "from": CUSTOMER,
            "direction": "inbound",
            "contact": CUSTOMER,
            "source": "live",
            "reply_id": "yes",
            "reply_title": "Sí",
            "reply_to": "wamid.the-question",
            "payload": {"type": "interactive", "context": {"id": "wamid.the-question"},
                "interactive": {"button_reply": {"id": "yes", "title": "Sí"}}},
            "received_at": "2026-09-07T10:00:00+00:00",
        }))
        .expect("the shape the SaaS serves since saas#1919");

        let payload = message.event_payload();
        assert_eq!(payload["reply_to"], json!("wamid.the-question"));
        assert_eq!(
            message.unexpected(),
            Vec::<String>::new(),
            "a field this runtime now has a place for must stop being reported as a gap"
        );
    }

    /// The same fallback `reply_id` has, for the same reason: a SaaS older than saas#1919, or a
    /// row parked before it shipped — including the coexistence backlog — still carries Meta's
    /// word verbatim in `payload`. Reading it there is what keeps a hub working against a cloud
    /// that has not shipped the field yet.
    #[test]
    fn the_question_is_read_off_metas_payload_when_the_saas_is_older_than_the_field() {
        let message: InboundMessage = serde_json::from_value(json!({
            "wa_message_id": "wamid.2",
            "from": CUSTOMER,
            "payload": {"type": "text", "context": {"id": "wamid.the-question"},
                "text": {"body": "sí"}},
            "received_at": "2026-09-07T10:00:00+00:00",
        }))
        .expect("what a pre-saas#1919 cloud serves: no `reply_to`, payload verbatim");

        assert_eq!(
            message.event_payload()["reply_to"],
            json!("wamid.the-question")
        );
    }

    /// What the SaaS says WINS over what the hub can work out, exactly as with `reply_id`: the
    /// SaaS is where Meta's shape is checked and where its next change gets taught first.
    #[test]
    fn the_saas_answers_which_question_even_when_the_payload_says_another() {
        let message: InboundMessage = serde_json::from_value(json!({
            "wa_message_id": "wamid.2",
            "from": CUSTOMER,
            "reply_to": "from-the-saas",
            "payload": {"type": "text", "context": {"id": "from-the-payload"},
                "text": {"body": "sí"}},
            "received_at": "2026-09-07T10:00:00+00:00",
        }))
        .unwrap();

        assert_eq!(message.event_payload()["reply_to"], json!("from-the-saas"));
    }

    /// **Empty and never absent**, exactly like `reply_id`: a flow comparing `reply_to` against
    /// the question it asked must simply not match an unprompted message, not have to test for
    /// absence first. And a `context` that answers nothing is not an answer: a forward's
    /// `context` carries no `id`, and anything that is not a non-empty string is not a `wamid`.
    #[test]
    fn a_message_that_answers_no_question_reads_as_empty_rather_than_missing() {
        for payload in [
            json!({"type": "text", "text": {"body": "hola"}}),
            json!({"type": "text", "context": {"forwarded": true}, "text": {"body": "hola"}}),
            json!({"type": "text", "context": {"id": ""}}),
            json!({"type": "text", "context": {"id": 7}}),
            json!({"type": "text", "context": {"id": {"nested": "object"}}}),
            json!({"type": "text", "context": ["not", "an", "object"]}),
            json!({"type": "text", "context": null}),
            json!(null),
        ] {
            let message: InboundMessage = serde_json::from_value(json!({
                "wa_message_id": "wamid.1",
                "from": CUSTOMER,
                "payload": payload,
                "received_at": "2026-09-07T10:00:00+00:00",
            }))
            .unwrap();
            let event = message.event_payload();
            assert_eq!(event["reply_to"], json!(""), "{payload}");
        }
    }

    /// What the SaaS says WINS over what the hub can work out. The SaaS is where the shape is
    /// checked and where Meta's next nesting will be taught first, so a fallback that overrode it
    /// would pin the whole fleet to whichever of the two was staler.
    #[test]
    fn the_saas_field_wins_over_what_the_hub_can_work_out_for_itself() {
        let message: InboundMessage = serde_json::from_value(json!({
            "wa_message_id": "wamid.1",
            "from": CUSTOMER,
            "reply_id": "from-the-saas",
            "reply_title": "lo que dijo el SaaS",
            "payload": {"type": "interactive", "interactive": {
                "button_reply": {"id": "from-the-payload", "title": "lo que dijo Meta"}
            }},
            "received_at": "2026-09-07T10:00:00+00:00",
        }))
        .unwrap();

        let event = message.event_payload();
        assert_eq!(event["reply_id"], json!("from-the-saas"));
        assert_eq!(event["reply_title"], json!("lo que dijo el SaaS"));
    }

    /// A `direction` outside the contract is **never** repainted as the customer's. Claiming the
    /// customer wrote what the owner wrote is the exact harm the SaaS default protects against,
    /// so an unknown value travels as-is — and gets named — instead of being quietly normalised
    /// into the one answer that does damage.
    #[test]
    fn an_out_of_contract_direction_is_reported_never_repainted_as_the_customer() {
        let message: InboundMessage = serde_json::from_value(json!({
            "wa_message_id": "wamid.1",
            "from": CUSTOMER,
            "direction": "sideways",
            "contact": CUSTOMER,
            "source": "yesterday",
            "payload": {},
            "received_at": "2026-08-09T10:00:00+00:00",
        }))
        .unwrap();

        assert_eq!(
            message.unexpected(),
            vec![
                "direction=sideways".to_string(),
                "source=yesterday".to_string()
            ]
        );
        assert_eq!(message.event_payload()["direction"], json!("sideways"));
        assert_eq!(message.event_payload()["source"], json!("yesterday"));
    }

    /// **The noise filter cannot become the leak.** Every gap it remembers is a string the SaaS
    /// served, and a FIELD NAME is remote data as much as a value is: a SaaS that grew a field per
    /// tick would hand this runtime a brand-new gap on every single tick, for the whole lifetime
    /// of the process. The tracker keeps at most [`ContractDrift::MAX_TRACKED`] distinct gaps;
    /// past that it says nothing more, which is the right way round: by then the drift has
    /// already earned its warnings, and `PollReport::unexpected` still counts every one of them
    /// into the tick line, so nothing goes mute.
    #[test]
    fn the_drift_tracker_cannot_grow_without_bound_however_odd_the_saas_gets() {
        let mut drift = ContractDrift::default();

        let reported: usize = (0..ContractDrift::MAX_TRACKED + 50)
            .map(|n| drift.observe(vec![format!("field:extra-{n}")]).len())
            .sum();

        assert_eq!(
            reported,
            ContractDrift::MAX_TRACKED,
            "a SaaS inventing a field per tick stops earning lines once the tracker is full"
        );
        assert_eq!(
            drift.tracked(),
            ContractDrift::MAX_TRACKED,
            "and the tracker stops growing with it"
        );
    }

    /// The tick runs every 5 s. A drift that warned on every one of them would be 720 lines an
    /// hour and nobody would read the 721st — the same reason the credential backoff above says
    /// it once and then stays quiet. Each distinct gap earns exactly one line.
    #[test]
    fn contract_drift_is_reported_the_first_time_and_then_stays_quiet() {
        let mut drift = ContractDrift::default();

        assert_eq!(
            drift.observe(vec!["field:reactions".into(), "field:reactions".into()]),
            vec!["field:reactions".to_string()],
            "one line even when a whole page carries it"
        );
        assert!(
            drift.observe(vec!["field:reactions".into()]).is_empty(),
            "the second tick says nothing"
        );
        assert_eq!(
            drift.observe(vec!["field:reactions".into(), "field:referral".into()]),
            vec!["field:referral".to_string()],
            "but a NEW gap is still worth a line"
        );
    }

    /// 🔴 **The cap must never mute a NEW gap.** A gap is identified by its FIELD, never by its
    /// value: a SaaS that stamps an id into an out-of-contract value (`source=history-<batch>`)
    /// costs ONE line, so it can never fill the tracker — and a field the SaaS grows after five
    /// minutes of that still earns its first warning. Keyed by value, 64 ticks of that SaaS would
    /// have silenced every gap that came after it, for the life of the process.
    #[test]
    fn a_value_that_changes_every_tick_costs_one_line_and_never_mutes_a_new_gap() {
        let mut drift = ContractDrift::default();

        let lines: Vec<String> = (0..ContractDrift::MAX_TRACKED + 50)
            .flat_map(|n| drift.observe(vec![format!("source=history-{n}")]))
            .collect();
        assert_eq!(
            lines,
            vec!["source=history-0".to_string()],
            "one line for the field that drifted, carrying the first value seen"
        );
        assert_eq!(drift.tracked(), 1, "one gap remembered, however many values it took");

        assert_eq!(
            drift.observe(vec!["field:reactions".into()]),
            vec!["field:reactions".to_string()],
            "a field the SaaS grows AFTER that still earns its first line"
        );
    }

    /// **No cursor.** `after` skips everything at or before an instant, and the SaaS already
    /// filters out what this hub acked — so a remembered cursor could only ever hide a message
    /// (Meta redelivers out of order; `received_at` is the SaaS's clock, not Meta's). The ack is
    /// what ends the loop, so the poller never sends one.
    #[tokio::test]
    async fn the_poller_asks_for_everything_pending_and_never_carries_a_cursor() {
        let cloud = fake_cloud(vec![message("wamid.1", "a"), message("wamid.2", "b")]).await;
        let runtime = hub_with_module(true).await;
        let poller = poller(&cloud.base_url, Some("machine-tok"));

        poller.poll_once(&runtime, &entitled()).await.unwrap();
        // A message written with an EARLIER timestamp than the ones already seen: a cursor-based
        // poller would never look at it again.
        let mut older = message("wamid.0", "earlier");
        older["received_at"] = json!("2026-08-09T09:00:00+00:00");
        cloud.inbox.pending.lock().unwrap().push(older);
        poller.poll_once(&runtime, &entitled()).await.unwrap();

        assert!(
            cloud.paths().iter().all(|p| !p.contains("after=")),
            "no cursor ever travels: {:?}",
            cloud.paths()
        );
        let ids: Vec<Value> = outbox_rows(&runtime)
            .await
            .into_iter()
            .map(|r| r["id"].clone())
            .collect();
        assert_eq!(
            ids,
            vec![
                json!("wa-wamid.0"),
                json!("wa-wamid.1"),
                json!("wa-wamid.2")
            ],
            "the late arrival is ingested too"
        );
    }

    /// The tick is 5 s by ADR-0283 K1c, and only an env var with a sane value moves it. A `0`
    /// would busy-loop the SaaS, so it falls back like every sibling job here.
    #[test]
    fn the_interval_defaults_to_five_seconds_and_ignores_nonsense() {
        assert_eq!(interval_secs(None), DEFAULT_INTERVAL_SECS);
        assert_eq!(interval_secs(Some("")), DEFAULT_INTERVAL_SECS);
        assert_eq!(interval_secs(Some("0")), DEFAULT_INTERVAL_SECS);
        assert_eq!(interval_secs(Some("nope")), DEFAULT_INTERVAL_SECS);
        assert_eq!(interval_secs(Some(" 30 ")), 30);
    }

    /// The machine token is a secret and the poller is printed when a tick logs a failure.
    #[test]
    fn debug_never_prints_the_machine_token() {
        let printed = format!("{:?}", poller("https://erplora.com", Some("s3cr3t")));
        assert!(!printed.contains("s3cr3t"), "{printed}");
    }

    // ── Auth backoff (hub#733): a 401 is "do not come back", not "the network hiccuped" ──────

    /// The sequence the issue asks for: exponential from two ticks up to a five-minute ceiling.
    /// 10 s → 20 s → 40 s → 80 s → 160 s → 300 s, and it stays at 300 s for ever after.
    #[test]
    fn auth_backoff_delays_double_from_two_ticks_and_cap_at_five_minutes() {
        let mut backoff = AuthBackoff::default();
        let mut now = std::time::Instant::now();
        let mut delays = Vec::new();
        for _ in 0..7 {
            let rejection = backoff.on_rejection(now);
            delays.push(rejection.retry_in.as_secs());
            now += rejection.retry_in;
        }
        assert_eq!(delays, vec![10, 20, 40, 80, 160, 300, 300]);
    }

    /// The whole state machine in one walk: only the FIRST rejection opens the backoff (that is
    /// the one WARN the issue allows), the window suppresses ticks until it elapses, and one
    /// success both ends the incident and resets the sequence to the initial delay.
    #[test]
    fn auth_backoff_enters_once_suppresses_the_window_and_recovers_on_success() {
        let mut backoff = AuthBackoff::new(Duration::from_secs(10), Duration::from_secs(300));
        let t0 = std::time::Instant::now();
        assert!(!backoff.is_suppressed(t0), "healthy: every tick may poll");

        let first = backoff.on_rejection(t0);
        assert!(
            first.entered_backoff,
            "the first refusal is the one worth a WARN"
        );
        assert!(backoff.is_suppressed(t0 + Duration::from_secs(9)));
        assert!(
            !backoff.is_suppressed(t0 + Duration::from_secs(10)),
            "window over: one probe may go out"
        );

        let second = backoff.on_rejection(t0 + Duration::from_secs(10));
        assert!(
            !second.entered_backoff,
            "still the same incident — a second WARN would be the bug again"
        );

        assert!(backoff.on_success(), "coming back IS worth one INFO");
        assert!(
            !backoff.is_suppressed(t0 + Duration::from_secs(11)),
            "recovery is immediate: no leftover window"
        );
        assert!(!backoff.on_success(), "a healthy success is not a recovery");

        let again = backoff.on_rejection(t0 + Duration::from_secs(60));
        assert!(again.entered_backoff, "a NEW incident gets its own WARN");
        assert_eq!(
            again.retry_in,
            Duration::from_secs(10),
            "the success reset the sequence to the initial delay"
        );
    }

    /// The bug itself (hub#733): a refused credential must not be retried every tick. The tick
    /// that meets the 401 completes as an empty report (an `Err` would make the caller's loop
    /// WARN once per tick — 354 lines in 35 minutes), and every tick inside the window is
    /// suppressed BEFORE opening a socket. After the window exactly one probe goes out; still
    /// refused, the poller goes quiet again.
    #[tokio::test]
    async fn a_refused_credential_backs_off_instead_of_hammering_the_saas() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        cloud.answer_the_inbox_with(StatusCode::UNAUTHORIZED);
        let runtime = hub_with_module(true).await;
        let poller = poller(&cloud.base_url, Some("machine-tok")).with_auth_backoff(
            AuthBackoff::new(Duration::from_millis(300), Duration::from_secs(300)),
        );

        let report = poller
            .poll_once(&runtime, &entitled())
            .await
            .expect("an auth refusal is absorbed by the backoff, not surfaced per tick");
        assert_eq!(report, PollReport::default());
        assert_eq!(cloud.paths().len(), 1);

        for _ in 0..5 {
            let report = poller.poll_once(&runtime, &entitled()).await.unwrap();
            assert_eq!(report, PollReport::default());
        }
        assert_eq!(
            cloud.paths().len(),
            1,
            "inside the window not a single request leaves the hub"
        );

        tokio::time::sleep(Duration::from_millis(350)).await;
        poller.poll_once(&runtime, &entitled()).await.unwrap();
        assert_eq!(cloud.paths().len(), 2, "exactly one probe after the window");

        poller.poll_once(&runtime, &entitled()).await.unwrap();
        assert_eq!(
            cloud.paths().len(),
            2,
            "refused again: quiet again, now behind a longer window"
        );
        assert!(outbox_rows(&runtime).await.is_empty());
    }

    /// «Reanudación inmediata cuando el token vuelva a valer»: the first successful probe both
    /// ingests whatever was pending AND ends the suppression, so the very next tick polls again.
    #[tokio::test]
    async fn the_first_success_after_backoff_resumes_normal_polling_at_once() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        cloud.answer_the_inbox_with(StatusCode::FORBIDDEN);
        let runtime = hub_with_module(true).await;
        let poller = poller(&cloud.base_url, Some("machine-tok")).with_auth_backoff(
            AuthBackoff::new(Duration::from_millis(200), Duration::from_secs(300)),
        );

        poller.poll_once(&runtime, &entitled()).await.unwrap();
        assert_eq!(cloud.paths().len(), 1);

        // The token starts being accepted again (rotation converged on the SaaS side).
        cloud.answer_the_inbox_with(StatusCode::OK);
        tokio::time::sleep(Duration::from_millis(250)).await;
        let probe = poller.poll_once(&runtime, &entitled()).await.unwrap();
        assert_eq!(probe.ingested, 1, "the probe itself ingests the backlog");
        assert_eq!(probe.acked, 1);

        let after = poller.poll_once(&runtime, &entitled()).await.unwrap();
        assert_eq!(after, PollReport::default(), "inbox drained");
        assert_eq!(
            cloud.paths(),
            vec![
                GET_INBOX.to_string(), // refused
                GET_INBOX.to_string(),  // the probe…
                "POST ack".to_string(), // …which acked what it wrote
                GET_INBOX.to_string(),  // and the next tick polls again, unsuppressed
            ]
        );
        assert_eq!(outbox_rows(&runtime).await.len(), 1);
    }

    /// Only a refused credential means "stop asking". Any other rejection (a 500, a bad gateway)
    /// keeps today's contract: the error surfaces to the caller and the next tick retries —
    /// transient trouble is exactly what a fixed tick handles well.
    #[tokio::test]
    async fn a_non_auth_rejection_still_surfaces_and_does_not_back_off() {
        let cloud = fake_cloud(vec![message("wamid.1", "hola")]).await;
        cloud.answer_the_inbox_with(StatusCode::INTERNAL_SERVER_ERROR);
        let runtime = hub_with_module(true).await;
        let poller = poller(&cloud.base_url, Some("machine-tok"));

        let err = poller.poll_once(&runtime, &entitled()).await.unwrap_err();
        assert!(matches!(err, PollError::Rejected(_)), "{err}");

        let err = poller.poll_once(&runtime, &entitled()).await.unwrap_err();
        assert!(matches!(err, PollError::Rejected(_)), "{err}");
        assert_eq!(
            cloud.paths().len(),
            2,
            "a 500 is transient: the next tick still asks"
        );
    }
}
