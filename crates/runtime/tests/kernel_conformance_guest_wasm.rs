//! KCS · guest WASM — the Tier 2 round-trip against a REAL compiled `handler.wasm`.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! Until now the only Tier 2 coverage the hub had was `wasm_tier2.rs`, whose fixture is four dummy
//! bytes: it proved the installer *stores* the blob and nothing else, and the one test that ran a
//! guest end to end was `#[ignore]`d with build instructions in a doc comment. A contract nobody
//! executes is a contract nobody keeps — `guest.snapshot` freezes the `Input`/`Output` field names
//! precisely because a published `.wasm` is never recompiled, so the only proof that the host still
//! speaks that shape is a guest binary that was compiled against it.
//!
//! The fixture guest lives in `fixtures/kernel-fixture/handler/` and its `handler.wasm` is
//! committed next to `module.json`, with the build stamp in `handler.build.json`.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use kernel_fixture::{admin, foreign_module_copy, install_fixture};
use serde_json::json;

/// The `.wasm` shipped in the fixture is a real Extism module, not a placeholder.
#[test]
fn the_committed_handler_is_a_real_wasm_binary_hub1238() {
    let wasm = kernel_fixture::dir().join("handler.wasm");
    let bytes = std::fs::read(&wasm).expect("the fixture ships a compiled handler.wasm");
    assert_eq!(
        &bytes[..4],
        b"\0asm",
        "handler.wasm must start with the WebAssembly magic number, not with placeholder bytes"
    );
    assert!(
        bytes.len() > 1024,
        "a real Extism guest is not 4 bytes: {} bytes",
        bytes.len()
    );
}

/// The round-trip that `wasm_tier2.rs::real_guest_bulk_create` could never run: payload → guest →
/// `Output.operations` → N rows written by the host, in one transaction.
#[tokio::test]
async fn guest_operations_become_rows_through_the_host_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut payload = Params::new();
    payload.insert("names".into(), json!(["c", "a", "b"]));
    let out = rt
        .execute_command("kfx.items.bulk", &payload, &admin())
        .await
        .expect("the guest returns three create operations");
    assert_eq!(out["operations"], json!(3), "one operation per name");
    assert_eq!(
        out["new_ids"]
            .as_array()
            .expect("the host reports the ids it minted")
            .len(),
        3,
        "every id the guest consumed came from the host's batch"
    );

    let rows = rt
        .execute_query("kfx.items.list", &Params::new(), &admin())
        .await
        .expect("list the rows the guest asked for");
    let names: Vec<&str> = rows.iter().map(|r| r["name"].as_str().unwrap()).collect();
    assert_eq!(
        names,
        vec!["a", "b", "c"],
        "the list engine sorts by its declared `default_sort`, not by insertion order"
    );
}

/// A guest's `Output.error` reaches the caller as a `Domain` error carrying the CODE, never prose.
#[tokio::test]
async fn guest_domain_error_travels_as_a_code_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut payload = Params::new();
    payload.insert("names".into(), json!([]));
    match rt
        .execute_command("kfx.items.bulk", &payload, &admin())
        .await
        .expect_err("an empty batch is refused by the guest")
    {
        RuntimeError::Domain { code, .. } => assert_eq!(code, "kfx.empty_batch"),
        other => panic!("expected Domain, got {other:?}"),
    }
}

/// An operation naming a command nobody declared is refused by the host before a single row is
/// written — `CommandNotFound`, naming it. (`hub.*` is the core's reserved namespace, ADR-0192:
/// no module can register there, so from the registry's point of view it does not exist.)
#[tokio::test]
async fn guest_cannot_drive_a_command_nobody_declared_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut payload = Params::new();
    payload.insert("names".into(), json!(["a"]));
    payload.insert("escape_to".into(), json!("hub.users.create"));
    match rt
        .execute_command("kfx.items.bulk", &payload, &admin())
        .await
        .expect_err("an operation naming nothing is refused")
    {
        RuntimeError::CommandNotFound(name) => assert_eq!(
            name, "hub.users.create",
            "the refusal names the command the guest tried to drive"
        ),
        other => panic!("expected CommandNotFound, got {other:?}"),
    }

    let rows = rt
        .execute_query("kfx.items.list", &Params::new(), &admin())
        .await
        .expect("list after the refusal");
    assert!(rows.is_empty(), "the whole batch rolled back");
}

