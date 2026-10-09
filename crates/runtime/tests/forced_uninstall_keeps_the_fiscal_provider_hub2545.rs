//! **hub#2545 — forcing the uninstall of an app takes its dependents with it, so the fiscal-provider
//! lock looks at all of them.**
//!
//! Forcing used to remove only the app the owner clicked and leave its dependents installed on a
//! dependency that no longer existed. Now the dependents go too (Odoo, Business Central), and the
//! provider lock of ADR-0273 D5 has to see the whole set: removing `fbase` from a live hub whose only
//! VeriFactu provider depends on it would leave the hub selling with nobody filing — the same back
//! door `deactivate` already closes for a cascade.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::certificate::CertificateKind;
use erplora_runtime::fiscal_profile::{self, FiscalStatus};
use erplora_runtime::{Runtime, RuntimeError};
use serde_json::json;

const HUB: &str = "hub-es-2545";

fn write_module(id: &str, manifest: serde_json::Value, files: &[(&str, &str)]) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-hub2545-{id}-{}", uuid::Uuid::new_v4()));
    for (path, body) in files {
        let file = dir.join(path);
        std::fs::create_dir_all(file.parent().unwrap()).unwrap();
        std::fs::write(file, body).unwrap();
    }
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest.to_string()).unwrap();
    dir
}

/// A plain app the provider depends on (in production: `invoice` under `verifactu`).
fn base_module() -> PathBuf {
    write_module(
        "fbase",
        json!({ "id": "fbase", "name": "fbase", "version": "1.0.0" }),
        &[],
    )
}

/// The only provider of the hub's regime, with the same shape the lock can see on `verifactu`.
fn provider_module() -> PathBuf {
    write_module(
        "fprov",
        json!({
            "id": "fprov",
            "name": "fprov",
            "version": "1.0.0",
            "depends_on": ["fbase"],
            "fiscal_regime": { "country": "ES", "regime": "verifactu" },
            "capabilities": { "certificate": { "purpose": "fiscal-sign" } },
            "permissions": ["fprov.configure"],
            "queries": {
                "fprov.config.get": {
                    "permission": "fprov.configure",
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": {
                "query": "fprov.config.get",
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": "Configure fprov",
                "route": "/m/fprov/setup",
                "permission": "fprov.configure",
                "order": 60
            }
        }),
        &[("queries/config_get.sql", "SELECT 1 AS ready")],
    )
}

async fn store_own_certificate(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("kind".into(), json!(CertificateKind::Own.as_str()));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, :kind, 'v1:ciphertext', 'v1:ciphertext', '2026-10-07T09:00:00Z', 'x')",
        &p,
    )
    .await
    .expect("the own slot is stored");
}

/// A Spanish hub that went live through the real door, with `fprov` as its only provider.
async fn live_hub() -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    for dir in [base_module(), provider_module()] {
        rt.install_from_dir(&dir).await.expect("install");
        std::fs::remove_dir_all(&dir).ok();
    }
    let mut identity = serde_json::Map::new();
    identity.insert("business_tax_id".into(), json!("B12345674"));
    identity.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    rt.set_settings(&identity, "u1").await.unwrap();
    store_own_certificate(rt.db()).await;
    rt.refresh_fiscal_profile().await.unwrap();
    rt.fiscal_go_live().await.expect("the hub goes live");
    let profile = rt.fiscal_profile().await.unwrap().unwrap();
    assert_eq!(profile.status, FiscalStatus::Active);
    rt
}

fn installed(rt: &Runtime) -> Vec<String> {
    let mut ids: Vec<String> = rt.modules().into_iter().map(|m| m.id).collect();
    ids.sort();
    ids
}

#[tokio::test]
async fn forcing_out_the_app_the_last_provider_depends_on_is_refused() {
    let mut rt = live_hub().await;

    let err = rt
        .uninstall_forced("fbase")
        .await
        .expect_err("`fprov` would leave with it, and it is the only one filing");
    assert!(
        matches!(err, RuntimeError::Domain { ref code, .. } if code == fiscal_profile::NO_PROVIDER_LEFT),
        "expected the provider lock, got {err:?}"
    );
    assert_eq!(
        installed(&rt),
        vec!["fbase", "fprov"],
        "a refused uninstall must not half-apply"
    );
}
