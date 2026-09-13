//! HTTP contract of the **print host registry** (hub#342, ADR-0196 §6).
//!
//! The queue (hub#341) guarantees a ticket is never lost for want of somebody holding a device.
//! This is the door where a device says *"I am the one that prints the kitchen's"*. What the tests
//! here pin is not that it persists — that is `erplora_runtime::print_hosts` — but **who may say
//! what about which device**:
//!
//!  - **A device only ever registers, beats for, or retires ITSELF.** The subject is the
//!    `X-Device-Id` of the caller and there is no way to name another device on the write doors,
//!    which is why an ordinary session is enough for them: the realistic gesture is "this device,
//!    the one in my hands, prints the kitchen's", and it has to work when the app starts, long
//!    after whoever set the hub up went home.
//!  - **Retiring somebody ELSE's device is an admin session** — the same asymmetry as
//!    `/api/device/mode`. That is the door for the till that was replaced or stolen, and it is the
//!    only one that can act on a device the caller is not holding.
//!  - **Reading takes a session.** Whether anything is going to print is operational information a
//!    cashier legitimately needs ("I charged and no ticket came out"), not public information.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB_ID: &str = "hub-print-hosts";

/// Router + an admin session and an employee session.
async fn fixture() -> (axum::Router, String, String) {
    let (router, admin, employee, _db) = fixture_with_db().await;
    (router, admin, employee)
}

/// Same fixture, plus a **second handle on the same schema**. Only the liveness test needs it: a
/// device that was switched off cannot report anything, so the only way to simulate it is to let
/// time pass on `last_seen_at`, and there is no HTTP door that writes it into the past (there must
/// not be — that would be a door for declaring yourself alive, which is exactly what the design
/// refuses).
async fn fixture_with_db() -> (axum::Router, String, String, erplora_db::PgAdapter) {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let db = test_db.adapter().await;
    let probe = test_db.adapter().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB_ID);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let employee_id = rt
        .create_user("Cashier", "2222", "employee", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    let employee = rt.create_session(&employee_id, 3600, None).await.unwrap();

    let temp = std::env::temp_dir().join(format!("erplora-print-hosts-{}", std::process::id()));
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
    (app(AppState::with_config(rt, cfg)), admin, employee, probe)
}

fn request(
    method: &str,
    uri: &str,
    session: Option<&str>,
    device_id: Option<&str>,
    body: Option<Value>,
) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    if let Some(id) = device_id {
        builder = builder.header("x-device-id", id);
    }
    match body {
        Some(b) => builder
            .header("content-type", "application/json")
            .body(Body::from(b.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// `POST /api/print/hosts` as `device_id`, for `role`.
async fn register(
    router: &axum::Router,
    session: &str,
    device_id: Option<&str>,
    role: &str,
    label: &str,
) -> (StatusCode, Value) {
    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/hosts",
            Some(session),
            device_id,
            Some(json!({ "role": role, "label": label })),
        ))
        .await
        .unwrap();
    (resp.status(), body_json(resp).await)
}

async fn registry(router: &axum::Router, session: &str) -> Value {
    let resp = router
        .clone()
        .oneshot(request(
            "GET",
            "/api/print/hosts",
            Some(session),
            None,
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    body_json(resp).await
}

fn coverage_of<'a>(body: &'a Value, role: &str) -> Option<&'a Value> {
    body["coverage"]
        .as_array()?
        .iter()
        .find(|c| c["role"] == json!(role))
}

/// The registry is hub data behind the same session gate as the rest of the core API — on every
/// door, including the read.
#[tokio::test]
async fn the_print_host_registry_requires_a_user_session() {
    let (router, _admin, _employee) = fixture().await;

    for (method, uri, body) in [
        (
            "POST",
            "/api/print/hosts",
            Some(json!({ "role": "kitchen" })),
        ),
        ("POST", "/api/print/hosts/heartbeat", None),
        ("GET", "/api/print/hosts", None),
        ("DELETE", "/api/print/hosts", None),
    ] {
        let resp = router
            .clone()
            .oneshot(request(method, uri, None, Some("till-1"), body))
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            StatusCode::UNAUTHORIZED,
            "{method} {uri} must not be anonymous"
        );
        // hub#1705: with the code the device can say «the session expired», not `→ HTTP 401`.
        let bytes = resp.into_body().collect().await.unwrap().to_bytes();
        let body: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
        assert_eq!(
            body["error"]["code"], "unauthorized",
            "{method} {uri}: {body}"
        );
    }
}

