//! **The signed Anexo I: captured here, custodied by ERPlora** (hub#817 / saas#1438).
//!
//! ERPlora remits VeriFactu records **on behalf of** the taxpayer, and that needs their signed
//! consent — the Anexo I of the DG AEAT Resolución of 18/12/2024 (BOE-A-2024-27600), under the
//! Convenio 17 of colaboración social. Until now the only way to create one was to call an API by
//! hand: a mechanism with no door.
//!
//! The door goes here, in the Hub, because this is where the go-live happens, this is where the
//! person who signs is standing, and this is the side that knows the **right NIF** — the obligado
//! is the business's `business_tax_id` (what travels as `IDEmisorFactura`), not the identity
//! ERPlora invoices.
//!
//! # Three rules this module exists to hold
//!
//! 1. **The machine token never reaches the browser** (ADR-0003). The screen posts to these routes
//!    and the RUNTIME adds `X-Hub-Token`, exactly like the marketplace and entitlement proxies.
//! 2. **The hub does not keep the documents.** The signature and the DNI copy are read from the
//!    request, composed into the otorgamiento, forwarded, and dropped — nothing is written to a
//!    table. Custody is the SaaS's (personal data, RGPD), and a copy sitting in a hub's database is
//!    a copy in every backup and every blueprint export.
//! 3. **Neither document goes anywhere near a log.** Not their bytes, not their names, not on the
//!    error path — which is the branch that most invites «let me show you what I sent».

use axum::extract::{Multipart, State};
use axum::http::{HeaderMap, StatusCode};
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

/// **The otorgamiento itself** — the text the customer signs, and the text the screen shows.
///
/// In **Spanish and not translated**, deliberately: this is a legal instrument addressed to the
/// Spanish tax authority, modelled on Anexo I of the DG AEAT Resolución of 18/12/2024
/// (BOE-A-2024-27600). Translating it would archive a document that says something the AEAT never
/// wrote. The UI *around* it is localised as usual; this is not UI.
///
/// It lives HERE, in one place, and both readers take it from here: the screen renders it so the
/// customer reads what they are signing (the FAQ requires a form that is *cumplimentado y
/// firmado*, not a link), and [`render_anexo`] freezes it into the archived document. A second
/// copy in the i18n bundle would be the same document saying two things.
///
/// ⚠️ **The literal wording must be checked against BOE-A-2024-27600 before launch.** What is here
/// carries every element the Resolución requires — otorgante, representante, object, legal basis,
/// date and signature — and is faithful to it, but it was written from the analysis in
/// `VERIFACTU-PROVEEDOR`, not copied from the Boletín.
pub const ANEXO_I_TEXT: &str = "\
OTORGAMIENTO DE LA REPRESENTACIÓN DIRECTA A EMPRESA SUMINISTRADORA DE SOFTWARE \
PARA LA REMISIÓN DE REGISTROS DE FACTURACIÓN VERI*FACTU\n\n\
(Modelo del Anexo I de la Resolución de 18 de diciembre de 2024, de la Dirección General \
de la Agencia Estatal de Administración Tributaria — BOE-A-2024-27600)\n\n\
DON/DOÑA {signer_name}, con NIF/NIE {signer_nif}, actuando en nombre propio o como \
representante legal del obligado tributario abajo indicado, OTORGA su representación a \
ERPLORA, en su condición de empresa suministradora del sistema informático de facturación \
que utiliza el obligado tributario, para que en su nombre remita a la Agencia Estatal de \
Administración Tributaria los registros de facturación generados por dicho sistema conforme \
al Reglamento aprobado por el Real Decreto 1007/2023 (VERI*FACTU).\n\n\
OBLIGADO TRIBUTARIO REPRESENTADO: {obligado_name}, con NIF {obligado_nif}.\n\n\
La representación se ejerce al amparo del Convenio de colaboración social número 17, suscrito \
entre la Agencia Estatal de Administración Tributaria y las empresas suministradoras de \
software. El presente otorgamiento se conserva por el representante y sólo se acreditará ante \
la Administración Tributaria cuando ésta lo inste al representante. El representante responde \
de la autenticidad de la firma de la persona otorgante, así como de la copia de su documento \
de identidad que se acompaña.\n\n\
El otorgamiento tiene vigencia indefinida hasta su revocación expresa por el otorgante, que \
podrá efectuarse en cualquier momento y surtirá efecto desde que se comunique.\n";

