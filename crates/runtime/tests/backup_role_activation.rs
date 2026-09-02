//! hub#417 — the role set of a hub in a **backup**: it travels, and the owner can take it back.
//!
//! `hub_role_activation` (system migration v13) is what says which of the roles the installed
//! modules DECLARE are live in this hub. hub#354 / [ADR-0242] made that set travel in the bundle —
//! as KEYS in the manifest, applied through `roles::set_active`, never as rows of the table. What
//! this file fixes is the OTHER half of the same round trip, and the half the reset never had:
//!
//! > *«lo que el hub sabe exportar es exactamente lo que sabe borrar»* — `export-import.md` §8, the
//! > sentence the reset engine is built on. Once the export learned to carry the role set, the
//! > reset was the only side of the mirror that could not clear it.
//!
//! Why that matters beyond tidiness, and why it is the conservative side:
//!
//! - Switching a role on is **granting capability** — it is what makes the role handable to a
//!   person (`roles::ensure_assignable`). A bundle can do it (ADR-0242 §2: bounded, but it can).
//! - Until now the ONLY way to take that back was to uninstall the module that declared it
//!   (`installer::uninstall` → `roles::clear_activation`). Wiping the hub to start over left the
//!   role set of whatever template had been tried on standing, live and assignable.
//! - So the owner of the hub gets the same door the bundle has, pointing the other way. A grant
//!   nobody can revoke without uninstalling a module is a grant that outlives the decision.
//!
//! Everything here is **opt-in** and **hub-scoped**, like the rest of the reset: the default
//! selection does not touch the table, and hub A switching its roles off says nothing about the hub
//! next door — they share one database (`tenancy.md`), which is the #1 risk of this engine.
//!
//! [ADR-0242]: ../../../architecture/00-overview/decision-log.md
use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection, ROLES_SECTION};
use erplora_runtime::hub_users::BASE_ROLES;
use erplora_runtime::import::{import_sections, ImportSelection};
use erplora_runtime::reset::{execute_reset, plan_reset, ResetSelection};
use erplora_runtime::Runtime;

/// A module folder with just its `module.json` — enough for the installer.
fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-backup-roles-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

/// The restaurant pack: the roles a hub of this vertical switches on.
const RESTAURANT_PACK: &str = r#"{
  "id":"restaurant_pack",
  "name":"Restaurant pack",
  "version":"1.0.0",
  "roles":[
    {"key":"waiter","label":"Waiter","extends":"employee"},
    {"key":"kitchen","label":"Kitchen","extends":"employee"},
    {"key":"shift_lead","label":"Shift lead","extends":"manager"}
  ],
  "role_permissions":{ "waiter":["pos.take_order"] }
}"#;

const CREATED_AT: &str = "2026-08-08T10:00:00Z";
const ACTOR: &str = "u1";

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

/// The rows of `hub_role_activation` themselves. The catalogue hides a row for a key nobody
/// declares, so a test about what is WRITTEN has to read the table.
async fn activation_rows(rt: &Runtime, hub_id: &str) -> Vec<String> {
    let mut p = Params::new();
    p.insert("hub_id".into(), serde_json::json!(hub_id));
    let res = rt
        .db()
        .query(
            "SELECT role_key FROM hub_role_activation WHERE hub_id = :hub_id ORDER BY role_key",
            &p,
        )
        .await
        .expect("read the activation table");
    res.rows
        .iter()
        .filter_map(|r| Some(r["role_key"].as_str()?.to_string()))
        .collect()
}

/// A reset that only asks for the role set. Everything else stays `false`: the reset never does
/// more than it was asked for.
fn wipe_roles() -> ResetSelection {
    ResetSelection {
        roles: true,
        ..Default::default()
    }
}

/// The `roles` row of a reset plan.
fn planned_roles(plan: &erplora_runtime::reset::ResetPlan) -> Option<i64> {
    plan.sections
        .iter()
        .find(|s| s.section == ROLES_SECTION)
        .map(|s| s.rows)
}

// ── The round trip: a backup restores the role set ──────────────────────────────────────

/// 🟢 The trip that names the issue: a hub with roles switched on is backed up, and restoring that
/// backup into a **clean** hub leaves the same role set live. Before hub#354 the restore gave the
/// users back with their roles while the roles themselves stayed off, so the administrator had to
/// go and switch them on again from memory — configuration silently lost on every migration of a
/// hub between deployments (ADR-0113 §1).
///
/// A **backup**, explicitly: hub#354 proved the trip for a published template, and the two purposes
/// have opposite requirements (ADR-0195). This is the one the issue is about.
#[tokio::test]
async fn a_backup_restores_the_same_role_set_into_a_clean_hub() {
    let mut origin = runtime("h1").await;
    install(&mut origin, RESTAURANT_PACK).await;
    origin.set_role_active("waiter", true, ACTOR).await.unwrap();
    origin
        .set_role_active("kitchen", true, ACTOR)
        .await
        .unwrap();
    let captured = active(&origin).await;

    // A plain backup: no checkbox names the role set, because there is none (ADR-0242 §7).
    let selection = ExportSelection {
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "bar-pepe", "es", CREATED_AT)
        .await
        .expect("export");
    assert_eq!(
        bundle.manifest.active_roles,
        vec!["kitchen".to_string(), "waiter".to_string()],
        "the backup has to carry the set, or there is nothing to restore"
    );
    assert!(bundle
        .manifest
        .sections
        .contains(&ROLES_SECTION.to_string()));

    // The new deployment: same modules, nothing switched on yet.
    let mut restored = runtime("h2").await;
    install(&mut restored, RESTAURANT_PACK).await;
    assert_eq!(
        active(&restored).await,
        BASE_ROLES.to_vec(),
        "a fresh hub starts with the base three"
    );

    import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h2",
    )
    .await
    .expect("the backup is accepted");

    assert_eq!(
        active(&restored).await,
        captured,
        "restoring a backup gives back the SAME role set the hub had — that is the round trip"
    );
    assert!(
        !active(&restored).await.contains(&"shift_lead".to_string()),
        "a declared role the origin never switched on stays off: a restore is not a blanket"
    );
}