/// The happy path: the device in the cashier's hands declares itself the kitchen's print host and
/// shows up live, under the name the owner will read.
#[tokio::test]
async fn a_device_registers_itself_and_shows_up_live() {
    let (router, _admin, employee) = fixture().await;

    let (status, body) = register(
        &router,
        &employee,
        Some("till-1"),
        "kitchen",
        "Counter till",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["ok"], json!(true));
    assert_eq!(body["host"]["deviceId"], json!("till-1"));
    assert_eq!(body["host"]["role"], json!("kitchen"));
    assert_eq!(body["host"]["label"], json!("Counter till"));
    assert_eq!(body["host"]["live"], json!(true));

    let body = registry(&router, &employee).await;
    assert_eq!(body["hosts"].as_array().unwrap().len(), 1);
    assert_eq!(body["hosts"][0]["deviceId"], json!("till-1"));
    assert_eq!(body["hosts"][0]["live"], json!(true));
    assert_eq!(
        coverage_of(&body, "kitchen").unwrap()["liveHosts"],
        json!(1)
    );
}

/// The write doors act on the CALLER's device, so a caller that names none has not said which
/// device prints anything. Refused, never guessed — a registration under an empty id would put a
/// host that does not exist in front of a real queue.
#[tokio::test]
async fn a_caller_that_names_no_device_cannot_register_or_beat() {
    let (router, _admin, employee) = fixture().await;

    let (status, body) = register(&router, &employee, None, "kitchen", "").await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
    assert_eq!(body["error"]["code"], json!("invalid_payload"));
    // The message has to name the HEADER, not a body field. The runtime rejects an empty device id
    // too, with the same status and the same code, so without this assertion the door's own guard
    // could be deleted and every test here would still pass — while the client got told that
    // "device_id is required" about something it never puts in the body.
    let message = body["error"]["message"].as_str().unwrap_or_default();
    assert!(
        message.contains("X-Device-Id"),
        "the caller must learn WHICH header is missing, got: {message}"
    );

    let (status, _) = register(&router, &employee, Some("   "), "kitchen", "").await;
    assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY, "blanks are no id");

    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/hosts/heartbeat",
            Some(&employee),
            None,
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

