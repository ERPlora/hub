//! **A bundle NEVER writes the hub's fiscal profile** — ADR-0273 D8 (hub#560).
//!
//! ADR-0252 drew the frontier of `purpose` with precision when it decided that the role set DOES
//! travel: *«what `purpose` separates is who you are (tax id, accounts, certificate), not what you
//! call the posts on your staff»*. The fiscal profile sits on the «who you are» side — the taxpayer
//! id the emitted chain is anchored to, the `system_id` of the installation, the stamp of the first
//! record sent to the tax authority.
//!
//! A bundle able to write it could declare a hub **already live**, or hand it another
//! installation's `system_id`: adopting somebody else's installation by the back door, which
//! hub#558 makes a deliberate act with a trace.
//!
//! Until now the frontier held only **by construction** — no module is called `_hub…`, so
//! `export::table_owner` never handed a system table to a module and the import never built a scope
//! that reached one. «It does not happen by accident» is not «it cannot happen», and nothing in the
//! code said so. This test is the rule written down.
//!
//! Note how it is asked: the profile is seeded **live and left in place** while the import runs, and
//! the assertion is that it did not move. Pulling the row out first and checking nothing appeared
//! would prove nothing at all.

use std::collections::BTreeMap;

use erplora_db::{DatabaseAdapter, Params, testutil::fresh_db};
use erplora_runtime::export::{
    BlueprintManifest, BundlePurpose, HubMeta, ManifestModule, HUB_ID_PLACEHOLDER, SCHEMA_VERSION,
    sha256_hex,
};
use erplora_runtime::fiscal_profile::{self, FiscalStatus};
use erplora_runtime::import::{ImportSelection, SectionStatus, ignore_reason, import_sections};
use erplora_runtime::Runtime;
use serde_json::json;

/// The hub that produced the tampered bundle…
const ORIGIN: &str = "h1";
/// …and the one that imports it, with a fiscal chain of its own already running.
const TARGET: &str = "h2";

/// Turns the destination hub into one that HAS gone live: it emits in production, under its own
/// tax id, with a first record already sent. This is the state the rule protects — and it is alive
/// during the whole import.
async fn go_live(db: &dyn DatabaseAdapter, hub_id: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    db.execute(
        "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = 'production', \
           taxpayer_id = 'B12345678', activated_at = '2026-08-01T09:00:00Z', \
           first_record_at = '2026-08-01T09:05:00Z' WHERE hub_id = :hub_id",
        &p,
    )
    .await
    .expect("go live");
}

/// A bundle from ANOTHER hub that tries to write the destination's fiscal identity, in the two
/// shapes a hand-made zip has available:
///
/// 1. a section that names the system table outright (`_hub_fiscal_profile`);
/// 2. a section disguised as a MODULE whose id is the system prefix (`modules/_hub`) — the shape
///    that matters, because `TableScope::Module("_hub")` reaches `_hub_*` by the very same prefix
///    rule the export uses to decide what a module owns.
///
/// It also carries one legitimate `hub_settings` row, so the test can tell «the bundle was refused»
/// from «the import blew up»: the rule is that the profile is ignored, not that the import dies.
fn tampered_bundle() -> (BlueprintManifest, BTreeMap<String, Vec<u8>>) {
    let mut files: BTreeMap<String, Vec<u8>> = BTreeMap::new();

    files.insert(
        "data/hub_settings.sql".into(),
        format!(
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\", \"updated_at\") \
             SELECT '{HUB_ID_PLACEHOLDER}', 'theme_palette', 'ocean', '2026-08-08T00:00:00Z' \
             WHERE NOT EXISTS (SELECT 1 FROM hub_settings WHERE \"key\" = 'theme_palette' \
               AND hub_id = '{HUB_ID_PLACEHOLDER}');\n"
        )
        .into_bytes(),
    );
    // «This hub is already live, under my tax id, and it is my installation.»
    files.insert(
        "data/_hub_fiscal_profile.sql".into(),
        format!(
            "INSERT INTO _hub_fiscal_profile (\"hub_id\", \"country_code\", \"taxpayer_id\", \
               \"fiscal_system\", \"status\", \"environment\", \"system_id\") \
             SELECT '{HUB_ID_PLACEHOLDER}', 'ES', 'B99999999', 'verifactu', 'ACTIVE', \
               'production', 'somebody-elses-installation';\n"
        )
        .into_bytes(),
    );
    // The same write, plus «Spain owes nothing» in the regime registry — one row there and a
    // Spanish hub stops owing VeriFactu on its next boot.
    files.insert(
        "data/_hub.sql".into(),
        format!(
            "INSERT INTO _hub_fiscal_profile (\"hub_id\", \"country_code\", \"taxpayer_id\", \
               \"fiscal_system\", \"status\", \"environment\", \"system_id\") \
             SELECT '{HUB_ID_PLACEHOLDER}', 'ES', 'B99999999', 'verifactu', 'ACTIVE', \
               'production', 'somebody-elses-installation';\n\
             INSERT INTO _hub_fiscal_regime_registry (\"country_code\", \"regime_key\", \"since\") \
             SELECT 'ES', '', '2020-01-01';\n"
        )
        .into_bytes(),
    );

    let sha256 = files.iter().map(|(p, b)| (p.clone(), sha256_hex(b))).collect();
    let manifest = BlueprintManifest {
        schema_version: SCHEMA_VERSION,
        // `backup` on purpose: the permissive end of `purpose`. If not even a backup of ANOTHER
        // hub may write this, no bundle may.
        purpose: BundlePurpose::Backup,
        name: "restaurante".into(),
        locale: "es".into(),
        hub: HubMeta {
            name: "Bar Pepe".into(),
            country: "ES".into(),
            currency: "EUR".into(),
            hub_id: ORIGIN.into(),
        },
        created_at: "2026-08-08T00:00:00Z".into(),
        modules: vec![ManifestModule { id: "_hub".into(), version: "1.0.0".into(), with_data: true }],
        sections: vec![
            "hub_settings".into(),
            "_hub_fiscal_profile".into(),
            "modules/_hub".into(),
        ],
        active_roles: Vec::new(),
        capability_grants: Default::default(),
        sha256,
    };
    (manifest, files)
}

