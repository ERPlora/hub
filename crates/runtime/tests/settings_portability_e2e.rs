//! A bundle does NOT carry the business identity of the hub that produced it (ADR-0195 §4, hub#405).
//!
//! `hub_settings` mixes two things that could not be more different: plain CONFIGURATION (country,
//! currency, language, palette) — which is exactly what a sector template is for — and the fiscal
//! IDENTITY of one business (tax id, legal name, address) plus its security switches. Until now the
//! export dumped the whole table and the import applied it, so importing someone else's backup left
//! this hub holding **another company's tax id**. That is not a cosmetic leak: the dispatcher's
//! fiscal gate (ADR-0203) requires precisely that identity to let a document be issued, so the hub
//! would go on to issue invoices — VeriFactu chain included — under a third party's NIF.
//!
//! Both ends of the rule are pinned here, because either alone is not a control (ADR-0195):
//!  - PRODUCER — a `template` export only takes the configuration keys with it;
//!  - CONSUMER — a bundle from ANOTHER hub can only write configuration keys, whatever it declares
//!    about itself (same criterion as hub#331: the question is not what the bundle is for, it is
//!    whose hub this is).
//!
//! And the half that must not break: a hub restoring its OWN backup gets its identity back
//! (ADR-0113 §1) — a restore that loses the NIF leaves the business unable to invoice.
//!
//! No modules-workspace needed: `hub_settings` exists in every hub (system migration v4).

use std::collections::BTreeMap;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{
    export_hub, BundlePurpose, ExportBundle, ExportSelection, HUB_ID_PLACEHOLDER,
};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::Runtime;
use serde_json::json;

/// The origin business, as a real hub has it: configuration AND fiscal identity in the same table.
const ORIGIN_TAX_ID: &str = "B12345674";
const ORIGIN_LEGAL_NAME: &str = "Bar Pepe SL";
const ORIGIN_ADDRESS: &str = "Calle Mayor 1, Madrid";
const ORIGIN_RECIPIENT: &str = "jefe@barpepe.es";

const CREATED_AT: &str = "2026-08-06T10:00:00Z";

async fn fresh(hub: &str) -> Runtime {
    ensure_master_key();
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub);
    rt.ensure_system_tables().await.expect("system tables");
    rt
}

/// Writes the settings of a hub through the real registry (`set_many` validates every key, so this
/// fixture cannot drift away from what a hub can actually hold).
async fn seed_settings(rt: &Runtime, hub: &str) {
    let updates = json!({
        // Configuration: what a sector template legitimately carries.
        "country_code": "ES",
        "currency": "EUR",
        "language": "es",
        "theme_palette": "ocean",
        // Identity of ONE business + one security switch: none of this may travel.
        "business_tax_id": ORIGIN_TAX_ID,
        "business_legal_name": ORIGIN_LEGAL_NAME,
        "business_address": ORIGIN_ADDRESS,
        "notify_allowed_recipients": ORIGIN_RECIPIENT,
        "api_docs_enabled": true,
    });
    erplora_runtime::settings::set_many(
        rt.db(),
        hub,
        updates.as_object().expect("settings map"),
        "hub_user:owner",
    )
    .await
    .expect("seed the origin hub settings");
}

fn selection(purpose: BundlePurpose) -> ExportSelection {
    ExportSelection {
        settings: true,
        purpose,
        ..Default::default()
    }
}

fn import_settings() -> ImportSelection {
    ImportSelection {
        settings: true,
        ..Default::default()
    }
}

fn settings_sql(bundle: &ExportBundle) -> String {
    String::from_utf8(bundle.files["data/hub_settings.sql"].clone()).expect("utf-8 settings dump")
}

async fn setting_value(rt: &Runtime, hub: &str, key: &str) -> Option<String> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub));
    p.insert("key".into(), json!(key));
    let res = rt
        .db()
        .query(
            "SELECT value FROM hub_settings WHERE hub_id = :hub_id AND key = :key",
            &p,
        )
        .await
        .ok()?;
    res.rows.first()?.get("value")?.as_str().map(str::to_string)
}

