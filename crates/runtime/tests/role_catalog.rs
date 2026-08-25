//! hub#352 (paso 2b) — the AGGREGATED role catalogue and its per-hub activation.
//!
//! hub#351 gave a module the right to DECLARE business roles (`roles[]`). This is what the hub
//! does with them: it aggregates the base catalogue of the core (`admin`/`manager`/`employee`)
//! with what the installed modules declare, and the administrator switches on the ones this
//! business actually needs. Install kitchen → Kitchen shows up; uninstall it → it goes away.
//!
//! Three properties are load-bearing and every one of them is fixed here:
//!
//! 1. **Opt-in.** A declared role lands in the catalogue **inactive**. Nobody is handed a role
//!    they never asked for, and it is what leaves room for the blueprint to pre-activate the
//!    right set per vertical (hub#354).
//! 2. **Activation never MINTS a role.** Only what an installed module declares can be switched
//!    on: the write door is not a place to invent role keys.
//! 3. **A declared role never administers the hub.** The guard of hub#347/#351 stays alive on
//!    this side too — activating a role is not a way around it.
use erplora_db::testutil::{fresh_db, TestDb};
use erplora_runtime::hub_users::{is_admin_role, NewHubUser, BASE_ROLES};
use erplora_runtime::roles::RoleSource;
use erplora_runtime::{Runtime, RuntimeError};

/// A module folder with just its `module.json` — enough for the installer.
fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-role-catalog-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

/// The kitchen module of the PLAN: declares its own roles and grants against them.
const KITCHEN: &str = r#"{
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
}"#;

/// The shape of the ~24 published manifests: three base keys, no `roles` block.
const INVENTORY: &str = r#"{
  "id":"inventory",
  "name":"Inventory",
  "version":"1.0.0",
  "role_permissions":{
    "admin":["*"],
    "manager":["inventory.view_product","inventory.add_product"],
    "employee":["inventory.view_product"]
  }
}"#;

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn install(rt: &mut Runtime, manifest: &str) -> String {
    let dir = fixture(manifest);
    let id = rt.install_from_dir(&dir).await.expect("el módulo instala");
    std::fs::remove_dir_all(dir).unwrap();
    id
}

async fn keys(rt: &Runtime) -> Vec<String> {
    rt.role_catalog()
        .await
        .unwrap()
        .into_iter()
        .map(|r| r.key)
        .collect()
}

async fn entry(rt: &Runtime, key: &str) -> Option<erplora_runtime::roles::CatalogRole> {
    rt.role_catalog()
        .await
        .unwrap()
        .into_iter()
        .find(|r| r.key == key)
}

#[tokio::test]
async fn the_catalogue_is_the_core_base_plus_what_the_installed_modules_declare() {
    let mut rt = runtime("hub-roles").await;
    install(&mut rt, KITCHEN).await;

    assert_eq!(
        keys(&rt).await,
        vec!["admin", "manager", "employee", "kitchen", "shift_lead"],
        "base catalogue first and in its own order, the declared ones after it"
    );

    let kitchen = entry(&rt, "kitchen").await.unwrap();
    assert_eq!(kitchen.label, "Kitchen", "the label the manifest declared");
    assert_eq!(kitchen.extends, "employee");
    assert_eq!(kitchen.source, RoleSource::Module("kitchen".into()));

    let shift_lead = entry(&rt, "shift_lead").await.unwrap();
    assert_eq!(shift_lead.extends, "manager");

    for base in BASE_ROLES {
        let it = entry(&rt, base).await.unwrap();
        assert_eq!(it.source, RoleSource::Core);
        assert!(it.active, "a base role is always live in every hub");
        assert_eq!(it.extends, *base, "a base role hangs from itself");
    }
}

#[tokio::test]
async fn a_hub_whose_modules_declare_no_role_keeps_exactly_the_three_base_roles() {
    let mut rt = runtime("hub-roles").await;
    install(&mut rt, INVENTORY).await;

    let catalogue = rt.role_catalog().await.unwrap();
    assert_eq!(
        catalogue.iter().map(|r| r.key.as_str()).collect::<Vec<_>>(),
        BASE_ROLES.to_vec(),
        "the ~24 published modules declare no role: nothing new shows up"
    );
    assert!(catalogue.iter().all(|r| r.active));
}

