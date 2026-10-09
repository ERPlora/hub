//! Round-trip restore of a hub's OWN backup (hub#2513).
//!
//! Contract (WORKFLOW.md HUB-F236 / HUB-F238): restoring the business copy leaves every person
//! ONCE and WHOLE — nobody who already exists gets duplicated, and each person keeps the profile
//! and preferences that point at them. The two scenarios the issue describes:
//!   - restore onto the LIVE hub (the running business importing its own backup), and
//!   - restore onto an EMPTY install of the same hub (disaster recovery).
//!
//! Both are `same_hub` imports: the bundle was born under this `hub_id`, so its rows already
//! live under the ids they carry. The tests assert the user-visible effect straight against the
//! database — row counts and the person↔profile join — because that is what "the team came back
//! duplicated / without their profiles" means. The import pipeline itself is covered by
//! `import_test.rs`; what travels, by `export_test.rs`.

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{export_hub, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

const CREATED_AT: &str = "2026-07-11T18:00:00Z";

/// Hub-scoped row counts the issue's symptom is made of.
const TEAM_SIZE: &str = "SELECT COUNT(*) AS n FROM hub_user WHERE hub_id = :hub";
const USERS_WITHOUT_PROFILE: &str = "SELECT COUNT(*) AS n FROM hub_user u \
     LEFT JOIN hub_user_profile p ON p.hub_id = u.hub_id AND p.user_id = u.id \
     WHERE u.hub_id = :hub AND p.user_id IS NULL";
const PROFILES_WITHOUT_USER: &str = "SELECT COUNT(*) AS n FROM hub_user_profile p \
     LEFT JOIN hub_user u ON u.hub_id = p.hub_id AND u.id = p.user_id \
     WHERE p.hub_id = :hub AND u.id IS NULL";
const PRODUCT_ROWS: &str =
    "SELECT COUNT(*) AS n FROM inventory_product WHERE hub_id = :hub AND sku = 'CAF'";

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
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

/// A hub with the modules installed (and therefore seeded) UNDER ITS OWN hub_id — like in
/// production, where the server installs the manifest modules for the destination hub before
/// calling the motor.
async fn fresh() -> Runtime {
    ensure_master_key();
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&erplora_runtime::e2e_support::modules_root().join("taxes"))
        .await
        .expect("install taxes");
    rt.install_from_dir(&erplora_runtime::e2e_support::modules_root().join("inventory"))
        .await
        .expect("install inventory");
    rt
}

async fn scalar(rt: &Runtime, sql: &str, hub: &str) -> i64 {
    let mut p = Params::new();
    p.insert("hub".into(), json!(hub));
    let result = rt.db().query(sql, &p).await.expect("count query");
    result
        .rows
        .first()
        .and_then(|r| r["n"].as_i64())
        .unwrap_or(0)
}

/// One person exactly as the issue describes: a team member with role, PIN, profile email and a
/// language preference. Returns their `hub_user.id`.
async fn create_person_with_profile(rt: &Runtime) -> String {
    let id = erplora_runtime::hub_users::create(
        rt.db(),
        // Empty registry on purpose (same as `import_test.rs`): the base role catalogue is enough.
        &erplora_runtime::Registry::new(),
        "h1",
        &erplora_runtime::hub_users::NewHubUser {
            name: "Encargada".into(),
            role: "manager".into(),
            pin: "4821".into(),
            email: "encargada@example.com".into(),
            badge: String::new(),
            local: false,
        },
        0,
    )
    .await
    .expect("create the team member");
    erplora_runtime::user_profile::update(
        rt.db(),
        "h1",
        &id,
        &erplora_runtime::user_profile::UpdateUserProfile {
            first_name: "Ana".into(),
            last_name: "Ruiz".into(),
            email: "ana@example.com".into(),
            preferences: erplora_runtime::user_profile::UserPreferences {
                language: Some("en".into()),
                theme_mode: None,
                theme_palette: None,
            },
        },
    )
    .await
    .expect("set the profile and the language");
    id
}

async fn create_product(rt: &Runtime, name: &str, sku: &str) {
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": name, "sku": sku, "price": 450, "cost": 200, "stock": erplora_runtime::e2e_support::units(10), "tax_category_key": "product.generic" })),
        &ctx("h1"),
    )
    .await
    .unwrap_or_else(|e| panic!("create product {name}: {e}"));
}

fn full_selection() -> ExportSelection {
    ExportSelection {
        users: true,
        settings: true,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![
            ModuleDataSelection {
                module_id: "taxes".into(),
                with_data: true,
                tables: None,
            },
            ModuleDataSelection {
                module_id: "inventory".into(),
                with_data: true,
                tables: None,
            },
        ],
        purpose: Default::default(),
    }
}

fn import_all() -> ImportSelection {
    ImportSelection {
        users: true,
        settings: true,
        fiscal: false,
        media: false,
        modules: vec!["taxes".into(), "inventory".into()],
    }
}

