//! Fetching ERPlora's DELEGATED fiscal certificate from the control plane (ADR-0202 §2 — hub#317).
//!
//! The SaaS custodies one `.p12` with which **ERPlora** identifies itself before the AEAT for every
//! hub that signed a power of attorney, and hands it down over
//! `GET /api/v1/hub/device/fiscal/certificate/` (saas#1125). This module is the hub half: it asks
//! for it with the machine credential, and stores it in the `delegated` slot of the core
//! (`erplora_runtime::certificate::set_delegated` — AES-GCM at rest, fail-closed).
//!
//! # This module handles somebody else's PRIVATE KEY
//!
//! Not the customer's: one leak compromises the whole fleet, not one business. Three rules hold it:
//!
//! 1. **Nothing of the container or the passphrase enters a log or an error string.** Errors here
//!    name the URL and the status code and stop there — the response BODY is never interpolated,
//!    not even when it fails to parse (that is exactly the body most likely to hold the key). The
//!    SaaS side does the same and drops `exc_info` on its decrypt branch for the same reason.
//! 2. **It never reaches the browser.** This runs in the runtime, with the `cloud_api_token`, and
//!    the value is stored — never proxied, unlike `cloud_json_passthrough`'s endpoints.
//! 3. **It never reaches disk in the clear**, nor a bundle: storage goes through the core's
//!    encrypted writer, and `certificate::exportable_der_bytes` keeps the slot out of every export.
//!
//! # The three triggers, and the budget that bounds them (ADR-0202 §2 point 4 — hub#318)
//!
//! Rotating a certificate has to converge across the whole fleet **without a push channel and
//! without polling**, so the refetch hangs off three things that already happen:
//!
//! 1. **Boot** — and only when the hub holds no delegated certificate. See
//!    [`boot_requires_refetch`]: a fleet redeploy must not become a thousand simultaneous requests
//!    for a private key.
//! 2. **The heartbeat**, whose response carries the control plane's `cert_version`
//!    ([`heartbeat_requires_refetch`]). This is the one that carries ROTATIONS.
//! 3. **A TLS failure against the AEAT**, raised from inside the `verifactu` engine through
//!    [`erplora_runtime::certificate_refetch`]. The failure IS the trigger, which is what makes
//!    convergence cheap: nobody polls, and a certificate that stopped working fixes itself.
//!
//! **All three go through [`RefetchBudget`], and that is a safety property, not tidiness.** The
//! control plane budgets this endpoint at 20/h per hub (§2.4 point 6), so a trigger that fires in
//! a loop does not merely waste requests: it spends the hub's whole allowance and takes away the
//! one call that could have installed a working certificate. [`MAX_REFETCHES_PER_HOUR`] stays well
//! under that limit on purpose, and it covers the three triggers TOGETHER — one budget, because
//! the endpoint counts one total.
//!
//! **Every trigger is best-effort.** A hub whose refetch fails keeps the certificate it already
//! had and carries on: none of these paths returns an error upwards, none of them clears a slot,
//! and the boot one runs in its own task so that an unreachable control plane cannot hold up
//! `axum::serve` (same rule as the declared-blueprint import of hub#406 — and unlike the seed,
//! which does abort the boot, because a broken seed means the hub is misconfigured).
//!
//! Wiring the delegated certificate into the module's `build_identity` is still hub#319.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use cloud_client::{Auth, CloudClient, DelegatedCertificate};
use erplora_db::DatabaseAdapter;
use erplora_runtime::certificate;
use erplora_runtime::certificate_refetch::RefetchSignal;

use crate::state::AppState;

/// What came of asking the control plane for a certificate.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DelegatedCertificateOutcome {
    /// Stored in the `delegated` slot, encrypted, under `version`. `not_after` is read back from the
    /// container that was actually stored, not copied from the response.
    Installed {
        version: i64,
        not_after: Option<String>,
    },
    /// **404 `no_delegated_certificate`** — the control plane has never uploaded one (`version == 0`
    /// on its side). A normal steady state, not a failure: most hubs use their own certificate and
    /// will never be handed one. The hub keeps whatever it has.
    NotProvisioned,
}

/// Asks the control plane for this hub's delegated certificate.
///
/// `Ok(None)` is the **404**: the SaaS has nothing to hand down. Any other non-2xx, a transport
/// failure or an unparseable body is an `Err`, and none of those error strings ever carries the
/// response body.
pub async fn fetch_delegated_certificate(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
) -> Result<Option<DelegatedCertificate>, String> {
    let req = CloudClient::new(cloud_base_url).fiscal_certificate(auth);
    let mut request = http.get(&req.url);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    let response = request.send().await.map_err(|error| error.to_string())?;
    let status = response.status();
    // 404 = `no_delegated_certificate`: the control plane has nothing for this hub. An ANSWER, not a
    // fault — most hubs sign with their own certificate and will never be delegated one, so turning
    // this into an error would put a permanent red into the majority of the fleet. Every other
    // non-2xx IS a fault the caller has to see: 403 `hub_not_entitled`, 410 `hub_not_found`, a 5xx.
    if status == reqwest::StatusCode::NOT_FOUND {
        return Ok(None);
    }
    if !status.is_success() {
        return Err(format!("{}: status {status}", req.url));
    }
    let body = response.text().await.map_err(|error| error.to_string())?;
    // ⚠️ The body is NEVER interpolated into the error. This is the branch that most invites it —
    // «it did not parse, let me show you what came back» — and the thing that came back is a private
    // key and its passphrase. `serde_json::Error` carries only a reason plus a line/column, which is
    // enough to tell a truncated response from a changed contract.
    DelegatedCertificate::parse(&body)
        .map(Some)
        .map_err(|error| format!("{}: respuesta ilegible ({error})", req.url))
}

/// Fetches the delegated certificate and stores it, encrypted, in the core's `delegated` slot.
///
/// A 404 leaves the hub exactly as it was: a hub with its own certificate keeps signing with it, and
/// one with neither stays as unable to invoice as it already was. Never an error — «ERPlora has not
/// delegated anything to you» is an answer, not a fault.
pub async fn install_delegated_certificate(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<DelegatedCertificateOutcome, String> {
    let Some(cert) = fetch_delegated_certificate(http, cloud_base_url, auth).await? else {
        return Ok(DelegatedCertificateOutcome::NotProvisioned);
    };
    store_delegated_certificate(db, hub_id, &cert).await
}

/// Stores an already-fetched certificate in the `delegated` slot and reports what landed.
///
/// Split out of [`install_delegated_certificate`] so the scheduled path can hold the runtime's lock
/// for THIS half only. Fetching takes a network round trip, and the runtime mutex is the one every
/// query and command in the hub goes through: holding it across a call to the control plane would
/// freeze the till for as long as the SaaS takes to answer.
async fn store_delegated_certificate(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    cert: &DelegatedCertificate,
) -> Result<DelegatedCertificateOutcome, String> {
    // `certificate_type` is the control plane's DECLARATION of what it is handing down (hub#470).
    // The core cross-checks it against the container itself and refuses the install when the two
    // disagree — the error surfaces here, the hub keeps the certificate it already had, and the
    // refetch triggers keep asking until the control plane serves something coherent. Refusing is
    // the recoverable failure: the alternative is every record POSTed to the wrong AEAT door and
    // rejected one by one (ADR-0189).
    certificate::set_delegated(
        db,
        hub_id,
        &cert.pkcs12_b64,
        &cert.password,
        cert.version,
        cert.certificate_type.as_deref(),
    )
    .await
    .map_err(|error| error.to_string())?;
    // The DELEGATED slot's date, not the active one's (ADR-0202 §2.5): this is what the heartbeat
    // reports, and the SaaS compares it against the `not_after` of the `.p12` it custodies. A hub
    // with its own certificate uploaded signs with THAT one but must still report its delegated
    // fallback — `certificate::expiry` would answer about the wrong certificate there.
    //
    // Read back from the container that was actually stored, never copied from `cert.not_after`: the
    // hub trusts the bytes it holds, not the metadata that came with them.
    let not_after = certificate::slot_expiry(db, hub_id, certificate::CertificateKind::Delegated)
        .await
        .ok()
        .flatten();
    Ok(DelegatedCertificateOutcome::Installed {
        version: cert.version,
        not_after,
    })
}

// ── The three triggers (ADR-0202 §2 point 4) ──────────────────────────────────────────────────

/// What is asking for a refetch. Named rather than boolean because each one answers «is this
/// needed?» differently, and because it is what the log line says when a certificate changes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RefetchTrigger {
    /// **Boot.** Fires once per process, and only for a hub that holds nothing from ERPlora.
    Boot,
    /// **The heartbeat**, carrying the version the control plane announced (`None` = it announced
    /// nothing, which an older SaaS does). This is the trigger that propagates a rotation.
    Heartbeat { announced: Option<i64> },
    /// **mTLS against the AEAT failed.** Unconditional: the hub cannot tell from here whether its
    /// certificate was revoked, replaced or simply refused, and the whole point of this trigger is
    /// to converge on a failure it does not understand. The budget is what bounds it.
    TlsFailure,
    /// **The customer just signed the Anexo I** (hub#817). Fires only for a hub that holds no
    /// delegated certificate — the same predicate as [`RefetchTrigger::Boot`], because that is
    /// exactly the state signing gets a hub out of: without a vigente grant the control plane
    /// refuses the key (saas#1438), so the hub has been coming up empty.
    ///
    /// It exists because the trigger that would otherwise pick this up is the heartbeat, and the
    /// heartbeat runs **once a day**. Waiting for it would mean the person who just signed sits in
    /// front of a go-live that still refuses, for up to 24 hours, with nothing to tell them why.
    GrantSigned,
}

