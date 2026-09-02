//! Tests de integración del **gateway multi-tenant compartido** (ADR-0005, hub#24) por HTTP.
//!
//! Verifican los criterios de aceptación del issue end-to-end, a través de los handlers reales de
//! Axum (`/api/command`, `/api/query`) con `tower::ServiceExt::oneshot`, sin red:
//!  1. Un request con el token (`X-Hub-Id`) de la org A solo accede a la BD de A; un `hub_id` de
//!     org desconocida se **rechaza** (`403 unknown_org`) sin tocar ninguna BD.
//!  2. El gate de permisos + el scoping `hub_id` se aplican **server-side** sobre el runtime de la
//!     org resuelta.
//!  3. N orgs servidas por **un solo proceso/router**, con un pool por org.
//!
//! Cada org usa su **propio SQLite en memoria** (factory de test) → dos "Aurora por-org" simuladas
//! sin Postgres real. El test que requiere Postgres real iría `#[ignore]` como el resto del repo.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{
    app, AppState, AuthMode, EnvOrgResolver, HubConfig, OrgDescriptor, OrgId, RuntimeFactory,
    TenantRouter,
};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_inventory")
}

async fn body_json(resp: axum::response::Response) -> Value {
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// POST con cabeceras de auth de Dev: el `X-Hub-Id` es la identidad (no spoofable en prod, la
/// inyecta el despliegue) por la que el gateway resuelve la org.
fn post_as(hub_id: &str, perms: &str, uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("x-hub-id", hub_id)
        .header("x-user-id", "u1")
        .header("x-permissions", perms)
        .body(Body::from(body.to_string()))
        .unwrap()
}

/// Factory de test: cada org abre su PROPIO SQLite en memoria e instala el módulo inventory del
/// fixture. Dos orgs ⇒ dos pools independientes ⇒ aislamiento estructural.
fn inventory_factory() -> RuntimeFactory {
    Arc::new(|desc: &OrgDescriptor| {
        let hub_id = desc.org_id.0.clone();
        Box::pin(async move {
            let db = fresh_db().await;
            let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
            rt.install_from_dir(&fixture())
                .await
                .expect("instala inventory");
            Ok(rt)
        })
    })
}

/// AppState en modo **cloud compartido** con dos orgs (org-a ← hub-a1, org-b ← hub-b1).
async fn shared_app() -> axum::Router {
    // Resolvedor mínimo por entorno: mapea cada hub_id a su org (el DSN es irrelevante con el
    // factory SQLite). En prod este seam lo cubre el plano de control de Django.
    let mut map = HashMap::new();
    map.insert(
        "hub-a1".to_string(),
        OrgDescriptor {
            org_id: OrgId("org-a".into()),
            dsn: "sqlite::memory:".into(),
        },
    );
    map.insert(
        "hub-b1".to_string(),
        OrgDescriptor {
            org_id: OrgId("org-b".into()),
            dsn: "sqlite::memory:".into(),
        },
    );
    let router = Arc::new(TenantRouter::with_factory(
        Arc::new(EnvOrgResolver::new(map)),
        inventory_factory(),
        32,
    ));

    // El `runtime` single-tenant del AppState es un throwaway (no se usa en el camino de datos
    // cuando hay tenants): un SQLite vacío sirve de bootstrap.
    let db = fresh_db().await;
    let base = AppState::with_config(
        Runtime::new(Box::new(db)),
        HubConfig::from_env_with_auth(AuthMode::Dev),
    );
    app(base.with_tenants(router))
}

/// Criterio 1 + 3: dos orgs en un solo router; el token de A solo ve datos de A, el de B solo los
/// de B. Mismo SKU en ambas, sin colisión (pools independientes + scoping `hub_id`).
#[tokio::test]
async fn org_a_request_only_touches_org_a_db() {
    let app = shared_app().await;

    // Org A crea un producto.
    let r = app
        .clone()
        .oneshot(post_as(
            "hub-a1",
            "*",
            "/api/command",
            json!({ "name": "inventory.products.create",
                    "payload": { "name": "Café de A", "sku": "SKU1", "price": 4.5, "stock": 10 } }),
        ))
        .await
        .unwrap();
    assert_eq!(r.status(), StatusCode::OK);

    // Org B crea otro producto (mismo SKU, otra BD).
    let r = app
        .clone()
        .oneshot(post_as(
            "hub-b1",
            "*",
            "/api/command",
            json!({ "name": "inventory.products.create",
                    "payload": { "name": "Té de B", "sku": "SKU1", "price": 2.0, "stock": 5 } }),
        ))
        .await
        .unwrap();
    assert_eq!(r.status(), StatusCode::OK);

    // A solo ve su producto.
    let la = app
        .clone()
        .oneshot(post_as(
            "hub-a1",
            "*",
            "/api/query",
            json!({ "name": "inventory.products.list" }),
        ))
        .await
        .unwrap();
    let ja = body_json(la).await;
    let rows_a = ja["data"].as_array().unwrap();
    assert_eq!(rows_a.len(), 1, "A solo ve su propio dato");
    assert_eq!(rows_a[0]["name"], json!("Café de A"));

    // B solo ve su producto (nunca el de A).
    let lb = app
        .clone()
        .oneshot(post_as(
            "hub-b1",
            "*",
            "/api/query",
            json!({ "name": "inventory.products.list" }),
        ))
        .await
        .unwrap();
    let jb = body_json(lb).await;
    let rows_b = jb["data"].as_array().unwrap();
    assert_eq!(rows_b.len(), 1, "B solo ve su propio dato");
    assert_eq!(rows_b[0]["name"], json!("Té de B"));
}

/// Criterio 1 (rechazo): un `hub_id` que no mapea a ninguna org se rechaza con `403 unknown_org`
/// ANTES de tocar BD alguna. Es la barrera anti acceso cruzado / hub no provisionado.
#[tokio::test]
async fn unknown_org_hub_id_is_rejected_403() {
    let app = shared_app().await;
    let r = app
        .oneshot(post_as(
            "hub-intruso", // no está en el resolvedor
            "*",
            "/api/query",
            json!({ "name": "inventory.products.list" }),
        ))
        .await
        .unwrap();
    assert_eq!(r.status(), StatusCode::FORBIDDEN);
    assert_eq!(body_json(r).await["error"]["code"], json!("unknown_org"));
}

/// Criterio 2: el gate de permisos sigue siendo server-side sobre el runtime de la org resuelta —
/// un usuario de la org A sin permiso de `create` recibe `403 permission_denied` (no un bypass por
/// estar en el tier compartido).
#[tokio::test]
async fn permission_gate_still_enforced_per_org() {
    let app = shared_app().await;
    let r = app
        .oneshot(post_as(
            "hub-a1",
            "inventory.products.read", // sin create
            "/api/command",
            json!({ "name": "inventory.products.create",
                    "payload": { "name": "X", "sku": "X", "price": 1, "stock": 1 } }),
        ))
        .await
        .unwrap();
    assert_eq!(r.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        body_json(r).await["error"]["code"],
        json!("permission_denied")
    );
}
