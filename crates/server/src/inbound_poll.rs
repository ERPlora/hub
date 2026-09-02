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
    /// The message object from Meta's webhook, verbatim.
    #[serde(default)]
    pub payload: Value,
    /// When the SaaS stored it (ISO-8601).
    #[serde(default)]
    pub received_at: String,
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
    pub fn event_payload(&self) -> Map<String, Value> {
        let mut payload = Map::new();
        payload.insert("wa_message_id".into(), json!(self.wa_message_id));
        payload.insert("from".into(), json!(self.from_number));
        payload.insert("text".into(), json!(self.text()));
        payload.insert("received_at".into(), json!(self.received_at));
        payload.insert("message".into(), self.payload.clone());
        payload
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
        })
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

    /// One message as `apps/whatsapp_inbox/api/inbox.py::_serialize` writes it.
    fn message(wa_message_id: &str, text: &str) -> Value {
        json!({
            "wa_message_id": wa_message_id,
            "from": "34600999888",
            "payload": {
                "id": wa_message_id,
                "from": "34600999888",
                "timestamp": "1785153600",
                "type": "text",
                "text": {"body": text},
            },
            "received_at": "2026-08-09T10:00:00+00:00",
        })
    }

    async fn fake_cloud(messages: Vec<Value>) -> FakeCloud {
        async fn inbox(
            State(st): State<FakeInbox>,
            Query(params): Query<HashMap<String, String>>,
            headers: HeaderMap,
        ) -> (StatusCode, Json<Value>) {
            let path = match params.get("after") {
                Some(after) => format!("GET inbox?after={after}"),
                None => "GET inbox".to_string(),
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
            let pending = st.pending.lock().unwrap().clone();
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
            vec!["GET inbox".to_string(), "POST ack".to_string()],
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
            vec!["GET inbox".to_string()],
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
            cloud
                .paths()
                .iter()
                .all(|p| p != "GET inbox?after=" && !p.starts_with("GET inbox?after=")),
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
                "GET inbox".to_string(), // refused
                "GET inbox".to_string(), // the probe…
                "POST ack".to_string(),  // …which acked what it wrote
                "GET inbox".to_string(), // and the next tick polls again, unsuppressed
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