/// Everything ticked — a checkbox is not a control (ADR-0195), so the rule has to hold with the
/// form asking for all of it.
fn import_everything() -> ImportSelection {
    ImportSelection {
        users: true,
        settings: true,
        fiscal: true,
        media: true,
        modules: vec!["_hub".into(), "_hub_fiscal_profile".into()],
    }
}

#[tokio::test]
async fn a_bundle_from_another_hub_never_touches_the_fiscal_profile() {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), TARGET);
    rt.ensure_system_tables().await.expect("boot");
    go_live(rt.db(), TARGET).await;
    let before = fiscal_profile::load(rt.db(), TARGET).await.unwrap().expect("a live profile");

    let (manifest, files) = tampered_bundle();
    let report = import_sections(&mut rt, &manifest, &files, &import_everything(), TARGET)
        .await
        .expect("a bundle that oversteps is refused section by section, it does not kill the import");

    // ── The profile did not move. Not one field. ─────────────────────────────
    let after = fiscal_profile::load(rt.db(), TARGET).await.unwrap().expect("the profile survives");
    assert_eq!(after, before, "no bundle writes the hub's fiscal profile");
    assert_eq!(after.taxpayer_id, "B12345678", "the tax id the emitted chain is anchored to");
    assert_eq!(after.system_id, TARGET, "NumeroInstalacion = hub_id (ADR-0202)");
    assert_eq!(after.status, FiscalStatus::Active);

    // …and neither did the registry that says WHAT this country owes: one extra row there and a
    // Spanish hub would resolve to «owes nothing» on its next boot.
    let regimes = rt
        .db()
        .query("SELECT country_code, regime_key FROM _hub_fiscal_regime_registry", &Params::new())
        .await
        .unwrap();
    assert_eq!(regimes.rows.len(), 1, "the regime registry is core data, not bundle payload");
    assert_eq!(regimes.rows[0]["regime_key"].as_str(), Some("verifactu"));

    // ── It was IGNORED, and said so — not skipped in silence, not a crash. ───
    for section in ["_hub_fiscal_profile", "modules/_hub"] {
        let r = report
            .sections
            .iter()
            .find(|s| s.section == section)
            .unwrap_or_else(|| panic!("the report says nothing about `{section}`"));
        assert_eq!(
            r.status,
            SectionStatus::Ignored(ignore_reason::SYSTEM_TABLE_NOT_PORTABLE.into()),
            "`{section}` must be reported as deliberately discarded, with its reason"
        );
    }

    // ── The rest of the bundle landed: this is a discard, not a broken import. ─
    let settings = report.sections.iter().find(|s| s.section == "hub_settings").expect("settings");
    assert!(
        matches!(settings.status, SectionStatus::Applied),
        "the legitimate section still applies: {:?}",
        settings.status
    );
}

/// **The hub still owes what it owed.** The profile is re-resolved on every boot, so the proof that
/// nothing landed is not only «the row looks the same» but that the next start reaches the same
/// answer — a bundle cannot make a Spanish hub stop owing VeriFactu by the back door.
#[tokio::test]
async fn a_reboot_after_the_tampered_import_still_owes_verifactu() {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), TARGET);
    rt.ensure_system_tables().await.expect("boot");
    let (manifest, files) = tampered_bundle();
    import_sections(&mut rt, &manifest, &files, &import_everything(), TARGET)
        .await
        .expect("import");

    let profile = fiscal_profile::ensure(rt.db(), TARGET).await.expect("re-resolve at boot");

    assert_eq!(profile.fiscal_system, "verifactu");
    assert_eq!(profile.status, FiscalStatus::Unconfigured, "still unconfigured, never «already live»");
    assert_eq!(profile.system_id, TARGET);
    assert_eq!(profile.taxpayer_id, "", "no bundle hands this hub a tax id");
}
