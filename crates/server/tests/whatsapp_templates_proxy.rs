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
//! verbatim, the SaaS's answer reaching the MODULE — **status and `code` included**, because the
//! module is the one that turns `invalid_name` into a sentence (ADR-0055, saas#1902) — and a
//! template name that cannot climb out of its route.
//!
//! hub#1688 fixed the one that did not hold: the answer travelled as the SaaS's bare body, and the
//! module-sdk transport reads only the runtime's envelope, so every call — including the ones Meta
//! ACCEPTED — reached the module as `unknown error`. The block at the end of this file is that
//! contract; the pattern guard over every module-reachable proxy is
//! `tests/module_doors_answer_in_one_shape.rs`.
use axum::body::Body;
use axum::extract::Path;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::response::IntoResponse;
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
                match name.as_str() {
                    // This hub has no template by that name — the SaaS names the reason.
                    "gone" => (
                        StatusCode::NOT_FOUND,
                        Json(json!({ "error": "template_not_found" })),
                    )
                        .into_response(),
                    // DRF's OWN throttle: `detail` and no `error` key anywhere.
                    "throttled" => (
                        StatusCode::TOO_MANY_REQUESTS,
                        Json(json!({ "detail": "Request was throttled. Expected available in 1893 seconds." })),
                    )
                        .into_response(),
                    _ => StatusCode::NO_CONTENT.into_response(),
                }
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
    // The shape itself is pinned by `the_list_reaches_the_module_in_the_envelope_the_sdk_reads`;
    // what THIS test is about is the credential on the wire.
    assert_eq!(body["data"]["templates"][0]["name"], "table_ready");
    // The reason Meta rejected it travels as it came: the tab is what turns it into a sentence.
    assert_eq!(body["data"]["templates"][0]["rejected_reason"], "INVALID_FORMAT");
    assert_eq!(body["data"]["stale"], false);
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
    assert_eq!(body_json(response).await["data"]["status"], "PENDING");
    let s = seen.lock().unwrap();
    assert_eq!(s.path, "register");
    assert_eq!(
        s.body, written,
        "the SaaS must see exactly what the business wrote, nothing rewritten"
    );
    machine_credential_and_nothing_else(&s);
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
    // A `204` has to stay EMPTY on the way out, header included: the tab calls this door with
    // `fetch` and a `content-type: application/json` over zero bytes is what makes the browser's
    // `response.json()` throw on a delete that actually worked.
    assert_eq!(
        response.headers().get(axum::http::header::CONTENT_TYPE),
        None,
        "a 204 must not be announced as JSON"
    );
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

// ── The shape the MODULE receives (hub#1688) ───────────────────────────────────────────────────
//
// The three doors above are the only cloud proxy a module can reach (`@erplora/module-sdk`,
// `erplora.forModule(id).whatsappTemplates`), and every door a module reaches answers in the
// runtime's ENVELOPE: `{ok:true,data}` or `{ok:false,error:{code,message}}`. That is not a
// convention of one route — it is the only shape `HttpWsTransport.send` reads, so a body outside
// it reaches the module as `unknown error` with the code stripped off.
//
// Handing the SaaS's plain body back is what hub#1682 shipped, and it turned every one of these
// calls into an error: a template Meta ACCEPTED was reported as «error» to the business, and a
// refusal Meta explained (`invalid_name`) arrived with nothing to explain it with.

#[tokio::test]
async fn the_list_reaches_the_module_in_the_envelope_the_sdk_reads() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "env-list").await;

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
    assert_eq!(body["ok"], true, "a module reads `ok` or it reads nothing");
    // The SaaS's payload travels WHOLE inside `data`: the verdict Meta gave each template and the
    // `stale` flag are what the tab draws, and neither is reinterpreted on the way.
    assert_eq!(body["data"]["templates"][0]["name"], "table_ready");
    assert_eq!(body["data"]["templates"][0]["rejected_reason"], "INVALID_FORMAT");
    assert_eq!(body["data"]["stale"], false);
}

