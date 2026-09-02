//! **The signed Anexo I: the customer signs it OUTSIDE, ERPlora reviews it** (hub#1293).
//!
//! ERPlora remits VeriFactu records **on behalf of** the taxpayer, and that needs their signed
//! consent — the Anexo I of the acuerdo de colaboración social 017, whose model (p. 11) says in so
//! many words that its text «no podrá ser modificado».
//!
//! # What this module stopped doing, and why (hub#1293)
//!
//! It used to COMPOSE the otorgamiento here: a paraphrase of the Anexo I rendered into HTML around
//! a stroke drawn on a `<canvas>`. Both halves were wrong, and the AEAT's own colaboración social
//! FAQ says why: the model may be signed **by hand** on the printed form (plus the company seal if
//! the otorgante is a legal person, plus a copy of the ID) **or electronically with a qualified
//! certificate of the customer's own** — and nothing else. A stroke captured on a screen is neither,
//! and a company seal does not fit in a canvas.
//!
//! So the shape is now: the **SaaS** is the single source of the model (it renders the official PDF
//! pre-filled), the customer signs it **off the screen**, and this module carries the result up.
//! Every upload lands on `pendiente` and **a person at ERPlora approves it** — ERPlora answers to
//! the tax authority «de la autenticidad de la firma… así como de la copia del DNI», and that is
//! not a responsibility a parser can take.
//!
//! # Three rules this module exists to hold
//!
//! 1. **The machine token never reaches the browser** (ADR-0003). The screen posts to these routes
//!    and the RUNTIME adds `X-Hub-Token`, exactly like the marketplace and entitlement proxies.
//! 2. **The hub does not keep the documents, and it does not rewrite them either.** What the
//!    customer signed is forwarded **byte for byte** and dropped — nothing is written to a table.
//!    Custody is the SaaS's (personal data, RGPD), and a copy sitting in a hub's database is a copy
//!    in every backup and every blueprint export. Re-packing it would be worse: the reviewer would
//!    be approving something the customer never signed.
//! 3. **No document goes anywhere near a log.** Not their bytes, not their names, not on the error
//!    path — which is the branch that most invites «let me show you what I sent».

