//! Servidor efímero para validar la presencia pública con un navegador real.
//!
//! Lo usa `apps/web/tests/e2e/PublicWeb.spec.ts`: crea una BD aislada, siembra una página y sirve
//! el router de producción en `PUBLIC_E2E_BIND` (127.0.0.1:8790 por defecto). No contiene atajos de
//! render ni mocks HTTP; la respuesta pasa por el mismo gate, renderer y CSP que producción.

use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::public::PublicSnapshot;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use serde_json::json;

#[tokio::main]
async fn main() {
    let hub_id = "hub-public-playwright";
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.expect("system tables");
    rt.set_public_page(
        "carta",
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

    let temp = std::env::temp_dir().join("erplora-public-playwright");
    let cfg = HubConfig {
        hub_id: hub_id.into(),
        cloud_base_url: "https://example.invalid".into(),
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
    let state = AppState::with_config(rt, cfg).with_public_snapshot(PublicSnapshot {
        landing_visible: true,
        business_name: "Bar Pepe".into(),
        business_address: "Calle Mayor 1".into(),
    });
    let bind = std::env::var("PUBLIC_E2E_BIND").unwrap_or_else(|_| "127.0.0.1:8790".into());
    let listener = tokio::net::TcpListener::bind(&bind).await.expect("bind public e2e server");
    println!("public e2e server listening on http://{bind}");
    axum::serve(listener, app(state)).await.expect("serve public e2e server");
}
