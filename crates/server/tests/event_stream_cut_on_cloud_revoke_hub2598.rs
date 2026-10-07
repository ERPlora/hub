//! **Losing the membership in erplora.com ends the live channel the person had open** (`GET /ws`,
//! `GET /api/events`, hub#2598).
//!
//! When the SaaS no longer names a person a member of this hub, the hub learns it the next time a
//! credential of theirs reaches `POST /api/auth/cloud` (rule D, HUB-F144): it deactivates their
//! `hub_user` and deletes their sessions. hub#2571 made the doors of the hub itself (role change,
//! removal, device limit) end the person's channels; this one did not, so the till or the phone
//! the person had open kept hearing every sale, order and appointment until it reconnected.
//!
//! Each case pairs the revoked person with another person listening at the same instant, so a cut
//! that closed every channel of the hub fails here.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::event_stream::ERR_CREDENTIAL_ENDED;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use futures_util::{SinkExt, StreamExt};
use http_body_util::BodyExt;
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use serde_json::{json, Value};
use std::net::SocketAddr;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;
use tokio_tungstenite::tungstenite::Message;
use tower::ServiceExt;

const HUB_ID: &str = "hub-events-cut-hub2598";

const FRAME_TIMEOUT: Duration = Duration::from_secs(10);
/// How long a channel that must stay open is watched for an unwanted cut.
const QUIET_WINDOW: Duration = Duration::from_millis(500);

/// The account of the person erplora.com takes off the business.
const CLOUD_USER_ID: i64 = 4242;
const MEMBER_EMAIL: &str = "lucia@example.com";

// The same test RSA pair as `auth_cloud_presence.rs`: the "SaaS" signs, the hub verifies.
const PRIV: &str = r#"-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDzGzIyJJGCZ9C6
y6Bm5rDSD6oyPm6vNLbP1XE3JsIdtZx8yRBpfomjsgtl5BNixVgqFAxts5m7odJ1
A3i2oKdBqsVK1wF+jpVaEf8O6+ts+8s3ju8AZCyUSNjCqRUObUC9jjOCW5VSWSnU
sZdGNXU7UTWOtbvOxqy+IdFE0DOeazH+i2SSQ+WV4u37rlidGh0GHYSsnbQeHRyX
Z4iyYxCfQDlqGAYCPp3GCvEdra+TiZXmJfIl7as8/cTqBY3wOuscwCi7pGLGODQy
H8QawNShpzvUHNqtTo5/o4DVTWf3j0LUJDCllswkMIRMX9m9M9Dhvqr6qD9dei+j
uR8WwyGdAgMBAAECggEAEKuWv5V+XODdkVGRSD0dduoYE6XwVRdaSdorD0sbGIpx
lqT6+SDyM0VsPqprIeTCbPA/Ae7E5fbsxZVdW7icf4ZETSN9OL5yQ2DkipNm62xA
vSiR/wbff7OXGZIanYikXds4cQHytVjj42/iHbBgv5aMA6M2o7E/+zG6deuI/p3c
8iq9mBEA8ErV10ybS5lMyo1ZkIXWG2OStP4yXVg4jH9GVVBKrV/vFVDPXgJLY6nv
aOBRu130OwK89STAqI13kBZ3H+wksu6UFc9NoQFPRnTf6pW+NhiO9F0RRAZwVC+N
mJJ4xwKUB8sg9p6/mIfqQTjDuKd1IsvFcaDZgd3KSQKBgQD9BUOv1ok6PnSrSSrU
5RsiJHuJcqR//qvFpyABejsB0Ilmco/dgQN6Knc4JZWX2FVcK8mofTbpQPKc6aOZ
GE+15xP3W62MIgaz5kyltxqa0g9DIRKktmiQtGWHDUkL8kXyLwaNxHjj03h/3ku/
AaiAt8qZ1xhBl4JvBKhmrUOnXwKBgQD1+AtzZ9fHLjN3GOk4SRvIMOt1mB0OOnZY
19jTPJD+Pyw9AH8ohhhdTIQTRMm+TIC5n/G6lMtJu9iSwqY2Kis60UyJa6BxwJpf
WTB1hyRUe9jGtwv9Aj9dyLwAyGAqp00WTkwoF7nRZO6pEpwCntydOsHFLlGR3hG2
+LYU4dkEgwKBgQCgN2QsBSJyMjg4eiVYGBc9YHKlj2Wg8wecKf63UMnqlT1cFPEK
ZvZntlo1wH7gXwl2Svfv7BIIU6sNN1jzyZQ38DIRcQkM8kLiSdOBH9gF7zvg2yFu
EV9XOhQMF5qIqQonmCWDQcT3JuJnvcCjG46yqy7siWp/pkvetslX8yEi6wKBgAdz
MN2Y+pck1hg4X+/9fuLsYGVaax7gNG9ycjXLstSQk0Vxu2g9z4Ub6TAwODAUXx3A
M3EkSpf8IY4oaSJg2phYeIn9AYoQfFyA9g/JPRd1/NXf+3P5WnP7vX4Ek60XDiWr
z3Czb0RhWz0xvBn0N9hnTDEtuvjBEiZJmDI/uPQDAoGBAOIt9bClD86rZ+gQttCH
+IQF7kWpM5sFJ1T99WgzVhh2KcoAbYBJXeNBrDaV5RXH81lgpJCr33UUb6dEH6Ro
jmmYhehBeEknoM0QbKpNkltZHLxv3hOEr3cdJxFhTfF1xtknyuD4PkCQxNCopR1N
2LZnAS37uyj9SuBl2xKDyikA
-----END PRIVATE KEY-----
"#;

