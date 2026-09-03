//! **Enrolling this hub's machine identity at the fiscal ingress, with nobody in front of it**
//! (hub#1457, ADR-0419/0433).
//!
//! The private key is born on the hub and never leaves it (ADR-0320): what travels is a CSR, and
//! what comes back is a certificate an operator signed with the internal CA, which is **offline**
//! and cannot live in the SaaS. Until now both legs were a human's: somebody pulled the CSR out of
//! `POST /api/business/gateway-identity/csr` and pushed the signed certificate back in through
//! `PUT …/certificate`. That works with an operator watching one hub; it does not scale to a
//! fleet.
//!
//! This module is the door that replaces the human: it files the CSR in the hub's legal-document
//! file at the control plane and collects the certificate once a person has approved it — with the
//! **machine credential**, which is a secret of this runtime and never reaches a browser
//! (ADR-0003). The screen that shows all this belongs to the `verifactu` module; the module cannot
//! make this call, which is exactly why the door is here.
//!
//! # The same split as the delegated certificate
//!
//! [`crate::fiscal_certificate`] is the precedent and this follows it: the layer that discovers
//! the need is not the layer that holds the credential, every pass is best-effort, and the whole
//! thing is bounded by a rolling budget because the control plane charges these calls per hub.
//!
//! # What is generic and what is ours
//!
//! The control plane's route is **not** a fiscal one: `POST/GET /api/v1/hub/device/legal-documents/`
//! is «a paper of this hub that needs a human», and the fiscal gateway identity is its first
//! tenant (saas#1833). The regime travels as the `kind`, so a second country is a new value here
//! and not a second endpoint.

use std::time::{Duration, Instant};

use base64::Engine as _;
use cloud_client::{Auth, CloudClient};
use erplora_db::DatabaseAdapter;
use erplora_runtime::gateway_identity;

use crate::fiscal_certificate::RefetchBudget;

/// The kind this hub files under, as the control plane declares it
/// (`apps/dashboard/fiscal/legal_documents.py`). ⚠️ It is written into rows and travels in the
/// API: renaming it is a migration on the SaaS side, not an edit here.
pub const KIND_FISCAL_GATEWAY_IDENTITY: &str = "fiscal_gateway_identity";

/// The generic legal-document route (saas#1833). Deliberately NOT `…/fiscal/csr/`: the regime
/// travels as the `kind`, so a second country is a new value and not a second endpoint.
pub const LEGAL_DOCUMENTS_PATH: &str = "/api/v1/hub/device/legal-documents/";

/// Calls one pass may spend: ask what the file says, and — only if nothing is filed — file.
pub const CALLS_PER_PASS: usize = 2;

/// Passes per rolling hour. An operator walking a CSR to an OFFLINE CA is a manual errand
/// measured in minutes at best, so asking twice a minute buys nothing and spends an allowance the
/// hub may need to collect the answer.
pub const MAX_ENROLMENT_PASSES_PER_HOUR: usize = 30;

/// What those passes cost the control plane at worst.
pub const MAX_ENROLMENT_CALLS_PER_HOUR: usize = MAX_ENROLMENT_PASSES_PER_HOUR * CALLS_PER_PASS;

/// The control plane's own limit on the route (`@quota(rate="120/h")` keyed by hub, saas#1833).
/// Mirrored here so the relation between the two numbers is checked instead of remembered.
pub const CONTROL_PLANE_QUOTA_PER_HOUR: usize = 120;

/// The relation is the guarantee, so the COMPILER checks it: the hub keeps HALF the allowance
/// free on purpose, because the screen of the `verifactu` module shares this quota and an
/// operator pressing «enrol» must never find it spent by a background loop.
const _: () = assert!(MAX_ENROLMENT_CALLS_PER_HOUR <= CONTROL_PLANE_QUOTA_PER_HOUR / 2);

/// How often the service looks at whether there is an enrolment in flight. The look itself is a
/// local read; only a hub that is actually enrolling ever spends a call.
pub const POLL_INTERVAL: Duration = Duration::from_secs(120);

/// After a refusal the hub waits before looking again: a rejection is a person saying no, and
/// nothing this side does will change it until somebody acts.
pub const REJECTED_BACKOFF: Duration = Duration::from_secs(1800);

/// The production budget: [`MAX_ENROLMENT_PASSES_PER_HOUR`] per rolling hour, shared by the
/// background service and the explicit door so the numbers live in ONE place.
pub fn hourly_budget() -> RefetchBudget {
    RefetchBudget::new(MAX_ENROLMENT_PASSES_PER_HOUR, Duration::from_secs(3600))
}

