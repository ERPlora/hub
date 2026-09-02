//! hub#473 — the capabilities a hub granted its modules travel in a **backup**, as KEYS.
//!
//! `_module_capability_grants` (system migration v5) is what says which host primitives —
//! `network`, `certificate`, `printer`, `notify` — the owner of the hub let each module use
//! (ADR-0079, «Android-style» permissions, default-deny). The export never carried it, so
//! restoring a backup came back with **every module denied**: VeriFactu could not read the
//! certificate nor reach the AEAT, the reminders could not notify, and nobody was told — the
//! restore looked complete and the hub silently could not work.
//!
//! The fix follows the shape ADR-0242 fixed for the role set (hub#354) and hub#405 for the fiscal
//! identity, and NOT the shape of a data section:
//!
//! - **Declarative keys in the manifest**, never rows of the table. A `data/capabilities.sql`
//!   would have handed any bundle raw INSERTs into the one table that decides what a module may
//!   do with the host's certificate and network.
//! - **Through the granting door** (`capabilities::set_grant`), the same one the administrator's
//!   switch uses, so the bundle gets the same guards a click gets: an unknown capability and one
//!   the installed module does not DECLARE are refused.
//! - **Only the hub restoring its own copy** writes them (`is_same_hub`, the 3rd defense of
//!   ADR-0195). A grant is an approval this deployment's owner gave; a downloaded template
//!   arriving with `certificate` pre-granted would be the marketplace deciding that a module may
//!   use your signing key.
use std::collections::BTreeMap;

use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::export::{
    export_hub, BundlePurpose, ExportSelection, CAPABILITY_GRANTS_SECTION,
};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::Runtime;

/// A module folder with just its `module.json` — enough for the installer.
fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-caps-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

/// The module that needs the host's real primitives: the signing certificate and the network.
const VERIFACTU: &str = r#"{
  "id":"verifactu",
  "name":"VeriFactu",
  "version":"1.0.0",
  "capabilities":{"certificate":{"purpose":"fiscal-sign"},"network":{"allow":["https://aeat"]}}
}"#;

/// A second module, so the export has to keep the grants of each one apart.
const APPOINTMENTS: &str = r#"{
  "id":"appointments",
  "name":"Appointments",
  "version":"1.0.0",
  "capabilities":{"notify":{"channels":["email"]}}
}"#;

const CREATED_AT: &str = "2026-08-15T10:00:00Z";
const ACTOR: &str = "hub_user:admin";

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn install(rt: &mut Runtime, manifest: &str) -> String {
    let dir = fixture(manifest);
    let id = rt
        .install_from_dir(&dir)
        .await
        .expect("the module installs");
    std::fs::remove_dir_all(dir).unwrap();
    id
}

async fn grant(rt: &Runtime, hub_id: &str, module: &str, capability: &str) {
    erplora_runtime::capabilities::set_grant(
        rt.db(),
        rt.registry(),
        hub_id,
        module,
        capability,
        true,
        ACTOR,
    )
    .await
    .expect("the administrator grants the capability");
}

/// What the enforcement door sees: the capabilities live for a module in a hub.
async fn granted(rt: &Runtime, hub_id: &str, module: &str) -> Vec<String> {
    let mut v: Vec<String> = erplora_runtime::capabilities::granted_set(rt.db(), hub_id, module)
        .await
        .expect("read the grants")
        .into_iter()
        .collect();
    v.sort();
    v
}

/// The rows of `_module_capability_grants` themselves, for the assertions about what is WRITTEN.
async fn grant_rows(rt: &Runtime, hub_id: &str) -> Vec<String> {
    let mut p = Params::new();
    p.insert("hub_id".into(), serde_json::json!(hub_id));
    let res = rt
        .db()
        .query(
            "SELECT module_id, capability, granted FROM _module_capability_grants \
             WHERE hub_id = :hub_id ORDER BY module_id, capability",
            &p,
        )
        .await
        .expect("read the grants table");
    res.rows
        .iter()
        .filter_map(|r| {
            Some(format!(
                "{}:{}={}",
                r["module_id"].as_str()?,
                r["capability"].as_str()?,
                r["granted"]
            ))
        })
        .collect()
}

/// The section row the import report carries for the grants, if any.
fn grants_row(
    report: &erplora_runtime::import::ImportReport,
) -> Option<&erplora_runtime::import::SectionResult> {
    report
        .sections
        .iter()
        .find(|s| s.section == CAPABILITY_GRANTS_SECTION)
}

