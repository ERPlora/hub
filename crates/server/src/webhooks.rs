//! Superficie HTTP del borde de integración (ADR-0049): entrada al dispatcher y salida Outbox.
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};
use std::time::Duration;

use async_trait::async_trait;
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::{json, Map, Value};

use crate::state::AppState;
use crate::{api_keys, auth};

#[derive(Debug)]
pub struct HttpWebhookTransport {
    allow_private_targets: bool,
}

impl HttpWebhookTransport {
    pub fn new(allow_private_targets: bool) -> Result<Self, String> {
        // Valida al arrancar que el cliente TLS puede construirse; cada entrega crea después un
        // cliente con la resolución DNS fijada para cerrar el TOCTOU de DNS rebinding.
        Self::client(None)?;
        Ok(Self {
            allow_private_targets,
        })
    }

    fn client(pinned: Option<(&str, SocketAddr)>) -> Result<reqwest::Client, String> {
        let mut builder = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .connect_timeout(Duration::from_secs(5))
            .timeout(Duration::from_secs(15));
        if let Some((host, address)) = pinned {
            builder = builder.resolve(host, address);
        }
        builder.build().map_err(|e| e.to_string())
    }

    async fn validate_resolved_target(
        &self,
        raw: &str,
    ) -> Result<(reqwest::Url, String, SocketAddr), String> {
        let url = validate_destination_url(raw, self.allow_private_targets)?;
        let host = url
            .host_str()
            .ok_or_else(|| "URL sin host".to_string())?
            .trim_matches(['[', ']'])
            .to_string();
        let port = url
            .port_or_known_default()
            .ok_or_else(|| "URL sin puerto resoluble".to_string())?;
        let resolved: Vec<_> = tokio::net::lookup_host((host.as_str(), port))
            .await
            .map_err(|e| format!("DNS de webhook: {e}"))?
            .collect();
        if resolved.is_empty() {
            return Err("el destino no resolvió ninguna IP".into());
        }
        if !self.allow_private_targets && resolved.iter().any(|addr| !is_public_ip(addr.ip())) {
            return Err("el destino resolvió una IP privada/reservada (SSRF bloqueado)".into());
        }
        Ok((url, host, resolved[0]))
    }
}

#[async_trait]
impl erplora_runtime::webhooks::WebhookTransport for HttpWebhookTransport {
    async fn send(
        &self,
        delivery: &erplora_runtime::webhooks::WebhookDelivery,
    ) -> Result<(), String> {
        let (url, host, address) = self.validate_resolved_target(&delivery.url).await?;
        let client = Self::client(Some((&host, address)))?;
        let response = client
            .post(url)
            .header("content-type", "application/json")
            .header("x-erplora-delivery", &delivery.event_id)
            .header("x-erplora-event", &delivery.event_name)
            .header("x-erplora-timestamp", delivery.timestamp.to_string())
            .header("x-erplora-signature", &delivery.signature)
            .body(delivery.body.clone())
            .send()
            .await
            .map_err(|e| format!("POST: {e}"))?;
        if !response.status().is_success() {
            return Err(format!("destino respondió HTTP {}", response.status()));
        }
        Ok(())
    }
}

fn is_public_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ip) => {
            let [a, b, ..] = ip.octets();
            !(ip.is_private()
                || ip.is_loopback()
                || ip.is_link_local()
                || ip.is_unspecified()
                || ip.is_multicast()
                || a == 0
                || a >= 224
                || (a == 100 && (64..=127).contains(&b))
                || (a == 192 && b == 0)
                || (a == 198 && (b == 18 || b == 19)))
        }
        IpAddr::V6(ip) => {
            if let Some(mapped) = ip.to_ipv4_mapped() {
                return is_public_ip(IpAddr::V4(mapped));
            }
            let first = ip.segments()[0];
            !(ip.is_loopback()
                || ip.is_unspecified()
                || ip.is_multicast()
                || (first & 0xfe00) == 0xfc00
                || (first & 0xffc0) == 0xfe80
                || (first & 0xffc0) == 0xfec0
                || (ip.segments()[0] == 0x2001 && ip.segments()[1] == 0x0db8))
        }
    }
}

