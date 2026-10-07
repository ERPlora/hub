//! `POST /api/modules/:id/uninstall` with other modules depending on the one leaving (hub#1101).
//!
//! The runtime contract lives in `erplora-runtime/tests/uninstall_dependents_gate.rs`. This file
//! exists for the door itself, because the door is where the defect was FOUND: `POST
//! /api/modules/taxes/uninstall` answered `200 {"ok":true}` with `sales`, `inventory`, `invoice`
//! and `services` all declaring `taxes` in `depends_on`, and from that moment the till could not
//! charge. The screen already warned before asking (hub#773); the API asked nobody.
//!
//! So what is pinned here is the wire contract the screen and any other caller program against:
//! **409** with the stable code `has_dependents` and the dependents as a **FIELD** — a list nobody
//! has to parse out of a sentence — plus the explicit `{"force": true}` that a confirmed owner
//! sends — which removes the dependents along with it and names them in `also_uninstalled`
//! (hub#2545).
use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

/// Writes a minimal installable module to `root/<id>` and returns its path.
fn write_module(root: &std::path::Path, id: &str, depends_on: &[&str]) -> std::path::PathBuf {
    let dir = root.join(id);
    std::fs::create_dir_all(dir.join("migrations/postgres")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        serde_json::to_string(&json!({
            "id": id,
            "name": id,
            "version": "1.0.0",
            "depends_on": depends_on,
            "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
        }))
        .unwrap(),
    )
    .unwrap();
    std::fs::write(
        dir.join("migrations/postgres/001_init.sql"),
        format!("CREATE TABLE IF NOT EXISTS {id}_row (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);"),
    )
    .unwrap();
    dir
}

/// A hub with `dbase` ← `dmid` ← `dtop` installed, plus `dloose` depending on nobody.
async fn fixture(tag: &str) -> (axum::Router, String) {
    let temp =
        std::env::temp_dir().join(format!("erplora-uninst-1101-{}-{tag}", std::process::id()));
    let _ = std::fs::remove_dir_all(&temp);
    std::fs::create_dir_all(&temp).unwrap();

    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-1101");
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let session = rt.create_session(&admin_id, 3600, None).await.unwrap();

    for (id, deps) in [
        ("dbase", &[][..]),
        ("dmid", &["dbase"][..]),
        ("dtop", &["dmid"][..]),
        ("dloose", &[][..]),
    ] {
        let dir = write_module(&temp, id, deps);
        rt.install_from_dir(&dir)
            .await
            .unwrap_or_else(|e| panic!("seed {id}: {e}"));
    }

    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-1101".into(),
        cloud_base_url: "http://127.0.0.1:1".into(),
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        // Present so `require_machine_registration` lets the business surface through.
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp.clone(),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    (app(AppState::with_config(rt, cfg)), session)
}

/// The call the web app makes today: no body at all, not even a content-type.
fn uninstall(session: &str, id: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(format!("/api/modules/{id}/uninstall"))
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

fn uninstall_with_body(session: &str, id: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(format!("/api/modules/{id}/uninstall"))
        .header("x-hub-session", session)
        .header("content-type", "application/json")
        .body(Body::from(body.to_string()))
        .unwrap()
}

async fn json_body(response: axum::response::Response) -> Value {
    let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

/// The ids `GET /api/modules` reports as installed, sorted.
async fn installed(router: &axum::Router, session: &str) -> Vec<String> {
    let res = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/modules")
                .header("x-hub-session", session)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let body = json_body(res).await;
    let mut ids: Vec<String> = body["data"]
        .as_array()
        .expect("the module list travels in `data`")
        .iter()
        .map(|m| m["id"].as_str().unwrap().to_string())
        .collect();
    ids.sort();
    ids
}

#[tokio::test]
async fn uninstalling_a_module_others_depend_on_is_a_409_that_names_them() {
    let (router, session) = fixture("refuses").await;

    let res = router
        .clone()
        .oneshot(uninstall(&session, "dbase"))
        .await
        .unwrap();

    assert_eq!(
        res.status(),
        StatusCode::CONFLICT,
        "the `ok:true` that left the till unable to charge"
    );
    let body = json_body(res).await;
    assert_eq!(body["ok"], json!(false));
    assert_eq!(body["error"]["code"], json!("has_dependents"));
    // A FIELD, not a sentence to parse: it is what the dialog lists.
    let mut dependents: Vec<String> = body["error"]["dependents"]
        .as_array()
        .expect("the dependents travel as an array")
        .iter()
        .map(|d| d.as_str().unwrap().to_string())
        .collect();
    dependents.sort();
    assert_eq!(dependents, vec!["dmid", "dtop"]);

    assert_eq!(
        installed(&router, &session).await,
        vec!["dbase", "dloose", "dmid", "dtop"],
        "a refused uninstall must change nothing"
    );
}

#[tokio::test]
async fn an_explicit_force_removes_it_anyway() {
    let (router, session) = fixture("force").await;

    let res = router
        .clone()
        .oneshot(uninstall_with_body(
            &session,
            "dbase",
            json!({ "force": true }),
        ))
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::OK);
    let body = json_body(res).await;
    assert_eq!(body["ok"], json!(true));
    // hub#2545: the dependents the dialog listed go with it, and the answer names them. Leaving
    // them installed kept them «Active» on a dependency that no longer existed, and their
    // re-download at the next boot brought `dbase` back on its own.
    let mut also: Vec<String> = body["also_uninstalled"]
        .as_array()
        .expect("the dependents that went with it travel as an array")
        .iter()
        .map(|d| d.as_str().unwrap().to_string())
        .collect();
    also.sort();
    assert_eq!(also, vec!["dmid", "dtop"]);
    assert_eq!(installed(&router, &session).await, vec!["dloose"]);
}

#[tokio::test]
async fn force_false_is_the_same_as_not_sending_it() {
    let (router, session) = fixture("force-false").await;

    let res = router
        .clone()
        .oneshot(uninstall_with_body(
            &session,
            "dbase",
            json!({ "force": false }),
        ))
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::CONFLICT);
    assert_eq!(
        json_body(res).await["error"]["code"],
        json!("has_dependents")
    );
}

#[tokio::test]
async fn a_module_nobody_depends_on_still_uninstalls_with_no_body() {
    let (router, session) = fixture("free").await;

    let res = router
        .clone()
        .oneshot(uninstall(&session, "dloose"))
        .await
        .unwrap();

    assert_eq!(
        res.status(),
        StatusCode::OK,
        "the gate must not tax the normal case, and the caller sends no body"
    );
    assert_eq!(
        installed(&router, &session).await,
        vec!["dbase", "dmid", "dtop"]
    );
}

#[tokio::test]
async fn force_does_not_turn_an_unknown_module_into_a_success() {
    let (router, session) = fixture("unknown").await;

    let res = router
        .clone()
        .oneshot(uninstall_with_body(
            &session,
            "nope",
            json!({ "force": true }),
        ))
        .await
        .unwrap();

    assert_ne!(res.status(), StatusCode::OK);
    assert_eq!(json_body(res).await["ok"], json!(false));
}
