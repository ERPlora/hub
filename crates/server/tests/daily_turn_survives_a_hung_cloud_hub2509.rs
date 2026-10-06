//! **A connection erplora.com leaves hanging must not silence the hub** (hub#2509).
//!
//! Once a day the hub checks its plan with erplora.com and sends its heartbeat, which is also what
//! tells erplora.com that somebody works in this business: a free hub whose heartbeat stops
//! carrying that mark is paused at 60 days and deleted at 120. Both calls went through a client
//! without any time limit, inside a single loop, so a control plane that ACCEPTS the connection and
//! then never answers froze the turn for good: no other heartbeat, no other plan check, until
//! somebody restarted the hub.
//!
//! Two locks, each pinned on its own so that neither hides the other:
//! - the shared client every call to erplora.com goes through gives up on its own, with the
//!   production limits (the clock is paused, so the test does not wait them out);
//! - the daily turn gives each step its own deadline, so even a call without a limit of its own
//!   cannot stop the next beat — and the next beat still carries the activity mark.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use cloud_client::Auth;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::daily_usage::{
    send_heartbeat, spawn_daily_turn, DailyUsageHeartbeat, PendingObligationFields,
};
use erplora_server::entitlement::fetch_verified_claims;
use erplora_server::{AppState, AuthMode, HubConfig, CLOUD_CALL_TIMEOUT, CLOUD_CONNECT_TIMEOUT};
use tokio::io::AsyncReadExt;

const HEARTBEAT_PATH: &str = "/api/v1/hub/device/heartbeat/";

fn config(cloud_base_url: String) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-hub2509-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-2509".into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

async fn state_against(cloud_base_url: String) -> AppState {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-2509");
    rt.ensure_system_tables().await.unwrap();
    AppState::with_config(rt, config(cloud_base_url))
}

fn machine() -> Auth {
    Auth::HubToken {
        hub_id: "hub-2509".into(),
        token: "machine-secret".into(),
    }
}

/// One request as erplora.com received it before going silent.
#[derive(Debug, Clone)]
struct Received {
    path: String,
    body: String,
}

/// An erplora.com that accepts every connection, reads the whole request and never writes a byte
/// back — a stuck proxy, a worker that never answers. Returns its base URL and what it received.
async fn a_cloud_that_never_answers() -> (String, Arc<Mutex<Vec<Received>>>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let received = Arc::new(Mutex::new(Vec::new()));
    let log = received.clone();
    tokio::spawn(async move {
        while let Ok((mut socket, _)) = listener.accept().await {
            let log = log.clone();
            tokio::spawn(async move {
                if let Some(request) = read_request(&mut socket).await {
                    log.lock().unwrap().push(request);
                }
                // Held open and never answered, until the hub gives up on it.
                let mut sink = [0u8; 1024];
                while matches!(socket.read(&mut sink).await, Ok(n) if n > 0) {}
            });
        }
    });
    (format!("http://{addr}"), received)
}

async fn read_request(socket: &mut tokio::net::TcpStream) -> Option<Received> {
    let mut buf = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        let n = socket.read(&mut chunk).await.ok()?;
        if n == 0 {
            return None;
        }
        buf.extend_from_slice(&chunk[..n]);
        let text = String::from_utf8_lossy(&buf).to_string();
        let Some(head_end) = text.find("\r\n\r\n") else {
            continue;
        };
        let head = &text[..head_end];
        let length = head
            .lines()
            .find_map(|line| {
                let (name, value) = line.split_once(':')?;
                name.eq_ignore_ascii_case("content-length")
                    .then(|| value.trim().parse::<usize>().ok())
                    .flatten()
            })
            .unwrap_or(0);
        let body = &text[head_end + 4..];
        if body.len() < length {
            continue;
        }
        let path = head.split_whitespace().nth(1)?.to_string();
        return Some(Received {
            path,
            body: body.to_string(),
        });
    }
}

fn heartbeats(received: &Mutex<Vec<Received>>) -> Vec<Received> {
    received
        .lock()
        .unwrap()
        .iter()
        .filter(|r| r.path == HEARTBEAT_PATH)
        .cloned()
        .collect()
}