use axum::extract::{Multipart, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::{json, Value};

use crate::state::AppState;
use crate::{auth, unauthorized};

/// Ceiling for each document, mirroring the control plane's own limit (`MAX_GRANT_DOCUMENT_BYTES`).
///
/// Checked HERE as well as there so an oversized upload is refused before it crosses the network:
/// the alternative is spending the hub's quota to be told no, and holding two copies in memory
/// meanwhile.
pub const MAX_DOCUMENT_BYTES: usize = 10 * 1024 * 1024;

/// **What the whole upload may weigh**, and the reason it is stated here.
///
/// 🔴 Axum's default body limit is **2 MB** — a fifth of what [`validate`] accepts for ONE
/// document, and this request carries up to four. Without saying so on the route, a customer who
/// scans the signed model at any sensible resolution gets a refusal from the framework, before a
/// line of this module runs and with no code the screen could explain. Four documents at the
/// per-document ceiling, plus room for the multipart envelope itself.
pub const MAX_UPLOAD_BYTES: usize = 4 * MAX_DOCUMENT_BYTES + 64 * 1024;

/// The magic every PDF starts with. What the customer uploads has to be one: both signing routes
/// the AEAT admits (a scan of the printed model, or AutoFirma over the model) produce a PDF, and
/// anything else reaches the human reviewer as a file they cannot open, three days later.
const PDF_MAGIC: &[u8] = b"%PDF";

/// **The first letter of a Spanish NIF tells you it belongs to an entity, not a person.**
///
/// Same name and same letters as the SaaS's `is_legal_person_nif`, on purpose: a company's grant is
/// signed by whoever its escritura names, so that document has to travel — and asking a
/// self-employed baker for one would be asking for something that does not exist. `X`/`Y`/`Z` (NIE)
/// and a leading digit (DNI) are people.
///
/// Normalises first (upper case, no spaces, no dashes): what the customer types is `b-12345674` as
/// often as `B12345674`, and reading the raw string would let a company through as a person.
pub fn is_legal_person_nif(nif: &str) -> bool {
    const ENTITY_LETTERS: &str = "ABCDEFGHJNPQRSUVW";
    normalise_nif(nif)
        .chars()
        .next()
        .is_some_and(|first| ENTITY_LETTERS.contains(first))
}

/// Upper case, without the separators people type. Shared by every read of a NIF here.
fn normalise_nif(nif: &str) -> String {
    nif.chars()
        .filter(|c| !c.is_whitespace() && *c != '-' && *c != '.')
        .flat_map(char::to_uppercase)
        .collect()
}

/// The two identity documents the model admits, and what each one implies.
const DOCUMENT_DNI: &str = "dni";
const DOCUMENT_NIE: &str = "nie";

/// A file as it arrived: `(file name, bytes)`. The name travels so the reviewer opens something
/// with an extension, and it is **never** logged.
pub type Upload = (String, Vec<u8>);

/// What the person at the till uploaded, collected from the browser's multipart.
///
/// `Debug` is **not** derived: this struct holds a scan of somebody's ID card, and a derived
/// `Debug` is how that ends up in a `tracing` line the day somebody adds `?capture`.
#[derive(Default)]
pub struct Capture {
    pub obligado_nif: String,
    pub obligado_name: String,
    pub signer_nif: String,
    pub signer_name: String,
    /// `dni` or `nie` — it decides whether a signature sample is required.
    pub document_type: String,
    /// Which colaboración social route the grant travels by. Its choices belong to the SaaS, so it
    /// is forwarded and not judged here: the hub would only have a second, staler copy of the list.
    pub via: String,
    /// 🔴 **THE document**: the official model, signed off the screen. A PDF, always.
    pub signed_document: Option<Upload>,
    /// Copy of the signer's DNI/NIE. ERPlora answers for it.
    pub dni_copy: Option<Upload>,
    /// A separate sheet with a handwritten signature — **required with a NIE**, because many
    /// foreign identity documents carry no printed signature to compare against.
    pub signature_sample: Option<Upload>,
    /// What proves who may sign for a company — the model's own note (2): «según documento
    /// justificativo que se adjunta». **Required when the obligado is a legal person.**
    pub representation_proof: Option<Upload>,
}

/// The fields that fill in the official model, exactly the ten the SaaS renders.
///
/// An allow-list and not a passthrough `Value`: whatever this browser sends ends up inside a
/// document ERPlora archives as legal evidence, so the runtime decides which keys exist.
/// The address fields may be empty — the model then keeps its dotted lines to fill in by hand.
///
/// `Debug` is **not** derived, same reason as [`Capture`].
#[derive(Default, serde::Deserialize)]
#[serde(default)]
pub struct ModelFields {
    pub obligado_nif: String,
    pub obligado_name: String,
    pub obligado_municipio: String,
    pub obligado_via: String,
    pub obligado_numero: String,
    pub signer_nif: String,
    pub signer_name: String,
    pub signer_municipio: String,
    pub signer_via: String,
    pub signer_numero: String,
}

impl ModelFields {
    /// As the control plane reads them. Written by hand rather than derived so that adding a field
    /// to the struct is a decision about what leaves the hub, not a side effect.
    fn to_json(&self) -> Value {
        json!({
            "obligado_nif": self.obligado_nif,
            "obligado_name": self.obligado_name,
            "obligado_municipio": self.obligado_municipio,
            "obligado_via": self.obligado_via,
            "obligado_numero": self.obligado_numero,
            "signer_nif": self.signer_nif,
            "signer_name": self.signer_name,
            "signer_municipio": self.signer_municipio,
            "signer_via": self.signer_via,
            "signer_numero": self.signer_numero,
        })
    }
}

/// **The control plane did not produce what was asked of it.**
///
/// The status travels separately from the message because the SCREEN needs it: while the SaaS is
/// still being deployed the model route answers `404`, and «404» is something a person can act on
/// — a blank panel is not. `None` means the request never got an answer at all.
///
/// `detail` is diagnosable and **free of anything the request was carrying**: this is the branch
/// that most invites quoting the body, and the body is a signed document and a scan of an ID card.
#[derive(Debug, PartialEq, Eq)]
pub struct CloudRefusal {
    pub status_code: Option<u16>,
    pub detail: String,
}

impl CloudRefusal {
    fn unreachable(detail: impl Into<String>) -> Self {
        Self {
            status_code: None,
            detail: detail.into(),
        }
    }

    fn status(status: StatusCode, detail: impl Into<String>) -> Self {
        Self {
            status_code: Some(status.as_u16()),
            detail: detail.into(),
        }
    }
}

/// What ERPlora holds, as the hub records it: `(status, instant)`.
///
/// `status` is the control plane's own word (`pendiente` / `vigente` / `rechazado` / `revocado` /
/// `absent`), copied and not translated — a mapping in the middle is one more place for the two
/// sides to drift, and this value decides whether a business may invoice for real.
pub type GrantState = (String, String);

/// Reads the control plane's answer into what the profile stores.
///
/// 🔴 **The instant comes RESOLVED, in `at`.** Which date belongs to a state — signed, reviewed or
/// revoked — is the control plane's decision, and it sends the answer in one field. Deriving it
/// here from the status was re-implementing that decision with data the hub does not have: the
/// SaaS never sends `reviewed_at`, so a refusal showed an EMPTY date — exactly the case where the
/// customer most needs to know when it came back.
///
/// `signed_at`/`revoked_at` are still read as a **fallback**, for a hub pointed at a control plane
/// old enough not to send `at` yet (the deploy order is SaaS before Hub, but not every hub follows
/// it the same hour). Degrading to "I do not know when" is worse than the approximate date we
/// already had.
///
/// A body that does not say answers `("absent", "")` — an unreadable answer is not a grant, and the
/// safe reading of "I could not tell" is "you have not signed".
pub fn grant_state_from_cloud(body: &Value) -> GrantState {
    use erplora_runtime::fiscal_profile as profile;
    let text = |key: &str| {
        body.get(key)
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string()
    };
    let status = text("status");
    if status.is_empty() {
        return (profile::REPRESENTATION_ABSENT.to_string(), String::new());
    }
    let mut at = text("at");
    if at.is_empty() {
        at = if status == profile::REPRESENTATION_REVOKED {
            text("revoked_at")
        } else {
            text("signed_at")
        };
    }
    (status, at)
}

/// Everything a capture must carry before it is worth a network call.
///
/// **The codes are the contract**, and the SaaS answers with the same ones over the same rules
/// (hub#1293): the screen programs against them, and a rule that only one side enforces is a rule
/// that stops being enforced the day the other side is called directly.
///
/// The obligado is required and there is **no fallback**: the SaaS refuses one too, because the
/// only other NIF around is the payer's, which is a different taxpayer.
pub fn validate(capture: &Capture) -> Result<(), &'static str> {
    if capture.obligado_nif.trim().is_empty() {
        return Err("obligado_nif_required");
    }
    if capture.signer_nif.trim().is_empty() || capture.signer_name.trim().is_empty() {
        return Err("signer_required");
    }
    let document_type = capture.document_type.trim();
    if document_type != DOCUMENT_DNI && document_type != DOCUMENT_NIE {
        return Err("document_type_invalid");
    }
    let signed = required_upload(&capture.signed_document, "signed_document_required")?;
    if !signed.starts_with(PDF_MAGIC) {
        return Err("signed_document_not_pdf");
    }
    required_upload(&capture.dni_copy, "dni_copy_required")?;
    // 🔴 A NIE needs something to compare the signature against: many foreign identity documents
    // carry no printed signature, and ERPlora answers for the authenticity of that signature.
    if document_type == DOCUMENT_NIE {
        required_upload(&capture.signature_sample, "signature_sample_required")?;
    }
    // 🔴 A company signs through whoever its escritura names — the model's note (2).
    if is_legal_person_nif(&capture.obligado_nif) {
        required_upload(
            &capture.representation_proof,
            "representation_proof_required",
        )?;
    }
    Ok(())
}

/// A document that has to be there, is not empty, and fits. An empty file is not an upload: a
/// picker that produced zero bytes would otherwise send an otorgamiento with nothing in it.
fn required_upload<'a>(
    upload: &'a Option<Upload>,
    missing: &'static str,
) -> Result<&'a [u8], &'static str> {
    match upload {
        Some((_, bytes)) if bytes.len() > MAX_DOCUMENT_BYTES => Err("document_too_large"),
        Some((_, bytes)) if !bytes.is_empty() => Ok(bytes),
        _ => Err(missing),
    }
}

/// The three fields the model needs before it is worth rendering: a model with no parties in it is
/// a sheet of paper the customer signs for nothing. Same codes as the capture.
pub fn validate_model_fields(fields: &ModelFields) -> Result<(), &'static str> {
    if fields.obligado_nif.trim().is_empty() {
        return Err("obligado_nif_required");
    }
    if fields.signer_nif.trim().is_empty() || fields.signer_name.trim().is_empty() {
        return Err("signer_required");
    }
    Ok(())
}

