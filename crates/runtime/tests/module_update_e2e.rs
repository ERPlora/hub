//! Updating an installed module (hub#516) — and what happens when the update **fails halfway**.
//!
//! Installing over a module that is already installed IS an update: same verified pipeline, and
//! the manifest of the new version replaces the old one in the registry. Two things must hold, and
//! neither did before:
//!
//! 1. **Only the migrations the new version adds run.** `_hub_migrations` dedupes by filename, so
//!    the data written under v1 has to survive untouched.
//! 2. **An update that fails leaves the previous version RUNNING.** This is the one that matters:
//!    a module left half-installed is worse than a module not updated. Before this, `install`
//!    stripped the module from the registry BEFORE migrating, so a migration that blew up left the
//!    hub with no queries, no commands and no navigation for that module until the next restart —
//!    while `hub_module` still claimed it was installed.
//!
//! What is deliberately NOT rolled back is the **schema**: migrations are forward-only and
//! expand-only (ADR-0269 §3.4/§7 — «al revertir no se ejecuta nada sobre el esquema»), and each
//! file is recorded as applied only once it succeeded, so the ones that did land stay and the one
//! that failed is retried on the next attempt.

use std::fs;
use std::path::{Path, PathBuf};

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::Runtime;
use serde_json::json;

/// Writes a module package on disk under `root/<version>/`. Each version is its own directory,
/// exactly like the download cache (`<cache>/<module_id>/<version>/`).
fn write_module(root: &Path, version: &str, manifest: serde_json::Value, files: &[(&str, &str)]) -> PathBuf {
    let dir = root.join(version);
    fs::create_dir_all(&dir).unwrap();
    fs::write(
        dir.join("module.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .unwrap();
    for (rel, body) in files {
        let path = dir.join(rel);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, body).unwrap();
    }
    dir
}

fn scratch(tag: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-upd-{tag}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    dir
}

/// Migrations recorded as applied for `module_id`, in order.
async fn applied(rt: &Runtime, module_id: &str) -> Vec<String> {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    rt.db_for_test()
        .query(
            "SELECT filename FROM _hub_migrations WHERE module_id = :module_id ORDER BY filename",
            &p,
        )
        .await
        .unwrap()
        .rows
        .into_iter()
        .map(|r| r["filename"].as_str().unwrap().to_string())
        .collect()
}

/// The version `hub_module` says this hub is running for `module_id`, or `""` if there is no such
/// row — which includes the table not existing yet, the shape of a hub where nothing ever
/// installed. The assertions below always compare against a concrete version, so a swallowed error
/// cannot make one of them pass by accident.
async fn recorded_version(rt: &Runtime, module_id: &str) -> String {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(rt.hub_id()));
    p.insert("module_id".into(), json!(module_id));
    rt.db_for_test()
        .query(
            "SELECT version FROM hub_module WHERE hub_id = :hub_id AND module_id = :module_id",
            &p,
        )
        .await
        .map(|res| {
            res.rows
                .first()
                .map(|r| r["version"].as_str().unwrap_or_default().to_string())
                .unwrap_or_default()
        })
        .unwrap_or_default()
}

/// v1 of `parts`: one table, one query, one nav entry.
fn v1_manifest() -> serde_json::Value {
    json!({
        "id": "parts",
        "name": "Parts",
        "version": "1.0.0",
        "permissions": ["parts.read"],
        "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
        "queries": {
            "parts.list": { "permission": "parts.read", "sql": "sql/list.sql" }
        },
        "navigation": [
            { "id": "parts", "label": "Parts", "component": "parts-page" }
        ]
    })
}

const V1_INIT: &str = "CREATE TABLE IF NOT EXISTS parts_item (\
    id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL);";
const V1_LIST: &str = "SELECT id, name FROM parts_item WHERE hub_id = :hub_id";

// ── 1. Only the new migrations run, and the data survives ────────────────────────────────