#[tokio::test]
async fn a_declared_role_lands_inactive_until_the_administrator_switches_it_on() {
    let mut rt = runtime("hub-roles").await;
    install(&mut rt, KITCHEN).await;

    assert!(
        !entry(&rt, "kitchen").await.unwrap().active,
        "opt-in: installing a module never activates its roles on its own"
    );

    rt.set_role_active("kitchen", true, "user-1").await.unwrap();

    assert!(entry(&rt, "kitchen").await.unwrap().active);
    assert!(
        !entry(&rt, "shift_lead").await.unwrap().active,
        "activation is per role, not per module"
    );

    // …and switching it back off is just as explicit.
    rt.set_role_active("kitchen", false, "user-1").await.unwrap();
    assert!(!entry(&rt, "kitchen").await.unwrap().active);
}

#[tokio::test]
async fn the_activation_is_persisted_and_survives_a_restart() {
    let shared = TestDb::new().await;

    {
        let mut rt = Runtime::with_hub_id(Box::new(shared.adapter().await), "hub-roles");
        rt.ensure_system_tables().await.unwrap();
        install(&mut rt, KITCHEN).await;
        rt.set_role_active("kitchen", true, "user-1").await.unwrap();
    }

    // A brand-new runtime over the SAME database = the hub restarting.
    let mut rt = Runtime::with_hub_id(Box::new(shared.adapter().await), "hub-roles");
    rt.ensure_system_tables().await.unwrap();
    install(&mut rt, KITCHEN).await;

    assert!(
        entry(&rt, "kitchen").await.unwrap().active,
        "the administrator's choice lives in the database, not in memory"
    );
}

#[tokio::test]
async fn the_activation_is_scoped_to_its_own_hub() {
    let shared = TestDb::new().await;

    let mut a = Runtime::with_hub_id(Box::new(shared.adapter().await), "hub-A");
    a.ensure_system_tables().await.unwrap();
    install(&mut a, KITCHEN).await;
    a.set_role_active("kitchen", true, "user-1").await.unwrap();

    let mut b = Runtime::with_hub_id(Box::new(shared.adapter().await), "hub-B");
    b.ensure_system_tables().await.unwrap();
    install(&mut b, KITCHEN).await;

    assert!(entry(&a, "kitchen").await.unwrap().active);
    assert!(
        !entry(&b, "kitchen").await.unwrap().active,
        "one hub switching a role on says nothing about the hub next door"
    );
}

#[tokio::test]
async fn activation_never_mints_a_role_no_installed_module_declares() {
    let mut rt = runtime("hub-roles").await;
    install(&mut rt, KITCHEN).await;

    let error = rt
        .set_role_active("superadmin", true, "user-1")
        .await
        .expect_err("the write door is not a place to invent role keys");
    assert!(
        matches!(
            &error,
            RuntimeError::InvalidField { field, reason, .. }
                if field == "role_key" && reason == "unknown"
        ),
        "the refusal is a structured unknown-role rejection: {error}"
    );
    assert!(
        error.to_string().contains("superadmin"),
        "the refusal names the role: {error}"
    );
    assert!(
        !keys(&rt).await.contains(&"superadmin".to_string()),
        "a refused activation leaves nothing behind"
    );
}

#[tokio::test]
async fn a_base_role_is_always_live_and_cannot_be_switched_off() {
    let mut rt = runtime("hub-roles").await;
    install(&mut rt, KITCHEN).await;

    for base in BASE_ROLES {
        let error = rt
            .set_role_active(base, false, "user-1")
            .await
            .expect_err("switching off a base role would leave the hub unusable");
        assert!(
            error.to_string().contains(base),
            "the refusal names the role: {error}"
        );
        // …and says WHY, because "base role" and "nobody declares it" are different answers: the
        // first means never, the second means install the module that declares it. A refusal the
        // administrator cannot act on is a refusal that gets read as a bug.
        assert!(
            matches!(
                &error,
                RuntimeError::InvalidField { field, reason, .. }
                    if field == "role_key" && reason == "immutable"
            ),
            "the refusal says, by code, that a base role cannot be switched off: {error}"
        );
        assert!(
            entry(&rt, base).await.unwrap().active,
            "`{base}` stays live no matter what"
        );
    }
}

