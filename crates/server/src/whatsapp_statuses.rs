//! What became of the WhatsApp this hub sent (hub#2723).
//!
//! Meta answers a send with an id (`wamid`) the moment it **accepts** it. Whether the customer's
//! phone ever gets it arrives later, as a status: `sent`, `delivered`, `read` or `failed`. The
//! commonest `failed` is free text to a customer who has not written in 24 hours (131047). Until
//! this tick the hub kept every accepted send as delivered, so an appointment reminder Meta threw
//! away looked sent to the business and nobody found out.
//!
//! erplora.com keeps those statuses for the hub (ERPlora/saas#2669) and this tick collects them the
//! way [`crate::inbound_poll`] collects the messages that come in, for the same reasons (the SaaS
//! cannot call a hub, ADR-0213) and in the same order: **fetch, write, and only then acknowledge**.
//! A status acknowledged before it is written is lost; one written and not acknowledged comes back
//! and is recorded once ([`outbox::Undelivered::AlreadySettled`]).
//!
//! What it writes: a `failed` status turns the reminder's outbox row into a dead-letter, stamped
//! `whatsapp.undelivered.<reason>` with Meta's code and words in `last_error`, so it shows in
//! «Eventos caídos» with its reason. It is NOT resendable: erplora.com remembers the key of an
//! accepted send and would answer the old id without sending. `sent`, `delivered` and `read`
//! change nothing the business sees and are simply acknowledged.

use std::time::Instant;

use cloud_client::{Auth, CloudClient};
use erplora_runtime::outbox::{self, Undelivered};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::entitlement::SharedRevalidation;
use crate::inbound_poll::{self, AuthBackoff, PollError};
use crate::state::{HubId, MachineToken, SharedRuntime};

/// How often the hub asks. A status is news minutes after the send, not seconds: 120 requests an
/// hour per hub that runs the inbox, and none for one that does not.
pub const DEFAULT_INTERVAL_SECS: u64 = 30;

/// Meta's word for a message it did not deliver.
const FAILED: &str = "failed";

/// The reason erplora.com gives when it cannot name a better one (ERPlora/saas#2669).
const GENERIC_REASON: &str = "meta_error";

/// Cap on what of Meta's words reaches `last_error`.
const MAX_DETAIL: usize = 300;

#[derive(Debug, Deserialize)]
struct StatusPage {
    #[serde(default)]
    statuses: Vec<DeliveryStatus>,
}

/// One status, in the shape `GET /api/v1/hub/device/whatsapp/statuses/` serves it.
#[derive(Debug, Deserialize)]
struct DeliveryStatus {
    #[serde(default)]
    wa_message_id: String,
    #[serde(default)]
    status: String,
    #[serde(default)]
    error: Option<Value>,
}

/// What one tick did. All zeros is the normal case: nothing to report, or the tick was gated off.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct StatusReport {
    /// Statuses erplora.com served.
    pub fetched: usize,
    /// Failed sends that became a dead-letter on this tick.
    pub recorded: usize,
    /// Statuses erplora.com confirmed it will not serve again.
    pub acked: usize,
}

/// Meta's error, as erplora.com relays it (`{code, reason, title, detail}`), in one line for
/// `last_error`: the code is what support searches for, the words are what the owner reads.
pub fn describe_meta_error(error: &Value) -> String {
    let text = |key: &str| error.get(key).and_then(Value::as_str).unwrap_or_default().trim();
    let code = match error.get("code") {
        Some(Value::Number(n)) => n.to_string(),
        Some(Value::String(s)) => s.trim().to_string(),
        _ => String::new(),
    };
    let reason = Some(text("reason"))
        .filter(|r| !r.is_empty())
        .unwrap_or(GENERIC_REASON);
    let words = [text("title"), text("detail")]
        .into_iter()
        .filter(|w| !w.is_empty())
        .collect::<Vec<_>>()
        .join(" — ");
    let line = match (code.is_empty(), words.is_empty()) {
        (false, false) => format!("Meta {code} ({reason}): {words}"),
        (false, true) => format!("Meta {code} ({reason})"),
        (true, false) => format!("Meta ({reason}): {words}"),
        (true, true) => format!("Meta ({reason})"),
    };
    line.chars().take(MAX_DETAIL).collect()
}

/// The reason erplora.com named for an error, or the generic one.
pub fn meta_reason(error: &Value) -> String {
    error
        .get("reason")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|r| !r.is_empty())
        .unwrap_or(GENERIC_REASON)
        .to_string()
}

/// Collects the delivery statuses of this hub's WhatsApp and records the failed ones.
///
/// Hub id and machine token are read live on every tick, like [`inbound_poll::InboundPoller`], so
/// a hub that enrols after boot starts asking without a restart.
pub struct StatusPoller {
    http: reqwest::Client,
    cloud: CloudClient,
    hub_id: HubId,
    machine_token: MachineToken,
    /// A refused credential quiets the tick down instead of warning on each one (hub#733). Never
    /// held across an `.await`.
    auth_backoff: std::sync::Mutex<AuthBackoff>,
}

/// Hand-written so the machine token never reaches a log line.
impl std::fmt::Debug for StatusPoller {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("StatusPoller")
            .field("machine_token", &"<redacted>")
            .finish()
    }
}

impl StatusPoller {
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

    fn machine_auth(&self) -> Option<Auth> {
        let hub_id = self.hub_id.read().ok().map(|g| g.clone())?;
        let token = self.machine_token.read().ok().and_then(|g| g.clone())?;
        Some(Auth::HubToken { hub_id, token })
    }