/// Drains the browser's multipart into a [`Capture`].
///
/// A text field that cannot be read is skipped: [`validate`] decides in one place whether what
/// arrived is enough. **A stream that breaks is not skipped.** Behind the route's body limit
/// ([`MAX_UPLOAD_BYTES`]) the one thing that cuts the stream in practice is an upload heavier than
/// the door, and an empty capture would then answer `obligado_nif_required` — «your business needs
/// a taxpayer ID» — to somebody whose only mistake was a 45 MB scan. The code names the problem.
pub async fn collect(mut multipart: Multipart) -> Result<Capture, &'static str> {
    let mut capture = Capture::default();
    loop {
        let field = match multipart.next_field().await {
            Ok(Some(field)) => field,
            Ok(None) => break,
            Err(_) => return Err("document_too_large"),
        };
        let name = field.name().unwrap_or_default().to_string();
        match name.as_str() {
            "signed_document" | "dni_copy" | "signature_sample" | "representation_proof" => {
                let file_name = field
                    .file_name()
                    .map(str::to_string)
                    .unwrap_or_else(|| name.clone());
                let Ok(bytes) = field.bytes().await else {
                    return Err("document_too_large");
                };
                let upload = Some((file_name, bytes.to_vec()));
                match name.as_str() {
                    "signed_document" => capture.signed_document = upload,
                    "dni_copy" => capture.dni_copy = upload,
                    "signature_sample" => capture.signature_sample = upload,
                    _ => capture.representation_proof = upload,
                }
            }
            "obligado_nif" | "obligado_name" | "signer_nif" | "signer_name" | "document_type"
            | "via" => {
                let Ok(value) = field.text().await else {
                    continue;
                };
                let value = value.trim().to_string();
                match name.as_str() {
                    "obligado_nif" => capture.obligado_nif = value,
                    "obligado_name" => capture.obligado_name = value,
                    "signer_nif" => capture.signer_nif = value,
                    "signer_name" => capture.signer_name = value,
                    "document_type" => capture.document_type = value,
                    _ => capture.via = value,
                }
            }
            _ => {}
        }
    }
    Ok(capture)
}

/// Sends the capture up to the control plane with the MACHINE credential.
///
/// 🔴 **The documents are forwarded exactly as they arrived.** The hub composes nothing any more
/// (hub#1293): what the customer signed is what ERPlora custodies and what a reviewer opens. An
/// optional document that was not uploaded is **omitted**, never sent as an empty part — an empty
/// attachment is what makes a reviewer stare at a blank file wondering whether it is missing or
/// broken.
///
/// `Ok(body)` is the SaaS's 201 payload (metadata only — it never returns the documents).
pub async fn forward_capture(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    capture: &Capture,
) -> Result<Value, CloudRefusal> {
    let request = cloud_client::CloudClient::new(cloud_base_url).representation_grant(auth);
    let mut form = reqwest::multipart::Form::new()
        .text("obligado_nif", capture.obligado_nif.clone())
        .text("obligado_name", capture.obligado_name.clone())
        .text("signer_nif", capture.signer_nif.clone())
        .text("signer_name", capture.signer_name.clone())
        .text("document_type", capture.document_type.clone());
    if !capture.via.is_empty() {
        form = form.text("via", capture.via.clone());
    }
    for (part, upload) in [
        ("signed_document", &capture.signed_document),
        ("dni_copy", &capture.dni_copy),
        ("signature_sample", &capture.signature_sample),
        ("representation_proof", &capture.representation_proof),
    ] {
        let Some((file_name, bytes)) = upload else {
            continue;
        };
        form = form.part(
            part,
            reqwest::multipart::Part::bytes(bytes.clone()).file_name(file_name.clone()),
        );
    }

    let mut sent = http.post(&request.url).multipart(form);
    for (name, value) in request.headers {
        sent = sent.header(name, value);
    }
    let response = sent
        .send()
        .await
        .map_err(|error| CloudRefusal::unreachable(error.to_string()))?;
    let status = response.status();
    if !status.is_success() {
        return Err(CloudRefusal::status(
            status,
            format!("{}: status {status}", request.url),
        ));
    }
    let body = response
        .text()
        .await
        .map_err(|error| CloudRefusal::status(status, error.to_string()))?;
    serde_json::from_str(&body).map_err(|error| {
        CloudRefusal::status(
            status,
            format!("{}: unreadable answer ({error})", request.url),
        )
    })
}

/// Brings down the **official model**, pre-filled, from the only place its text lives.
///
/// 🔴 The Hub does not compose it and does not cache it. Page 11 of the acuerdo 017 says the text
/// «no podrá ser modificado», so there is ONE source — the SaaS — and this is a pipe: bytes in,
/// bytes out. What comes back is checked to actually be a PDF, because handing the customer an HTML
/// error page named `anexo-i.pdf` is the silent failure this route exists not to have.
pub async fn fetch_model_pdf(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    fields: &ModelFields,
) -> Result<Vec<u8>, CloudRefusal> {
    let request = cloud_client::CloudClient::new(cloud_base_url).representation_grant_model(auth);
    let mut sent = http.post(&request.url).json(&fields.to_json());
    for (name, value) in request.headers {
        sent = sent.header(name, value);
    }
    let response = sent
        .send()
        .await
        .map_err(|error| CloudRefusal::unreachable(error.to_string()))?;
    let status = response.status();
    if !status.is_success() {
        return Err(CloudRefusal::status(
            status,
            format!("{}: status {status}", request.url),
        ));
    }
    let bytes = response
        .bytes()
        .await
        .map_err(|error| CloudRefusal::status(status, error.to_string()))?;
    if !bytes.starts_with(PDF_MAGIC) {
        return Err(CloudRefusal::status(
            status,
            format!("{}: not a pdf", request.url),
        ));
    }
    Ok(bytes.to_vec())
}

/// Asks the control plane what it holds. Metadata only — this route never serves the documents.
pub async fn fetch_state(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
) -> Result<Value, CloudRefusal> {
    let request = cloud_client::CloudClient::new(cloud_base_url).representation_grant(auth);
    let mut sent = http.get(&request.url);
    for (name, value) in request.headers {
        sent = sent.header(name, value);
    }
    let response = sent
        .send()
        .await
        .map_err(|error| CloudRefusal::unreachable(error.to_string()))?;
    let status = response.status();
    if !status.is_success() {
        return Err(CloudRefusal::status(
            status,
            format!("{}: status {status}", request.url),
        ));
    }
    let body = response
        .text()
        .await
        .map_err(|error| CloudRefusal::status(status, error.to_string()))?;
    serde_json::from_str(&body).map_err(|error| {
        CloudRefusal::status(
            status,
            format!("{}: unreadable answer ({error})", request.url),
        )
    })
}

// ── HTTP surface ────────────────────────────────────────────────────────────────────────────────

