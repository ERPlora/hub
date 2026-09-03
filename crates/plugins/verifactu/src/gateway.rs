//! The gateway leg of the transmission (hub#1432, hub#985 §1): the hub-without-certificate road.
//!
//! The engine builds the SAME SOAP envelope as ever and, instead of presenting a certificate to
//! the AEAT itself, POSTs the exact bytes to the fiscal cell, which authenticates the CHANNEL
//! with ERPlora's Sello and forwards them untouched. **The body authorises nothing** — the
//! Bearer inside [`GatewayAccess`] does — but the body's `environment` SELECTS the destination:
//! the module's config decides it (one-way go-live), the cell obeys it, and `production` only
//! opens when the token carries the grant (verifactu-gateway#42).
//!
//! This file is the ONLY place that names the cell's path AND the control-plane path that
//! authorises a burst through it: since hub#1459 the core lends two GENERIC primitives —
//! `machine_identity` (who this hub is on the wire) and `cloud_call` (call my cloud with my
//! machine credential) — and knows nothing about fiscal gateways. Which path, what the answer
//! means, how long the authorisation is good for and what a 409 implies are all decisions of the
//! regime, so they live here (the hub#1407 guard keeps regime names out of the base, and this
//! crate is the regime).

use std::collections::HashMap;
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use base64::Engine as _;
use erplora_runtime::cloud_call::{CloudMethod, CloudRequest};
use erplora_runtime::errors::RuntimeError;
use erplora_runtime::native::NativeHost;
use sha2::Digest as _;

use crate::engine::VerifactuError;

/// `docs/api.md` of the cell: the envelope schema this crate speaks.
pub(crate) const SCHEMA_VERSION: u32 = 1;

/// 30 s of AEAT timeout ride INSIDE the cell's leg, so this side waits longer than the sum —
/// a shorter budget here would abandon a delivery the cell is still completing (504 semantics).
const GATEWAY_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(75);

/// The transmission path, appended HERE and never in the core. Tolerates a base URL with or
/// without a trailing slash; anything else in the URL is the control plane's business.
pub(crate) fn transmissions_url(base: &str) -> String {
    format!("{}/v1/verifactu/transmissions", base.trim_end_matches('/'))
}

/// What travels: the exact XML bytes plus the identity/destination facts the cell cross-checks.
pub(crate) struct GatewayEnvelope<'a> {
    pub hub_id: &'a str,
    pub obligado_nif: &'a str,
    /// The record's chain environment (`destination_of`): `testing` → prewww, `production` → the
    /// real AEAT — and the latter only passes with the grant aboard the token.
    pub environment: &'a str,
    /// Stable across retries — the record id. A 504 is retried with the SAME bytes and id.
    pub transmission_id: &'a str,
    pub xml: &'a str,
}

