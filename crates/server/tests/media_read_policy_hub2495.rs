//! 🔴 hub#2495: reading a folder goes through the same rule as writing to it.
//!
//! Before this, `GET /api/media` and `GET /api/media/raw` only asked for a session of the hub, so a
//! cashier could open `_logs` (the hub's request log) and `modules/verifactu/…` (the XML records sent
//! to the tax agency, with the customers' tax id, name and address). The folder policy only guarded
//! writes. Now the hub's own folders (`_*`) and the apps' tree (`modules/…`) are read by an owner or
//! an administrator only, the refusal happens BEFORE erplora.com is asked for anything, and the
//! folder tree a non-admin receives does not even name them. A folder of the business (product
//! photos, WhatsApp headers, what a person uploaded) stays readable by every session: the till
//! paints those images for the cashier.

use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::{Request, State};
use axum::http::StatusCode;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::{json, Value};
use tower::ServiceExt;

/// Every request the mini-Cloud received: `(path, query)`.
type Captured = Arc<Mutex<Vec<(String, String)>>>;

/// The listing erplora.com answers for any folder: a tree with the hub's own folders, the apps'
/// tree and two folders of the business.
fn listing() -> Value {
    json!({
        "folders": [
            { "id": "", "label": "media", "children": [
                { "id": "_logs", "label": "_logs" },
                { "id": "_system", "label": "_system", "children": [
                    { "id": "_system/activity", "label": "activity" }
                ]},
                { "id": "modules", "label": "modules", "children": [
                    { "id": "modules/verifactu", "label": "verifactu", "children": [
                        { "id": "modules/verifactu/xml", "label": "xml" }
                    ]}
                ]},
                { "id": "hospitality", "label": "hospitality" },
                { "id": "whatsapp", "label": "whatsapp", "children": [
                    { "id": "whatsapp/headers", "label": "headers" }
                ]}
            ]}
        ],
        "files": [],
        "path": [],
        "usage": { "used_bytes": 0 }
    })
}

async fn capture(State(captured): State<Captured>, request: Request) -> Json<Value> {
    let path = request.uri().path().to_string();
    let query = request.uri().query().unwrap_or_default().to_string();
    captured.lock().unwrap().push((path, query));
    Json(listing())
}

async fn spawn_mock_cloud() -> (String, Captured) {
    let captured: Captured = Arc::new(Mutex::new(Vec::new()));
    let cloud = Router::new().fallback(capture).with_state(captured.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, cloud).await.unwrap() });
    (format!("http://{addr}"), captured)
}

struct Hub {
    router: Router,
    admin: String,
    manager: String,
    employee: String,
    captured: Captured,
}

async fn hub() -> Hub {
    let (cloud_base_url, captured) = spawn_mock_cloud().await;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-media-read");
    rt.ensure_system_tables().await.unwrap();
    let mut sessions = Vec::new();
    for (name, pin, role) in [
        ("Admin", "1111", "admin"),
        ("Manager", "2222", "manager"),
        ("Employee", "3333", "employee"),
    ] {
        let id = rt.create_user(name, pin, role, None).await.unwrap();
        sessions.push(rt.create_session(&id, 3600, None).await.unwrap());
    }
    let cfg = HubConfig {
        demo: false,
        hub_id: "hub-media-read".into(),
        cloud_base_url,
        module_cache: std::env::temp_dir().join("erplora-media-read-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-media-read-scratch"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let employee = sessions.pop().unwrap();
    let manager = sessions.pop().unwrap();
    let admin = sessions.pop().unwrap();
    Hub {
        router: app(AppState::with_config(rt, cfg)),
        admin,
        manager,
        employee,
        captured,
    }
}

fn pct(s: &str) -> String {
    s.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                (b as char).to_string()
            }
            _ => format!("%{b:02X}"),
        })
        .collect()
}

