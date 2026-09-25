//! `POST /api/entitlement/refresh` — the SaaS hands a running hub its new entitlement (hub#2105).
//!
//! Before this door a plan upgrade reached the hub only on the daily revalidation tick or on a
//! restart, so the SaaS restarted the hub mid-shift to make it land. The SaaS half (saas#1959)
//! POSTs the same RS256 token `GET /api/v1/hub/device/entitlement/` returns; the hub applies it
//! at once, and a `200 {"ok": true}` is the ONLY answer the SaaS reads as "delivered".
//!
//! There is no session and no key on this door: the signature IS the authentication. So every
//! refusal is asserted here by its stable code, and the brute-force guard with it.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use cloud_client::{EntitledModule, EntitlementClaims};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-1";

// Par de claves RSA de prueba: el "SaaS" firma con la privada, el Hub verifica con la pública.
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

const REFRESH_URI: &str = "/api/entitlement/refresh";

async fn fixture() -> (axum::Router, AppState) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    rt.create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let temp = std::env::temp_dir().join(format!("erplora-ent-push-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: Some(PUB.into()),
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let state = AppState::with_config(rt, cfg);
    (app(state.clone()), state)
}

fn now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64
}

/// The claims `build_signed_entitlement` emits, for this hub unless told otherwise.
fn claims(hub_id: &str, iat: i64, plan: &str, max_devices: u32) -> Value {
    json!({
        "hub_id": hub_id,
        "modules": [{ "module_id": "pos", "tier": "basic", "version": "1.0.0" }],
        "iat": iat,
        "exp": iat + 86_400,
        "grace_until": iat + 7 * 86_400,
        "paid_grace_until": iat + 5 * 86_400,
        "plan": plan,
        "max_devices": max_devices,
        "max_database_size_gb": 0,
        "max_users": 10,
    })
}

fn sign(claims: &Value) -> String {
    let key = EncodingKey::from_rsa_pem(PRIV.as_bytes()).unwrap();
    encode(&Header::new(Algorithm::RS256), claims, &key).unwrap()
}

fn seeded(iat: i64, plan: &str, max_devices: u32) -> EntitlementClaims {
    EntitlementClaims {
        hub_id: HUB_ID.into(),
        modules: vec![EntitledModule {
            module_id: "pos".into(),
            tier: "basic".into(),
            version: "1.0.0".into(),
        }],
        iat,
        exp: iat + 86_400,
        grace_until: iat + 7 * 86_400,
        paid_grace_until: None,
        plan: Some(plan.into()),
        max_devices,
        max_database_size_gb: 0,
        max_users: 3,
    }
}

fn push_from(ip: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(REFRESH_URI)
        .header("content-type", "application/json")
        .header("x-forwarded-for", ip)
        .body(Body::from(body.to_string()))
        .unwrap()
}

fn push(token: &str) -> Request<Body> {
    push_from("10.0.0.1", json!({ "token": token }))
}

async fn send(router: &axum::Router, req: Request<Body>) -> (StatusCode, Value) {
    let resp = router.clone().oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    )
}

fn current_plan(state: &AppState) -> (Option<String>, u32, u32) {
    let g = state.entitlement.read().unwrap();
    (
        g.last_claims.as_ref().and_then(|c| c.plan.clone()),
        g.max_devices(),
        g.consecutive_failures,
    )
}

#[tokio::test]
async fn a_signed_token_for_this_hub_applies_at_once_without_a_session() {
    let (router, state) = fixture().await;
    let t0 = now();
    {
        let mut g = state.entitlement.write().unwrap();
        g.apply_success(seeded(t0 - 3_600, "free", 1), t0 - 3_600);
        g.apply_failure(t0 - 60);
    }

    let (status, body) = send(&router, push(&sign(&claims(HUB_ID, t0, "starter", 3)))).await;

    assert_eq!(status, StatusCode::OK, "{body}");
    assert_eq!(body, json!({ "ok": true }));
    assert_eq!(current_plan(&state), (Some("starter".into()), 3, 0));
    assert_eq!(state.entitlement.read().unwrap().max_users(), 10);
}

/// The shell reads the plan through the 60 s cache of `GET /api/entitlement`: a push that left it
/// warm would show the OLD plan for up to a minute after the hub had already applied the new one.
#[tokio::test]
async fn applying_a_push_expires_the_cached_entitlement_the_shell_reads() {
    let (router, state) = fixture().await;
    let t0 = now();
    state
        .entitlement_proxy
        .write()
        .unwrap()
        .store_success(json!({ "plan": "free" }), t0);

    let (status, _) = send(&router, push(&sign(&claims(HUB_ID, t0, "starter", 3)))).await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        state.entitlement_proxy.read().unwrap().decide(t0),
        erplora_server::entitlement::Decision::Ask
    );
}

