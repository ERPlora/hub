//! KCS · install — what the REAL installer accepts, and what it refuses by name.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! Installing is the first promise the kernel makes to a module: everything the manifest declares
//! is registered, and everything it declares WRONG is refused loudly, naming the element — never
//! dropped in silence, which is the failure mode `RuntimeError::ManifestUnknownField` exists for.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::testutil::fresh_db;
use erplora_runtime::{ModuleStatus, Runtime};
use kernel_fixture::{broken_copy, install_fixture, MODULE_ID};

#[tokio::test]
async fn installing_registers_every_declared_surface_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let id = install_fixture(&mut rt).await;
    assert_eq!(id, MODULE_ID);

    let reg = rt.registry();
    assert!(
        reg.is_active(MODULE_ID),
        "a freshly installed module is active"
    );
    assert!(
        reg.get_query("kfx.items.list").is_some(),
        "the query is registered"
    );
    for command in [
        "kfx.item.create",
        "kfx.item.archive",
        "kfx.items.bulk",
        "kfx._insert_item",
        "kfx._log_created",
    ] {
        assert!(
            reg.get_command(command).is_some(),
            "the command `{command}` is registered"
        );
    }
    for permission in ["kfx.read", "kfx.write", "kfx.bulk"] {
        assert!(
            reg.permissions.contains(permission),
            "the permission `{permission}` is registered"
        );
    }
    assert_eq!(
        reg.listeners_for("kfx.item.created"),
        vec!["kfx._log_created".to_string()],
        "the listener is wired to the module's own command"
    );
    assert_eq!(reg.module_version(MODULE_ID), "1.1.0");
}

/// The wasm bytes travel from the package into the registry — and only for the command that
/// declares a handler.
#[tokio::test]
async fn the_handler_binary_reaches_the_registry_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let bulk = rt
        .registry()
        .get_command("kfx.items.bulk")
        .expect("registered");
    let bytes = bulk
        .wasm
        .as_ref()
        .expect("kfx.items.bulk carries its handler bytes");
    assert_eq!(&bytes[..4], b"\0asm", "a real WebAssembly binary");

    let create = rt
        .registry()
        .get_command("kfx.item.create")
        .expect("registered");
    assert!(
        create.wasm.is_none(),
        "a SQL-only command carries no binary"
    );
}

/// The fixture is the kernel's own module: it must install with a clean bill of health. A warning
/// here means the kernel does not understand something the KCS itself declares.
#[tokio::test]
async fn the_fixture_installs_without_manifest_warnings_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let info = rt
        .modules()
        .into_iter()
        .find(|m| m.id == MODULE_ID)
        .expect("installed");
    assert_eq!(info.status, ModuleStatus::Active);
    assert_eq!(info.version, "1.1.0");
    assert!(
        info.manifest_warnings.is_empty(),
        "the kernel's own fixture must not warn: {:?}",
        info.manifest_warnings
    );
}

/// 🔴 Proof the guard catches the positive: a field the core does not understand inside a command
/// changes what RUNS, so the install is refused NAMING the path — it is not dropped in silence.
#[tokio::test]
async fn install_refuses_an_unknown_field_naming_it_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let broken = broken_copy("unknown-field", |m| {
        m["commands"]["kfx.item.create"]["validates_stock"] = serde_json::json!(true);
    });

    let err = rt
        .install_from_dir(broken.path())
        .await
        .expect_err("a command clause this core cannot honour is refused")
        .to_string();
    assert!(
        err.contains("validates_stock") && err.contains(MODULE_ID),
        "the refusal names the module and the clause: {err}"
    );
}

/// 🔴 Proof the guard catches the positive: a listener may only run the module's OWN command.
#[tokio::test]
async fn install_refuses_a_listener_on_a_foreign_command_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let broken = broken_copy("foreign-listener", |m| {
        m["events"]["listen"]["kfx.item.created"]["command"] =
            serde_json::json!("inventory.stock.decrease");
    });

    let err = rt
        .install_from_dir(broken.path())
        .await
        .expect_err("reacting by running another module's command is not a manifest line")
        .to_string();
    assert!(
        err.contains("kfx.item.created") && err.contains("inventory.stock.decrease"),
        "the refusal names the event and the foreign command: {err}"
    );
}

/// A module that is not installed is a different answer from a query that does not exist: the SDK's
/// `queryOptional` depends on the distinction (ADR-0127).
#[tokio::test]
async fn an_uninstalled_module_is_not_a_broken_contract_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.expect("system tables");

    let err = rt
        .execute_query(
            "kfx.items.list",
            &erplora_db::Params::new(),
            &kernel_fixture::admin(),
        )
        .await
        .expect_err("nothing is installed yet");
    assert!(
        matches!(
            err,
            erplora_runtime::RuntimeError::ModuleNotInstalled { .. }
        ),
        "got {err:?}"
    );

    install_fixture(&mut rt).await;
    match rt
        .execute_query(
            "kfx.items.missing",
            &erplora_db::Params::new(),
            &kernel_fixture::admin(),
        )
        .await
        .expect_err("an unknown query of an installed module is a broken contract, not an absence")
    {
        erplora_runtime::RuntimeError::QueryNotFound(name) => {
            assert_eq!(name, "kfx.items.missing", "the refusal names the query")
        }
        other => panic!("expected QueryNotFound naming the query, got {other:?}"),
    }
}