/// 🔴 PRODUCER (ADR-0195 §4). A template is a PUBLIC artefact: it takes the configuration of the
/// sector and leaves the business behind. The whitelist lives in the engine, not in the caller —
/// the shell sends `settings_items: null` («all of them»), and a checkbox is not a control.
#[tokio::test]
async fn a_template_carries_configuration_but_never_the_business_identity() {
    let rt = fresh("h1").await;
    seed_settings(&rt, "h1").await;

    let bundle = export_hub(
        &rt,
        "h1",
        &selection(BundlePurpose::Template),
        "restaurante",
        "es",
        CREATED_AT,
    )
    .await
    .expect("template export");
    let sql = settings_sql(&bundle);

    for leaked in [
        ORIGIN_TAX_ID,
        ORIGIN_LEGAL_NAME,
        ORIGIN_ADDRESS,
        ORIGIN_RECIPIENT,
    ] {
        assert!(
            !sql.contains(leaked),
            "a published template must not carry `{leaked}` of the origin business:\n{sql}"
        );
    }
    for key in [
        "business_tax_id",
        "business_legal_name",
        "business_address",
        "notify_allowed_recipients",
        "api_docs_enabled",
    ] {
        assert!(
            !sql.contains(key),
            "the key `{key}` must not be in a template:\n{sql}"
        );
    }

    // …and what a template IS for does travel: the configuration of the sector.
    for key in ["country_code", "currency", "language", "theme_palette"] {
        assert!(
            sql.contains(key),
            "a template must still carry `{key}`:\n{sql}"
        );
    }
    assert!(
        sql.contains(HUB_ID_PLACEHOLDER),
        "the dump must stay portable (placeholder tenant)"
    );
}

