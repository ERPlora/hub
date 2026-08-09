//! hub#659 (ADR-0283 §7, delivery 0) — `events.listen` may only point at the module's OWN command.
//!
//! A listener is the one door where a module names a command it does not run itself: the relay
//! resolves the name later, out of the caller's sight. Without an ownership check at install time,
//! a `module.json` could subscribe `sale.completed` to `inventory.stock.decrease` — a command of
//! ANOTHER module — and the runtime would register it. Only the permission gate at delivery time
//! stood in the way, which is an omission, not a decision: the two sibling doors already refuse it
//! (`scheduler::run_task` requires `c.module_id == module_id`, and `validate_operation` requires
//! the same module for a handler's operations).
//!
//! It is closed BEFORE `Origin::Automation` opens (ADR-0283): cross-module reactions with
//! transformation become the territory of flows with explicit grants, not of a line in a manifest
//! that nobody audits.

use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-listener-own-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

#[tokio::test]
async fn install_rejects_a_listener_pointing_at_another_modules_command() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-listeners");
    runtime.ensure_system_tables().await.unwrap();
    // The manifest from the issue: `analytics` subscribes to a sale and reaches into `inventory`.
    let dir = fixture(
        r#"{
          "id":"analytics",
          "name":"Analytics",
          "version":"1.0.0",
          "events":{
            "listen":{ "sale.completed": {"command":"inventory.stock.decrease"} }
          }
        }"#,
    );

    let error = runtime
        .install_from_dir(&dir)
        .await
        .expect_err("a module never subscribes another module's command to an event")
        .to_string();

    assert!(
        error.contains("sale.completed") && error.contains("inventory.stock.decrease"),
        "the refusal must name the event and the foreign command: {error}"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_rejects_a_listener_pointing_at_the_core_namespace() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-listeners");
    runtime.ensure_system_tables().await.unwrap();
    // `hub.*` is the core's reserved namespace (ADR-0192) and the dispatcher resolves it before
    // looking at the registry, so a listener there would run core capabilities on every event.
    let dir = fixture(
        r#"{
          "id":"analytics",
          "name":"Analytics",
          "version":"1.0.0",
          "events":{
            "listen":{ "sale.completed": {"command":"hub.users.create"} }
          }
        }"#,
    );

    let error = runtime
        .install_from_dir(&dir)
        .await
        .expect_err("the core namespace is as foreign to a module as another module is")
        .to_string();

    assert!(
        error.contains("hub.users.create"),
        "the refusal must name the command it refused: {error}"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_accepts_a_listener_pointing_at_its_own_command() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-listeners");
    runtime.ensure_system_tables().await.unwrap();
    // The shape of the 10 published modules that listen today (`inventory`, `invoice`,
    // `verifactu`…): they react to a foreign EVENT with a command of their own.
    let dir = fixture(
        r#"{
          "id":"inventory",
          "name":"Inventory",
          "version":"1.0.0",
          "commands":{
            "inventory.stock.decrease_on_sale": {"permission":"inventory.edit_stock","sql":[]}
          },
          "events":{
            "listen":{ "sale.completed": {"command":"inventory.stock.decrease_on_sale"} }
          }
        }"#,
    );

    let id = runtime
        .install_from_dir(&dir)
        .await
        .expect("reacting to another module's event with your own command is the whole point");

    assert_eq!(id, "inventory");
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_rejects_a_listener_whose_command_only_shares_the_id_as_a_prefix() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-listeners");
    runtime.ensure_system_tables().await.unwrap();
    // `inventory_admin.wipe` starts with `inventory` but belongs to `inventory_admin`: ownership
    // is a namespace boundary (`<id>.`), never a string prefix.
    let dir = fixture(
        r#"{
          "id":"inventory",
          "name":"Inventory",
          "version":"1.0.0",
          "events":{
            "listen":{ "sale.completed": {"command":"inventory_admin.wipe"} }
          }
        }"#,
    );

    let error = runtime
        .install_from_dir(&dir)
        .await
        .expect_err("a shared prefix is not the same namespace")
        .to_string();

    assert!(
        error.contains("inventory_admin.wipe"),
        "the refusal must name the command it refused: {error}"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

/// hub#686 turned this check into the PREMISE of something else, so it is worth stating what it
/// now holds up.
///
/// The relay runs a listener with the authority of its own module (`outbox::listener_ctx`) instead
/// of the emitting user's permissions — because the reaction to an event is the module's decision,
/// not the cashier's. That is only safe while a listener can name nothing but its own command:
/// otherwise a `module.json` could point a listener at somebody else's command and have the relay
/// run it with that module's full authority, on every event, with nobody looking.
///
/// The check that guarantees it lives in `installer::install`, which is the single registration
/// path: `Runtime::rehydrate_installed` re-runs it for every module on every boot. So a foreign
/// listener cannot merely be *refused at install* — it cannot be in a live registry at all, not
/// even one built before the check existed. This test pins the second half of that sentence: after
/// a refusal, there is nothing registered for the relay to elevate.
#[tokio::test]
async fn a_refused_listener_leaves_the_relay_nothing_to_run() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-listeners");
    runtime.ensure_system_tables().await.unwrap();
    let dir = fixture(
        r#"{
          "id":"analytics",
          "name":"Analytics",
          "version":"1.0.0",
          "events":{
            "listen":{ "sale.completed": {"command":"inventory.stock.decrease"} }
          }
        }"#,
    );

    runtime.install_from_dir(&dir).await.unwrap_err();

    assert!(
        runtime.registry().listeners_for("sale.completed").is_empty(),
        "a refused install registers no listener: the relay never sees a foreign command to run"
    );
    std::fs::remove_dir_all(dir).unwrap();
}
