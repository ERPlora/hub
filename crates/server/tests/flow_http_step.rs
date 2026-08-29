//! **The `http` step against a server that is really there** (hub#662 — ADR-0283 §4 / K3).
//!
//! The runtime's own tests pin what a flow is ALLOWED to do; they cannot pin what actually leaves
//! the machine, because the runtime has no network. That is what this file is for, and it is
//! written around one question: **did a request happen, or not?** A fake HTTP server counts them,
//! so «no grant → nothing goes out» is a zero measured at the other end of a socket rather than the
//! absence of an assertion.
//!
//! Every zero here has a twin that is a one. A test that only proves nothing happened would still
//! pass if the step were broken outright, and «the feature is disabled» is not the property being
//! defended — «the feature works, and refuses» is.
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::IntoResponse;
use axum::routing::{any, get};
use erplora_db::testutil::fresh_db;
use erplora_runtime::flows::grants::GrantKind;
use erplora_runtime::flows::{IoResult, NewFlow, PendingIo};
use erplora_runtime::Runtime;
use erplora_server::flow_io::{self, Limits};
use serde_json::{json, Value};

const HUB: &str = "hub-flow-http";

// ── a server that is really listening ─────────────────────────────────────────────────────────

#[derive(Clone)]
struct Fake {
    hits: Arc<AtomicUsize>,
    last_auth: Arc<std::sync::Mutex<String>>,
}

struct Server {
    base: String,
    state: Fake,
}

impl Server {
    /// How many requests actually arrived. THE measurement of this file.
    fn hits(&self) -> usize {
        self.state.hits.load(Ordering::SeqCst)
    }

    fn last_authorization(&self) -> String {
        self.state.last_auth.lock().unwrap().clone()
    }

    fn url(&self, path: &str) -> String {
        format!("{}{path}", self.base)
    }
}

async fn count(State(fake): State<Fake>, headers: HeaderMap) {
    fake.hits.fetch_add(1, Ordering::SeqCst);
    if let Some(auth) = headers.get("authorization").and_then(|v| v.to_str().ok()) {
        *fake.last_auth.lock().unwrap() = auth.to_string();
    }
}

async fn start_server() -> Server {
    let state = Fake {
        hits: Arc::new(AtomicUsize::new(0)),
        last_auth: Arc::new(std::sync::Mutex::new(String::new())),
    };

    let app = axum::Router::new()
        .route(
            "/ok",
            any(|s: State<Fake>, h: HeaderMap| async move {
                count(s, h).await;
                axum::Json(json!({ "name": "Marta", "id": 7 }))
            }),
        )
        .route(
            "/text",
            get(|s: State<Fake>, h: HeaderMap| async move {
                count(s, h).await;
                "just words"
            }),
        )
        .route(
            "/boom",
            get(|s: State<Fake>, h: HeaderMap| async move {
                count(s, h).await;
                (StatusCode::INTERNAL_SERVER_ERROR, "the till is on fire")
            }),
        )
        .route(
            "/slow",
            get(|s: State<Fake>, h: HeaderMap| async move {
                count(s, h).await;
                tokio::time::sleep(std::time::Duration::from_secs(30)).await;
                "too late"
            }),
        )
        .route(
            "/big",
            get(|s: State<Fake>, h: HeaderMap| async move {
                count(s, h).await;
                "x".repeat(3 * 1024 * 1024)
            }),
        )
        .route(
            "/redirect",
            get(|s: State<Fake>, h: HeaderMap| async move {
                count(s, h).await;
                (
                    StatusCode::FOUND,
                    [(axum::http::header::LOCATION, "/ok")],
                    "moved",
                )
            }),
        )
        .route(
            "/echo-key",
            get(|s: State<Fake>, h: HeaderMap| async move {
                let key = h
                    .get("authorization")
                    .and_then(|v| v.to_str().ok())
                    .unwrap_or_default()
                    .to_string();
                count(s, h).await;
                // Plenty of real APIs do exactly this in an error message.
                axum::Json(json!({ "error": format!("bad credentials: {key}") })).into_response()
            }),
        )
        .with_state(state.clone());

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        let _ = axum::serve(listener, app).await;
    });
    Server {
        base: format!("http://127.0.0.1:{}", addr.port()),
        state,
    }
}

