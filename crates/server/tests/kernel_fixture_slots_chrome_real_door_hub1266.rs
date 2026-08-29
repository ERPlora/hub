//! HTTP door for `provides_slots` and `navigation[].chrome` — ERPlora/hub#1266 (review of the KCS,
//! hub#1263). Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! `crates/runtime/tests/kernel_conformance_slots_navigation.rs` used to assert on these two blocks
//! by reading the fixture's OWN `module.json` straight off disk — that proves the FIXTURE carries
//! them, never that the KERNEL serves them back. Neither block is typed by the runtime
//! (`Manifest.navigation: Vec<Nav>` has no `chrome` field, and `provides_slots` is only a recognised
//! ROOT key in `crates/runtime/src/manifest.rs`, its contents left untouched on purpose): the shell
//! reads both from the RAW `module.json` that `GET /modules/:id/*path` serves from the download
//! cache (`apps/web/src/lib/module-loader.ts::loadInstalledManifests`,
//! `crates/server/src/lib.rs::serve_module_asset`). That HTTP door is what this file drives.
//!
//! Two fixture modules, same trick the KCS install suite uses for a neighbour
//! (`crates/runtime/tests/support/kernel_fixture.rs::foreign_module_copy`): `kfx` — the fixture as
//! published, provider of the slot `kfx.items.aside` and `chrome: ["fullscreen"]` — and its twin
//! `kfy`, every `kfx` occurrence rewritten to `kfy` and its OWN `provides_slots` block stripped, so
//! `kfy` is a plain consumer of the shell's `chrome` capability that never provides a slot of its
//! own. Both installed through `Runtime::install_from_dir` from a directory sitting INSIDE the
//! configured `module_cache` (`crates/server/tests/module_assets.rs`'s pattern) — exactly where a
//! real download would leave them — so `GET /modules/:id/module.json` finds them for real: no
//! manifest is read off disk by the assertions.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::Value;
use std::path::{Path, PathBuf};
use tower::ServiceExt; // oneshot

const FIXTURE_VERSION: &str = "1.1.0";

/// The KCS fixture the runtime's own conformance suite installs
/// (`crates/runtime/tests/fixtures/kernel-fixture/`), read from the sibling crate: `erplora-runtime`
/// and `erplora-server` sit side by side under `crates/`.
fn fixture_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../runtime/tests/fixtures/kernel-fixture")
        .join(FIXTURE_VERSION)
}

fn cfg(module_cache: PathBuf) -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: "hub-slots-chrome".into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache,
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-test-media-slots-chrome"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

fn copy_tree(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).expect("scratch dir");
    for entry in std::fs::read_dir(from).expect("read fixture").flatten() {
        let target = to.join(entry.file_name());
        if entry.path().is_dir() {
            copy_tree(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), &target).expect("copy fixture file");
        }
    }
}

/// Rewrites every `from` occurrence to `to` in the tree's JSON/SQL text files — the same trick
/// `kernel_fixture::foreign_module_copy` uses to mint a neighbour module: id, tables, slot names,
/// permissions and events all carry the module id, so one text replace produces a whole twin. The
/// compiled `handler.wasm` is left untouched (still speaks `kfx`) and is never invoked here — these
/// tests only install and read the manifest back, they never execute a command.
fn rewrite_tree(dir: &Path, from: &str, to: &str) {
    for entry in std::fs::read_dir(dir).expect("read the twin").flatten() {
        let path = entry.path();
        if path.is_dir() {
            rewrite_tree(&path, from, to);
            continue;
        }
        let is_text = path
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| matches!(e, "json" | "sql"));
        if is_text {
            let text = std::fs::read_to_string(&path).expect("read a twin file");
            std::fs::write(&path, text.replace(from, to)).expect("rewrite a twin file");
        }
    }
}