#[tokio::test]
async fn uninstalling_a_module_retires_its_roles_and_clears_their_activation() {
    let mut rt = runtime("hub-roles").await;
    install(&mut rt, KITCHEN).await;
    rt.set_role_active("kitchen", true, "user-1").await.unwrap();
    let cook = rt
        .create_hub_user(&NewHubUser {
            name: "Marta Ruiz".into(),
            role: "kitchen".into(),
            pin: "4821".into(),
            // Un rol que declara un módulo es del personal LOCAL: el SaaS no sabe ponerlo en una
            // membresía, así que un usuario de CUENTA no puede llevarlo (hub#356).
            local: true,
            ..Default::default()
        })
        .await
        .unwrap();

    rt.uninstall("kitchen").await.unwrap();

    assert!(
        !keys(&rt).await.contains(&"shift_lead".to_string()),
        "nobody carries `shift_lead`, so it leaves the catalogue with its module"
    );
    let kitchen = entry(&rt, "kitchen").await.unwrap();
    assert_eq!(
        kitchen.source,
        RoleSource::InUse,
        "a role somebody still carries stays VISIBLE, but no module declares it any more"
    );
    assert!(
        !kitchen.active,
        "the module is gone: the role it declared is off"
    );

    // The person is NOT touched: re-roling somebody behind their back is the one thing that
    // would be worse than an orphan role. What they lose is the permissions the module granted,
    // which is strictly narrower — never an escalation.
    let user = rt
        .list_hub_users()
        .await
        .unwrap()
        .into_iter()
        .find(|u| u.id == cook)
        .expect("the user survives the uninstall");
    assert_eq!(user.role, "kitchen");
    assert!(user.is_active);
    assert!(rt.permissions_for_role("kitchen").is_empty());

    // Reinstalling brings the role back — INACTIVE. The activation was cleared with the module,
    // so a package installed later cannot inherit an approval given to the previous one.
    install(&mut rt, KITCHEN).await;
    let kitchen = entry(&rt, "kitchen").await.unwrap();
    assert_eq!(kitchen.source, RoleSource::Module("kitchen".into()));
    assert!(
        !kitchen.active,
        "coming back from an uninstall asks the administrator again"
    );
}

#[tokio::test]
async fn a_role_two_modules_declare_survives_uninstalling_only_one_of_them() {
    let mut rt = runtime("hub-roles").await;
    install(
        &mut rt,
        r#"{"id":"tables","name":"Tables","version":"2.2.7",
            "roles":[{"key":"waiter","label":"Waiter","extends":"employee"}],
            "role_permissions":{"waiter":["tables.view_table"]}}"#,
    )
    .await;
    install(
        &mut rt,
        r#"{"id":"kds","name":"KDS","version":"1.0.0",
            "roles":[{"key":"waiter","label":"Waiter","extends":"employee"}],
            "role_permissions":{"waiter":["kds.view_ticket"]}}"#,
    )
    .await;
    rt.set_role_active("waiter", true, "user-1").await.unwrap();

    rt.uninstall("kds").await.unwrap();

    let waiter = entry(&rt, "waiter").await.unwrap();
    assert_eq!(
        waiter.source,
        RoleSource::Module("tables".into()),
        "`tables` still declares it, so the role is still declared"
    );
    assert!(
        waiter.active,
        "retiring one declarer must not switch off a role another module still declares"
    );
}

