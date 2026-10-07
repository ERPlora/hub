//! Regression test for hub#1317 (spin-off of the hub#1311 review, ADR «El Hub se CIERRA como
//! KERNEL»): activate/deactivate/uninstall did not broadcast anything over `/ws`, unlike install
//! (`module.installed`) and update (`module.updated` + `module.installed`). Another tab/device of
//! the same hub stayed on yesterday's module state until it reloaded — the exact "shell blind
//! until reload" hole hub#631 closed only for `module.installed`, and since hub#1211 also the
//! module-sdk's `queryOptional` short-circuit cache staying stale in every OTHER tab.
//!
//! Same shape and same door as `module.installed` (`crates/server/src/lib.rs`): a raw frame with
//! no [`erplora_server::state::FRAME_MODULE`], published via `AppState::broadcast`, so
//! `event_stream::may_receive` treats it as "the hub's own" — exactly like `module.installed`.

use std::time::Duration;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use erplora_vector::{Chunk, MemoryVectorStore, VectorStore};
use serde_json::json;
use tokio::sync::broadcast::error::TryRecvError;
use tower::ServiceExt; // oneshot

fn cfg(module_cache: std::path::PathBuf, hub_id: &str) -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: hub_id.to_string(),
        cloud_base_url: "https://example.invalid".into(),
        module_cache,
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join(format!("erplora-lifecycle-ws-media-{hub_id}")),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// Escribe un módulo declarativo mínimo en `cache/<id>/<version>/module.json` e instalable vía
/// `Runtime::install_from_dir` (mismo patrón que `crates/server/tests/module_assets.rs`).
fn write_module(cache: &std::path::Path, id: &str, version: &str) -> std::path::PathBuf {
    let dir = cache.join(id).join(version);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        format!(r#"{{"id":"{id}","name":"{id}","version":"{version}"}}"#),
    )
    .unwrap();
    dir
}

fn request(method: &str, uri: &str, session: &str) -> Request<Body> {
    Request::builder()
        .method(method)
        .uri(uri)
        .header("x-hub-session", session)
        .body(Body::empty())
        .unwrap()
}

