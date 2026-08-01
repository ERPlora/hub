//! ADR-0062: country/region persistidos viajan en el context de arranque y auto-filtran el
//! marketplace. El test usa Axum real en ambos lados y observa la URI que recibe el mini-Cloud.

use std::sync::{Arc, Mutex};

use axum::body::Body;
use axum::extract::State;
use axum::http::{Request, StatusCode, Uri};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

type Seen = Arc<Mutex<Vec<String>>>;

async fn mock_cloud() -> (String, Seen) {
    async fn catalog(State(seen): State<Seen>, uri: Uri) -> Json<Value> {
        seen.lock().unwrap().push(uri.to_string());
        Json(json!({ "results": [] }))
    }
    let seen = Arc::new(Mutex::new(Vec::new()));
    let app = Router::new()
        .route("/api/v1/marketplace/modules/", get(catalog))
        .with_state(seen.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (format!("http://{addr}"), seen)
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

fn request(uri: &str) -> Request<Body> {
    Request::builder()
        .uri(uri)
        .header("x-hub-id", "hub-country")
        .header("x-user-id", "admin")
        .header("x-permissions", "*")
        .body(Body::empty())
        .unwrap()
}

#[tokio::test]
async fn context_and_marketplace_use_persisted_country_region() {
    let (cloud, seen) = mock_cloud().await;
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-country");
    rt.ensure_system_tables().await.unwrap();
    rt.set_settings(
        &[
            ("country_code".to_string(), json!("fr")),
            ("region_code".to_string(), json!("idf")),
        ]
        .into_iter()
        .collect(),
        "test",
    )
    .await
    .unwrap();
    let cfg = HubConfig {
        hub_id: "hub-country".into(),
        cloud_base_url: cloud,
        module_cache: std::env::temp_dir().join("erplora-marketplace-country"),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("machine".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-marketplace-country-media"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    };
    let router = app(AppState::with_config(rt, cfg));

    let response = router.clone().oneshot(request("/api/hub/context")).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let context = body_json(response).await;
    assert_eq!(context["country"], json!("FR"));
    assert_eq!(context["region"], json!("IDF"));

    let response = router
        .clone()
        .oneshot(request("/api/marketplace/catalog"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        seen.lock().unwrap().last().map(String::as_str),
        Some("/api/v1/marketplace/modules/?countries=FR&region=IDF")
    );

    // Cambiar el país en la UI no arrastra la región del país persistido.
    let response = router
        .oneshot(request("/api/marketplace/catalog?countries=ES"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        seen.lock().unwrap().last().map(String::as_str),
        Some("/api/v1/marketplace/modules/?countries=ES")
    );
}
