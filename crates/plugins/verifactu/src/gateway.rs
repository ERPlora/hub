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
    VerifactuError::Transmission(format!("pasarela fiscal: {status} {code}: {message}"))
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

    fn receipt_with(aeat_body: &str) -> String {
        serde_json::json!({
            "schema_version": 1,
            "transmission_id": "record-42",
            "request_sha256": "00".repeat(32),
            "certificate_generation": "seal-test",
            "aeat_http_status": 200,
            "aeat_response_b64": base64::engine::general_purpose::STANDARD.encode(aeat_body),
            "aeat_response_sha256": "00".repeat(32),
            "received_at": "2026-09-02T10:00:00Z",
        })
        .to_string()
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
        }
    }

    struct InvalidateCountingHost {
        invalidations: std::sync::Mutex<u32>,
        fresh_access_url: String,
    }
    #[async_trait::async_trait]
    impl NativeHost for InvalidateCountingHost {
        async fn read(
            &self,
            _sql: &str,
            _params: &erplora_db::Params,
        ) -> erplora_runtime::Result<Vec<serde_json::Value>> {
            Ok(vec![])
        }
        async fn fiscal_gateway_access(
            &self,
            _hub_id: &str,
        ) -> erplora_runtime::Result<Option<GatewayAccess>> {
            Ok(Some(test_access(&self.fresh_access_url)))
        }
        async fn fiscal_gateway_invalidate(&self) {
            *self.invalidations.lock().unwrap() += 1;
        }
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
        let host = InvalidateCountingHost {
            invalidations: std::sync::Mutex::new(0),
            fresh_access_url: url.clone(),
        };

        let body = transmit_via_gateway(&host, "hub-1", &test_access(&url), &envelope("<x/>"))
            .await
            .unwrap();

        assert_eq!(body, soap);
        assert_eq!(
            *host.invalidations.lock().unwrap(),
            0,
            "no 401, no invalidation"
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
        let host = InvalidateCountingHost {
            invalidations: std::sync::Mutex::new(0),
            fresh_access_url: url.clone(),
        };

        let body = transmit_via_gateway(&host, "hub-1", &test_access(&url), &envelope("<x/>"))
            .await
            .unwrap();

        assert_eq!(body, soap);
        assert_eq!(
            *host.invalidations.lock().unwrap(),
            1,
            "exactly one invalidation"
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
        let host = InvalidateCountingHost {
            invalidations: std::sync::Mutex::new(0),
            fresh_access_url: url.clone(),
        };

        let err = transmit_via_gateway(&host, "hub-1", &test_access(&url), &envelope("<x/>"))
            .await
            .unwrap_err();

        let message = err.to_string();
        assert!(message.contains("401"), "{message}");
        assert!(message.contains("invalid_hub_token"), "{message}");
        assert_eq!(*host.invalidations.lock().unwrap(), 1);
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
        assert!(
            !crate::aeat::is_tls_failure(&err),
            "must not trip the refetch trigger"
        );
    }
}
