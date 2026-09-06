//! `GET /api/navigation` must not offer a tab whose permission the actor does not have (hub#1052).
//!
//! A module could not express «this tab is admin-only». `navigation[]` had no `permission` field
//! and the endpoint filtered nothing, so the module painted the tab for everyone and the user
//! discovered the limit by crashing into a `403`.
//!
//! `flows` is the case that shows the shape of the bug best: the module took the right decision and
//! had nowhere to write it. Its own code says a cashier gets a `403` there and that sending them to
//! check their permissions «would point them at a place they cannot go» — and it painted the tab
//! anyway, because the contract had no way to say otherwise.
//!
//! Two properties, both load-bearing:
//!
//! - A tab WITHOUT `permission` behaves exactly as before: visible to everyone. Every published
//!   manifest predates this field, so anything else would empty the menu of the whole fleet.
//! - The filter shares its predicate with the real gate (`permissions::has`), so the menu and the
//!   command can never disagree about what a permission means.
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt; // oneshot

/// A module with two tabs: one gated behind a permission, one open to everyone.
fn write_module(root: &Path) -> PathBuf {
    let dir = root.join("reports");
    fs::create_dir_all(&dir).unwrap();
    let manifest = json!({
        "id": "reports",
        "name": "Reports",
        "version": "1.0.0",
        "permissions": ["reports.view"],
        "role_permissions": { "admin": ["*"], "employee": [] },
        "navigation": [
            { "id": "daily", "label": "Daily", "component": "erp-reports-daily" },
            {
                "id": "settings",
                "label": "Settings",
                "component": "erp-reports-settings",
                "permission": "reports.view"
            }
        ]
    });
    fs::write(dir.join("module.json"), manifest.to_string()).unwrap();
    dir
}

async fn tab_ids(app: axum::Router, permissions: &str) -> Vec<String> {
    let resp = app
        .oneshot(
            Request::builder()
                .uri("/api/navigation")
                // Dev auth mode reads the actor's permissions from this header.
                .header("x-permissions", permissions)
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    let j: Value = serde_json::from_slice(&bytes).unwrap();
    j["data"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["id"].as_str().unwrap().to_string())
        .collect()
}

/// A scratch dir of this call's own (hub#1607).
///
/// It used to be derived from the process id alone, which is the SAME for every test in the
/// binary: both tests below wiped it with `remove_dir_all` on their way in, so one's delete landed
/// between the other's `create_dir_all` and its `fs::write` and the write died with `NotFound`.
/// That is a red `cargo test --workspace` — the only gate before a merge — on a diff that never
/// touched Rust, which is how a gate stops being read.
fn scratch_dir() -> PathBuf {
    static NEXT: AtomicU32 = AtomicU32::new(0);
    // The pid keeps two `cargo test` processes apart; the counter keeps two tests of THIS one apart.
    std::env::temp_dir().join(format!(
        "erplora-nav-perm-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ))
}

/// hub#1607: two calls must not hand out the same directory.
///
/// Deterministic on purpose: the failure it guards is a race, and asserting on a race is how you
/// get a test that passes on the machine that has the bug.
#[test]
fn hub1607_each_call_gets_its_own_scratch_dir() {
    assert_ne!(
        scratch_dir(),
        scratch_dir(),
        "concurrent tests share this dir and wipe it under each other"
    );
}

async fn hub_with_reports() -> Runtime {
    let tmp = scratch_dir();
    let _ = fs::remove_dir_all(&tmp);
    let dir = write_module(&tmp);
    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&dir).await.unwrap();
    rt
}

#[tokio::test]
async fn a_gated_tab_is_not_served_to_whoever_cannot_open_it() {
    let rt = hub_with_reports().await;
    let app = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    // An employee holds no permission of this module: only the ungated tab reaches them.
    let ids = tab_ids(app, "sales.add_sale").await;

    assert_eq!(
        ids,
        vec!["daily".to_string()],
        "the gated tab must not be offered to someone who would only get a 403 there"
    );
}

#[tokio::test]
async fn the_admin_still_gets_the_gated_tab() {
    let rt = hub_with_reports().await;
    let app = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ));

    let ids = tab_ids(app, "*").await;

    assert_eq!(ids, vec!["daily".to_string(), "settings".to_string()]);
}