/// `GET /api/fiscal/representation-grant` — what ERPlora holds, and the hub's copy of it.
///
/// Auth = a user session (any role): the fiscal screen shows this to whoever is looking at it, and
/// it is metadata about a document, never the document.
///
/// **The answer is mirrored into the profile on the way through**, which is what lets
/// `fiscal_profile::go_live` — a database transition — ask the question without a network call and
/// keeps the answer across a restart. A control plane that does not respond leaves the stored copy
/// exactly as it was and says so, rather than inventing an "absent" that would close the go-live.
pub async fn get_representation_grant(State(st): State<AppState>, headers: HeaderMap) -> Response {
    {
        let runtime = st.runtime.read().await;
        if let Err(error) = auth::require_user_session(&headers, &st.config, &runtime).await {
            return unauthorized(error);
        }
    }
    let Some(machine) = auth::machine_auth(&st) else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ok": false, "error": "hub_not_enrolled" })),
        )
            .into_response();
    };
    match fetch_state(&st.http, &st.config.cloud_base_url, &machine).await {
        Ok(body) => {
            let previous = stored_state(&st).await;
            let state = grant_state_from_cloud(&body);
            mirror_into_profile(&st, &state).await;
            // 🔴 **Approval arrives DAYS later, and nobody tells the hub.** A reviewer approves at
            // ERPlora, and the delegated certificate is unlocked on that side (saas#1438); the hub
            // only learns of it when it next asks — which is here, on the screen the customer opens
            // to check. Without this, the person would read «vigente» and still find a go-live that
            // refuses, until the next hourly refetch happened to run.
            if state.0 == erplora_runtime::fiscal_profile::REPRESENTATION_VIGENTE
                && previous.0 != erplora_runtime::fiscal_profile::REPRESENTATION_VIGENTE
            {
                crate::fiscal_certificate::refetch_after_grant(&st);
            }
            Json(json!({
                "ok": true,
                "status": state.0,
                "at": state.1,
                "obligado_nif": body.get("obligado_nif").and_then(Value::as_str).unwrap_or(""),
                // Why a reviewer sent it back, so the screen can say it instead of «rechazado» on
                // its own — which tells the customer to try again with no idea what to change.
                "rejected_reason": body.get("rejected_reason").and_then(Value::as_str).unwrap_or(""),
                "signature_kind": body.get("signature_kind").and_then(Value::as_str).unwrap_or(""),
                "document_type": body.get("document_type").and_then(Value::as_str).unwrap_or(""),
            }))
            .into_response()
        }
        Err(refusal) => {
            // The stored copy is left untouched: "I could not ask" is not "you have not signed".
            tracing::warn!(
                detail = %refusal.detail,
                "no se pudo consultar el otorgamiento en el plano de control"
            );
            let stored = stored_state(&st).await;
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({
                    "ok": false,
                    "error": "cloud_unreachable",
                    "status_code": refusal.status_code,
                    "status": stored.0,
                    "at": stored.1,
                })),
            )
                .into_response()
        }
    }
}

/// `POST /api/fiscal/representation-grant/model` — the official model, pre-filled, to print or to
/// sign with AutoFirma.
///
/// Auth = an **admin** session, the same bar as the upload: the fields travel into a document that
/// names the business as a taxpayer.
pub async fn post_representation_grant_model(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(fields): Json<ModelFields>,
) -> Response {
    {
        let runtime = st.runtime.read().await;
        if let Err(error) = auth::require_admin_session(&headers, &st.config, &runtime).await {
            return unauthorized(error);
        }
    }
    if let Err(reason) = validate_model_fields(&fields) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": reason })),
        )
            .into_response();
    }
    let Some(machine) = auth::machine_auth(&st) else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ok": false, "error": "hub_not_enrolled" })),
        )
            .into_response();
    };
    match fetch_model_pdf(&st.http, &st.config.cloud_base_url, &machine, &fields).await {
        Ok(pdf) => (
            StatusCode::OK,
            [
                (header::CONTENT_TYPE, "application/pdf".to_string()),
                (
                    header::CONTENT_DISPOSITION,
                    "attachment; filename=\"anexo-i-otorgamiento.pdf\"".to_string(),
                ),
                // A legal form that is about to be signed is never served from a cache.
                (header::CACHE_CONTROL, "no-store".to_string()),
            ],
            pdf,
        )
            .into_response(),
        Err(refusal) => {
            // 🔴 The SaaS is deployed BEFORE the hub, so while that is in flight this route answers
            // 404 — and the status is what the screen turns into a sentence instead of a dead
            // button. `detail` never carries the fields (see `fetch_model_pdf`).
            tracing::warn!(
                detail = %refusal.detail,
                "el plano de control no sirvió el modelo del otorgamiento"
            );
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({
                    "ok": false,
                    "error": "cloud_rejected",
                    "status_code": refusal.status_code,
                })),
            )
                .into_response()
        }
    }
}

/// `POST /api/fiscal/representation-grant` — the signed model goes up, and the wait begins.
///
/// Auth = an **admin** session: signing away the power to file on the business's behalf is the
/// owner's decision, the same bar as uploading the fiscal certificate or editing the fiscal
/// identity.
///
/// What comes back is `pendiente`, not `vigente`: a person at ERPlora reviews it (24-72 h).
pub async fn post_representation_grant(
    State(st): State<AppState>,
    headers: HeaderMap,
    multipart: Multipart,
) -> Response {
    {
        let runtime = st.runtime.read().await;
        if let Err(error) = auth::require_admin_session(&headers, &st.config, &runtime).await {
            return unauthorized(error);
        }
    }
    let refused = |reason: &'static str| {
        (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": reason })),
        )
            .into_response()
    };
    let capture = match collect(multipart).await {
        Ok(capture) => capture,
        Err(reason) => return refused(reason),
    };
    if let Err(reason) = validate(&capture) {
        return refused(reason);
    }
    let Some(machine) = auth::machine_auth(&st) else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ok": false, "error": "hub_not_enrolled" })),
        )
            .into_response();
    };

    match forward_capture(&st.http, &st.config.cloud_base_url, &machine, &capture).await {
        Ok(body) => {
            let state = grant_state_from_cloud(&body);
            mirror_into_profile(&st, &state).await;
            // Status only. Not the NIF of the signer, not a byte of any document.
            tracing::info!(status = %state.0, "otorgamiento de representación enviado a revisión");
            (
                StatusCode::CREATED,
                Json(json!({ "ok": true, "status": state.0, "at": state.1 })),
            )
                .into_response()
        }
        Err(refusal) => {
            // `refusal.detail` never carries the request or the response body (see
            // `forward_capture`); the status does travel, so the screen can say WHICH refusal.
            tracing::warn!(
                detail = %refusal.detail,
                "el plano de control rechazó el otorgamiento"
            );
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({
                    "ok": false,
                    "error": "cloud_rejected",
                    "status_code": refusal.status_code,
                })),
            )
                .into_response()
        }
    }
}

