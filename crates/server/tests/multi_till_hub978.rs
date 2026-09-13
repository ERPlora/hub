//! Regression tests for ERPlora/hub#978 — multi-till no longer serialises on a global lock.
//!
//! Until hub#978 every `POST /api/command` held the runtime's `tokio::Mutex` for the WHOLE
//! execution (SQL + WASM + outbox), and the 1 s relay tick took the same lock for `process_outbox`
//! + `process_scheduler` + `process_flows`. With N tills the p50 scaled ≈ N× and a relay backlog
//! froze every till at once. The runtime now sits behind a `RwLock`: commands, queries and the
//! relay share it, and only module installs/updates take it exclusively.
//!
//! The approval test pins what the decision-log used to attribute to the `Mutex`: an approval is
//! spent **exactly once** even when the retries race, because the atomicity comes from the grant
//! store itself (one `std::sync::Mutex` around a single get+remove), not from the request lock.
use std::path::PathBuf;
use std::time::{Duration, Instant};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;


fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(name)
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

async fn slow_till_app() -> axum::Router {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("tests/fixture_hub978"))
        .await
        .unwrap();
    app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ))
}

/// `POST /api/command` from till `till`, in `Dev` auth mode (identity from headers).
fn command_request(till: &str, name: &str, payload: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/command")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", till)
        .header("x-permissions", "*")
        .body(Body::from(
            json!({ "name": name, "payload": payload }).to_string(),
        ))
        .unwrap()
}

/// Two tills take a payment at the same instant, and each command waits INSIDE the database until
/// it sees the other one arrive (`sale_create_meeting.sql`). Let in together, they meet within
/// milliseconds; queued on a global lock, the first gives up alone after its 10 s wait, because the
/// second cannot start until the first is done.
///
/// hub#1680: this used to decide by wall clock (total under 600 ms = overlap, over = queued), and a
/// loaded CI runner turned two overlapping commands into 610 ms and a red nobody believed. What the
/// test proves now is the ORDER — «the other one was in flight while I was» — which no load changes.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn hub978_two_concurrent_commands_overlap_instead_of_queueing() {
    let app = slow_till_app().await;

    let first = tokio::spawn(app.clone().oneshot(command_request(
        "till-1",
        "slowtill.sale.create_meeting",
        json!({ "label": "table 1" }),
    )));
    let second = tokio::spawn(app.clone().oneshot(command_request(
        "till-2",
        "slowtill.sale.create_meeting",
        json!({ "label": "table 2" }),
    )));
    let (first, second) = (
        first.await.unwrap().unwrap(),
        second.await.unwrap().unwrap(),
    );
    assert_eq!(
        first.status(),
        StatusCode::OK,
        "{:?}",
        body_json(first).await
    );
    assert_eq!(
        second.status(),
        StatusCode::OK,
        "{:?}",
        body_json(second).await
    );

    let listed = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/query")
                .header("content-type", "application/json")
                .header("x-hub-id", "h1")
                .header("x-user-id", "till-1")
                .header("x-permissions", "*")
                .body(Body::from(
                    json!({ "name": "slowtill.sales.list" }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    let body = body_json(listed).await;
    let labels: Vec<String> = body["data"]
        .as_array()
        .or_else(|| body["data"]["rows"].as_array())
        .expect("the two sales are listed")
        .iter()
        .map(|row| row["label"].as_str().unwrap_or_default().to_string())
        .collect();
    assert_eq!(labels.len(), 2, "{body}");
    // Both meet, deterministically: the first does not depart until it has seen the second arrive,
    // so the second always arrives with the first still in. Queued on a lock, NEITHER meets anybody.
    assert!(
        labels.iter().all(|label| label.ends_with(":met")),
        "two concurrent commands never saw each other in flight: they queued on the runtime lock \
         ({labels:?})"
    );
}

/// The relay tick (`process_outbox` + `process_scheduler` + `process_flows`) used to take the
/// SAME lock as the commands, so a backlog drain froze every till. It now runs under a shared
/// read guard: a command in flight and a relay pass overlap instead of waiting on each other.
///
/// hub#1680: proven by ORDER, not by milliseconds. A meeting command stays in flight until a second
/// one arrives; once it has arrived, a relay pass runs — and the command must STILL be in flight
/// when the pass returns. Under an exclusive lock the pass could only start after the command had
/// given up and finished. Then a second command lets the first one go.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn hub978_a_relay_pass_does_not_wait_for_a_command_in_flight() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("tests/fixture_hub978"))
        .await
        .unwrap();
    let state = AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev));
    let router = app(state.clone());

    let command = tokio::spawn(router.clone().oneshot(command_request(
        "till-1",
        "slowtill.sale.create_meeting",
        json!({ "label": "table 1" }),
    )));

    // Wait until the command is INSIDE the database (its arrival is recorded), however long the
    // machine takes to get it there — no sleep that a loaded runner can outlast.
    let arrivals = || {
        let router = router.clone();
        async move {
            let resp = router
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri("/api/query")
                        .header("content-type", "application/json")
                        .header("x-hub-id", "h1")
                        .header("x-user-id", "till-1")
                        .header("x-permissions", "*")
                        .body(Body::from(
                            json!({ "name": "slowtill.arrivals" }).to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            let body = body_json(resp).await;
            body["data"][0]["arrived"].as_i64().unwrap_or(0)
        }
    };
    while arrivals().await < 1 {
        assert!(
            !command.is_finished(),
            "the command finished before it was seen arriving"
        );
        tokio::task::yield_now().await;
    }

    let relayed = {
        let rt = state.runtime.read().await;
        rt.process_outbox().await.unwrap()
    };
    assert_eq!(
        relayed, 0,
        "nothing was pending; the pass is about the wait, not the work"
    );
    assert!(
        !command.is_finished(),
        "the relay pass only got the runtime after the command in flight had finished: they queued"
    );

    // Let the first command go: a second arrival is the company it is waiting for.
    let release = router
        .clone()
        .oneshot(command_request(
            "till-2",
            "slowtill.sale.create_meeting",
            json!({ "label": "table 2" }),
        ))
        .await
        .unwrap();
    assert_eq!(
        release.status(),
        StatusCode::OK,
        "{:?}",
        body_json(release).await
    );
    let resp = command.await.unwrap().unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "{:?}", body_json(resp).await);
}