/// What the person at the till filled in, collected from the browser's multipart.
///
/// `Debug` is **not** derived: this struct holds a scan of somebody's ID card, and a derived
/// `Debug` is how that ends up in a `tracing` line the day somebody adds `?capture`.
#[derive(Default)]
pub struct Capture {
    pub obligado_nif: String,
    pub obligado_name: String,
    pub signer_nif: String,
    pub signer_name: String,
    pub via: String,
    /// The **stroke**, as PNG bytes drawn on the screen's canvas.
    ///
    /// 🔴 The browser sends a signature, **not a document**. The archived otorgamiento is composed
    /// by [`render_anexo`] here in the runtime, so what ERPlora custodies is guaranteed to contain
    /// the actual Anexo I text: a client that posted its own "signed document" could archive a
    /// blank page, a different text, or the signature alone — and the AEAT requires the
    /// *cumplimentación* as much as the *firma*.
    pub signature: Option<Vec<u8>>,
    /// `(file name, bytes)` of the signer's DNI/NIE copy.
    pub dni_copy: Option<(String, Vec<u8>)>,
}

/// Composes the otorgamiento the customer just signed into one self-contained HTML document.
///
/// Self-contained on purpose: the signature travels **inside** it as a `data:` URI, so the archived
/// file opens years later with nothing else next to it. HTML rather than PDF because the hub has
/// no PDF writer, and a document that is complete, readable and stored beats one that needs a
/// dependency to exist — what the Resolución asks for is the completed and signed grant, not a
/// format.
///
/// Every interpolated value is HTML-escaped: a business name with an `&` in it must not be able to
/// change the shape of the document that is about to be archived as legal evidence.
pub fn render_anexo(capture: &Capture, signed_at: &str) -> String {
    let body = ANEXO_I_TEXT
        .replace("{signer_name}", &escape(&capture.signer_name))
        .replace("{signer_nif}", &escape(&capture.signer_nif))
        .replace("{obligado_name}", &escape(&capture.obligado_name))
        .replace("{obligado_nif}", &escape(&capture.obligado_nif));
    let signature = capture
        .signature
        .as_ref()
        .map(|bytes| base64_encode(bytes))
        .unwrap_or_default();
    format!(
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">\
         <title>Otorgamiento de representación — {nif}</title></head><body>\
         <pre style=\"white-space:pre-wrap;font-family:system-ui,sans-serif\">{body}</pre>\
         <p>Firmado el {signed_at}.</p>\
         <p>Firma:</p><img alt=\"Firma del otorgante\" src=\"data:image/png;base64,{signature}\">\
         </body></html>",
        nif = escape(&capture.obligado_nif),
        body = body,
        signed_at = escape(signed_at),
        signature = signature,
    )
}

/// The five characters that could otherwise turn a customer's name into markup.
fn escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

/// Standard base64, for embedding the signature in the document. Small and self-contained rather
/// than one more dependency for sixteen lines.
fn base64_encode(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let b = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        out.push(ALPHABET[(n >> 18) as usize & 63] as char);
        out.push(ALPHABET[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 {
            ALPHABET[(n >> 6) as usize & 63] as char
        } else {
            '='
        });
        out.push(if chunk.len() > 2 {
            ALPHABET[n as usize & 63] as char
        } else {
            '='
        });
    }
    out
}

/// What ERPlora holds, as the hub records it: `(status, instant)`.
///
/// `status` is the control plane's own word (`vigente` / `revocado` / `absent`), copied and not
/// translated — a mapping in the middle is one more place for the two sides to drift, and this
/// value decides whether a business may invoice for real.
pub type GrantState = (String, String);

