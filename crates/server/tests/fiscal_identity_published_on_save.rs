//! **Saving the business tax id publishes the fiscal identity to the control plane** — hub#1306.
//!
//! ERPlora files VERI*FACTU records ON BEHALF OF the business, and the grant of representation
//! (Annex I of the collaboration agreement) has to name that business. The control plane only
//! knows who it is if the hub told it: the identity lives in `hub_settings` and the SaaS never
//! reaches into a hub's database (ADR-0201, decision 5).
//!
//! Until this test existed, the only thing that ever told it was the *«use these details for my
//! ERPlora invoice too»* toggle — an OPTIONAL box about BILLING. A customer who filled in the tax
//! id and pressed Save reached `/dashboard/hubs/<id>/fiscal/representation-grant/` and found a wall
//! («set your tax details first»), went back to the hub, saved again… and hit the same wall. Dead
//! end, with nothing left to try.
//!
//! So the save itself publishes. What this file pins, and the unit tests of the payload cannot:
//!
//!  - the SAVE door (`PUT /api/settings`) is the one that publishes, with the machine credential
//!    the browser never sees (ADR-0003);
//!  - it publishes only when the update touches the identity, and never with an empty tax id —
//!    the control plane would reject it, and a settings save is not a fiscal event;
//!  - **a control plane that is down cannot cost the customer the save**: the settings are stored,
//!    the response is `200`, and the failure travels as a STABLE code so the screen can say it
//!    instead of swallowing it.
use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::State;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::routing::post;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig, DEV_HUB_ID};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

const HUB_ID: &str = "hub-1306";

/// Everything the fake control plane received: `(headers, body)` per publication.
type Published = Arc<Mutex<Vec<(HeaderMap, Value)>>>;

/// A control plane that does one thing: write down who published a fiscal identity, and answer
/// `answer` (so a rejecting SaaS can be tested with the same fake).
async fn spawn_cloud(answer: StatusCode) -> (String, Published) {
    async fn capture(
        State((published, answer)): State<(Published, StatusCode)>,
        headers: HeaderMap,
        Json(body): Json<Value>,
    ) -> StatusCode {
        published.lock().unwrap().push((headers, body));
        answer
    }

    let published: Published = Arc::new(Mutex::new(Vec::new()));
    let router = Router::new()
        .route("/api/v1/hub/device/fiscal-identity/", post(capture))
        .with_state((published.clone(), answer));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{address}"), published)
}