pub fn validate_destination_url(
    raw: &str,
    allow_private_targets: bool,
) -> Result<reqwest::Url, String> {
    let url = reqwest::Url::parse(raw).map_err(|e| format!("URL inválida: {e}"))?;
    if !url.username().is_empty() || url.password().is_some() {
        return Err("la URL no puede incluir credenciales".into());
    }
    let host = url.host_str().ok_or_else(|| "URL sin host".to_string())?;
    let ip_host = host.trim_matches(['[', ']']);
    if !allow_private_targets && url.scheme() != "https" {
        return Err("las suscripciones requieren HTTPS".into());
    }
    if allow_private_targets && !matches!(url.scheme(), "http" | "https") {
        return Err("solo se admite HTTP(S)".into());
    }
    let lower = host.to_ascii_lowercase();
    if !allow_private_targets
        && (lower == "localhost"
            || lower.ends_with(".local")
            || lower.ends_with(".internal")
            || lower.contains("::ffff:"))
    {
        return Err("host privado/reservado (SSRF bloqueado)".into());
    }
    if !allow_private_targets {
        if let Ok(ip) = ip_host
            .parse::<Ipv4Addr>()
            .map(IpAddr::V4)
            .or_else(|_| host.parse::<Ipv6Addr>().map(IpAddr::V6))
        {
            if !is_public_ip(ip) {
                return Err("IP privada/reservada (SSRF bloqueado)".into());
            }
        }
    }
    Ok(url)
}

#[derive(Deserialize)]
pub struct WebhookEnvelope {
    id: String,
    #[serde(default)]
    occurred_at: Option<String>,
    #[serde(default)]
    payload: Map<String, Value>,
}

fn conflict(code: &str, message: &str) -> Response {
    (
        StatusCode::CONFLICT,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// POST /webhook/{module}/{command}: envelope autenticado → command expuesto del dispatcher.
pub async fn inbound(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path((module, command)): Path<(String, String)>,
    Json(envelope): Json<WebhookEnvelope>,
) -> Response {
    if envelope.id.is_empty()
        || envelope.id.len() > 128
        || !envelope
            .id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.' | ':'))
    {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": { "code": "invalid_envelope", "message": "id debe tener 1..128 caracteres seguros" } })),
        )
            .into_response();
    }
    if let Some(occurred_at) = envelope.occurred_at.as_deref() {
        if chrono::DateTime::parse_from_rfc3339(occurred_at).is_err() {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({ "ok": false, "error": { "code": "invalid_envelope", "message": "occurred_at debe ser RFC3339" } })),
            )
                .into_response();
        }
    }

    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let name = format!("{module}.{command}");
    if !rt.registry().is_command_exposed(&module, &name) {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({ "ok": false, "error": { "code": "not_found", "message": "command no expuesto" } })),
        )
            .into_response();
    }
    let principal = match api_keys::external_principal(&headers, &st.config, &rt).await {
        Ok(principal) => principal,
        Err(response) => return response,
    };
    let state = match erplora_runtime::webhooks::begin_receipt(
        rt.db(),
        rt.hub_id(),
        &principal.key_id,
        &envelope.id,
        &name,
        &envelope.payload,
    )
    .await
    {
        Ok(state) => state,
        Err(e) => return crate::err_response(e),
    };
    match state {
        erplora_runtime::webhooks::ReceiptState::Replay(data) => {
            return Json(
                json!({ "ok": true, "data": data, "delivery_id": envelope.id, "replay": true }),
            )
            .into_response();
        }
        erplora_runtime::webhooks::ReceiptState::Processing => {
            return conflict("request_in_progress", "el mismo id ya se está procesando");
        }
        erplora_runtime::webhooks::ReceiptState::Conflict => {
            return conflict(
                "idempotency_conflict",
                "el mismo id ya se usó para otro command",
            );
        }
        erplora_runtime::webhooks::ReceiptState::New => {}
    }

    match rt
        .execute_webhook_command(
            &name,
            &envelope.payload,
            &principal.context,
            &principal.key_id,
            &envelope.id,
        )
        .await
    {
        Ok(data) => Json(json!({ "ok": true, "data": data, "delivery_id": envelope.id, "replay": false }))
            .into_response(),
        Err(e) => {
            let _ = erplora_runtime::webhooks::abandon_receipt(
                rt.db(),
                rt.hub_id(),
                &principal.key_id,
                &envelope.id,
            )
            .await;
            crate::err_response(e)
        }
    }
}