const PUB: &str = r#"-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA8xsyMiSRgmfQusugZuaw
0g+qMj5urzS2z9VxNybCHbWcfMkQaX6Jo7ILZeQTYsVYKhQMbbOZu6HSdQN4tqCn
QarFStcBfo6VWhH/DuvrbPvLN47vAGQslEjYwqkVDm1AvY4zgluVUlkp1LGXRjV1
O1E1jrW7zsasviHRRNAznmsx/otkkkPlleLt+65YnRodBh2ErJ20Hh0cl2eIsmMQ
n0A5ahgGAj6dxgrxHa2vk4mV5iXyJe2rPP3E6gWN8DrrHMAou6Rixjg0Mh/EGsDU
oac71BzarU6Of6OA1U1n949C1CQwpZbMJDCETF/ZvTPQ4b6q+qg/XXovo7kfFsMh
nQIDAQAB
-----END PUBLIC KEY-----
"#;

struct Server {
    addr: SocketAddr,
    state: AppState,
    /// Another person of the hub (PIN only), listening at the same time.
    other: String,
}

async fn serve() -> Server {
    static NEXT: AtomicU32 = AtomicU32::new(0);
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let other_user = rt
        .create_user("Marta", "3579", "manager", None)
        .await
        .unwrap();
    let other = rt.create_session(&other_user, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!(
        "erplora-events-cut-2598-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: Some(PUB.into()),
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        demo: false,
    };
    let state = AppState::with_config(rt, cfg);
    let router = app(state.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        let _ = axum::serve(listener, router.into_make_service()).await;
    });
    Server { addr, state, other }
}

/// An erplora.com credential of the member, naming the hubs in `hubs`.
fn account_token(hubs: Value) -> String {
    account_token_with_email(MEMBER_EMAIL, hubs)
}

fn account_token_with_email(email: &str, hubs: Value) -> String {
    let claims = json!({
        "user_id": CLOUD_USER_ID,
        "email": email,
        "token_type": "access",
        "exp": 9_999_999_999_i64,
        "hubs": hubs,
    });
    let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
}

/// `POST /api/auth/cloud` with `bearer`, as the app sends it.
async fn cloud_login(srv: &Server, bearer: &str) -> (StatusCode, Value) {
    let req = Request::builder()
        .method("POST")
        .uri("/api/auth/cloud")
        .header("authorization", format!("Bearer {bearer}"))
        .header("content-type", "application/json")
        .body(Body::from(json!({}).to_string()))
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}

