//! hub#351 (paso 2b) — the `roles[]` block of `module.json`, checked at the INSTALL door.
//!
//! A module may declare the business roles its vertical needs (`waiter`, `kitchen`, `accountant`)
//! on top of the frozen base catalogue (`admin`/`manager`/`employee`). The block is optional: the
//! ~24 published modules do not carry it and must keep installing untouched.
//!
//! The border matters. A `module.zip` is third-party input, so the manifest is validated **before
//! any side effect** — no migrations, no seed, no registered capability — exactly like the command
//! contracts of hub#139. And the one thing a manifest can never buy is administration of the hub
//! (hub#347): that property is granted by the hub itself, so a role that tries to extend `admin`
//! is refused at this door.

use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-module-roles-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

#[tokio::test]
async fn install_accepts_a_module_that_declares_its_own_roles() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-roles");
    runtime.ensure_system_tables().await.unwrap();
    let dir = fixture(
        r#"{
          "id":"kitchen",
          "name":"Kitchen",
          "version":"2.3.1",
          "roles":[
            {"key":"kitchen","label":"Kitchen","extends":"employee"},
            {"key":"shift_lead","label":"Shift lead","extends":"manager"}
          ],
          "role_permissions":{
            "kitchen":["kitchen.view_ticket","kitchen.bump_ticket"],
            "employee":["kitchen.view_ticket"]
          }
        }"#,
    );

    let id = runtime
        .install_from_dir(&dir)
        .await
        .expect("a module declaring roles installs");

    assert_eq!(id, "kitchen");
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_rejects_a_role_that_would_administer_the_hub() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-roles");
    runtime.ensure_system_tables().await.unwrap();
    let dir = fixture(
        r#"{
          "id":"kitchen",
          "name":"Kitchen",
          "version":"2.3.1",
          "roles":[{"key":"backdoor","label":"Back door","extends":"admin"}],
          "role_permissions":{"backdoor":["*"]}
        }"#,
    );

    let error = runtime
        .install_from_dir(&dir)
        .await
        .expect_err("a manifest never grants administration of the hub")
        .to_string();

    assert!(
        error.contains("backdoor") && error.contains("administ"),
        "the refusal must name the role and the reason: {error}"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_still_accepts_a_module_without_the_roles_block() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-roles");
    runtime.ensure_system_tables().await.unwrap();
    // The shape of the ~24 already published manifests: `role_permissions` for the three base
    // keys and no `roles` block at all.
    let dir = fixture(
        r#"{
          "id":"inventory",
          "name":"Inventory",
          "version":"1.0.0",
          "role_permissions":{
            "admin":["*"],
            "manager":["inventory.view_product","inventory.add_product"],
            "employee":["inventory.view_product"]
          }
        }"#,
    );

    let id = runtime
        .install_from_dir(&dir)
        .await
        .expect("a published module keeps installing without a `roles` block");

    assert_eq!(id, "inventory");
    std::fs::remove_dir_all(dir).unwrap();
}