/// An approved document with nothing to collect. Impossible by the control plane's own rule, so
/// if it ever happens the hub says so instead of polling a row that says «done» forever.
pub const NO_ISSUED_DOCUMENT: &str = "enrolment.no_issued_document";
/// `issued_document` was not base64 of anything.
pub const ISSUED_NOT_BASE64: &str = "enrolment.issued_not_base64";
/// 🔴 A certificate with no internal CA behind it, on a hub that does not know one yet.
pub const ISSUED_WITHOUT_CA: &str = "enrolment.issued_without_ca";
/// The certificate came back but the core refused to install it (another key, another CN, or
/// already expired). The detail is the core's own message — no bytes of the document.
pub const INSTALL_REFUSED: &str = "enrolment.install_refused";
/// The CSR could not be produced (no master key, or a platform without the crypto).
pub const CSR_UNAVAILABLE: &str = "enrolment.csr_unavailable";
/// The control plane could not be reached, or answered something unreadable.
pub const CLOUD_UNREACHABLE: &str = "enrolment.cloud_unreachable";
/// The control plane answered a status with no code in it (a proxy page, a 5xx).
pub const CLOUD_REFUSED: &str = "enrolment.cloud_refused";

/// Why a pass could not finish, named by a CODE the screen programs against (ADR-0055).
///
/// When the refusal is the control plane's, the code is **its** code verbatim (`invalid_csr`,
/// `csr_common_name_mismatch`, `document_too_large`, …): one vocabulary, so an operator reading
/// the admin and a runtime reading this answer describe the same failure with the same word.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EnrolmentRefusal {
    pub code: String,
    /// Context for a human. **Never a byte of any document and never a response body**: these
    /// bodies come from the control plane and a proxy mishap can put a bearer in one.
    pub detail: String,
}

impl EnrolmentRefusal {
    fn new(code: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            detail: detail.into(),
        }
    }
}

impl std::fmt::Display for EnrolmentRefusal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.detail)
    }
}

/// What one pass concluded. Every variant is an ANSWER — the failures are the `Err` side.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EnrolmentOutcome {
    /// The CSR was filed just now and is waiting for a person.
    Filed { version: i64 },
    /// It was already filed and nobody has decided yet.
    AwaitingReview { version: i64 },
    /// The signed certificate was collected and installed. The road is open.
    Installed { not_after: Option<String> },
    /// A person refused it. The hub does not re-file: the operator rotates the key
    /// (`DELETE /api/business/gateway-identity`) and enrols again.
    Rejected { version: i64, reason: String },
    /// The hourly allowance is spent. Not an error and not a wait — the next tick picks it up.
    OutOfBudget,
}

/// The state of this hub's document in the file, as the control plane reports it.
struct FiledDocument {
    version: i64,
    status: String,
    rejected_reason: String,
    /// Base64 of what the review issued, served ONLY once approved.
    issued_document: Option<String>,
}

/// **Is an enrolment in flight on this hub?** A key with no certificate, and nothing else.
///
/// 🔴 This is what keeps the fleet from drowning its operator: a key only exists because somebody
/// asked for the CSR on THIS hub, so a hub that signs with its own certificate never files
/// anything and never spends a call. It is also why the background service never creates a key —
/// only the explicit door does.
pub async fn enrolment_in_flight(db: &dyn DatabaseAdapter, hub_id: &str) -> bool {
    match gateway_identity::status(db, hub_id).await {
        Ok(status) => status.has_key && !status.has_certificate,
        Err(error) => {
            // Never silent: a status that cannot be read is a hub whose enrolment will never
            // converge, and nobody would otherwise notice.
            tracing::warn!(%error, "no se pudo leer el estado de la identidad de máquina");
            false
        }
    }
}

/// One complete pass of the enrolment: ask what the file says and do the one thing it implies.
///
/// Best-effort by construction — every failure leaves the hub exactly as it was, with whatever
/// identity it already had, and says why with a code.
pub async fn enrol_once(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    budget: &RefetchBudget,
) -> std::result::Result<EnrolmentOutcome, EnrolmentRefusal> {
    if !budget.try_spend(Instant::now()) {
        // The guard doing its job, not a problem with the identity. Logged so a hub that keeps
        // hitting it is visible: that would mean something is asking in a loop.
        tracing::warn!(
            max_per_hour = MAX_ENROLMENT_PASSES_PER_HOUR,
            "alta de identidad de máquina omitida: presupuesto horario agotado"
        );
        return Ok(EnrolmentOutcome::OutOfBudget);
    }

    let Some(filed) = fetch_state(http, cloud_base_url, auth).await? else {
        return file_csr(http, cloud_base_url, auth, db, hub_id).await;
    };

    match filed.status.as_str() {
        "approved" => install_issued(db, hub_id, filed).await,
        "rejected" => Ok(EnrolmentOutcome::Rejected {
            version: filed.version,
            reason: filed.rejected_reason,
        }),
        // `revoked` is an identity cut off on purpose and `superseded` cannot be the latest row;
        // in both cases re-filing by ourselves would be the hub arguing with a decision.
        "revoked" | "superseded" => Ok(EnrolmentOutcome::AwaitingReview {
            version: filed.version,
        }),
        _ => Ok(EnrolmentOutcome::AwaitingReview {
            version: filed.version,
        }),
    }
}

