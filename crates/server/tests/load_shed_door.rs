//! hub#1401 — the runtime sheds load under overload instead of queueing until the origin
//! saturates and Cloudflare answers `502` for everyone.
//!
//! Reproduced against a live PRE hub: a read ramp on `GET /api/hub/context` never returned a
//! single `429`/`503`; at 1000 concurrent it produced a `502` storm (12k of them) and recovery
//! took ~54s. The runtime must instead bound the in-flight business work and reject the excess
//! IMMEDIATELY with a fast `503` + `Retry-After`, following the runtime error envelope
//! (`{ok:false, error:{code, message}}`), while liveness/readiness keeps answering.
//!
//! This drives the REAL production layer ([`erplora_server::with_load_shedding`]) composed the
//! same way [`erplora_server::app`] composes it — health merged OUTSIDE the budget — over a
//! controllable slow handler, so the shedding is deterministic (no reliance on real DB latency).

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use axum::routing::get;
use axum::Router;
use erplora_server::with_load_shedding;
use tokio::net::TcpListener;
use tokio::sync::Semaphore;

/// Tiny budget so the test can saturate it deterministically.
const BUDGET: usize = 2;
/// How many requests over the budget we fire; all of them must be shed.
const EXCESS: usize = 3;

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn excess_concurrent_requests_are_shed_as_503_while_readyz_stays_up() {
    // `started` lets the test know when the in-budget handlers are actually holding their
    // permits; `gate` parks those handlers (holding the tower permit) until we release them.
    let started = Arc::new(AtomicUsize::new(0));
    let gate = Arc::new(Semaphore::new(0));

    let business = {
        let started = started.clone();
        let gate = gate.clone();
        Router::new().route(
            "/slow",
            get(move || {
                let started = started.clone();
                let gate = gate.clone();
                async move {
                    started.fetch_add(1, Ordering::SeqCst);
                    // Park while holding the concurrency permit until the test opens the gate.
                    let _permit = gate.acquire_owned().await.expect("gate open");
                    "ok"
                }
            }),
        )
    };
    // The REAL production layer, with a tiny budget.
    let business = with_load_shedding(business, BUDGET);
    // Health lives OUTSIDE the budget — exactly how `app()` composes it.
    let health = Router::new().route("/readyz", get(|| async { "ready" }));
    let app: Router = health.merge(business);

    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
    let addr = listener.local_addr().expect("addr");
    let server = tokio::spawn(async move {
        axum::serve(listener, app).await.expect("serve");
    });

    let base = format!("http://{addr}");
    let client = reqwest::Client::builder()
        .pool_max_idle_per_host(0)
        .timeout(Duration::from_secs(5))
        .build()
        .expect("client");

    // 1) Fill the budget: BUDGET concurrent slow requests, each parks holding one permit.
    let mut held = Vec::new();
    for _ in 0..BUDGET {
        let c = client.clone();
        let u = format!("{base}/slow");
        held.push(tokio::spawn(async move { c.get(u).send().await }));
    }
    wait_for(&started, BUDGET).await;

    // 2) Excess: more concurrent requests than the budget MUST be shed immediately as `503`.
    //    Without shedding they instead enter the handler and park on the gate, so the client
    //    times out — which is exactly the failure that proves the guard catches the positive.
    for _ in 0..EXCESS {
        let resp = client
            .get(format!("{base}/slow"))
            .timeout(Duration::from_secs(2))
            .send()
            .await
            .expect("excess request should get a fast 503, not hang");
        assert_eq!(
            resp.status().as_u16(),
            503,
            "excess request must be shed with 503 Service Unavailable"
        );
        let retry_after = resp
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|v| v.to_str().ok())
            .map(str::to_string);
        assert!(
            retry_after.is_some(),
            "a shed 503 must carry a Retry-After header"
        );
        let body: serde_json::Value = resp.json().await.expect("503 body is the JSON envelope");
        assert_eq!(body["ok"], serde_json::json!(false), "envelope ok=false");
        assert_eq!(
            body["error"]["code"],
            serde_json::json!("service_overloaded"),
            "envelope carries the stable overload code"
        );
        assert!(
            body["error"]["message"].is_string(),
            "envelope carries a human message"
        );
    }

    // 3) Health must still answer 200 even while the business budget is fully saturated.
    let readyz = client
        .get(format!("{base}/readyz"))
        .timeout(Duration::from_secs(2))
        .send()
        .await
        .expect("readyz must answer under overload");
    assert_eq!(
        readyz.status().as_u16(),
        200,
        "readyz must bypass the shed and stay up under overload"
    );

    // 4) Open the gate: the within-budget requests complete with their normal 200.
    gate.add_permits(BUDGET);
    for h in held {
        let resp = h
            .await
            .expect("join held request")
            .expect("held request completes");
        assert_eq!(
            resp.status().as_u16(),
            200,
            "within-budget request still gets its normal response"
        );
        assert_eq!(resp.text().await.expect("body"), "ok");
    }

    server.abort();
}

async fn wait_for(counter: &Arc<AtomicUsize>, target: usize) {
    for _ in 0..200 {
        if counter.load(Ordering::SeqCst) >= target {
            return;
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
    panic!(
        "handlers never reached the body: {}/{}",
        counter.load(Ordering::SeqCst),
        target
    );
}