/// The digest of an exact XML payload, lowercase hex.
///
/// ONE definition on purpose (verifactu#75). Three places need this number and they must never be
/// able to disagree: the envelope that asks the cell to echo it back as `request_sha256`, the
/// canary in [`post_transmission`] that compares the two, and the `xml_sha256` column the record
/// keeps so a later reader can tell whether the stored XML still is the XML that travelled.
pub(crate) fn xml_sha256(xml: &str) -> String {
    sha2::Sha256::digest(xml.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

impl GatewayEnvelope<'_> {
    /// The digest of the EXACT bytes that travel. The cell recomputes it over what it decodes
    /// and echoes it back as `request_sha256`; comparing the two is the canary of ADR-0320 §2
    /// («el gateway NO modifica el XML») — see [`post_transmission`].
    pub(crate) fn xml_sha256(&self) -> String {
        xml_sha256(self.xml)
    }
}

pub(crate) fn envelope_json(envelope: &GatewayEnvelope<'_>) -> serde_json::Value {
    let xml_sha256 = envelope.xml_sha256();
    serde_json::json!({
        "schema_version": SCHEMA_VERSION,
        "hub_id": envelope.hub_id,
        "obligado_nif": envelope.obligado_nif,
        "environment": envelope.environment,
        "transmission_id": envelope.transmission_id,
        "xml_b64": base64::engine::general_purpose::STANDARD.encode(envelope.xml.as_bytes()),
        "xml_sha256": xml_sha256,
    })
}

/// How one gateway refusal maps onto the engine's machine (the cell's `docs/api.md` table):
/// everything lands in the contingency backoff except a 401, which gets ONE in-line retry with a
/// fresh token first — the Bearer lives 300 s and a queue drain can outlive it legitimately.
fn refusal_error(status: u16, code: &str, message: &str) -> VerifactuError {
    VerifactuError::Transmission(format!("pasarela fiscal: {status} {code}: {message}"))
}

/// A 200 whose RECEIPT does not hold up. Same treatment as a refusal —contingency with backoff,
/// never `::Tls`— and a stable `code` an operator can grep: the prose is for humans, the code is
/// what a test and an alert assert on (ADR-0055).
fn receipt_error(code: &str, detail: &str) -> VerifactuError {
    VerifactuError::Transmission(format!("pasarela fiscal: recibo inválido ({code}): {detail}"))
}

/// POSTs the envelope to the cell and hands back the AEAT's raw SOAP body — the SAME string
/// `aeat::post_soap` would have returned, so the parse/classify/persist chain downstream does
/// not know which road the bytes took.
///
/// A 401 invalidates the cached Bearer through the host and retries ONCE with a fresh access;
/// everything else maps to [`VerifactuError::Transmission`] — never `::Tls`, which on this road
/// would send an operator to renew a certificate the hub does not even have: the mTLS against the
/// AEAT happens in the CELL, with a Seal nobody here can see, let alone fix.
pub(crate) async fn transmit_via_gateway(
    host: &dyn NativeHost,
    hub_id: &str,
    access: &GatewayAccess,
    envelope: &GatewayEnvelope<'_>,
) -> Result<String, VerifactuError> {
    match post_transmission(access, envelope).await? {
        PostOutcome::AeatBody(body) => Ok(body),
        PostOutcome::TokenRefused { code, message } => {
            // One fresh token, one retry. A second 401 is a real refusal.
            invalidate_token(hub_id).await;
            let fresh = resolve_access(host, hub_id)
                .await
                .map_err(|e| VerifactuError::Transmission(format!("pasarela fiscal: {e}")))?
                .ok_or_else(|| refusal_error(401, &code, &message))?;
            match post_transmission(&fresh, envelope).await? {
                PostOutcome::AeatBody(body) => Ok(body),
                PostOutcome::TokenRefused { code, message } => {
                    Err(refusal_error(401, &code, &message))
                }
            }
        }
    }
}

enum PostOutcome {
    AeatBody(String),
    TokenRefused { code: String, message: String },
}

async fn post_transmission(
    access: &GatewayAccess,
    envelope: &GatewayEnvelope<'_>,
) -> Result<PostOutcome, VerifactuError> {
    let client = reqwest::Client::builder()
        .use_rustls_tls()
        .identity(access.identity.clone())
        .add_root_certificate(reqwest::Certificate::from_pem(&access.ca_pem).map_err(|e| {
            VerifactuError::Transmission(format!("CA de la pasarela ilegible: {e}"))
        })?)
        .timeout(GATEWAY_TIMEOUT)
        .build()
        .map_err(|e| VerifactuError::Transmission(format!("cliente mTLS de la pasarela: {e}")))?;

    let response = client
        .post(transmissions_url(&access.url))
        .header("Authorization", format!("Bearer {}", access.token))
        .header("Idempotency-Key", envelope.transmission_id)
        .header("Content-Type", "application/json")
        .body(envelope_json(envelope).to_string())
        .send()
        .await
        .map_err(|e| VerifactuError::Transmission(format!("conexión con la pasarela: {e}")))?;

    let status = response.status().as_u16();
    let body = response
        .text()
        .await
        .map_err(|e| VerifactuError::Transmission(format!("respuesta de la pasarela: {e}")))?;

    if status == 200 {
        let value: serde_json::Value = serde_json::from_str(&body).map_err(|e| {
            VerifactuError::Transmission(format!("recibo de la pasarela ilegible: {e}"))
        })?;
        // ── The canary of ADR-0320 (hub#1461) ─────────────────────────────────────────────────
        // The cell recomputes the sha256 OVER THE BYTES IT DECODED and echoes it here. That it
        // equals ours is the only proof available on this side of the wire that what reached the
        // AEAT are the bytes this SIF produced — hash and chain included. §2 of the ADR («the
        // gateway does NOT modify the XML») stops being a promise and becomes a per-delivery check.
        //
        // It runs BEFORE looking at the AEAT body on purpose: if the bytes are not ours, neither
        // is the verdict riding with them, and filing it would be exactly the silent send with
        // different bytes this exists to prevent. The record goes to contingency with its reason
        // visible, like a 504 — what the AEAT ended up holding is unknown.
        let sent = envelope.xml_sha256();
        match value.get("request_sha256").and_then(|v| v.as_str()) {
            // Fails CLOSED: with no field there is no canary, and skipping the check when it is
            // missing cannot tell a healthy cell from an intermediary that stripped it.
            None => {
                return Err(receipt_error(
                    "receipt_without_request_sha256",
                    "la pasarela no devolvió el digest de lo que transmitió",
                ));
            }
            // Compared case-insensitively: the contract asks for lowercase hex, but a difference
            // in case is not a difference in bytes, and refusing one would stop the filing.
            Some(echoed) if !echoed.eq_ignore_ascii_case(&sent) => {
                return Err(receipt_error(
                    "request_digest_mismatch",
                    &format!(
                        "los bytes transmitidos no son los enviados: enviado {sent}, \
                         recibo {echoed}"
                    ),
                ));
            }
            Some(_) => {}
        }
        let b64 = value
            .get("aeat_response_b64")
            .and_then(|v| v.as_str())
            .ok_or_else(|| {
                VerifactuError::Transmission("recibo de la pasarela sin aeat_response_b64".into())
            })?;
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(b64)
            .map_err(|e| {
                VerifactuError::Transmission(format!("aeat_response_b64 no es base64: {e}"))
            })?;
        return String::from_utf8(bytes)
            .map(PostOutcome::AeatBody)
            .map_err(|e| {
                VerifactuError::Transmission(format!("respuesta AEAT no UTF-8 vía pasarela: {e}"))
            });
    }

    // The error contract is `{code, message}` — public material, safe to surface on the record.
    let (code, message) = match serde_json::from_str::<serde_json::Value>(&body) {
        Ok(value) => (
            value
                .get("code")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_owned(),
            value
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_owned(),
        ),
        Err(_) => (String::new(), String::new()),
    };
    if status == 401 {
        return Ok(PostOutcome::TokenRefused { code, message });
    }
    // 504 = the AEAT may HAVE the record: the retry (same bytes, same id) is what resolves it,
    // and the marker in the message lets an operator recognise the indeterminate case.
    let annotated = if status == 504 {
        format!("{message} [indeterminate: reenviar los MISMOS bytes]")
    } else {
        message
    };
    Err(refusal_error(status, &code, &annotated))
}

// ---------------------------------------------------------------------------------------------
// Getting authorised to use the cell (hub#1459: this used to be `NativeHost::fiscal_gateway_access`
// plus a broker in the server — a door named after ONE caller. The host now lends the identity and
// the call; the regime does the rest).
// ---------------------------------------------------------------------------------------------

/// The control-plane path that authorises one burst through the cell. It lives HERE because it is
/// regime knowledge: the engine chooses it, the host only puts the destination and the credential.
pub(crate) const TOKEN_PATH: &str = "/api/v1/hub/device/fiscal/gateway-token/";

/// A token handed out with less than this left could expire in flight between here and the cell.
const EXPIRY_MARGIN: Duration = Duration::from_secs(30);
/// After a failed mint, wait before asking again: the mint quota is 60/h and a contingency queue
/// draining N records against a fallen SaaS must not burn it.
const FAILURE_BRAKE: Duration = Duration::from_secs(10);

/// Everything ONE transmission through the cell needs. Opaque to the transport below: it carries
/// no machine credential and does not say how any of it was obtained.
#[derive(Clone)]
pub(crate) struct GatewayAccess {
    /// The cell's base URL, as the control plane answered it (`gateway_url`). ONE for every hub,
    /// behind the private LB — the hub reads no env for this (saas#1794).
    pub url: String,
    /// The short-lived Bearer. NEVER in a log line — the manual `Debug` below is the guard.
    pub token: String,
    /// The hub's mTLS client identity (key born on the hub, `gateway_identity.rs`).
    pub identity: reqwest::Identity,
    /// PEM of the internal CA that anchors the cell's SERVER certificate.
    pub ca_pem: Vec<u8>,
    /// **Who the control plane SIGNED as the presenter of this burst** — the `Representante` of
    /// every envelope that goes out through it (hub#1460). It travels on the access and not on a
    /// second lookup on purpose: «who presents?» is the same question as «is the road open, and
    /// with what?», and asking it twice is how hub#317/#318/#319/#470 kept coming back.
    pub presenter_nif: String,
    pub presenter_name: String,
}

impl GatewayAccess {
    /// The signed presenter, in the shape the envelope builder takes.
    pub(crate) fn presenter(&self) -> crate::aeat::Presenter<'_> {
        crate::aeat::Presenter {
            nif: &self.presenter_nif,
            name: &self.presenter_name,
        }
    }
}

