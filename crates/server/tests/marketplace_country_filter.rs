//! **The marketplace catalogue is asked FOR THE HUB'S COUNTRY** (ADR-0062, hub#69).
//!
//! Compliance is sold as atomic modules per regime (`verifactu`, `ticketbai`, `nf525`…), each
//! declaring the countries it applies to. The hub asked for the catalogue without ever saying where
//! it is, so it got every country's regime at once: a hub in France was offered VeriFactu, a
//! Spanish regime it cannot use, and the module it does need was buried among the rest.
//!
//! The chain these tests pin down: `hub_settings.country_code` → the runtime proxy appends
//! `?countries=` → the SaaS filters by `Module.countries` (a module with none is universal and
//! always shows). **The front is not in the conversation** — it receives the catalogue already
//! filtered, so a query param from the page cannot widen what a till is offered.

//! ⚠️ Cada aserción de aquí fija la query **entera**, así que también ve el `lang=` que viaja
//! desde `hub_settings.language` (hub#1003, ADR-0364) — el respaldo que usa el runtime cuando la
//! petición no trae `?locale=`, como es el caso de estos tests. El sujeto sigue siendo el país: si
//! el filtro de país se rompe, estos tests siguen cayendo. El idioma tiene los suyos, en
//! `crates/cloud-client` y en `apps/web`.

use axum::body::Body;
use axum::http::{Request, StatusCode, Uri};
use axum::routing::get;
use axum::{Json, Router};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig, DEV_HUB_ID};
use serde_json::json;
use std::sync::{Arc, Mutex};
use tower::ServiceExt; // oneshot

/// Boots a mock SaaS on `path` that records the query string it was called with, and answers a
/// one-module catalogue. Returns the address and the recorded-query handle.
async fn mock_cloud(path: &'static str) -> (String, Arc<Mutex<Option<String>>>, tokio::task::JoinHandle<()>) {
    let seen: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));
    let recorder = seen.clone();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let router = Router::new().route(
        path,
        get(move |uri: Uri| {
            let recorder = recorder.clone();
            async move {
                *recorder.lock().unwrap() = Some(uri.query().unwrap_or_default().to_string());
                (
                    StatusCode::OK,
                    Json(json!({ "results": [{ "module_id": "inventory" }] })),
                )
            }
        }),
    );
    let task = tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });
    (format!("http://{address}"), seen, task)
}

fn config(cloud_base_url: String, hub_id: &str, token: Option<&str>, tag: &str) -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: hub_id.into(),
        cloud_base_url,
        module_cache: std::env::temp_dir().join(format!("erplora-country-{tag}-cache")),
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: token.map(str::to_string),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join(format!("erplora-country-{tag}-media")),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

async fn ask_catalogue(rt: Runtime, cfg: HubConfig) {
    let response = app(AppState::with_config(rt, cfg))
        .oneshot(
            Request::builder()
                .uri("/api/marketplace/catalog")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
}

/// A REGISTERED hub (machine credential, `/modules/`) asks about its own country.
#[tokio::test]
async fn a_registered_hub_asks_the_marketplace_about_its_own_country() {
    let (url, seen, task) = mock_cloud("/api/v1/marketplace/modules/").await;

    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "real-hub");
    rt.ensure_system_tables().await.unwrap();
    rt.set_settings(
        &[("country_code".to_string(), json!("FR"))].into_iter().collect(),
        "test",
    )
    .await
    .unwrap();

    ask_catalogue(rt, config(url, "real-hub", Some("machine-secret"), "registered")).await;

    assert_eq!(
        seen.lock().unwrap().clone().unwrap(),
        "countries=FR&lang=es",
        "the catalogue must be asked about the country the hub has stored"
    );
    task.abort();
}

/// The REGION refines it when the hub declares one (TicketBAI vs VeriFactu in the foral regions).
///
/// 🔴 Note the two spellings: the hub stores `ES-PV` (full ISO-3166-2, what `validate_region`
/// accepts) and the marketplace filter wants `PV` alone. Sending the stored form matches no link
/// and errors nowhere, so a hub in the Basque Country would be offered VeriFactu instead of
/// TicketBAI. `CountryFilter` translates at the boundary; this asserts the wire, not the store.
#[tokio::test]
async fn a_region_travels_alongside_the_country() {
    let (url, seen, task) = mock_cloud("/api/v1/marketplace/modules/").await;

    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "real-hub");
    rt.ensure_system_tables().await.unwrap();
    rt.set_settings(
        &[
            ("country_code".to_string(), json!("ES")),
            ("region_code".to_string(), json!("ES-PV")),
        ]
        .into_iter()
        .collect(),
        "test",
    )
    .await
    .unwrap();

    ask_catalogue(rt, config(url, "real-hub", Some("machine-secret"), "region")).await;

    assert_eq!(
        seen.lock().unwrap().clone().unwrap(),
        "countries=ES&region=PV&lang=es"
    );
    task.abort();
}

/// **The demo path carries the same filter.** A demo is a real hub in a real country (ADR-0197);
/// offering it another country's fiscal regime is the same wrong answer, and it is the surface a
/// visitor judges the product by.
#[tokio::test]
async fn the_demo_catalogue_is_filtered_by_country_too() {
    let (url, seen, task) = mock_cloud("/api/v1/marketplace/catalog/").await;

    let rt = Runtime::new(Box::new(fresh_db().await));
    rt.ensure_system_tables().await.unwrap();
    rt.set_settings(
        &[("country_code".to_string(), json!("PT"))].into_iter().collect(),
        "test",
    )
    .await
    .unwrap();

    ask_catalogue(rt, config(url, DEV_HUB_ID, None, "demo")).await;

    assert_eq!(seen.lock().unwrap().clone().unwrap(), "countries=PT&lang=es");
    task.abort();
}

/// 🔴 The other direction, and the one that would be expensive to get wrong: a hub whose country
/// cannot be resolved gets the WHOLE catalogue, not an empty shelf. Not knowing where a hub is is a
/// reason to show everything.
#[tokio::test]
async fn a_hub_with_no_country_still_sees_the_whole_catalogue() {
    let (url, seen, task) = mock_cloud("/api/v1/marketplace/catalog/").await;

    // No `ensure_system_tables`: `hub_settings` does not even exist, the harshest version of
    // "the country cannot be read".
    let rt = Runtime::new(Box::new(fresh_db().await));

    ask_catalogue(rt, config(url, DEV_HUB_ID, None, "nocountry")).await;

    assert_eq!(
        seen.lock().unwrap().clone().unwrap(),
        "",
        "no country resolved → no filter, never an empty catalogue"
    );
    task.abort();
}
