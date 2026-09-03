//! hub#1435 — **the `delegated` certificate slot is RETIRED**, and this file is the proof that no
//! door is left (ADR-0320 point 8; the SaaS half is `test_delegated_certificate_retired.py`).
//!
//! The slot held ERPlora's `.p12`, handed down by the control plane over
//! `GET /api/v1/hub/device/fiscal/certificate/` so that ERPlora could sign before the AEAT on a
//! hub's behalf (ADR-0202 §2). ADR-0320 replaced that with the fiscal cell: the Hub builds the XML
//! and a central gateway transmits it, and **no private key of ERPlora's ever reaches the fleet
//! again**. The SaaS shut its half in saas#1435 phase 2 — the model, the endpoint, the four
//! `reported_cert_*` columns and the expiry task are gone — so everything the hub still had for it
//! (the fetch, the three refetch triggers, the TLS signal, the slot itself) was asking a door that
//! no longer answers.
//!
//! # 🔒 The canary: the delegated ROUTE is NOT the delegated SLOT
//!
//! Two things share the word and only one of them is being retired. [`ROUTE_DELEGATED`] is the
//! **transmission route** — «ERPlora files on behalf of the taxpayer, with its Seal, through the
//! cell» — and it is the route ADR-0320 puts every hub without an own certificate on. It is the
//! live one. [`CertificateKind::Delegated`] was the **slot** that used to hold the key that route
//! needed back when the key travelled. Retiring the slot must leave the route exactly where it is,
//! so the last test here fails loudly if a future cleanup takes both.

use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::certificate::{self, CertificateKind};
use erplora_runtime::Runtime;
use serde_json::json;

/// The bytes a hub deployed before this retirement may still be holding in its `delegated` row.
const DELEGATED_B64: &str = "REVMRUdBVEVE";

/// A hub with its system schema applied — the same door a real boot goes through, so the retirement
/// is exercised where it actually runs and not against a hand-built table.
async fn booted_hub(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn plant_row(db: &dyn DatabaseAdapter, hub_id: &str, kind: &str, b64: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(kind));
    p.insert("b64".into(), json!(b64));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, :kind, :b64, 'pw', '2026-01-01T00:00:00Z', 'cloud')",
        &p,
    )
    .await
    .unwrap();
}

/// The version of the migration under test, read from the catalogue by NAME so a renumbering
/// cannot make this file quietly stop testing anything.
async fn retirement_version(db: &dyn DatabaseAdapter) -> i64 {
    let res = db
        .query(
            "SELECT version FROM _hub_system_migrations \
             WHERE name = 'retire_delegated_certificate_slot'",
            &Params::new(),
        )
        .await
        .unwrap();
    res.rows
        .first()
        .and_then(|r| r.get("version").and_then(|v| v.as_i64()))
        .expect("the retirement is in the catalogue and was applied at boot")
}

async fn retirement_is_registered(db: &dyn DatabaseAdapter) -> bool {
    let res = db
        .query(
            "SELECT version FROM _hub_system_migrations \
             WHERE name = 'retire_delegated_certificate_slot'",
            &Params::new(),
        )
        .await
        .unwrap();
    !res.rows.is_empty()
}

/// Rewinds this hub to the state of one that was deployed BEFORE the retirement.
async fn unapply_the_retirement(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("version".into(), json!(retirement_version(db).await));
    db.execute(
        "DELETE FROM _hub_system_migrations WHERE version = :version",
        &p,
    )
    .await
    .unwrap();
}

async fn kinds_held(db: &dyn DatabaseAdapter, hub_id: &str) -> Vec<String> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT kind FROM _hub_certificate WHERE hub_id = :hub_id ORDER BY kind",
            &p,
        )
        .await
        .unwrap();
    res.rows
        .iter()
        .filter_map(|r| r.get("kind").and_then(|v| v.as_str()).map(str::to_owned))
        .collect()
}

