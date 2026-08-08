//! E2E — the fiscal chain does NOT travel across hubs (ADR-0202 §4.2, phase 0) — hub#312.
//!
//! `NumeroInstalacion` = `hub_id`: a bundle restored into a DIFFERENT hub is a different
//! installation before the AEAT, so the origin's `verifactu_record` chain must not be applied
//! there — the next record would chain on a `RegistroAnterior` the AEAT never received for
//! that installation. Restoring a backup into the SAME hub keeps the chain (the same
//! installation resumes its own sequence — that case is pinned here too).

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{export_hub, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection};
use erplora_runtime::Runtime;
use serde_json::json;

const HUB_ORIGIN: &str = "6c9e7a52-0f1b-4b2e-9c1d-2f8a5e3d7b10";
const HUB_OTHER: &str = "a3d94f1c-8e57-4d0a-b6c2-91e0f4728c55";

/// Same resolution as the `require_modules_workspace` guard — it honours `$ERPLORA_MODULES_DIR`.
fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
}

/// Runtime with the real fiscal chain installed: verifactu ← invoice ← sales ← inventory+taxes.
async fn runtime_with_fiscal_chain(hub: &str) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub);
    for m in ["taxes", "inventory", "sales", "invoice", "verifactu"] {
        rt.install_from_dir(&modules_root().join(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    rt
}

/// Seeds one accepted chain record for `hub` (the minimal chain the AEAT already knows about).
async fn insert_chain_record(rt: &Runtime, hub: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub));
    rt.db()
        .execute(
            "INSERT INTO verifactu_record (id, hub_id, record_type, sequence_number, issuer_nif, \
             issuer_name, invoice_number, invoice_date, invoice_type, generation_timestamp, \
             status, aeat_csv, created_at) \
             VALUES ('vr-origin-1', :hub_id, 'alta', 1, 'B12345678', 'Origin SL', 'F-0001', \
             '2026-08-01', 'F2', '2026-08-01T10:00:00+02:00', 'accepted', 'CSV1', \
             '2026-08-01T10:00:00Z')",
            &p,
        )
        .await
        .expect("seed verifactu_record");
}

async fn chain_rows(rt: &Runtime, hub: &str) -> usize {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub));
    rt.db()
        .query("SELECT id FROM verifactu_record WHERE hub_id = :hub_id", &p)
        .await
        .expect("query verifactu_record")
        .rows
        .len()
}

fn verifactu_backup_selection() -> ExportSelection {
    ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection { module_id: "verifactu".into(), with_data: true, tables: None }],
        purpose: Default::default(), // Backup
    }
}

fn import_verifactu() -> ImportSelection {
    ImportSelection {
        users: false,
        settings: false,
        fiscal: false,
        media: false,
        modules: vec!["verifactu".into()],
    }
}

#[tokio::test]
async fn a_backup_restored_into_a_different_hub_does_not_inherit_the_chain() {
    // CI checks out `hub` alone, without the sibling `modules-workspace` these fixtures install
    // from; same guard the other module-backed e2e use.
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let origin = runtime_with_fiscal_chain(HUB_ORIGIN).await;
    insert_chain_record(&origin, HUB_ORIGIN).await;
    let bundle = export_hub(&origin, HUB_ORIGIN, &verifactu_backup_selection(), "backup", "es", "2026-08-05T12:00:00Z")
        .await
        .expect("export origin backup");

    let mut other = runtime_with_fiscal_chain(HUB_OTHER).await;
    let report =
        import_sections(&mut other, &bundle.manifest, &bundle.files, &import_verifactu(), HUB_OTHER)
            .await
            .expect("import into another hub");

    assert_eq!(
        chain_rows(&other, HUB_OTHER).await,
        0,
        "the chain belongs to the origin installation (NumeroInstalacion = hub_id): applying it \
         under another hub would make its next record chain on a RegistroAnterior the AEAT never \
         received for that installation — sections: {:?} · manifest.hub: {:?}",
        report.sections,
        bundle.manifest.hub,
    );
}

#[tokio::test]
async fn a_backup_restored_into_the_same_hub_keeps_the_chain() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let origin = runtime_with_fiscal_chain(HUB_ORIGIN).await;
    insert_chain_record(&origin, HUB_ORIGIN).await;
    let bundle = export_hub(&origin, HUB_ORIGIN, &verifactu_backup_selection(), "backup", "es", "2026-08-05T12:00:00Z")
        .await
        .expect("export origin backup");

    let mut same = runtime_with_fiscal_chain(HUB_ORIGIN).await;
    import_sections(&mut same, &bundle.manifest, &bundle.files, &import_verifactu(), HUB_ORIGIN)
        .await
        .expect("import into the same hub");

    assert_eq!(
        chain_rows(&same, HUB_ORIGIN).await,
        1,
        "the same installation restores its own chain and resumes its sequence"
    );
}