/// How many refetches this hub allows itself per rolling hour, across ALL three triggers.
///
/// Deliberately far below [`CONTROL_PLANE_QUOTA_PER_HOUR`]. Being throttled by the SaaS is not a
/// slowdown here: the refused request is the one that would have installed a working certificate,
/// so a hub that spends its allowance chasing a problem locks itself out of the fix. Legitimate use
/// is one refetch at boot plus one per rotation, so six is already generous.
pub const MAX_REFETCHES_PER_HOUR: usize = 6;

/// The control plane's own limit on `GET /api/v1/hub/device/fiscal/certificate/`
/// (`@quota(rate="20/h")` keyed by hub — ADR-0202 §2.4 point 6). Mirrored here so the relation
/// between the two numbers is checked by a test instead of remembered.
pub const CONTROL_PLANE_QUOTA_PER_HOUR: usize = 20;

/// The relation between the two is the guarantee, so the COMPILER checks it: raising the hub's own
/// budget to (or past) the control plane's quota does not fail a test somebody can skip — it fails
/// the build. A throttled hub is a hub locked out of the request that fixes its certificate.
const _: () = assert!(MAX_REFETCHES_PER_HOUR < CONTROL_PLANE_QUOTA_PER_HOUR);

/// A rolling-window allowance for refetches, shared by the three triggers.
///
/// Rolling rather than fixed buckets on purpose: a fixed hourly bucket lets a hub spend the whole
/// allowance at 10:59 and the whole next one at 11:01, which is exactly the burst the control plane
/// is protecting itself from.
#[derive(Debug)]
pub struct RefetchBudget {
    max: usize,
    window: Duration,
    /// When each spend happened, oldest first. Bounded by `max`, so it never grows.
    spent: Mutex<VecDeque<Instant>>,
}

impl RefetchBudget {
    /// The production budget: [`MAX_REFETCHES_PER_HOUR`] per rolling hour.
    pub fn hourly() -> Self {
        Self::new(MAX_REFETCHES_PER_HOUR, Duration::from_secs(3600))
    }

    pub fn new(max: usize, window: Duration) -> Self {
        Self {
            max,
            window,
            spent: Mutex::new(VecDeque::new()),
        }
    }

    /// Takes one unit of budget if there is one. `false` = «not now» — never an error and never a
    /// wait: a refetch that is skipped is picked up by the next heartbeat.
    ///
    /// `now` is a parameter so the window is testable without sleeping for an hour.
    pub fn try_spend(&self, now: Instant) -> bool {
        let mut spent = match self.spent.lock() {
            Ok(guard) => guard,
            // A panic in another thread must not disable the fetching of certificates; the worst
            // case of continuing is one extra request.
            Err(poisoned) => poisoned.into_inner(),
        };
        while spent
            .front()
            .is_some_and(|t| now.duration_since(*t) >= self.window)
        {
            spent.pop_front();
        }
        if spent.len() >= self.max {
            return false;
        }
        spent.push_back(now);
        true
    }
}

/// Does the version the heartbeat announced mean this hub has to refetch? (ADR-0202 §2.5)
///
/// - **Nothing announced** (`None`) — an older SaaS, or a body this hub could not read. No news is
///   not news of a rotation.
/// - **`0`** — the control plane has never uploaded a certificate. The GET would answer 404
///   `no_delegated_certificate`, so asking is pure quota burnt: §2.5 states it in exactly those
///   terms. Note this holds even when the hub holds a version of its own — that hub is `ahead`,
///   an anomaly the SaaS records verbatim and an operator resolves by re-uploading the `.p12`;
///   a 404 would not have fixed it either way.
/// - **Anything else** — refetch when it differs from what this hub holds, in EITHER direction. A
///   hub that somehow ran ahead converges back down by the same rule.
///
/// «Only once» falls out of the comparison: once the refetch lands, the hub holds the announced
/// version and the next heartbeat is a no-op. A refetch that FAILED leaves them different, so the
/// next heartbeat tries again — which is the behaviour that makes this converge at all.
pub fn heartbeat_requires_refetch(local: Option<i64>, announced: Option<i64>) -> bool {
    match announced {
        None | Some(0) => false,
        Some(version) => local != Some(version),
    }
}

/// Does this hub need a certificate at boot? **Only when it holds no delegated one.**
///
/// The obvious alternative — fetch unconditionally on every boot — is what a fleet-wide redeploy
/// turns into a thousand simultaneous requests for the same private key, and what a crash-looping
/// container turns into a hub that throttles itself out of its own allowance. Neither buys
/// anything: a hub that already holds a certificate learns about a rotation from the heartbeat,
/// which runs its first tick immediately at boot anyway.
///
/// What this DOES cover is the case boot exists for: a hub that has just been provisioned (or a
/// demo, which is provisioned exactly the same way — §3.4, no special case) coming up with nothing
/// and needing to be able to invoice.
///
/// A read failure answers `false`: a hub that cannot read its own certificate table is not a hub
/// that should start asking the control plane for private keys.
pub async fn boot_requires_refetch(db: &dyn DatabaseAdapter, hub_id: &str) -> bool {
    matches!(certificate::delegated_version(db, hub_id).await, Ok(None))
}

