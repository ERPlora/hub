//! hub#2497 — «this is my own copy» is something the HUB proves, not something the file says.
//!
//! The import gives one kind of bundle a wider door than any other: the hub restoring ITS OWN
//! backup. Only that one may bring back the people with their PIN, the business identity in the
//! settings, the fiscal chain, the permissions granted to each app and the automations armed with
//! their permissions (ADR-0195 §3, hub#331, hub#405, hub#473, hub#986). Until this issue the only
//! question asked was whether `manifest.hub.hub_id` equals this hub's id — and that id is public
//! (`GET /api/hub/context` serves it without a session, hub#2510). Anybody could take a backup of
//! their own hub, write somebody else's id into its manifest, and hand it to that business: an
//! administrator importing it gave the file's accounts a PIN into the till.
//!
//! The rule now: a bundle is this hub's own copy only if it carries the hub's **origin seal**, an
//! HMAC over the whole manifest under a key derived from `HUB_SECRETS_KEY` — the per-hub master key
//! that never leaves the deployment's environment. Editing a sealed manifest (the id, or one more
//! permission) breaks the seal, and the bundle is treated like any other hub's file.
use std::collections::BTreeMap;

use erplora_db::testutil::fresh_db;
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection};
use erplora_runtime::import::{
    ignore_reason, import_sections, ImportReport, ImportSelection, SectionStatus,
};
use erplora_runtime::Runtime;

const CREATED_AT: &str = "2026-10-08T10:00:00Z";
const ACTOR: &str = "hub_user:admin";

/// The module that asks for the host's signing certificate.
const VERIFACTU: &str = r#"{
  "id":"verifactu",
  "name":"VeriFactu",
  "version":"1.0.0",
  "capabilities":{"certificate":{"purpose":"fiscal-sign"},"network":{"allow":["https://aeat"]}}
}"#;

/// `HUB_SECRETS_KEY` once for this binary, as every production hub has it (the SaaS generates it
/// per hub and injects it into the container). Every runtime of this process shares it, which is
/// exactly the «same hub, redeployed» situation a real restore is in.
fn ensure_master_key() {
    use base64::Engine as _;
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let key = base64::engine::general_purpose::STANDARD.encode([0x24u8; 32]);
        // SAFETY: `Once` runs this before any test reads the variable, and nothing writes it again.
        unsafe { std::env::set_var("HUB_SECRETS_KEY", key) };
    });
}