/// `Ok(None)` = **404**, nothing filed yet. A normal state, not a failure: every hub starts there.
async fn fetch_state(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
) -> std::result::Result<Option<FiledDocument>, EnrolmentRefusal> {
    let request = CloudClient::new(cloud_base_url).machine_request(
        "GET",
        &format!("{LEGAL_DOCUMENTS_PATH}?kind={KIND_FISCAL_GATEWAY_IDENTITY}"),
        auth,
    );
    let (status, body) = send(http, &request).await?;
    if status == 404 {
        return Ok(None);
    }
    if !(200..300).contains(&status) {
        return Err(refusal_from(status, &body));
    }
    parse_filed(&body).map(Some)
}

/// Files the CSR. The key is generated here if this is the first time — which is why the
/// background service never reaches this branch on a hub that never asked.
async fn file_csr(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> std::result::Result<EnrolmentOutcome, EnrolmentRefusal> {
    let csr = gateway_identity::ensure_key_and_csr(db, hub_id)
        .await
        .map_err(|error| EnrolmentRefusal::new(CSR_UNAVAILABLE, error.to_string()))?;

    // Base64 of the BYTES, also for a PEM: one rule for a certificate request and for a PDF.
    let document = base64::engine::general_purpose::STANDARD.encode(csr.as_bytes());
    let payload = serde_json::json!({
        "kind": KIND_FISCAL_GATEWAY_IDENTITY,
        "document": document,
    })
    .to_string();

    let request =
        CloudClient::new(cloud_base_url).machine_request("POST", LEGAL_DOCUMENTS_PATH, auth);
    let (status, body) = send_json(http, &request, payload).await?;
    if !(200..300).contains(&status) {
        return Err(refusal_from(status, &body));
    }
    // 201 = filed now, 200 = the same bytes landed on the row that was already there (a POST
    // whose answer we lost). Both mean the same thing to this hub: it is waiting for a person.
    let version = parse_filed(&body).map(|filed| filed.version).unwrap_or(0);
    tracing::info!(
        version,
        "CSR de la identidad de máquina presentado al plano de control"
    );
    Ok(EnrolmentOutcome::Filed { version })
}

/// Collects what the review issued and installs it, CA included.
///
/// **The issued document is a PEM chain, the certificate FIRST** — the `fullchain` shape every
/// TLS deployment uses. The certificate alone is not an identity: without the internal CA this
/// hub cannot verify the cell's server certificate, so a chain of one is only enough when the
/// hub already knows the CA (the yearly renewal). Otherwise it is refused, visibly, and nothing
/// is written — a half-installed identity fails much later and talks about TLS instead.
async fn install_issued(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    filed: FiledDocument,
) -> std::result::Result<EnrolmentOutcome, EnrolmentRefusal> {
    let Some(encoded) = filed.issued_document.filter(|d| !d.is_empty()) else {
        return Err(EnrolmentRefusal::new(
            NO_ISSUED_DOCUMENT,
            format!("v{} aprobada sin certificado que recoger", filed.version),
        ));
    };
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(encoded.as_bytes())
        // The decoder error names positions, never content — but the encoded value itself is the
        // one thing that must not travel, so it is not interpolated either.
        .map_err(|_| EnrolmentRefusal::new(ISSUED_NOT_BASE64, "el certificado emitido no es base64"))?;
    let chain = String::from_utf8(bytes)
        .map_err(|_| EnrolmentRefusal::new(ISSUED_NOT_BASE64, "el certificado emitido no es UTF-8"))?;

    let (certificate_pem, rest) = split_leaf_and_chain(&chain);
    let ca_pem = if rest.trim().is_empty() {
        gateway_identity::stored_ca_pem(db, hub_id)
            .await
            .map_err(|error| EnrolmentRefusal::new(INSTALL_REFUSED, error.to_string()))?
            .ok_or_else(|| {
                EnrolmentRefusal::new(
                    ISSUED_WITHOUT_CA,
                    "el certificado emitido viene sin la CA interna y este hub aún no conoce \
                     ninguna: adjunta la cadena completa (certificado primero, CA después)",
                )
            })?
    } else {
        rest
    };

    let installed = gateway_identity::install_certificate(db, hub_id, &certificate_pem, &ca_pem)
        .await
        .map_err(|error| EnrolmentRefusal::new(INSTALL_REFUSED, error.to_string()))?;
    tracing::info!(
        version = filed.version,
        not_after = installed.not_after.as_deref().unwrap_or("?"),
        "identidad de máquina instalada: la ruta por la celda fiscal queda abierta"
    );
    Ok(EnrolmentOutcome::Installed {
        not_after: installed.not_after,
    })
}

/// Splits a PEM chain into its first certificate and whatever follows it. Anything that is not a
/// certificate block is left where it is — this is a splitter, not a parser; the core validates.
fn split_leaf_and_chain(chain: &str) -> (String, String) {
    const END: &str = "-----END CERTIFICATE-----";
    match chain.find(END) {
        Some(at) => {
            let cut = at + END.len();
            (chain[..cut].to_string(), chain[cut..].trim_start().to_string())
        }
        None => (chain.to_string(), String::new()),
    }
}

/// Reads the answer of the file. Field by field on purpose: a missing field is named, and the
/// BODY is never quoted back.
fn parse_filed(body: &str) -> std::result::Result<FiledDocument, EnrolmentRefusal> {
    let value: serde_json::Value = serde_json::from_str(body).map_err(|error| {
        // `serde_json::Error` carries a reason plus a line/column and no content, which is enough
        // to tell a truncated response from a changed contract.
        EnrolmentRefusal::new(
            CLOUD_UNREACHABLE,
            format!("{LEGAL_DOCUMENTS_PATH}: respuesta ilegible ({error})"),
        )
    })?;
    let status = value
        .get("status")
        .and_then(|v| v.as_str())
        .ok_or_else(|| {
            EnrolmentRefusal::new(
                CLOUD_UNREACHABLE,
                format!("{LEGAL_DOCUMENTS_PATH}: respuesta sin el campo `status`"),
            )
        })?
        .to_owned();
    Ok(FiledDocument {
        version: value.get("version").and_then(|v| v.as_i64()).unwrap_or(0),
        status,
        rejected_reason: value
            .get("rejected_reason")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_owned(),
        issued_document: value
            .get("issued_document")
            .and_then(|v| v.as_str())
            .map(str::to_owned),
    })
}

/// The control plane's refusal, by its CODE. `detail` is the whole contract (saas#1833); a status
/// with no code in it is the hub's own `cloud_refused`, never a slice of the body.
fn refusal_from(status: u16, body: &str) -> EnrolmentRefusal {
    let code = serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|value| {
            value
                .get("detail")
                .and_then(|v| v.as_str())
                .filter(|d| !d.is_empty())
                .map(str::to_owned)
        });
    match code {
        Some(code) => EnrolmentRefusal::new(code, format!("{LEGAL_DOCUMENTS_PATH}: status {status}")),
        None => EnrolmentRefusal::new(
            CLOUD_REFUSED,
            format!("{LEGAL_DOCUMENTS_PATH}: status {status}"),
        ),
    }
}