/// What this hub reports UP about its delegated certificate (ADR-0202 §2.5): `(version, notAfter)`.
///
/// `Some((0, None))` when the hub holds none — an explicit zero, because the Cloud keeps «never
/// reported» (`NULL`) and «holds nothing» (`0`) as different states and only the hub can tell them
/// apart. `None` when the read FAILED, and that is the whole reason this returns an `Option`
/// instead of defaulting: a fabricated `0` would show a healthy hub as one that lost ERPlora's
/// certificate, and would send somebody chasing a rotation that never broke.
pub async fn delegated_certificate_report(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Option<(i64, Option<String>)> {
    match certificate::delegated_version(db, hub_id).await {
        Ok(Some(version)) => {
            // The INSTANT, not the day (`slot_expiry_instant`, hub#318): the fleet panel compares
            // this against the `not_after` the SaaS extracted from the container it custodies, for
            // EQUALITY (ADR-0202 §2.6). A truncated date arrives as midnight and differs from every
            // certificate that does not expire at 00:00:00 — the whole healthy fleet would be
            // flagged «not running our certificate».
            //
            // Read from the container the hub actually holds, so an unreadable `.p12` reports its
            // version with an unknown date rather than lying about either.
            let not_after = certificate::slot_expiry_instant(
                db,
                hub_id,
                certificate::CertificateKind::Delegated,
            )
            .await
            .ok()
            .flatten();
            Some((version, not_after))
        }
        Ok(None) => Some((0, None)),
        Err(_) => None,
    }
}

/// Result of one refetch attempt. Every arm is a normal outcome: none of them stops the hub.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RefetchOutcome {
    /// The trigger fired but nothing had to be done (no rotation, or the hub already has one).
    NotNeeded,
    /// The hourly allowance is spent. Deliberately not an error: the next heartbeat picks it up,
    /// and stopping here is what keeps the control plane's 20/h from being exhausted.
    OutOfBudget,
    /// The control plane answered, and the hub acted on it (installed, or told there is nothing).
    Done(DelegatedCertificateOutcome),
    /// The attempt failed. **The hub keeps the certificate it already had** — the slot is only ever
    /// written by a successful fetch, so a network failure, a 5xx or an unreadable body all leave
    /// it exactly as it was.
    Failed(String),
}

/// One refetch attempt: decide, spend budget, fetch, store. Never returns an error and never
/// panics — the caller is a background task whose failure must not be visible to the till.
///
/// The runtime lock is taken **twice and briefly** (to decide, and to store), never across the
/// network call: it is the same mutex every query and command goes through.
pub async fn refetch_once(
    trigger: RefetchTrigger,
    budget: &RefetchBudget,
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    runtime: &crate::state::SharedRuntime,
    hub_id: &str,
) -> RefetchOutcome {
    let needed = match trigger {
        RefetchTrigger::Boot | RefetchTrigger::GrantSigned => {
            let rt = runtime.read().await;
            boot_requires_refetch(rt.db(), hub_id).await
        }
        RefetchTrigger::Heartbeat { announced } => {
            let local = {
                let rt = runtime.read().await;
                certificate::delegated_version(rt.db(), hub_id)
                    .await
                    .ok()
                    .flatten()
            };
            heartbeat_requires_refetch(local, announced)
        }
        RefetchTrigger::TlsFailure => true,
    };
    if !needed {
        return RefetchOutcome::NotNeeded;
    }
    if !budget.try_spend(Instant::now()) {
        // Not a warning about the certificate: it is the guard doing its job. Logged so a hub that
        // keeps hitting it is visible, because that means a trigger is firing in a loop.
        tracing::warn!(
            ?trigger,
            max_per_hour = MAX_REFETCHES_PER_HOUR,
            "refetch del certificado delegado omitido: presupuesto horario agotado"
        );
        return RefetchOutcome::OutOfBudget;
    }

    let fetched = match fetch_delegated_certificate(http, cloud_base_url, auth).await {
        Ok(fetched) => fetched,
        Err(error) => {
            // The hub keeps whatever it had. `error` never carries the response body (see the
            // module docs), so this line is safe to write.
            tracing::warn!(?trigger, %error, "refetch del certificado delegado fallido");
            return RefetchOutcome::Failed(error);
        }
    };
    let Some(cert) = fetched else {
        tracing::debug!(
            ?trigger,
            "el plano de control no tiene certificado delegado para este hub"
        );
        return RefetchOutcome::Done(DelegatedCertificateOutcome::NotProvisioned);
    };
    let stored = {
        let rt = runtime.read().await;
        store_delegated_certificate(rt.db(), hub_id, &cert).await
    };
    match stored {
        Ok(outcome) => {
            // Version and expiry only — the heartbeat announces both in the clear anyway. Never
            // `cert` itself: its `Debug` is redacted, but the rule is that it does not go near a
            // log line at all.
            tracing::info!(?trigger, ?outcome, "certificado delegado actualizado");
            RefetchOutcome::Done(outcome)
        }
        Err(error) => {
            tracing::warn!(?trigger, %error, "no se pudo guardar el certificado delegado");
            RefetchOutcome::Failed(error)
        }
    }
}

/// **Asks for the certificate the signature just unlocked** (hub#817), off the request path.
///
/// Spawned rather than awaited: the person who signed gets their `201` back straight away, and a
/// control plane that is slow or down must not turn a successful capture into a failed one. Its
/// outcome is deliberately dropped — the grant is archived either way, and the hub converges by the
/// boot and heartbeat triggers if this attempt does not land.
///
/// Spends the SAME hourly budget as the other three (`AppState::certificate_budget`): the control
/// plane counts one total per hub, so a fourth trigger with a budget of its own would be a fourth
/// way to blow the allowance.
pub fn refetch_after_grant(st: &AppState) {
    let Some(auth) = crate::auth::machine_auth(st) else {
        return;
    };
    let (st, hub_id) = (st.clone(), st.hub_id());
    tokio::spawn(async move {
        refetch_once(
            RefetchTrigger::GrantSigned,
            &st.certificate_budget,
            &st.http,
            &st.config.cloud_base_url,
            &auth,
            &st.runtime,
            &hub_id,
        )
        .await;
    });
}

