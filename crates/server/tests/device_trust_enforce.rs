//! Device-trust has no bypass: omitting `device_id` must not skip the gate (hub#330).
//!
//! With `HUB_DEVICE_TRUST=enforce` the PIN login is meant to be refused on a device that never
//! did an online (cloud) login — §2.9. The check used to live inside an `if let Some(device_id)`
//! with **no `else`**, so a client that simply left `device_id` out walked straight past it. The
//! hub is on the public internet (`{slug}.erplora.com`), so "the client forgot to identify its
//! device" is not a benign case: it is the shape of the bypass.
//!
//! Contract fixed here:
//!   - enforce ON  + no `device_id`      → refused (`device_unidentified`)
//!   - enforce ON  + blank `device_id`   → refused (`device_unidentified`) — blanks are not names
//!   - enforce ON  + untrusted device    → refused (`device_untrusted`)
//!   - enforce ON  + trusted device      → allowed
//!   - enforce OFF + no `device_id`      → allowed (the gate can still be disarmed)
//!
//! Two things this file is careful about, because both were easy to get wrong:
//!
//!  - **What EARNS the trust is asserted through the door that grants it.** Most tests here set the
//!    state up with `rt.trust_device(..)`, which is seeding, not the contract: they would all stay
//!    green if `POST /api/auth/cloud` stopped writing the row and no PIN ever worked again. So one
//!    test walks the real path — a signed JWT through the online login, then the PIN.
//!  - **The device gate is FIRST in a chain**, ahead of the brute-force lock (hub#329) and the PIN
//!    check itself. A guard that runs first can hide the ones behind it, so the two below it are
//!    asserted with the gate satisfied — otherwise deleting them leaves this file green.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// Test RSA pair: the "Cloud" signs with the private half, the hub verifies with the public one.
/// Same pair as `auth_cloud_presence.rs` / `entitlement.rs` — it only has to be a valid key.
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

/// App in `Session` mode with one admin (PIN 1111), the given device-trust setting, and
/// optionally a device already marked as trusted (as an online cloud login would leave it).
async fn fixture(enforce: bool, trusted_device: Option<&str>) -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    if let Some(device_id) = trusted_device {
        rt.trust_device(device_id, "Admin").await.unwrap();
    }
    let temp = std::env::temp_dir().join(format!("erplora-device-trust-{}", std::process::id()));
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        // Loaded so the ONLINE login works: it is the door that earns a device its trust, and one
        // test below walks it instead of seeding the row.
        jwt_public_key: Some(PUB.into()),
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: enforce,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    };
    app(AppState::with_config(rt, cfg))
}

const HUB_ID: &str = "hub-dt";

/// Like [`fixture`] with a trusted device, but the device has since been **revoked** (its row
/// dropped, as `devices::revoke` does — ADR-0258).
async fn fixture_with_revoked(device_id: &str) -> axum::Router {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None).await.unwrap();
    rt.trust_device(device_id, "Admin").await.unwrap();
    rt.untrust_device(device_id).await.unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-device-trust-{}", std::process::id()));
    let cfg = HubConfig {
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: Some(PUB.into()),
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: true,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
        bootstrap_blueprint: None,
    };
    app(AppState::with_config(rt, cfg))
}

/// A signed user JWT this hub accepts: the `hubs` claim carries its own id, which is the presence
/// gate of ADR-0157.
fn sign_user_jwt() -> String {
    let claims = json!({
        "user_id": 7_i64,
        "email": "ana@example.com",
        "token_type": "access",
        "exp": 9_999_999_999_i64,
        "organizations": [{"id": HUB_ID, "role": "admin"}],
        "hubs": [{"id": HUB_ID, "org": HUB_ID, "role": "admin"}],
    });
    let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), &claims, &key).unwrap()
}

/// The ONLINE login — the door that grants a device its trust (§2.9). Nothing here seeds a row.
async fn post_cloud_login(app_: &axum::Router, device_id: &str) -> StatusCode {
    let res = app_
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
    res.status()
}

async fn post_pin(app_: &axum::Router, body: Value) -> (StatusCode, Value) {
    let res = app_
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/auth/pin")
                .header("content-type", "application/json")
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = res.status();
    let bytes = res.into_body().collect().await.unwrap().to_bytes();
    let json: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, json)
}

#[tokio::test]
async fn enforce_on_without_device_id_is_refused() {
    let app_ = fixture(true, None).await;
    let (status, body) = post_pin(&app_, json!({ "name": "Admin", "pin": "1111" })).await;
    assert_eq!(
        status,
        StatusCode::FORBIDDEN,
        "omitting device_id must not skip the gate: {body}"
    );
    assert_eq!(body["code"], json!("device_unidentified"), "{body}");
}