fn config(tag: &str, hub_id: &str, cloud_base_url: &str, token: Option<&str>) -> HubConfig {
    let temp =
        std::env::temp_dir().join(format!("erplora-publish-save-{}-{tag}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        cloud_base_url: cloud_base_url.into(),
        module_cache: temp.join("modules-cache"),
        // The dev hub is the only shape that gets past `require_machine_registration` with no
        // machine credential, and it is dev-mode by definition (`AppState::is_dev_hub`).
        auth_mode: if hub_id == DEV_HUB_ID {
            AuthMode::Dev
        } else {
            AuthMode::Session
        },
        jwt_public_key: None,
        cloud_api_token: token.map(str::to_owned),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// Router + an **admin** session (the role that configures the fiscal identity). `seeded_tax_id`
/// stamps the identity this hub already had before the save under test.
async fn fixture(
    tag: &str,
    cloud_base_url: &str,
    token: Option<&str>,
    seeded_tax_id: Option<&str>,
) -> (Router, String) {
    fixture_for(tag, HUB_ID, cloud_base_url, token, seeded_tax_id).await
}

async fn fixture_for(
    tag: &str,
    hub_id: &str,
    cloud_base_url: &str,
    token: Option<&str>,
    seeded_tax_id: Option<&str>,
) -> (Router, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();

    if let Some(tax_id) = seeded_tax_id {
        let mut updates = serde_json::Map::new();
        updates.insert("business_tax_id".into(), json!(tax_id));
        rt.set_settings(&updates, "hub_user:seed").await.unwrap();
    }

    (
        app(AppState::with_config(
            rt,
            config(tag, hub_id, cloud_base_url, token),
        )),
        admin,
    )
}

async fn put(router: &Router, session: &str, body: Value) -> axum::response::Response {
    router
        .clone()
        .oneshot(
            Request::builder()
                .method("PUT")
                .uri("/api/settings")
                .header("content-type", "application/json")
                .header("x-hub-session", session)
                .body(Body::from(body.to_string()))
                .unwrap(),
        )
        .await
        .unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// 🔴 **The case this exists for.** The owner fills in Settings → Business and presses Save; the
/// control plane learns who the taxpayer is, with the hub's machine credential.
#[tokio::test]
async fn saving_the_business_identity_publishes_it_to_the_control_plane() {
    let (cloud, published) = spawn_cloud(StatusCode::OK).await;
    let (router, admin) = fixture("happy", &cloud, Some("machine-secret"), None).await;

    let response = put(
        &router,
        &admin,
        json!({
            "business_tax_id": "B12345674",
            "business_legal_name": "Bar Manolo SL",
            "business_address": "Calle Mayor 1",
        }),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let published = published.lock().unwrap();
    assert_eq!(
        published.len(),
        1,
        "saving the tax id has to publish it exactly once"
    );
    let (headers, body) = &published[0];
    assert_eq!(headers["x-hub-id"], HUB_ID);
    assert_eq!(
        headers["x-hub-token"], "machine-secret",
        "the machine credential is the hub's, and it is what authorises this"
    );
    assert_eq!(body["tax_id"], json!("B12345674"));
    assert_eq!(body["billing_name"], json!("Bar Manolo SL"));
}

/// Saving the rest of the identity of a hub that ALREADY has a tax id publishes too: the legal
/// name is half of who the taxpayer is, and the grant is issued in that name.
#[tokio::test]
async fn correcting_the_legal_name_republishes_the_identity() {
    let (cloud, published) = spawn_cloud(StatusCode::OK).await;
    let (router, admin) = fixture("name", &cloud, Some("machine-secret"), Some("B12345674")).await;

    let response = put(
        &router,
        &admin,
        json!({ "business_legal_name": "Bar Manolo SLU" }),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    let published = published.lock().unwrap();
    assert_eq!(published.len(), 1, "the name is part of the identity");
    assert_eq!(published[0].1["billing_name"], json!("Bar Manolo SLU"));
    assert_eq!(
        published[0].1["tax_id"],
        json!("B12345674"),
        "the tax id already stored travels with it"
    );
}

/// 🔴 **No tax id, nothing to publish.** A hub still setting itself up saves its legal name before
/// it knows its tax id; the control plane would reject a nameless taxpayer, and a settings save is
/// not a fiscal event.
#[tokio::test]
async fn a_save_without_a_tax_id_publishes_nothing() {
    let (cloud, published) = spawn_cloud(StatusCode::OK).await;
    let (router, admin) = fixture("no-nif", &cloud, Some("machine-secret"), None).await;

    let response = put(
        &router,
        &admin,
        json!({ "business_legal_name": "Bar Manolo SL" }),
    )
    .await;

    assert_eq!(response.status(), StatusCode::OK);
    assert!(
        published.lock().unwrap().is_empty(),
        "an empty tax id is not an identity"
    );
}

/// 🔴 **The save that has nothing to do with the identity stays quiet.** Every screen in Settings
/// writes through this same door; if any save published, the control plane would be told the same
/// thing every time somebody flips the API-docs switch.
#[tokio::test]
async fn a_save_that_does_not_touch_the_identity_publishes_nothing() {
    let (cloud, published) = spawn_cloud(StatusCode::OK).await;
    let (router, admin) = fixture("other", &cloud, Some("machine-secret"), Some("B12345674")).await;

    let response = put(&router, &admin, json!({ "api_docs_enabled": true })).await;

    assert_eq!(response.status(), StatusCode::OK);
    assert!(published.lock().unwrap().is_empty());
}

/// 🔴 **A control plane that is down cannot cost the customer the save.** The settings are stored
/// and the answer is `200` — but the failure is NOT swallowed: it travels as a stable code, which
/// is what lets the screen say «saved, but ERPlora was not told» instead of pretending all is well
/// and sending the owner to a wall she cannot get past.
#[tokio::test]
async fn a_control_plane_that_rejects_does_not_cost_the_save() {
    let (cloud, published) = spawn_cloud(StatusCode::INTERNAL_SERVER_ERROR).await;
    let (router, admin) = fixture("down", &cloud, Some("machine-secret"), None).await;

    let response = put(&router, &admin, json!({ "business_tax_id": "B12345674" })).await;

    assert_eq!(
        response.status(),
        StatusCode::OK,
        "the save is the customer's"
    );
    let body = body_json(response).await;
    assert_eq!(
        body["business_tax_id"],
        json!("B12345674"),
        "stored, not rolled back: {body}"
    );
    assert_eq!(
        body["fiscal_identity_publish_error"],
        json!("cloud_rejected"),
        "the failure has to be visible, by CODE: {body}"
    );
    assert_eq!(
        published.lock().unwrap().len(),
        1,
        "it was tried, and the control plane is the one that said no"
    );
}

/// A hub with no machine credential — a local `pnpm dev`, the only shape that gets past
/// `require_machine_registration` without one — has nobody to tell. That is not a failure of the
/// save and is not reported as one: same contract as the boot announcement, where an un-enrolled
/// hub simply carries on.
#[tokio::test]
async fn a_hub_without_a_machine_credential_saves_without_publishing() {
    let (cloud, published) = spawn_cloud(StatusCode::OK).await;
    let (router, admin) = fixture_for("unenrolled", DEV_HUB_ID, &cloud, None, None).await;

    let response = put(&router, &admin, json!({ "business_tax_id": "B12345674" })).await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert!(
        body.get("fiscal_identity_publish_error").is_none(),
        "not being enrolled is not a failed publication: {body}"
    );
    assert!(published.lock().unwrap().is_empty());
}

/// 🔴 **An unreachable control plane is reported by CODE, never by reqwest's prose.** That prose
/// names the control plane's address (`error_redaction_door`), and a save is not the place to
/// print it: the answer is `200` with `cloud_unreachable`, and nothing in the body says where the
/// hub tried to go.
#[tokio::test]
async fn an_unreachable_control_plane_is_reported_by_code_without_its_address() {
    // Nothing listens on port 1: the connection is refused at once, no 5 s wait.
    let (router, admin) = fixture(
        "unreachable",
        "http://127.0.0.1:1",
        Some("machine-secret"),
        None,
    )
    .await;

    let response = put(&router, &admin, json!({ "business_tax_id": "B12345674" })).await;

    assert_eq!(
        response.status(),
        StatusCode::OK,
        "the save is the customer's"
    );
    let body = body_json(response).await;
    assert_eq!(
        body["fiscal_identity_publish_error"],
        json!("cloud_unreachable"),
        "an unreachable control plane has its own code: {body}"
    );
    let text = body.to_string();
    assert!(
        !text.contains("127.0.0.1") && !text.contains("error sending request"),
        "reqwest's prose (control-plane address included) leaked into the save: {text}"
    );
}

/// The explicit door (`POST /api/business/fiscal-identity`) answered with `e.to_string()` until
/// hub#1306 — reqwest's prose, control-plane address included. Same rule as the save: a stable
/// code, and nothing else.
#[tokio::test]
async fn the_explicit_door_reports_an_unreachable_control_plane_by_code_too() {
    let (router, admin) = fixture(
        "explicit-unreachable",
        "http://127.0.0.1:1",
        Some("machine-secret"),
        Some("B12345674"),
    )
    .await;

    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/business/fiscal-identity")
                .header("x-hub-session", &admin)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    // hub#1763: `424`, no `502` — el borde sustituye el cuerpo de un `5xx` por su propia página, y
    // con él se iría el `cloud_unreachable` que la línea de abajo exige que llegue al navegador.
    assert_eq!(response.status(), StatusCode::FAILED_DEPENDENCY);
    let body = body_json(response).await;
    assert_eq!(body["error"], json!("cloud_unreachable"), "{body}");
    let text = body.to_string();
    assert!(
        !text.contains("127.0.0.1") && !text.contains("error sending request"),
        "reqwest's prose (control-plane address included) leaked out of the door: {text}"
    );
}
