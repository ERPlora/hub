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
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{
    app, AppState, AuthMode, EnvOrgResolver, HubConfig, OrgDescriptor, OrgId, RuntimeFactory,
    TenantRouter,
};
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

async fn media_upload(
    State(state): State<MediaCloud>,
    headers: HeaderMap,
    mut multipart: Multipart,
) -> Json<Value> {
    let hub_id = headers
        .get("x-hub-id")
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
        .to_string();
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
        objects.insert(
            format!("{hub_id}:{}/{name}", folder.trim_matches('/')),
            bytes,
        );
    }
    Json(json!({ "ok": true }))
}

async fn media_raw(
    State(state): State<MediaCloud>,
    headers: HeaderMap,
    Query(query): Query<RawQuery>,
) -> Response {
    let hub_id = headers
        .get("x-hub-id")
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    if !state
        .objects
        .lock()
        .await
        .contains_key(&format!("{hub_id}:{}", query.path))
    {
        return StatusCode::NOT_FOUND.into_response();
    }
    Json(json!({ "url": format!("{}/objects/{hub_id}/{}", state.origin, query.path) }))
        .into_response()
}

async fn object(State(state): State<MediaCloud>, Path(path): Path<String>) -> Response {
    let Some((hub_id, relative)) = path.split_once('/') else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let Some(bytes) = state
        .objects
        .lock()
        .await
        .get(&format!("{hub_id}:{relative}"))
        .cloned()
    else {
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

fn public_runtime_factory() -> RuntimeFactory {
    Arc::new(|descriptor: &OrgDescriptor| {
        let org_id = descriptor.org_id.0.clone();
        Box::pin(async move {
            let db = fresh_db().await;
            let mut runtime = Runtime::with_hub_id(Box::new(db), org_id.clone());
            runtime
                .ensure_system_tables()
                .await
                .expect("tenant system tables");
            let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixture_public_query");
            runtime
                .install_from_dir(&fixture)
                .await
                .expect("tenant public fixture");
            let (business, address, heading, paragraph) = if org_id == "org-a" {
                (
                    "Bar Pepe",
                    "Calle Mayor 1",
                    "Nuestra carta",
                    "Café <b>recién molido</b> · Tenant A",
                )
            } else {
                ("Bistró Beta", "Calle Norte 2", "Carta Beta", "Tenant B")
            };
            let mut settings = Map::new();
            settings.insert("public.landing.visible".into(), json!(true));
            settings.insert("business_legal_name".into(), json!(business));
            settings.insert("business_address".into(), json!(address));
            settings.insert("country_code".into(), json!("ES"));
            settings.insert("currency".into(), json!("EUR"));
            settings.insert("language".into(), json!("es"));
            runtime
                .set_settings(&settings, "playwright")
                .await
                .expect("tenant public settings");
            runtime
                .set_public_page(
                    "menu",
                    &json!({
                        "blocks": [
                            { "type": "header", "data": { "text": heading, "level": 1 } },
                            { "type": "paragraph", "data": { "text": paragraph } }
                        ]
                    }),
                    "playwright",
                )
                .await
                .expect("tenant public page");
            Ok(runtime)
        })
    })
}

#[tokio::main]
async fn main() {
    let cloud_base_url = spawn_media_cloud().await;
    let temp = std::env::temp_dir().join(format!(
        "erplora-public-playwright-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&temp);
    let cfg = HubConfig {
        hub_id: "hub-public-playwright".into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("bootstrap-token-must-never-leave".into()),
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
    let mut descriptors = HashMap::new();
    for (hub_id, org_id, origin, token) in [
        (
            "hub-public-playwright",
            "org-a",
            format!("http://{address}"),
            "token-a",
        ),
        (
            "hub-a",
            "org-a",
            format!("http://a.localhost:{}", address.port()),
            "token-a",
        ),
        (
            "hub-b",
            "org-b",
            format!("http://b.localhost:{}", address.port()),
            "token-b",
        ),
    ] {
        descriptors.insert(
            hub_id.to_string(),
            OrgDescriptor {
                org_id: OrgId(org_id.into()),
                dsn: "unused".into(),
                cloud_api_token: Some(token.into()),
                public_origin: Some(origin),
            },
        );
    }
    let tenants = Arc::new(TenantRouter::with_factory(
        Arc::new(EnvOrgResolver::new(descriptors)),
        public_runtime_factory(),
        8,
    ));
    let bootstrap = Runtime::with_hub_id(Box::new(fresh_db().await), "bootstrap");
    let state = AppState::with_config(bootstrap, cfg).with_tenants(tenants);
    erplora_server::public::warm_public_snapshots(&state)
        .await
        .expect("warm public tenant snapshots");
    println!("public e2e server listening on http://{address}");
    axum::serve(
        listener,
        app(state).into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
        .await
        .expect("serve public e2e server");
}
