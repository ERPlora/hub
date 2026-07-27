//! Daily business-usage heartbeat (hub#199 / saas#806).
//!
//! This reuses the entitlement's 24-hour tick. The runtime reads the canonical
//! `sales_sale` table and active local device sessions, then posts one compact
//! cumulative snapshot to the SaaS. If the sales module/table is unavailable,
//! `orders_today` is omitted: the Cloud must not turn a read failure into a
//! fabricated zero.

use erplora_db::{DatabaseAdapter, Params};
use serde::Serialize;
use serde_json::{json, Value};

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DailyUsageHeartbeat {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub orders_today: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_sale_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub terminals: Option<u64>,
}

/// Collect today's completed, non-deleted sales and the latest sale timestamp.
/// The SQL intentionally mirrors the module's canonical `sales.today` query.
pub async fn collect_daily_usage(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    now: &str,
) -> DailyUsageHeartbeat {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    params.insert("now".into(), json!(now));

    let sales = db
        .query(
            "SELECT COUNT(*) AS orders_today, MAX(created_at) AS last_sale_at \
             FROM sales_sale \
             WHERE hub_id = :hub_id AND is_deleted = 0 AND status = 'completed' \
             AND erp_date(created_at) = erp_date(:now)",
            &params,
        )
        .await
        .ok()
        .and_then(|result| result.rows.into_iter().next());

    let orders_today = sales
        .as_ref()
        .and_then(|row| value_as_u64(&row["orders_today"]));
    let last_sale_at = sales
        .as_ref()
        .and_then(|row| row["last_sale_at"].as_str().map(str::to_owned));

    let terminals = db
        .query(
            "SELECT COUNT(DISTINCT device_id) AS terminals FROM hub_session \
             WHERE expires_at > :now AND device_id IS NOT NULL",
            &params,
        )
        .await
        .ok()
        .and_then(|result| result.rows.into_iter().next())
        .and_then(|row| value_as_u64(&row["terminals"]));

    DailyUsageHeartbeat {
        orders_today,
        last_sale_at,
        terminals,
    }
}

/// Send a best-effort heartbeat with the existing machine credential.
pub async fn send_heartbeat(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    body: &DailyUsageHeartbeat,
) -> Result<(), String> {
    let req = cloud_client::CloudClient::new(cloud_base_url).heartbeat(auth);
    let mut request = http.post(&req.url).json(body);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    let response = request.send().await.map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("{}: status {}", req.url, response.status()));
    }
    Ok(())
}

fn value_as_u64(value: &Value) -> Option<u64> {
    match value {
        Value::Number(number) => number
            .as_u64()
            .or_else(|| number.as_i64().and_then(|n| u64::try_from(n).ok())),
        Value::String(text) => text.trim().parse().ok(),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::extract::State;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::post;
    use axum::{Json, Router};
    use erplora_db::testutil::fresh_db;
    use std::sync::{Arc, Mutex};
    use tokio::sync::oneshot;

    #[tokio::test]
    async fn collects_only_completed_sales_for_this_hub_and_day() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE sales_sale (\
               id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, status TEXT NOT NULL, \
               is_deleted BIGINT NOT NULL DEFAULT 0, created_at TEXT NOT NULL\
             );\
             CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, device_id TEXT, expires_at TEXT NOT NULL\
             );\
             INSERT INTO sales_sale VALUES\
               ('s1', 'hub-a', 'completed', 0, '2026-07-27T09:00:00Z'),\
               ('s2', 'hub-a', 'completed', 0, '2026-07-27T11:30:00Z'),\
               ('old', 'hub-a', 'completed', 0, '2026-07-26T23:59:59Z'),\
               ('void', 'hub-a', 'voided', 0, '2026-07-27T12:00:00Z'),\
               ('deleted', 'hub-a', 'completed', 1, '2026-07-27T13:00:00Z'),\
               ('other', 'hub-b', 'completed', 0, '2026-07-27T14:00:00Z');\
             INSERT INTO hub_session VALUES\
               ('a1', 'device-a', '2026-07-28T00:00:00Z'),\
               ('a2', 'device-a', '2026-07-28T00:00:00Z'),\
               ('b1', 'device-b', '2026-07-28T00:00:00Z'),\
               ('expired', 'device-c', '2026-07-27T00:00:00Z'),\
               ('unknown', NULL, '2026-07-28T00:00:00Z');",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z").await;
        assert_eq!(usage.orders_today, Some(2));
        assert_eq!(usage.last_sale_at.as_deref(), Some("2026-07-27T11:30:00Z"));
        assert_eq!(usage.terminals, Some(2));
    }

    #[tokio::test]
    async fn missing_sales_table_omits_usage_instead_of_inventing_zero() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, device_id TEXT, expires_at TEXT NOT NULL\
             );",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z").await;
        assert_eq!(usage.orders_today, None);
        assert_eq!(usage.last_sale_at, None);
        assert_eq!(usage.terminals, Some(0));
        assert_eq!(
            serde_json::to_value(usage).unwrap(),
            json!({"terminals": 0})
        );
    }

    #[tokio::test]
    async fn sends_expected_json_and_machine_headers() {
        type Captured = Arc<Mutex<Option<oneshot::Sender<(HeaderMap, Value)>>>>;

        async fn capture(
            State(sender): State<Captured>,
            headers: HeaderMap,
            Json(body): Json<Value>,
        ) -> StatusCode {
            if let Some(sender) = sender.lock().unwrap().take() {
                let _ = sender.send((headers, body));
            }
            StatusCode::OK
        }

        let (sender, receiver) = oneshot::channel();
        let app = Router::new()
            .route("/api/v1/hub/device/heartbeat/", post(capture))
            .with_state(Arc::new(Mutex::new(Some(sender))));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

        let auth = cloud_client::Auth::HubToken {
            hub_id: "hub-a".into(),
            token: "machine-token".into(),
        };
        let body = DailyUsageHeartbeat {
            orders_today: Some(12),
            last_sale_at: Some("2026-07-27T11:30:00Z".into()),
            terminals: Some(3),
        };
        send_heartbeat(
            &reqwest::Client::new(),
            &format!("http://{address}"),
            &auth,
            &body,
        )
        .await
        .unwrap();

        let (headers, received) = receiver.await.unwrap();
        assert_eq!(headers["x-hub-id"], "hub-a");
        assert_eq!(headers["x-hub-token"], "machine-token");
        assert_eq!(
            received,
            json!({
                "orders_today": 12,
                "last_sale_at": "2026-07-27T11:30:00Z",
                "terminals": 3,
            })
        );
        server.abort();
    }
}