async fn send(
    http: &reqwest::Client,
    request: &cloud_client::PreparedRequest,
) -> std::result::Result<(u16, String), EnrolmentRefusal> {
    let mut builder = http.get(&request.url);
    for (name, value) in &request.headers {
        builder = builder.header(*name, value);
    }
    read_answer(builder).await
}

async fn send_json(
    http: &reqwest::Client,
    request: &cloud_client::PreparedRequest,
    payload: String,
) -> std::result::Result<(u16, String), EnrolmentRefusal> {
    let mut builder = http
        .post(&request.url)
        .header("Content-Type", "application/json")
        .body(payload);
    for (name, value) in &request.headers {
        builder = builder.header(*name, value);
    }
    read_answer(builder).await
}

async fn read_answer(
    builder: reqwest::RequestBuilder,
) -> std::result::Result<(u16, String), EnrolmentRefusal> {
    let response = builder.send().await.map_err(|error| {
        EnrolmentRefusal::new(
            CLOUD_UNREACHABLE,
            format!("{LEGAL_DOCUMENTS_PATH}: {error}"),
        )
    })?;
    let status = response.status().as_u16();
    let body = response.text().await.map_err(|error| {
        EnrolmentRefusal::new(
            CLOUD_UNREACHABLE,
            format!("{LEGAL_DOCUMENTS_PATH}: status {status} ({error})"),
        )
    })?;
    Ok((status, body))
}

/// The service that makes an enrolment converge **without an operator in front of it**.
///
/// It looks at a local flag on a timer and only spends a call when there is an enrolment in
/// flight — so a fleet of hubs that sign with their own certificate costs the control plane
/// nothing. A hub whose request was refused backs right off: nothing this side does will change
/// a person's «no».
pub fn spawn_enrolment_service(st: &crate::state::AppState) {
    let Some(auth) = crate::auth::machine_auth(st) else {
        // A hub whose bootstrap never finished has no machine credential; it also cannot enrol.
        return;
    };
    let st = st.clone();
    tokio::spawn(async move {
        let budget = hourly_budget();
        let mut wait = POLL_INTERVAL;
        loop {
            tokio::time::sleep(wait).await;
            wait = POLL_INTERVAL;
            let hub_id = st.hub_id();
            let in_flight = {
                let rt = st.runtime.read().await;
                enrolment_in_flight(rt.db(), &hub_id).await
            };
            if !in_flight {
                continue;
            }
            let rt = st.runtime.read().await;
            match enrol_once(
                &st.http,
                &st.config.cloud_base_url,
                &auth,
                rt.db(),
                &hub_id,
                &budget,
            )
            .await
            {
                Ok(EnrolmentOutcome::Rejected { version, reason }) => {
                    // Visible and rare on purpose: this is the state a human has to resolve.
                    tracing::warn!(
                        version,
                        %reason,
                        "el plano de control rechazó el CSR de la identidad de máquina; \
                         el hub no vuelve a presentarlo por su cuenta"
                    );
                    wait = REJECTED_BACKOFF;
                }
                Ok(_) => {}
                Err(refusal) => {
                    tracing::warn!(
                        code = %refusal.code,
                        detail = %refusal.detail,
                        "no se pudo avanzar el alta de la identidad de máquina"
                    );
                }
            }
        }
    });
}

