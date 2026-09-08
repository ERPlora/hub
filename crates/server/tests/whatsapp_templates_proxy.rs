//! The runtime's door for the business's WhatsApp TEMPLATES (hub#1610) — the hub half of saas#1899.
//!
//! The owner writes a template in the WhatsApp module's «Plantillas» tab. For anything to leave
//! the business outside the 24 h since the customer last wrote, that template has to live in the
//! business's **Meta** account, and who talks to Meta is the SaaS. The module cannot call the SaaS
//! itself: the credential that opens that door is the hub's **machine token**, a secret of the
//! runtime that never reaches the browser (ADR-0003). So the runtime proxies it — three doors,
//! same gate and same shape as the four `whatsapp_connect` already has.
//!
//! What is asserted: the gate (no session → 401, an employee → 403), the credential on the wire
//! (`X-Hub-Token`, never the browser's bearer nor the local session), the body reaching the SaaS
//! verbatim, the SaaS's answer coming back untouched — **status and `code` included**, because the
//! module is the one that turns `invalid_name` into a sentence (ADR-0055, saas#1902) — and a
//! template name that cannot climb out of its route.
use axum::body::Body;
use axum::extract::Path;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::routing::{delete, get};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use tower::ServiceExt;

fn config(hub_id: &str, cloud_base_url: String, tag: &str) -> HubConfig {
    let temp =
        std::env::temp_dir().join(format!("erplora-wa-templates-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: hub_id.into(),
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

/// A router with one admin session and one employee session, pointed at `cloud_base_url`.
async fn fixture(cloud_base_url: String, tag: &str) -> (Router, String, String) {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-wa");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let admin_session = rt.create_session(&admin, 3600, None).await.unwrap();
    let employee = rt
        .create_user("Luis", "2222", "employee", None)
        .await
        .unwrap();
    let employee_session = rt.create_session(&employee, 3600, None).await.unwrap();
    (
        app(AppState::with_config(
            rt,
            config("hub-wa", cloud_base_url, tag),
        )),
        admin_session,
        employee_session,
    )
}

fn request(method: &str, uri: &str, session: Option<&str>, body: Option<Value>) -> Request<Body> {
    let mut req = Request::builder().method(method).uri(uri);
    if body.is_some() {
        req = req.header("content-type", "application/json");
    }
    if let Some(s) = session {
        req = req.header("x-hub-session", s);
    }
    req.body(body.map_or(Body::empty(), |b| Body::from(b.to_string())))
        .unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// What the fake SaaS saw: headers and body of the last call to each door.
#[derive(Default)]
struct Seen {
    headers: Vec<(String, String)>,
    body: Value,
    path: String,
}

fn record(seen: &Arc<Mutex<Seen>>, path: &str, headers: &HeaderMap, body: Value) {
    let mut s = seen.lock().unwrap();
    s.path = path.to_string();
    s.body = body;
    s.headers = headers
        .iter()
        .map(|(k, v)| (k.as_str().to_string(), v.to_str().unwrap_or("").to_string()))
        .collect();
}

fn machine_credential_and_nothing_else(seen: &Seen) {
    let get = |k: &str| {
        seen.headers
            .iter()
            .find(|(h, _)| h == k)
            .map(|(_, v)| v.clone())
    };
    assert_eq!(
        get("x-hub-token").as_deref(),
        Some("machine-secret"),
        "{:?}",
        seen.headers
    );
    assert_eq!(get("x-hub-id").as_deref(), Some("hub-wa"));
    assert!(
        get("authorization").is_none(),
        "the browser's bearer must never reach the SaaS"
    );
    assert!(
        get("x-hub-session").is_none(),
        "the local session token must never leave the hub"
    );
}

async fn fake_saas(seen: Arc<Mutex<Seen>>) -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (s1, s2, s3) = (seen.clone(), seen.clone(), seen.clone());
    let saas = Router::new()
        .route(
            "/api/v1/hub/device/whatsapp/templates/",
            get(move |headers: HeaderMap| async move {
                record(&s1, "list", &headers, Value::Null);
                Json(json!({
                    "templates": [{
                        "name": "table_ready",
                        "language": "es",
                        "category": "UTILITY",
                        "status": "REJECTED",
                        "rejected_reason": "INVALID_FORMAT",
                        "meta_id": "123"
                    }],
                    "stale": false
                }))
            })
            .post(move |headers: HeaderMap, Json(body): Json<Value>| async move {
                let name = body.get("name").and_then(Value::as_str).unwrap_or("");
                let refused = name == "Table Ready";
                record(&s2, "register", &headers, body);
                if refused {
                    // The SaaS answers with a CODE, never with prose (saas#1902).
                    return (
                        StatusCode::BAD_REQUEST,
                        Json(json!({ "error": "invalid_name", "detail": "lowercase letters, digits and underscores only" })),
                    );
                }
                (
                    StatusCode::CREATED,
                    Json(json!({ "name": "table_ready", "language": "es", "status": "PENDING" })),
                )
            }),
        )
        .route(
            "/api/v1/hub/device/whatsapp/templates/:name/",
            delete(move |Path(name): Path<String>, headers: HeaderMap| async move {
                record(&s3, &format!("delete:{name}"), &headers, Value::Null);
                StatusCode::NO_CONTENT
            }),
        );
    tokio::spawn(async move { axum::serve(listener, saas).await.unwrap() });
    format!("http://{address}")
}

#[tokio::test]
async fn the_templates_and_the_verdict_meta_gave_them_reach_the_tab() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "list").await;

    let response = router
        .oneshot(request(
            "GET",
            "/api/hub/whatsapp/templates",
            Some(&admin),
            None,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["templates"][0]["name"], "table_ready");
    // The reason Meta rejected it travels as it came: the tab is what turns it into a sentence.
    assert_eq!(body["templates"][0]["rejected_reason"], "INVALID_FORMAT");
    assert_eq!(body["stale"], false);
    let s = seen.lock().unwrap();
    assert_eq!(s.path, "list");
    machine_credential_and_nothing_else(&s);
}

#[tokio::test]
async fn saving_a_template_reaches_the_saas_verbatim_and_metas_answer_comes_back() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "register").await;
    let written = json!({
        "name": "table_ready",
        "language": "es",
        "category": "UTILITY",
        "header": "",
        "body": "Hola {{1}}, tu mesa esta lista.",
        "footer": "",
        "variables": ["nombre"]
    });

    let response = router
        .oneshot(request(
            "POST",
            "/api/hub/whatsapp/templates",
            Some(&admin),
            Some(written.clone()),
        ))
        .await
        .unwrap();

    // 201 = new to Meta, 200 = edited in place. The status is the answer, so it is not flattened.
    assert_eq!(response.status(), StatusCode::CREATED);
    assert_eq!(body_json(response).await["status"], "PENDING");
    let s = seen.lock().unwrap();
    assert_eq!(s.path, "register");
    assert_eq!(
        s.body, written,
        "the SaaS must see exactly what the business wrote, nothing rewritten"
    );
    machine_credential_and_nothing_else(&s);
}