/// Runs `call` against the silent erplora.com and measures how long the hub waits on it.
///
/// The clock runs for real until erplora.com holds the whole request — a paused clock could jump
/// past the connection before the listener even saw it — and is paused from then on: the limits
/// are the production ones, and a call without any limit leaves only the one-hour guard to fire.
async fn time_to_give_up<T: Send + 'static>(
    call: impl std::future::Future<Output = T> + Send + 'static,
    received: &Mutex<Vec<Received>>,
) -> (T, Duration) {
    let started = tokio::time::Instant::now();
    let call = tokio::spawn(call);
    let reached = tokio::time::Instant::now() + Duration::from_secs(10);
    while received.lock().unwrap().is_empty() {
        assert!(
            tokio::time::Instant::now() < reached,
            "the call never reached the silent erplora.com"
        );
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    tokio::time::pause();
    let outcome = tokio::time::timeout(Duration::from_secs(3600), call)
        .await
        .expect("still waiting on a silent erplora.com an hour later (hub#2509)")
        .unwrap();
    (outcome, started.elapsed())
}

/// The plan check of the daily turn, through the client the hub really builds, ends by itself
/// when erplora.com never answers — within the production limits, not «some day».
#[tokio::test]
async fn the_plan_check_gives_up_on_a_cloud_that_never_answers() {
    let (cloud, received) = a_cloud_that_never_answers().await;
    let state = state_against(cloud.clone()).await;

    let http = state.http.clone();
    let (outcome, waited) = time_to_give_up(
        async move { fetch_verified_claims(&http, &cloud, &machine(), 0).await },
        &received,
    )
    .await;

    assert!(
        outcome.is_err(),
        "a silent erplora.com is a failed check: {outcome:?}"
    );
    assert!(
        waited <= CLOUD_CALL_TIMEOUT + Duration::from_secs(1),
        "gave up after {waited:?}, beyond the ceiling of the shared client"
    );
}

/// Same for the heartbeat itself, the call that carries the activity mark.
#[tokio::test]
async fn the_heartbeat_gives_up_on_a_cloud_that_never_answers() {
    let (cloud, received) = a_cloud_that_never_answers().await;
    let state = state_against(cloud.clone()).await;
    let body = DailyUsageHeartbeat {
        orders_today: None,
        last_sale_at: None,
        terminals: None,
        active_users: None,
        last_user_activity_at: Some("2026-10-06T09:00:00Z".into()),
        activity: Vec::new(),
        core_version: "test".into(),
        pending: PendingObligationFields(Vec::new()),
        cpu_pct: None,
        memory_used_mb: None,
        memory_limit_mb: None,
        memory_peak_mb: None,
        transmission_route: None,
    };

    let http = state.http.clone();
    let (outcome, waited) = time_to_give_up(
        async move { send_heartbeat(&http, &cloud, &machine(), &body).await },
        &received,
    )
    .await;

    assert!(outcome.is_err(), "a silent erplora.com is a failed beat");
    assert!(waited <= CLOUD_CALL_TIMEOUT + Duration::from_secs(1));
    assert_eq!(heartbeats(&received).len(), 1);
}

/// The P0 itself: with a call that hangs, the next turn still runs and its heartbeat still
/// carries the activity mark that keeps a free hub in use from being paused and deleted.
#[tokio::test]
async fn the_daily_turn_keeps_beating_when_a_cloud_call_hangs() {
    let (cloud, received) = a_cloud_that_never_answers().await;
    let mut state = state_against(cloud).await;
    // A client with no limit of its own: the turn must not depend on the client to move on.
    state.http = reqwest::Client::new();
    state.activity.touch(1_790_000_000);

    let turn = spawn_daily_turn(
        state,
        Duration::from_millis(200),
        Duration::from_millis(300),
    );

    let deadline = tokio::time::Instant::now() + Duration::from_secs(20);
    while heartbeats(&received).len() < 2 {
        assert!(
            tokio::time::Instant::now() < deadline,
            "the daily turn froze on a hung call: {} heartbeat(s) in 20 s with a 200 ms period (hub#2509)",
            heartbeats(&received).len()
        );
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    turn.abort();

    let second = heartbeats(&received)[1].clone();
    let sent: serde_json::Value = serde_json::from_str(&second.body).unwrap();
    assert!(
        sent["last_user_activity_at"].is_string(),
        "an undelivered activity mark travels again on the next beat: {sent}"
    );
}

/// The other side of the ceiling: a call that streams asks for a longer one, so the assistant's
/// answer is not cut at the shared client's limit when erplora.com pauses in the middle of it.
#[tokio::test]
async fn the_assistant_stream_outlives_the_shared_ceiling() {
    use axum::body::Body;
    use axum::http::Request;
    use futures_util::StreamExt;
    use tower::ServiceExt; // oneshot

    let pause = CLOUD_CALL_TIMEOUT + Duration::from_secs(30);
    let app = axum::Router::new().route(
        "/api/v1/hub/device/assistant/chat/stream/",
        axum::routing::post(move || async move {
            let first = futures_util::stream::once(async {
                Ok::<_, std::io::Error>(axum::body::Bytes::from_static(
                    b"data: {\"text\":\"first\"}\n\n",
                ))
            });
            let second = futures_util::stream::once(async move {
                tokio::time::sleep(pause).await;
                Ok::<_, std::io::Error>(axum::body::Bytes::from_static(
                    b"data: {\"text\":\"second\"}\n\ndata: [DONE]\n\n",
                ))
            });
            axum::response::Response::builder()
                .header("content-type", "text/event-stream")
                .body(Body::from_stream(first.chain(second)))
                .unwrap()
        }),
    );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-2509");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let router = erplora_server::app(AppState::with_config(
        rt,
        config(format!("http://{addr}")),
    ));

    let response = router
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/assistant/chat/stream")
                .header("x-hub-session", &session)
                .header("content-type", "application/json")
                .body(Body::from(
                    r#"{"messages":[{"role":"user","content":"hi"}]}"#,
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    let mut body = response.into_body().into_data_stream();
    let mut text = String::new();
    // Real clock until erplora.com is streaming (the session check reads the database, whose pool
    // has time limits of its own); from the first frame on, the clock is paused.
    let first = tokio::time::timeout(Duration::from_secs(10), body.next())
        .await
        .expect("the assistant stream did not start")
        .expect("the assistant stream ended before its first frame")
        .unwrap();
    text.push_str(&String::from_utf8_lossy(&first));

    tokio::time::pause();
    let started = tokio::time::Instant::now();
    let rest = tokio::time::timeout(Duration::from_secs(3600), async {
        let mut rest = String::new();
        while let Some(chunk) = body.next().await {
            rest.push_str(&String::from_utf8_lossy(&chunk.unwrap()));
        }
        rest
    })
    .await
    .expect("the assistant stream never ended");
    text.push_str(&rest);

    assert!(started.elapsed() >= pause, "the pause did not happen: {text}");
    assert!(
        text.contains("second") && !text.contains("\"type\":\"error\""),
        "the stream was cut at the shared ceiling instead of reaching its end: {text}"
    );
}

/// An erplora.com that never even completes the connection (a full accept queue drops the
/// handshake, like a firewall that swallows it) is given up at the connection limit, well before
/// the ceiling of the whole call.
#[tokio::test]
async fn a_connection_that_never_completes_is_given_up_at_the_connect_limit() {
    let socket = tokio::net::TcpSocket::new_v4().unwrap();
    socket.bind("127.0.0.1:0".parse().unwrap()).unwrap();
    let listener = socket.listen(1).unwrap(); // never accepts
    let addr = listener.local_addr().unwrap();
    // Fill the accept queue: from here on the kernel drops every new handshake.
    let mut fillers = Vec::new();
    for _ in 0..16 {
        fillers.push(tokio::spawn(tokio::net::TcpStream::connect(addr)));
    }
    tokio::time::sleep(Duration::from_millis(300)).await;
    let state = state_against(format!("http://{addr}")).await;

    tokio::time::pause();
    let started = tokio::time::Instant::now();
    let outcome = tokio::time::timeout(
        Duration::from_secs(3600),
        fetch_verified_claims(&state.http, &format!("http://{addr}"), &machine(), 0),
    )
    .await
    .expect("the plan check is still connecting an hour later (hub#2509)");

    assert!(outcome.is_err(), "a connection that never completes is a failed check");
    assert!(
        started.elapsed() < CLOUD_CALL_TIMEOUT,
        "gave up after {:?}: the connection limit ({CLOUD_CONNECT_TIMEOUT:?}) did not act",
        started.elapsed()
    );
    drop(listener);
    for filler in fillers {
        filler.abort();
    }
}
