//! Borde de integración de ADR-0049: receipts idempotentes de entrada y suscripciones de salida.
//!
//! El broker sigue siendo el Outbox del runtime. Este módulo solo conserva configuración
//! hub-scoped y prepara deliveries firmadas; el host inyecta el transporte HTTP real.
use async_trait::async_trait;
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::registry::{new_id, now_rfc3339};
use crate::secret_box;

pub const STATUS_ACTIVE: &str = "active";
pub const STATUS_REVOKED: &str = "revoked";
pub const SIGNING_PREFIX: &str = "whsec_";

#[derive(Debug, Clone, serde::Serialize)]
pub struct WebhookSubscriptionInfo {
    pub id: String,
    pub name: String,
    pub url: String,
    pub events: Vec<String>,
    pub status: String,
    pub created_at: String,
    pub last_delivery_at: Option<String>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct WebhookSubscriptionSecret {
    pub id: String,
    pub name: String,
    pub url: String,
    pub events: Vec<String>,
    /// Se revela una sola vez al crear/rotar. En BD solo existe el envelope AES-GCM.
    pub secret: String,
}

#[derive(Debug, Clone)]
pub struct ActiveSubscription {
    pub id: String,
    pub url: String,
    pub secret: String,
}

#[derive(Debug, Clone)]
pub struct WebhookDelivery {
    pub subscription_id: String,
    pub url: String,
    pub event_id: String,
    pub event_name: String,
    pub timestamp: i64,
    pub signature: String,
    pub body: String,
}

#[async_trait]
pub trait WebhookTransport: Send + Sync + std::fmt::Debug {
    async fn send(&self, delivery: &WebhookDelivery) -> std::result::Result<(), String>;
}

fn webhook_error(context: &str, detail: impl std::fmt::Display) -> RuntimeError {
    RuntimeError::Webhook(format!("{context}: {detail}"))
}

fn load_master_key() -> Result<secret_box::SecretsKey> {
    secret_box::master_key_from_env()
        .map_err(|e| webhook_error("master key inválida", e))?
        .ok_or_else(|| {
            webhook_error(
                "no se puede guardar el secreto",
                format!("falta {}", secret_box::MASTER_KEY_ENV),
            )
        })
}

fn random_signing_secret() -> String {
    use argon2::password_hash::rand_core::{OsRng, RngCore};
    let mut bytes = [0u8; 32];
    OsRng.fill_bytes(&mut bytes);
    let hex: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    format!("{SIGNING_PREFIX}{hex}")
}

fn parse_events(value: &Json) -> Vec<String> {
    value
        .as_str()
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_default()
}

fn row_to_info(row: &Json) -> WebhookSubscriptionInfo {
    WebhookSubscriptionInfo {
        id: row["id"].as_str().unwrap_or_default().to_string(),
        name: row["name"].as_str().unwrap_or_default().to_string(),
        url: row["url"].as_str().unwrap_or_default().to_string(),
        events: parse_events(&row["events_json"]),
        status: row["status"].as_str().unwrap_or_default().to_string(),
        created_at: row["created_at"].as_str().unwrap_or_default().to_string(),
        last_delivery_at: row["last_delivery_at"].as_str().map(str::to_string),
    }
}

fn normalize_events(events: &[String]) -> Result<Vec<String>> {
    let mut normalized: Vec<String> = events
        .iter()
        .map(|e| e.trim())
        .filter(|e| !e.is_empty())
        .map(str::to_string)
        .collect();
    normalized.sort();
    normalized.dedup();
    if normalized.is_empty() || normalized.len() > 100 {
        return Err(webhook_error(
            "events inválidos",
            "se requieren entre 1 y 100 eventos",
        ));
    }
    if normalized.iter().any(|e| e.len() > 160) {
        return Err(webhook_error(
            "events inválidos",
            "un nombre supera 160 caracteres",
        ));
    }
    Ok(normalized)
}

pub async fn create_subscription(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    name: &str,
    url: &str,
    events: &[String],
    created_by: &str,
) -> Result<WebhookSubscriptionSecret> {
    let name = name.trim();
    if name.is_empty() || name.len() > 120 {
        return Err(webhook_error(
            "nombre inválido",
            "debe tener entre 1 y 120 caracteres",
        ));
    }
    let events = normalize_events(events)?;
    let secret = random_signing_secret();
    let encrypted = secret_box::encrypt(&load_master_key()?, &secret)
        .map_err(|e| webhook_error("cifrando secreto", e))?;
    let id = new_id().replace('-', "");
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("name".into(), json!(name));
    p.insert("url".into(), json!(url));
    p.insert(
        "events".into(),
        json!(serde_json::to_string(&events).unwrap_or_else(|_| "[]".into())),
    );
    p.insert("secret".into(), json!(encrypted));
    p.insert("status".into(), json!(STATUS_ACTIVE));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("created_by".into(), json!(created_by));
    db.execute(
        "INSERT INTO hub_webhook_subscription \
         (id, hub_id, name, url, events_json, secret_encrypted, status, created_at, created_by, last_delivery_at) \
         VALUES (:id, :hub_id, :name, :url, :events, :secret, :status, :now, :created_by, NULL)",
        &p,
    )
    .await?;
    Ok(WebhookSubscriptionSecret {
        id,
        name: name.to_string(),
        url: url.to_string(),
        events,
        secret,
    })
}

pub async fn list_subscriptions(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<WebhookSubscriptionInfo>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let rows = db
        .query(
            "SELECT id, name, url, events_json, status, created_at, last_delivery_at \
             FROM hub_webhook_subscription WHERE hub_id = :hub_id ORDER BY created_at DESC",
            &p,
        )
        .await?;
    Ok(rows.rows.iter().map(row_to_info).collect())
}

pub async fn rotate_subscription(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
) -> Result<Option<WebhookSubscriptionSecret>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(id));
    let rows = db
        .query(
            "SELECT id, name, url, events_json, status, created_at, last_delivery_at \
             FROM hub_webhook_subscription WHERE hub_id = :hub_id AND id = :id",
            &p,
        )
        .await?;
    let Some(row) = rows.rows.first() else {
        return Ok(None);
    };
    let info = row_to_info(row);
    let secret = random_signing_secret();
    let encrypted = secret_box::encrypt(&load_master_key()?, &secret)
        .map_err(|e| webhook_error("cifrando secreto", e))?;
    p.insert("secret".into(), json!(encrypted));
    p.insert("status".into(), json!(STATUS_ACTIVE));
    db.execute(
        "UPDATE hub_webhook_subscription SET secret_encrypted = :secret, status = :status \
         WHERE hub_id = :hub_id AND id = :id",
        &p,
    )
    .await?;
    Ok(Some(WebhookSubscriptionSecret {
        id: info.id,
        name: info.name,
        url: info.url,
        events: info.events,
        secret,
    }))
}