fn list(folder: &str, session: &str) -> Request {
    Request::builder()
        .uri(format!("/api/media?folder={}", pct(folder)))
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

fn raw(path: &str, session: &str) -> Request {
    Request::builder()
        .uri(format!("/api/media/raw?path={}", pct(path)))
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

/// The `<img src>` door: the session travels in the read-only cookie, not the header.
fn raw_with_cookie(path: &str, session: &str) -> Request {
    Request::builder()
        .uri(format!("/api/media/raw?path={}", pct(path)))
        .header("cookie", format!("erplora_media={session}"))
        .body(Body::empty())
        .unwrap()
}

async fn send(router: &Router, request: Request) -> (StatusCode, Value) {
    let response = router.clone().oneshot(request).await.unwrap();
    let status = response.status();
    let bytes = http_body_util::BodyExt::collect(response.into_body())
        .await
        .unwrap()
        .to_bytes();
    (status, serde_json::from_slice(&bytes).unwrap_or(Value::Null))
}

/// Every folder id in the tree, flattened.
fn folder_ids(tree: &Value, out: &mut Vec<String>) {
    for node in tree.as_array().into_iter().flatten() {
        if let Some(id) = node["id"].as_str() {
            out.push(id.to_string());
        }
        folder_ids(&node["children"], out);
    }
}

/// Paths of the hub's own folders and of the apps' tree, including the spellings that land on the
/// same object once erplora.com normalises them.
const RESTRICTED: &[&str] = &[
    "_logs",
    "_logs/hub.2026-10-06.log",
    "_system/activity/2026-10.json",
    "_import_tmp/upload-1/data.zip",
    "modules",
    "modules/verifactu",
    "modules/verifactu/xml/rec-1.xml",
    "/_logs/hub.log",
    "./_logs/hub.log",
    "hospitality/../_logs/hub.log",
    "hospitality/../modules/verifactu/xml/rec-1.xml",
    "hospitality\\..\\_logs\\hub.log",
];

#[tokio::test]
async fn a_cashier_cannot_list_the_hubs_logs_nor_the_records_sent_to_the_tax_agency() {
    let hub = hub().await;
    for session in [&hub.employee, &hub.manager] {
        for folder in RESTRICTED {
            let (status, body) = send(&hub.router, list(folder, session)).await;
            assert_eq!(status, StatusCode::FORBIDDEN, "listing {folder:?}");
            assert_eq!(body["error"]["code"], json!("forbidden"), "listing {folder:?}");
        }
    }
    assert!(
        hub.captured.lock().unwrap().is_empty(),
        "the refusal happens before erplora.com is asked: {:?}",
        hub.captured.lock().unwrap()
    );
}

#[tokio::test]
async fn a_cashier_cannot_download_a_log_nor_a_verifactu_xml() {
    let hub = hub().await;
    for session in [&hub.employee, &hub.manager] {
        for path in RESTRICTED {
            let (status, body) = send(&hub.router, raw(path, session)).await;
            assert_eq!(status, StatusCode::FORBIDDEN, "raw {path:?}");
            assert_eq!(body["error"]["code"], json!("forbidden"), "raw {path:?}");
            // The image door (cookie) is the same rule, not a way around it.
            let (status, _) = send(&hub.router, raw_with_cookie(path, session)).await;
            assert_eq!(status, StatusCode::FORBIDDEN, "raw by cookie {path:?}");
        }
    }
    assert!(
        hub.captured.lock().unwrap().is_empty(),
        "no signed link is asked for: {:?}",
        hub.captured.lock().unwrap()
    );
}

#[tokio::test]
async fn the_tree_a_cashier_receives_does_not_name_the_restricted_folders() {
    let hub = hub().await;
    let (status, body) = send(&hub.router, list("", &hub.employee)).await;
    assert_eq!(status, StatusCode::OK);
    let mut ids = Vec::new();
    folder_ids(&body["data"]["folders"], &mut ids);
    assert_eq!(
        ids,
        vec!["", "hospitality", "whatsapp", "whatsapp/headers"],
        "only the business' own folders are offered"
    );
}

#[tokio::test]
async fn a_cashier_still_reads_the_folders_of_the_business() {
    // The till paints the product photos for the cashier, and the WhatsApp header samples live in
    // a folder of the business too: closing the hub's folders must not close these.
    let hub = hub().await;
    let (status, _) = send(&hub.router, list("hospitality", &hub.employee)).await;
    assert_eq!(status, StatusCode::OK);
    for path in ["hospitality/cafe.webp", "whatsapp/headers/0b8e.jpg"] {
        let (status, _) = send(&hub.router, raw_with_cookie(path, &hub.employee)).await;
        assert_ne!(status, StatusCode::FORBIDDEN, "raw {path:?}");
    }
    let asked: Vec<String> = hub
        .captured
        .lock()
        .unwrap()
        .iter()
        .map(|(_, query)| query.clone())
        .collect();
    assert!(
        asked.iter().any(|q| q == "path=hospitality/cafe.webp"),
        "the photo was asked for: {asked:?}"
    );
    assert!(
        asked.iter().any(|q| q == "path=whatsapp/headers/0b8e.jpg"),
        "the header sample was asked for: {asked:?}"
    );
}

#[tokio::test]
async fn an_administrator_reads_every_folder() {
    let hub = hub().await;
    let (status, body) = send(&hub.router, list("", &hub.admin)).await;
    assert_eq!(status, StatusCode::OK);
    let mut ids = Vec::new();
    folder_ids(&body["data"]["folders"], &mut ids);
    for id in ["_logs", "_system/activity", "modules/verifactu/xml"] {
        assert!(ids.iter().any(|i| i == id), "{id} missing from {ids:?}");
    }
    let (status, _) = send(&hub.router, list("_logs", &hub.admin)).await;
    assert_eq!(status, StatusCode::OK);
    let (status, _) = send(
        &hub.router,
        raw("modules/verifactu/xml/rec-1.xml", &hub.admin),
    )
    .await;
    assert_ne!(status, StatusCode::FORBIDDEN);
    assert!(
        hub.captured
            .lock()
            .unwrap()
            .iter()
            .any(|(_, q)| q == "path=modules/verifactu/xml/rec-1.xml"),
        "the administrator's download reached erplora.com"
    );
}