impl std::fmt::Debug for GatewayAccess {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // The token is a bearer credential and the identity wraps a private key: neither has any
        // business in a Debug dump. The URL alone is enough to recognise the value in a log.
        f.debug_struct("GatewayAccess")
            .field("url", &self.url)
            .field("token", &"[redacted]")
            .field("ca_pem_bytes", &self.ca_pem.len())
            .finish_non_exhaustive()
    }
}

/// What `POST /api/v1/hub/device/fiscal/gateway-token/` answers (saas#1794: it AUTHORISES, it
/// does not route — there is no `environment` field any more; the Hub stamps the environment in
/// each envelope from its own fiscal config).
pub(crate) struct GatewayToken {
    pub token: String,
    pub expires_in: i64,
    pub gateway_url: String,
    pub obligado_nif: String,
    pub grant_version: Option<i64>,
    pub presenter_nif: String,
    pub presenter_name: String,
    pub mtls_common_name: String,
}

impl std::fmt::Debug for GatewayToken {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // The bearer is the one field that must never reach a log; everything else is public.
        f.debug_struct("GatewayToken")
            .field("token", &"[redacted]")
            .field("gateway_url", &self.gateway_url)
            .field("mtls_common_name", &self.mtls_common_name)
            .finish_non_exhaustive()
    }
}

impl GatewayToken {
    /// Parses the 200 body. Field-by-field on purpose (no derive): the error names the FIELD
    /// that was missing, never the body — which carries the bearer.
    pub(crate) fn parse(body: &str) -> std::result::Result<Self, String> {
        let value: serde_json::Value =
            serde_json::from_str(body).map_err(|e| format!("respuesta ilegible ({e})"))?;
        let text = |name: &str| -> std::result::Result<String, String> {
            value
                .get(name)
                .and_then(|v| v.as_str())
                .map(str::to_owned)
                .filter(|s| !s.is_empty())
                .ok_or_else(|| format!("respuesta sin el campo `{name}`"))
        };
        Ok(Self {
            token: text("token")?,
            expires_in: value
                .get("expires_in")
                .and_then(|v| v.as_i64())
                .unwrap_or(300),
            gateway_url: text("gateway_url")?,
            obligado_nif: text("obligado_nif")?,
            grant_version: value.get("grant_version").and_then(|v| v.as_i64()),
            presenter_nif: text("presenter_nif")?,
            presenter_name: text("presenter_name")?,
            mtls_common_name: text("mtls_common_name")?,
        })
    }

    fn clone_token(&self) -> Self {
        Self {
            token: self.token.clone(),
            expires_in: self.expires_in,
            gateway_url: self.gateway_url.clone(),
            obligado_nif: self.obligado_nif.clone(),
            grant_version: self.grant_version,
            presenter_nif: self.presenter_nif.clone(),
            presenter_name: self.presenter_name.clone(),
            mtls_common_name: self.mtls_common_name.clone(),
        }
    }
}

struct CachedToken {
    token: GatewayToken,
    fresh_until: Instant,
}

