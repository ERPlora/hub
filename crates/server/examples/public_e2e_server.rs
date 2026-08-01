//! Entorno reproducible para el E2E real de la presencia pública (hub#224).
//!
//! Playwright recorre navegador → Vite → Axum → Runtime/Postgres y, para media, un mini-Cloud
//! efímero que conserva objetos en memoria. No hay interceptores ni respuestas simuladas dentro
//! del navegador: editor, settings, upload, SSR, ETag, CSP y media usan sus handlers reales.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use axum::body::Body;
use axum::extract::{Multipart, Path, Query, State};
use axum::http::{header, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::public::PublicSnapshot;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use tokio::sync::Mutex;

#[derive(Clone)]
struct MediaCloud {
    objects: Arc<Mutex<HashMap<String, Vec<u8>>>>,
    origin: String,
}

#[derive(Deserialize)]
struct RawQuery {
    path: String,
}

async fn media_upload(State(state): State<MediaCloud>, mut multipart: Multipart) -> Json<Value> {
    let mut folder = String::new();
    let mut files = Vec::new();
    while let Ok(Some(field)) = multipart.next_field().await {
        match field.name() {
            Some("folder") => folder = field.text().await.unwrap_or_default(),
            Some("files") => {
                let name = field.file_name().unwrap_or("file").to_string();
                if let Ok(bytes) = field.bytes().await {
                    files.push((name, bytes.to_vec()));
                }
            }
            _ => {}
        }
    }
    let mut objects = state.objects.lock().await;
    for (name, bytes) in files {
        objects.insert(format!("{}/{name}", folder.trim_matches('/')), bytes);
    }
    Json(json!({ "ok": true }))
}

async fn media_raw(State(state): State<MediaCloud>, Query(query): Query<RawQuery>) -> Response {
    if !state.objects.lock().await.contains_key(&query.path) {
        return StatusCode::NOT_FOUND.into_response();
    }
    Json(json!({ "url": format!("{}/objects/{}", state.origin, query.path) })).into_response()
}

async fn object(State(state): State<MediaCloud>, Path(path): Path<String>) -> Response {
    let Some(bytes) = state.objects.lock().await.get(&path).cloned() else {
        return StatusCode::NOT_FOUND.into_response();
    };
    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, "image/png")
        .body(Body::from(bytes))
        .expect("object response")
}

async fn spawn_media_cloud() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind media cloud");
    let address = listener.local_addr().expect("media cloud address");
    let origin = format!("http://{address}");
    let state = MediaCloud {
        objects: Arc::new(Mutex::new(HashMap::new())),
        origin: origin.clone(),
    };
    let router = Router::new()
        .route("/api/v1/hub/device/media/", post(media_upload))
        .route("/api/v1/hub/device/media/raw", get(media_raw))
        .route("/objects/*path", get(object))
        .with_state(state);
    tokio::spawn(async move {
        axum::serve(listener, router)
            .await
            .expect("serve media cloud")
    });
    origin
}

#[tokio::main]
async fn main() {
    let hub_id = "hub-public-playwright";
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.expect("system tables");
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixture_public_query");
    rt.install_from_dir(&fixture)
        .await
        .expect("install public page fixture");

    let mut settings = Map::new();
    settings.insert("public.landing.visible".into(), json!(true));
    settings.insert("business_legal_name".into(), json!("Bar Pepe"));
    settings.insert("business_address".into(), json!("Calle Mayor 1"));
    settings.insert("country_code".into(), json!("ES"));
    settings.insert("currency".into(), json!("EUR"));
    settings.insert("language".into(), json!("es"));
    rt.set_settings(&settings, "playwright")
        .await
        .expect("seed public settings");
    rt.set_public_page(
        "menu",
        &json!({
            "blocks": [
                { "type": "header", "data": { "text": "Nuestra carta", "level": 1 } },
                { "type": "paragraph", "data": { "text": "Café <b>recién molido</b>" } }
            ]
        }),
        "playwright",
    )
    .await
    .expect("seed public page");

    let cloud_base_url = spawn_media_cloud().await;
    let temp = std::env::temp_dir().join(format!(
        "erplora-public-playwright-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&temp);
    let cfg = HubConfig {
        hub_id: hub_id.into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("playwright-machine-token".into()),
        device_trust_enforce: false,
        media_dir: temp.join("media"),
        sector: None,
        dev_mode: true,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let bind = std::env::var("PUBLIC_E2E_BIND").unwrap_or_else(|_| "127.0.0.1:8787".into());
    let listener = tokio::net::TcpListener::bind(&bind)
        .await
        .expect("bind public e2e server");
    let address = listener.local_addr().expect("public server address");
    let snapshot = PublicSnapshot::from_settings(&Value::Object(settings))
        .with_origin(Some(&format!("http://{address}")))
        .expect("public origin");
    let state = AppState::with_config(rt, cfg).with_public_snapshot(snapshot);
    println!("public e2e server listening on http://{address}");
    axum::serve(listener, app(state))
        .await
        .expect("serve public e2e server");
}