#[tokio::test]
async fn an_update_applies_only_the_migrations_the_new_version_adds() {
    let root = scratch("only-new");
    let v1 = write_module(
        &root,
        "1.0.0",
        v1_manifest(),
        &[
            ("migrations/postgres/001_init.sql", V1_INIT),
            ("sql/list.sql", V1_LIST),
        ],
    );
    let mut v2_manifest = v1_manifest();
    v2_manifest["version"] = json!("2.0.0");
    v2_manifest["migrations"]["postgres"] = json!([
        "migrations/postgres/001_init.sql",
        "migrations/postgres/002_add_note.sql"
    ]);
    let v2 = write_module(
        &root,
        "2.0.0",
        v2_manifest,
        &[
            // Same 001 (already applied → must be skipped) + a genuinely new 002.
            ("migrations/postgres/001_init.sql", V1_INIT),
            (
                "migrations/postgres/002_add_note.sql",
                "ALTER TABLE parts_item ADD COLUMN IF NOT EXISTS note TEXT;",
            ),
            ("sql/list.sql", V1_LIST),
        ],
    );

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&v1).await.expect("install v1");

    // Business data written while v1 was running.
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(rt.hub_id()));
    rt.db_for_test()
        .execute(
            "INSERT INTO parts_item (id, hub_id, name) VALUES ('p1', :hub_id, 'bolt')",
            &p,
        )
        .await
        .unwrap();

    rt.update_from_dir(&v2).await.expect("update to v2");

    assert_eq!(
        applied(&rt, "parts").await,
        [
            "migrations/postgres/001_init.sql",
            "migrations/postgres/002_add_note.sql"
        ],
        "001 was already applied: it must be recorded once, not twice"
    );
    assert_eq!(recorded_version(&rt, "parts").await, "2.0.0");

    // The row written under v1 is still there, and the column the update added is usable.
    let rows = rt
        .db_for_test()
        .query("SELECT id, note FROM parts_item", &Params::new())
        .await
        .unwrap()
        .rows;
    assert_eq!(rows.len(), 1, "v1 data survives the update");
    assert_eq!(rows[0]["id"].as_str(), Some("p1"));

    let _ = fs::remove_dir_all(&root);
}

// ── 2. An update that fails leaves the previous version running ──────────────────────────

/// The heart of hub#516: a module migration that blows up must NOT leave the hub without the
/// module. What was running keeps running, and `hub_module` still points at it.
#[tokio::test]
async fn an_update_that_fails_halfway_leaves_the_previous_version_running() {
    let root = scratch("fails");
    let v1 = write_module(
        &root,
        "1.0.0",
        v1_manifest(),
        &[
            ("migrations/postgres/001_init.sql", V1_INIT),
            ("sql/list.sql", V1_LIST),
        ],
    );
    let mut broken = v1_manifest();
    broken["version"] = json!("2.0.0");
    broken["migrations"]["postgres"] = json!([
        "migrations/postgres/001_init.sql",
        "migrations/postgres/002_broken.sql"
    ]);
    // The new version also renames its nav and drops the query, so restoring the old manifest is
    // observable and not a coincidence.
    broken["navigation"] = json!([{ "id": "parts2", "label": "Parts v2", "component": "parts-page-2" }]);
    broken["queries"] = json!({ "parts.list_v2": { "permission": "parts.read", "sql": "sql/list.sql" } });
    let v2 = write_module(
        &root,
        "2.0.0",
        broken,
        &[
            ("migrations/postgres/001_init.sql", V1_INIT),
            // Passes the guard (expand, own table prefix) but explodes: the table does not exist.
            (
                "migrations/postgres/002_broken.sql",
                "ALTER TABLE parts_missing ADD COLUMN note TEXT;",
            ),
            ("sql/list.sql", V1_LIST),
        ],
    );

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&v1).await.expect("install v1");

    let error = rt.update_from_dir(&v2).await.expect_err("the update must fail");
    assert!(
        !error.to_string().is_empty(),
        "a failed update says why: {error}"
    );

    // The module is still there, still v1, still serving.
    let registry = rt.registry();
    assert!(
        registry.is_installed("parts"),
        "a failed update must never leave the hub WITHOUT the module"
    );
    assert_eq!(
        registry.installed.iter().find(|m| m.id == "parts").map(|m| m.version.as_str()),
        Some("1.0.0"),
        "the previous version keeps running"
    );
    assert!(
        registry.queries.contains_key("parts.list"),
        "v1's query is still registered — the module keeps answering"
    );
    assert!(
        !registry.queries.contains_key("parts.list_v2"),
        "nothing of the version that failed is left behind"
    );
    assert_eq!(
        registry.navigation.iter().filter(|n| n.module_id == "parts").count(),
        1,
        "v1's navigation entry is back, exactly once"
    );
    assert_eq!(
        registry.navigation.iter().find(|n| n.module_id == "parts").map(|n| n.nav.id.as_str()),
        Some("parts"),
        "and it is v1's, not the one the failed version declared"
    );
    assert_eq!(
        recorded_version(&rt, "parts").await,
        "1.0.0",
        "hub_module still points at the version that works"
    );

    let _ = fs::remove_dir_all(&root);
}