// ── Approvals (hub#361) keep their exactly-once spend without the request lock ──────────────

/// The `till` fixture of hub#361 plus a manager with a PIN, in `Dev` auth mode.
async fn elevation_state() -> AppState {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("../runtime/tests/fixture_elevation"))
        .await
        .unwrap();
    rt.create_user("Sofía", "8317", "manager", None)
        .await
        .unwrap();
    AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev))
}

fn take_payment_request(token: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/command")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u-cashier")
        .header("x-permissions", "till.view_sale,till.add_sale")
        .header("x-elevation-token", token)
        .body(Body::from(
            json!({ "name": "till.sale.take_payment", "payload": { "label": "table 4" } })
                .to_string(),
        ))
        .unwrap()
}

fn approve_request() -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri("/api/elevation/approve")
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u-cashier")
        .header("x-permissions", "till.view_sale,till.add_sale")
        .body(Body::from(
            json!({
                "approver": "Sofía",
                "pin": "8317",
                "command": "till.sale.take_payment",
                "payload": { "label": "table 4" }
            })
            .to_string(),
        ))
        .unwrap()
}

/// One approval, sixteen retries racing with the same token: exactly one action runs, the other
/// fifteen are sent back to the manager, and the audit trail records exactly one spend. The
/// decision-log of hub#361 attributed this to the runtime `Mutex`; with commands overlapping the
/// guarantee has to come from the grant store, and this test is what says it does.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn hub978_an_approval_is_still_spent_exactly_once_without_the_mutex() {
    let state = elevation_state().await;
    let router = app(state.clone());

    let resp = router.clone().oneshot(approve_request()).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let token = body_json(resp).await["data"]["token"]
        .as_str()
        .unwrap()
        .to_string();

    const RACERS: usize = 16;
    let mut tasks = Vec::with_capacity(RACERS);
    for _ in 0..RACERS {
        let router = router.clone();
        let token = token.clone();
        tasks.push(tokio::spawn(async move {
            let resp = router.oneshot(take_payment_request(&token)).await.unwrap();
            let status = resp.status();
            (status, body_json(resp).await)
        }));
    }
    let mut ran = 0;
    let mut refused = 0;
    for task in tasks {
        let (status, body) = task.await.unwrap();
        match status {
            StatusCode::OK => ran += 1,
            StatusCode::FORBIDDEN => {
                assert_eq!(body["error"]["code"], json!("requires_elevation"), "{body}");
                refused += 1;
            }
            other => panic!("unexpected status {other}: {body}"),
        }
    }
    assert_eq!(ran, 1, "exactly one retry spends the approval");
    assert_eq!(
        refused,
        RACERS - 1,
        "every other retry is sent back to the manager"
    );

    // What the database saw: one sale, one receipt — never two of either.
    let rt = state.runtime.read().await;
    let db = rt.db();
    let mut params = Params::new();
    params.insert("hub_id".into(), json!("h1"));
    let sales = db
        .query(
            "SELECT COUNT(*) AS n FROM till_sales WHERE hub_id = :hub_id",
            &params,
        )
        .await
        .unwrap();
    assert_eq!(
        sales.rows[0]["n"].as_i64(),
        Some(1),
        "one sale: {:?}",
        sales.rows
    );
    let receipts = db
        .query(
            "SELECT COUNT(*) AS n FROM _elevation_audit WHERE hub_id = :hub_id",
            &params,
        )
        .await
        .unwrap();
    assert_eq!(
        receipts.rows[0]["n"].as_i64(),
        Some(1),
        "one receipt: {:?}",
        receipts.rows
    );
}