/// Restore onto the hub that is STILL RUNNING — the business importing its own backup over its
/// live data. Every person must stay exactly once, each one with their profile: the issue's
/// first symptom is «cada persona aparece dos veces: la de siempre y otra nueva con el mismo
/// nombre, rol y PIN, pero sin su perfil».
#[tokio::test]
async fn restoring_own_backup_on_the_live_hub_does_not_duplicate_the_team() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut a = fresh().await;
    let ana = create_person_with_profile(&a).await;
    create_product(&a, "Café", "CAF").await;
    let bundle = export_hub(&a, "h1", &full_selection(), "copia", "es", CREATED_AT)
        .await
        .expect("export the hub's own backup");
    assert_eq!(bundle.manifest.hub.hub_id, "h1", "the bundle records its origin hub");

    let report = import_sections(&mut a, &bundle.manifest, &bundle.files, &import_all(), "h1")
        .await
        .expect("restore onto the live hub");
    let section = report
        .sections
        .iter()
        .find(|s| s.section == "hub_users")
        .expect("hub_users in the report");
    assert!(
        matches!(section.status, SectionStatus::Applied),
        "the team section had to apply: {:?}",
        section.status
    );

    // One person, not two: a duplicate means the import rewrote the id the row already has and
    // its idempotency guard asked for an id that was never there.
    assert_eq!(
        scalar(&a, TEAM_SIZE, "h1").await,
        1,
        "the restore duplicated the team"
    );
    // …and the person that is there still has their profile attached (the issue's duplicate
    // came without one).
    assert_eq!(
        scalar(&a, USERS_WITHOUT_PROFILE, "h1").await,
        0,
        "a person of this hub lost their profile"
    );
    let profile = erplora_runtime::user_profile::get(a.db(), "h1", &ana)
        .await
        .expect("the person's profile");
    assert_eq!(profile.email, "ana@example.com", "profile email lost");
    assert_eq!(
        profile.preferences.language,
        Some("en".into()),
        "language preference lost"
    );
    // Module data on the live hub is not duplicated either.
    assert_eq!(
        scalar(&a, PRODUCT_ROWS, "h1").await,
        1,
        "the restore duplicated a product"
    );

    // Re-importing stays idempotent (HUB-F238: «reimportar en el mismo hub no duplica»).
    import_sections(&mut a, &bundle.manifest, &bundle.files, &import_all(), "h1")
        .await
        .expect("second restore");
    assert_eq!(
        scalar(&a, TEAM_SIZE, "h1").await,
        1,
        "the second restore duplicated the team"
    );
}

/// Restore onto an EMPTY install of the same hub — the disaster-recovery path. The person must
/// come back WHOLE: the profile and the language preference linked to the id they came back
/// with, not orphaned rows pointing at an id nobody restored («todos aparecen sin nombre
/// visible, foto, correo de perfil ni idioma»).
#[tokio::test]
async fn restoring_own_backup_on_an_empty_install_returns_each_person_with_their_profile() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let a = fresh().await;
    create_person_with_profile(&a).await;
    create_product(&a, "Café", "CAF").await;
    let bundle = export_hub(&a, "h1", &full_selection(), "copia", "es", CREATED_AT)
        .await
        .expect("export the hub's own backup");

    // Same hub_id, rebuilt from scratch: a fresh database with the modules installed.
    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h1")
        .await
        .expect("disaster-recovery restore");
    let section = report
        .sections
        .iter()
        .find(|s| s.section == "hub_users")
        .expect("hub_users in the report");
    assert!(
        matches!(section.status, SectionStatus::Applied),
        "the team section had to apply: {:?}",
        section.status
    );

    let users = erplora_runtime::hub_users::list(b.db(), "h1")
        .await
        .expect("list the restored team");
    assert_eq!(users.len(), 1, "the team did not come back: {users:?}");
    assert_eq!(users[0].name, "Ana Ruiz", "the person lost their name");
    assert_eq!(users[0].role, "manager", "the role was lost on restore");
    assert!(users[0].has_pin, "the PIN was lost on restore");

    // The person↔profile relation survived: the profile answers for the id the person came
    // back with, and no row is left pointing at an id that does not exist.
    let profile = erplora_runtime::user_profile::get(b.db(), "h1", &users[0].id)
        .await
        .expect("the restored person's profile");
    assert_eq!(
        profile.email, "ana@example.com",
        "the profile row stayed orphaned: the person came back without their profile email"
    );
    assert_eq!(
        profile.preferences.language,
        Some("en".into()),
        "the preference row stayed orphaned: the person came back without their language"
    );
    assert_eq!(
        scalar(&b, PROFILES_WITHOUT_USER, "h1").await,
        0,
        "a restored profile points at a person nobody restored"
    );
    assert_eq!(
        scalar(&b, USERS_WITHOUT_PROFILE, "h1").await,
        0,
        "a restored person lost their profile"
    );
}