/// Reads the control plane's answer into what the profile stores.
///
/// The instant is the date **of the state being reported**: when it was revoked if it is revoked,
/// when it was signed otherwise. A body that does not say answers `("absent", "")` — an unreadable
/// answer is not a grant, and the safe reading of "I could not tell" is "you have not signed".
pub fn grant_state_from_cloud(body: &Value) -> GrantState {
    let text = |key: &str| {
        body.get(key)
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string()
    };
    let status = text("status");
    let at = if status == erplora_runtime::fiscal_profile::REPRESENTATION_REVOKED {
        text("revoked_at")
    } else {
        text("signed_at")
    };
    if status.is_empty() {
        return (
            erplora_runtime::fiscal_profile::REPRESENTATION_ABSENT.to_string(),
            String::new(),
        );
    }
    (status, at)
}

/// Everything a capture must carry before it is worth a network call.
///
/// **A tick-box is not a grant.** The AEAT developer FAQ v1.3 (4-12-2025) §16.4 admits a web form
/// and refuses acceptance of terms *without* a signature: it requires «la cumplimentación y
/// **firma** (incluyendo electrónica) del otorgamiento». So the signed document is the subject of
/// this request, and the DNI copy is the other thing ERPlora answers for. Neither is optional.
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
    match &capture.signature {
        None => return Err("signature_required"),
        Some(bytes) if bytes.is_empty() => return Err("signature_required"),
        Some(bytes) if bytes.len() > MAX_DOCUMENT_BYTES => return Err("document_too_large"),
        Some(_) => {}
    }
    match &capture.dni_copy {
        None => return Err("dni_copy_required"),
        Some((_, bytes)) if bytes.is_empty() => return Err("dni_copy_required"),
        Some((_, bytes)) if bytes.len() > MAX_DOCUMENT_BYTES => return Err("document_too_large"),
        Some(_) => {}
    }
    Ok(())
}

/// Drains the browser's multipart into a [`Capture`].
///
/// A field that cannot be read is skipped rather than aborting: [`validate`] is what decides
/// whether what arrived is enough, in one place, so a truncated upload produces "the signed
/// document is missing" and not a parser error nobody can act on.
pub async fn collect(mut multipart: Multipart) -> Capture {
    let mut capture = Capture::default();
    while let Ok(Some(field)) = multipart.next_field().await {
        let name = field.name().unwrap_or_default().to_string();
        match name.as_str() {
            "signature" => {
                if let Ok(bytes) = field.bytes().await {
                    capture.signature = Some(bytes.to_vec());
                }
            }
            "dni_copy" => {
                let file_name = field
                    .file_name()
                    .map(str::to_string)
                    .unwrap_or_else(|| name.clone());
                if let Ok(bytes) = field.bytes().await {
                    capture.dni_copy = Some((file_name, bytes.to_vec()));
                }
            }
            "obligado_nif" | "obligado_name" | "signer_nif" | "signer_name" | "via" => {
                let Ok(value) = field.text().await else {
                    continue;
                };
                let value = value.trim().to_string();
                match name.as_str() {
                    "obligado_nif" => capture.obligado_nif = value,
                    "obligado_name" => capture.obligado_name = value,
                    "signer_nif" => capture.signer_nif = value,
                    "signer_name" => capture.signer_name = value,
                    _ => capture.via = value,
                }
            }
            _ => {}
        }
    }
    capture
}