/// Runtime con un admin logueado y `module_id` YA instalado (estado inicial: Active, el default
/// de `installer::install`). Devuelve el `AppState` completo (para suscribirse a `state.events`
/// ANTES de golpear la ruta HTTP) + el token de sesión admin.
async fn fixture(hub_id: &str, module_id: &str) -> (AppState, String, std::path::PathBuf) {
    let cache = std::env::temp_dir().join(format!(
        "erplora-lifecycle-ws-{hub_id}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&cache);
    let dir = write_module(&cache, module_id, "1.0.0");

    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let admin_id = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    let admin = rt.create_session(&admin_id, 3600, None).await.unwrap();
    rt.install_from_dir(&dir).await.unwrap();

    let state = AppState::with_config(rt, cfg(cache.clone(), hub_id));
    (state, admin, cache)
}

#[tokio::test]
async fn activating_a_module_broadcasts_module_activated_exactly_once_hub1317() {
    let (state_owner, admin, cache) = fixture("hub-lifecycle-activate", "demo").await;
    // Arranca INACTIVO (llamado directo al runtime, sin pasar por HTTP: no debe emitir nada).
    state_owner
        .runtime
        .write()
        .await
        .deactivate("demo")
        .await
        .unwrap();
    let mut rx = state_owner.events.subscribe();

    let response = app(state_owner.clone())
        .oneshot(request("POST", "/api/modules/demo/activate", &admin))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let frame = tokio::time::timeout(Duration::from_secs(2), rx.recv())
        .await
        .expect("timed out waiting for module.activated")
        .unwrap();
    assert_eq!(
        frame,
        json!({ "type": "module.activated", "module_id": "demo" })
    );
    assert_eq!(
        rx.try_recv().unwrap_err(),
        TryRecvError::Empty,
        "activate must broadcast module.activated exactly once"
    );

    std::fs::remove_dir_all(cache).ok();
}

#[tokio::test]
async fn deactivating_a_module_broadcasts_module_deactivated_exactly_once_hub1317() {
    let (state, admin, cache) = fixture("hub-lifecycle-deactivate", "demo").await;
    // Ya está Active tras instalar (default de `installer::install`) — nada más que preparar.
    let mut rx = state.events.subscribe();

    let response = app(state.clone())
        .oneshot(request("POST", "/api/modules/demo/deactivate", &admin))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let frame = tokio::time::timeout(Duration::from_secs(2), rx.recv())
        .await
        .expect("timed out waiting for module.deactivated")
        .unwrap();
    assert_eq!(
        frame,
        json!({ "type": "module.deactivated", "module_id": "demo" })
    );
    assert_eq!(
        rx.try_recv().unwrap_err(),
        TryRecvError::Empty,
        "deactivate must broadcast module.deactivated exactly once"
    );

    std::fs::remove_dir_all(cache).ok();
}

#[tokio::test]
async fn uninstalling_a_module_broadcasts_module_uninstalled_exactly_once_hub1317() {
    let (state, admin, cache) = fixture("hub-lifecycle-uninstall", "demo").await;
    let mut rx = state.events.subscribe();

    let response = app(state.clone())
        .oneshot(request("POST", "/api/modules/demo/uninstall", &admin))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    let frame = tokio::time::timeout(Duration::from_secs(2), rx.recv())
        .await
        .expect("timed out waiting for module.uninstalled")
        .unwrap();
    assert_eq!(
        frame,
        json!({ "type": "module.uninstalled", "module_id": "demo" })
    );
    assert_eq!(
        rx.try_recv().unwrap_err(),
        TryRecvError::Empty,
        "uninstall must broadcast module.uninstalled exactly once"
    );

    std::fs::remove_dir_all(cache).ok();
}

/// hub#2545: forcing the uninstall of an app others depend on removes them too, so every other
/// tab/device has to hear about EACH app that left — not only the one the owner clicked, or their
/// menus would keep tabs for apps that are no longer installed. The answer names the dependents
/// that went with it, for the screen that asked.
#[tokio::test]
async fn a_forced_uninstall_broadcasts_every_app_that_left_and_names_them_hub2545() {
    let (state, admin, cache) = fixture("hub-lifecycle-forced-2545", "base").await;
    let child = cache.join("child").join("1.0.0");
    std::fs::create_dir_all(&child).unwrap();
    std::fs::write(
        child.join("module.json"),
        r#"{"id":"child","name":"child","version":"1.0.0","depends_on":["base"]}"#,
    )
    .unwrap();
    state
        .runtime
        .write()
        .await
        .install_from_dir(&child)
        .await
        .unwrap();
    // Both apps taught the assistant something: what leaves must leave its index too (§9.6).
    let store = std::sync::Arc::new(MemoryVectorStore::new());
    for ref_id in ["base", "child"] {
        store
            .upsert(&Chunk {
                id: format!("{ref_id}-1"),
                hub_id: "hub-lifecycle-forced-2545".into(),
                ref_id: ref_id.into(),
                version: "1.0.0".into(),
                lang: "es".into(),
                source: "module.json".into(),
                content: ref_id.into(),
                embedding: vec![1.0, 0.0],
            })
            .await
            .unwrap();
    }
    let state = state.with_vector(store.clone());
    let mut rx = state.events.subscribe();

    let response = app(state.clone())
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/modules/base/uninstall")
                .header("x-hub-session", admin.as_str())
                .header("content-type", "application/json")
                .body(Body::from(r#"{"force":true}"#))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), 1 << 20)
        .await
        .unwrap();
    let body: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(body, json!({ "ok": true, "also_uninstalled": ["child"] }));

    let mut frames = Vec::new();
    for _ in 0..2 {
        frames.push(
            tokio::time::timeout(Duration::from_secs(2), rx.recv())
                .await
                .expect("timed out waiting for module.uninstalled")
                .unwrap(),
        );
    }
    assert_eq!(
        frames,
        vec![
            json!({ "type": "module.uninstalled", "module_id": "child" }),
            json!({ "type": "module.uninstalled", "module_id": "base" }),
        ]
    );
    assert_eq!(
        rx.try_recv().unwrap_err(),
        TryRecvError::Empty,
        "one module.uninstalled per app that left, and no more"
    );
    assert!(state.runtime.read().await.modules().is_empty());
    assert!(
        store
            .indexed_refs("hub-lifecycle-forced-2545")
            .await
            .unwrap()
            .is_empty(),
        "the assistant must not keep answering about an app that left with the forced one"
    );

    std::fs::remove_dir_all(cache).ok();
}

/// Guard-catches-the-positive control: a FAILED activate (module never installed) must NOT
/// broadcast anything — the event means "this actually changed", not "this door was hit".
#[tokio::test]
async fn a_rejected_activate_on_an_unknown_module_broadcasts_nothing_hub1317() {
    let (state, admin, cache) = fixture("hub-lifecycle-reject", "demo").await;
    let mut rx = state.events.subscribe();

    let response = app(state.clone())
        .oneshot(request(
            "POST",
            "/api/modules/does-not-exist/activate",
            &admin,
        ))
        .await
        .unwrap();
    assert_ne!(response.status(), StatusCode::OK);
    assert_eq!(
        rx.try_recv().unwrap_err(),
        TryRecvError::Empty,
        "a rejected activate must not broadcast module.activated"
    );

    std::fs::remove_dir_all(cache).ok();
}