/// 🔴 A backup restored where the modules of the vertical are NOT installed activates nothing —
/// and leaves **no latent row** behind either. Storing the key dormant would mean that installing
/// that module later found its role already live, switched on by a file instead of by a person:
/// the approval would outlive the moment anybody could have reviewed it. Fail closed, and the
/// administrator switches on what this business actually runs.
#[tokio::test]
async fn a_backup_whose_modules_are_missing_activates_nothing_and_leaves_no_latent_row() {
    let mut origin = runtime("h1").await;
    install(&mut origin, RESTAURANT_PACK).await;
    origin.set_role_active("waiter", true, ACTOR).await.unwrap();
    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "bar-pepe",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    // The destination never installed the restaurant pack.
    let mut bare = runtime("h2").await;
    import_sections(
        &mut bare,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h2",
    )
    .await
    .expect("the bundle is accepted: a missing module is not a reason to refuse the whole restore");

    assert_eq!(active(&bare).await, BASE_ROLES.to_vec());
    assert!(
        activation_rows(&bare, "h2").await.is_empty(),
        "a key nobody declares is refused, not parked: no dormant row may wait for the module"
    );
}

// ── The other half: the owner can take the role set back ────────────────────────────────

/// 🔴 The reset is the mirror of the export (`export-import.md` §8), so once the export carries the
/// role set the reset has to be able to clear it. Until this, wiping a hub to start over left every
/// role a tried-on template had switched on standing — live, and handable to a person.
#[tokio::test]
async fn resetting_the_roles_switches_off_what_the_hub_had_switched_on() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;
    rt.set_role_active("waiter", true, ACTOR).await.unwrap();
    rt.set_role_active("kitchen", true, ACTOR).await.unwrap();
    assert_eq!(
        activation_rows(&rt, "h1").await,
        vec!["kitchen".to_string(), "waiter".to_string()]
    );

    let report = execute_reset(&rt, "h1", &wipe_roles(), ACTOR)
        .await
        .expect("reset");

    assert!(
        activation_rows(&rt, "h1").await.is_empty(),
        "the role set is gone from the table"
    );
    assert_eq!(
        active(&rt).await,
        BASE_ROLES.to_vec(),
        "the hub is back to the frozen base three — those can never be switched off"
    );
    // The section is named with the SAME constant the export uses: the two sides of the mirror
    // cannot be allowed to drift apart into `roles` and `role_activation`.
    let section = report
        .sections
        .iter()
        .find(|s| s.section == ROLES_SECTION)
        .expect("the report says what it did with the roles");
    assert_eq!(
        section.rows_deleted, 2,
        "the report counts the rows it really took, not adjectives"
    );
}

/// 🔴 Opt-in, like every other section: a reset that does not ask for the role set does not touch a
/// single row of it. `ResetSelection::default()` is all-`false` on purpose — a body that forgets a
/// field must never WIDEN what gets deleted.
#[tokio::test]
async fn the_reset_leaves_the_role_set_alone_unless_it_is_asked_for() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;
    rt.set_role_active("waiter", true, ACTOR).await.unwrap();

    // Everything else the reset knows how to wipe, and NOT the roles.
    let selection = ResetSelection {
        settings: true,
        users: true,
        media: true,
        modules: vec!["restaurant_pack".into()],
        ..Default::default()
    };
    execute_reset(&rt, "h1", &selection, ACTOR)
        .await
        .expect("reset");

    assert_eq!(
        activation_rows(&rt, "h1").await,
        vec!["waiter".to_string()],
        "no other section may take the role set with it as a side effect"
    );
}