pub async fn revoke_subscription(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<bool> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(id));
    p.insert("status".into(), json!(STATUS_REVOKED));
    Ok(db
        .execute(
            "UPDATE hub_webhook_subscription SET status = :status WHERE hub_id = :hub_id AND id = :id",
            &p,
        )
        .await?
        .affected
        > 0)
}

/// Suscripciones activas que escuchan exactamente `event_name`. El catálogo `external` del módulo
/// se comprueba en el Outbox antes de llamar aquí; una suscripción no puede abrir un evento privado.
pub async fn active_for_event(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    event_name: &str,
) -> Result<Vec<ActiveSubscription>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("status".into(), json!(STATUS_ACTIVE));
    let rows = db
        .query(
            "SELECT id, url, events_json, secret_encrypted FROM hub_webhook_subscription \
             WHERE hub_id = :hub_id AND status = :status",
            &p,
        )
        .await?;
    let key =
        secret_box::master_key_from_env().map_err(|e| webhook_error("master key inválida", e))?;
    rows.rows
        .iter()
        .filter(|row| {
            parse_events(&row["events_json"])
                .iter()
                .any(|e| e == event_name)
        })
        .map(|row| {
            let stored = row["secret_encrypted"].as_str().unwrap_or_default();
            let secret = secret_box::decrypt_or_legacy(key.as_ref(), stored)
                .map_err(|e| webhook_error("descifrando secreto", e))?;
            Ok(ActiveSubscription {
                id: row["id"].as_str().unwrap_or_default().to_string(),
                url: row["url"].as_str().unwrap_or_default().to_string(),
                secret,
            })
        })
        .collect()
}

pub fn build_delivery(
    subscription: &ActiveSubscription,
    event_id: &str,
    event_name: &str,
    hub_id: &str,
    created_at: &str,
    payload: &Params,
) -> Result<WebhookDelivery> {
    let timestamp = chrono::Utc::now().timestamp();
    let body = serde_json::to_string(&json!({
        "id": event_id,
        "type": event_name,
        "created_at": created_at,
        "hub_id": hub_id,
        "data": Json::Object(payload.clone()),
    }))
    .map_err(|e| webhook_error("serializando delivery", e))?;
    let signed = format!("{timestamp}.{event_id}.{body}");
    let key = ring::hmac::Key::new(ring::hmac::HMAC_SHA256, subscription.secret.as_bytes());
    let tag = ring::hmac::sign(&key, signed.as_bytes());
    let signature: String = tag.as_ref().iter().map(|b| format!("{b:02x}")).collect();
    Ok(WebhookDelivery {
        subscription_id: subscription.id.clone(),
        url: subscription.url.clone(),
        event_id: event_id.to_string(),
        event_name: event_name.to_string(),
        timestamp,
        signature: format!("v1={signature}"),
        body,
    })
}