/// **The hub tells the host how often to report.** Otherwise the client hard-codes an interval that
/// can drift away from the hub's window, and the day they disagree every till looks offline.
#[tokio::test]
async fn the_hub_tells_the_host_how_often_to_report() {
    let (router, _admin, employee) = fixture().await;
    let expected = json!(erplora_runtime::print_hosts::HEARTBEAT_SECONDS);

    let (_, body) = register(&router, &employee, Some("till-1"), "kitchen", "").await;
    assert_eq!(body["heartbeatSeconds"], expected);

    let resp = router
        .oneshot(request(
            "POST",
            "/api/print/hosts/heartbeat",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["refreshed"], json!(1));
    assert_eq!(
        body["heartbeatSeconds"], expected,
        "the interval travels on every beat, not only at registration"
    );
}

/// A beat from a device that hosts nothing answers `0` instead of failing: that is the signal the
/// app needs to register again, and a 404 would look like a broken hub instead.
#[tokio::test]
async fn a_beat_from_a_device_that_hosts_nothing_answers_zero() {
    let (router, _admin, employee) = fixture().await;

    let resp = router
        .oneshot(request(
            "POST",
            "/api/print/hosts/heartbeat",
            Some(&employee),
            Some("phone-9"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["refreshed"], json!(0));
}

/// A device retires itself from one role and keeps the others: "this till no longer prints the
/// kitchen's" is not "this till prints nothing".
#[tokio::test]
async fn a_device_retires_itself_from_one_role() {
    let (router, _admin, employee) = fixture().await;
    register(&router, &employee, Some("till-1"), "kitchen", "Counter").await;
    register(&router, &employee, Some("till-1"), "receipt", "Counter").await;

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?role=kitchen",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["removed"], json!(1));

    let body = registry(&router, &employee).await;
    assert_eq!(body["hosts"].as_array().unwrap().len(), 1);
    assert_eq!(body["hosts"][0]["role"], json!("receipt"));
}

/// With no `role`, the device retires from everything: "this device is no longer a print host".
#[tokio::test]
async fn a_device_retires_itself_from_every_role() {
    let (router, _admin, employee) = fixture().await;
    register(&router, &employee, Some("till-1"), "kitchen", "Counter").await;
    register(&router, &employee, Some("till-1"), "receipt", "Counter").await;

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(body_json(resp).await["removed"], json!(2));
    assert!(registry(&router, &employee).await["hosts"]
        .as_array()
        .unwrap()
        .is_empty());
}

/// **Retiring somebody else's device is administration.** It is the door for the till that was
/// replaced or stolen — the only gesture here that reaches a device the caller is not holding —
/// so it takes the same session as settings and the role catalogue. An ordinary cashier cannot
/// silently stop another till from printing.
#[tokio::test]
async fn retiring_another_device_takes_an_admin_session() {
    let (router, admin, employee) = fixture().await;
    register(&router, &employee, Some("till-2"), "kitchen", "Old till").await;

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?deviceId=till-2",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    // hub#1705: a valid session without the role is `403 forbidden` — signing in again would not help.
    assert_eq!(
        resp.status(),
        StatusCode::FORBIDDEN,
        "a cashier cannot retire a till they are not holding"
    );
    assert_eq!(
        registry(&router, &employee).await["hosts"]
            .as_array()
            .unwrap()
            .len(),
        1,
        "and nothing was removed"
    );

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?deviceId=till-2",
            Some(&admin),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["removed"], json!(1));
    assert!(registry(&router, &admin).await["hosts"]
        .as_array()
        .unwrap()
        .is_empty());
}

/// Naming your OWN device explicitly is still your own device, so it does not need an admin: the
/// gate is "somebody else's", not "the parameter was present".
#[tokio::test]
async fn naming_your_own_device_explicitly_needs_no_admin() {
    let (router, _admin, employee) = fixture().await;
    register(&router, &employee, Some("till-1"), "kitchen", "Counter").await;

    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?deviceId=till-1",
            Some(&employee),
            Some("till-1"),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    assert_eq!(body_json(resp).await["removed"], json!(1));
}

/// **A device that went quiet reports `live: false` over the wire.** The whole point of deriving
/// liveness is that the owner's screen can tell "nobody is printing this" from "somebody is"; a
/// door that always answered `true` would look right on the happy path and hide the only state
/// worth showing.
#[tokio::test]
async fn a_host_that_went_quiet_is_reported_as_not_live() {
    let (router, _admin, employee, db) = fixture_with_db().await;
    register(&router, &employee, Some("till-1"), "kitchen", "Counter").await;
    assert_eq!(
        registry(&router, &employee).await["hosts"][0]["live"],
        json!(true)
    );

    // The device was switched off: it cannot tell anybody, so silence is the only signal.
    use erplora_db::{DatabaseAdapter, Params};
    let mut p = Params::new();
    p.insert(
        "at".into(),
        json!((chrono::Utc::now()
            - chrono::Duration::seconds(erplora_runtime::print_hosts::HOST_TTL_SECONDS + 5))
        .to_rfc3339()),
    );
    db.execute(
        "UPDATE _print_host SET last_seen_at = :at WHERE device_id = 'till-1'",
        &p,
    )
    .await
    .unwrap();

    let body = registry(&router, &employee).await;
    assert_eq!(
        body["hosts"][0]["live"],
        json!(false),
        "the registry must report the till that stopped answering"
    );
    assert_eq!(
        coverage_of(&body, "kitchen").unwrap()["liveHosts"],
        json!(0)
    );
}

/// **`X-Device-Id` is trimmed at the door.** A header the client padded with a space has to name
/// the same device as the unpadded one — otherwise `" till-1 "` registers a second, phantom host,
/// and worse, retiring your own device by name stops matching the header and demands an admin.
#[tokio::test]
async fn a_padded_device_header_names_the_same_device() {
    let (router, _admin, employee) = fixture().await;

    register(&router, &employee, Some(" till-1 "), "kitchen", "Counter").await;
    let body = registry(&router, &employee).await;
    assert_eq!(
        body["hosts"].as_array().unwrap().len(),
        1,
        "one device, not one per spelling"
    );
    assert_eq!(body["hosts"][0]["deviceId"], json!("till-1"));

    // Naming your own device explicitly must still be "your own", padding and all: with an
    // untrimmed header this comparison fails and a cashier is refused their own till.
    let resp = router
        .clone()
        .oneshot(request(
            "DELETE",
            "/api/print/hosts?deviceId=till-1",
            Some(&employee),
            Some(" till-1 "),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "a padded header is the same device, so no admin is needed"
    );
    assert_eq!(body_json(resp).await["removed"], json!(1));
}

/// **Somebody charged and nothing is going to print.** The sale is not blocked and the ticket is
/// not lost — it waits — but the registry now says so out loud, per role, which is what lets a
/// screen warn the owner instead of leaving them to find out at the pass.
#[tokio::test]
async fn the_registry_reports_work_waiting_with_nobody_to_print_it() {
    let (router, _admin, employee) = fixture().await;

    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/print/jobs",
            Some(&employee),
            Some("phone-1"),
            Some(json!({
                "jobId": "j1",
                "role": "kitchen",
                "documentType": "kitchen_order",
                "document": { "receipt_id": "K-1" },
            })),
        ))
        .await
        .unwrap();
    assert_eq!(
        resp.status(),
        StatusCode::OK,
        "charging never depends on a printer being attended"
    );

    let body = registry(&router, &employee).await;
    let kitchen = coverage_of(&body, "kitchen").expect("the role is reported even with no host");
    assert_eq!(kitchen["waiting"], json!(1));
    assert_eq!(kitchen["liveHosts"], json!(0));
}

// ── The device that prints presents itself with a NAME (hub#1560) ────────────────────────────
//
// hub#1527 made the Printers screen say *which* device prints each station instead of *how many*.
// It landed on a registry where nobody had ever written a name: the shell registers with the role
// and nothing else, so every station was about to read `dev_` + 32 hex — an id the owner cannot
// match to either of the two tablets on the counter.
//
// The name is **not** minted here. This hub already knows what the business calls each device
// (`hub_trusted_device.name`, hub#494): born from the platform it announced on its first online
// login, renameable by an administrator in Settings → Devices. Reusing it is what keeps one device
// from having two names — the one in the device list and a second, frozen one on the printer card.

/// `POST /api/print/hosts` **exactly as the shell does it** (`print-host.ts`): the role, no name.
/// `user_agent` is what the browser announces, which is the only thing a hub that never saw this
/// device before has to go on.
async fn register_bare(
    router: &axum::Router,
    session: &str,
    device_id: &str,
    role: &str,
    user_agent: Option<&str>,
) -> (StatusCode, Value) {
    let mut builder = Request::builder()
        .method("POST")
        .uri("/api/print/hosts")
        .header("x-hub-session", session)
        .header("x-device-id", device_id)
        .header("content-type", "application/json");
    if let Some(agent) = user_agent {
        builder = builder.header("user-agent", agent);
    }
    let resp = router
        .clone()
        .oneshot(
            builder
                .body(Body::from(json!({ "role": role }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    (resp.status(), body_json(resp).await)
}

/// A second handle on the fixture's schema, to write the facts a login would have written.
fn behind(probe: erplora_db::PgAdapter) -> Runtime {
    Runtime::with_hub_id(Box::new(probe), HUB_ID)
}

#[tokio::test]
async fn hub1560_a_host_that_sends_no_name_takes_the_name_the_business_gave_the_device() {
    let (router, admin, _employee, probe) = fixture_with_db().await;
    let rt = behind(probe);
    // The device signed in online once (that is what writes the trust row) and the owner then
    // named it in Settings → Devices. That name is the whole point of hub#494.
    rt.trust_device_with_default_name("till-1", "Marta Ruiz", "Chrome · Android")
        .await
        .unwrap();
    rt.rename_device("till-1", "Caja 1").await.unwrap();

    let (status, body) = register_bare(&router, &admin, "till-1", "receipt", None).await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        body["host"]["label"], "Caja 1",
        "the printer card must read the name the owner chose, not the opaque device id"
    );
}

#[tokio::test]
async fn hub1560_a_device_the_business_never_named_is_presented_by_what_it_announced() {
    let (router, admin, _employee, _probe) = fixture_with_db().await;

    // No trust row and no name: the hub has never seen this device anywhere but here. The honest
    // default is the platform it announces — the same one `hub_trusted_device` is born with, so
    // both screens say the same words about the same tablet.
    let (status, body) = register_bare(
        &router,
        &admin,
        "tablet-9",
        "receipt",
        Some("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"),
    )
    .await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["host"]["label"], "Chrome · Android");
}

#[tokio::test]
async fn hub1560_a_client_that_does_send_a_name_still_wins() {
    let (router, admin, _employee, probe) = fixture_with_db().await;
    let rt = behind(probe);
    rt.trust_device_with_default_name("till-1", "Marta Ruiz", "Chrome · Android")
        .await
        .unwrap();
    rt.rename_device("till-1", "Caja 1").await.unwrap();

    // The default fills a gap; it does not take the door's own field away from a client that has
    // something better to say (a host registered by a fixed installation, say).
    let (status, body) = register(&router, &admin, Some("till-1"), "receipt", "Barra").await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["host"]["label"], "Barra");
}

#[tokio::test]
async fn hub1560_a_device_with_no_name_and_an_unreadable_agent_keeps_the_name_it_had() {
    let (router, admin, _employee, _probe) = fixture_with_db().await;
    register(&router, &admin, Some("till-1"), "receipt", "Counter till").await;

    // Nothing to derive a name from — and "nothing" must never blank the name already on the
    // owner's screen. This is `print_hosts::register`'s empty-label contract, which the default
    // must not step around.
    let (status, body) = register_bare(&router, &admin, "till-1", "receipt", None).await;

    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["host"]["label"], "Counter till");
}

// ── From the alta to the owner's screen (hub#1560, review) ───────────────────────────────────
//
// The tests above prove the door answers with a name. The owner never reads that answer: they read
// `liveHostLabels` of `hub.print.coverage`, which is what Settings → Printers and the `printing`
// module render (hub#1527 / printing#33). These walk the same path the shell walks — a bare
// `POST /api/print/hosts` from a device called `dev_<32 hex>` — and then run the query the screen
// runs, asserting on the words the owner reads and on the absence of the opaque id.

/// The `hub.print.coverage` row of `role`, read through `/api/query` as a module does.
async fn coverage_row(router: &axum::Router, session: &str, role: &str) -> Value {
    let resp = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/query",
            Some(session),
            None,
            Some(json!({ "name": "hub.print.coverage", "params": {} })),
        ))
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let body = body_json(resp).await;
    assert_eq!(body["ok"], json!(true), "{body}");
    body["data"]
        .as_array()
        .unwrap_or_else(|| panic!("coverage is an array: {body}"))
        .iter()
        .find(|c| c["role"] == json!(role))
        .cloned()
        .unwrap_or_else(|| panic!("no coverage row for {role}: {body}"))
}