#[tokio::test]
async fn a_template_meta_accepted_comes_back_as_accepted_not_as_error() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen.clone()).await, "env-register").await;

    let response = router
        .oneshot(request(
            "POST",
            "/api/hub/whatsapp/templates",
            Some(&admin),
            Some(json!({ "name": "table_ready", "language": "es", "category": "UTILITY", "body": "x" })),
        ))
        .await
        .unwrap();

    // 201 = new to Meta, 200 = edited in place. The status is part of the answer and is not flattened.
    assert_eq!(response.status(), StatusCode::CREATED);
    let body = body_json(response).await;
    assert_eq!(body["ok"], true);
    assert_eq!(body["data"]["status"], "PENDING");
}

#[tokio::test]
async fn a_saas_refusal_reaches_the_module_with_its_code_so_it_can_say_why() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen).await, "env-refusal").await;

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
    let body = body_json(response).await;
    assert_eq!(body["ok"], false);
    assert_eq!(
        body["error"]["code"], "invalid_name",
        "the code is the whole point: it is what lets the tab tell the owner WHAT to change"
    );
    // The SaaS's `detail` is the fallback sentence for a code the module never translated
    // (ADR-0055): a code with no words at all reads as «error» just the same.
    assert_eq!(
        body["error"]["message"],
        "lowercase letters, digits and underscores only"
    );
}

#[tokio::test]
async fn a_delete_the_saas_refuses_keeps_its_code_too() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen).await, "env-delete-refusal").await;

    let response = router
        .oneshot(request(
            "DELETE",
            "/api/hub/whatsapp/templates/gone",
            Some(&admin),
            None,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false);
    assert_eq!(body["error"]["code"], "template_not_found");
}

#[tokio::test]
async fn a_refusal_the_saas_did_not_name_still_arrives_as_a_refusal_with_a_code() {
    let seen = Arc::new(Mutex::new(Seen::default()));
    let (router, admin, _) = fixture(fake_saas(seen).await, "env-throttled").await;

    // DRF's own throttle answers `{"detail": "Request was throttled…"}` — no `error` key at all.
    // It still has to reach the module as a refusal it can branch on, not as `unknown error`.
    let response = router
        .oneshot(request(
            "DELETE",
            "/api/hub/whatsapp/templates/throttled",
            Some(&admin),
            None,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false);
    assert_eq!(body["error"]["code"], "cloud_rejected");
    assert!(
        body["error"]["message"]
            .as_str()
            .unwrap_or_default()
            .contains("throttled"),
        "what the SaaS did say must survive: {body}"
    );
}

#[tokio::test]
async fn a_saas_that_does_not_answer_reaches_the_module_as_a_code_not_as_a_url() {
    let (router, admin, _) = fixture("http://127.0.0.1:1/".into(), "env-down").await;

    let response = router
        .oneshot(request(
            "GET",
            "/api/hub/whatsapp/templates",
            Some(&admin),
            None,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false);
    assert_eq!(body["error"]["code"], "cloud_unreachable");
    // `error_redaction_door`: the `reqwest` message carries the control plane's internal URL and
    // must not travel to a module — the detail belongs in the hub's log.
    let message = body["error"]["message"].as_str().unwrap_or_default();
    assert!(
        !message.contains("127.0.0.1") && !message.contains("http://"),
        "the address the hub dialled must not reach the caller: {message}"
    );
}

#[tokio::test]
async fn a_success_the_hub_cannot_read_reaches_the_module_as_a_code_not_as_an_empty_list() {
    // An edge in front of the SaaS answering `200` with an HTML page instead of the SaaS's JSON:
    // `text/html` labelled or not, the bytes do not parse. Handed to the module as `ok: true`
    // with `data: null`, the tab would draw «no templates» over a business that has ten and be
    // told nothing went wrong — the envelope must say the hub could not READ the answer.
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let edge = Router::new().fallback(|| async {
        (
            StatusCode::OK,
            [(axum::http::header::CONTENT_TYPE, "text/html")],
            "<!DOCTYPE html><html><body>edge</body></html>",
        )
    });
    tokio::spawn(async move { axum::serve(listener, edge).await.unwrap() });
    let (router, admin, _) = fixture(format!("http://{address}"), "env-unreadable").await;

    let response = router
        .oneshot(request(
            "GET",
            "/api/hub/whatsapp/templates",
            Some(&admin),
            None,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
    let body = body_json(response).await;
    assert_eq!(body["ok"], false, "an answer the hub could not read is not a success: {body}");
    assert_eq!(body["error"]["code"], "cloud_unreadable");
}