/// Copies the fixture at `id` directly inside `cache/<id>/<version>/` — where a real download would
/// leave it — applies `mutate` to its `module.json`, and registers it through the REAL installer
/// (`install_from_dir`) from that same path, so the version `serve_module_asset` looks up in the
/// registry is the version sitting in the cache.
async fn install_into_cache(
    rt: &mut Runtime,
    cache: &Path,
    id: &str,
    mutate: impl FnOnce(&mut Value),
) -> PathBuf {
    let dest = cache.join(id).join(FIXTURE_VERSION);
    copy_tree(&fixture_dir(), &dest);
    if id != "kfx" {
        rewrite_tree(&dest, "kfx", id);
    }
    let manifest_path = dest.join("module.json");
    let mut manifest: Value =
        serde_json::from_str(&std::fs::read_to_string(&manifest_path).expect("read manifest"))
            .expect("parse manifest");
    mutate(&mut manifest);
    std::fs::write(
        &manifest_path,
        serde_json::to_string_pretty(&manifest).expect("serialise manifest"),
    )
    .expect("write manifest");
    rt.install_from_dir(&dest)
        .await
        .unwrap_or_else(|e| panic!("install the {id} fixture: {e}"));
    dest
}

async fn get_json(router: axum::Router, uri: &str) -> (StatusCode, Value) {
    let resp = router
        .oneshot(Request::get(uri).body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let value = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or(Value::Null)
    };
    (status, value)
}

/// 🔴 Regression test for ERPlora/hub#1266: `provides_slots` and `navigation[].chrome` travel
/// verbatim through the SAME door the shell uses (`GET /modules/:id/module.json`), never read off
/// the fixture's file on disk.
#[tokio::test]
async fn provides_slots_and_chrome_travel_through_the_real_http_door_hub1266() {
    let cache = std::env::temp_dir().join(format!("erplora-kcs-door-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&cache);

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_into_cache(&mut rt, &cache, "kfx", |_| {}).await;
    let state = AppState::with_config(rt, cfg(cache.clone()));

    let (status, body) = get_json(app(state), "/modules/kfx/module.json").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        body["provides_slots"][0]["slot"],
        serde_json::json!("kfx.items.aside"),
        "served manifest: {body}"
    );
    assert_eq!(
        body["provides_slots"][0]["component"],
        serde_json::json!("kfx-aside"),
        "the filler is the module's OWN component: coupling by slot name, never by import — served manifest: {body}"
    );
    assert_eq!(
        body["navigation"][0]["chrome"],
        serde_json::json!(["fullscreen"]),
        "chrome is an opt-in to a control the SHELL owns; the module never ships the button — served manifest: {body}"
    );

    let _ = std::fs::remove_dir_all(&cache);
}

/// Two modules installed side by side through the real door: `kfx` provides a slot, its neighbour
/// `kfy` does not (a plain consumer of `chrome`, no `provides_slots` block at all). Each one's
/// `GET /modules/:id/module.json` carries only what ITS OWN manifest declares — never the
/// neighbour's, and never a slot nobody declared. A door that leaked or merged manifests across
/// modules would hand every consumer of `kfx.items.aside` a filler from a module that never wrote
/// it, or invent a slot for a module that opted out entirely.
#[tokio::test]
async fn an_undeclared_slot_is_never_served_for_the_neighbour_module_hub1266() {
    let cache = std::env::temp_dir().join(format!("erplora-kcs-door-twin-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&cache);

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    install_into_cache(&mut rt, &cache, "kfx", |_| {}).await;
    install_into_cache(&mut rt, &cache, "kfy", |manifest| {
        manifest
            .as_object_mut()
            .expect("manifest is an object")
            .remove("provides_slots");
    })
    .await;
    let state = AppState::with_config(rt, cfg(cache.clone()));

    let (status, kfx) = get_json(app(state.clone()), "/modules/kfx/module.json").await;
    assert_eq!(status, StatusCode::OK);
    let (status, kfy) = get_json(app(state.clone()), "/modules/kfy/module.json").await;
    assert_eq!(status, StatusCode::OK);

    assert_eq!(
        kfx["provides_slots"][0]["slot"],
        serde_json::json!("kfx.items.aside"),
        "the provider keeps its own slot: {kfx}"
    );
    assert!(
        kfy.get("provides_slots").is_none(),
        "kfy never declared a slot — the door must not invent one for it: {kfy}"
    );
    // And what `kfy` DOES declare (its own `navigation[].chrome`) is untouched by the neighbour.
    assert_eq!(
        kfy["navigation"][0]["chrome"],
        serde_json::json!(["fullscreen"]),
        "served manifest: {kfy}"
    );

    let _ = std::fs::remove_dir_all(&cache);
}