/// Cache + brake, keyed by hub. Keyed and not global because the cached value is a credential
/// minted FOR one hub: a runtime that ever hosts two would otherwise hand the second hub the
/// first one's bearer, and the cross-check below would be the only thing between that and the
/// cell. The broker this replaced kept one unkeyed slot.
#[derive(Default)]
struct HubTokens {
    cached: Option<CachedToken>,
    last_failure: Option<Instant>,
}

fn token_cache() -> &'static tokio::sync::Mutex<HashMap<String, HubTokens>> {
    static CACHE: OnceLock<tokio::sync::Mutex<HashMap<String, HubTokens>>> = OnceLock::new();
    CACHE.get_or_init(Default::default)
}

/// The cell refused the Bearer in flight (401): drop the cached token so the next
/// [`resolve_access`] mints a fresh one.
pub(crate) async fn invalidate_token(hub_id: &str) {
    token_cache().lock().await.remove(hub_id);
}

/// What the control plane answered about this hub's road.
enum TokenAnswer {
    Minted(GatewayToken),
    /// 409 `own_certificate_direct`: this hub holds its own certificate and transmits direct.
    /// An answer, not an error — the caller reports «gateway route not applicable».
    GoDirect,
    /// This hub cannot reach its cloud at all (bootstrap never finished, embedded runtime).
    NoCloud,
}

/// One mint through the host's generic primitive. The machine credential rides headers this crate
/// never sees; the body of a non-2xx is summarised by STATUS only — it may carry a bearer on a
/// proxy mishap, and the delegated-certificate fetch (retired in hub#1435) learned it first.
async fn mint_token(
    host: &dyn NativeHost,
    hub_id: &str,
) -> std::result::Result<TokenAnswer, String> {
    let answer = host
        .cloud_call(CloudRequest {
            method: CloudMethod::Post,
            path: TOKEN_PATH.to_owned(),
            body: None,
        })
        .await
        .map_err(|e| e.to_string())?;
    let Some(response) = answer else {
        return Ok(TokenAnswer::NoCloud);
    };
    if response.status == 409 {
        return Ok(TokenAnswer::GoDirect);
    }
    if !(200..300).contains(&response.status) {
        return Err(format!("{TOKEN_PATH}: status {} ({hub_id})", response.status));
    }
    GatewayToken::parse(&response.body)
        .map(TokenAnswer::Minted)
        .map_err(|e| format!("{TOKEN_PATH}: {e}"))
}

/// The cached-or-minted authorisation for `hub_id`.
async fn token(
    host: &dyn NativeHost,
    hub_id: &str,
) -> std::result::Result<Option<GatewayToken>, String> {
    let mut cache = token_cache().lock().await;
    let entry = cache.entry(hub_id.to_owned()).or_default();
    if let Some(cached) = &entry.cached {
        if cached.fresh_until > Instant::now() {
            return Ok(Some(cached.token.clone_token()));
        }
    }
    if let Some(last_failure) = entry.last_failure {
        if last_failure.elapsed() < FAILURE_BRAKE {
            return Err(
                "la última petición de token falló hace un instante; frenando para no quemar la cuota"
                    .to_owned(),
            );
        }
    }
    match mint_token(host, hub_id).await {
        Ok(TokenAnswer::Minted(minted)) => {
            let margin = Duration::from_secs(minted.expires_in.max(31) as u64) - EXPIRY_MARGIN;
            entry.cached = Some(CachedToken {
                token: minted.clone_token(),
                fresh_until: Instant::now() + margin,
            });
            entry.last_failure = None;
            Ok(Some(minted))
        }
        Ok(TokenAnswer::GoDirect) | Ok(TokenAnswer::NoCloud) => {
            entry.cached = None;
            entry.last_failure = None;
            Ok(None)
        }
        Err(error) => {
            entry.last_failure = Some(Instant::now());
            Err(error)
        }
    }
}