// ── Bench (ignored): p50 per command with 1 vs 4 tills, numbers for the PR body ─────────────

/// `cargo test -p erplora-server --test multi_till_hub978 -- --ignored --nocapture bench`
///
/// Not an assertion — a measurement. Each till fires `ITERATIONS` fast commands back to back;
/// the p50/p95 of the per-request latency is what the issue measured (hub#978 table).
#[tokio::test(flavor = "multi_thread", worker_threads = 8)]
#[ignore = "benchmark: run by hand, prints p50/p95 for 1 vs 4 tills"]
async fn hub978_bench_p50_by_tills() {
    const ITERATIONS: usize = 150;
    for tills in [1usize, 4] {
        let router = slow_till_app().await;
        // Warm-up: first statements pay the prepared-statement cache.
        for _ in 0..20 {
            let resp = router
                .clone()
                .oneshot(command_request(
                    "warm",
                    "slowtill.sale.create_fast",
                    json!({ "label": "warm" }),
                ))
                .await
                .unwrap();
            assert_eq!(resp.status(), StatusCode::OK);
        }
        let mut tasks = Vec::with_capacity(tills);
        for till in 0..tills {
            let router = router.clone();
            tasks.push(tokio::spawn(async move {
                let mut latencies = Vec::with_capacity(ITERATIONS);
                for i in 0..ITERATIONS {
                    let started = Instant::now();
                    let resp = router
                        .clone()
                        .oneshot(command_request(
                            &format!("till-{till}"),
                            "slowtill.sale.create_fast",
                            json!({ "label": format!("sale {i}") }),
                        ))
                        .await
                        .unwrap();
                    assert_eq!(resp.status(), StatusCode::OK);
                    latencies.push(started.elapsed());
                }
                latencies
            }));
        }
        let mut all: Vec<Duration> = Vec::new();
        let wall = Instant::now();
        for task in tasks {
            all.extend(task.await.unwrap());
        }
        let wall = wall.elapsed();
        all.sort();
        let p50 = all[all.len() / 2];
        let p95 = all[all.len() * 95 / 100];
        let throughput = all.len() as f64 / wall.as_secs_f64();
        println!(
            "hub978 bench tills={tills} p50={:.1}ms p95={:.1}ms cmd/s={throughput:.0}",
            p50.as_secs_f64() * 1000.0,
            p95.as_secs_f64() * 1000.0
        );
    }
}