/// 🔴 Tenant isolation — the #1 risk of this engine. The database is SHARED (`tenancy.md`), so a
/// reset that forgot its `WHERE hub_id` would switch off the roles of the hub next door, and the
/// people there would find their job titles unassignable with nobody having touched anything.
#[tokio::test]
async fn resetting_the_roles_of_one_hub_leaves_the_hub_next_door_alone() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;
    rt.set_role_active("waiter", true, ACTOR).await.unwrap();
    // The neighbour lives in the SAME database, one row apart.
    erplora_runtime::roles::set_active(rt.db(), rt.registry(), "h2", "kitchen", true, ACTOR)
        .await
        .expect("the hub next door switches its own role on");

    execute_reset(&rt, "h1", &wipe_roles(), ACTOR)
        .await
        .expect("reset");

    assert!(activation_rows(&rt, "h1").await.is_empty());
    assert_eq!(
        activation_rows(&rt, "h2").await,
        vec!["kitchen".to_string()],
        "the neighbour's role set is untouched"
    );
}

/// 🔴 The point of all this, end to end and in the direction that matters for security: a bundle
/// somebody downloaded switches a role on (bounded, but it does — ADR-0242), and the owner of the
/// hub can **take it back** without uninstalling the module that declared it. A grant that can only
/// be revoked by uninstalling is a grant that outlives the decision behind it.
///
/// Proven through the door that actually enforces it: `roles::ensure_assignable`, which is what
/// `hub_users::create` — the HTTP path that adds a person to the hub — asks before writing the row.
/// Asserted there and not on a `create_user` helper, because the guarantee belongs to the guard:
/// every caller that hands out a role has to go through it, so that is where it has to hold.
#[tokio::test]
async fn the_owner_can_take_back_a_role_a_bundle_switched_on() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;

    // A bundle from somewhere else — another hub's id, published as a template — pre-activates the
    // vertical's role set. `purpose` does not filter roles (ADR-0242 §8) and neither does origin.
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
    foreign.manifest.purpose = BundlePurpose::Template;
    foreign.manifest.hub.hub_id = "some-other-hub".into();
    foreign.manifest.active_roles = vec!["waiter".into()];
    foreign.manifest.sections.push(ROLES_SECTION.to_string());
    import_sections(
        &mut rt,
        &foreign.manifest,
        &foreign.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("the bundle is accepted");
    assert!(
        active(&rt).await.contains(&"waiter".to_string()),
        "precondition: the bundle switched it on"
    );
    erplora_runtime::roles::ensure_assignable(rt.db(), rt.registry(), "h1", "waiter")
        .await
        .expect("precondition: while it is live the role can be handed to a person");

    execute_reset(&rt, "h1", &wipe_roles(), ACTOR)
        .await
        .expect("reset");

    assert!(activation_rows(&rt, "h1").await.is_empty());
    assert!(
        erplora_runtime::roles::ensure_assignable(rt.db(), rt.registry(), "h1", "waiter")
            .await
            .is_err(),
        "once the owner switched it off, the role a downloaded file granted is no longer handable"
    );
}

/// 🔴 A hub whose activation table is not there yet must not have its reset blow up. The reset runs
/// in ONE transaction, so a `DELETE` against a missing table would roll back every other section
/// with it: asking for the roles on a hub that predates the v13 migration would take the settings
/// and the module data down too. The guard is «only emit statements for tables that EXIST», and it
/// has to key on THIS table — not on «some table exists», which is true of every hub alive.
#[tokio::test]
async fn a_hub_without_the_activation_table_still_resets_everything_else() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;
    let mut updates = serde_json::Map::new();
    updates.insert("language".into(), serde_json::json!("es"));
    rt.set_settings(&updates, ACTOR)
        .await
        .expect("a setting to clear");
    rt.db()
        .execute("DROP TABLE hub_role_activation", &Params::new())
        .await
        .expect("take the activation table away");

    let selection = ResetSelection {
        roles: true,
        settings: true,
        ..Default::default()
    };
    let report = execute_reset(&rt, "h1", &selection, ACTOR)
        .await
        .expect("a missing table is a no-op, never a reason to abort the whole reset");

    assert!(
        report.sections.iter().any(|s| s.section == "hub_settings"),
        "the section that COULD be cleared was: {:?}",
        report.sections
    );
    assert!(
        !report.sections.iter().any(|s| s.section == ROLES_SECTION),
        "there was no table to clear, so there is nothing to report about roles"
    );
}

/// 🔴 `plan_reset` is a dry run and it counts REAL rows: the panel paints figures, not adjectives,
/// and confirming a destructive action against a made-up number is worse than no number at all.
#[tokio::test]
async fn the_plan_counts_the_roles_it_would_switch_off_and_switches_off_none() {
    let mut rt = runtime("h1").await;
    install(&mut rt, RESTAURANT_PACK).await;
    rt.set_role_active("waiter", true, ACTOR).await.unwrap();
    rt.set_role_active("shift_lead", true, ACTOR).await.unwrap();
    // The neighbour's rows are NOT this hub's: counting them would inflate the figure the owner
    // confirms against.
    erplora_runtime::roles::set_active(rt.db(), rt.registry(), "h2", "kitchen", true, ACTOR)
        .await
        .unwrap();

    let plan = plan_reset(&rt, "h1").await.expect("plan");

    assert_eq!(
        planned_roles(&plan),
        Some(2),
        "two rows of THIS hub would go"
    );
    assert_eq!(
        activation_rows(&rt, "h1").await,
        vec!["shift_lead".to_string(), "waiter".to_string()],
        "a dry run does not delete"
    );
}