// ── The round trip the issue is about ───────────────────────────────────────────────────

/// 🟢 The trip that names the issue: a hub whose owner granted the certificate and the network to
/// VeriFactu is backed up, redeployed, and restored — and the modules come back **allowed**.
///
/// Before this, `export_hub` never looked at `_module_capability_grants`, so the restore left the
/// table empty and default-deny did the rest: `capabilities::enforce` refused every native handler
/// of the module. The hub looked whole and could not sign an invoice.
#[tokio::test]
async fn a_backup_restores_the_capabilities_the_owner_had_granted() {
    let mut origin = runtime("h1").await;
    install(&mut origin, VERIFACTU).await;
    install(&mut origin, APPOINTMENTS).await;
    grant(&origin, "h1", "verifactu", "certificate").await;
    grant(&origin, "h1", "verifactu", "network").await;
    grant(&origin, "h1", "appointments", "notify").await;

    let selection = ExportSelection {
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "bar-pepe", "es", CREATED_AT)
        .await
        .expect("export");

    assert_eq!(
        bundle.manifest.capability_grants,
        BTreeMap::from([
            ("appointments".to_string(), vec!["notify".to_string()]),
            (
                "verifactu".to_string(),
                vec!["certificate".to_string(), "network".to_string()]
            ),
        ]),
        "the backup carries WHAT was granted to WHOM, per module — or there is nothing to restore"
    );
    assert!(
        bundle
            .manifest
            .sections
            .contains(&CAPABILITY_GRANTS_SECTION.to_string()),
        "the inventory the user confirms before importing has to show the bundle brings grants"
    );
    assert!(
        !bundle.files.keys().any(|p| p.contains("capabilit")),
        "grants are KEYS in the manifest, never a `data/*.sql`: no bundle gets raw INSERTs into \
         the table that decides what a module may do with the certificate"
    );

    // The new deployment: same hub id (it IS this hub coming back), same modules, nothing granted.
    let mut restored = runtime("h1").await;
    install(&mut restored, VERIFACTU).await;
    install(&mut restored, APPOINTMENTS).await;
    assert!(
        grant_rows(&restored, "h1").await.is_empty(),
        "precondition: a fresh deployment starts default-deny"
    );

    let report = import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("the backup is accepted");

    assert_eq!(
        granted(&restored, "h1", "verifactu").await,
        vec!["certificate", "network"]
    );
    assert_eq!(
        granted(&restored, "h1", "appointments").await,
        vec!["notify"]
    );
    // Proven at the door that actually enforces it, not on a helper: `enforce` is what the
    // dispatcher calls before a native handler runs.
    erplora_runtime::capabilities::enforce(restored.db(), restored.registry(), "verifactu", "h1")
        .await
        .expect("after the restore the module can sign again");
    assert!(
        matches!(
            grants_row(&report).map(|r| &r.status),
            Some(SectionStatus::Applied)
        ),
        "the report says what it did with the grants: {:?}",
        report.sections
    );
}

/// 🔴 A capability the installed module does **not declare** is refused, even in the hub's own
/// backup: the manifest of the module that is installed HERE is the authority, not the file.
///
/// It is the case a module update creates — v2 dropped `network` — and the case a hand-edited zip
/// creates. Same guard `set_grant` applies to the administrator's switch, reached through the same
/// door; and it must leave **no latent row**, or reinstalling the old version would find the
/// capability already granted by a file instead of by a person.
#[tokio::test]
async fn a_capability_the_installed_module_does_not_declare_is_refused_and_leaves_no_row() {
    let mut origin = runtime("h1").await;
    install(&mut origin, VERIFACTU).await;
    grant(&origin, "h1", "verifactu", "certificate").await;
    grant(&origin, "h1", "verifactu", "network").await;
    let mut bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    // …and the bundle also claims a capability nobody ever declared.
    bundle
        .manifest
        .capability_grants
        .get_mut("verifactu")
        .expect("the module is in the manifest")
        .push("printer".into());

    // The destination runs a NEWER VeriFactu that no longer asks for the network.
    let mut restored = runtime("h1").await;
    install(
        &mut restored,
        r#"{"id":"verifactu","name":"VeriFactu","version":"2.0.0",
            "capabilities":{"certificate":{"purpose":"fiscal-sign"}}}"#,
    )
    .await;

    let report = import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("a refused key is not a reason to refuse the whole restore");

    assert_eq!(
        granted(&restored, "h1", "verifactu").await,
        vec!["certificate"],
        "what the module still declares is granted; what it dropped is not"
    );
    assert_eq!(
        grant_rows(&restored, "h1").await,
        vec!["verifactu:certificate=1".to_string()],
        "no dormant row may wait for a capability nobody declares"
    );
    let row = grants_row(&report).expect("the report has a row for the grants");
    assert!(
        matches!(row.status, SectionStatus::PartiallyApplied(_)),
        "part of it landed, so the report says exactly that: {:?}",
        row.status
    );
    assert_eq!(
        row.discarded_rows, 2,
        "`network` and `printer` were left out, and they are counted"
    );
}