/// Starts the two refetch triggers that need a task of their own: **boot** and **TLS failure**.
/// (The heartbeat one rides the tick that already exists, in `serve`.)
///
/// 🔴 Both go in their own task, never on the boot path. An unreachable control plane must leave a
/// hub that WORKS — degraded, signing with its own certificate or refusing to invoice, but serving
/// — not a hub that never finished starting. Same rule as the declared-blueprint import (hub#406);
/// the seed above it is the deliberate exception, because a broken seed means the hub was
/// misconfigured and starting it would be worse.
///
/// Without a machine token (dev, or a hub that has not enrolled yet) nothing is spawned: there is
/// no credential to ask with, and the endpoint accepts no other.
pub fn spawn_refetch_service(st: &AppState, budget: Arc<RefetchBudget>) {
    let Some(auth) = crate::auth::machine_auth(st) else {
        return;
    };
    let hub_id = st.hub_id();

    // 1) Boot.
    {
        let (st, auth, budget, hub_id) = (st.clone(), auth.clone(), budget.clone(), hub_id.clone());
        tokio::spawn(async move {
            refetch_once(
                RefetchTrigger::Boot,
                &budget,
                &st.http,
                &st.config.cloud_base_url,
                &auth,
                &st.runtime,
                &hub_id,
            )
            .await;
        });
    }

    // 2) TLS failure against the AEAT, raised from inside the `verifactu` engine. One consumer for
    //    the whole process, so a queue drain that fails N records asks once (the signal coalesces)
    //    and this loop turns it into at most one request.
    {
        let st = st.clone();
        tokio::spawn(async move {
            loop {
                RefetchSignal::global().wait().await;
                let Some(auth) = crate::auth::machine_auth(&st) else {
                    continue;
                };
                refetch_once(
                    RefetchTrigger::TlsFailure,
                    &budget,
                    &st.http,
                    &st.config.cloud_base_url,
                    &auth,
                    &st.runtime,
                    &st.hub_id(),
                )
                .await;
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::get;
    use axum::Router;
    use erplora_db::testutil::fresh_db;
    use erplora_db::PgAdapter;
    use erplora_runtime::Runtime;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::{Arc, Mutex};

    /// A real `.p12` is not needed to prove where the bytes go: what matters is that this exact
    /// string never shows up anywhere it should not. Base64 of "DELEGATED-PKCS12".
    const DELEGATED_B64: &str = "REVMRUdBVEVELVBLQ1MxMg==";
    const DELEGATED_PASSWORD: &str = "erplora-delegated-passphrase";
    const OWN_B64: &str = "T1dOLVBLQ1MxMg==";

    fn served_body(version: i64) -> String {
        format!(
            r#"{{"version": {version}, "pkcs12_b64": "{DELEGATED_B64}", "password": "{DELEGATED_PASSWORD}", "not_after": "2028-06-10"}}"#
        )
    }

    /// A cloud stub answering the fiscal-certificate endpoint with a fixed status and body, and
    /// recording the headers it was asked with. Returns `(base_url, captured_headers, shutdown)`.
    async fn cloud_stub(
        status: StatusCode,
        body: impl Into<String>,
    ) -> (
        String,
        Arc<Mutex<Option<HeaderMap>>>,
        tokio::task::JoinHandle<()>,
    ) {
        type Seen = Arc<Mutex<Option<HeaderMap>>>;
        let seen: Seen = Arc::new(Mutex::new(None));
        let body = body.into();
        let app = Router::new().route(
            "/api/v1/hub/device/fiscal/certificate/",
            get({
                let seen = seen.clone();
                move |headers: HeaderMap| {
                    *seen.lock().unwrap() = Some(headers);
                    let body = body.clone();
                    async move { (status, body) }
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (format!("http://{address}"), seen, server)
    }

    fn machine_auth() -> Auth {
        Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "machine-tok".into(),
        }
    }

    async fn db_ready() -> PgAdapter {
        let db = fresh_db().await;
        erplora_runtime::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        erplora_runtime::identity::ensure_tables(&db).await.unwrap();
        erplora_runtime::system_migrations::apply(&db, "hub-test")
            .await
            .unwrap();
        db
    }

    /// `HUB_SECRETS_KEY` for the tests that actually store something (base64 of 32 zero-ish bytes).
    ///
    /// Written exactly ONCE for the whole binary, and never removed: no test here asserts its
    /// absence (the fail-closed path is covered where it belongs, in the runtime's own tests), so
    /// there is no state another test could observe. Every reader goes through this function, and
    /// `Once` makes them all wait for the write to finish before any of them reads.
    fn ensure_master_key() {
        static SET: std::sync::Once = std::sync::Once::new();
        SET.call_once(|| {
            // SAFETY: the only write in this binary, serialised by `Once`, and it happens-before
            // every read because every reader calls this first.
            unsafe { std::env::set_var("HUB_SECRETS_KEY", "A".repeat(43) + "=") };
        });
    }

    // ── Security first: the key must not leak into an error, a log or the response path ───────

    /// 🔒 **An unreadable response must not be quoted back.** The body of THIS endpoint is the
    /// private key: the one moment you most want to print «what did the SaaS actually send me» is
    /// the one moment you must not. The error may name the URL and the status, nothing else.
    #[tokio::test]
    async fn a_malformed_response_never_quotes_the_body_that_holds_the_key() {
        // Valid JSON, wrong shape — the tempting branch is «parse failed, here is what I got».
        let (base, _seen, server) = cloud_stub(
            StatusCode::OK,
            r#"{"pkcs12_b64": "REVMRUdBVEVELVBLQ1MxMg==", "password": "erplora-delegated-passphrase"}"#,
        )
        .await;

        let error = fetch_delegated_certificate(&reqwest::Client::new(), &base, &machine_auth())
            .await
            .unwrap_err();

        assert!(
            !error.contains(DELEGATED_B64),
            "el error arrastra el contenedor PKCS#12: {error}"
        );
        assert!(
            !error.contains(DELEGATED_PASSWORD),
            "el error arrastra la contraseña: {error}"
        );
        server.abort();
    }

    /// 🔒 Same rule on a server error, where a body is even more likely to be echoed into a log.
    #[tokio::test]
    async fn a_server_error_never_quotes_the_body_either() {
        let (base, _seen, server) = cloud_stub(
            StatusCode::INTERNAL_SERVER_ERROR,
            r#"{"detail": "boom", "pkcs12_b64": "REVMRUdBVEVELVBLQ1MxMg==", "password": "erplora-delegated-passphrase"}"#,
        )
        .await;

        let error = fetch_delegated_certificate(&reqwest::Client::new(), &base, &machine_auth())
            .await
            .unwrap_err();

        assert!(!error.contains(DELEGATED_B64), "{error}");
        assert!(!error.contains(DELEGATED_PASSWORD), "{error}");
        // Y sigue siendo diagnosticable: el status es lo que dice si reintentar.
        assert!(
            error.contains("500"),
            "el error debería nombrar el status: {error}"
        );
        server.abort();
    }

    /// 🔒 **Nothing of the `.p12` reaches the logs**, on the happy path — the one that runs on every
    /// hub, every rotation. Captures the whole `tracing` output of a real install and greps it.
    #[tokio::test]
    async fn installing_the_certificate_writes_nothing_secret_to_the_logs() {
        ensure_master_key();
        let db = db_ready().await;
        let body = served_body(4);
        let (base, _seen, server) = cloud_stub(StatusCode::OK, body).await;

        let captured = Arc::new(Mutex::new(Vec::<u8>::new()));
        let writer = CapturingWriter(captured.clone());
        let subscriber = tracing_subscriber::fmt()
            .with_writer(writer)
            .with_max_level(tracing::Level::TRACE)
            .finish();

        let outcome = {
            let _guard = tracing::subscriber::set_default(subscriber);
            install_delegated_certificate(
                &reqwest::Client::new(),
                &base,
                &machine_auth(),
                &db,
                "hub-test",
            )
            .await
            .unwrap()
        };
        assert!(matches!(
            outcome,
            DelegatedCertificateOutcome::Installed { version: 4, .. }
        ));

        let logs = String::from_utf8_lossy(&captured.lock().unwrap().clone()).into_owned();
        assert!(
            !logs.contains(DELEGATED_B64),
            "el contenedor PKCS#12 ha llegado a los logs: {logs}"
        );
        assert!(
            !logs.contains(DELEGATED_PASSWORD),
            "la contraseña ha llegado a los logs: {logs}"
        );
        // Ni un fragmento: una traza que imprimiese el principio de la clave seguiría siendo una fuga.
        for fragment in ["REVMRUdB", "erplora-delegated", "delegated-passphrase"] {
            assert!(
                !logs.contains(fragment),
                "fuga del fragmento {fragment:?}: {logs}"
            );
        }
        server.abort();
    }

    /// A `tracing` writer that keeps everything in memory so a test can grep it.
    #[derive(Clone)]
    struct CapturingWriter(Arc<Mutex<Vec<u8>>>);

    impl std::io::Write for CapturingWriter {
        fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(buf);
            Ok(buf.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for CapturingWriter {
        type Writer = CapturingWriter;
        fn make_writer(&'a self) -> Self::Writer {
            self.clone()
        }
    }

    /// 🔒 The MACHINE credential goes out and the user's JWT does not — the SaaS refuses anything
    /// else, and a browser-borne token must never be what asks for a private key.
    #[tokio::test]
    async fn the_request_carries_the_machine_credential_and_no_user_jwt() {
        let body = served_body(2);
        let (base, seen, server) = cloud_stub(StatusCode::OK, body).await;

        fetch_delegated_certificate(&reqwest::Client::new(), &base, &machine_auth())
            .await
            .unwrap()
            .expect("el certificado servido");

        let headers = seen.lock().unwrap().clone().expect("cabeceras capturadas");
        assert_eq!(headers["x-hub-id"], "hub-test");
        assert_eq!(headers["x-hub-token"], "machine-tok");
        assert!(!headers.contains_key("authorization"));
        server.abort();
    }

    // ── A 404 is an answer, not a breakage ────────────────────────────────────────────────────

    /// **404 `no_delegated_certificate` must not break the hub.** Most hubs sign with their own
    /// certificate and will never be delegated one; turning that into an error would put a permanent
    /// red into every one of them.
    #[tokio::test]
    async fn a_404_is_reported_as_not_provisioned_and_not_as_an_error() {
        ensure_master_key();
        let db = db_ready().await;
        let (base, _seen, server) = cloud_stub(
            StatusCode::NOT_FOUND,
            r#"{"detail": "no_delegated_certificate"}"#,
        )
        .await;

        let outcome = install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();

        assert_eq!(outcome, DelegatedCertificateOutcome::NotProvisioned);
        server.abort();
    }

    /// …and the hub **keeps its own certificate**. This is the case that matters in production: the
    /// customer uploaded their `.p12`, the control plane has nothing to add, and the fetch must be a
    /// no-op — not something that clears a slot or blocks invoicing.
    #[tokio::test]
    async fn a_404_leaves_a_hub_that_has_its_own_certificate_untouched() {
        ensure_master_key();
        let db = db_ready().await;

        // El hub llega con SU certificado puesto (lo subió su dueño en Ajustes → Negocio).
        seed_own_certificate(&db).await;
        assert_eq!(
            certificate::status(&db, "hub-test").await.unwrap()["present"],
            serde_json::json!(true)
        );

        let (base, _seen, server) = cloud_stub(
            StatusCode::NOT_FOUND,
            r#"{"detail": "no_delegated_certificate"}"#,
        )
        .await;
        let outcome = install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();

        assert_eq!(outcome, DelegatedCertificateOutcome::NotProvisioned);
        assert_eq!(
            certificate::status(&db, "hub-test").await.unwrap()["present"],
            serde_json::json!(true),
            "un 404 no puede quitarle al hub el certificado que ya tenía"
        );
        assert_eq!(
            certificate::active_kind(&db, "hub-test").await.unwrap(),
            Some(certificate::CertificateKind::Own)
        );
        server.abort();
    }

    /// Seeds the own slot the way the business screen would, but without a real `.p12`.
    async fn seed_own_certificate(db: &PgAdapter) {
        use erplora_db::DatabaseAdapter as _;
        db.execute_batch(&format!(
            "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES ('hub-test', 'own', '{OWN_B64}', 'pw-own', '2026-08-07T00:00:00Z', 'hub_user:admin');"
        ))
        .await
        .unwrap();
    }

    // ── The happy path: stored, encrypted, under the version that was served ──────────────────

    /// 🔒 What arrives over the wire lands **encrypted** in the `delegated` slot, under the version
    /// the SaaS served — and, being ERPlora's key, it still does not travel in an export.
    #[tokio::test]
    async fn the_served_certificate_is_stored_encrypted_under_the_served_version() {
        ensure_master_key();
        let db = db_ready().await;
        let body = served_body(4);
        let (base, _seen, server) = cloud_stub(StatusCode::OK, body).await;

        let outcome = install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();

        assert!(matches!(
            outcome,
            DelegatedCertificateOutcome::Installed { version: 4, .. }
        ));
        assert_eq!(
            certificate::delegated_version(&db, "hub-test")
                .await
                .unwrap(),
            Some(4)
        );
        assert_eq!(
            certificate::active_kind(&db, "hub-test").await.unwrap(),
            Some(certificate::CertificateKind::Delegated)
        );
        // En la BD, cifrado: un `pg_dump` no lleva la clave de ERPlora.
        let (stored_b64, stored_password) = raw_delegated_row(&db).await;
        assert!(
            stored_b64.starts_with("v1:"),
            "no está cifrado: {stored_b64}"
        );
        assert!(
            stored_password.starts_with("v1:"),
            "no está cifrada: {stored_password}"
        );
        assert!(!stored_b64.contains(DELEGATED_B64));
        assert!(!stored_password.contains(DELEGATED_PASSWORD));
        // Descifrado, es EXACTAMENTE lo servido y en su columna: el contenedor en `pkcs12_b64` y la
        // contraseña en `password`. Intercambiarlos guardaría un `.p12` que ya no abre nunca — y el
        // hub no lo descubriría hasta el primer envío a la AEAT.
        assert_eq!(decrypt(&stored_b64), DELEGATED_B64);
        assert_eq!(decrypt(&stored_password), DELEGATED_PASSWORD);
        // Y la guarda de hub#316 sigue en pie por esta vía nueva.
        assert_eq!(
            certificate::exportable_der_bytes(&db, "hub-test")
                .await
                .unwrap(),
            None,
            "la clave privada de ERPlora no sale del hub"
        );
        server.abort();
    }

    /// `(pkcs12_b64, password)` of the delegated row exactly as they sit in the database — what
    /// somebody holding a `pg_dump` would get.
    async fn raw_delegated_row(db: &PgAdapter) -> (String, String) {
        use erplora_db::DatabaseAdapter as _;
        let res = db
            .query(
                "SELECT pkcs12_b64, password FROM _hub_certificate \
                 WHERE hub_id = 'hub-test' AND kind = 'delegated'",
                &erplora_db::Params::new(),
            )
            .await
            .unwrap();
        let row = &res.rows[0];
        (
            row["pkcs12_b64"].as_str().unwrap().to_string(),
            row["password"].as_str().unwrap().to_string(),
        )
    }

    /// Undoes the at-rest encryption with the same master key the hub used, so a test can assert
    /// WHICH value landed in which column and not merely that both look encrypted.
    fn decrypt(stored: &str) -> String {
        let key = erplora_runtime::secret_box::master_key_from_env()
            .unwrap()
            .expect("HUB_SECRETS_KEY");
        erplora_runtime::secret_box::decrypt_or_legacy(Some(&key), stored).unwrap()
    }

    /// A **real** self-signed PKCS#12 (`CN=ERPlora delegated test`, `notAfter` 2036-01-01, password
    /// `delegated-pw`), so a test can assert a DATE and not merely a `None`. Generated once with
    /// `openssl req -x509` + `openssl pkcs12 -export`; it holds no secret worth protecting.
    const REAL_P12_B64: &str = include_str!("../tests/fixtures/delegated_test_cert.p12.b64");
    const REAL_P12_PASSWORD: &str = "delegated-pw";
    const REAL_P12_NOT_AFTER: &str = "2036-01-01";

    /// **The reported expiry describes the DELEGATED slot, even when the own certificate signs.**
    ///
    /// End-to-end half of the runtime's `the_delegated_expiry_is_reported_even_when_the_own_
    /// certificate_signs`. The heartbeat's `reported_cert_not_after` is the delegated slot's date and
    /// only that (ADR-0202 §2.5): the SaaS compares it against the `not_after` of the `.p12` it
    /// custodies, so a hub that answered with its OWN certificate's date would trip the mismatch
    /// alarm while being perfectly healthy.
    ///
    /// The two slots are deliberately asymmetric — the delegated one is a real container and the own
    /// one is not — because that is what makes «which slot did you read?» observable.
    #[tokio::test]
    async fn the_reported_expiry_is_the_delegated_slots_even_when_the_own_certificate_signs() {
        ensure_master_key();
        let db = db_ready().await;
        seed_own_certificate(&db).await; // no es un `.p12` legible, y además MANDA para firmar

        let body = format!(
            r#"{{"version": 9, "pkcs12_b64": "{}", "password": "{REAL_P12_PASSWORD}"}}"#,
            REAL_P12_B64.trim()
        );
        let (base, _seen, server) = cloud_stub(StatusCode::OK, body).await;

        let outcome = install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();

        assert_eq!(
            outcome,
            DelegatedCertificateOutcome::Installed {
                version: 9,
                not_after: Some(REAL_P12_NOT_AFTER.to_string()),
            }
        );
        // El que firma sigue siendo el PROPIO (regla de hub#316) — y su fecha no se sabe leer, que
        // es justo lo que demuestra que la reportada NO sale de ahí.
        assert_eq!(
            certificate::active_kind(&db, "hub-test").await.unwrap(),
            Some(certificate::CertificateKind::Own)
        );
        assert_eq!(
            certificate::expiry(&db, "hub-test").await.ok().flatten(),
            None
        );
        server.abort();
    }

    // ═══ The three refetch triggers (ADR-0202 §2 point 4 — hub#318) ═══════════════════════════

    /// A cloud stub that COUNTS how many times the certificate endpoint was asked. The count is
    /// the whole point: this issue is about how often a private key is requested, not about what
    /// comes back.
    async fn counting_stub(
        status: StatusCode,
        body: impl Into<String>,
    ) -> (String, Arc<AtomicUsize>, tokio::task::JoinHandle<()>) {
        let hits = Arc::new(AtomicUsize::new(0));
        let body = body.into();
        let app = Router::new().route(
            "/api/v1/hub/device/fiscal/certificate/",
            get({
                let hits = hits.clone();
                move || {
                    hits.fetch_add(1, Ordering::SeqCst);
                    let body = body.clone();
                    async move { (status, body) }
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (format!("http://{address}"), hits, server)
    }

    /// The database wrapped the way the production path sees it: behind the runtime's lock.
    fn runtime_of(db: PgAdapter) -> crate::state::SharedRuntime {
        Arc::new(tokio::sync::RwLock::new(Runtime::with_hub_id(
            Box::new(db),
            "hub-test",
        )))
    }

    async fn local_version(runtime: &crate::state::SharedRuntime) -> Option<i64> {
        let rt = runtime.read().await;
        certificate::delegated_version(rt.db(), "hub-test")
            .await
            .unwrap()
    }

    async fn refetch(
        trigger: RefetchTrigger,
        budget: &RefetchBudget,
        base: &str,
        runtime: &crate::state::SharedRuntime,
    ) -> RefetchOutcome {
        refetch_once(
            trigger,
            budget,
            &reqwest::Client::new(),
            base,
            &machine_auth(),
            runtime,
            "hub-test",
        )
        .await
    }

    // ── Trigger 2: the heartbeat, which is what carries a rotation ────────────────────────────

    /// **A new version fires the refetch, and fires it ONCE.** Convergence has to be self-limiting:
    /// once the rotation lands the hub holds the announced version, so the next heartbeat asks for
    /// nothing. A trigger that kept firing would spend the control plane's 20/h allowance on a hub
    /// that is already up to date.
    #[tokio::test]
    async fn a_new_version_in_the_heartbeat_refetches_exactly_once() {
        ensure_master_key();
        let db = db_ready().await;
        certificate::set_delegated(&db, "hub-test", DELEGATED_B64, "pw-4", 4, None)
            .await
            .unwrap();
        let runtime = runtime_of(db);
        let (base, hits, server) = counting_stub(StatusCode::OK, served_body(5)).await;
        let budget = RefetchBudget::hourly();

        let first = refetch(
            RefetchTrigger::Heartbeat { announced: Some(5) },
            &budget,
            &base,
            &runtime,
        )
        .await;
        assert!(matches!(
            first,
            RefetchOutcome::Done(DelegatedCertificateOutcome::Installed { version: 5, .. })
        ));
        assert_eq!(local_version(&runtime).await, Some(5));
        assert_eq!(hits.load(Ordering::SeqCst), 1);

        // Mismo anuncio, ya instalado: ni una petición más.
        let second = refetch(
            RefetchTrigger::Heartbeat { announced: Some(5) },
            &budget,
            &base,
            &runtime,
        )
        .await;
        assert_eq!(second, RefetchOutcome::NotNeeded);
        assert_eq!(
            hits.load(Ordering::SeqCst),
            1,
            "un hub al día no vuelve a pedir la clave privada"
        );
        server.abort();
    }

    /// 🔒 **`0` means «there is nothing to fetch», so the hub must not ask.** The GET would answer
    /// 404 `no_delegated_certificate` (§2.5), and this is the state MOST of the fleet is in — every
    /// hub that signs with its own certificate. Asking anyway would be a guaranteed-useless request
    /// for a private key, once per heartbeat, forever.
    #[tokio::test]
    async fn an_announced_zero_never_asks_for_a_certificate() {
        ensure_master_key();
        let db = db_ready().await;
        let runtime = runtime_of(db);
        let (base, hits, server) = counting_stub(StatusCode::OK, served_body(1)).await;

        let outcome = refetch(
            RefetchTrigger::Heartbeat { announced: Some(0) },
            &RefetchBudget::hourly(),
            &base,
            &runtime,
        )
        .await;

        assert_eq!(outcome, RefetchOutcome::NotNeeded);
        assert_eq!(hits.load(Ordering::SeqCst), 0);
        server.abort();
    }

    /// The whole rule, without a database: silence is not news, `0` is «nothing to fetch», and a
    /// difference in EITHER direction converges.
    #[test]
    fn the_heartbeat_rule_reads_silence_zero_and_drift_correctly() {
        // Nada anunciado (SaaS anterior a saas#1126, o un cuerpo ilegible).
        assert!(!heartbeat_requires_refetch(None, None));
        assert!(!heartbeat_requires_refetch(Some(4), None));
        // `0` = el plano de control no ha subido nada: el GET daría 404.
        assert!(!heartbeat_requires_refetch(None, Some(0)));
        assert!(!heartbeat_requires_refetch(Some(4), Some(0)));
        // Una rotación.
        assert!(heartbeat_requires_refetch(Some(4), Some(5)));
        // Un hub que nunca tuvo ninguno.
        assert!(heartbeat_requires_refetch(None, Some(5)));
        // Ya al día.
        assert!(!heartbeat_requires_refetch(Some(5), Some(5)));
        // Y un hub POR DELANTE converge hacia abajo (§2.5: la anomalía se registra, no se recorta).
        assert!(heartbeat_requires_refetch(Some(9), Some(5)));
    }

    // ── Trigger 1: boot ───────────────────────────────────────────────────────────────────────

    /// Boot covers the hub this exists for: freshly provisioned (a demo is provisioned the same
    /// way — §3.4, no special case) and holding nothing.
    #[tokio::test]
    async fn a_hub_that_holds_nothing_fetches_at_boot() {
        ensure_master_key();
        let db = db_ready().await;
        let runtime = runtime_of(db);
        let (base, hits, server) = counting_stub(StatusCode::OK, served_body(4)).await;

        let outcome = refetch(
            RefetchTrigger::Boot,
            &RefetchBudget::hourly(),
            &base,
            &runtime,
        )
        .await;

        assert!(matches!(
            outcome,
            RefetchOutcome::Done(DelegatedCertificateOutcome::Installed { version: 4, .. })
        ));
        assert_eq!(hits.load(Ordering::SeqCst), 1);
        server.abort();
    }

    /// 🔒 **A hub that already holds one does NOT ask at boot.** Every hub in the fleet reboots at
    /// the same instant on a redeploy; fetching unconditionally would turn that into a thousand
    /// simultaneous requests for the same private key — and a crash-looping container into a hub
    /// that throttles itself out of its own allowance. Rotations come down the heartbeat, whose
    /// first tick fires at boot anyway.
    #[tokio::test]
    async fn a_hub_that_already_holds_a_certificate_does_not_ask_at_boot() {
        ensure_master_key();
        let db = db_ready().await;
        certificate::set_delegated(&db, "hub-test", DELEGATED_B64, "pw-4", 4, None)
            .await
            .unwrap();
        let runtime = runtime_of(db);
        let (base, hits, server) = counting_stub(StatusCode::OK, served_body(4)).await;

        let outcome = refetch(
            RefetchTrigger::Boot,
            &RefetchBudget::hourly(),
            &base,
            &runtime,
        )
        .await;

        assert_eq!(outcome, RefetchOutcome::NotNeeded);
        assert_eq!(hits.load(Ordering::SeqCst), 0);
        server.abort();
    }

    /// A hub with only its OWN certificate still has nothing from ERPlora, so boot does ask: the
    /// two slots are independent (hub#316) and the delegated one is the fallback that keeps the
    /// hub invoicing if the customer ever deletes theirs.
    #[tokio::test]
    async fn owning_a_business_certificate_does_not_count_as_holding_the_delegated_one() {
        ensure_master_key();
        let db = db_ready().await;
        seed_own_certificate(&db).await;
        assert!(boot_requires_refetch(&db, "hub-test").await);
    }

    // ── Trigger 3: a TLS failure against the AEAT, and the budget that bounds it ───────────────

    /// 🔒 **The budget is a safety property, not tidiness.** A revoked certificate fails the
    /// handshake for every record the contingency queue drains, and each of those is a trigger. If
    /// they all became requests, the hub would blow through the control plane's 20/h allowance and
    /// the NEXT request — the one that would have installed a working certificate — would be the
    /// one that gets throttled. The hub would have locked itself out of its own fix.
    #[tokio::test]
    async fn a_storm_of_tls_failures_cannot_exhaust_the_control_planes_quota() {
        ensure_master_key();
        let db = db_ready().await;
        let runtime = runtime_of(db);
        let (base, hits, server) = counting_stub(StatusCode::OK, served_body(4)).await;
        let budget = RefetchBudget::hourly();

        let mut refused = 0;
        for _ in 0..100 {
            if refetch(RefetchTrigger::TlsFailure, &budget, &base, &runtime).await
                == RefetchOutcome::OutOfBudget
            {
                refused += 1;
            }
        }

        let asked = hits.load(Ordering::SeqCst);
        assert_eq!(asked, MAX_REFETCHES_PER_HOUR, "el presupuesto es el techo");
        assert!(
            asked < CONTROL_PLANE_QUOTA_PER_HOUR,
            "el hub NUNCA puede ser quien agota su propia cuota: {asked} de {CONTROL_PLANE_QUOTA_PER_HOUR}"
        );
        assert_eq!(refused, 100 - MAX_REFETCHES_PER_HOUR);
        server.abort();
    }

    /// The window ROLLS: budget spent an hour ago is budget again. A hub whose certificate breaks
    /// twice in a day must be able to fix itself twice.
    #[test]
    fn the_budget_window_rolls_instead_of_resetting_on_the_hour() {
        let budget = RefetchBudget::new(2, Duration::from_secs(60));
        let start = Instant::now();
        assert!(budget.try_spend(start));
        assert!(budget.try_spend(start + Duration::from_secs(1)));
        assert!(!budget.try_spend(start + Duration::from_secs(2)), "agotado");
        // Justo antes de que expire el primero: sigue agotado.
        assert!(!budget.try_spend(start + Duration::from_secs(59)));
        // Cumplida la ventana del PRIMERO vuelve a haber sitio, y solo para uno: el segundo se
        // gastó un segundo más tarde y cumple su ventana un segundo más tarde. Eso es lo que
        // distingue una ventana deslizante de un cubo horario, que los liberaría a la vez.
        assert!(budget.try_spend(start + Duration::from_secs(60)));
        assert!(!budget.try_spend(start + Duration::from_secs(60)));
        // Y al vencer el segundo, otro más.
        assert!(budget.try_spend(start + Duration::from_secs(61)));
    }

    // ── Failure: whatever happens, the hub keeps its certificate and keeps running ─────────────

    /// 🔒 **A failed refetch must never leave the hub without a certificate.** The slot is only
    /// written by a fetch that succeeded, so a 5xx leaves the hub signing exactly as it was — and
    /// the function returns rather than propagating, because its caller is a background task and a
    /// broken control plane is not a reason to stop selling.
    #[tokio::test]
    async fn a_server_error_leaves_the_hub_with_the_certificate_it_had() {
        ensure_master_key();
        let db = db_ready().await;
        certificate::set_delegated(&db, "hub-test", DELEGATED_B64, "pw-4", 4, None)
            .await
            .unwrap();
        let runtime = runtime_of(db);
        let (base, _hits, server) = counting_stub(StatusCode::INTERNAL_SERVER_ERROR, "boom").await;

        let outcome = refetch(
            RefetchTrigger::Heartbeat { announced: Some(5) },
            &RefetchBudget::hourly(),
            &base,
            &runtime,
        )
        .await;

        assert!(matches!(outcome, RefetchOutcome::Failed(_)));
        assert_eq!(local_version(&runtime).await, Some(4), "sigue con el suyo");
        {
            let rt = runtime.read().await;
            assert_eq!(
                certificate::active_kind(rt.db(), "hub-test").await.unwrap(),
                Some(certificate::CertificateKind::Delegated),
                "y sigue pudiendo firmar"
            );
        }
        server.abort();
    }

    /// …and the same when the control plane is not reachable at all. This is the one that happens
    /// in real life: a hub behind a till in a shop whose internet dropped.
    #[tokio::test]
    async fn an_unreachable_control_plane_leaves_the_hub_with_the_certificate_it_had() {
        ensure_master_key();
        let db = db_ready().await;
        certificate::set_delegated(&db, "hub-test", DELEGATED_B64, "pw-4", 4, None)
            .await
            .unwrap();
        let runtime = runtime_of(db);
        // Puerto cerrado: nada escucha ahí.
        let outcome = refetch(
            RefetchTrigger::TlsFailure,
            &RefetchBudget::hourly(),
            "http://127.0.0.1:1",
            &runtime,
        )
        .await;

        assert!(matches!(outcome, RefetchOutcome::Failed(_)));
        assert_eq!(local_version(&runtime).await, Some(4));
    }

    /// A 404 is an answer, not a failure — through the refetch path too. Most hubs will never be
    /// delegated a certificate, and this is the shape their every trigger takes.
    #[tokio::test]
    async fn a_404_through_the_refetch_path_is_not_a_failure() {
        ensure_master_key();
        let db = db_ready().await;
        let runtime = runtime_of(db);
        let (base, _hits, server) = counting_stub(
            StatusCode::NOT_FOUND,
            r#"{"detail": "no_delegated_certificate"}"#,
        )
        .await;

        let outcome = refetch(
            RefetchTrigger::Boot,
            &RefetchBudget::hourly(),
            &base,
            &runtime,
        )
        .await;

        assert_eq!(
            outcome,
            RefetchOutcome::Done(DelegatedCertificateOutcome::NotProvisioned)
        );
        server.abort();
    }

    // ── Nothing of the key reaches the logs, on the paths THIS issue added ────────────────────

    /// 🔒 **The failure path is the one that logs the response.** `refetch_once` writes the error
    /// into a `tracing::warn!`, and the error of this endpoint is about a body that holds a private
    /// key. A 5xx whose body carries the container and the passphrase must come out of the log with
    /// neither.
    #[tokio::test]
    async fn a_failed_refetch_writes_nothing_secret_to_the_logs() {
        ensure_master_key();
        let db = db_ready().await;
        let runtime = runtime_of(db);
        let (base, _hits, server) = counting_stub(
            StatusCode::INTERNAL_SERVER_ERROR,
            format!(
                r#"{{"detail": "boom", "pkcs12_b64": "{DELEGATED_B64}", "password": "{DELEGATED_PASSWORD}"}}"#
            ),
        )
        .await;

        let logs = capture_logs(|| async {
            refetch(
                RefetchTrigger::Boot,
                &RefetchBudget::hourly(),
                &base,
                &runtime,
            )
            .await
        })
        .await;

        assert!(!logs.contains(DELEGATED_B64), "fuga del contenedor: {logs}");
        assert!(
            !logs.contains(DELEGATED_PASSWORD),
            "fuga de la contraseña: {logs}"
        );
        for fragment in ["REVMRUdB", "erplora-delegated", "delegated-passphrase"] {
            assert!(
                !logs.contains(fragment),
                "fuga del fragmento {fragment:?}: {logs}"
            );
        }
        // Y sigue siendo diagnosticable: se ve QUÉ disparador y que hubo un 500.
        assert!(
            logs.contains("Boot"),
            "el log debería nombrar el disparador: {logs}"
        );
        assert!(
            logs.contains("500"),
            "el log debería nombrar el status: {logs}"
        );
        server.abort();
    }

    /// 🔒 Same on the path that succeeds — the one that runs on every hub, every rotation, and the
    /// only one that has the decrypted container in hand while it writes a log line.
    #[tokio::test]
    async fn a_successful_refetch_writes_nothing_secret_to_the_logs() {
        ensure_master_key();
        let db = db_ready().await;
        let runtime = runtime_of(db);
        let (base, _hits, server) = counting_stub(StatusCode::OK, served_body(7)).await;

        let logs = capture_logs(|| async {
            refetch(
                RefetchTrigger::Boot,
                &RefetchBudget::hourly(),
                &base,
                &runtime,
            )
            .await
        })
        .await;

        assert!(!logs.contains(DELEGATED_B64), "fuga del contenedor: {logs}");
        assert!(
            !logs.contains(DELEGATED_PASSWORD),
            "fuga de la contraseña: {logs}"
        );
        // La versión sí: no es secreta (el heartbeat la anuncia en claro) y es lo que se diagnostica.
        assert!(
            logs.contains('7'),
            "el log debería decir la versión: {logs}"
        );
        server.abort();
    }

    /// Runs `body` with every `tracing` event captured, and returns what was written.
    async fn capture_logs<F, Fut, T>(body: F) -> String
    where
        F: FnOnce() -> Fut,
        Fut: std::future::Future<Output = T>,
    {
        let captured = Arc::new(Mutex::new(Vec::<u8>::new()));
        let subscriber = tracing_subscriber::fmt()
            .with_writer(CapturingWriter(captured.clone()))
            .with_max_level(tracing::Level::TRACE)
            .finish();
        {
            let _guard = tracing::subscriber::set_default(subscriber);
            body().await;
        }
        let logs = captured.lock().unwrap().clone();
        String::from_utf8_lossy(&logs).into_owned()
    }

    // ── What the hub REPORTS up (ADR-0202 §2.5) ───────────────────────────────────────────────

    /// A hub that holds nothing says so with an explicit `0`. The Cloud keeps `NULL` («never
    /// reported») and `0` («holds nothing») apart, and only the hub can tell them apart.
    #[tokio::test]
    async fn a_hub_with_no_delegated_certificate_reports_version_zero() {
        ensure_master_key();
        let db = db_ready().await;
        assert_eq!(
            delegated_certificate_report(&db, "hub-test").await,
            Some((0, None))
        );
    }

    /// **And a hub with only its OWN certificate reports `0` too** — not the version of anything
    /// else. The pair describes the DELEGATED slot and only that (§2.5): the Cloud compares it
    /// against the `.p12` it custodies, so borrowing a number from the other slot would light up
    /// the mismatch alarm on a perfectly healthy hub.
    #[tokio::test]
    async fn a_hub_with_only_its_own_certificate_still_reports_zero() {
        ensure_master_key();
        let db = db_ready().await;
        seed_own_certificate(&db).await;
        assert_eq!(
            delegated_certificate_report(&db, "hub-test").await,
            Some((0, None))
        );
    }

    /// With a real container installed, both halves of the pair describe it: the version served
    /// and the date read back from the bytes the hub actually holds.
    ///
    /// The hub ALSO has its own certificate here, and that is the point: the own slot is the one
    /// that signs (hub#316) and the one whose date is unreadable, so a reader that resolved by
    /// «active slot» would answer `None` and the Cloud's mismatch alarm would fire on a healthy
    /// hub. The pair describes the DELEGATED slot, always (§2.5, and the defect hub#317 found).
    #[tokio::test]
    async fn the_report_carries_the_version_and_the_expiry_of_the_stored_container() {
        ensure_master_key();
        let db = db_ready().await;
        seed_own_certificate(&db).await; // manda para firmar, y no es un `.p12` legible
        certificate::set_delegated(
            &db,
            "hub-test",
            REAL_P12_B64.trim(),
            REAL_P12_PASSWORD,
            9,
            None,
        )
        .await
        .unwrap();
        assert_eq!(
            certificate::active_kind(&db, "hub-test").await.unwrap(),
            Some(certificate::CertificateKind::Own)
        );
        let (version, not_after) = delegated_certificate_report(&db, "hub-test")
            .await
            .expect("el hub tiene delegado, así que reporta");
        assert_eq!(version, 9);
        // 🔒 Un INSTANTE, no un día: el panel de flota lo compara por IGUALDAD contra el
        // `not_after` que el SaaS extrajo del contenedor que custodia
        // (`x509_cert.not_valid_after_utc`). Reportar la fecha pelada la convertiría en medianoche
        // y marcaría «no está firmando con nuestro certificado» a TODA la flota sana.
        let not_after = not_after.expect("el contenedor es real, tiene fecha");
        assert!(
            not_after.starts_with(&format!("{REAL_P12_NOT_AFTER}T")),
            "no es el instante del contenedor: {not_after}"
        );
        assert!(not_after.ends_with('Z'), "tiene que ser UTC: {not_after}");
    }

    /// 🔒 **A read failure reports NOTHING, never a zero.** The Cloud keeps `NULL` and `0` apart,
    /// and a fabricated `0` would show a hub that is signing perfectly well as one that lost
    /// ERPlora's certificate — sending somebody to chase a rotation that never broke, and
    /// (§2.5) wiping the expiry it had on record.
    #[tokio::test]
    async fn a_hub_that_cannot_read_its_certificate_table_reports_nothing() {
        ensure_master_key();
        let db = db_ready().await;
        db.execute_batch("DROP TABLE _hub_certificate;")
            .await
            .unwrap();
        assert_eq!(delegated_certificate_report(&db, "hub-test").await, None);
        // Y por el mismo motivo tampoco sale a pedir una clave privada al arrancar.
        assert!(!boot_requires_refetch(&db, "hub-test").await);
    }

    /// A rotation replaces bytes AND number together, so the hub never reports a version whose bytes
    /// it does not hold (ADR-0202 §2.5 — that is what the fleet panel counts).
    #[tokio::test]
    async fn a_rotation_moves_the_bytes_and_the_version_together() {
        ensure_master_key();
        let db = db_ready().await;

        let first = served_body(4);
        let (base, _seen, server) = cloud_stub(StatusCode::OK, first).await;
        install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();
        assert_eq!(
            certificate::delegated_version(&db, "hub-test")
                .await
                .unwrap(),
            Some(4)
        );
        server.abort();

        let rotated = r#"{"version": 5, "pkcs12_b64": "Uk9UQVRFRC1QS0NTMTI=", "password": "pw-5"}"#;
        let (base, _seen, server) = cloud_stub(StatusCode::OK, rotated).await;
        install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();
        assert_eq!(
            certificate::delegated_version(&db, "hub-test")
                .await
                .unwrap(),
            Some(5)
        );
        server.abort();
    }
}