/// `liveHostLabels` of a coverage row, as the screen receives them.
fn labels_of(row: &Value) -> Vec<String> {
    row["liveHostLabels"]
        .as_array()
        .unwrap_or_else(|| panic!("liveHostLabels is an array: {row}"))
        .iter()
        .map(|l| l.as_str().unwrap_or_default().to_string())
        .collect()
}

/// Device ids exactly as the shell mints them (`apps/web/src/lib/device.ts`): `dev_` + 32 hex.
const TILL: &str = "dev_3f9c2b1c4d5e6f708192a3b4c5d6e7f8";
const TABLET: &str = "dev_0a1b2c3d4e5f60718293a4b5c6d7e8f9";
const ANDROID_UA: &str =
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36";
const IPAD_UA: &str =
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Safari/604.1";

#[tokio::test]
async fn hub1560_the_owner_reads_a_name_on_the_coverage_and_never_the_device_id() {
    let (router, admin, _employee, probe) = fixture_with_db().await;
    let rt = behind(probe);
    // The till signed in online once (that writes the trust row, born "Chrome · Android") and the
    // owner then named it in Settings → Devices.
    rt.trust_device_with_default_name(TILL, "Marta Ruiz", "Chrome · Android")
        .await
        .unwrap();
    rt.rename_device(TILL, "Caja 1").await.unwrap();
    // The tablet signed in as Luis and nobody named it. Its name is the platform it announced —
    // NOT the person who signed in on it: that is `label`, a different column with a different job,
    // and a name that changes with every login would not be a name.
    rt.trust_device_with_default_name(TABLET, "Luis Pérez", "Safari · iPad")
        .await
        .unwrap();

    // Both register exactly as the shell does: the role and nothing else.
    let (status, _) = register_bare(&router, &admin, TILL, "receipt", Some(ANDROID_UA)).await;
    assert_eq!(status, StatusCode::OK);
    let (status, _) = register_bare(&router, &admin, TABLET, "receipt", Some(IPAD_UA)).await;
    assert_eq!(status, StatusCode::OK);

    let receipt = coverage_row(&router, &admin, "receipt").await;
    let labels = labels_of(&receipt);
    assert_eq!(labels, ["Caja 1", "Safari · iPad"], "{receipt}");
    assert_eq!(receipt["liveHosts"], json!(2));
    assert!(
        labels.iter().all(|l| !l.starts_with("dev_")),
        "the owner must never read the opaque device id: {labels:?}"
    );
    assert!(
        !labels
            .iter()
            .any(|l| l.contains("Luis") || l.contains("Marta")),
        "who signed in on a device is not the device's name: {labels:?}"
    );
}

