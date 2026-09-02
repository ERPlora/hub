//! The gateway leg of the transmission (hub#1432, hub#985 §1): the hub-without-certificate road.
//!
//! The engine builds the SAME SOAP envelope as ever and, instead of presenting a certificate to
//! the AEAT itself, POSTs the exact bytes to the fiscal cell, which authenticates the CHANNEL
//! with ERPlora's Sello and forwards them untouched. **The body authorises nothing** — the
//! Bearer inside [`GatewayAccess`] does — but the body's `environment` SELECTS the destination:
//! the module's config decides it (one-way go-live), the cell obeys it, and `production` only
//! opens when the token carries the grant (verifactu-gateway#42).
//!
//! This file is the ONLY place that names the cell's path: the core hands the URL over opaque
//! (the hub#1407 guard keeps regime names out of it, and this crate is the regime).

use base64::Engine as _;
use erplora_runtime::fiscal_gateway::GatewayAccess;
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

pub(crate) fn envelope_json(envelope: &GatewayEnvelope<'_>) -> serde_json::Value {
    let xml_sha256: String = sha2::Sha256::digest(envelope.xml.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
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
    VerifactuError::Transmission(format!(
        "pasarela fiscal: {status} {code}: {message}"
    ))
}

/// POSTs the envelope to the cell and hands back the AEAT's raw SOAP body — the SAME string
/// `aeat::post_soap` would have returned, so the parse/classify/persist chain downstream does
/// not know which road the bytes took.
///
/// A 401 invalidates the cached Bearer through the host and retries ONCE with a fresh access;
/// everything else maps to [`VerifactuError::Transmission`] — never `::Tls`, which would fire
/// the DELEGATED-certificate refetch signal that has no business on this road.
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
            host.fiscal_gateway_invalidate().await;
            let fresh = host
                .fiscal_gateway_access(hub_id)
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
        .add_root_certificate(
            reqwest::Certificate::from_pem(&access.ca_pem)
                .map_err(|e| VerifactuError::Transmission(format!("CA de la pasarela ilegible: {e}")))?,
        )
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
        return String::from_utf8(bytes).map(PostOutcome::AeatBody).map_err(|e| {
            VerifactuError::Transmission(format!("respuesta AEAT no UTF-8 vía pasarela: {e}"))
        });
    }

    // The error contract is `{code, message}` — public material, safe to surface on the record.
    let (code, message) = match serde_json::from_str::<serde_json::Value>(&body) {
        Ok(value) => (
            value.get("code").and_then(|v| v.as_str()).unwrap_or("").to_owned(),
            value.get("message").and_then(|v| v.as_str()).unwrap_or("").to_owned(),
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
        assert_eq!(sha, sha.to_lowercase(), "lowercase hex, as the cell demands");
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

    /// The refusal keeps the cell's `{code, message}` — public material — and stays a
    /// `Transmission` error: `::Tls` would fire the delegated-certificate refetch signal, which
    /// has no business on the gateway road.
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
        assert!(!crate::aeat::is_tls_failure(&err), "must not trip the refetch trigger");
    }
}