async fn runtime(hub_id: &str) -> Runtime {
    ensure_master_key();
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn install(rt: &mut Runtime, manifest: &str) {
    let dir = std::env::temp_dir().join(format!("erplora-seal-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    rt.install_from_dir(&dir).await.expect("the module installs");
    std::fs::remove_dir_all(dir).unwrap();
}

async fn add_person(rt: &Runtime, hub_id: &str, name: &str, role: &str, pin: &str) {
    erplora_runtime::hub_users::create(
        rt.db(),
        &erplora_runtime::Registry::new(),
        hub_id,
        &erplora_runtime::hub_users::NewHubUser {
            name: name.into(),
            role: role.into(),
            pin: pin.into(),
            email: format!("{}@example.com", name.to_lowercase()),
            badge: String::new(),
            local: false,
        },
        0,
    )
    .await
    .unwrap_or_else(|e| panic!("create {name}: {e}"));
}

async fn people(rt: &Runtime, hub_id: &str) -> Vec<String> {
    let mut names: Vec<String> = erplora_runtime::hub_users::list(rt.db(), hub_id)
        .await
        .expect("list people")
        .into_iter()
        .map(|u| u.name)
        .collect();
    names.sort();
    names
}

fn backup_with_people() -> ExportSelection {
    ExportSelection {
        users: true,
        purpose: BundlePurpose::Backup,
        ..Default::default()
    }
}

fn import_people() -> ImportSelection {
    ImportSelection {
        users: true,
        ..Default::default()
    }
}

fn row<'a>(report: &'a ImportReport, section: &str) -> &'a SectionStatus {
    &report
        .sections
        .iter()
        .find(|s| s.section == section)
        .unwrap_or_else(|| panic!("{section} in the report: {:?}", report.sections))
        .status
}

/// 🔴 The attack of the issue. The attacker backs up THEIR OWN hub (two accounts with a PIN they
/// know, one of them `admin`), rewrites `manifest.hub.hub_id` to the victim's public id, and the
/// victim's administrator imports the file. The accounts must not land: the file only CLAIMS to be
/// the victim's copy.
#[tokio::test]
async fn a_file_that_only_names_this_hub_brings_in_no_account_with_a_pin() {
    let attacker = runtime("hub-attacker").await;
    add_person(&attacker, "hub-attacker", "Backdoor", "admin", "4821").await;
    add_person(&attacker, "hub-attacker", "Helper", "manager", "5390").await;
    let mut bundle = export_hub(
        &attacker,
        "hub-attacker",
        &backup_with_people(),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export of the attacker's hub");
    assert!(
        bundle.files.contains_key("data/hub_users.sql"),
        "precondition: the file carries accounts, or this proves nothing"
    );
    // The victim's id is public: `GET /api/hub/context` serves it without a session.
    bundle.manifest.hub.hub_id = "hub-victim".into();

    let mut victim = runtime("hub-victim").await;
    add_person(&victim, "hub-victim", "Owner", "admin", "1357").await;
    let report = import_sections(
        &mut victim,
        &bundle.manifest,
        &bundle.files,
        &import_people(),
        "hub-victim",
    )
    .await
    .expect("the import runs");

    assert_eq!(
        people(&victim, "hub-victim").await,
        vec!["Owner".to_string()],
        "a file that only names this hub handed out accounts with a PIN: {:?}",
        report.sections
    );
    assert_eq!(
        row(&report, "hub_users"),
        &SectionStatus::Ignored(ignore_reason::IDENTITY_NOT_PORTABLE.into()),
    );
}

/// 🟢 The other half, and the one that keeps backups useful: the hub's real backup, restored into
/// the same hub on a fresh database (a redeploy), still brings its people back.
#[tokio::test]
async fn the_hub_s_own_backup_still_brings_its_people_back() {
    let origin = runtime("hub-own").await;
    add_person(&origin, "hub-own", "Lucia", "admin", "4821").await;
    add_person(&origin, "hub-own", "Mario", "employee", "5390").await;
    let bundle = export_hub(
        &origin,
        "hub-own",
        &backup_with_people(),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    let mut restored = runtime("hub-own").await;
    let report = import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &import_people(),
        "hub-own",
    )
    .await
    .expect("the import runs");

    assert_eq!(
        people(&restored, "hub-own").await,
        vec!["Lucia".to_string(), "Mario".to_string()],
        "the hub's own backup lost its people: {:?}",
        report.sections
    );
    assert_eq!(row(&report, "hub_users"), &SectionStatus::Applied);
}

/// 🔴 The seal covers the WHOLE manifest, not only the id: the hub's genuine backup with one
/// permission added by hand (the signing certificate for an app nobody granted it to) is no longer
/// the hub's own copy, so no permission in it is granted.
#[tokio::test]
async fn the_own_backup_edited_to_grant_one_more_permission_grants_none() {
    let mut origin = runtime("hub-edit").await;
    install(&mut origin, VERIFACTU).await;
    erplora_runtime::capabilities::set_grant(
        origin.db(),
        origin.registry(),
        "hub-edit",
        "verifactu",
        "network",
        true,
        ACTOR,
    )
    .await
    .expect("the owner grants the network");
    let mut bundle = export_hub(
        &origin,
        "hub-edit",
        &ExportSelection {
            purpose: BundlePurpose::Backup,
            ..Default::default()
        },
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    assert_eq!(
        bundle.manifest.capability_grants,
        BTreeMap::from([("verifactu".to_string(), vec!["network".to_string()])]),
        "precondition: the backup carries the one grant the owner gave"
    );
    bundle
        .manifest
        .capability_grants
        .get_mut("verifactu")
        .expect("verifactu in the manifest")
        .push("certificate".into());

    let mut restored = runtime("hub-edit").await;
    install(&mut restored, VERIFACTU).await;
    let report = import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "hub-edit",
    )
    .await
    .expect("the import runs");

    let granted = erplora_runtime::capabilities::granted_set(restored.db(), "hub-edit", "verifactu")
        .await
        .expect("read grants");
    assert!(
        granted.is_empty(),
        "an edited backup granted permissions: {granted:?}"
    );
    assert_eq!(
        row(&report, erplora_runtime::export::CAPABILITY_GRANTS_SECTION),
        &SectionStatus::Ignored(ignore_reason::CAPABILITY_GRANTS_NOT_PORTABLE.into()),
    );
}

/// 🔴 The person has to be TOLD. A backup taken before this change (no seal), or one edited
/// afterwards, names this hub and still comes in like another business's file: without staff,
/// permissions or armed automations. The report says so with `origin_unproven`, so the screen can
/// explain why the people did not come back instead of claiming the file is someone else's. A
/// genuine own copy and a file that never named this hub do not raise it.
#[tokio::test]
async fn a_file_that_names_this_hub_without_its_seal_is_reported_as_unproven() {
    let origin = runtime("hub-legacy").await;
    add_person(&origin, "hub-legacy", "Lucia", "admin", "4821").await;
    let sealed = export_hub(
        &origin,
        "hub-legacy",
        &backup_with_people(),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    // The same backup as a hub made it before the seal existed.
    let mut legacy = sealed.manifest.clone();
    legacy.origin_seal = None;

    let mut restored = runtime("hub-legacy").await;
    let report = import_sections(
        &mut restored,
        &legacy,
        &sealed.files,
        &import_people(),
        "hub-legacy",
    )
    .await
    .expect("the import runs");
    assert!(
        report.origin_unproven,
        "a file naming this hub without its seal must be reported as unproven"
    );
    assert_eq!(
        row(&report, "hub_users"),
        &SectionStatus::Ignored(ignore_reason::IDENTITY_NOT_PORTABLE.into()),
    );
    let wire = serde_json::to_value(&report).expect("the report serialises");
    assert_eq!(wire["origin_unproven"], serde_json::json!(true));

    // The genuine copy: proven, so nothing to explain.
    let mut again = runtime("hub-legacy").await;
    let report = import_sections(
        &mut again,
        &sealed.manifest,
        &sealed.files,
        &import_people(),
        "hub-legacy",
    )
    .await
    .expect("the import runs");
    assert!(!report.origin_unproven, "the sealed own copy is proven");
    let wire = serde_json::to_value(&report).expect("the report serialises");
    assert!(
        wire.get("origin_unproven").is_none(),
        "the field only travels when it is true: {wire}"
    );

    // Another business's file never claimed to be this hub's copy: nothing to explain either.
    let mut elsewhere = runtime("hub-other").await;
    let report = import_sections(
        &mut elsewhere,
        &legacy,
        &sealed.files,
        &import_people(),
        "hub-other",
    )
    .await
    .expect("the import runs");
    assert!(!report.origin_unproven, "a foreign file is not «unproven»");
}