/// The member signs in with their account while erplora.com still names them: their session.
async fn member_signs_in(srv: &Server) -> String {
    let (status, body) = cloud_login(srv, &account_token(json!([{ "id": HUB_ID }]))).await;
    assert_eq!(status, StatusCode::OK, "a member signs in: {body}");
    body["token"]
        .as_str()
        .unwrap_or_else(|| panic!("the sign-in returns a session: {body}"))
        .to_string()
}

/// erplora.com took them off the business: a fresh credential of theirs no longer names this hub
/// and reaches the hub (rule D).
async fn erplora_revokes_the_member(srv: &Server) {
    let (status, body) = cloud_login(srv, &account_token(json!([{ "id": "another-hub" }]))).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["code"], "not_a_member", "{body}");
}

async fn ticket_status(srv: &Server, session: &str) -> (StatusCode, Value) {
    let req = Request::builder()
        .method("POST")
        .uri("/api/events/ticket")
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}

async fn ticket(srv: &Server, session: &str) -> String {
    let (status, json) = ticket_status(srv, session).await;
    assert_eq!(status, StatusCode::OK, "a session gets a ticket: {json}");
    json["data"]["ticket"].as_str().unwrap().to_string()
}

/// A frame every listener of this file is entitled to (an app was installed).
fn something_happens(srv: &Server) {
    srv.state
        .broadcast(json!({ "type": "module.installed", "module_id": "sales" }));
}

// ── The WebSocket door ────────────────────────────────────────────────────────────────────────

type Socket =
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

async fn ws_with(srv: &Server, token: &str) -> Socket {
    let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{}/ws", srv.addr))
        .await
        .expect("the upgrade succeeds");
    socket
        .send(Message::Text(
            json!({ "type": "auth", "token": token }).to_string(),
        ))
        .await
        .unwrap();
    socket
}

async fn ws_as(srv: &Server, session: &str) -> Socket {
    let t = ticket(srv, session).await;
    let mut socket = ws_with(srv, &t).await;
    assert_eq!(recv(&mut socket).await["type"], "stream.ready");
    socket
}

async fn recv(socket: &mut Socket) -> Value {
    loop {
        let next = tokio::time::timeout(FRAME_TIMEOUT, socket.next())
            .await
            .expect("the hub answered within the window");
        match next {
            Some(Ok(Message::Text(t))) => return serde_json::from_str(&t).expect("a JSON frame"),
            Some(Ok(_)) => continue,
            other => panic!("the channel closed instead of answering: {other:?}"),
        }
    }
}

/// The socket was told why and then closed: the next thing after the `stream.error` frame is the
/// end of the stream, not another frame.
async fn assert_cut(socket: &mut Socket, srv: &Server, what: &str) {
    let last = match tokio::time::timeout(FRAME_TIMEOUT, socket.next()).await {
        Err(_) => panic!("{what}: the socket was neither cut nor told"),
        Ok(Some(Ok(Message::Text(t)))) => serde_json::from_str::<Value>(&t).unwrap(),
        Ok(other) => panic!("{what}: the socket ended without saying why: {other:?}"),
    };
    assert_eq!(last["type"], "stream.error", "{what}: {last}");
    assert_eq!(last["code"], ERR_CREDENTIAL_ENDED, "{what}: {last}");
    something_happens(srv);
    loop {
        match tokio::time::timeout(FRAME_TIMEOUT, socket.next()).await {
            Err(_) => panic!("{what}: the socket was told it ended but was left open"),
            Ok(None) | Ok(Some(Err(_))) | Ok(Some(Ok(Message::Close(_)))) => return,
            Ok(Some(Ok(Message::Text(t)))) => {
                panic!("{what}: the socket kept hearing after the cut: {t}")
            }
            Ok(Some(Ok(_))) => continue,
        }
    }
}

/// The socket hears the next frame, and that frame is not a cut.
async fn assert_still_hears(socket: &mut Socket, srv: &Server, what: &str) {
    // Give a wrongly issued cut the time to land before the frame is sent: a cut that arrives
    // later than the frame would let this pass.
    tokio::time::sleep(QUIET_WINDOW).await;
    something_happens(srv);
    let heard = recv(socket).await;
    assert_eq!(heard["type"], "module.installed", "{what}: {heard}");
}