    /// One tick: gate → fetch → write → acknowledge. The runtime lock is held for the gate and
    /// the writes, never across the network (the relay shares it on a 1 s tick).
    pub async fn poll_once(
        &self,
        runtime: &SharedRuntime,
        entitlement: &SharedRevalidation,
    ) -> Result<StatusReport, PollError> {
        // The same gate as the inbox: no module, no entitlement or no credential, no request.
        {
            let rt = runtime.read().await;
            if !rt.registry().is_active(inbound_poll::MODULE_ID) {
                return Ok(StatusReport::default());
            }
        }
        let blocked = entitlement
            .read()
            .map(|state| state.is_blocked(inbound_poll::MODULE_ID, crate::entitlement::now_unix()))
            .unwrap_or(false);
        if blocked {
            return Ok(StatusReport::default());
        }
        let Some(auth) = self.machine_auth() else {
            return Ok(StatusReport::default());
        };
        if self.backoff(|b| b.is_suppressed(Instant::now())) {
            return Ok(StatusReport::default());
        }

        let statuses = match self.fetch(&auth).await {
            Ok(statuses) => {
                if self.backoff(AuthBackoff::on_success) {
                    tracing::info!(
                        "whatsapp statuses: erplora.com accepts the credential again, resuming"
                    );
                }
                statuses
            }
            Err(PollError::AuthRejected(detail)) => {
                let rejection = self.backoff(|b| b.on_rejection(Instant::now()));
                if rejection.entered_backoff {
                    tracing::warn!(
                        retry_in_secs = rejection.retry_in.as_secs(),
                        "whatsapp statuses: erplora.com refused this hub's credential, backing off: {detail}"
                    );
                }
                return Ok(StatusReport::default());
            }
            Err(e) => return Err(e),
        };
        if statuses.is_empty() {
            return Ok(StatusReport::default());
        }

        // ── Write FIRST: only what is settled here is acknowledged ─────────────────────────
        let mut report = StatusReport {
            fetched: statuses.len(),
            ..StatusReport::default()
        };
        let mut acknowledge: Vec<Value> = Vec::with_capacity(statuses.len());
        {
            let rt = runtime.read().await;
            let hub_id = rt.hub_id().to_string();
            for status in &statuses {
                if status.status == FAILED {
                    let error = status.error.clone().unwrap_or(Value::Null);
                    let detail = format!(
                        "WhatsApp did not deliver it after accepting it: {}",
                        describe_meta_error(&error)
                    );
                    match outbox::record_undelivered(
                        rt.db(),
                        &hub_id,
                        &status.wa_message_id,
                        &meta_reason(&error),
                        &detail,
                    )
                    .await
                    {
                        Ok(Undelivered::Recorded) => report.recorded += 1,
                        Ok(Undelivered::NotOurs | Undelivered::AlreadySettled) => {}
                        // The relay still holds the row: the status comes back on the next tick.
                        Ok(Undelivered::NotYetSettled) => continue,
                        // Not written, so not acknowledged: it is served again.
                        Err(e) => {
                            tracing::warn!(
                                "whatsapp statuses: could not record a failed send: {e}"
                            );
                            continue;
                        }
                    }
                }
                acknowledge.push(json!({
                    "wa_message_id": status.wa_message_id,
                    "status": status.status,
                }));
            }
        }

        // A failed ack is not a failed tick: what was written stays written, and the statuses
        // served again are settled the second time.
        match self.ack(&auth, &acknowledge).await {
            Ok(acked) => report.acked = acked,
            Err(e) => tracing::warn!("whatsapp statuses: ack failed, they will be served again: {e}"),
        }
        Ok(report)
    }

    fn backoff<T>(&self, f: impl FnOnce(&mut AuthBackoff) -> T) -> T {
        match self.auth_backoff.lock() {
            Ok(mut guard) => f(&mut guard),
            Err(poisoned) => f(&mut poisoned.into_inner()),
        }
    }

    /// `GET /api/v1/hub/device/whatsapp/statuses/`.
    async fn fetch(&self, auth: &Auth) -> Result<Vec<DeliveryStatus>, PollError> {
        let request = self.cloud.whatsapp_statuses(auth);
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
            return Err(inbound_poll::rejection(status, &body));
        }
        let page: StatusPage =
            serde_json::from_str(&body).map_err(|e| PollError::Malformed(e.to_string()))?;
        Ok(page.statuses)
    }

    /// `POST …/statuses/ack/` — returns how many erplora.com confirmed.
    async fn ack(&self, auth: &Auth, statuses: &[Value]) -> Result<usize, PollError> {
        if statuses.is_empty() {
            return Ok(0);
        }
        let request = self.cloud.whatsapp_statuses_ack(auth);
        let mut builder = self
            .http
            .post(&request.url)
            .json(&json!({ "statuses": statuses }));
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
            return Err(inbound_poll::rejection(status, &body));
        }
        Ok(serde_json::from_str::<Value>(&body)
            .ok()
            .and_then(|v| v["acked"].as_u64())
            .unwrap_or(0) as usize)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// What `last_error` says carries Meta's code and words, whatever erplora.com left out.
    #[test]
    fn a_meta_error_reads_with_its_code_reason_and_words_hub2723() {
        let full = json!({"code": 131047, "reason": "outside_window", "title": "Re-engagement message", "detail": "More than 24 hours."});
        assert_eq!(
            describe_meta_error(&full),
            "Meta 131047 (outside_window): Re-engagement message — More than 24 hours."
        );
        assert_eq!(meta_reason(&full), "outside_window");
        assert_eq!(describe_meta_error(&Value::Null), "Meta (meta_error)");
        assert_eq!(meta_reason(&Value::Null), "meta_error");
        assert_eq!(meta_reason(&json!({"reason": "  "})), "meta_error");
        assert_eq!(describe_meta_error(&json!({"code": "470"})), "Meta 470 (meta_error)");
    }
}