/// Writes the control plane's answer into `_hub_fiscal_profile`. Best-effort: a write that fails
/// leaves the previous copy, and the next read of the screen tries again.
async fn mirror_into_profile(st: &AppState, state: &GrantState) {
    let runtime = st.runtime.read().await;
    if let Err(error) = erplora_runtime::fiscal_profile::record_representation(
        runtime.db(),
        runtime.hub_id(),
        &state.0,
        &state.1,
    )
    .await
    {
        tracing::warn!(%error, "no se pudo guardar el estado del otorgamiento en el perfil fiscal");
    }
}

/// The copy the hub already holds, for when the control plane cannot be reached.
async fn stored_state(st: &AppState) -> GrantState {
    let runtime = st.runtime.read().await;
    match erplora_runtime::fiscal_profile::load(runtime.db(), runtime.hub_id()).await {
        Ok(Some(profile)) => (profile.representation_status, profile.representation_at),
        _ => (String::new(), String::new()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderMap as AxumHeaderMap;
    use axum::routing::{get, post};
    use axum::Router;
    use erplora_runtime::fiscal_profile::{
        REPRESENTATION_ABSENT, REPRESENTATION_PENDING, REPRESENTATION_REJECTED,
        REPRESENTATION_REVOKED, REPRESENTATION_VIGENTE,
    };
    use std::sync::{Arc, Mutex};

    /// The official model, printed, signed by hand and scanned back in — a PDF, always.
    const SIGNED_PDF: &[u8] = b"%PDF-1.7 el modelo que firmo Manolo";
    const DNI_SCAN: &[u8] = b"\xff\xd8\xff\xe0 the scan of an ID card";
    const SIGNATURE_SAMPLE: &[u8] = b"\xff\xd8\xff\xe0 a sheet with a handwritten signature";
    const PROOF_PDF: &[u8] = b"%PDF-1.7 la escritura que nombra al administrador";
    const MACHINE_TOKEN: &str = "machine-tok";

    fn machine_auth() -> cloud_client::Auth {
        cloud_client::Auth::HubToken {
            hub_id: "hub-test".into(),
            token: MACHINE_TOKEN.into(),
        }
    }

    /// A **natural person** signing for themselves: DNI, no sample, no proof of representation.
    fn natural_capture() -> Capture {
        Capture {
            obligado_nif: "12345678Z".into(),
            obligado_name: "Manolo García".into(),
            signer_nif: "12345678Z".into(),
            signer_name: "Manolo García".into(),
            document_type: "dni".into(),
            via: "convenio_17".into(),
            signed_document: Some(("anexo-i.pdf".into(), SIGNED_PDF.to_vec())),
            dni_copy: Some(("dni.jpg".into(), DNI_SCAN.to_vec())),
            signature_sample: None,
            representation_proof: None,
        }
    }

    /// A **company**: its administrator signs, so the document naming them travels too.
    fn company_capture() -> Capture {
        Capture {
            obligado_nif: "B12345674".into(),
            obligado_name: "Bar Manolo SL".into(),
            representation_proof: Some(("escritura.pdf".into(), PROOF_PDF.to_vec())),
            ..natural_capture()
        }
    }

    // ── Who is a legal person ─────────────────────────────────────────────────────────────────

    /// 🔴 **The first letter of the NIF is what decides it**, and both sides read it the same way
    /// (`is_legal_person_nif`, byte for byte in the SaaS): a company's grant is signed by whoever
    /// its escritura names, so ERPlora has to be handed that document — and asking a self-employed
    /// baker for one would be asking for something that does not exist.
    #[test]
    fn a_nif_that_starts_with_an_entity_letter_is_a_legal_person() {
        for nif in [
            "B12345674",
            "A28001234",
            "G12345678",
            "W1234567H",
            "J99999999",
        ] {
            assert!(
                is_legal_person_nif(nif),
                "{nif} debería ser persona jurídica"
            );
        }
        // Personas físicas (DNI) y extranjeros (NIE: X/Y/Z) NO lo son.
        for nif in [
            "12345678Z",
            "X1234567L",
            "Y1234567X",
            "Z1234567R",
            "",
            "K1234567L",
        ] {
            assert!(!is_legal_person_nif(nif), "{nif} NO es persona jurídica");
        }
    }

    /// Lo que el cliente escribe lleva minúsculas, espacios y guiones. Normalizar ANTES de mirar la
    /// letra es lo que impide que «b-12345674» pase por persona física y se archive sin el
    /// justificante de representación.
    #[test]
    fn the_nif_is_normalised_before_its_first_letter_is_read() {
        for nif in [" b12345674 ", "b-12345674", "B 12345674"] {
            assert!(is_legal_person_nif(nif), "{nif} debería normalizarse");
        }
    }

    // ── What a capture must carry ─────────────────────────────────────────────────────────────

    /// 🔴 **El documento firmado ya no lo compone el Hub: llega firmado desde fuera** (hub#1293).
    /// La FAQ de colaboración social de la AEAT admite exactamente dos vías —manuscrita sobre el
    /// modelo impreso o firma electrónica con certificado cualificado del cliente— y las dos
    /// producen un PDF. Sin él, y sin la copia del documento de identidad de la que ERPlora
    /// responde, no hay otorgamiento.
    #[test]
    fn a_capture_is_refused_unless_it_carries_the_signed_model_and_the_identity_copy() {
        assert_eq!(validate(&natural_capture()), Ok(()));
        assert_eq!(validate(&company_capture()), Ok(()));

        let without_document = Capture {
            signed_document: None,
            ..natural_capture()
        };
        assert_eq!(validate(&without_document), Err("signed_document_required"));

        let without_dni = Capture {
            dni_copy: None,
            ..natural_capture()
        };
        assert_eq!(validate(&without_dni), Err("dni_copy_required"));

        let without_obligado = Capture {
            obligado_nif: "  ".into(),
            ..natural_capture()
        };
        assert_eq!(validate(&without_obligado), Err("obligado_nif_required"));

        let without_signer = Capture {
            signer_name: String::new(),
            ..natural_capture()
        };
        assert_eq!(validate(&without_signer), Err("signer_required"));
    }

    /// An EMPTY file is not a document. A picker that produced a zero-byte file would otherwise
    /// send an otorgamiento with nothing in it for a person to review.
    #[test]
    fn an_empty_document_does_not_count_as_uploaded() {
        let empty = Capture {
            signed_document: Some(("anexo-i.pdf".into(), Vec::new())),
            ..natural_capture()
        };
        assert_eq!(validate(&empty), Err("signed_document_required"));

        let empty_dni = Capture {
            dni_copy: Some(("dni.jpg".into(), Vec::new())),
            ..natural_capture()
        };
        assert_eq!(validate(&empty_dni), Err("dni_copy_required"));
    }

    /// 🔴 **Lo que se sube tiene que ser EL PDF**, no una foto del papel ni un `.docx`. El modelo se
    /// firma con AutoFirma o se escanea, y en las dos vías sale un PDF; cualquier otra cosa llega al
    /// revisor como un fichero que no puede abrir, tres días después de subirlo.
    #[test]
    fn what_is_uploaded_has_to_be_a_pdf() {
        let photo = Capture {
            signed_document: Some(("anexo.jpg".into(), b"\xff\xd8\xff\xe0 una foto".to_vec())),
            ..natural_capture()
        };
        assert_eq!(validate(&photo), Err("signed_document_not_pdf"));
    }

    /// El tipo de documento de identidad decide qué más hace falta, así que no puede llegar vacío
    /// ni con una palabra inventada.
    #[test]
    fn the_identity_document_type_is_dni_or_nie_and_nothing_else() {
        for kind in ["", "pasaporte", "DNI "] {
            let capture = Capture {
                document_type: kind.into(),
                ..natural_capture()
            };
            assert_eq!(validate(&capture), Err("document_type_invalid"), "{kind:?}");
        }
    }

    /// 🔴 **Un NIE exige además una muestra de firma.** Muchos documentos de identidad extranjeros
    /// no llevan firma impresa, y ERPlora responde ante la AEAT de la autenticidad de la firma del
    /// otorgante: sin nada con que compararla, el revisor no puede responder de ella.
    #[test]
    fn a_nie_needs_a_separate_signature_sample() {
        let nie = Capture {
            document_type: "nie".into(),
            ..natural_capture()
        };
        assert_eq!(validate(&nie), Err("signature_sample_required"));

        let with_sample = Capture {
            signature_sample: Some(("firma.jpg".into(), SIGNATURE_SAMPLE.to_vec())),
            ..nie
        };
        assert_eq!(validate(&with_sample), Ok(()));

        // Con DNI no se pide: la firma va en el propio documento.
        assert_eq!(validate(&natural_capture()), Ok(()));
    }

    /// 🔴 **Una sociedad tiene que acreditar quién puede firmar por ella.** El modelo oficial lo
    /// dice en su nota (2): quien firma lo hace «según documento justificativo que se adjunta». Al
    /// autónomo no se le pide, porque no existe.
    #[test]
    fn a_company_has_to_prove_who_may_sign_for_it() {
        let without_proof = Capture {
            representation_proof: None,
            ..company_capture()
        };
        assert_eq!(
            validate(&without_proof),
            Err("representation_proof_required")
        );

        // Y a la persona física NO se le exige.
        assert_eq!(validate(&natural_capture()), Ok(()));
    }

    /// Refused HERE and not only by the SaaS: crossing the network to be told no spends the hub's
    /// quota and holds two copies of the upload in memory meanwhile. Los cuatro ficheros, porque el
    /// que se olvide es el que llega de 40 MB.
    #[test]
    fn an_oversized_document_is_refused_before_it_crosses_the_network() {
        let huge = vec![0u8; MAX_DOCUMENT_BYTES + 1];

        let cases = [
            Capture {
                signed_document: Some((
                    "anexo-i.pdf".into(),
                    [b"%PDF".to_vec(), huge.clone()].concat(),
                )),
                ..company_capture()
            },
            Capture {
                dni_copy: Some(("dni.jpg".into(), huge.clone())),
                ..company_capture()
            },
            Capture {
                document_type: "nie".into(),
                signature_sample: Some(("firma.jpg".into(), huge.clone())),
                ..company_capture()
            },
            Capture {
                representation_proof: Some(("escritura.pdf".into(), huge.clone())),
                ..company_capture()
            },
        ];
        for capture in &cases {
            assert_eq!(validate(capture), Err("document_too_large"));
        }
    }

    /// 🔴 **La puerta tiene que ser más ancha que lo que se deja pasar.** El límite de cuerpo por
    /// defecto de axum son 2 MB: con él, un modelo escaneado a resolución normal lo rechaza el
    /// framework antes de que corra una línea de este módulo, sin código que la pantalla pueda
    /// explicar. Si alguien baja `MAX_UPLOAD_BYTES` por debajo de lo que `validate` admite, esto
    /// se pone rojo aquí y no en el mostrador de un cliente.
    #[test]
    fn the_route_accepts_everything_validate_accepts() {
        assert!(MAX_UPLOAD_BYTES >= 4 * MAX_DOCUMENT_BYTES);
    }

    // ── Reading the control plane's answer ────────────────────────────────────────────────────

    /// 🔴 **La fecha del estado la manda el SaaS ya resuelta, en `at`** (contrato del plan, revisor
    /// de saas#1727). El control plane calcula cuál toca —firmado, revisado o revocado— y la envía
    /// en UN campo; `signed_at`/`revoked_at` viajan solo por compatibilidad con los hubs viejos y
    /// **`reviewed_at` NO se envía**. Deducirla aquí a partir del estado era reimplementar su
    /// decisión con datos que no tiene: en `rechazado` pintaba fecha VACÍA.
    #[test]
    fn the_instant_is_the_one_the_control_plane_resolved() {
        let rechazado = json!({
            "status": "rechazado",
            "at": "2026-08-29T10:00:00Z",
            "signed_at": "2026-08-28T09:00:00Z"
        });
        assert_eq!(
            grant_state_from_cloud(&rechazado),
            (
                REPRESENTATION_REJECTED.to_string(),
                "2026-08-29T10:00:00Z".to_string()
            ),
            "un rechazo tiene que decir cuándo se lo devolvieron"
        );

        let vigente = json!({
            "status": "vigente",
            "at": "2026-08-30T09:00:00Z",
            "signed_at": "2026-08-28T09:00:00Z"
        });
        assert_eq!(
            grant_state_from_cloud(&vigente).1,
            "2026-08-30T09:00:00Z",
            "`at` manda sobre `signed_at` cuando vienen los dos"
        );
    }

    /// Y con un SaaS que todavía no manda `at` (el orden de despliegue es SaaS antes que Hub, pero
    /// un hub puede apuntar a uno viejo), se cae a los campos de siempre en vez de a una fecha en
    /// blanco: degradar a «no sé cuándo» es peor que la fecha aproximada que ya teníamos.
    #[test]
    fn without_at_the_old_fields_still_answer() {
        let vigente =
            json!({"status": "vigente", "signed_at": "2026-08-11T09:00:00Z", "revoked_at": null});
        assert_eq!(
            grant_state_from_cloud(&vigente),
            (
                REPRESENTATION_VIGENTE.to_string(),
                "2026-08-11T09:00:00Z".to_string()
            )
        );

        let pendiente = json!({"status": "pendiente", "signed_at": "2026-08-28T09:00:00Z"});
        assert_eq!(
            grant_state_from_cloud(&pendiente),
            (
                REPRESENTATION_PENDING.to_string(),
                "2026-08-28T09:00:00Z".to_string()
            )
        );

        let revoked = json!({"status": "revocado", "signed_at": "2026-01-01T00:00:00Z", "revoked_at": "2026-08-11T10:00:00Z"});
        assert_eq!(
            grant_state_from_cloud(&revoked),
            (
                REPRESENTATION_REVOKED.to_string(),
                "2026-08-11T10:00:00Z".to_string()
            )
        );
    }

    /// 🔒 **An answer that says nothing reads as "not signed".** The safe direction is the closed
    /// one: a body the hub could not understand must not open the go-live, because the door it
    /// opens is filing real invoices on somebody's behalf without their consent.
    #[test]
    fn an_answer_that_says_nothing_is_read_as_absent() {
        assert_eq!(
            grant_state_from_cloud(&json!({})),
            (REPRESENTATION_ABSENT.to_string(), String::new())
        );
        assert_eq!(
            grant_state_from_cloud(&json!({"detail": "whatever"})),
            (REPRESENTATION_ABSENT.to_string(), String::new())
        );
    }

    // ── The credential, and what must never travel ────────────────────────────────────────────

    /// A control-plane stub that records the headers and the raw body it was asked with.
    async fn cloud_stub(
        status: StatusCode,
        body: &'static str,
    ) -> (
        String,
        Arc<Mutex<Option<AxumHeaderMap>>>,
        Arc<Mutex<Vec<u8>>>,
        tokio::task::JoinHandle<()>,
    ) {
        let seen_headers: Arc<Mutex<Option<AxumHeaderMap>>> = Arc::new(Mutex::new(None));
        let seen_body: Arc<Mutex<Vec<u8>>> = Arc::new(Mutex::new(Vec::new()));
        let route = "/api/v1/hub/device/fiscal/representation-grant/";
        let model_route = "/api/v1/hub/device/fiscal/representation-grant/model/";
        let app = Router::new()
            .route(
                route,
                post({
                    let (headers, raw) = (seen_headers.clone(), seen_body.clone());
                    move |hs: AxumHeaderMap, payload: axum::body::Bytes| {
                        *headers.lock().unwrap() = Some(hs);
                        raw.lock().unwrap().extend_from_slice(&payload);
                        async move { (status, body) }
                    }
                }),
            )
            .route(
                route,
                get({
                    let headers = seen_headers.clone();
                    move |hs: AxumHeaderMap| {
                        *headers.lock().unwrap() = Some(hs);
                        async move { (status, body) }
                    }
                }),
            )
            .route(
                model_route,
                post({
                    let (headers, raw) = (seen_headers.clone(), seen_body.clone());
                    move |hs: AxumHeaderMap, payload: axum::body::Bytes| {
                        *headers.lock().unwrap() = Some(hs);
                        raw.lock().unwrap().extend_from_slice(&payload);
                        async move { (status, body) }
                    }
                }),
            );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (format!("http://{address}"), seen_headers, seen_body, server)
    }

    /// 🔒 **The MACHINE credential goes out and a user JWT does not.** The SaaS accepts nothing
    /// else on this route, and the whole reason the browser posts to the runtime instead of to the
    /// SaaS is that `X-Hub-Token` must never exist inside a webview.
    #[tokio::test]
    async fn the_capture_travels_with_the_machine_credential_and_no_user_jwt() {
        let (base, headers, _body, server) = cloud_stub(
            StatusCode::CREATED,
            r#"{"status": "pendiente", "signed_at": "2026-08-28T09:00:00Z"}"#,
        )
        .await;

        forward_capture(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &company_capture(),
        )
        .await
        .expect("el plano de control acepta el otorgamiento");

        let seen = headers
            .lock()
            .unwrap()
            .clone()
            .expect("cabeceras capturadas");
        assert_eq!(seen["x-hub-id"], "hub-test");
        assert_eq!(seen["x-hub-token"], MACHINE_TOKEN);
        assert!(!seen.contains_key("authorization"));
        server.abort();
    }

    /// 🔴 **Los cuatro ficheros viajan TAL CUAL.** El Hub ya no compone nada (hub#1293): lo que el
    /// cliente firmó fuera es exactamente lo que ERPlora custodia y lo que un revisor va a abrir. Si
    /// el runtime lo reempaquetara, el revisor estaría aprobando algo que el cliente no firmó.
    #[tokio::test]
    async fn the_four_documents_and_the_declared_obligado_reach_the_control_plane_untouched() {
        let (base, _headers, body, server) = cloud_stub(
            StatusCode::CREATED,
            r#"{"status": "pendiente", "signed_at": "2026-08-28T09:00:00Z"}"#,
        )
        .await;

        let capture = Capture {
            document_type: "nie".into(),
            signature_sample: Some(("firma.jpg".into(), SIGNATURE_SAMPLE.to_vec())),
            ..company_capture()
        };
        forward_capture(&reqwest::Client::new(), &base, &machine_auth(), &capture)
            .await
            .unwrap();

        let sent = body.lock().unwrap().clone();
        let sent = String::from_utf8_lossy(&sent);
        assert!(
            sent.contains("B12345674"),
            "el obligado declarado tiene que viajar"
        );
        assert!(sent.contains("name=\"document_type\""));
        assert!(sent.contains("nie"));
        for part in [
            "signed_document",
            "dni_copy",
            "signature_sample",
            "representation_proof",
        ] {
            assert!(
                sent.contains(&format!("name=\"{part}\"")),
                "falta la parte {part}"
            );
        }
        // Los BYTES del PDF firmado, sin recomponer: es la prueba legal.
        assert!(sent.contains("%PDF-1.7 el modelo que firmo Manolo"));
        server.abort();
    }

    /// Lo que NO se subió no viaja como una parte vacía: una `signature_sample` de cero bytes es
    /// justo lo que hace que el revisor mire un adjunto en blanco y no sepa si falta o falló.
    #[tokio::test]
    async fn the_optional_documents_are_omitted_when_there_are_none() {
        let (base, _headers, body, server) = cloud_stub(
            StatusCode::CREATED,
            r#"{"status": "pendiente", "signed_at": "2026-08-28T09:00:00Z"}"#,
        )
        .await;

        forward_capture(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &natural_capture(),
        )
        .await
        .unwrap();

        let sent = body.lock().unwrap().clone();
        let sent = String::from_utf8_lossy(&sent);
        assert!(!sent.contains("name=\"signature_sample\""));
        assert!(!sent.contains("name=\"representation_proof\""));
        server.abort();
    }

    /// 🔒 **A failure must not quote what was sent** — and it has to say the STATUS, because that is
    /// what the screen turns into something the customer can act on instead of a blank panel.
    #[tokio::test]
    async fn a_rejection_never_quotes_the_documents_it_was_carrying() {
        let (base, _headers, _body, server) = cloud_stub(
            StatusCode::INTERNAL_SERVER_ERROR,
            r#"{"detail": "boom", "echo": "Bar Manolo SL — the scan of an ID card"}"#,
        )
        .await;

        let refusal = forward_capture(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &company_capture(),
        )
        .await
        .unwrap_err();

        assert_eq!(refusal.status_code, Some(500));
        for secret in ["Bar Manolo", "Manolo", "ID card"] {
            assert!(
                !refusal.detail.contains(secret),
                "el error arrastra {secret:?}: {}",
                refusal.detail
            );
        }
        server.abort();
    }

    /// 🔒 The same rule on an unreadable 2xx: a body that did not parse is exactly the body most
    /// likely to hold something personal.
    #[tokio::test]
    async fn an_unreadable_answer_is_not_echoed_either() {
        let (base, _headers, _body, server) =
            cloud_stub(StatusCode::CREATED, "not json at all — Bar Manolo SL").await;

        let refusal = forward_capture(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &company_capture(),
        )
        .await
        .unwrap_err();

        assert!(!refusal.detail.contains("Bar Manolo"), "{}", refusal.detail);
        server.abort();
    }

    /// 🔒 **Nothing personal reaches the logs on the happy path** — the one that runs on every
    /// capture. Captures the whole `tracing` output of a forward and greps it.
    #[tokio::test]
    async fn forwarding_a_capture_writes_nothing_personal_to_the_logs() {
        let (base, _headers, _body, server) = cloud_stub(
            StatusCode::CREATED,
            r#"{"status": "pendiente", "signed_at": "2026-08-28T09:00:00Z"}"#,
        )
        .await;

        let captured = Arc::new(Mutex::new(Vec::<u8>::new()));
        let subscriber = tracing_subscriber::fmt()
            .with_writer(CapturingWriter(captured.clone()))
            .with_max_level(tracing::Level::TRACE)
            .finish();
        {
            let _guard = tracing::subscriber::set_default(subscriber);
            forward_capture(
                &reqwest::Client::new(),
                &base,
                &machine_auth(),
                &company_capture(),
            )
            .await
            .unwrap();
        }

        let logs = String::from_utf8_lossy(&captured.lock().unwrap().clone()).into_owned();
        for secret in [
            "%PDF",
            "ID card",
            "12345678Z",
            "escritura",
            "anexo-i.pdf",
            MACHINE_TOKEN,
        ] {
            assert!(
                !logs.contains(secret),
                "fuga de {secret:?} a los logs: {logs}"
            );
        }
        server.abort();
    }

    // ── El modelo oficial: se PROXYA, no se compone ───────────────────────────────────────────

    /// 🔴 **El texto del modelo ya no vive en el Hub** (hub#1293). La página 11 del acuerdo 017 dice
    /// que «no podrá ser modificado», así que hay UNA fuente —el SaaS— y el runtime solo trae los
    /// bytes. Lo que se descarga es el PDF, tal cual salió de allí.
    #[tokio::test]
    async fn the_official_model_is_fetched_from_the_control_plane_and_returned_verbatim() {
        let (base, headers, body, server) = cloud_stub(StatusCode::OK, "%PDF-1.7 el modelo").await;

        let pdf = fetch_model_pdf(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &model_fields(),
        )
        .await
        .expect("el plano de control devuelve el modelo");

        assert_eq!(pdf, b"%PDF-1.7 el modelo");
        let seen = headers.lock().unwrap().clone().expect("cabeceras");
        assert_eq!(seen["x-hub-token"], MACHINE_TOKEN);
        assert!(!seen.contains_key("authorization"));
        // Y los datos que rellenan el modelo viajan como JSON.
        let sent = String::from_utf8_lossy(&body.lock().unwrap().clone()).into_owned();
        assert!(sent.contains("B12345674"));
        assert!(sent.contains("obligado_municipio"));
        server.abort();
    }

    /// 🔴 **Un SaaS que todavía no tiene la ruta contesta 404, y eso se DICE.** El orden de
    /// despliegue es SaaS antes que Hub; mientras tanto, un botón que no hace nada es peor que un
    /// error: el status viaja para que la pantalla lo pueda enseñar.
    #[tokio::test]
    async fn a_control_plane_without_the_model_route_answers_with_its_status() {
        let refusal = fetch_model_pdf(
            &reqwest::Client::new(),
            "http://127.0.0.1:1",
            &machine_auth(),
            &model_fields(),
        )
        .await
        .unwrap_err();
        // Sin respuesta no hay status, pero sí un motivo diagnosticable.
        assert_eq!(refusal.status_code, None);
        assert!(!refusal.detail.is_empty());

        let (base, _h, _b, server) =
            cloud_stub(StatusCode::NOT_FOUND, "<html>Not Found</html>").await;
        let refusal = fetch_model_pdf(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &model_fields(),
        )
        .await
        .unwrap_err();
        assert_eq!(refusal.status_code, Some(404));
        server.abort();
    }

    /// 🔒 Y un 200 que no es un PDF tampoco pasa: descargar un HTML de error con nombre
    /// `anexo-i.pdf` es exactamente el fallo mudo que esta ruta existe para no tener.
    #[tokio::test]
    async fn an_answer_that_is_not_a_pdf_is_refused_instead_of_downloaded() {
        let (base, _h, _b, server) =
            cloud_stub(StatusCode::OK, "<html>error de sesión</html>").await;

        let refusal = fetch_model_pdf(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &model_fields(),
        )
        .await
        .unwrap_err();

        assert_eq!(refusal.status_code, Some(200));
        assert!(refusal.detail.contains("not a pdf"), "{}", refusal.detail);
        server.abort();
    }

    /// El modelo no se pide sin saber para quién es: los dos NIF son lo único que el SaaS no puede
    /// deducir, y un modelo en blanco es un papel que el cliente firma para nada.
    #[test]
    fn the_model_cannot_be_asked_for_without_the_parties() {
        assert_eq!(validate_model_fields(&model_fields()), Ok(()));

        let no_obligado = ModelFields {
            obligado_nif: "  ".into(),
            ..model_fields()
        };
        assert_eq!(
            validate_model_fields(&no_obligado),
            Err("obligado_nif_required")
        );

        let no_signer = ModelFields {
            signer_name: String::new(),
            ..model_fields()
        };
        assert_eq!(validate_model_fields(&no_signer), Err("signer_required"));
    }

    fn model_fields() -> ModelFields {
        ModelFields {
            obligado_nif: "B12345674".into(),
            obligado_name: "Bar Manolo SL".into(),
            obligado_municipio: "Vigo".into(),
            obligado_via: "Rúa do Príncipe".into(),
            obligado_numero: "10".into(),
            signer_nif: "12345678Z".into(),
            signer_name: "Manolo García".into(),
            signer_municipio: String::new(),
            signer_via: String::new(),
            signer_numero: String::new(),
        }
    }

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
}
