//! **A device's id never leaves it, except towards an administrator** (hub#2551).
//!
//! The `X-Device-Id` a browser mints (`dev_` + 32 hex, `apps/web/src/lib/device.ts`) is the only
//! proof the hub asks for to treat that browser as a TRUSTED device: the PIN door and the team list
//! of the access screen read `is_device_trusted(device_id)` and nothing else (hub#2510). The hub
//! cannot tell "the device that asks" from "whoever presents its id", so the id has to stay a
//! secret of its device.
//!
//! It did not: `GET /api/print/hosts` (any session, a cashier's included) listed the `deviceId` of
//! every device that prints — typically the trusted till at the counter — and a host registered
//! without a name was NAMED by its id on every coverage door (`liveHostLabels`). A cashier copied it
//! and, from any other browser, walked through the till's trust.
//!
//! What these tests pin:
//!  - a counter session reads its OWN device's id and nobody else's;
//!  - an administrator reads every id (it is what retiring a lost till takes, HUB-F197);
//!  - a host with no name is presented by a fallback that is NOT its id, on every door — the HTTP
//!    registry and the core query `hub.print.coverage` the modules read.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-print-hosts-hub2551";

/// Device ids exactly as the shell mints them: `dev_` + 32 hex.
const TILL: &str = "dev_3f9c2b1c4d5e6f708192a3b4c5d6e7f8";
const TABLET: &str = "dev_0a1b2c3d4e5f60718293a4b5c6d7e8f9";

/// Router, an admin session, a cashier session, and a second handle on the same schema to seed
/// hosts the way the fleet has them (registered without a name).
async fn fixture() -> (axum::Router, String, String, Runtime) {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let db = test_db.adapter().await;
    let probe = test_db.adapter().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let cashier_id = rt
        .create_user("Cashier", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let cashier = rt.create_session(&cashier_id, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-hub2551-{}", std::process::id()));
    let cfg = HubConfig {
        demo: false,
        hub_id: HUB_ID.into(),
        cloud_base_url: "https://example.invalid".into(),
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
    };
    let behind = Runtime::with_hub_id(Box::new(probe), HUB_ID);
    (app(AppState::with_config(rt, cfg)), admin, cashier, behind)
}

async fn call(
    router: &axum::Router,
    method: &str,
    uri: &str,
    session: &str,
    device_id: Option<&str>,
    body: Option<Value>,
) -> Value {
    let mut builder = Request::builder()
        .method(method)
        .uri(uri)
        .header("x-hub-session", session);
    if let Some(id) = device_id {
        builder = builder.header("x-device-id", id);
    }
    let req = match body {
        Some(b) => builder
            .header("content-type", "application/json")
            .body(Body::from(b.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    };
    let resp = router.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "{method} {uri}");
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// `GET /api/print/hosts` as `session`, from `device_id`.
async fn registry(router: &axum::Router, session: &str, device_id: Option<&str>) -> Value {
    call(router, "GET", "/api/print/hosts", session, device_id, None).await
}

/// The registry row of `device` — found by its NAME, since a counter session must not get the id.
fn host_named<'a>(body: &'a Value, name: &str) -> &'a Value {
    body["hosts"]
        .as_array()
        .unwrap_or_else(|| panic!("hosts is an array: {body}"))
        .iter()
        .find(|h| h["name"] == json!(name))
        .unwrap_or_else(|| panic!("no host named {name}: {body}"))
}

/// The till (trusted, prints the receipts) and the tablet (prints the kitchen's), both named.
async fn two_named_hosts(behind: &Runtime) {
    behind
        .register_print_host(TILL, "receipt", "Caja 1", "u1")
        .await
        .unwrap();
    behind
        .register_print_host(TABLET, "kitchen", "Tablet cocina", "u1")
        .await
        .unwrap();
}

#[tokio::test]
async fn hub2551_a_cashier_never_reads_the_id_of_another_device() {
    let (router, _admin, cashier, behind) = fixture().await;
    two_named_hosts(&behind).await;

    // From a browser that is neither of the two: the cashier at home.
    let body = registry(&router, &cashier, Some("dev_somebody_elses_browser_000000")).await;

    let text = body.to_string();
    assert!(
        !text.contains(TILL) && !text.contains(TABLET),
        "a counter session must not read any device id but its own: {body}"
    );
    // The screen still has what it paints: who prints, by name, and whether it is live.
    assert_eq!(host_named(&body, "Caja 1")["role"], json!("receipt"));
    assert_eq!(host_named(&body, "Caja 1")["live"], json!(true));
    assert!(host_named(&body, "Caja 1").get("deviceId").is_none());
}

#[tokio::test]
async fn hub2551_a_device_reads_its_own_id_and_only_its_own() {
    let (router, _admin, cashier, behind) = fixture().await;
    two_named_hosts(&behind).await;

    // The till itself asks: knowing its own id tells it nothing it did not already hold.
    let body = registry(&router, &cashier, Some(TILL)).await;

    assert_eq!(host_named(&body, "Caja 1")["deviceId"], json!(TILL));
    assert!(
        !body.to_string().contains(TABLET),
        "the till must not read the tablet's id: {body}"
    );
}

#[tokio::test]
async fn hub2551_an_administrator_reads_every_device_id() {
    let (router, admin, _cashier, behind) = fixture().await;
    two_named_hosts(&behind).await;

    // Retiring a lost or stolen till names it by id (HUB-F197): that door is the admin's.
    let body = registry(&router, &admin, None).await;

    assert_eq!(host_named(&body, "Caja 1")["deviceId"], json!(TILL));
    assert_eq!(
        host_named(&body, "Tablet cocina")["deviceId"],
        json!(TABLET)
    );
}

#[tokio::test]
async fn hub2551_a_nameless_host_is_never_named_by_its_id() {
    let (router, admin, cashier, behind) = fixture().await;
    // What the fleet has: a till registered before hosts took a name (hub#1560), not re-booted.
    behind
        .register_print_host(TILL, "receipt", "", "u1")
        .await
        .unwrap();

    // The registry, for the cashier and for the admin: a name that is NOT the id.
    for session in [&cashier, &admin] {
        let body = registry(&router, session, None).await;
        let host = &body["hosts"][0];
        assert_eq!(host["name"], json!("…e7f8"), "{body}");
        let coverage = &body["coverage"][0];
        assert_eq!(coverage["liveHostLabels"], json!(["…e7f8"]), "{body}");
    }
    let cashier_view = registry(&router, &cashier, None).await;
    assert!(
        !cashier_view.to_string().contains(TILL),
        "the cashier reads no id at all: {cashier_view}"
    );

    // The core query the modules' Printers screen reads (HUB-F202): same name, no id.
    let query = call(
        &router,
        "POST",
        "/api/query",
        &cashier,
        None,
        Some(json!({ "name": "hub.print.coverage", "params": {} })),
    )
    .await;
    assert_eq!(
        query["data"][0]["liveHostLabels"],
        json!(["…e7f8"]),
        "{query}"
    );
    assert!(
        !query.to_string().contains(TILL),
        "a module must not read the till's id either: {query}"
    );
}