// ── the hub side ──────────────────────────────────────────────────────────────────────────────

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn flow_calling(rt: &Runtime, url: &str, timeout: u64) -> String {
    rt.create_flow(
        &NewFlow {
            name: "Caller".into(),
            enabled: true,
            definition: json!({
                "schema_version": 1,
                "steps": [{ "id": "call", "kind": "http", "url": url, "timeout": timeout }]
            }),
        },
        "hub_user:1",
    )
    .await
    .unwrap()
    .id
}

async fn allow(rt: &Runtime, flow_id: &str, pattern: &str) {
    rt.replace_flow_grants(
        flow_id,
        &[(GrantKind::Http, pattern.to_string())],
        "hub_user:1",
    )
    .await
    .unwrap();
}

/// Drives one full turn of claim → I/O → complete, the way the background loop does it: the tick
/// under the lock, the call outside it, the result back in.
///
/// `limits` is the only thing a test bends: a fake server necessarily lives on loopback, which the
/// SSRF guard blocks by design. Everything else is what ships — and the tests that are ABOUT the
/// guard use [`Limits::default`], so bending it here never hides what it is for.
async fn turn(rt: &Runtime, limits: &Limits) -> Vec<IoResult> {
    let report = rt.process_flows().await.unwrap();
    let mut results = Vec::new();
    for io in &report.pending_io {
        let PendingIo::Http { run_id, step_id, request } = io else {
            continue;
        };
        let result = flow_io::execute(request, limits).await;
        results.push(result.clone());
        rt.complete_flow_io(run_id, step_id, result).await.unwrap();
    }
    results
}

async fn run_status(rt: &Runtime, flow_id: &str) -> (String, String) {
    let run = rt.list_flow_runs(flow_id, 1, None).await.unwrap().remove(0);
    (run.status, run.last_error)
}

// ── the zero, and its twin ────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn without_a_grant_not_one_request_reaches_the_server() {
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/ok"), 5).await;
    // No grants at all — the default answer of `_flow_grants`.
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    turn(&rt, &Limits::allowing_private_addresses()).await;

    assert_eq!(server.hits(), 0, "the hub never opened the socket");
    let (status, error) = run_status(&rt, &flow_id).await;
    assert_eq!(status, "failed");
    assert!(error.contains("flow.grant_denied"), "{error}");
}

#[tokio::test]
async fn with_the_grant_exactly_one_request_reaches_it_and_its_answer_comes_back() {
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/ok"), 5).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    let results = turn(&rt, &Limits::allowing_private_addresses()).await;

    assert_eq!(server.hits(), 1, "one step, one request — no retries, no doubles");
    assert_eq!(
        results,
        vec![IoResult::Done(json!({
            "status": 200,
            "ok": true,
            "body_json": { "name": "Marta", "id": 7 }
        }))],
        "the next step reads `steps.call.body_json.name`"
    );

    // The completed run goes back in the queue and the NEXT tick finds it has no steps left.
    turn(&rt, &Limits::allowing_private_addresses()).await;
    assert_eq!(run_status(&rt, &flow_id).await.0, "done");
    assert_eq!(server.hits(), 1, "finishing the run did not call again");
}

#[tokio::test]
async fn a_body_that_is_not_json_comes_back_as_text() {
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/text"), 5).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    let results = turn(&rt, &Limits::allowing_private_addresses()).await;
    assert_eq!(
        results,
        vec![IoResult::Done(
            json!({ "status": 200, "ok": true, "body_text": "just words" })
        )]
    );
}

// ── the limits ────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_server_that_never_answers_fails_the_step_and_stops_the_run() {
    let server = start_server().await;
    let rt = runtime().await;
    // One second, so the test costs a second and not thirty.
    let flow_id = flow_calling(&rt, &server.url("/slow"), 1).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    let started = std::time::Instant::now();
    turn(&rt, &Limits::allowing_private_addresses()).await;
    let elapsed = started.elapsed();

    assert!(elapsed.as_secs() < 10, "it gave up on time ({elapsed:?})");
    assert_eq!(server.hits(), 1, "the request did go out");
    let (status, error) = run_status(&rt, &flow_id).await;
    assert_eq!(status, "failed", "v1 is `on_error: stop`");
    assert!(error.contains("flow.http_timeout"), "{error}");
}