#[tokio::test]
async fn a_tampered_token_is_refused_and_changes_nothing() {
    let (router, state) = fixture().await;
    let t0 = now();
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(seeded(t0 - 3_600, "free", 1), t0 - 3_600);

    // Payload swapped for an enterprise one, signature kept from the real token.
    let real = sign(&claims(HUB_ID, t0, "starter", 3));
    let forged_payload = sign(&claims(HUB_ID, t0, "enterprise", 0));
    let parts: Vec<&str> = real.split('.').collect();
    let forged: Vec<&str> = forged_payload.split('.').collect();
    let tampered = format!("{}.{}.{}", parts[0], forged[1], parts[2]);

    let (status, body) = send(&router, push(&tampered)).await;

    assert_eq!(status, StatusCode::UNAUTHORIZED, "{body}");
    assert_eq!(body["error"]["code"], "entitlement_token_invalid");
    assert_eq!(current_plan(&state).0, Some("free".into()));
}

#[tokio::test]
async fn a_token_signed_for_another_hub_is_refused() {
    let (router, state) = fixture().await;
    let t0 = now();

    let (status, body) = send(
        &router,
        push(&sign(&claims("someone-else", t0, "starter", 3))),
    )
    .await;

    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["error"]["code"], "entitlement_wrong_hub");
    assert!(state.entitlement.read().unwrap().last_claims.is_none());
}

/// Anti-replay: the free-plan token captured before the upgrade cannot roll the hub back.
#[tokio::test]
async fn a_token_older_than_the_one_in_force_is_refused() {
    let (router, state) = fixture().await;
    let t0 = now();
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(seeded(t0, "starter", 3), t0);

    let (status, body) = send(&router, push(&sign(&claims(HUB_ID, t0 - 60, "free", 1)))).await;

    assert_eq!(status, StatusCode::CONFLICT, "{body}");
    assert_eq!(body["error"]["code"], "entitlement_stale");
    assert_eq!(current_plan(&state), (Some("starter".into()), 3, 0));
}

#[tokio::test]
async fn a_body_without_a_token_is_a_bad_request() {
    let (router, _state) = fixture().await;

    for body in [json!({}), json!({ "token": "" }), json!({ "token": 42 })] {
        let (status, resp) = send(&router, push_from("10.0.0.1", body.clone())).await;
        assert_eq!(status, StatusCode::BAD_REQUEST, "{body} → {resp}");
        assert_eq!(resp["error"]["code"], "entitlement_token_missing");
    }
}

/// The door is open, and an RSA verification is not free: a caller that keeps sending bad
/// tokens is locked out BEFORE the hub verifies anything else it sends. Another address — the
/// SaaS — is not affected.
#[tokio::test]
async fn repeated_bad_tokens_lock_that_address_out_but_not_the_saas() {
    let (router, state) = fixture().await;
    let t0 = now();
    let good = sign(&claims(HUB_ID, t0, "starter", 3));

    for _ in 0..5 {
        let (status, _) = send(
            &router,
            push_from("198.51.100.7", json!({ "token": "not.a.jwt" })),
        )
        .await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
    }

    let (status, body) = send(&router, push_from("198.51.100.7", json!({ "token": good }))).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS, "{body}");
    assert_eq!(body["error"]["code"], "entitlement_push_throttled");
    assert!(state.entitlement.read().unwrap().last_claims.is_none());

    let (status, body) = send(&router, push_from("203.0.113.9", json!({ "token": good }))).await;
    assert_eq!(status, StatusCode::OK, "{body}");
}

/// Applying a plan does not close anybody's session: a downgrade to one device evicts the extra
/// one at its NEXT sign-in, never in the middle of a sale.
#[tokio::test]
async fn applying_a_push_keeps_every_open_session_alive() {
    let (router, state) = fixture().await;
    let t0 = now();
    state
        .entitlement
        .write()
        .unwrap()
        .apply_success(seeded(t0 - 3_600, "starter", 0), t0 - 3_600);

    let mut tokens = Vec::new();
    for device in ["dev-A", "dev-B"] {
        let login = Request::builder()
            .method("POST")
            .uri("/api/auth/pin")
            .header("content-type", "application/json")
            .body(Body::from(
                json!({ "name": "Admin", "pin": "1111", "device_id": device }).to_string(),
            ))
            .unwrap();
        let (status, body) = send(&router, login).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        tokens.push(body["token"].as_str().unwrap().to_string());
    }

    let (status, _) = send(&router, push(&sign(&claims(HUB_ID, t0, "free", 1)))).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(current_plan(&state).1, 1);

    for token in &tokens {
        let req = Request::builder()
            .method("GET")
            .uri("/api/system")
            .header("x-hub-session", token)
            .body(Body::empty())
            .unwrap();
        let (status, body) = send(&router, req).await;
        assert_eq!(status, StatusCode::OK, "session closed by the push: {body}");
    }
}