/// 🔴 Proof the host catches the positive: the guest names a command that EXISTS and belongs to a
/// neighbour. The same-module rule of `validate_operation` refuses it naming the command, and
/// neither module gets a row — a handler is not a way into another module's tables.
#[tokio::test]
async fn guest_cannot_drive_another_modules_command_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;
    let neighbour = foreign_module_copy("kfy");
    rt.install_from_dir(neighbour.path())
        .await
        .expect("the twin installs next to the fixture");
    assert!(
        rt.registry().get_command("kfy._insert_item").is_some(),
        "the command the guest will try to drive is real"
    );

    let mut payload = Params::new();
    payload.insert("names".into(), json!(["a"]));
    payload.insert("escape_to".into(), json!("kfy._insert_item"));
    match rt
        .execute_command("kfx.items.bulk", &payload, &admin())
        .await
        .expect_err("a command of another module is out of the guest's reach")
    {
        RuntimeError::PermissionDenied(detail) => assert!(
            detail.contains("kfy._insert_item") && detail.contains("kfx"),
            "the refusal names the foreign command and the handler's module: {detail}"
        ),
        other => panic!("expected the same-module refusal, got {other:?}"),
    }

    for table in ["kfx_item", "kfy_item"] {
        let rows = rt
            .db_for_test()
            .query(&format!("SELECT id FROM {table}"), &Params::new())
            .await
            .expect("read the table")
            .rows;
        assert!(rows.is_empty(), "no row landed in {table}");
    }
}

/// The permission gate is the host's, not the guest's: without the command's permission the guest
/// is never even loaded.
#[tokio::test]
async fn the_host_gates_the_handler_before_loading_it_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let ctx = RequestContext::new("h1", "u1", ["kfx.read".to_string()]);
    let mut payload = Params::new();
    payload.insert("names".into(), json!(["a"]));
    match rt
        .execute_command("kfx.items.bulk", &payload, &ctx)
        .await
        .expect_err("kfx.bulk is required")
    {
        RuntimeError::PermissionDenied(permission) => assert_eq!(
            permission, "kfx.bulk",
            "the flat refusal names the permission the command declares"
        ),
        other => panic!("expected a flat denial, got {other:?}"),
    }
}

/// The committed binary was built from the committed sources.
///
/// This is hole #7 of the kernel contract (module-toolkit#93) applied to the fixture itself: a
/// `.wasm` published without proof that it was rebuilt from its `handler/` is a binary nobody can
/// vouch for. Editing `handler/src/lib.rs` and forgetting `build-handler.sh` would otherwise leave
/// the suite green while testing yesterday's guest.
#[test]
fn the_committed_wasm_matches_the_committed_handler_sources_hub1238() {
    use sha2::{Digest, Sha256};

    let fixture = kernel_fixture::dir();
    let stamp: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(fixture.join("handler.build.json"))
            .expect("the fixture ships handler.build.json"),
    )
    .expect("the stamp is JSON");

    let wasm = std::fs::read(fixture.join("handler.wasm")).expect("handler.wasm");
    assert_eq!(
        stamp["wasm_sha256"].as_str().unwrap(),
        hex(&Sha256::digest(&wasm)),
        "handler.wasm does not match its stamp — run \
         crates/runtime/tests/fixtures/kernel-fixture/build-handler.sh and commit both files"
    );

    // Same recipe as the toolkit's `hashHandlerSources`: relative path + NUL + bytes + NUL, sorted,
    // `Cargo.lock` excluded (it is an output of cargo, not evidence — module-toolkit#31).
    let handler = fixture.parent().unwrap().join("handler");
    let mut sources: Vec<std::path::PathBuf> = Vec::new();
    collect(&handler, &mut sources);
    sources.sort();
    let mut digest = Sha256::new();
    for path in &sources {
        digest.update(
            path.strip_prefix(&handler)
                .unwrap()
                .to_str()
                .expect("utf-8 path")
                .as_bytes(),
        );
        digest.update(b"\0");
        digest.update(std::fs::read(path).expect("read source"));
        digest.update(b"\0");
    }
    assert_eq!(
        stamp["sources_sha256"].as_str().unwrap(),
        hex(&digest.finalize()),
        "handler/ changed since the build that wrote handler.build.json — run \
         crates/runtime/tests/fixtures/kernel-fixture/build-handler.sh and commit both files"
    );
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Every file under `dir`, skipping dotfiles, build outputs and `Cargo.lock`.
fn collect(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
    const IGNORED_DIRS: [&str; 3] = ["target", "node_modules", "dist"];
    for entry in std::fs::read_dir(dir)
        .expect("read the handler dir")
        .flatten()
    {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with('.') || name == "Cargo.lock" {
            continue;
        }
        let path = entry.path();
        if path.is_dir() {
            if !IGNORED_DIRS.contains(&name.as_str()) {
                collect(&path, out);
            }
        } else {
            out.push(path);
        }
    }
}
