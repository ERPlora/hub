//! hub#354 (paso 2b) — a blueprint PRE-ACTIVATES the role set of its vertical.
//!
//! hub#351 let a module DECLARE the roles its vertical needs; hub#352 made a declared role land
//! **inactive** so nobody is handed a role they never asked for. That opt-in is exactly what leaves
//! a hole to fill: a brand-new restaurant would open with `Waiter`, `Bartender`, `Kitchen` and
//! `Cashier` all switched off, and somebody would have to guess which ones this business runs on.
//! The vertical knows. So the blueprint carries the answer, and a new vertical costs a blueprint
//! instead of a release of the core.
//!
//! Pre-activating is **granting capability without anybody pressing anything**, so every property
//! that keeps it bounded is fixed here:
//!
//! 1. Importing the blueprint of a vertical leaves **its** roles live — and only those (a declared
//!    role the blueprint does not name stays off: the opt-in of hub#352 survives).
//! 2. A key **no installed module declares** is never activated, and never MINTED: a bundle is a
//!    file the user supplies, so it cannot invent role keys any more than the write door can.
//! 3. The **administrative** roles stay untouchable — a manifest cannot mint privilege (hub#347 /
//!    hub#351) and neither can a blueprint.
//! 4. Re-importing is **idempotent**: the same bundle twice leaves the same hub.
//! 5. A template activates ROLES, never USERS (ADR-0195 §5): the sample people of a vertical are
//!    rows of `staff`, never `hub_user`.
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::export::{
    export_hub, BlueprintManifest, BundlePurpose, ExportSelection, HubMeta, SCHEMA_VERSION,
};
use erplora_runtime::hub_users::{is_admin_role, BASE_ROLES};
use erplora_runtime::import::{import_sections, ImportReport, ImportSelection, SectionStatus};
use erplora_runtime::Runtime;
use std::collections::BTreeMap;

/// A module folder with just its `module.json` — enough for the installer.
fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-bp-roles-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

/// The restaurant pack of the PLAN: Waiter · Bartender · Kitchen · Cashier, plus the roles every
/// vertical shares (Shift lead, HR manager, Accountant — read-only fiscal, so `extends: manager`).
const RESTAURANT_PACK: &str = r#"{
  "id":"restaurant_pack",
  "name":"Restaurant pack",
  "version":"1.0.0",
  "roles":[
    {"key":"waiter","label":"Waiter","extends":"employee"},
    {"key":"bartender","label":"Bartender","extends":"employee"},
    {"key":"kitchen","label":"Kitchen","extends":"employee"},
    {"key":"cashier","label":"Cashier","extends":"employee"},
    {"key":"shift_lead","label":"Shift lead","extends":"manager"},
    {"key":"hr_manager","label":"HR manager","extends":"manager"},
    {"key":"accountant","label":"Accountant","extends":"manager"}
  ],
  "role_permissions":{
    "waiter":["pos.take_order"],
    "employee":["pos.view_order"]
  }
}"#;

/// The hairdresser pack of the PLAN: Receptionist · Stylist. Never installed next to the
/// restaurant one — it is here to name a role that this hub's modules do NOT declare.
const BEAUTY_PACK: &str = r#"{
  "id":"beauty_pack",
  "name":"Beauty pack",
  "version":"1.0.0",
  "roles":[
    {"key":"receptionist","label":"Receptionist","extends":"employee"},
    {"key":"stylist","label":"Stylist","extends":"employee"}
  ]
}"#;

const CREATED_AT: &str = "2026-08-07T10:00:00Z";

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

/// A manifest whose only cargo is the role set of a vertical: no files, no data sections. It is
/// the smallest bundle that pre-activates, and it keeps these tests about the roles.
fn blueprint(name: &str, active_roles: &[&str]) -> BlueprintManifest {
    BlueprintManifest {
        schema_version: SCHEMA_VERSION,
        purpose: BundlePurpose::Template,
        name: name.into(),
        locale: "es".into(),
        hub: HubMeta {
            name: "Bar Pepe".into(),
            country: "ES".into(),
            currency: "EUR".into(),
            hub_id: "origin-hub".into(),
        },
        created_at: CREATED_AT.into(),
        modules: Vec::new(),
        sections: vec!["roles".into()],
        active_roles: active_roles.iter().map(|r| (*r).to_string()).collect(),
        capability_grants: Default::default(),
        flows: Vec::new(),
        sha256: BTreeMap::new(),
    }
}

async fn import(rt: &mut Runtime, manifest: &BlueprintManifest, hub_id: &str) -> ImportReport {
    import_sections(
        rt,
        manifest,
        &BTreeMap::new(),
        &ImportSelection::default(),
        hub_id,
    )
    .await
    .expect("the bundle is accepted")
}