/// **Is the cell road open for this hub, and with what?** `Ok(None)` = it is not (nothing
/// enrolled, no cloud, or the control plane says this hub goes direct). `Err` = it should be and
/// something broke — the caller surfaces it on the record and the queue stays put.
pub(crate) async fn resolve_access(
    host: &dyn NativeHost,
    hub_id: &str,
) -> erplora_runtime::errors::Result<Option<GatewayAccess>> {
    // Local identity FIRST: without it there is nothing to present at the ingress, and the
    // control-plane quota must not be spent asking for a token nobody can use.
    let Some(machine) = host.machine_identity(hub_id).await? else {
        return Ok(None);
    };

    let token = token(host, hub_id)
        .await
        .map_err(|error| RuntimeError::Certificate(format!("gateway token: {error}")))?;
    let Some(token) = token else {
        return Ok(None);
    };

    // The control plane and this hub must agree on WHO this machine is: a mismatch means an
    // identity enrolled for another hub, and the ingress would refuse it anyway — with a far
    // less actionable message.
    if token.mtls_common_name != machine.common_name {
        return Err(RuntimeError::Certificate(format!(
            "gateway token: el plano de control espera '{}' y este hub es '{}'",
            token.mtls_common_name, machine.common_name
        )));
    }

    Ok(Some(GatewayAccess {
        url: token.gateway_url,
        token: token.token,
        identity: machine.identity,
        ca_pem: machine.ca_pem,
        presenter_nif: token.presenter_nif,
        presenter_name: token.presenter_name,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The envelope must speak the cell's contract to the byte: schema 1, STANDARD base64,
    /// lowercase-hex sha256 of the exact bytes, and the record id as transmission id.
    #[test]
    fn the_envelope_matches_the_cell_contract() {
        let xml = "<soapenv:Envelope>exact bytes</soapenv:Envelope>";
        let value = envelope_json(&GatewayEnvelope {
            hub_id: "hub-1",
            obligado_nif: "B12345678",
            environment: "testing",
            transmission_id: "record-42",
            xml,
        });

        assert_eq!(value["schema_version"], 1);
        assert_eq!(value["hub_id"], "hub-1");
        assert_eq!(value["obligado_nif"], "B12345678");
        assert_eq!(value["environment"], "testing");
        assert_eq!(value["transmission_id"], "record-42");
        let decoded = base64::engine::general_purpose::STANDARD
            .decode(value["xml_b64"].as_str().unwrap())
            .unwrap();
        assert_eq!(decoded, xml.as_bytes(), "the EXACT bytes travel");
        let sha = value["xml_sha256"].as_str().unwrap();
        assert_eq!(sha.len(), 64);
        assert_eq!(
            sha,
            sha.to_lowercase(),
            "lowercase hex, as the cell demands"
        );
        let recomputed: String = sha2::Sha256::digest(xml.as_bytes())
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        assert_eq!(sha, recomputed);
    }

    /// The path is appended here and only here, and a trailing slash does not double.
    #[test]
    fn the_transmissions_url_tolerates_both_base_shapes() {
        assert_eq!(
            transmissions_url("https://cell.internal"),
            "https://cell.internal/v1/verifactu/transmissions"
        );
        assert_eq!(
            transmissions_url("https://cell.internal/"),
            "https://cell.internal/v1/verifactu/transmissions"
        );
    }

    /// One canned HTTP answer per accepted connection, in order. Plain HTTP on purpose: the
    /// mTLS handshake belongs to the REAL cell (and to the PRE end-to-end); what this pins is
    /// the transport glue — receipt decoding and the 401 semantics.
    async fn canned_cell(answers: Vec<String>) -> String {
        use tokio::io::{AsyncReadExt as _, AsyncWriteExt as _};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move {
            for answer in answers {
                let Ok((mut socket, _)) = listener.accept().await else {
                    return;
                };
                let mut buffer = [0u8; 65536];
                let _ = socket.read(&mut buffer).await;
                let _ = socket.write_all(answer.as_bytes()).await;
                let _ = socket.shutdown().await;
            }
        });
        format!("http://{address}")
    }

    fn http_json(status: &str, body: &str) -> String {
        format!(
            "HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
            body.len()
        )
    }

    /// The exact bytes every canned transmission of this module puts on the wire. The cell
    /// recomputes THEIR digest and echoes it, so a receipt quoting anything else is not ours.
    const SENT_XML: &str = "<x/>";

    fn digest_of(xml: &str) -> String {
        sha2::Sha256::digest(xml.as_bytes())
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }

    /// A receipt as the REAL cell answers it: `request_sha256` is the digest of the bytes it
    /// decoded, so on the happy path it equals the hub's own. This is the POSITIVE control of
    /// the canary — if the check were wrong, every honest delivery below would go red.
    fn receipt_with(aeat_body: &str) -> String {
        receipt_quoting(&digest_of(SENT_XML), aeat_body)
    }

    /// The same receipt with the echoed digest under the caller's control, to forge the shapes
    /// the canary must refuse.
    fn receipt_quoting(request_sha256: &str, aeat_body: &str) -> String {
        let mut receipt = receipt_without_digest(aeat_body);
        receipt["request_sha256"] = serde_json::Value::String(request_sha256.to_owned());
        receipt.to_string()
    }

    fn receipt_without_digest(aeat_body: &str) -> serde_json::Value {
        serde_json::json!({
            "schema_version": 1,
            "transmission_id": "record-42",
            "certificate_generation": "seal-test",
            "aeat_http_status": 200,
            "aeat_response_b64": base64::engine::general_purpose::STANDARD.encode(aeat_body),
            "aeat_response_sha256": "00".repeat(32),
            "received_at": "2026-09-02T10:00:00Z",
        })
    }

    fn test_access(url: &str) -> GatewayAccess {
        // The CA is required by the client builder; over plain HTTP it is simply unused.
        let group =
            openssl::ec::EcGroup::from_curve_name(openssl::nid::Nid::X9_62_PRIME256V1).unwrap();
        let pkey = openssl::pkey::PKey::from_ec_key(openssl::ec::EcKey::generate(&group).unwrap())
            .unwrap();
        let mut name = openssl::x509::X509NameBuilder::new().unwrap();
        name.append_entry_by_nid(openssl::nid::Nid::COMMONNAME, "canned")
            .unwrap();
        let name = name.build();
        let mut cert = openssl::x509::X509::builder().unwrap();
        cert.set_version(2).unwrap();
        cert.set_subject_name(&name).unwrap();
        cert.set_issuer_name(&name).unwrap();
        cert.set_pubkey(&pkey).unwrap();
        cert.set_not_before(&openssl::asn1::Asn1Time::days_from_now(0).unwrap())
            .unwrap();
        cert.set_not_after(&openssl::asn1::Asn1Time::days_from_now(1).unwrap())
            .unwrap();
        cert.sign(&pkey, openssl::hash::MessageDigest::sha256())
            .unwrap();
        let ca_pem = cert.build().to_pem().unwrap();
        let bundle = format!(
            "{}\n{}",
            String::from_utf8(pkey.private_key_to_pem_pkcs8().unwrap()).unwrap(),
            String::from_utf8(ca_pem.clone()).unwrap(),
        );
        GatewayAccess {
            url: url.to_owned(),
            token: "bearer-token".to_owned(),
            identity: reqwest::Identity::from_pem(bundle.as_bytes()).unwrap(),
            ca_pem,
            presenter_nif: "B27593136".to_owned(),
            presenter_name: "ERPLORA CLOUD SL".to_owned(),
        }
    }

    const CN: &str = "hub-test.fiscal.erplora.internal";

    /// The token body the control plane answers with, as `docs/api.md` fixes it.
    fn token_body(common_name: &str, gateway_url: &str) -> String {
        serde_json::json!({
            "token": "SECRET-BEARER-VALUE",
            "token_type": "Bearer",
            "expires_in": 300,
            "expires_at": "2026-09-02T10:00:00+00:00",
            "route": "gateway",
            "gateway_url": gateway_url,
            "obligado_nif": "B12345678",
            "grant_version": null,
            "via": null,
            "presenter_nif": "B27593136",
            "presenter_name": "ERPLORA CLOUD SL",
            "mtls_common_name": common_name,
        })
        .to_string()
    }

    /// A host that lends what hub#1459 says a host lends — an identity and a call to its own
    /// cloud — and counts the calls, which is how «the cache was dropped» is OBSERVED now that
    /// the cache lives in this crate instead of behind a host method.
    struct LendingHost {
        calls: std::sync::Mutex<u32>,
        enrolled: bool,
        common_name: String,
        status: u16,
        body: String,
        /// `false` = this hub cannot reach its cloud at all (`cloud_call` answers `None`).
        has_cloud: bool,
    }

    impl LendingHost {
        fn answering(status: u16, body: String) -> Self {
            Self {
                calls: std::sync::Mutex::new(0),
                enrolled: true,
                common_name: CN.to_owned(),
                status,
                body,
                has_cloud: true,
            }
        }
        fn minting(gateway_url: &str) -> Self {
            Self::answering(200, token_body(CN, gateway_url))
        }
        fn calls(&self) -> u32 {
            *self.calls.lock().unwrap()
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for LendingHost {
        async fn read(
            &self,
            _sql: &str,
            _params: &erplora_db::Params,
        ) -> erplora_runtime::Result<Vec<serde_json::Value>> {
            Ok(vec![])
        }
        async fn machine_identity(
            &self,
            _hub_id: &str,
        ) -> erplora_runtime::Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
            if !self.enrolled {
                return Ok(None);
            }
            let access = test_access("https://unused.example");
            Ok(Some(erplora_runtime::gateway_identity::MachineIdentity {
                identity: access.identity,
                ca_pem: access.ca_pem,
                common_name: self.common_name.clone(),
            }))
        }
        async fn cloud_call(
            &self,
            request: erplora_runtime::cloud_call::CloudRequest,
        ) -> erplora_runtime::Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
            assert_eq!(
                request.path, TOKEN_PATH,
                "the engine names the path, and this is the one it names"
            );
            *self.calls.lock().unwrap() += 1;
            if !self.has_cloud {
                return Ok(None);
            }
            Ok(Some(erplora_runtime::cloud_call::CloudResponse {
                status: self.status,
                body: self.body.clone(),
            }))
        }
    }

    /// Every test gets its own hub: the token cache is keyed by hub and shared by the process.
    fn a_hub(name: &str) -> String {
        format!("hub-{name}")
    }

    fn envelope<'a>(xml: &'a str) -> GatewayEnvelope<'a> {
        GatewayEnvelope {
            hub_id: "hub-1",
            obligado_nif: "B12345678",
            environment: "testing",
            transmission_id: "record-42",
            xml,
        }
    }

    /// The glue that matters: a 200 receipt comes back as the DECODED AEAT SOAP — the same
    /// string `post_soap` would have returned, so the downstream chain is road-blind.
    #[tokio::test]
    async fn a_200_receipt_hands_back_the_decoded_aeat_body() {
        let soap = "<soapenv:Envelope>respuesta AEAT</soapenv:Envelope>";
        let url = canned_cell(vec![http_json("200 OK", &receipt_with(soap))]).await;
        let host = LendingHost::minting(&url);
        let hub = a_hub("receipt-200");

        let body = transmit_via_gateway(&host, &hub, &test_access(&url), &envelope(SENT_XML))
            .await
            .unwrap();

        assert_eq!(body, soap);
        assert_eq!(host.calls(), 0, "no 401, no fresh token minted");
    }

    /// 🔒 REGRESSION — the canary of ADR-0320 §2/§4 (hub#1461). The cell recomputes the sha256
    /// **over the bytes it decoded** and echoes it as `request_sha256`; if that is not the digest
    /// of what left here, what travelled the wire are not our bytes. The receipt is refused WHOLE
    /// — the AEAT verdict riding with it belongs to a delivery we do not recognise — and the
    /// record goes to contingency: a silent send with different bytes is never filed as a verdict.
    #[tokio::test]
    async fn a_receipt_that_quotes_another_digest_is_refused_not_believed() {
        let soap = "<soapenv:Envelope>veredicto de OTROS bytes</soapenv:Envelope>";
        let forged = receipt_quoting(&digest_of("<tampered/>"), soap);
        let url = canned_cell(vec![http_json("200 OK", &forged)]).await;
        let host = LendingHost::minting(&url);
        let hub = a_hub("digest-mismatch");

        let err = transmit_via_gateway(&host, &hub, &test_access(&url), &envelope(SENT_XML))
            .await
            .unwrap_err();

        let message = err.to_string();
        assert!(
            message.contains("request_digest_mismatch"),
            "the failure names itself with a stable code an operator can grep: {message}"
        );
        assert!(
            message.contains(&digest_of(SENT_XML)) && message.contains(&digest_of("<tampered/>")),
            "both digests ride along — that is the forensic value of the canary: {message}"
        );
        assert!(
            !message.contains(soap),
            "an unverified AEAT body is never quoted back: {message}"
        );
        match &err {
            VerifactuError::Transmission(_) => {}
            other => panic!("contingency + backoff, never ::Tls; got {other:?}"),
        }
        assert!(
            !crate::aeat::is_tls_failure(&err),
            "on the cell's road there is no certificate of ours to blame"
        );
    }

    /// And it fails CLOSED: a receipt WITHOUT `request_sha256` is a receipt without a canary,
    /// and a canary skipped when the field is missing cannot tell a healthy cell from an
    /// intermediary that stripped it — that is a guard that fails open. Same treatment as a
    /// receipt without `aeat_response_b64`.
    #[tokio::test]
    async fn a_receipt_without_the_digest_is_refused_the_canary_never_fails_open() {
        let soap = "<soapenv:Envelope>sin canario</soapenv:Envelope>";
        let url = canned_cell(vec![http_json(
            "200 OK",
            &receipt_without_digest(soap).to_string(),
        )])
        .await;
        let host = LendingHost::minting(&url);
        let hub = a_hub("digest-missing");

        let err = transmit_via_gateway(&host, &hub, &test_access(&url), &envelope(SENT_XML))
            .await
            .unwrap_err();

        let message = err.to_string();
        assert!(
            message.contains("receipt_without_request_sha256"),
            "{message}"
        );
        assert!(
            !message.contains(soap),
            "the body of an unverifiable receipt is not surfaced: {message}"
        );
    }

    /// A 401 invalidates the cached Bearer and retries EXACTLY once with a fresh access; the
    /// second answer is the one that counts.
    #[tokio::test]
    async fn a_401_invalidates_the_token_and_retries_exactly_once() {
        let soap = "<soapenv:Envelope>tras renovar</soapenv:Envelope>";
        let url = canned_cell(vec![
            http_json(
                "401 Unauthorized",
                r#"{"code":"invalid_hub_token","message":"token is expired"}"#,
            ),
            http_json("200 OK", &receipt_with(soap)),
        ])
        .await;
        let host = LendingHost::minting(&url);
        let hub = a_hub("401-retry");

        let body = transmit_via_gateway(&host, &hub, &test_access(&url), &envelope(SENT_XML))
            .await
            .unwrap();

        assert_eq!(body, soap);
        assert_eq!(
            host.calls(),
            1,
            "exactly one fresh mint — the cached bearer was dropped and asked for again"
        );
    }

    /// And a second 401 is a real refusal — no loop, the record goes to the backoff queue.
    #[tokio::test]
    async fn a_second_401_is_a_refusal_not_a_loop() {
        let refusal = http_json(
            "401 Unauthorized",
            r#"{"code":"invalid_hub_token","message":"still refused"}"#,
        );
        let url = canned_cell(vec![refusal.clone(), refusal]).await;
        let host = LendingHost::minting(&url);
        let hub = a_hub("401-twice");

        let err = transmit_via_gateway(&host, &hub, &test_access(&url), &envelope(SENT_XML))
            .await
            .unwrap_err();

        let message = err.to_string();
        assert!(message.contains("401"), "{message}");
        assert!(message.contains("invalid_hub_token"), "{message}");
        assert_eq!(host.calls(), 1, "one fresh mint, not a loop of them");
    }

    /// The refusal keeps the cell's `{code, message}` — public material — and stays a
    /// `Transmission` error: `::Tls` would point an operator at a certificate this hub does not
    /// have — on this road the mTLS happens in the cell, with a Seal nobody here can fix.
    #[test]
    fn a_refusal_is_a_transmission_error_never_tls() {
        let err = refusal_error(429, "gateway_overloaded", "backoff, please");
        match &err {
            VerifactuError::Transmission(message) => {
                assert!(message.contains("429"), "{message}");
                assert!(message.contains("gateway_overloaded"), "{message}");
            }
            other => panic!("expected Transmission, got {other:?}"),
        }
        assert!(
            !crate::aeat::is_tls_failure(&err),
            "never ::Tls on the cell's road"
        );
    }

    // ------------------------------------------------------------------------------------
    // Getting authorised (hub#1459): these used to live in `erplora-server`'s broker. They
    // moved with the behaviour — the core no longer knows what a fiscal gateway is.
    // ------------------------------------------------------------------------------------

    /// 🔒 The rule BEFORE the feature, like `fiscal_certificate.rs`: an unreadable body is never
    /// quoted — on a proxy mishap it could carry the bearer itself.
    #[tokio::test]
    async fn a_bad_token_response_never_quotes_the_body() {
        let host = LendingHost::answering(200, "SECRET-BEARER-IN-BROKEN-BODY not json".into());

        let error = resolve_access(&host, &a_hub("broken-body"))
            .await
            .err()
            .expect("a broken body is an error");

        let message = error.to_string();
        assert!(!message.contains("SECRET-BEARER-IN-BROKEN-BODY"), "{message}");
        assert!(message.contains("ilegible"), "{message}");
    }

    /// A missing field names the FIELD, never the body (which holds the bearer).
    #[tokio::test]
    async fn a_missing_field_is_named_without_the_body() {
        let mut value: serde_json::Value =
            serde_json::from_str(&token_body(CN, "https://cell.internal.example")).unwrap();
        value.as_object_mut().unwrap().remove("gateway_url");
        let host = LendingHost::answering(200, value.to_string());

        let error = resolve_access(&host, &a_hub("missing-field"))
            .await
            .err()
            .expect("a token without its URL is unusable");

        let message = error.to_string();
        assert!(message.contains("gateway_url"), "{message}");
        assert!(!message.contains("SECRET-BEARER-VALUE"), "{message}");
    }

    /// A 409 is an ANSWER: that hub holds its own certificate and goes direct. The engine decides
    /// what the status means now — the core used to decide it (`TokenAnswer::GoDirect`).
    #[tokio::test]
    async fn a_409_is_an_answer_not_an_error() {
        let host = LendingHost::answering(409, r#"{"detail":"own_certificate_direct"}"#.into());

        let access = resolve_access(&host, &a_hub("go-direct"))
            .await
            .expect("409 is not a failure");

        assert!(access.is_none(), "the gateway road is simply not this hub's");
    }

    /// A non-2xx that is not a 409 is a failure described by its STATUS — never by its body.
    #[tokio::test]
    async fn a_server_error_is_described_by_its_status_only() {
        let host = LendingHost::answering(500, "SECRET-BEARER-IN-A-500".into());

        let error = resolve_access(&host, &a_hub("cloud-500"))
            .await
            .err()
            .expect("a 500 is a failure");

        let message = error.to_string();
        assert!(message.contains("500"), "{message}");
        assert!(!message.contains("SECRET-BEARER-IN-A-500"), "{message}");
    }

    /// 🔒 Nothing enrolled = no road, and the control-plane quota is NOT spent finding out.
    #[tokio::test]
    async fn without_an_enrolled_identity_the_quota_is_never_touched() {
        let mut host = LendingHost::minting("https://cell.internal.example");
        host.enrolled = false;

        let access = resolve_access(&host, &a_hub("not-enrolled")).await.unwrap();

        assert!(access.is_none());
        assert_eq!(host.calls(), 0, "no identity, no mint");
    }

    /// A hub that cannot reach its cloud at all has no road either — and does not panic.
    #[tokio::test]
    async fn without_a_cloud_there_is_no_road() {
        let mut host = LendingHost::minting("https://cell.internal.example");
        host.has_cloud = false;

        let access = resolve_access(&host, &a_hub("no-cloud")).await.unwrap();

        assert!(access.is_none());
    }

    /// 🔒 The control plane and this hub must agree on WHO this machine is: a token minted for
    /// another hub is refused HERE, with an actionable message, instead of at the ingress.
    #[tokio::test]
    async fn a_token_minted_for_another_hub_is_refused() {
        let host = LendingHost::answering(
            200,
            token_body("hub-otro.fiscal.erplora.internal", "https://cell.example"),
        );

        let error = resolve_access(&host, &a_hub("cn-mismatch"))
            .await
            .err()
            .expect("a mismatched common name is not usable");

        let message = error.to_string();
        assert!(message.contains("hub-otro.fiscal.erplora.internal"), "{message}");
        assert!(message.contains(CN), "{message}");
    }

    /// The mint quota is 60/h and a queue drain asks many times: the second call is served from
    /// the cache. Same protection the server's broker gave, now keyed BY HUB.
    #[tokio::test]
    async fn a_second_ask_is_served_from_the_cache() {
        let host = LendingHost::minting("https://cell.internal.example");
        let hub = a_hub("cache-hit");

        let first = resolve_access(&host, &hub).await.unwrap().expect("minted");
        let second = resolve_access(&host, &hub).await.unwrap().expect("cached");

        assert_eq!(first.token, second.token);
        assert_eq!(host.calls(), 1, "one mint for two asks");
    }

    /// And the cache does not leak ACROSS hubs: each one asks for its own.
    #[tokio::test]
    async fn the_cache_does_not_serve_one_hubs_token_to_another() {
        let host = LendingHost::minting("https://cell.internal.example");

        resolve_access(&host, &a_hub("tenant-a")).await.unwrap();
        resolve_access(&host, &a_hub("tenant-b")).await.unwrap();

        assert_eq!(host.calls(), 2, "a bearer minted for one hub is not another's");
    }

    /// After a failure the next ask BRAKES instead of asking again: a contingency queue draining
    /// against a fallen SaaS must not burn the quota.
    #[tokio::test]
    async fn a_failure_brakes_before_burning_the_quota() {
        let host = LendingHost::answering(500, "boom".into());
        let hub = a_hub("brake");

        resolve_access(&host, &hub).await.unwrap_err();
        let braked = resolve_access(&host, &hub).await.unwrap_err().to_string();

        assert!(braked.contains("frenando"), "{braked}");
        assert_eq!(host.calls(), 1, "the second ask never reached the cloud");
    }

    /// The Debug of an access must never print the Bearer: it is the one shape of this value
    /// that could end up in a log line by accident.
    #[test]
    fn the_debug_of_an_access_redacts_the_bearer() {
        let mut access = test_access("https://cell.internal.example");
        access.token = "SUPER-SECRET-BEARER".to_owned();

        let printed = format!("{access:?}");

        assert!(!printed.contains("SUPER-SECRET-BEARER"), "{printed}");
        assert!(printed.contains("[redacted]"));
        assert!(printed.contains("https://cell.internal.example"));
    }

    /// The Debug of a token never prints the bearer either.
    #[test]
    fn the_debug_of_a_token_redacts_the_bearer() {
        let token = GatewayToken::parse(&token_body(CN, "https://cell.example")).unwrap();
        let printed = format!("{token:?}");
        assert!(!printed.contains("SECRET-BEARER-VALUE"), "{printed}");
        assert!(printed.contains("[redacted]"));
    }
}