/// 🔴 A backup restored where the module is **not installed** grants nothing and parks nothing.
/// A dormant row would mean that installing that module later found its access to the certificate
/// already approved — by a file, at a moment nobody could review.
#[tokio::test]
async fn a_backup_whose_module_is_missing_grants_nothing_and_leaves_no_latent_row() {
    let mut origin = runtime("h1").await;
    install(&mut origin, VERIFACTU).await;
    grant(&origin, "h1", "verifactu", "certificate").await;
    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    let mut bare = runtime("h1").await; // same hub, but the module never got installed
    let report = import_sections(
        &mut bare,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("a missing module is not a reason to refuse the whole restore");

    assert!(
        grant_rows(&bare, "h1").await.is_empty(),
        "nothing is granted and nothing is parked for a module that is not here"
    );
    assert!(
        matches!(
            grants_row(&report).map(|r| &r.status),
            Some(SectionStatus::Ignored(_))
        ),
        "none of it landed: {:?}",
        report.sections
    );
}

// ── The security half: a bundle that is not ours cannot grant anything ──────────────────

/// 🔴 The defense the issue asks for by name: a bundle produced by **another hub** cannot grant a
/// capability here, however well-formed it is. `certificate` and `network` are the host primitives
/// of THIS deployment; a downloaded blueprint pre-granting them would be a file deciding that a
/// module may use your signing key and call out to the internet — with nobody having pressed
/// anything.
///
/// Same criterion, and the same `is_same_hub`, as the identities of ADR-0195 §3: the rule does not
/// ask what the bundle claims to be, it asks whose hub this is.
#[tokio::test]
async fn a_bundle_from_another_hub_grants_nothing() {
    let mut rt = runtime("h1").await;
    install(&mut rt, VERIFACTU).await;
    let mut foreign = export_hub(
        &rt,
        "h1",
        &ExportSelection::default(),
        "otro",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    foreign.manifest.hub.hub_id = "some-other-hub".into();
    foreign.manifest.capability_grants =
        BTreeMap::from([("verifactu".to_string(), vec!["certificate".to_string()])]);
    foreign
        .manifest
        .sections
        .push(CAPABILITY_GRANTS_SECTION.to_string());

    let report = import_sections(
        &mut rt,
        &foreign.manifest,
        &foreign.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("the bundle is accepted, its grants are not");

    assert!(
        grant_rows(&rt, "h1").await.is_empty(),
        "not one grant lands from a bundle that is not this hub's own copy"
    );
    assert!(
        erplora_runtime::capabilities::enforce(rt.db(), rt.registry(), "verifactu", "h1")
            .await
            .is_err(),
        "default-deny still holds: the module cannot touch the certificate"
    );
    let row = grants_row(&report).expect("the report tells the user the grants were discarded");
    assert!(
        matches!(&row.status, SectionStatus::Ignored(reason)
            if reason == erplora_runtime::import::ignore_reason::CAPABILITY_GRANTS_NOT_PORTABLE),
        "with the stable reason code the shell translates: {:?}",
        row.status
    );
    assert_eq!(
        row.discarded_rows, 1,
        "«1 permiso descartado» is what makes the row actionable"
    );
}

/// 🔴 An **unknown origin** never matches, exactly as it does not for identities: a bundle older
/// than `hub.hub_id` carries it empty, and letting «unknown == unknown» count as the same hub would
/// mean that simply omitting the field is how you grant yourself the certificate.
#[tokio::test]
async fn a_bundle_of_unknown_origin_grants_nothing() {
    let mut rt = runtime("h1").await;
    install(&mut rt, VERIFACTU).await;
    let mut old = export_hub(
        &rt,
        "h1",
        &ExportSelection::default(),
        "viejo",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    old.manifest.hub.hub_id = String::new();
    old.manifest.capability_grants =
        BTreeMap::from([("verifactu".to_string(), vec!["certificate".to_string()])]);

    import_sections(
        &mut rt,
        &old.manifest,
        &old.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("accepted");

    assert!(
        grant_rows(&rt, "h1").await.is_empty(),
        "unknown origin is not this hub"
    );
}

/// 🔴 A **template** is a public artefact and does not carry the grants of the hub that produced
/// it — the producer gate, the other end of the defense above. Grants are not vocabulary of a
/// business (which is why the role set travels in both purposes, ADR-0242 §8): they are the
/// security decisions of ONE deployment's owner about the host's own primitives.
#[tokio::test]
async fn a_template_carries_no_grants_at_all() {
    let mut rt = runtime("h1").await;
    install(&mut rt, VERIFACTU).await;
    grant(&rt, "h1", "verifactu", "certificate").await;

    let selection = ExportSelection {
        purpose: BundlePurpose::Template,
        ..Default::default()
    };
    let bundle = export_hub(&rt, "h1", &selection, "restaurante", "es", CREATED_AT)
        .await
        .expect("export");

    assert!(
        bundle.manifest.capability_grants.is_empty(),
        "the grants do not enter the zip: not filtered on import, not there at all"
    );
    assert!(!bundle
        .manifest
        .sections
        .contains(&CAPABILITY_GRANTS_SECTION.to_string()));
}

// ── Shape of what travels ───────────────────────────────────────────────────────────────

/// 🔴 A **revoked** grant is not carried: `granted = 0` is the default state of a hub that never
/// answered, so exporting it would add a row that says nothing and re-granting it would be a
/// no-op. What travels is what was ALLOWED.
#[tokio::test]
async fn a_revoked_grant_does_not_travel() {
    let mut rt = runtime("h1").await;
    install(&mut rt, VERIFACTU).await;
    grant(&rt, "h1", "verifactu", "certificate").await;
    erplora_runtime::capabilities::set_grant(
        rt.db(),
        rt.registry(),
        "h1",
        "verifactu",
        "network",
        false,
        ACTOR,
    )
    .await
    .expect("the owner says no to the network");

    let bundle = export_hub(
        &rt,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    assert_eq!(
        bundle.manifest.capability_grants,
        BTreeMap::from([("verifactu".to_string(), vec!["certificate".to_string()])]),
        "only what was granted travels; a `no` is the default and needs no row"
    );
}

/// 🔴 Tenant isolation — the #1 risk of this engine: the database is SHARED (`tenancy.md`), so an
/// export that forgot its `WHERE hub_id` would put the grants of the hub next door inside this
/// hub's backup, and restoring it would hand another business's approvals to these modules.
#[tokio::test]
async fn the_export_carries_only_the_grants_of_its_own_hub() {
    let mut rt = runtime("h1").await;
    install(&mut rt, VERIFACTU).await;
    install(&mut rt, APPOINTMENTS).await;
    grant(&rt, "h1", "verifactu", "certificate").await;
    // The neighbour lives in the SAME database, one row apart, and granted something else.
    grant(&rt, "h2", "appointments", "notify").await;

    let bundle = export_hub(
        &rt,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    assert_eq!(
        bundle.manifest.capability_grants,
        BTreeMap::from([("verifactu".to_string(), vec!["certificate".to_string()])]),
        "the neighbour's grant is not this hub's to export"
    );
}

/// 🔴 The restore is **additive**: a capability this hub already had granted and the bundle does
/// not name stays granted. Mirroring the bundle exactly would let a file REVOKE — a restore of an
/// older backup would silently switch off a permission the owner granted afterwards, and the module
/// would stop working with nobody having decided that.
#[tokio::test]
async fn restoring_never_revokes_what_the_bundle_does_not_name() {
    let mut origin = runtime("h1").await;
    install(&mut origin, VERIFACTU).await;
    grant(&origin, "h1", "verifactu", "certificate").await;
    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    // The hub granted the network AFTER that backup was taken.
    let mut rt = runtime("h1").await;
    install(&mut rt, VERIFACTU).await;
    grant(&rt, "h1", "verifactu", "network").await;

    import_sections(
        &mut rt,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("accepted");

    assert_eq!(
        granted(&rt, "h1", "verifactu").await,
        vec!["certificate", "network"],
        "an old backup adds what it brings; it does not take away what came later"
    );
}