#[tokio::test]
async fn hub1560_a_name_the_owner_took_back_falls_to_the_platform_or_the_id_never_to_a_blank() {
    let (router, admin, _employee, probe) = fixture_with_db().await;
    let rt = behind(probe);
    rt.trust_device_with_default_name(TILL, "Marta Ruiz", "Chrome · Android")
        .await
        .unwrap();
    rt.rename_device(TILL, "Caja 1").await.unwrap();
    // "I have no name for it" is a real gesture in Settings → Devices.
    rt.rename_device(TILL, "   ").await.unwrap();

    // The till boots: no name from the business, so the platform it announces.
    register_bare(&router, &admin, TILL, "receipt", Some(ANDROID_UA)).await;
    // A device nobody named, that announces nothing and that this hub never saw: the id, spelled
    // out — never an empty string, which the screen would render as a dangling comma.
    register_bare(&router, &admin, TABLET, "receipt", None).await;

    let labels = labels_of(&coverage_row(&router, &admin, "receipt").await);
    assert_eq!(labels, ["Chrome · Android", TABLET]);
    assert!(
        labels.iter().all(|l| !l.trim().is_empty()),
        "no entry of the list is ever blank: {labels:?}"
    );
}

/// The rows every live hub holds today (shell at `origin/develop` registers `{ role }` and nothing
/// else) are not migrated or backfilled: the shell re-registers on **every boot**
/// (`bootPrintHost` → `registration.tick()`), still bare, and that boot is what names the row.
#[tokio::test]
async fn hub1560_a_host_the_fleet_registered_nameless_is_named_on_its_next_boot() {
    let (router, admin, _employee, probe) = fixture_with_db().await;
    let rt = behind(probe);
    rt.trust_device_with_default_name(TILL, "Marta Ruiz", "Chrome · Android")
        .await
        .unwrap();
    rt.rename_device(TILL, "Caja 1").await.unwrap();
    // Named in the device list, nameless on the printer card: what the fleet has today.
    rt.register_print_host(TILL, "receipt", "", "u1")
        .await
        .unwrap();
    rt.register_print_host(TABLET, "receipt", "", "u1")
        .await
        .unwrap();
    let before = labels_of(&coverage_row(&router, &admin, "receipt").await);
    assert_eq!(
        before,
        [TABLET, TILL],
        "the rows the fleet has today read as ids"
    );

    register_bare(&router, &admin, TILL, "receipt", Some(ANDROID_UA)).await;
    register_bare(&router, &admin, TABLET, "receipt", Some(IPAD_UA)).await;

    let after = labels_of(&coverage_row(&router, &admin, "receipt").await);
    assert_eq!(after, ["Caja 1", "Safari · iPad"]);
}