#[derive(Deserialize)]
pub struct CreateSubscriptionReq {
    name: String,
    url: String,
    events: Vec<String>,
}

fn management_error(e: erplora_runtime::RuntimeError) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({ "ok": false, "error": e.to_string() })),
    )
        .into_response()
}

pub async fn list_subscriptions(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": e.message() })),
        )
            .into_response();
    }
    match rt.list_webhook_subscriptions().await {
        Ok(data) => Json(json!({ "ok": true, "data": data })).into_response(),
        Err(e) => management_error(e),
    }
}

pub async fn create_subscription(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CreateSubscriptionReq>,
) -> Response {
    let rt = st.runtime.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(admin) => admin,
        Err(e) => {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": e.message() })),
            )
                .into_response()
        }
    };
    if let Err(message) = validate_destination_url(&req.url, st.config.dev_mode) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": message })),
        )
            .into_response();
    }
    let unknown: Vec<&str> = req
        .events
        .iter()
        .map(String::as_str)
        .filter(|event| !rt.registry().is_any_external_event(event.trim()))
        .collect();
    if !unknown.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "ok": false,
                "error": format!("eventos no publicados como externos: {}", unknown.join(", "))
            })),
        )
            .into_response();
    }
    match rt
        .create_webhook_subscription(
            &req.name,
            &req.url,
            &req.events,
            &format!("hub_user:{}", admin.id),
        )
        .await
    {
        Ok(data) => Json(json!({ "ok": true, "data": data })).into_response(),
        Err(e) => management_error(e),
    }
}

pub async fn rotate_subscription(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": e.message() })),
        )
            .into_response();
    }
    match rt.rotate_webhook_subscription(&id).await {
        Ok(Some(data)) => Json(json!({ "ok": true, "data": data })).into_response(),
        Ok(None) => (
            StatusCode::NOT_FOUND,
            Json(json!({ "ok": false, "error": "suscripción no encontrada" })),
        )
            .into_response(),
        Err(e) => management_error(e),
    }
}

pub async fn revoke_subscription(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": e.message() })),
        )
            .into_response();
    }
    match rt.revoke_webhook_subscription(&id).await {
        Ok(true) => Json(json!({ "ok": true })).into_response(),
        Ok(false) => (
            StatusCode::NOT_FOUND,
            Json(json!({ "ok": false, "error": "suscripción no encontrada" })),
        )
            .into_response(),
        Err(e) => management_error(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn production_rejects_http_and_private_targets() {
        assert!(validate_destination_url("http://example.com/h", false).is_err());
        assert!(validate_destination_url("https://127.0.0.1/h", false).is_err());
        assert!(
            validate_destination_url("https://169.254.169.254/latest/meta-data", false).is_err()
        );
        assert!(validate_destination_url("https://[::ffff:127.0.0.1]/h", false).is_err());
        assert!(validate_destination_url("https://localhost/h", false).is_err());
        assert!(validate_destination_url("https://example.com/h", false).is_ok());
    }

    #[test]
    fn dev_mode_allows_loopback_receiver_for_e2e_only() {
        assert!(validate_destination_url("http://127.0.0.1:43210/h", true).is_ok());
    }
}
