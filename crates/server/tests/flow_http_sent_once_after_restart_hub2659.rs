//! **hub#2659 — an automation that calls another system must not make it act twice because the hub
//! restarted mid-call.**
//!
//! The `http` step is at-least-once by design (`PendingIo` in `crates/runtime/src/flows/executor.rs`):
//! if the hub dies while the call is in flight, the lease expires, the run is reclaimed and the step
//! is re-issued. The other system then sees the same order or the same charge twice — unless both
//! attempts carry the same `Idempotency-Key`, which is how Stripe, Adyen, GoCardless or Mollie (and
//! the IETF `Idempotency-Key` header draft) recognise a repeat. The hub already does this for its own
//! notifications (hub#2648); this file pins it for the step a flow author writes.
//!
//! What is measured is what arrives at a real socket, after a real lease expiry on Postgres:
//! - the re-issued attempt carries the SAME key as the one that was cut off;
//! - two different runs of the same automation carry DIFFERENT keys (a fixed key would make the
//!   second order disappear on the other side);
//! - an author who writes their own `Idempotency-Key` keeps it, and the hub does not add a second.
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

const HUB: &str = "hub-flow-http-2659";

/// Every `Idempotency-Key` header of every request, in arrival order (one entry per header line,
/// so a request that carried two shows up twice).
#[derive(Clone, Default)]
struct Seen(Arc<Mutex<Vec<Vec<String>>>>);

impl Seen {
    fn requests(&self) -> Vec<Vec<String>> {
        self.0.lock().unwrap().clone()
    }
}

async fn start_server() -> (String, Seen) {
    let seen = Seen::default();
    let app = axum::Router::new()
        .route(
            "/charges",
            post(|State(seen): State<Seen>, h: HeaderMap| async move {
                let keys = h
                    .get_all("idempotency-key")
                    .iter()
                    .map(|v| v.to_str().unwrap_or_default().to_string())
                    .collect();
                seen.0.lock().unwrap().push(keys);
                axum::Json(json!({ "id": "ch_1" }))
            }),
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

async fn charging_flow(rt: &Runtime, base: &str, headers: Value) -> String {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Charge".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{
                        "id": "charge", "kind": "http", "method": "POST",
                        "url": format!("{base}/charges"),
                        "headers": headers,
                        "body": { "amount": 1200 }
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

/// What five minutes do to a run whose hub died mid-call: its lease runs out. Only the lease —
/// the status stays `running`, exactly as the dead process left it.
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
async fn hub2659_the_call_repeated_after_a_restart_carries_the_same_idempotency_key() {
    let (base, seen) = start_server().await;
    let rt = runtime().await;
    let flow_id = charging_flow(&rt, &base, json!({})).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1")
        .await
        .unwrap();

    turn(&rt, false).await; // the call lands, the hub dies before writing the answer
    lease_runs_out(&rt).await;
    turn(&rt, true).await; // reclaimed: the step is re-issued

    let requests = seen.requests();
    assert_eq!(requests.len(), 2, "at-least-once: the step was re-issued");
    assert_eq!(requests[0].len(), 1, "one key per request: {requests:?}");
    assert!(!requests[0][0].is_empty(), "{requests:?}");
    assert_eq!(
        requests[0], requests[1],
        "the repeat must be recognisable as the same call by the other system"
    );

    // And the run history shows the key the call went out with, so support can match it against
    // the other system's log.
    let run = rt.list_flow_runs(&flow_id, 1, None).await.unwrap().remove(0);
    let (_, steps) = rt.get_flow_run(&run.id).await.unwrap();
    assert_eq!(
        steps[0].input["headers"]["Idempotency-Key"],
        json!(requests[0][0]),
        "{:?}",
        steps[0].input
    );
}

#[tokio::test]
async fn hub2659_two_runs_of_the_same_automation_carry_different_keys() {
    let (base, seen) = start_server().await;
    let rt = runtime().await;
    let flow_id = charging_flow(&rt, &base, json!({})).await;
    for _ in 0..2 {
        rt.start_flow_run(&flow_id, &json!({}), "hub_user:1")
            .await
            .unwrap();
    }

    turn(&rt, true).await;
    turn(&rt, true).await;

    let requests = seen.requests();
    assert_eq!(requests.len(), 2, "{requests:?}");
    assert!(requests.iter().all(|keys| keys.len() == 1), "{requests:?}");
    assert_ne!(
        requests[0], requests[1],
        "two charges are two charges: a shared key would swallow the second one"
    );
}

#[tokio::test]
async fn hub2659_an_idempotency_key_the_author_wrote_is_kept_and_not_doubled() {
    let (base, seen) = start_server().await;
    let rt = runtime().await;
    let flow_id = charging_flow(
        &rt,
        &base,
        json!({ "idempotency-key": "order-{{input.order_id}}" }),
    )
    .await;
    rt.start_flow_run(&flow_id, &json!({ "order_id": 42 }), "hub_user:1")
        .await
        .unwrap();

    turn(&rt, true).await;

    assert_eq!(seen.requests(), vec![vec!["order-42".to_string()]]);
}