/// The `roles` row of the import report, which is what the UI paints.
fn roles_section(report: &ImportReport) -> Option<&erplora_runtime::import::SectionResult> {
    report.sections.iter().find(|s| s.section == "roles")
}

/// The role keys live in this hub, straight from the catalogue.
async fn active(rt: &Runtime) -> Vec<String> {
    rt.role_catalog()
        .await
        .unwrap()
        .into_iter()
        .filter(|r| r.active)
        .map(|r| r.key)
        .collect()
}

/// The keys of the catalogue — what EXISTS, active or not. Used to prove nothing was minted.
async fn catalog_keys(rt: &Runtime) -> Vec<String> {
    rt.role_catalog()
        .await
        .unwrap()
        .into_iter()
        .map(|r| r.key)
        .collect()
}

/// The rows of `hub_role_activation` themselves: the catalogue hides a row for a key nobody
/// declares, so a test about what was WRITTEN has to read the table.
async fn activation_rows(rt: &Runtime, hub_id: &str) -> Vec<String> {
    activation_table(rt, hub_id)
        .await
        .into_iter()
        .map(|(key, _)| key)
        .collect()
}

/// The rows with their `activated_by`: who is on record as having switched the role on.
async fn activation_table(rt: &Runtime, hub_id: &str) -> Vec<(String, String)> {
    let mut p = Params::new();
    p.insert("hub_id".into(), serde_json::json!(hub_id));
    let res = rt
        .db()
        .query(
            "SELECT role_key, activated_by FROM hub_role_activation \
             WHERE hub_id = :hub_id ORDER BY role_key",
            &p,
        )
        .await
        .expect("read the activation table");
    res.rows
        .iter()
        .filter_map(|r| {
            Some((
                r["role_key"].as_str()?.to_string(),
                r["activated_by"].as_str()?.to_string(),
            ))
        })
        .collect()
}

/// 🟢 The whole point: importing the blueprint of a vertical leaves the roles of that vertical
/// live, so the business opens with its own job titles instead of three generic ones.
#[tokio::test]
async fn importing_the_blueprint_of_a_vertical_activates_the_roles_of_that_vertical() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;

    // Opt-in (hub#352): installing the pack activated nothing on its own.
    assert_eq!(active(&rt).await, BASE_ROLES.to_vec());

    let manifest = blueprint(
        "restaurante",
        &["waiter", "bartender", "kitchen", "cashier", "shift_lead"],
    );
    let report = import(&mut rt, &manifest, "h1").await;

    let live = active(&rt).await;
    for role in ["waiter", "bartender", "kitchen", "cashier", "shift_lead"] {
        assert!(
            live.contains(&role.to_string()),
            "`{role}` had to be live: {live:?}"
        );
    }
    // …and ONLY those: a declared role the blueprint does not name keeps the opt-in of hub#352.
    for off in ["hr_manager", "accountant"] {
        assert!(
            !live.contains(&off.to_string()),
            "`{off}` was not in the blueprint: pre-activation is a list, not a blanket: {live:?}"
        );
    }

    let section = roles_section(&report).expect("the report says what it did with the roles");
    assert_eq!(section.status, SectionStatus::Applied);
    assert_eq!(section.discarded_rows, 0, "nothing was left out");

    // The audit column says the template did it, not a person: no `hub_user` decided this.
    for (key, by) in activation_table(&rt, "h1").await {
        assert_eq!(
            by, "blueprint",
            "`{key}` was switched on by the import, and says so"
        );
    }
}

/// The roles land in the hub the import is FOR, not in whatever hub the runtime happens to serve.
/// The server passes the data-plane `hub_id`, which is not always the runtime's own — and an
/// activation written under the wrong tenant would switch a role on for the hub next door.
#[tokio::test]
async fn the_roles_land_in_the_target_hub_not_in_the_runtime_s_own() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;

    let report = import(&mut rt, &blueprint("restaurante", &["waiter"]), "h2").await;

    assert_eq!(activation_rows(&rt, "h2").await, vec!["waiter".to_string()]);
    assert!(
        activation_rows(&rt, "h1").await.is_empty(),
        "the runtime's own hub was not the destination: nothing may be switched on there"
    );
    assert_eq!(
        roles_section(&report).map(|s| &s.status),
        Some(&SectionStatus::Applied)
    );
}

/// 🔴 A database that will not take the write is `Failed`, never a discard. They read the same on
/// a screen and mean opposite things: `Ignored` says «this hub refused these roles» — a decision —
/// while the truth would be «nobody decided anything, the write did not happen». And the rest of
/// the import still goes on: best-effort is per section (ADR-0113).
#[tokio::test]
async fn a_database_failure_is_reported_as_failed_not_as_a_discard() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;
    rt.db()
        .execute("DROP TABLE hub_role_activation", &Params::new())
        .await
        .expect("take the activation table away");

    let report = import(&mut rt, &blueprint("restaurante", &["waiter"]), "h1").await;

    let section = roles_section(&report).expect("the report has to say so");
    assert!(
        matches!(section.status, SectionStatus::Failed(_)),
        "a write that could not happen is a failure, not «the hub said no»: {:?}",
        section.status
    );
    assert_eq!(
        section.discarded_rows, 0,
        "nothing was discarded on purpose"
    );
}