#[tokio::test]
async fn the_permissions_of_a_role_are_the_union_of_what_the_installed_modules_grant_it() {
    let mut rt = runtime("hub-roles").await;
    // `tables` INVENTS the role; `sales` only GRANTS against it — declaring and granting are
    // different axes on purpose, so no module needs to know the roles it did not invent.
    install(
        &mut rt,
        r#"{"id":"tables","name":"Tables","version":"2.2.7",
            "roles":[{"key":"waiter","label":"Waiter","extends":"employee"}],
            "role_permissions":{"waiter":["tables.view_table","tables.open_table"]}}"#,
    )
    .await;
    install(
        &mut rt,
        r#"{"id":"sales","name":"Sales","version":"3.0.0",
            "role_permissions":{"waiter":["sales.add_sale"],"employee":["sales.view_sale"]}}"#,
    )
    .await;
    rt.set_role_active("waiter", true, "user-1").await.unwrap();

    let waiter = rt
        .list_hub_roles()
        .await
        .unwrap()
        .into_iter()
        .find(|r| r.name == "waiter")
        .expect("the declared role is listed with the base ones");
    assert_eq!(
        waiter.permissions, 3,
        "two from `tables` plus one from `sales`"
    );
    assert_eq!(waiter.label, "Waiter");
    assert!(waiter.active);
    assert_eq!(
        waiter.members, 0,
        "nobody carries it yet: activating a role is not assigning it"
    );
    // A waiter is not a cashier: `sales` grants key by key, so what it did NOT give `waiter`
    // stays out of the union however many modules are installed.
    let granted = rt.permissions_for_role("waiter");
    assert!(granted.contains("sales.add_sale"));
    assert!(!granted.contains("sales.take_payment"));
}

#[tokio::test]
async fn an_inactive_declared_role_cannot_be_handed_to_a_person() {
    let mut rt = runtime("hub-roles").await;
    install(&mut rt, KITCHEN).await;

    let error = rt
        .create_hub_user(&NewHubUser {
            name: "Marta Ruiz".into(),
            role: "kitchen".into(),
            pin: "4821".into(),
            // Un rol que declara un módulo es del personal LOCAL: el SaaS no sabe ponerlo en una
            // membresía, así que un usuario de CUENTA no puede llevarlo (hub#356).
            local: true,
            ..Default::default()
        })
        .await
        .expect_err("a role nobody switched on is not live in this hub")
        .to_string();
    assert!(error.contains("kitchen"), "the refusal names the role: {error}");

    rt.set_role_active("kitchen", true, "user-1").await.unwrap();
    rt.create_hub_user(&NewHubUser {
        name: "Marta Ruiz".into(),
        role: "kitchen".into(),
        pin: "4821".into(),
        local: true,
        ..Default::default()
    })
    .await
    .expect("once it is live, it can be handed out");
}

#[tokio::test]
async fn a_free_role_no_module_declares_keeps_being_assignable() {
    // No regression for hubs that already carry hand-typed roles (`cashier`, `waiter`…) from
    // before there was a catalogue: only what a module DECLARES is gated by activation.
    let mut rt = runtime("hub-roles").await;
    install(&mut rt, KITCHEN).await;

    rt.create_hub_user(&NewHubUser {
        name: "Marta Ruiz".into(),
        role: "cashier".into(),
        pin: "4821".into(),
        local: true,
        ..Default::default()
    })
    .await
    .expect("a role no installed module declares is not gated by the catalogue");
}

#[tokio::test]
async fn no_role_of_the_catalogue_ever_administers_the_hub() {
    let mut rt = runtime("hub-roles").await;
    // The most generous grant a manifest can write, on a role it invented.
    install(
        &mut rt,
        r#"{"id":"kitchen","name":"Kitchen","version":"2.3.1",
            "roles":[{"key":"chef","label":"Chef","extends":"manager"}],
            "role_permissions":{"chef":["*"]}}"#,
    )
    .await;
    rt.set_role_active("chef", true, "user-1").await.unwrap();

    assert!(
        !is_admin_role("chef"),
        "administering the hub is granted by the hub, never by a manifest — and never by \
         switching a role on"
    );
    for role in rt.role_catalog().await.unwrap() {
        if role.source == RoleSource::Core {
            continue;
        }
        assert!(
            !is_admin_role(&role.extends),
            "`{}` hangs from `{}`: no declared role resolves to an administrator",
            role.key,
            role.extends
        );
    }
}