#[tokio::test]
async fn a_refusal_keeps_its_status_and_its_code_so_the_module_can_name_it() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen).await, "refusal").await;

    let response = router
        .oneshot(request(
            "POST",
            "/api/hub/whatsapp/templates",
            Some(&admin),
            Some(json!({ "name": "Table Ready", "language": "es", "category": "UTILITY", "body": "x" })),
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        body_json(response).await["error"],
        "invalid_name",
        "the code is the contract; translating it here would leave the module nothing to act on"
    );
}

#[tokio::test]
async fn deleting_a_template_names_it_in_the_path_and_answers_with_no_content() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "delete").await;

    let response = router
        .oneshot(request(
            "DELETE",
            "/api/hub/whatsapp/templates/table_ready",
            Some(&admin),
            None,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NO_CONTENT);
    let s = seen.lock().unwrap();
    assert_eq!(s.path, "delete:table_ready");
    machine_credential_and_nothing_else(&s);
}

#[tokio::test]
async fn a_template_name_cannot_climb_out_of_its_route() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "hostile").await;

    for hostile in [
        "..%2Fnotify%2Fwhatsapp",
        "..%2F..%2Fdisconnect%2F123",
        "Table%20Ready",
    ] {
        let response = router
            .clone()
            .oneshot(request(
                "DELETE",
                &format!("/api/hub/whatsapp/templates/{hostile}"),
                Some(&admin),
                None,
            ))
            .await
            .unwrap();

        assert_eq!(
            response.status(),
            StatusCode::BAD_REQUEST,
            "{hostile:?} was let through"
        );
        assert_eq!(
            seen.lock().unwrap().path,
            "",
            "nothing may reach the SaaS with a name like {hostile:?}"
        );
    }
}

#[tokio::test]
async fn without_an_admin_session_the_template_doors_stay_closed() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, _admin, employee) = fixture(fake_saas(seen.clone()).await, "gate").await;

    let anonymous = router
        .clone()
        .oneshot(request("GET", "/api/hub/whatsapp/templates", None, None))
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let cashier = router
        .clone()
        .oneshot(request(
            "POST",
            "/api/hub/whatsapp/templates",
            Some(&employee),
            Some(json!({ "name": "table_ready" })),
        ))
        .await
        .unwrap();
    assert_eq!(
        cashier.status(),
        StatusCode::FORBIDDEN,
        "what the business promises Meta is the owner's, not the shift's"
    );

    let cashier_delete = router
        .oneshot(request(
            "DELETE",
            "/api/hub/whatsapp/templates/table_ready",
            Some(&employee),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(cashier_delete.status(), StatusCode::FORBIDDEN);

    assert_eq!(
        seen.lock().unwrap().path,
        "",
        "a refused call must not touch the SaaS"
    );
}

#[tokio::test]
async fn a_saas_that_does_not_answer_is_an_error_not_a_silent_ok() {
    let (router, admin, _) = fixture("http://127.0.0.1:1/".into(), "down").await;

    for (method, uri, body) in [
        ("GET", "/api/hub/whatsapp/templates", None),
        (
            "POST",
            "/api/hub/whatsapp/templates",
            Some(json!({ "name": "table_ready" })),
        ),
        ("DELETE", "/api/hub/whatsapp/templates/table_ready", None),
    ] {
        let response = router
            .clone()
            .oneshot(request(method, uri, Some(&admin), body))
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::BAD_GATEWAY,
            "{method} {uri} swallowed a SaaS that is not there"
        );
    }
}