#[cfg(not(target_os = "android"))]
#[cfg(test)]
mod tests {
    use super::*;
    use axum::extract::Json as AxumJson;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::get;
    use axum::Router;
    use cloud_client::Auth;
    use erplora_db::testutil::fresh_db;
    use erplora_db::PgAdapter;
    use erplora_runtime::gateway_identity;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::{Arc, Mutex};

    const HUB: &str = "11111111-2222-4333-8444-555566667777";

    /// A bearer-shaped string planted in the stub's answers: no error, no log line and no outcome
    /// may ever carry it back. Same rule as `fiscal_certificate.rs`, and for the same reason —
    /// these bodies come from the control plane and a proxy mishap can put anything in them.
    const NEVER_ECHOED: &str = "SECRET-BEARER-abcdefghijklmnop";

    fn machine_auth() -> Auth {
        Auth::HubToken {
            hub_id: HUB.into(),
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

    /// `HUB_SECRETS_KEY` for the tests that store a key. Written exactly ONCE for the binary and
    /// never removed: no test here asserts its absence, so there is no state another can observe.
    fn ensure_master_key() {
        static SET: std::sync::Once = std::sync::Once::new();
        SET.call_once(|| {
            // SAFETY: the only write in this binary, serialised by `Once`, and it happens-before
            // every read because every reader calls this first.
            unsafe { std::env::set_var("HUB_SECRETS_KEY", "A".repeat(43) + "=") };
        });
    }

    /// Signs `csr_pem` with a throwaway CA — the shape `gateway-pki sign` produces, built here so
    /// the roundtrip needs no external binary. Returns `(leaf_pem, ca_pem)`.
    fn sign_with_test_ca(csr_pem: &str) -> (String, String) {
        use openssl::asn1::Asn1Time;
        use openssl::hash::MessageDigest;
        use openssl::nid::Nid;
        use openssl::pkey::PKey;
        use openssl::x509::{X509NameBuilder, X509Req, X509};

        let ca_key = PKey::from_ec_key(
            openssl::ec::EcKey::generate(
                &openssl::ec::EcGroup::from_curve_name(Nid::X9_62_PRIME256V1).unwrap(),
            )
            .unwrap(),
        )
        .unwrap();
        let mut ca_name = X509NameBuilder::new().unwrap();
        ca_name
            .append_entry_by_nid(Nid::COMMONNAME, "ERPlora Fiscal Internal CA TEST")
            .unwrap();
        let ca_name = ca_name.build();
        let mut ca = X509::builder().unwrap();
        ca.set_version(2).unwrap();
        ca.set_subject_name(&ca_name).unwrap();
        ca.set_issuer_name(&ca_name).unwrap();
        ca.set_pubkey(&ca_key).unwrap();
        ca.set_not_before(&Asn1Time::days_from_now(0).unwrap())
            .unwrap();
        ca.set_not_after(&Asn1Time::days_from_now(3650).unwrap())
            .unwrap();
        ca.sign(&ca_key, MessageDigest::sha256()).unwrap();
        let ca = ca.build();

        let req = X509Req::from_pem(csr_pem.as_bytes()).unwrap();
        let mut cert = X509::builder().unwrap();
        cert.set_version(2).unwrap();
        cert.set_subject_name(req.subject_name()).unwrap();
        cert.set_issuer_name(&ca_name).unwrap();
        cert.set_pubkey(&req.public_key().unwrap()).unwrap();
        cert.set_not_before(&Asn1Time::days_from_now(0).unwrap())
            .unwrap();
        cert.set_not_after(&Asn1Time::days_from_now(365).unwrap())
            .unwrap();
        cert.sign(&ca_key, MessageDigest::sha256()).unwrap();
        let cert = cert.build();
        (
            String::from_utf8(cert.to_pem().unwrap()).unwrap(),
            String::from_utf8(ca.to_pem().unwrap()).unwrap(),
        )
    }

    struct Stub {
        base: String,
        posts: Arc<Mutex<Vec<serde_json::Value>>>,
        post_headers: Arc<Mutex<Option<HeaderMap>>>,
        gets: Arc<AtomicUsize>,
        server: tokio::task::JoinHandle<()>,
    }

    impl Stub {
        fn posted(&self) -> Vec<serde_json::Value> {
            self.posts.lock().unwrap().clone()
        }
        fn get_calls(&self) -> usize {
            self.gets.load(Ordering::SeqCst)
        }
    }

    impl Drop for Stub {
        fn drop(&mut self) {
            self.server.abort();
        }
    }

    /// A control plane answering the legal-document route: the GET with `(status, body)` and the
    /// POST with `(status, body)`, recording what it was asked with.
    async fn cloud_stub(
        get_answer: (StatusCode, String),
        post_answer: (StatusCode, String),
    ) -> Stub {
        let posts: Arc<Mutex<Vec<serde_json::Value>>> = Arc::new(Mutex::new(Vec::new()));
        let post_headers: Arc<Mutex<Option<HeaderMap>>> = Arc::new(Mutex::new(None));
        let gets = Arc::new(AtomicUsize::new(0));

        let app = Router::new().route(
            "/api/v1/hub/device/legal-documents/",
            get({
                let gets = gets.clone();
                move || {
                    gets.fetch_add(1, Ordering::SeqCst);
                    let (status, body) = (get_answer.0, get_answer.1.clone());
                    async move { (status, body) }
                }
            })
            .post({
                let posts = posts.clone();
                let post_headers = post_headers.clone();
                move |headers: HeaderMap, AxumJson(body): AxumJson<serde_json::Value>| {
                    posts.lock().unwrap().push(body);
                    *post_headers.lock().unwrap() = Some(headers);
                    let (status, body) = (post_answer.0, post_answer.1.clone());
                    async move { (status, body) }
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Stub {
            base: format!("http://{address}"),
            posts,
            post_headers,
            gets,
            server,
        }
    }

    fn approved_body(issued: &str) -> String {
        serde_json::json!({
            "id": "doc-1",
            "kind": KIND_FISCAL_GATEWAY_IDENTITY,
            "regime": "es-verifactu",
            "version": 1,
            "status": "approved",
            "rejected_reason": "",
            "issued_document": base64::engine::general_purpose::STANDARD.encode(issued),
            "issued_at": "2026-09-03T10:00:00+00:00",
            "updated_at": "2026-09-03T10:00:00+00:00",
        })
        .to_string()
    }

    fn budget() -> RefetchBudget {
        RefetchBudget::new(MAX_ENROLMENT_PASSES_PER_HOUR, std::time::Duration::from_secs(3600))
    }

    // ── The door itself ───────────────────────────────────────────────────────────────────────

    /// The whole point of the issue: the CSR reaches the control plane **with the machine
    /// credential** and under the declared kind, and what travels is base64 of the PEM bytes.
    #[tokio::test]
    async fn the_hub_files_its_own_csr_with_the_machine_credential() {
        ensure_master_key();
        let db = db_ready().await;
        let stub = cloud_stub(
            (StatusCode::NOT_FOUND, r#"{"detail":"not_found"}"#.into()),
            (
                StatusCode::CREATED,
                r#"{"id":"doc-1","kind":"fiscal_gateway_identity","version":1,"status":"pending"}"#
                    .into(),
            ),
        )
        .await;

        let outcome = enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &budget(),
        )
        .await
        .expect("el alta no debe fallar");

        assert_eq!(outcome, EnrolmentOutcome::Filed { version: 1 });

        let posted = stub.posted();
        assert_eq!(posted.len(), 1, "se presenta UNA vez, no en bucle");
        assert_eq!(posted[0]["kind"], KIND_FISCAL_GATEWAY_IDENTITY);
        let document = base64::engine::general_purpose::STANDARD
            .decode(posted[0]["document"].as_str().expect("document base64"))
            .expect("`document` es base64 de los BYTES del PEM");
        let csr = openssl::x509::X509Req::from_pem(&document).expect("es un CSR PEM");
        let cn = csr
            .subject_name()
            .entries_by_nid(openssl::nid::Nid::COMMONNAME)
            .next()
            .and_then(|e| e.data().as_slice().to_vec().into())
            .map(|raw: Vec<u8>| String::from_utf8_lossy(&raw).into_owned())
            .unwrap_or_default();
        assert_eq!(cn, gateway_identity::common_name(HUB));

        let headers = stub.post_headers.lock().unwrap().clone().expect("cabeceras");
        assert_eq!(headers.get("X-Hub-Token").unwrap(), "machine-tok");
        assert_eq!(headers.get("X-Hub-Id").unwrap(), HUB);
    }

    /// Approving is only half: the hub has to COLLECT. After this pass the machine identity is
    /// usable — which is the only assertion that proves the road opened.
    #[tokio::test]
    async fn an_approved_certificate_is_collected_and_the_identity_becomes_usable() {
        ensure_master_key();
        let db = db_ready().await;
        let csr = gateway_identity::ensure_key_and_csr(&db, HUB).await.unwrap();
        let (leaf, ca) = sign_with_test_ca(&csr);

        let stub = cloud_stub(
            (StatusCode::OK, approved_body(&format!("{leaf}{ca}"))),
            (StatusCode::CREATED, "{}".into()),
        )
        .await;

        let outcome = enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &budget(),
        )
        .await
        .expect("recoger el certificado no debe fallar");

        assert!(matches!(outcome, EnrolmentOutcome::Installed { .. }));
        assert!(stub.posted().is_empty(), "no se re-presenta lo ya aprobado");
        assert!(
            gateway_identity::client_identity(&db, HUB)
                .await
                .unwrap()
                .is_some(),
            "la identidad mTLS tiene que quedar montable tras recoger el certificado"
        );
    }

    /// 🔴 The certificate alone is not an identity: without the internal CA the hub cannot verify
    /// the cell's server certificate. Refused by CODE and NOTHING installed — a half-installed
    /// identity would fail later, at transmission time, with a message about TLS.
    #[tokio::test]
    async fn a_certificate_without_the_internal_ca_is_refused_and_nothing_is_installed() {
        ensure_master_key();
        let db = db_ready().await;
        let csr = gateway_identity::ensure_key_and_csr(&db, HUB).await.unwrap();
        let (leaf, _ca) = sign_with_test_ca(&csr);

        let stub = cloud_stub(
            (StatusCode::OK, approved_body(&leaf)),
            (StatusCode::CREATED, "{}".into()),
        )
        .await;

        let refusal = enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &budget(),
        )
        .await
        .expect_err("sin CA no se instala");

        assert_eq!(refusal.code, ISSUED_WITHOUT_CA);
        assert!(
            !gateway_identity::status(&db, HUB)
                .await
                .unwrap()
                .has_certificate,
            "no puede quedar un certificado a medias instalado"
        );
    }

    /// The yearly renewal: the key is the same and the CA is already stored, so a leaf on its own
    /// is enough. Without this the renewal of every hub in the fleet stops on a technicality.
    #[tokio::test]
    async fn a_renewal_with_the_certificate_alone_reuses_the_ca_already_stored() {
        ensure_master_key();
        let db = db_ready().await;
        let csr = gateway_identity::ensure_key_and_csr(&db, HUB).await.unwrap();
        let (first, ca) = sign_with_test_ca(&csr);
        gateway_identity::install_certificate(&db, HUB, &first, &ca)
            .await
            .unwrap();

        // A SECOND certificate for the same key, delivered without the CA.
        let (renewed, _other_ca) = sign_with_test_ca(&csr);
        let stub = cloud_stub(
            (StatusCode::OK, approved_body(&renewed)),
            (StatusCode::CREATED, "{}".into()),
        )
        .await;

        let outcome = enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &budget(),
        )
        .await
        .expect("la renovación con la CA ya guardada debe instalar");

        assert!(matches!(outcome, EnrolmentOutcome::Installed { .. }));
    }

    /// A rejection is a person saying no. The hub reports it and **stops**: re-filing the same
    /// bytes would open a new review every pass and turn one refusal into a queue of them.
    #[tokio::test]
    async fn a_rejected_request_is_never_refiled_by_the_hub() {
        ensure_master_key();
        let db = db_ready().await;
        gateway_identity::ensure_key_and_csr(&db, HUB).await.unwrap();

        let body = serde_json::json!({
            "id": "doc-1", "kind": KIND_FISCAL_GATEWAY_IDENTITY, "regime": "es-verifactu",
            "version": 2, "status": "rejected", "rejected_reason": "wrong_key",
            "issued_document": serde_json::Value::Null, "issued_at": serde_json::Value::Null,
            "updated_at": "2026-09-03T10:00:00+00:00",
        })
        .to_string();
        let stub = cloud_stub((StatusCode::OK, body), (StatusCode::CREATED, "{}".into())).await;

        let outcome = enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &budget(),
        )
        .await
        .expect("un rechazo es una respuesta, no un fallo");

        assert_eq!(
            outcome,
            EnrolmentOutcome::Rejected {
                version: 2,
                reason: "wrong_key".into()
            }
        );
        assert!(stub.posted().is_empty(), "un rechazo NO se vuelve a presentar");
    }

    /// The control plane's refusal codes are the contract (`invalid_csr`,
    /// `csr_common_name_mismatch`, …). They travel 1:1 so the screen can say what to fix; the
    /// prose is never read.
    #[tokio::test]
    async fn a_refusal_from_the_control_plane_travels_by_its_code() {
        ensure_master_key();
        let db = db_ready().await;
        let stub = cloud_stub(
            (StatusCode::NOT_FOUND, r#"{"detail":"not_found"}"#.into()),
            (
                StatusCode::BAD_REQUEST,
                r#"{"detail":"csr_common_name_mismatch"}"#.into(),
            ),
        )
        .await;

        let refusal = enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &budget(),
        )
        .await
        .expect_err("un 400 del plano de control es una negativa");

        assert_eq!(refusal.code, "csr_common_name_mismatch");
    }

    /// 🔒 These bodies come from the control plane and a proxy mishap can put a bearer in one. No
    /// error may quote it — the same lesson as the delegated certificate.
    #[tokio::test]
    async fn an_unreadable_answer_never_quotes_the_body() {
        ensure_master_key();
        let db = db_ready().await;
        let stub = cloud_stub(
            (StatusCode::OK, format!("not json at all {NEVER_ECHOED}")),
            (StatusCode::CREATED, "{}".into()),
        )
        .await;

        let refusal = enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &budget(),
        )
        .await
        .expect_err("una respuesta ilegible es un fallo");

        assert!(
            !refusal.detail.contains(NEVER_ECHOED) && !refusal.code.contains(NEVER_ECHOED),
            "el fallo arrastra el cuerpo de la respuesta: {refusal:?}"
        );
    }

    /// A pass costs at most two calls (ask, then file). The control plane charges these per hub,
    /// so the number is a safety property and not a detail.
    #[tokio::test]
    async fn one_pass_never_costs_more_than_two_calls() {
        ensure_master_key();
        let db = db_ready().await;
        let stub = cloud_stub(
            (StatusCode::NOT_FOUND, r#"{"detail":"not_found"}"#.into()),
            (
                StatusCode::CREATED,
                r#"{"version":1,"status":"pending"}"#.into(),
            ),
        )
        .await;

        enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &budget(),
        )
        .await
        .unwrap();

        assert_eq!(stub.get_calls() + stub.posted().len(), CALLS_PER_PASS);
    }

    /// An exhausted budget skips the pass; it never errors and never waits. The next tick picks
    /// it up — the enrolment is not urgent, and burning the hub's allowance is what would be.
    #[tokio::test]
    async fn an_exhausted_budget_skips_the_pass_without_calling() {
        ensure_master_key();
        let db = db_ready().await;
        let stub = cloud_stub(
            (StatusCode::NOT_FOUND, r#"{"detail":"not_found"}"#.into()),
            (StatusCode::CREATED, "{}".into()),
        )
        .await;
        let spent = RefetchBudget::new(0, std::time::Duration::from_secs(3600));

        let outcome = enrol_once(
            &reqwest::Client::new(),
            &stub.base,
            &machine_auth(),
            &db,
            HUB,
            &spent,
        )
        .await
        .expect("quedarse sin presupuesto no es un error");

        assert_eq!(outcome, EnrolmentOutcome::OutOfBudget);
        assert_eq!(stub.get_calls(), 0);
        assert!(stub.posted().is_empty());
    }

    // ── When the service is allowed to spend anything at all ──────────────────────────────────

    /// 🔴 The trigger, and the reason the fleet does not drown its operator in reviews: an
    /// enrolment is only «in flight» when somebody already asked for the CSR on this hub. A hub
    /// that signs with its own certificate never files anything.
    #[tokio::test]
    async fn only_a_hub_that_asked_for_a_csr_is_enrolling() {
        ensure_master_key();
        let db = db_ready().await;

        assert!(
            !enrolment_in_flight(&db, HUB).await,
            "sin clave nadie ha pedido nada: el servicio no debe gastar una llamada"
        );

        let csr = gateway_identity::ensure_key_and_csr(&db, HUB).await.unwrap();
        assert!(
            enrolment_in_flight(&db, HUB).await,
            "con clave y sin certificado hay un alta en curso"
        );

        let (leaf, ca) = sign_with_test_ca(&csr);
        gateway_identity::install_certificate(&db, HUB, &leaf, &ca)
            .await
            .unwrap();
        assert!(
            !enrolment_in_flight(&db, HUB).await,
            "con certificado instalado ya no hay nada que sondear"
        );
    }

    /// The hub's own ceiling has to stay under the control plane's — and the relation is checked
    /// by the COMPILER (`const _: () = assert!(…)` above), which is why this test does not repeat
    /// it. What it does is NAME the numbers, so raising one has to face a failure that says which
    /// quota it is eating: the screen of the `verifactu` module shares this allowance, and an
    /// operator pressing «enrol» must never find it spent by a background loop.
    #[test]
    fn the_budget_names_the_numbers_it_is_bounded_by() {
        assert_eq!(MAX_ENROLMENT_PASSES_PER_HOUR, 30);
        assert_eq!(CALLS_PER_PASS, 2);
        assert_eq!(MAX_ENROLMENT_CALLS_PER_HOUR, 60);
        assert_eq!(CONTROL_PLANE_QUOTA_PER_HOUR, 120);
    }
}