/// **The hole, over a socket.** The member listens on the phone they signed in with; erplora.com
/// takes them off the business and a fresh credential of theirs reaches the hub: their socket
/// closes with `events.credential_ended`. Another person's screen keeps listening.
#[tokio::test]
async fn losing_the_membership_closes_their_socket_hub2598() {
    let srv = serve().await;
    let session = member_signs_in(&srv).await;
    let mut member = ws_as(&srv, &session).await;
    let mut other = ws_as(&srv, &srv.other).await;

    erplora_revokes_the_member(&srv).await;

    assert_cut(&mut member, &srv, "erplora.com revoked the membership").await;
    assert_still_hears(&mut other, &srv, "another person").await;
}

/// …and the till where the same person entered with their **PIN** (a session that never touched
/// erplora.com) closes too: what is cut is the person, not the session the revoked credential
/// would have opened.
#[tokio::test]
async fn losing_the_membership_closes_the_socket_of_their_pin_session_hub2598() {
    let srv = serve().await;
    let session = member_signs_in(&srv).await;
    let user_id = srv
        .state
        .runtime
        .read()
        .await
        .resolve_session(&session)
        .await
        .unwrap()
        .expect("the session resolves")
        .id;
    let pin_session = srv
        .state
        .runtime
        .read()
        .await
        .create_session(&user_id, 3600, None)
        .await
        .unwrap();
    let mut till = ws_as(&srv, &pin_session).await;
    let mut other = ws_as(&srv, &srv.other).await;

    erplora_revokes_the_member(&srv).await;

    assert_cut(&mut till, &srv, "the till of the revoked member").await;
    assert_still_hears(&mut other, &srv, "another person").await;
}

/// …and so does the till of a person who was **invited by email** and has only ever entered with
/// their PIN: rule D closes that row by the address the credential carries, and its channels go
/// with it.
#[tokio::test]
async fn losing_the_membership_closes_the_socket_of_an_invited_person_hub2598() {
    let srv = serve().await;
    let invited = {
        let rt = srv.state.runtime.read().await;
        let id = rt
            .create_login_user(MEMBER_EMAIL, "employee", 0)
            .await
            .unwrap()
            .id;
        rt.create_session(&id, 3600, None).await.unwrap()
    };
    let mut till = ws_as(&srv, &invited).await;
    let mut other = ws_as(&srv, &srv.other).await;

    erplora_revokes_the_member(&srv).await;

    assert_cut(&mut till, &srv, "the till of the invited person").await;
    assert_still_hears(&mut other, &srv, "another person").await;
}