#[tokio::test]
async fn enforce_on_with_an_untrusted_device_is_refused() {
    let app_ = fixture(true, None).await;
    let (status, body) =
        post_pin(&app_, json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-1" })).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["code"], json!("device_untrusted"), "{body}");
}

#[tokio::test]
async fn enforce_on_with_a_trusted_device_is_allowed() {
    let app_ = fixture(true, Some("tablet-ok")).await;
    let (status, body) =
        post_pin(&app_, json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-ok" })).await;
    assert_eq!(status, StatusCode::OK, "a trusted device still logs in: {body}");
    assert_eq!(body["ok"], json!(true), "{body}");
}

#[tokio::test]
async fn enforce_off_without_device_id_still_works() {
    let app_ = fixture(false, None).await;
    let (status, body) = post_pin(&app_, json!({ "name": "Admin", "pin": "1111" })).await;
    assert_eq!(status, StatusCode::OK, "the gate can be disarmed: {body}");
    assert_eq!(body["ok"], json!(true), "{body}");
}

/// **A device_id of blanks is not an identity.** `"  "` used to walk past the `is_some()` check and
/// land on a lookup for a whitespace id — refused, but as `device_untrusted`, i.e. "the hub does
/// not know this device" instead of "you named none". The neighbouring door already trims
/// (`device_mode::device_id_of`), and two doors disagreeing about what counts as naming a device is
/// how one of them ends up storing `""` as a device.
#[tokio::test]
async fn a_device_id_of_blanks_names_no_device() {
    let app_ = fixture(true, None).await;
    for blank in ["", " ", "   ", "\t", "\n"] {
        let (status, body) =
            post_pin(&app_, json!({ "name": "Admin", "pin": "1111", "device_id": blank })).await;
        assert_eq!(status, StatusCode::FORBIDDEN, "{blank:?}: {body}");
        assert_eq!(
            body["code"],
            json!("device_unidentified"),
            "blanks name no device: {blank:?} → {body}"
        );
    }
}

/// **A trusted device is one that did an ONLINE login here** — asserted through the door that
/// grants it, not through `rt.trust_device`.
///
/// Every other test in this file seeds the row directly, so all of them would stay green if
/// `POST /api/auth/cloud` quietly stopped writing it — and the whole hub would be locked out of the
/// PIN with the suite passing. That is exactly what happened once already: the browser never sent
/// `device_id`, so no row was ever written, and nobody noticed because the gate was off (hub#454).
#[tokio::test]
async fn the_online_login_is_what_earns_the_pin() {
    let app_ = fixture(true, None).await;

    // Before the online login, this device is nobody.
    let (status, body) =
        post_pin(&app_, json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-bar" })).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");

    assert_eq!(
        post_cloud_login(&app_, "tablet-bar").await,
        StatusCode::OK,
        "the online login must succeed for this test to mean anything"
    );

    let (status, body) =
        post_pin(&app_, json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-bar" })).await;
    assert_eq!(status, StatusCode::OK, "the online login earned the PIN: {body}");

    // …and it earned it for THAT device only: the trust is not hub-wide (hub#454).
    let (status, body) =
        post_pin(&app_, json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-kitchen" })).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "trust is per device: {body}");
    assert_eq!(body["code"], json!("device_untrusted"), "{body}");
}

/// **Revoked and never-seen are the same answer.** Cutting a lost tablet (ADR-0258) drops its row,
/// and from the PIN door that must be indistinguishable from an id the hub never met: a thief
/// holding the tablet learns nothing about whether the owner reacted, and nobody can use the door
/// to sort real device ids from invented ones.
#[tokio::test]
async fn a_revoked_device_is_answered_exactly_like_one_never_seen() {
    let app_ = fixture(true, Some("tablet-lost")).await;
    let attempt = json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-lost" });

    let (ok_status, _) = post_pin(&app_, attempt.clone()).await;
    assert_eq!(ok_status, StatusCode::OK, "trusted to begin with");

    // The revocation door of ADR-0258 takes an admin session; what this test is about is the shape
    // of the PIN refusal afterwards, so the row is dropped straight through the runtime.
    let unknown = fixture(true, None).await;
    let (unknown_status, unknown_body) = post_pin(
        &unknown,
        json!({ "name": "Admin", "pin": "1111", "device_id": "tablet-never-seen" }),
    )
    .await;

    let revoked = fixture_with_revoked("tablet-lost").await;
    let (revoked_status, revoked_body) = post_pin(&revoked, attempt).await;

    assert_eq!(revoked_status, unknown_status, "same status");
    assert_eq!(revoked_body["code"], unknown_body["code"], "same code");
    assert_eq!(revoked_body["error"], unknown_body["error"], "same words");
}

/// **The device gate must not hide the brute-force lock (hub#329).** It runs first, so a chain
/// where it refuses everything would let the lock be deleted with this file still green. Asserted
/// with the gate SATISFIED: a trusted device typing the wrong PIN five times gets locked out.
#[tokio::test]
async fn the_device_gate_does_not_hide_the_brute_force_lock() {
    let app_ = fixture(true, Some("till-1")).await;
    let wrong = json!({ "name": "Admin", "pin": "9999", "device_id": "till-1" });
    for attempt in 1..=5 {
        let (status, body) = post_pin(&app_, wrong.clone()).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED, "attempt {attempt}: {body}");
    }
    let (status, body) = post_pin(&app_, wrong).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS, "{body}");
    assert_eq!(body["code"], json!("too_many_attempts"), "{body}");
}

/// **The device gate must not hide the PIN check either.** A trusted device is a place, never a
/// credential: the four digits still have to be right.
#[tokio::test]
async fn the_device_gate_does_not_hide_a_wrong_pin() {
    let app_ = fixture(true, Some("till-2")).await;
    let (status, body) =
        post_pin(&app_, json!({ "name": "Admin", "pin": "9999", "device_id": "till-2" })).await;
    assert_eq!(
        status,
        StatusCode::UNAUTHORIZED,
        "a trusted device with the wrong PIN does not get in: {body}"
    );
}