pub async fn touch_subscription(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE hub_webhook_subscription SET last_delivery_at = :now \
         WHERE hub_id = :hub_id AND id = :id",
        &p,
    )
    .await?;
    Ok(())
}

#[derive(Debug, Clone, PartialEq)]
pub enum ReceiptState {
    New,
    Replay(Json),
    Processing,
    Conflict,
}

fn request_hash(command: &str, payload: &Params) -> String {
    let canonical = serde_json::to_string(&json!({
        "command": command,
        "payload": Json::Object(payload.clone()),
    }))
    .unwrap_or_default();
    ring::digest::digest(&ring::digest::SHA256, canonical.as_bytes())
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

pub async fn begin_receipt(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    api_key_id: &str,
    request_id: &str,
    command: &str,
    payload: &Params,
) -> Result<ReceiptState> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("api_key_id".into(), json!(api_key_id));
    p.insert("request_id".into(), json!(request_id));
    p.insert("command".into(), json!(command));
    p.insert("request_hash".into(), json!(request_hash(command, payload)));
    p.insert("now".into(), json!(now_rfc3339()));
    let inserted = db
        .execute(
            "INSERT INTO hub_webhook_receipt \
             (hub_id, api_key_id, request_id, command, request_hash, status, response_json, created_at, completed_at) \
             VALUES (:hub_id, :api_key_id, :request_id, :command, :request_hash, 'processing', NULL, :now, NULL) \
             ON CONFLICT (hub_id, api_key_id, request_id) DO NOTHING",
            &p,
        )
        .await?;
    if inserted.affected > 0 {
        return Ok(ReceiptState::New);
    }
    let rows = db
        .query(
            "SELECT command, request_hash, status, response_json FROM hub_webhook_receipt \
             WHERE hub_id = :hub_id AND api_key_id = :api_key_id AND request_id = :request_id",
            &p,
        )
        .await?;
    let Some(row) = rows.rows.first() else {
        return Ok(ReceiptState::Processing);
    };
    if row["command"].as_str() != Some(command)
        || row["request_hash"].as_str() != p["request_hash"].as_str()
    {
        return Ok(ReceiptState::Conflict);
    }
    if row["status"].as_str() == Some("completed") {
        let response = row["response_json"]
            .as_str()
            .and_then(|raw| serde_json::from_str(raw).ok())
            .unwrap_or(Json::Null);
        return Ok(ReceiptState::Replay(response));
    }
    Ok(ReceiptState::Processing)
}

pub async fn complete_receipt(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    api_key_id: &str,
    request_id: &str,
    response: &Json,
) -> Result<()> {
    let (sql, p) = complete_receipt_op(hub_id, api_key_id, request_id, response);
    db.execute(&sql, &p).await?;
    Ok(())
}

/// Operación que sella el receipt dentro de la MISMA transacción que el command. Se escribe
/// primero con respuesta `null`; tras el commit se reemplaza por la respuesta real. Si el proceso
/// cae entre ambas escrituras, el replay queda sellado y no duplica la mutación.
pub(crate) fn complete_receipt_op(
    hub_id: &str,
    api_key_id: &str,
    request_id: &str,
    response: &Json,
) -> (String, Params) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("api_key_id".into(), json!(api_key_id));
    p.insert("request_id".into(), json!(request_id));
    p.insert(
        "response".into(),
        json!(serde_json::to_string(response).unwrap_or_else(|_| "null".into())),
    );
    p.insert("now".into(), json!(now_rfc3339()));
    (
        "UPDATE hub_webhook_receipt SET status = 'completed', response_json = :response, completed_at = :now \
         WHERE hub_id = :hub_id AND api_key_id = :api_key_id AND request_id = :request_id"
            .to_string(),
        p,
    )
}

pub async fn abandon_receipt(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    api_key_id: &str,
    request_id: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("api_key_id".into(), json!(api_key_id));
    p.insert("request_id".into(), json!(request_id));
    db.execute(
        "DELETE FROM hub_webhook_receipt WHERE hub_id = :hub_id AND api_key_id = :api_key_id \
         AND request_id = :request_id AND status = 'processing'",
        &p,
    )
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signature_is_sha256_hmac_over_exact_wire_body() {
        let sub = ActiveSubscription {
            id: "s1".into(),
            url: "https://example.com/hook".into(),
            secret: "whsec_test".into(),
        };
        let delivery = build_delivery(
            &sub,
            "evt_1",
            "catalog.created",
            "hub-1",
            "2026-01-01T00:00:00Z",
            &Params::new(),
        )
        .unwrap();
        let signed = format!(
            "{}.{}.{}",
            delivery.timestamp, delivery.event_id, delivery.body
        );
        let key = ring::hmac::Key::new(ring::hmac::HMAC_SHA256, b"whsec_test");
        let expected: String = ring::hmac::sign(&key, signed.as_bytes())
            .as_ref()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(delivery.signature, format!("v1={expected}"));
    }
}