/// One slot left. `SLOTS` is what `active_kind`, `status` and `exportable_der_bytes` all walk, so
/// the length is the whole selection rule: with two entries there was a fallback, with one there
/// is only the certificate the business uploaded.
#[test]
fn the_core_knows_exactly_one_certificate_slot() {
    assert_eq!(
        certificate::SLOTS.as_slice(),
        [CertificateKind::Own].as_slice(),
        "the delegated slot is retired: only the business's own certificate is held here"
    );
}

/// 🔴 **The key does not linger.** A hub that was handed ERPlora's `.p12` before the retirement has
/// those bytes sitting encrypted in its own database — somebody else's private key, on a machine
/// that has no reason to hold it and no code left that reads it. Retiring the slot without deleting
/// the row would leave the fleet's worst secret parked in every one of them.
#[tokio::test]
async fn the_migration_deletes_the_delegated_key_a_hub_may_still_be_holding() {
    let rt = booted_hub("hub-test").await;
    let db = rt.db();

    // A hub that was ALREADY RUNNING when this landed: its schema is one version behind, and it is
    // holding the key. Un-registering the retirement is what makes this fixture that hub — applying
    // the catalogue to a hub that has already run it would skip the migration and prove nothing.
    unapply_the_retirement(db).await;
    plant_row(db, "hub-test", "delegated", DELEGATED_B64).await;
    plant_row(db, "hub-test", "own", "T1dO").await;
    assert_eq!(
        kinds_held(db, "hub-test").await,
        vec!["delegated".to_string(), "own".to_string()],
        "the fixture has to plant both, or the test cannot tell a deletion from an empty table"
    );

    // The redeploy.
    erplora_runtime::system_migrations::apply(db, "hub-test")
        .await
        .unwrap();

    assert_eq!(
        kinds_held(db, "hub-test").await,
        vec!["own".to_string()],
        "the delegated row is deleted and the business's own certificate is untouched"
    );
    assert!(
        retirement_is_registered(db).await,
        "and it is recorded as applied, so the next boot does not redo it"
    );

    // Idempotent: a hub that reboots does not re-run it, and re-running it would be harmless.
    erplora_runtime::system_migrations::apply(db, "hub-test")
        .await
        .unwrap();
    assert_eq!(kinds_held(db, "hub-test").await, vec!["own".to_string()]);
}

/// The screen (`GET /api/business/certificate`) stops offering a slot nothing can fill.
#[tokio::test]
async fn the_certificate_status_no_longer_names_a_delegated_slot() {
    let rt = booted_hub("hub-test").await;

    let status = certificate::status(rt.db(), "hub-test").await.unwrap();
    let slots = status["slots"].as_object().expect("`slots` is an object");
    assert!(
        slots.contains_key("own"),
        "the own slot is what this screen has always described"
    );
    assert!(
        !slots.contains_key("delegated"),
        "a slot that nothing can fill is not offered: {slots:?}"
    );
}

/// 🔒 **The canary of this issue.** `delegated` as a ROUTE is ADR-0320's live path — the hub with no
/// own certificate files through the fiscal cell — and it must survive the slot that shares its
/// name. Deleting both is the regression this file exists to catch: it would put every hub without
/// a `.p12` on the `own` route, i.e. tell the screen to demand a certificate the business does not
/// have and the go-live to skip the Anexo I that the cell actually requires.
#[tokio::test]
async fn the_delegated_route_survives_the_delegated_slot() {
    assert_eq!(
        certificate::route_of(None),
        certificate::ROUTE_DELEGATED,
        "no certificate = the cell files on the taxpayer's behalf (ADR-0320 §1)"
    );
    assert_eq!(
        certificate::route_of(Some(CertificateKind::Own)),
        certificate::ROUTE_OWN,
        "an own certificate = direct mTLS, nothing delegated to anybody"
    );

    let rt = booted_hub("hub-test").await;
    assert_eq!(
        certificate::transmission_route(rt.db(), "hub-test")
            .await
            .unwrap(),
        certificate::ROUTE_DELEGATED,
        "a hub holding nothing is on the cell's route, exactly as before this retirement"
    );
}

