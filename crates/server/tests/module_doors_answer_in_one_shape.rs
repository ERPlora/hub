//! **Every door a MODULE can reach answers in ONE shape** — the runtime's envelope (hub#1688).
//!
//! Module code never fetches. It goes through `@erplora/module-sdk`, and that transport ends every
//! single call in `unwrap(env)`: it reads `{"ok": true, "data": …}` or
//! `{"ok": false, "error": {"code", "message"}}` and nothing else. A body outside that shape does
//! not degrade — it reaches the module as `ErploraError('error', 'unknown error')`, with whatever
//! the answer actually said stripped off.
//!
//! hub#1682 shipped three doors that answered outside it: the WhatsApp templates proxy handed the
//! SaaS's plain body straight back, so a template **Meta had accepted** was reported to the
//! business as «error», and a refusal Meta explained (`invalid_name`) arrived with nothing to
//! explain it with. Its own test was green because it simulated an envelope the runtime never
//! produced.
//!
//! 🔴 **This is a PATTERN, not a point.** The runtime's proxy helpers hand the Cloud's body back
//! untouched by default, which is right for the doors the SHELL fetches itself and wrong for every
//! door a module reaches — so the next cloud proxy added to the module surface repeats it. Hence
//! this guard: it does not name the WhatsApp routes, it walks **every** module-reachable route in
//! `contracts/kernel/routes.snapshot` (`auth:admin+capability`, the class the module gate derives)
//! and refuses any answer the SDK could not read. A new door is covered the day it is added,
//! because the snapshot it is read from is regenerated from the router by
//! `kernel_contract_routes` — a route missing from it fails there first.
use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

#[path = "support/kernel_snapshot.rs"]
mod kernel_snapshot;

/// The class the snapshot derives for «an admin session AND the calling module's capability» —
/// which is exactly «a module may call this».
const MODULE_REACHABLE: &str = "auth:admin+capability";

/// Every (method, path) a module can reach, straight from the committed kernel contract.
fn module_reachable_routes() -> Vec<(String, String)> {
    let snapshot = std::fs::read_to_string(kernel_snapshot::snapshot_path("routes.snapshot"))
        .expect("contracts/kernel/routes.snapshot is part of the kernel contract and is committed");
    let routes: Vec<(String, String)> = snapshot
        .lines()
        .filter(|line| !line.starts_with('#') && line.contains(MODULE_REACHABLE))
        .filter_map(|line| {
            let mut parts = line.split_whitespace();
            Some((parts.next()?.to_string(), parts.next()?.to_string()))
        })
        .collect();
    assert!(
        routes.len() >= 30,
        "the module surface cannot have shrunk to {} routes — the snapshot is not being read",
        routes.len()
    );
    routes
}

/// A path with its `:params` filled in. Nothing must EXIST: a `404` is an answer like any other,
/// and this test is about the shape of the answer, not about finding a row.
fn concrete(path: &str) -> String {
    path.split('/')
        .map(|segment| match segment {
            // Lowercase letters, digits and underscores: what a template name and a secret name
            // both accept, so neither is refused before its handler runs.
            ":name" => "not_here",
            s if s.starts_with(':') => "00000000-0000-0000-0000-000000000000",
            s => s,
        })
        .collect::<Vec<_>>()
        .join("/")
}

fn config(cloud_base_url: String) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-one-shape-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: "hub-shape".into(),
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

/// A SaaS that answers every path with a **plain** body — no envelope anywhere.
///
/// That is what the real one answers (`{"templates": […], "stale": false}`, `serialize(row)`,
/// `{"error": "<code>"}`), and it is the input that made hub#1682 fail: a proxy that hands this
/// back untouched is a door the SDK cannot read.
async fn fake_plain_saas() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let saas = Router::new().fallback(|| async {
        (
            StatusCode::OK,
            Json(json!({ "templates": [], "stale": false })),
        )
    });
    tokio::spawn(async move { axum::serve(listener, saas).await.unwrap() });
    format!("http://{address}")
}

#[tokio::test]
async fn every_door_a_module_can_reach_answers_in_the_envelope_the_sdk_reads() {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-shape");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt.create_user("Ana", "1111", "admin", None).await.unwrap();
    let session = rt.create_session(&admin, 3600, None).await.unwrap();
    let router = app(AppState::with_config(rt, config(fake_plain_saas().await)));

    let mut checked = 0;
    for (method, path) in module_reachable_routes() {
        let uri = concrete(&path);
        let carries_body = matches!(method.as_str(), "POST" | "PUT" | "PATCH");
        let mut request = Request::builder()
            .method(method.as_str())
            .uri(&uri)
            .header("x-hub-session", &session);
        if carries_body {
            request = request.header("content-type", "application/json");
        }
        let request = request
            .body(if carries_body {
                Body::from("{}")
            } else {
                Body::empty()
            })
            .unwrap();

        let response = router.clone().oneshot(request).await.unwrap();
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let door = format!("{method} {path}");

        // A body-less answer is fine and needs no envelope: a `204` says «done» by definition of
        // the status, and the SDK transport reads it as such before it ever looks for `ok`.
        if bytes.is_empty() {
            checked += 1;
            continue;
        }

        let body: Value = serde_json::from_slice(&bytes).unwrap_or_else(|e| {
            panic!("{door} answered {status} with a body that is not JSON ({e}): {bytes:?}")
        });
        assert!(
            body.get("ok").and_then(Value::as_bool).is_some(),
            "{door} answered {status} outside the envelope — a module reads `ok` or it reads \
             `unknown error`. Proxy it with `cloud_proxy::proxy_cloud_*_enveloped`, not with the \
             passthrough the shell's own doors use. Body: {body}"
        );
        if body["ok"] == Value::Bool(false) {
            let code = body
                .get("error")
                .and_then(|e| e.get("code"))
                .and_then(Value::as_str);
            assert!(
                code.is_some_and(|c| !c.is_empty()),
                "{door} refused with {status} and no `error.code` — the code is what a module \
                 branches on and what lets it say WHY. Body: {body}"
            );
        }
        checked += 1;
    }
    assert!(checked >= 30, "only {checked} doors were driven");
}
