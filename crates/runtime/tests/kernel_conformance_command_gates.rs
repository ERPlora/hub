//! KCS · command gates — `expect_rows`, transactions and the internal-command door.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! A declarative command is SQL plus the gates around it, and the gates are the kernel's, not the
//! module's: `expect_rows` turns "the UPDATE matched nothing" into a domain refusal with a code
//! instead of a silent success, the transaction rolls the whole thing back when any statement
//! fails, and a command whose last segment starts with `_` is not a public door.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{Runtime, RuntimeError};
use kernel_fixture::{admin, install_fixture};
use serde_json::json;

async fn rows(rt: &Runtime) -> usize {
    rt.db_for_test()
        .query("SELECT id FROM kfx_item", &Params::new())
        .await
        .expect("count rows")
        .rows
        .len()
}

/// 🔑 `expect_rows` catching the positive: the archive matched nothing, so the command FAILS with
/// the declared code rather than reporting success over a no-op.
#[tokio::test]
async fn expect_rows_turns_a_no_op_into_the_declared_code_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("id".into(), json!("no-such-item"));
    match rt
        .execute_command("kfx.item.archive", &p, &admin())
        .await
        .expect_err("nothing matched")
    {
        RuntimeError::Domain { code, .. } => assert_eq!(
            code, "kfx.not_found",
            "the code is the one the manifest declared, not prose"
        ),
        other => panic!("expected the declared domain code, got {other:?}"),
    }
}

/// And the same gate stays quiet when the row IS there: a guard that always fires is a guard
/// nobody keeps.
#[tokio::test]
async fn expect_rows_passes_when_the_row_is_there_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut create = Params::new();
    create.insert("name".into(), json!("a"));
    rt.execute_command("kfx.item.create", &create, &admin())
        .await
        .expect("create");
    let id = rt
        .db_for_test()
        .query("SELECT id FROM kfx_item", &Params::new())
        .await
        .unwrap()
        .rows
        .remove(0)["id"]
        .as_str()
        .unwrap()
        .to_string();

    let mut archive = Params::new();
    archive.insert("id".into(), json!(id));
    rt.execute_command("kfx.item.archive", &archive, &admin())
        .await
        .expect("the row is there, the gate lets it through");
}

/// 🔴 Proof the gate catches the positive: archiving the SAME row twice fails the second time —
/// the second UPDATE matches nothing because the first one set `deleted_at`.
#[tokio::test]
async fn archiving_twice_is_refused_by_the_row_gate_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut create = Params::new();
    create.insert("name".into(), json!("a"));
    rt.execute_command("kfx.item.create", &create, &admin())
        .await
        .expect("create");
    let id = rt
        .db_for_test()
        .query("SELECT id FROM kfx_item", &Params::new())
        .await
        .unwrap()
        .rows
        .remove(0)["id"]
        .as_str()
        .unwrap()
        .to_string();

    let mut archive = Params::new();
    archive.insert("id".into(), json!(id));
    rt.execute_command("kfx.item.archive", &archive, &admin())
        .await
        .expect("first archive");
    assert!(matches!(
        rt.execute_command("kfx.item.archive", &archive, &admin())
            .await
            .expect_err("the second one matches nothing"),
        RuntimeError::Domain { .. }
    ));
}

/// A command whose last segment starts with `_` is not a public door: it is reachable by the
/// outbox relay, the scheduler and a handler's operations, never by an external caller.
#[tokio::test]
async fn an_internal_command_is_not_a_public_door_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("id".into(), json!("forged"));
    p.insert("name".into(), json!("straight in"));
    let err = rt
        .execute_command("kfx._insert_item", &p, &admin())
        .await
        .expect_err("`_` means the front door is shut, even for a `*` context");
    assert!(
        matches!(err, RuntimeError::InternalCommand(_)),
        "got {err:?}"
    );
    assert_eq!(rows(&rt).await, 0, "and nothing was written");
}

/// The transaction is the kernel's: a batch whose operations are refused halfway leaves no rows
/// behind. Driven through the real handler, which is where a partial write would hurt.
#[tokio::test]
async fn a_refused_batch_leaves_no_rows_behind_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("names".into(), json!(["a", "b", "c"]));
    p.insert("escape_to".into(), json!("kfx.nowhere"));
    rt.execute_command("kfx.items.bulk", &p, &admin())
        .await
        .expect_err("the operations name a command that does not exist");
    assert_eq!(rows(&rt).await, 0, "the whole transaction rolled back");
}

/// The dispatcher refuses a command nobody declared, naming it — never a silent no-op.
#[tokio::test]
async fn an_undeclared_command_is_refused_naming_it_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let err = rt
        .execute_command("kfx.item.explode", &Params::new(), &admin())
        .await
        .expect_err("no such command");
    assert!(
        err.to_string().contains("kfx.item.explode"),
        "the refusal names the command: {err}"
    );
}