// ── The mechanical guard: the door does not come back ─────────────────────────────────────────
//
// The compiler already refuses the retired SYMBOLS — they do not exist any more. What it cannot
// see is somebody writing the path again, which is how this door would return: a `.header(...)` on
// a fresh `reqwest` builder pointed at `/api/v1/hub/device/fiscal/certificate/` compiles perfectly
// and hands ERPlora's private key back to the fleet. That URL answers 404 on every SaaS since
// saas#1435 phase 2, so naming it in production code is always a mistake — which is what makes it
// a guard and not a style rule.

use std::fs;
use std::path::{Path, PathBuf};

/// The control-plane door that distributed ERPlora's `.p12`, retired on both sides.
///
/// The machine path, not the bare words: `data/fiscal/certificate.p12` is a file INSIDE an export
/// bundle (`export_import.rs`) and has nothing to do with this door. A guard that cannot tell them
/// apart is one somebody silences.
const RETIRED_DOOR: &str = "hub/device/fiscal/certificate";

fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// Every `.rs` under `crates/` that is PRODUCTION code: `src/`, minus the `tests/` directories.
/// Naming a retired door to talk about it — here, or in a comment — is not opening it.
fn production_sources(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if path.is_dir() {
            if name != "tests" && name != "target" && name != "node_modules" {
                production_sources(&path, out);
            }
        } else if name.ends_with(".rs") {
            out.push(path);
        }
    }
}

/// Production lines that NAME the door: the path outside a comment. A `//` line mentioning it is
/// documentation of a retirement, which is the opposite of reopening it.
fn lines_naming_the_door(text: &str) -> Vec<(usize, String)> {
    let mut hits = Vec::new();
    let mut in_test = false;
    for (n, line) in text.lines().enumerate() {
        let trimmed = line.trim_start();
        if trimmed == "#[cfg(test)]" {
            in_test = true;
            continue;
        }
        if in_test {
            if line == "}" {
                in_test = false;
            }
            continue;
        }
        if trimmed.starts_with("//") {
            continue;
        }
        if line.contains(RETIRED_DOOR) {
            hits.push((n + 1, line.trim().to_string()));
        }
    }
    hits
}

/// 🔒 Nothing in production asks the control plane for a fiscal certificate any more.
#[test]
fn no_production_code_reopens_the_retired_certificate_door() {
    // Positive control FIRST: a guard that cannot see the thing it forbids is a green light with
    // no lamp behind it. Eight convincing false negatives in one day is why this line is here.
    let planted = "        let url = format!(\"{base}/api/v1/hub/device/fiscal/certificate/\");";
    assert_eq!(
        lines_naming_the_door(planted).len(),
        1,
        "the guard must catch the door it forbids before its silence means anything"
    );
    assert!(
        lines_naming_the_door("// the hub/device/fiscal/certificate door is retired (hub#1435)")
            .is_empty(),
        "naming the retired door in a comment is documentation, not a door"
    );
    assert!(
        lines_naming_the_door("let path = \"data/fiscal/certificate.p12\".to_string();").is_empty(),
        "a file inside an export bundle is not the control plane's door"
    );

    let root = workspace_root().join("crates");
    let mut sources = Vec::new();
    production_sources(&root, &mut sources);
    assert!(
        sources.len() > 50,
        "the walk found {} files: it is not reading the tree",
        sources.len()
    );

    let mut offenders = Vec::new();
    for path in &sources {
        let text = fs::read_to_string(path).unwrap_or_default();
        for (line, code) in lines_naming_the_door(&text) {
            let shown = path.strip_prefix(workspace_root()).unwrap_or(path);
            offenders.push(format!("{}:{line}: {code}", shown.display()));
        }
    }
    assert!(
        offenders.is_empty(),
        "the delegated-certificate door is retired on both sides (saas#1435 phase 2): it answers \
         404 and no hub may ask for it again — {offenders:#?}"
    );
}