/// Sends the capture up to the control plane with the MACHINE credential.
///
/// `Ok(body)` is the SaaS's 201 payload (metadata only — it never returns the documents).
/// `Err(message)` names the URL and the status and **stops there**: the request body is a signed
/// PDF and a scan of an ID card, so it is never interpolated into an error, not even on the branch
/// where the response failed to parse.
pub async fn forward_capture(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    capture: &Capture,
    signed_at: &str,
) -> Result<Value, String> {
    let request = cloud_client::CloudClient::new(cloud_base_url).representation_grant(auth);
    let mut form = reqwest::multipart::Form::new()
        .text("obligado_nif", capture.obligado_nif.clone())
        .text("obligado_name", capture.obligado_name.clone())
        .text("signer_nif", capture.signer_nif.clone())
        .text("signer_name", capture.signer_name.clone());
    if !capture.via.is_empty() {
        form = form.text("via", capture.via.clone());
    }
    // THE document: composed here, not received. See `render_anexo`.
    form = form.part(
        "signed_document",
        reqwest::multipart::Part::bytes(render_anexo(capture, signed_at).into_bytes())
            .file_name("anexo-i-otorgamiento.html")
            .mime_str("text/html")
            .map_err(|error| error.to_string())?,
    );
    if let Some((file_name, bytes)) = &capture.dni_copy {
        form = form.part(
            "dni_copy",
            reqwest::multipart::Part::bytes(bytes.clone()).file_name(file_name.clone()),
        );
    }

    let mut sent = http.post(&request.url).multipart(form);
    for (name, value) in request.headers {
        sent = sent.header(name, value);
    }
    let response = sent.send().await.map_err(|error| error.to_string())?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!("{}: status {status}", request.url));
    }
    let body = response.text().await.map_err(|error| error.to_string())?;
    serde_json::from_str(&body)
        .map_err(|error| format!("{}: unreadable answer ({error})", request.url))
}

/// Asks the control plane what it holds. Metadata only — this route never serves the documents.
pub async fn fetch_state(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
) -> Result<Value, String> {
    let request = cloud_client::CloudClient::new(cloud_base_url).representation_grant(auth);
    let mut sent = http.get(&request.url);
    for (name, value) in request.headers {
        sent = sent.header(name, value);
    }
    let response = sent.send().await.map_err(|error| error.to_string())?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!("{}: status {status}", request.url));
    }
    let body = response.text().await.map_err(|error| error.to_string())?;
    serde_json::from_str(&body)
        .map_err(|error| format!("{}: unreadable answer ({error})", request.url))
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
        let runtime = st.runtime.lock().await;
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
            let state = grant_state_from_cloud(&body);
            mirror_into_profile(&st, &state).await;
            Json(json!({
                "ok": true,
                "status": state.0,
                "at": state.1,
                "obligado_nif": body.get("obligado_nif").and_then(Value::as_str).unwrap_or(""),
                // The text the screen must SHOW — served from here so the document the customer
                // reads and the document that gets archived are literally the same string.
                "anexo_text": ANEXO_I_TEXT,
            }))
            .into_response()
        }
        Err(error) => {
            // The stored copy is left untouched: "I could not ask" is not "you have not signed".
            tracing::warn!(%error, "no se pudo consultar el otorgamiento en el plano de control");
            let stored = stored_state(&st).await;
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "ok": false, "error": "cloud_unreachable", "status": stored.0, "at": stored.1 })),
            )
                .into_response()
        }
    }
}

/// `POST /api/fiscal/representation-grant` — the signed Anexo I goes up.
///
/// Auth = an **admin** session: signing away the power to file on the business's behalf is the
/// owner's decision, the same bar as uploading the fiscal certificate or editing the fiscal
/// identity.
pub async fn post_representation_grant(
    State(st): State<AppState>,
    headers: HeaderMap,
    multipart: Multipart,
) -> Response {
    {
        let runtime = st.runtime.lock().await;
        if let Err(error) = auth::require_admin_session(&headers, &st.config, &runtime).await {
            return unauthorized(error);
        }
    }
    let capture = collect(multipart).await;
    if let Err(reason) = validate(&capture) {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
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

    let signed_at = chrono::Utc::now().to_rfc3339();
    match forward_capture(
        &st.http,
        &st.config.cloud_base_url,
        &machine,
        &capture,
        &signed_at,
    )
    .await
    {
        Ok(body) => {
            let state = grant_state_from_cloud(&body);
            mirror_into_profile(&st, &state).await;
            // Signing is what unlocks ERPlora's delegated certificate on the other side
            // (saas#1438): without this the hub would wait for the next heartbeat to discover it,
            // and the person who just signed would be looking at a go-live that still refuses. The
            // refetch spends the same hourly budget as the other triggers.
            crate::fiscal_certificate::refetch_after_grant(&st);
            // Status only. Not the NIF of the signer, not a byte of either document.
            tracing::info!(status = %state.0, "otorgamiento de representación registrado");
            (
                StatusCode::CREATED,
                Json(json!({ "ok": true, "status": state.0, "at": state.1 })),
            )
                .into_response()
        }
        Err(error) => {
            // `error` never carries the request or the response body (see `forward_capture`).
            tracing::warn!(%error, "el plano de control rechazó el otorgamiento");
            (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "ok": false, "error": "cloud_rejected" })),
            )
                .into_response()
        }
    }
}