/// The schema is NOT rolled back, on purpose (ADR-0269 §3.4/§7): what applied before the failing
/// file stays, and only the file that failed is left to retry. Undoing it would delete data and,
/// for a package already published and signed, is not even executable.
#[tokio::test]
async fn a_failed_update_keeps_the_migrations_that_did_apply_and_retries_only_the_failed_one() {
    let root = scratch("partial-schema");
    let v1 = write_module(
        &root,
        "1.0.0",
        v1_manifest(),
        &[
            ("migrations/postgres/001_init.sql", V1_INIT),
            ("sql/list.sql", V1_LIST),
        ],
    );
    let mut v2m = v1_manifest();
    v2m["version"] = json!("2.0.0");
    v2m["migrations"]["postgres"] = json!([
        "migrations/postgres/001_init.sql",
        "migrations/postgres/002_ok.sql",
        "migrations/postgres/003_broken.sql"
    ]);
    let v2 = write_module(
        &root,
        "2.0.0",
        v2m,
        &[
            ("migrations/postgres/001_init.sql", V1_INIT),
            (
                "migrations/postgres/002_ok.sql",
                "ALTER TABLE parts_item ADD COLUMN IF NOT EXISTS note TEXT;",
            ),
            (
                "migrations/postgres/003_broken.sql",
                "ALTER TABLE parts_missing ADD COLUMN note TEXT;",
            ),
            ("sql/list.sql", V1_LIST),
        ],
    );

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&v1).await.unwrap();
    rt.update_from_dir(&v2).await.expect_err("003 blows up");

    assert_eq!(
        applied(&rt, "parts").await,
        [
            "migrations/postgres/001_init.sql",
            "migrations/postgres/002_ok.sql"
        ],
        "002 landed and stays (expand-only, forward-only); 003 is not recorded, so it is retried"
    );

    let _ = fs::remove_dir_all(&root);
}

// ── 3. A first install that fails still leaves nothing ───────────────────────────────────

/// The restore only puts back what WAS there. A module that never installed must not appear
/// half-registered because of it.
#[tokio::test]
async fn a_first_install_that_fails_leaves_no_module_behind() {
    let root = scratch("first-fails");
    let mut broken = v1_manifest();
    broken["migrations"]["postgres"] = json!(["migrations/postgres/001_broken.sql"]);
    let dir = write_module(
        &root,
        "1.0.0",
        broken,
        &[
            (
                "migrations/postgres/001_broken.sql",
                "ALTER TABLE parts_missing ADD COLUMN note TEXT;",
            ),
            ("sql/list.sql", V1_LIST),
        ],
    );

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&dir).await.expect_err("the install fails");

    assert!(!rt.registry().is_installed("parts"));
    assert!(!rt.registry().queries.contains_key("parts.list"));
    assert_eq!(recorded_version(&rt, "parts").await, "");

    let _ = fs::remove_dir_all(&root);
}
