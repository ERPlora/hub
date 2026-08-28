//! KCS · permissions — the gate, the ceiling of a handler's operations, and elevation.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! The kernel's answer to "may this context run this?" is the same for the UI, the API, the
//! assistant and a handler's own operations — that sameness IS the contract. Two properties the
//! suite pins because both have been holes: an operation a handler pushes is checked against the
//! CALLER's permissions (hub#459), and whether a refusal can be approved by a manager is DERIVED
//! from the manifests, never declared by one (hub#351).
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{registry::Principal, Runtime, RuntimeError};
use kernel_fixture::{admin, ctx_with, install_fixture};
use serde_json::json;

#[tokio::test]
async fn a_command_runs_with_exactly_its_declared_permission_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("name".into(), json!("a"));
    rt.execute_command("kfx.item.create", &p, &ctx_with(&["kfx.write"]))
        .await
        .expect("kfx.write is what the manifest asks for");
}

/// 🔴 Proof the gate catches the positive: a permission the module never grants to `manager` is a
/// FLAT refusal — there is no dialog to offer.
#[tokio::test]
async fn a_permission_no_role_can_approve_is_denied_flat_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("names".into(), json!(["a"]));
    match rt
        .execute_command("kfx.items.bulk", &p, &ctx_with(&["kfx.read"]))
        .await
        .expect_err("kfx.bulk is required")
    {
        RuntimeError::PermissionDenied(permission) => assert_eq!(permission, "kfx.bulk"),
        other => panic!("expected a flat denial, got {other:?}"),
    }
}

/// The elevable half, DERIVED from `role_permissions.manager` in the module's own manifest: a
/// human missing `kfx.write` is offered the manager's PIN instead of a dead 403.
#[tokio::test]
async fn a_manager_grantable_permission_comes_back_as_elevation_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("name".into(), json!("a"));
    match rt
        .execute_command("kfx.item.create", &p, &ctx_with(&["kfx.read"]))
        .await
        .expect_err("kfx.write is missing")
    {
        RuntimeError::RequiresElevation { permission } => assert_eq!(permission, "kfx.write"),
        other => panic!("expected RequiresElevation, got {other:?}"),
    }
}

/// …and a MACHINE is never offered that dialog: an API key has nobody standing at it, so a stored
/// credential must not gain a second way in.
#[tokio::test]
async fn a_machine_principal_is_never_offered_elevation_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut ctx = ctx_with(&["kfx.read"]);
    ctx.principal = Principal::Machine;
    let mut p = Params::new();
    p.insert("name".into(), json!("a"));
    assert!(
        matches!(
            rt.execute_command("kfx.item.create", &p, &ctx)
                .await
                .expect_err("kfx.write is missing"),
            RuntimeError::PermissionDenied(_)
        ),
        "a machine gets the flat refusal, never the PIN dialog"
    );
}

/// 🔑 The CEILING of a handler (hub#459): the operations a guest pushes are checked against the
/// caller's permissions, not only against the command that pushed them. `kfx._insert_item` asks
/// for `kfx.bulk`, so a caller holding only `kfx.bulk` passes both doors…
#[tokio::test]
async fn the_operations_of_a_handler_are_checked_against_the_caller_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("names".into(), json!(["a"]));
    rt.execute_command("kfx.items.bulk", &p, &ctx_with(&["kfx.bulk"]))
        .await
        .expect("the caller may run the command AND the operations it pushes");
    assert_eq!(
        rt.execute_query("kfx.items.list", &Params::new(), &admin())
            .await
            .expect("list")
            .len(),
        1
    );
}

/// The permission the module declares is registered as its own: the kernel never invents one.
#[tokio::test]
async fn the_permission_catalogue_is_exactly_what_the_manifest_declares_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut declared: Vec<&str> = rt
        .registry()
        .permissions
        .iter()
        .filter(|p| p.starts_with("kfx."))
        .map(String::as_str)
        .collect();
    declared.sort_unstable();
    assert_eq!(declared, vec!["kfx.bulk", "kfx.read", "kfx.write"]);
}