/// Writes the control plane's answer into `_hub_fiscal_profile`. Best-effort: a write that fails
/// leaves the previous copy, and the next read of the screen tries again.
async fn mirror_into_profile(st: &AppState, state: &GrantState) {
    let runtime = st.runtime.lock().await;
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
    let runtime = st.runtime.lock().await;
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
        REPRESENTATION_ABSENT, REPRESENTATION_REVOKED, REPRESENTATION_VIGENTE,
    };
    use std::sync::{Arc, Mutex};

    const SIGNATURE_PNG: &[u8] = b"\x89PNG\r\n the stroke Manolo drew";
    const DNI_SCAN: &[u8] = b"\xff\xd8\xff\xe0 the scan of an ID card";
    const SIGNED_AT: &str = "2026-08-11T09:00:00Z";
    const MACHINE_TOKEN: &str = "machine-tok";

    fn machine_auth() -> cloud_client::Auth {
        cloud_client::Auth::HubToken {
            hub_id: "hub-test".into(),
            token: MACHINE_TOKEN.into(),
        }
    }

    fn full_capture() -> Capture {
        Capture {
            obligado_nif: "B12345678".into(),
            obligado_name: "Bar Manolo SL".into(),
            signer_nif: "12345678Z".into(),
            signer_name: "Manolo García".into(),
            via: "convenio_17".into(),
            signature: Some(SIGNATURE_PNG.to_vec()),
            dni_copy: Some(("dni.jpg".into(), DNI_SCAN.to_vec())),
        }
    }

    // ── What a capture must carry ─────────────────────────────────────────────────────────────

    /// 🔴 **A tick-box is not a grant** (AEAT developer FAQ v1.3 §16.4): what the form has to
    /// collect is the *cumplimentación y **firma*** of the otorgamiento, plus the DNI copy ERPlora
    /// answers for. Neither is optional, and the obligado has no fallback — the only other NIF
    /// around is the payer's, which is a different taxpayer.
    #[test]
    fn a_capture_is_refused_unless_it_carries_the_signature_and_the_dni() {
        assert_eq!(validate(&full_capture()), Ok(()));

        let without_signature = Capture {
            signature: None,
            ..full_capture()
        };
        assert_eq!(validate(&without_signature), Err("signature_required"));

        let without_dni = Capture {
            dni_copy: None,
            ..full_capture()
        };
        assert_eq!(validate(&without_dni), Err("dni_copy_required"));

        let without_obligado = Capture {
            obligado_nif: "  ".into(),
            ..full_capture()
        };
        assert_eq!(validate(&without_obligado), Err("obligado_nif_required"));

        let without_signer = Capture {
            signer_name: String::new(),
            ..full_capture()
        };
        assert_eq!(validate(&without_signer), Err("signer_required"));
    }

    /// An EMPTY file is not a signature. A picker that produced a zero-byte file would otherwise
    /// archive a grant with nothing in it and the hub would go live on it.
    #[test]
    fn an_empty_document_does_not_count_as_uploaded() {
        let empty = Capture {
            signature: Some(Vec::new()),
            ..full_capture()
        };
        assert_eq!(validate(&empty), Err("signature_required"));
    }

    /// Refused HERE and not only by the SaaS: crossing the network to be told no spends the hub's
    /// quota and holds two copies of the upload in memory meanwhile.
    #[test]
    fn an_oversized_document_is_refused_before_it_crosses_the_network() {
        let huge = Capture {
            dni_copy: Some(("dni.jpg".into(), vec![0u8; MAX_DOCUMENT_BYTES + 1])),
            ..full_capture()
        };
        assert_eq!(validate(&huge), Err("document_too_large"));
    }

    // ── The document that gets archived ───────────────────────────────────────────────────────

    /// 🔴 **What is archived is the OTORGAMIENTO, not a signature.** The AEAT requires the
    /// *cumplimentación* as much as the *firma* (FAQ v1.3 §16.4), so the document has to carry the
    /// Anexo I text with the parties filled in — and it is composed here rather than accepted from
    /// the browser precisely so it always does.
    #[test]
    fn the_archived_document_carries_the_anexo_text_the_parties_and_the_signature() {
        let document = render_anexo(&full_capture(), SIGNED_AT);

        assert!(
            document.contains("VERI*FACTU"),
            "falta el objeto del otorgamiento"
        );
        assert!(
            document.contains("Convenio de colaboración social número 17"),
            "falta la vía"
        );
        assert!(
            document.contains("BOE-A-2024-27600"),
            "falta el modelo que sigue"
        );
        // Las dos partes, cada una con su NIF: el firmante es una PERSONA y el obligado la empresa.
        assert!(document.contains("Manolo García"));
        assert!(document.contains("12345678Z"));
        assert!(document.contains("Bar Manolo SL"));
        assert!(document.contains("B12345678"));
        assert!(document.contains(SIGNED_AT), "falta la fecha de la firma");
        // Y el trazo, DENTRO del documento: se archiva un fichero que se abre solo.
        assert!(document.contains("data:image/png;base64,"));
        assert!(document.contains(&base64_encode(SIGNATURE_PNG)));
    }

    /// El texto va **en español**: es un instrumento dirigido a la AEAT, no interfaz. Traducirlo
    /// archivaría un documento que dice algo que la Agencia nunca escribió.
    #[test]
    fn the_otorgamiento_is_in_spanish_and_leaves_no_placeholder_behind() {
        let document = render_anexo(&full_capture(), SIGNED_AT);

        assert!(document.contains("OTORGA su representación"));
        assert!(
            !document.contains('{'),
            "quedó un placeholder sin sustituir: {document}"
        );
    }

    /// 🔒 Un nombre con `<` no puede reescribir el documento que se archiva como prueba legal.
    #[test]
    fn a_business_name_cannot_inject_markup_into_the_evidence() {
        let hostile = Capture {
            obligado_name: "<script>alert(1)</script> SL".into(),
            ..full_capture()
        };

        let document = render_anexo(&hostile, SIGNED_AT);

        assert!(
            !document.contains("<script>"),
            "inyección de markup: {document}"
        );
        assert!(document.contains("&lt;script&gt;"));
    }

    /// El base64 de la firma tiene que ser base64 de verdad, o el `data:` URI no pinta nada — y el
    /// documento archivado se quedaría sin la firma sin que nadie se entere hasta que la AEAT
    /// pregunte.
    #[test]
    fn the_signature_is_encoded_as_standard_base64_with_its_padding() {
        assert_eq!(base64_encode(b""), "");
        assert_eq!(base64_encode(b"f"), "Zg==");
        assert_eq!(base64_encode(b"fo"), "Zm8=");
        assert_eq!(base64_encode(b"foo"), "Zm9v");
        assert_eq!(base64_encode(b"foob"), "Zm9vYg==");
        assert_eq!(base64_encode(b"foobar"), "Zm9vYmFy");
        assert_eq!(base64_encode(&[0xff, 0xfe, 0xfd]), "//79");
    }

    // ── Reading the control plane's answer ────────────────────────────────────────────────────

    /// The instant reported is the one **of the state**: revoked shows when it was revoked.
    #[test]
    fn the_reported_instant_belongs_to_the_state_being_reported() {
        let vigente =
            json!({"status": "vigente", "signed_at": "2026-08-11T09:00:00Z", "revoked_at": null});
        assert_eq!(
            grant_state_from_cloud(&vigente),
            (
                REPRESENTATION_VIGENTE.to_string(),
                "2026-08-11T09:00:00Z".to_string()
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
            r#"{"status": "vigente", "signed_at": "2026-08-11T09:00:00Z"}"#,
        )
        .await;

        forward_capture(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &full_capture(),
            SIGNED_AT,
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

    /// The documents DO travel — this is the request that archives them — and they travel with the
    /// obligado the hub declared, which is the fact the SaaS has no other way of knowing.
    #[tokio::test]
    async fn the_documents_and_the_declared_obligado_reach_the_control_plane() {
        let (base, _headers, body, server) = cloud_stub(
            StatusCode::CREATED,
            r#"{"status": "vigente", "signed_at": "2026-08-11T09:00:00Z"}"#,
        )
        .await;

        forward_capture(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &full_capture(),
            SIGNED_AT,
        )
        .await
        .unwrap();

        let sent = body.lock().unwrap().clone();
        let sent = String::from_utf8_lossy(&sent);
        assert!(
            sent.contains("B12345678"),
            "el obligado declarado tiene que viajar"
        );
        assert!(
            sent.contains("VERI*FACTU"),
            "el texto del Anexo I tiene que viajar DENTRO del documento"
        );
        assert!(
            sent.contains("name=\"dni_copy\""),
            "la copia del DNI tiene que viajar"
        );
        server.abort();
    }

    /// 🔒 **A failure must not quote what was sent.** This is the branch that most invites «here is
    /// the body I could not parse» — and the body of this request is a signed document and a scan
    /// of an ID card.
    #[tokio::test]
    async fn a_rejection_never_quotes_the_documents_it_was_carrying() {
        let (base, _headers, _body, server) = cloud_stub(
            StatusCode::INTERNAL_SERVER_ERROR,
            r#"{"detail": "boom", "echo": "Bar Manolo SL — the scan of an ID card"}"#,
        )
        .await;

        let error = forward_capture(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &full_capture(),
            SIGNED_AT,
        )
        .await
        .unwrap_err();

        assert!(
            !error.contains("Bar Manolo"),
            "el error arrastra el documento: {error}"
        );
        assert!(
            !error.contains("Manolo"),
            "el error arrastra al firmante: {error}"
        );
        assert!(
            !error.contains("ID card"),
            "el error arrastra el DNI: {error}"
        );
        // Y sigue siendo diagnosticable.
        assert!(
            error.contains("500"),
            "el error debería nombrar el status: {error}"
        );
        server.abort();
    }

    /// 🔒 The same rule on an unreadable 2xx: a body that did not parse is exactly the body most
    /// likely to hold something personal.
    #[tokio::test]
    async fn an_unreadable_answer_is_not_echoed_either() {
        let (base, _headers, _body, server) =
            cloud_stub(StatusCode::CREATED, "not json at all — Bar Manolo SL").await;

        let error = forward_capture(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &full_capture(),
            SIGNED_AT,
        )
        .await
        .unwrap_err();

        assert!(!error.contains("Bar Manolo"), "{error}");
        server.abort();
    }

    /// 🔒 **Nothing personal reaches the logs on the happy path** — the one that runs on every
    /// capture. Captures the whole `tracing` output of a forward and greps it.
    #[tokio::test]
    async fn forwarding_a_capture_writes_nothing_personal_to_the_logs() {
        let (base, _headers, _body, server) = cloud_stub(
            StatusCode::CREATED,
            r#"{"status": "vigente", "signed_at": "2026-08-11T09:00:00Z"}"#,
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
                &full_capture(),
                SIGNED_AT,
            )
            .await
            .unwrap();
        }

        let logs = String::from_utf8_lossy(&captured.lock().unwrap().clone()).into_owned();
        for secret in ["the stroke", "PNG", "ID card", "12345678Z", MACHINE_TOKEN] {
            assert!(
                !logs.contains(secret),
                "fuga de {secret:?} a los logs: {logs}"
            );
        }
        server.abort();
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
