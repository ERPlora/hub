//! **hub#2675 — an automation that calls Square or PayPal must not make it act twice because the
//! hub restarted mid-call.**
//!
//! hub#2659 sends one key per run and step in the standard `Idempotency-Key` header, which is where
//! Stripe, Adyen or Mollie read it. Square reads it from the BODY (`idempotency_key`) and PayPal from
//! another header (`PayPal-Request-Id`), so the author needs to place that same key themselves:
//! `{{run.idempotency_key}}`. A fixed text would not do — it would make the second, legitimate
//! order disappear on the other side.
//!
//! What is measured is what arrives at a real socket, after a real lease expiry on Postgres:
//! - the re-issued attempt carries the SAME key in the body and in the other header, and it is the
//!   key of the standard header too (one key per call, wherever the other system reads it);
//! - two different runs of the same automation carry DIFFERENT keys;
//! - the run history shows the key where it went out.
use std::sync::{Arc, Mutex};

use axum::extract::State;
use axum::http::HeaderMap;
use axum::routing::post;
use erplora_db::testutil::fresh_db;
use erplora_runtime::flows::grants::{GrantKind, GrantSpec};
use erplora_runtime::flows::{IoResult, NewFlow, PendingIo};
use erplora_runtime::Runtime;
use erplora_server::flow_io::{self, Limits};
use serde_json::{json, Value};

const HUB: &str = "hub-flow-http-2675";

/// What one request carried: the key in the body, in `PayPal-Request-Id` and in `Idempotency-Key`.
#[derive(Clone, Debug, PartialEq)]
struct Arrived {
    body_key: Value,
    paypal: Option<String>,
    standard: Option<String>,
}

#[derive(Clone, Default)]
struct Seen(Arc<Mutex<Vec<Arrived>>>);

impl Seen {
    fn requests(&self) -> Vec<Arrived> {
        self.0.lock().unwrap().clone()
    }
}

fn header(h: &HeaderMap, name: &str) -> Option<String> {
    h.get(name).map(|v| v.to_str().unwrap_or_default().to_string())
}

async fn start_server() -> (String, Seen) {
    let seen = Seen::default();
    let app = axum::Router::new()
        .route(
            "/v2/payments",
            post(
                |State(seen): State<Seen>, h: HeaderMap, axum::Json(body): axum::Json<Value>| async move {
                    seen.0.lock().unwrap().push(Arrived {
                        body_key: body["idempotency_key"].clone(),
                        paypal: header(&h, "paypal-request-id"),
                        standard: header(&h, "idempotency-key"),
                    });
                    axum::Json(json!({ "payment": { "id": "p_1" } }))
                },
            ),
        )
        .with_state(seen.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        let _ = axum::serve(listener, app).await;
    });
    (format!("http://127.0.0.1:{}", addr.port()), seen)
}

async fn runtime() -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// The step a Square/PayPal author writes: the key in the body AND in PayPal's header.
async fn paying_flow(rt: &Runtime, base: &str) -> String {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Pay".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{
                        "id": "pay", "kind": "http", "method": "POST",
                        "url": format!("{base}/v2/payments"),
                        "headers": { "PayPal-Request-Id": "{{run.idempotency_key}}" },
                        "body": {
                            "idempotency_key": "{{run.idempotency_key}}",
                            "amount_money": { "amount": 1200, "currency": "EUR" }
                        }
                    }]
                }),
            },
            "hub_user:1",
        )
        .await
        .unwrap()
        .id;
    rt.replace_flow_grants(
        &flow_id,
        &[GrantSpec::pair(GrantKind::Http, format!("{base}/*"))],
        "hub_user:1",
    )
    .await
    .unwrap();
    flow_id
}

/// One tick, and the calls it hands out go to the network. `complete` false is the hub dying after
/// the request reached the other system and before the answer was written back.
async fn turn(rt: &Runtime, complete: bool) {
    let report = rt.process_flows().await.unwrap();
    for io in &report.pending_io {
        let PendingIo::Http {
            run_id,
            step_id,
            request,
        } = io
        else {
            continue;
        };
        let result = flow_io::execute(request, &Limits::allowing_private_addresses()).await;
        assert!(matches!(result, IoResult::Done(_)), "{result:?}");
        if complete {
            rt.complete_flow_io(run_id, step_id, result).await.unwrap();
        }
    }
}

/// What five minutes do to a run whose hub died mid-call: its lease runs out.
async fn lease_runs_out(rt: &Runtime) {
    rt.db()
        .execute_batch(
            "UPDATE _flow_runs SET claim_expires_at = '2000-01-01T00:00:00+00:00' \
             WHERE status = 'running';",
        )
        .await
        .unwrap();
}

#[tokio::test]
async fn hub2675_square_and_paypal_get_the_same_key_on_the_call_repeated_after_a_restart() {
    let (base, seen) = start_server().await;
    let rt = runtime().await;
    let flow_id = paying_flow(&rt, &base).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1")
        .await
        .unwrap();

    turn(&rt, false).await; // the call lands, the hub dies before writing the answer
    lease_runs_out(&rt).await;
    turn(&rt, true).await; // reclaimed: the step is re-issued

    let requests = seen.requests();
    assert_eq!(requests.len(), 2, "at-least-once: the step was re-issued");
    let first = &requests[0];
    let key = first
        .body_key
        .as_str()
        .unwrap_or_else(|| panic!("Square reads the key from the body: {first:?}"));
    assert_eq!(key.len(), 36, "a UUID, inside Square's 45 characters: {first:?}");
    assert_eq!(first.paypal.as_deref(), Some(key), "{first:?}");
    assert_eq!(
        first.standard.as_deref(),
        Some(key),
        "one key per call, wherever the other system reads it: {first:?}"
    );
    assert_eq!(
        requests[0], requests[1],
        "the repeat must be recognisable as the same call by the other system"
    );

    let run = rt
        .list_flow_runs(&flow_id, 1, None)
        .await
        .unwrap()
        .remove(0);
    let (_, steps) = rt.get_flow_run(&run.id).await.unwrap();
    let recorded = &steps[0].input;
    assert_eq!(recorded["headers"]["PayPal-Request-Id"], json!(key), "{recorded:?}");
    let body: Value = serde_json::from_str(recorded["body"].as_str().unwrap()).unwrap();
    assert_eq!(body["idempotency_key"], json!(key), "{recorded:?}");
}

#[tokio::test]
async fn hub2675_two_runs_of_the_same_automation_carry_different_keys_in_the_body() {
    let (base, seen) = start_server().await;
    let rt = runtime().await;
    let flow_id = paying_flow(&rt, &base).await;
    for _ in 0..2 {
        rt.start_flow_run(&flow_id, &json!({}), "hub_user:1")
            .await
            .unwrap();
    }

    turn(&rt, true).await;
    turn(&rt, true).await;

    let requests = seen.requests();
    assert_eq!(requests.len(), 2, "{requests:?}");
    assert!(
        requests.iter().all(|r| r.body_key.as_str().is_some_and(|k| k.len() == 36)),
        "{requests:?}"
    );
    assert_ne!(
        requests[0].body_key, requests[1].body_key,
        "two payments are two payments: a shared key would swallow the second one"
    );
    assert_ne!(requests[0].paypal, requests[1].paypal, "{requests:?}");
}