/// …and when the revocation closes **two** rows of the same person —the one linked to their
/// account, which entered with an older address, and an invitation waiting under the address the
/// account has now— the channels of both end.
#[tokio::test]
async fn losing_the_membership_closes_the_sockets_of_every_row_it_closes_hub2598() {
    let srv = serve().await;
    let (status, body) = cloud_login(
        &srv,
        &account_token_with_email("lucia.old@example.com", json!([{ "id": HUB_ID }])),
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{body}");
    let linked = body["token"].as_str().unwrap().to_string();
    let invited = {
        let rt = srv.state.runtime.read().await;
        let id = rt
            .create_login_user(MEMBER_EMAIL, "employee", 0)
            .await
            .unwrap()
            .id;
        rt.create_session(&id, 3600, None).await.unwrap()
    };
    let mut phone = ws_as(&srv, &linked).await;
    let mut till = ws_as(&srv, &invited).await;
    let mut other = ws_as(&srv, &srv.other).await;

    erplora_revokes_the_member(&srv).await;

    assert_cut(&mut phone, &srv, "the row linked to the account").await;
    assert_cut(
        &mut till,
        &srv,
        "the row invited under the account's address",
    )
    .await;
    assert_still_hears(&mut other, &srv, "another person").await;
}

/// **A ticket minted before the revocation opens nothing after it**: it was minted for a person
/// who is no longer on the team.
#[tokio::test]
async fn a_ticket_minted_before_the_revocation_opens_nothing_after_it_hub2598() {
    let srv = serve().await;
    let session = member_signs_in(&srv).await;
    let early = ticket(&srv, &session).await;

    erplora_revokes_the_member(&srv).await;

    let mut socket = ws_with(&srv, &early).await;
    let refused = recv(&mut socket).await;
    assert_eq!(refused["type"], "stream.error", "{refused}");
    assert_eq!(refused["code"], "unauthenticated", "{refused}");
}

/// **A credential that names nobody of this hub** (a stranger's account) cuts nothing: the
/// revocation reaches the channels of the people it closed, and only those.
#[tokio::test]
async fn a_strangers_refused_credential_closes_no_one_hub2598() {
    let srv = serve().await;
    let session = member_signs_in(&srv).await;
    let mut member = ws_as(&srv, &session).await;
    let mut other = ws_as(&srv, &srv.other).await;

    let stranger = {
        let claims = json!({
            "user_id": 9999,
            "email": "stranger@example.com",
            "token_type": "access",
            "exp": 9_999_999_999_i64,
            "hubs": [{ "id": "another-hub" }],
        });
        let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
        encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
    };
    let (status, body) = cloud_login(&srv, &stranger).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");

    assert_still_hears(&mut member, &srv, "the member erplora.com still names").await;
    assert_still_hears(&mut other, &srv, "another person").await;
}

// ── The SSE door (`GET /api/events`) ───────────────────────────────────────────────────────────

async fn sse_as(srv: &Server, session: &str) -> axum::body::BodyDataStream {
    let t = ticket(srv, session).await;
    let req = Request::builder()
        .uri(format!("/api/events?ticket={t}"))
        .body(Body::empty())
        .unwrap();
    let resp = app(srv.state.clone()).oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "the stream opens");
    resp.into_body().into_data_stream()
}

/// Next `data:` frame, or `Err(())` once the stream has ended. `Ok(None)` is silence.
async fn sse_next(
    body: &mut axum::body::BodyDataStream,
    window: Duration,
) -> Result<Option<Value>, ()> {
    let deadline = tokio::time::Instant::now() + window;
    let mut buffered = String::new();
    loop {
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        if left.is_zero() {
            return Ok(None);
        }
        match tokio::time::timeout(left, body.next()).await {
            Err(_) => return Ok(None),
            Ok(None) | Ok(Some(Err(_))) => return Err(()),
            Ok(Some(Ok(chunk))) => {
                buffered.push_str(&String::from_utf8_lossy(&chunk));
                for line in buffered.lines() {
                    if let Some(rest) = line.strip_prefix("data:") {
                        if let Ok(v) = serde_json::from_str::<Value>(rest.trim()) {
                            return Ok(Some(v));
                        }
                    }
                }
            }
        }
    }
}

/// **The same hole over SSE**: the stream says why and ends; another person's stream goes on.
#[tokio::test]
async fn losing_the_membership_closes_their_sse_stream_hub2598() {
    let srv = serve().await;
    let session = member_signs_in(&srv).await;
    let mut member = sse_as(&srv, &session).await;
    let mut other = sse_as(&srv, &srv.other).await;

    erplora_revokes_the_member(&srv).await;

    let last = sse_next(&mut member, FRAME_TIMEOUT)
        .await
        .expect("the stream said why before ending")
        .expect("the stream was neither cut nor told");
    assert_eq!(last["type"], "stream.error", "{last}");
    assert_eq!(last["code"], ERR_CREDENTIAL_ENDED, "{last}");
    tokio::time::sleep(QUIET_WINDOW).await;
    something_happens(&srv);
    assert!(
        sse_next(&mut member, FRAME_TIMEOUT).await.is_err(),
        "the stream ended after saying why"
    );
    let heard = sse_next(&mut other, FRAME_TIMEOUT)
        .await
        .expect("another person's stream is open")
        .expect("another person's stream hears");
    assert_eq!(heard["type"], "module.installed", "{heard}");
}