#[tokio::test]
async fn an_error_status_fails_the_step_instead_of_being_read_as_success() {
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/boom"), 5).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    turn(&rt, &Limits::allowing_private_addresses()).await;

    let (status, error) = run_status(&rt, &flow_id).await;
    assert_eq!(status, "failed");
    assert!(error.contains("flow.http_status") && error.contains("500"), "{error}");
    // The body is in the error, because "500" alone is not something anybody can act on.
    assert!(error.contains("the till is on fire"), "{error}");
}

#[tokio::test]
async fn an_enormous_answer_is_truncated_instead_of_becoming_the_hubs_memory() {
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/big"), 10).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    let results = turn(&rt, &Limits::allowing_private_addresses()).await;

    let IoResult::Done(output) = &results[0] else {
        panic!("a 3 MB answer is still an answer: {results:?}");
    };
    assert_eq!(output["truncated"], json!(true), "the step says it was cut");
    let kept = output["body_text"].as_str().unwrap().len();
    assert_eq!(kept, 1024 * 1024, "one megabyte, not three");
}

// ── anti-SSRF ─────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_name_that_resolves_inside_this_network_is_refused_and_nothing_is_dialled() {
    // `localhost` is a NAME, so the literal check does not catch it: this is the resolver guard,
    // and it is the one that closes DNS rebinding — the addresses it approves ARE the addresses
    // hyper dials, so there is no second lookup to swap them in.
    let server = start_server().await;
    let rt = runtime().await;
    let port = server.base.rsplit(':').next().unwrap().to_string();
    let url = format!("http://localhost:{port}/ok");
    let flow_id = flow_calling(&rt, &url, 5).await;
    allow(&rt, &flow_id, &format!("http://localhost:{port}/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    // The limits that SHIP — this test is about the guard, so it does not bend them.
    turn(&rt, &Limits::default()).await;

    assert_eq!(server.hits(), 0, "the socket was never opened");
    let (status, error) = run_status(&rt, &flow_id).await;
    assert_eq!(status, "failed");
    assert!(error.contains("flow.http_blocked"), "{error}");
    assert!(
        error.contains("127.0.0.1") || error.contains("::1"),
        "the refusal names the address it resolved to: {error}"
    );
}

#[tokio::test]
async fn a_literal_address_inside_this_network_is_refused_even_with_a_grant_for_it() {
    // The allow-list and the SSRF guard are different questions: an admin can grant a hub's own
    // address by mistake, and the answer is still no.
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/ok"), 5).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    turn(&rt, &Limits::default()).await;

    assert_eq!(server.hits(), 0);
    let (status, error) = run_status(&rt, &flow_id).await;
    assert_eq!(status, "failed");
    assert!(error.contains("flow.http_blocked"), "{error}");
}

/// hub#728 — the bug a QA reproduced on a live hub: `http://2130706433:8791/api/hub/context`
/// answered 200 with the hub's own context inside it. `2130706433` IS `127.0.0.1` to the parser
/// the HTTP client uses; it was «some host name» to a guard that did its own string cutting.
///
/// The zero is the point, and so is its twin below it: the same decimal URL DOES reach this
/// server when the guard is deliberately bent, which is what makes the zero mean "refused" and
/// not "unparseable".
#[tokio::test]
async fn an_address_written_in_decimal_is_the_loopback_it_spells() {
    let server = start_server().await;
    let rt = runtime().await;
    let port = server.base.rsplit(':').next().unwrap().to_string();
    let decimal = format!("http://2130706433:{port}/ok"); // 2130706433 == 127.0.0.1

    let flow_id = flow_calling(&rt, &decimal, 5).await;
    // The grant an admin would really write, in the notation they would really read.
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    turn(&rt, &Limits::default()).await;

    assert_eq!(server.hits(), 0, "the socket was never opened");
    let (status, error) = run_status(&rt, &flow_id).await;
    assert_eq!(status, "failed");
    assert!(
        error.contains("flow.http_blocked"),
        "the allow-list agreed — it is the ADDRESS guard that refuses, and it must be the one \
         that speaks: {error}"
    );
    assert!(
        error.contains("127.0.0.1"),
        "the refusal names the address, not the decimal it was hidden behind: {error}"
    );
}

#[tokio::test]
async fn the_same_decimal_address_reaches_the_same_server_when_the_guard_is_bent() {
    let server = start_server().await;
    let rt = runtime().await;
    let port = server.base.rsplit(':').next().unwrap().to_string();
    let flow_id = flow_calling(&rt, &format!("http://2130706433:{port}/ok"), 5).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    let results = turn(&rt, &Limits::allowing_private_addresses()).await;

    assert_eq!(server.hits(), 1, "`2130706433` is this very server");
    assert_eq!(
        results,
        vec![IoResult::Done(json!({
            "status": 200, "ok": true, "body_json": { "name": "Marta", "id": 7 }
        }))]
    );
}

/// hub#729 — `…/ok/../boom` matched a grant for `/ok*` and fetched `/boom`. The grant did not
/// contain what it said it contained.
#[tokio::test]
async fn a_dot_segment_that_leaves_the_granted_path_never_reaches_the_server() {
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/ok/../boom"), 5).await;
    allow(&rt, &flow_id, &server.url("/ok*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    turn(&rt, &Limits::allowing_private_addresses()).await;

    assert_eq!(server.hits(), 0, "`/boom` was never granted");
    let (status, error) = run_status(&rt, &flow_id).await;
    assert_eq!(status, "failed");
    assert!(error.contains("flow.grant_denied"), "{error}");
}

/// The twin: a `..` that lands back INSIDE the grant is inside the grant. The path is judged
/// resolved, not refused for containing a dot — a fix that blocked everything would pass the test
/// above and break every flow.
#[tokio::test]
async fn a_dot_segment_that_lands_back_inside_the_grant_still_goes_out() {
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/text/../ok"), 5).await;
    allow(&rt, &flow_id, &server.url("/ok*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    let results = turn(&rt, &Limits::allowing_private_addresses()).await;

    assert_eq!(server.hits(), 1);
    assert_eq!(
        results,
        vec![IoResult::Done(json!({
            "status": 200, "ok": true, "body_json": { "name": "Marta", "id": 7 }
        }))],
        "it was fetched from `/ok`, which is what the grant named"
    );
}

/// **The invariant of hub#728 + hub#729, measured at the wire.** The URL the guard judged and the
/// URL hyper is handed are the same object, so no transformation can be inserted between them
/// without this failing.
#[tokio::test]
async fn the_url_that_is_judged_is_the_url_that_is_dialled() {
    let server = start_server().await;
    let rt = runtime().await;
    let port = server.base.rsplit(':').next().unwrap().to_string();
    // Every trap of both issues in one URL: a decimal host, a `..`, a `\`, and a default port.
    let flow_id = flow_calling(&rt, &format!("http://2130706433:{port}/text/..\\ok"), 5).await;
    allow(&rt, &flow_id, &server.url("/ok*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    let report = rt.process_flows().await.unwrap();
    let PendingIo::Http { request, .. } = &report.pending_io[0] else {
        panic!("the step asked for an http call: {:?}", report.pending_io);
    };

    let wire = flow_io::wire_request(request, &Limits::allowing_private_addresses())
        .expect("the guard let it through");
    assert_eq!(
        wire.url(),
        &request.url,
        "what goes on the wire is the very URL the allow-list and the guard judged"
    );
    assert_eq!(
        request.url.as_str(),
        server.url("/ok"),
        "and that URL is the resolved one, not the text the flow author typed"
    );
}

#[tokio::test]
async fn a_redirect_is_not_followed_because_the_second_hop_was_never_granted() {
    // A 302 is a SECOND request, to a location the server chose — not the admin. Following it
    // would walk straight past both the allow-list and the address guard.
    let server = start_server().await;
    let rt = runtime().await;
    let flow_id = flow_calling(&rt, &server.url("/redirect"), 5).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    turn(&rt, &Limits::allowing_private_addresses()).await;

    assert_eq!(server.hits(), 1, "the redirect itself, and nothing after it");
    let (status, error) = run_status(&rt, &flow_id).await;
    assert_eq!(status, "failed");
    assert!(error.contains("302"), "the step reports the 3xx it got: {error}");
}

/// The wiring the 1 s loop uses: `process_flows` → [`flow_io::dispatch`] → `complete_flow_io`,
/// with the limits that really ship. The call is refused (a fake server lives on loopback), and
/// that is the point of THIS test: what it proves is that the result comes back and the run ends
/// instead of sitting `running` until its lease expires.
#[tokio::test]
async fn the_background_loop_completes_what_it_dispatched() {
    use erplora_server::{AppState, HubConfig};

    let server = start_server().await;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    let flow_id = flow_calling(&rt, &server.url("/ok"), 5).await;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    let mut config = HubConfig::from_env();
    config.hub_id = HUB.to_string();
    let state = AppState::with_config(rt, config);

    let pending = {
        let rt = state.runtime.read().await;
        rt.process_flows().await.unwrap().pending_io
    };
    assert_eq!(pending.len(), 1);
    flow_io::dispatch(&state, pending);

    // The dispatched task completes it out of band; wait for the run to stop being in flight.
    let mut status = String::new();
    for _ in 0..50 {
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        let rt = state.runtime.read().await;
        let run = rt.list_flow_runs(&flow_id, 1, None).await.unwrap().remove(0);
        status = run.status.clone();
        if status == "failed" || status == "pending" {
            assert!(run.last_error.contains("flow.http_blocked"), "{}", run.last_error);
            break;
        }
    }
    assert_eq!(status, "failed", "the run came back from its I/O instead of hanging");
    assert_eq!(server.hits(), 0, "and the guard that ships refused loopback");
}

// ── secrets, on the wire ──────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_credential_arrives_at_the_server_and_never_at_the_run_history() {
    // SAFETY: every test in this binary that touches the master key sets it to the same value, so
    // there is nothing for a parallel test to observe changing.
    unsafe { std::env::set_var("HUB_SECRETS_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=") };

    let server = start_server().await;
    let rt = runtime().await;
    rt.put_flow_secret("API_KEY", "sk-live-42", "hub_user:1").await.unwrap();
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Caller".into(),
                enabled: true,
                definition: json!({
                    "schema_version": 1,
                    "steps": [{
                        "id": "call", "kind": "http", "url": server.url("/echo-key"),
                        "headers": { "Authorization": "Bearer {{secret.API_KEY}}" }
                    }]
                }),
            },
            "hub_user:1",
        )
        .await
        .unwrap()
        .id;
    allow(&rt, &flow_id, &server.url("/*")).await;
    rt.start_flow_run(&flow_id, &json!({}), "hub_user:1").await.unwrap();

    turn(&rt, &Limits::allowing_private_addresses()).await;

    // It really went out…
    assert_eq!(server.hits(), 1);
    assert_eq!(server.last_authorization(), "Bearer sk-live-42");

    // …and it is nowhere in what the hub wrote down — not in the step's input, and not in the
    // OUTPUT either, because this server echoed the key back inside its answer.
    let (run, steps) = {
        let run = rt.list_flow_runs(&flow_id, 1, None).await.unwrap().remove(0);
        rt.get_flow_run(&run.id).await.unwrap()
    };
    let written = format!("{:?}{:?}", run, steps);
    assert!(!written.contains("sk-live-42"), "the run history holds the credential: {written}");

    // Two layers, and this is what each of them caught — they are not redundant:
    //
    //  · the WRITE door (hub#662, `HttpRequest::scrub`): the OUTPUT. This server echoed the key
    //    back inside its answer, and no rule about key NAMES could have found it there — it is
    //    free-form data. It is `***` because the request scrubbed its own credential out of
    //    everything that came back.
    //  · the READ door (hub#666, `store::redact_step`): the INPUT. The `Authorization` header is
    //    blanked when the run is read, by learning the key name from the flow's own definition.
    assert!(
        written.contains("Bearer ***"),
        "the echoed credential is scrubbed out of the answer: {written}"
    );
    assert!(
        written.contains("«secret»"),
        "and the header that carried it is blanked on the way out: {written}"
    );
}

#[tokio::test]
async fn the_secret_names_are_listed_and_the_values_have_no_way_out() {
    // SAFETY: see above — same value, every test.
    unsafe { std::env::set_var("HUB_SECRETS_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=") };
    let rt = runtime().await;
    rt.put_flow_secret("API_KEY", "sk-live-42", "hub_user:1").await.unwrap();

    let listed = rt.list_flow_secrets().await.unwrap();
    let as_json: Value = serde_json::to_value(&listed).unwrap();
    assert_eq!(as_json[0]["name"], json!("API_KEY"));
    assert!(
        !as_json.to_string().contains("sk-live-42"),
        "the listing is names: {as_json}"
    );

    rt.delete_flow_secret("API_KEY", "hub_user:1").await.unwrap();
    assert!(rt.list_flow_secrets().await.unwrap().is_empty());
}
