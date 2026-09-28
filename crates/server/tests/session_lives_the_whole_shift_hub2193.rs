//! **The hub session "drops after ~17 minutes"** — measured, it does not (hub#2193).
//!
//! The report came from the automated recording of the user manual on a Free-plan hub: at 08:16 the
//! recorder found the PIN lock screen, and minutes later the full «Entra en tu negocio» login. The
//! runtime's own log for that hub (Loki, 2026-09-26) shows what really happened: the last `200` of
//! that session at 06:14:53 UTC, the first `401` at 06:15:15 UTC, **no login and no eviction in
//! between** — and the recorder had signed in at ~18:14 UTC the evening before. Twelve hours to the
//! minute. The episode on 2026-09-25 is the same shape: sign-in at 18:44 UTC on the 24th, first
//! `401` on the first request after 06:44 UTC. Both takes (desktop and mobile) share ONE browser
//! profile, so they are one device and the Free plan's single-device limit never fired.
//!
//! That is the **shared-device window** (`SHARED_SESSION_TTL_SECS`, one shift, hub#358), working as
//! designed: the recorder's browser was never marked personal (the login screen claiming it was is
//! hub#2189, a separate fix), and a till must not keep an open session overnight.
//!
//! What this file pins is the path the recorder actually walked — the ONLINE login from a brand-new
//! browser, not the PIN door `session_ttl_by_device_mode.rs` covers — at the exact instants that
//! matter, with a simulated clock (the row's expiry is moved back as if time had passed):
//!
//!   - 17 minutes in, the session is alive (the reported symptom cannot come back unseen);
//!   - one minute before the shift ends, still alive;
//!   - one minute after, `401` — and **without** the eviction code, because time ended it, not
//!     another device;
//!   - a second sign-in from the SAME device on a one-device plan does not throw the first out.
//!
//! The existing TTL test tolerates twelve hours of slack on the shared side, so its lower bound is
//! "more than zero seconds": a 17-minute window would have passed it. This one would not.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::device_mode::SHARED_SESSION_TTL_SECS;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-2193";

/// A browser the hub has never seen: nobody marked it personal, so it is a shared device.
const NEW_BROWSER: &str = "browser-recorder-profile";

/// Test RSA pair: the "Cloud" signs with the private half, the hub verifies with the public one.
/// Same pair as `device_trust_enforce.rs` — it only has to be a valid key.
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

async fn fixture() -> (axum::Router, AppState, TestDb) {
    let test_db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-hub2193-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
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
    };
    let state = AppState::with_config(rt, cfg);
    (app(state.clone()), state, test_db)
}

fn sign_user_jwt() -> String {
    let claims = json!({
        "user_id": 7_i64,
        "email": "test@example.com",
        "token_type": "access",
        "exp": 9_999_999_999_i64,
        "hubs": [{"id": HUB_ID, "org": HUB_ID, "role": "admin"}],
    });
    let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
}

/// The online login the recorder used (email + password on the hub → `POST /api/auth/cloud`).
async fn cloud_login(router: &axum::Router, device_id: &str) -> String {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/cloud")
                .header("authorization", format!("Bearer {}", sign_user_jwt()))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({ "name": "Ana", "device_id": device_id }).to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    let body: Value = serde_json::from_slice(&bytes).unwrap();
    body["token"].as_str().unwrap().to_string()
}

/// The probe the shell uses to decide a session is dead (`lib/runtime.ts`).
async fn probe(router: &axum::Router, session: &str) -> (StatusCode, Value) {
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/api/settings")
                .header("x-hub-session", session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (status, serde_json::from_slice(&bytes).unwrap_or(Value::Null))
}

/// The simulated clock: pretends `elapsed_secs` have passed since the sign-in by moving the row's
/// expiry back by that much from what the login stamped. `stamped` is that original expiry.
async fn advance_clock(
    test_db: &TestDb,
    token: &str,
    stamped: chrono::DateTime<chrono::Utc>,
    elapsed_secs: i64,
) {
    let db = test_db.adapter().await;
    let mut p = Params::new();
    p.insert("token".into(), json!(token));
    p.insert(
        "expires_at".into(),
        json!((stamped - chrono::Duration::seconds(elapsed_secs)).to_rfc3339()),
    );
    db.execute(
        "UPDATE hub_session SET expires_at = :expires_at WHERE token = :token",
        &p,
    )
    .await
    .unwrap();
}

async fn stamped_expiry(test_db: &TestDb, token: &str) -> chrono::DateTime<chrono::Utc> {
    let db = test_db.adapter().await;
    let mut p = Params::new();
    p.insert("token".into(), json!(token));
    let res = db
        .query(
            "SELECT expires_at FROM hub_session WHERE token = :token",
            &p,
        )
        .await
        .unwrap();
    let raw = res.rows[0]["expires_at"].as_str().unwrap().to_string();
    chrono::DateTime::parse_from_rfc3339(&raw)
        .expect("expires_at is RFC3339")
        .with_timezone(&chrono::Utc)
}

const MINUTE: i64 = 60;

#[tokio::test]
async fn hub2193_an_online_login_on_a_new_browser_lives_the_whole_shift_not_17_minutes() {
    let (router, _state, test_db) = fixture().await;
    let token = cloud_login(&router, NEW_BROWSER).await;
    let stamped = stamped_expiry(&test_db, &token).await;

    // Pinned with a literal, not with the constant: a shorter window must fail HERE, even though
    // the rest of this test moves the clock by `SHARED_SESSION_TTL_SECS` and would follow it down.
    let window = (stamped - chrono::Utc::now()).num_seconds();
    assert!(
        (12 * 60 * MINUTE - 2 * MINUTE..=12 * 60 * MINUTE).contains(&window),
        "an online sign-in on a shared device opens a twelve-hour shift, got {window}s"
    );

    advance_clock(&test_db, &token, stamped, 17 * MINUTE).await;
    assert_eq!(
        probe(&router, &token).await.0,
        StatusCode::OK,
        "17 minutes after signing in the session has to be alive: this is the symptom of hub#2193"
    );

    advance_clock(&test_db, &token, stamped, SHARED_SESSION_TTL_SECS - MINUTE).await;
    assert_eq!(
        probe(&router, &token).await.0,
        StatusCode::OK,
        "a minute before the shift ends the session is still open"
    );

    advance_clock(&test_db, &token, stamped, SHARED_SESSION_TTL_SECS + MINUTE).await;
    let (status, body) = probe(&router, &token).await;
    assert_eq!(
        status,
        StatusCode::UNAUTHORIZED,
        "a shared device must not keep its session past the shift: that is an open till overnight"
    );
    assert_ne!(
        body["code"], "session_evicted_device_limit",
        "time ended it, not another device: the screen must not blame the plan ({body})"
    );
}

#[tokio::test]
async fn hub2193_signing_in_again_from_the_same_browser_on_a_one_device_plan_keeps_the_first_session()
{
    // The recorder's desktop and mobile takes share ONE browser profile, so ONE device id. The plan's
    // single-device limit is about other devices; the same device signing in again is not "another".
    let (router, state, _test_db) = fixture().await;
    let first = cloud_login(&router, NEW_BROWSER).await;
    {
        let arc = state.runtime_for(&state.hub_id()).await.unwrap();
        let rt = arc.read().await;
        rt.enforce_device_limit(1, Some(NEW_BROWSER)).await.unwrap();
    }
    assert_eq!(
        probe(&router, &first).await.0,
        StatusCode::OK,
        "the same browser signing in again must not evict its own earlier session"
    );
}