/// 🔴 A blueprint cannot activate what nobody declares — and cannot MINT it either. A bundle is a
/// file the user supplies: if naming a key were enough to create it, the manifest gate of hub#351
/// and the write door of hub#352 would both have a way round them.
#[tokio::test]
async fn a_role_no_installed_module_declares_is_never_activated_nor_minted() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;

    // `stylist` belongs to the hairdresser pack, which is NOT installed here — and it is named
    // THREE times, one of them padded, because a key repeated in a template is one role, not two.
    let manifest = blueprint(
        "restaurante",
        &["waiter", "stylist", "sommelier", "stylist", "  stylist  "],
    );
    let report = import(&mut rt, &manifest, "h1").await;

    assert!(
        active(&rt).await.contains(&"waiter".to_string()),
        "the declared one goes live"
    );

    let keys = catalog_keys(&rt).await;
    for ghost in ["stylist", "sommelier"] {
        assert!(
            !keys.contains(&ghost.to_string()),
            "`{ghost}` must not exist: a blueprint activates a catalogue, it does not create one: {keys:?}"
        );
    }
    assert_eq!(
        activation_rows(&rt, "h1").await,
        vec!["waiter".to_string()],
        "nothing was written for a key no installed module declares"
    );

    let section = roles_section(&report).expect("the report has to say so");
    assert_eq!(
        section.status,
        SectionStatus::PartiallyApplied(
            erplora_runtime::import::ignore_reason::ROLES_NOT_ACTIVATABLE.into()
        ),
        "part of the set landed and part did not: neither Applied nor Ignored is true"
    );
    assert_eq!(
        section.discarded_rows, 2,
        "both refused keys are counted — and the repeated one only once"
    );
}

/// 🔴 The administrative roles stay untouchable. A manifest cannot mint privilege (hub#347 /
/// hub#351) and a blueprint is a weaker artefact still: it is downloaded, published and imported
/// by strangers. `admin` — and its legacy spelling `owner` — go through the same door as everything
/// else, and that door refuses them.
#[tokio::test]
async fn a_blueprint_cannot_pre_activate_an_administrative_role() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;

    let manifest = blueprint("restaurante", &["admin", "owner", "manager", "employee"]);
    let report = import(&mut rt, &manifest, "h1").await;

    assert!(
        activation_rows(&rt, "h1").await.is_empty(),
        "a base role is live by construction: the bundle must not write a row for it, and least of all for an administrative one"
    );
    // The base catalogue is exactly what it was: still live, still administered by `admin` alone.
    assert_eq!(active(&rt).await, BASE_ROLES.to_vec());
    for role in rt.role_catalog().await.unwrap() {
        if role.source != erplora_runtime::roles::RoleSource::Core {
            assert!(
                !is_admin_role(&role.key),
                "`{}` came from a package: it can never administer the hub",
                role.key
            );
        }
    }

    let section = roles_section(&report).expect("the report has to say so");
    // The code is spelled out, not taken from the constant: it is the WIRE contract the shell
    // matches on (`SECTION_DISCARD_CODES`), so renaming the constant has to break something here.
    assert_eq!(
        section.status,
        SectionStatus::Ignored("roles_not_activatable".into()),
        "nothing landed at all"
    );
    assert_eq!(section.discarded_rows, 4);
}

/// Re-importing the same blueprint leaves the same hub: the roles do not pile up and the report
/// does not change. A hub that re-applies its vertical (a redeploy, a second run of the bootstrap
/// import) must not drift.
#[tokio::test]
async fn re_importing_the_same_blueprint_is_idempotent() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;
    let manifest = blueprint("restaurante", &["waiter", "kitchen"]);

    let first = import(&mut rt, &manifest, "h1").await;
    let live_once = active(&rt).await;
    let rows_once = activation_rows(&rt, "h1").await;

    let second = import(&mut rt, &manifest, "h1").await;

    assert_eq!(
        active(&rt).await,
        live_once,
        "the second import changes nothing"
    );
    assert_eq!(
        activation_rows(&rt, "h1").await,
        rows_once,
        "no duplicated rows"
    );
    assert_eq!(rows_once, vec!["kitchen".to_string(), "waiter".to_string()]);
    assert_eq!(
        roles_section(&second),
        roles_section(&first),
        "same report both times"
    );
}