/// The mirror, and the half that keeps backups alive (ADR-0113 §1): a BACKUP of this hub takes its
/// own identity with it. A restore that comes back without the tax id leaves the business unable to
/// invoice — and the fiscal gate of the dispatcher (ADR-0203) would refuse every document.
#[tokio::test]
async fn a_backup_still_carries_the_identity_of_its_own_hub() {
    let rt = fresh("h1").await;
    seed_settings(&rt, "h1").await;

    let bundle = export_hub(
        &rt,
        "h1",
        &selection(BundlePurpose::Backup),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("backup export");
    let sql = settings_sql(&bundle);

    assert!(
        sql.contains(ORIGIN_TAX_ID),
        "a backup must keep the hub's own tax id:\n{sql}"
    );
    assert!(
        sql.contains(ORIGIN_LEGAL_NAME),
        "a backup must keep the hub's own legal name:\n{sql}"
    );
}

/// 🔴 CONSUMER — the defence that holds for a file nobody vetted (same plane as hub#331).
///
/// The producer gate above only reaches bundles this runtime produced as templates. The bundle here
/// says «backup» and says it truthfully: it IS hub A's backup, with A's tax id inside. Applied on
/// hub B it would hand B the identity of A, and from that moment B issues documents — and a
/// VeriFactu chain — under A's NIF (ADR-0203 reads exactly these keys to decide it may issue).
#[tokio::test]
async fn a_foreign_bundle_never_writes_the_business_identity() {
    let a = fresh("h1").await;
    seed_settings(&a, "h1").await;
    let bundle = export_hub(
        &a,
        "h1",
        &selection(BundlePurpose::Backup),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");
    assert_eq!(
        bundle.manifest.purpose,
        BundlePurpose::Backup,
        "the bundle must claim to be a backup"
    );
    assert!(
        settings_sql(&bundle).contains(ORIGIN_TAX_ID),
        "the bundle must carry the identity"
    );

    // Destination: ANOTHER hub, brand new — the case that matters, because the idempotence guard
    // only skips a key the destination already has. A hub that never typed its tax id has no row.
    let mut b = fresh("h2").await;
    let report = import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &import_settings(),
        "h2",
    )
    .await
    .expect("import of the foreign bundle");

    // 1. Not one identity key landed.
    for key in [
        "business_tax_id",
        "business_legal_name",
        "business_address",
        "notify_allowed_recipients",
        "api_docs_enabled",
    ] {
        assert_eq!(
            setting_value(&b, "h2", key).await,
            None,
            "a foreign bundle wrote `{key}` into this hub"
        );
    }

    // 2. The configuration DID land: this is a filter, not a rejection.
    assert_eq!(
        setting_value(&b, "h2", "country_code").await.as_deref(),
        Some("ES")
    );
    assert_eq!(
        setting_value(&b, "h2", "currency").await.as_deref(),
        Some("EUR")
    );
    assert_eq!(
        setting_value(&b, "h2", "language").await.as_deref(),
        Some("es")
    );

    // 3. And the report SAYS it, with a stable code and the number of rows kept out (hub#331):
    //    a silent drop is indistinguishable from «I did not tick that box».
    let section = report
        .sections
        .iter()
        .find(|s| s.section == "hub_settings")
        .expect("hub_settings in the report");
    let SectionStatus::PartiallyApplied(reason) = &section.status else {
        panic!(
            "hub_settings had to be reported as partially applied, and came out as {:?}",
            section.status
        );
    };
    assert_eq!(
        reason,
        erplora_runtime::import::ignore_reason::SETTINGS_NOT_PORTABLE
    );
    assert_eq!(
        section.discarded_rows, 5,
        "the report must say HOW MANY settings were kept out: {section:?}"
    );
}

/// The other half: hub A restoring ITS OWN backup gets its identity back untouched (ADR-0113 §1).
/// The rule asks whose hub this is, not what the bundle is for — the same question hub#331 asks.
#[tokio::test]
async fn a_hub_restoring_its_own_backup_gets_its_identity_back() {
    let a = fresh("h1").await;
    seed_settings(&a, "h1").await;
    let bundle = export_hub(
        &a,
        "h1",
        &selection(BundlePurpose::Backup),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");
    assert_eq!(
        bundle.manifest.hub.hub_id, "h1",
        "the bundle must record its origin hub"
    );

    // The same installation, rebuilt from scratch (a redeploy over its own backup).
    let mut b = fresh("h1").await;
    let report = import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &import_settings(),
        "h1",
    )
    .await
    .expect("restore of its own backup");

    let section = report
        .sections
        .iter()
        .find(|s| s.section == "hub_settings")
        .expect("hub_settings in the report");
    assert!(
        matches!(section.status, SectionStatus::Applied),
        "a hub restoring its own backup must get its settings back whole: {:?}",
        section.status
    );
    assert_eq!(
        setting_value(&b, "h1", "business_tax_id").await.as_deref(),
        Some(ORIGIN_TAX_ID)
    );
    assert_eq!(
        setting_value(&b, "h1", "business_legal_name")
            .await
            .as_deref(),
        Some(ORIGIN_LEGAL_NAME)
    );
    assert_eq!(
        setting_value(&b, "h1", "api_docs_enabled").await.as_deref(),
        Some("true")
    );
}

/// A bundle whose settings section is identity and nothing else has nothing left to apply: the
/// whole section is DISCARDED, with its reason and its count — not «Applied» over zero rows, which
/// would read as if the import had done what it was asked.
#[tokio::test]
async fn a_settings_section_that_is_all_identity_is_discarded_whole() {
    let a = fresh("h1").await;
    erplora_runtime::settings::set_many(
        a.db(),
        "h1",
        json!({ "business_tax_id": ORIGIN_TAX_ID, "business_legal_name": ORIGIN_LEGAL_NAME })
            .as_object()
            .expect("settings map"),
        "hub_user:owner",
    )
    .await
    .expect("seed identity-only settings");

    let bundle = export_hub(
        &a,
        "h1",
        &selection(BundlePurpose::Backup),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");

    let mut b = fresh("h2").await;
    let report = import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &import_settings(),
        "h2",
    )
    .await
    .expect("import of the foreign bundle");

    let section = report
        .sections
        .iter()
        .find(|s| s.section == "hub_settings")
        .expect("hub_settings in the report");
    let SectionStatus::Ignored(reason) = &section.status else {
        panic!(
            "an all-identity section had to be discarded whole, and came out as {:?}",
            section.status
        );
    };
    assert_eq!(
        reason,
        erplora_runtime::import::ignore_reason::SETTINGS_NOT_PORTABLE
    );
    assert_eq!(
        section.discarded_rows, 2,
        "the discard must count what it dropped: {section:?}"
    );
    assert_eq!(setting_value(&b, "h2", "business_tax_id").await, None);
}

/// A key nobody has classified is NOT portable. The list is an allowlist on purpose: with a
/// denylist every setting added later leaks until someone remembers to add it — and the import is
/// the one path that can write keys the settings registry itself would reject (raw SQL).
#[tokio::test]
async fn an_unknown_settings_key_from_a_foreign_bundle_is_not_written() {
    let mut b = fresh("h2").await;
    // Hand-made bundle: the shape `export::rows_to_sql` emits, with a key the registry does not know.
    let sql = format!(
        "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\", \"updated_at\", \"updated_by\") \
         SELECT '{HUB_ID_PLACEHOLDER}', 'printer_ip', '192.168.1.50', '{CREATED_AT}', 'system' \
         WHERE NOT EXISTS (SELECT 1 FROM hub_settings WHERE \"key\" = 'printer_ip' AND hub_id = '{HUB_ID_PLACEHOLDER}');\n"
    );
    let mut files: BTreeMap<String, Vec<u8>> = BTreeMap::new();
    files.insert("data/hub_settings.sql".into(), sql.into_bytes());
    let mut sha256 = BTreeMap::new();
    for (path, bytes) in &files {
        sha256.insert(path.clone(), erplora_runtime::export::sha256_hex(bytes));
    }
    let manifest = erplora_runtime::export::BlueprintManifest {
        schema_version: erplora_runtime::export::SCHEMA_VERSION,
        purpose: BundlePurpose::Backup,
        name: "hecho-a-mano".into(),
        locale: "es".into(),
        hub: erplora_runtime::export::HubMeta {
            name: "Bar Pepe".into(),
            country: "ES".into(),
            currency: "EUR".into(),
            hub_id: "h1".into(),
        },
        created_at: CREATED_AT.into(),
        modules: Vec::new(),
        sections: vec!["hub_settings".into()],
        active_roles: Vec::new(),
        capability_grants: Default::default(),
        flows: Vec::new(),
        sha256,
        origin_seal: None,
    };

    import_sections(&mut b, &manifest, &files, &import_settings(), "h2")
        .await
        .expect("import of the hand-made bundle");
    assert_eq!(
        setting_value(&b, "h2", "printer_ip").await,
        None,
        "an unclassified key must not travel between hubs"
    );
}

/// 🔴 hub#1848: a **DEMO** hub restoring its own backup gets its identity back, like any hub.
///
/// The filter used to apply ALWAYS in a demo, because a hand-made bundle claiming to be «this same
/// hub» would have gone around the demo closure of `settings::set_many`. That closure is gone: a
/// demo admin (every PRE hub is one) writes the tax id through Settings, so the import has nothing
/// left to protect and the demo's own backup must not lose what its admin typed.
#[tokio::test]
async fn a_demo_hub_restoring_its_own_backup_gets_its_identity_back() {
    let a = fresh("h1").await;
    seed_settings(&a, "h1").await;
    let bundle = export_hub(
        &a,
        "h1",
        &selection(BundlePurpose::Backup),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");
    assert_eq!(
        bundle.manifest.hub.hub_id, "h1",
        "the bundle claims to be this same hub"
    );

    // The SAME hub_id, and this deployment is a demo.
    let mut demo = fresh("h1").await;
    demo.set_demo_hub(true);
    import_sections(
        &mut demo,
        &bundle.manifest,
        &bundle.files,
        &import_settings(),
        "h1",
    )
    .await
    .expect("restore of its own backup");

    assert_eq!(
        setting_value(&demo, "h1", "business_tax_id").await,
        setting_value(&a, "h1", "business_tax_id").await,
        "a demo restoring its own backup keeps the tax id its admin saved"
    );
    assert!(setting_value(&demo, "h1", "business_tax_id")
        .await
        .is_some());
    assert_eq!(
        setting_value(&demo, "h1", "business_legal_name").await,
        setting_value(&a, "h1", "business_legal_name").await
    );
}

/// A REAL hub restoring its own backup gets its identity back too. A filter written as «always»
/// would leave a business without its tax id after a redeploy.
#[tokio::test]
async fn a_real_hub_restoring_its_own_backup_gets_its_identity_back_too() {
    let a = fresh("h1").await;
    seed_settings(&a, "h1").await;
    let bundle = export_hub(
        &a,
        "h1",
        &selection(BundlePurpose::Backup),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");

    let mut real = fresh("h1").await;
    assert!(!real.is_demo_hub());
    import_sections(
        &mut real,
        &bundle.manifest,
        &bundle.files,
        &import_settings(),
        "h1",
    )
    .await
    .expect("restore of its own backup");
    assert_eq!(
        setting_value(&real, "h1", "business_tax_id")
            .await
            .as_deref(),
        Some(ORIGIN_TAX_ID),
        "a real hub must get its own tax id back after a redeploy"
    );
}

/// `HUB_SECRETS_KEY` once for this binary, as every production hub has it: a hub's own copy is
/// only proven by the origin seal derived from it (hub#2497), so a restore of the hub's own backup
/// needs it at both ends.
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