/// A bundle that predates the field activates nothing — and does not grow a phantom row in the
/// report either. `#[serde(default)]` is the whole compatibility story of the published artefacts.
#[tokio::test]
async fn a_bundle_that_predates_the_field_activates_nothing() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;

    let json = serde_json::json!({
        "schema_version": SCHEMA_VERSION,
        "name": "restaurante",
        "locale": "es",
        "hub": { "name": "Bar Pepe", "country": "ES", "currency": "EUR" },
        "created_at": CREATED_AT,
        "modules": [],
        "sections": [],
        "sha256": {},
    });
    let manifest: BlueprintManifest =
        serde_json::from_value(json).expect("an older manifest still parses");
    assert!(manifest.active_roles.is_empty());

    let report = import(&mut rt, &manifest, "h1").await;

    assert_eq!(active(&rt).await, BASE_ROLES.to_vec());
    assert!(activation_rows(&rt, "h1").await.is_empty());
    assert!(
        roles_section(&report).is_none(),
        "a bundle with no roles has nothing to report about roles"
    );
}

/// The producer half: exporting a hub carries the roles it has switched ON, so the vertical can be
/// captured from a hub that was configured by hand instead of being written into the core.
#[tokio::test]
async fn an_export_carries_the_roles_the_hub_has_switched_on() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;

    let empty = export_hub(
        &rt,
        "h1",
        &ExportSelection::default(),
        "restaurante",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    assert!(
        empty.manifest.active_roles.is_empty()
            && !empty.manifest.sections.contains(&"roles".to_string()),
        "a hub that switched nothing on has no role set to publish"
    );

    rt.set_role_active("waiter", true, "user-1").await.unwrap();
    rt.set_role_active("kitchen", true, "user-1").await.unwrap();

    let bundle = export_hub(
        &rt,
        "h1",
        &ExportSelection::default(),
        "restaurante",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    assert_eq!(
        bundle.manifest.active_roles,
        vec!["kitchen".to_string(), "waiter".to_string()],
        "the role set travels in the manifest, sorted, and only the live ones"
    );
    assert!(bundle.manifest.sections.contains(&"roles".to_string()));
}

/// ADR-0195 §5: a template activates ROLES and never creates USERS. The two halves of the same
/// sentence have to hold in the SAME bundle — the role set travels while the accounts stay behind.
#[tokio::test]
async fn a_template_carries_the_role_set_but_never_the_accounts() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;
    rt.set_role_active("waiter", true, "user-1").await.unwrap();
    rt.create_user("Ana", "1234", "waiter", None)
        .await
        .expect("an employee of the hub");

    let selection = ExportSelection {
        users: true, // asked for, and refused: a checkbox is not a control (ADR-0195)
        purpose: BundlePurpose::Template,
        ..Default::default()
    };
    let bundle = export_hub(&rt, "h1", &selection, "restaurante", "es", CREATED_AT)
        .await
        .expect("export");

    assert_eq!(bundle.manifest.active_roles, vec!["waiter".to_string()]);
    assert!(
        !bundle.manifest.sections.contains(&"hub_users".to_string()),
        "the people of a vertical are examples, not identities: they never travel"
    );
    assert!(!bundle.files.contains_key("data/hub_users.sql"));
}

/// End to end across two hubs: the vertical captured in hub A opens hub B with the same job
/// titles — which is what «a new vertical costs a blueprint, never a release of the core» means.
#[tokio::test]
async fn a_vertical_travels_from_the_hub_that_captured_it_to_a_brand_new_one() {
    let mut a = runtime("h1").await;
    install(&mut a, RESTAURANT_PACK).await;
    a.set_role_active("waiter", true, "user-1").await.unwrap();
    a.set_role_active("shift_lead", true, "user-1")
        .await
        .unwrap();

    let selection = ExportSelection {
        purpose: BundlePurpose::Template,
        ..Default::default()
    };
    let bundle = export_hub(&a, "h1", &selection, "restaurante", "es", CREATED_AT)
        .await
        .expect("export");

    // Hub B: brand new, its modules installed by the server before the engine runs.
    let mut b = runtime("h2").await;
    install(&mut b, RESTAURANT_PACK).await;
    install(&mut b, BEAUTY_PACK).await;
    assert_eq!(
        active(&b).await,
        BASE_ROLES.to_vec(),
        "a new hub starts with the base three"
    );

    let report = import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h2",
    )
    .await
    .expect("the bundle is accepted");

    let live = active(&b).await;
    assert!(live.contains(&"waiter".to_string()) && live.contains(&"shift_lead".to_string()));
    assert!(
        !live.contains(&"stylist".to_string()),
        "the hairdresser role is installed but the restaurant blueprint does not name it"
    );
    assert_eq!(
        roles_section(&report).map(|s| &s.status),
        Some(&SectionStatus::Applied)
    );
}
