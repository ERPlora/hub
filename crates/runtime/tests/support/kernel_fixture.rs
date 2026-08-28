//! Shared helpers of the **Kernel Conformance Suite** (KCS) — ERPlora/hub#1238.
//!
//! Kernel contract («El Hub se CIERRA como KERNEL») §5: the kernel proves ITS contract with a
//! fixture module of its own, never with `sales`, `kitchen` or `invoice`. A module's behaviour is
//! the module's business; what the hub owes is the surface underneath it — install, migrate,
//! query/list/row, command gates, permissions, events, slots/navigation, guest WASM, error codes
//! and hot update.
//!
//! The fixture lives in `tests/fixtures/kernel-fixture/<version>/` and ships two versions on
//! purpose: `1.0.0` is the module before the retirement, `1.1.0` adds the `contract` migration, the
//! Tier 2 handler, the events, the navigation and the error catalogue. Installing `1.0.0` and then
//! `1.1.0` IS the update path, so the same two directories serve every area of the suite.
#![allow(dead_code)] // each test binary uses the slice of this it needs

use std::path::PathBuf;

use erplora_runtime::{RequestContext, Runtime};

/// The fixture module's id. Short on purpose: it prefixes every table, permission, event and
/// error code, and the suite asserts on those names.
pub const MODULE_ID: &str = "kfx";

/// The version every area of the suite installs unless it is testing the update itself.
pub const CURRENT: &str = "1.1.0";

/// The version before the retirement — the left-hand side of the update test.
pub const PREVIOUS: &str = "1.0.0";

/// Directory of the fixture at [`CURRENT`].
pub fn dir() -> PathBuf {
    dir_at(CURRENT)
}

/// Directory of the fixture at `version`.
pub fn dir_at(version: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("kernel-fixture")
        .join(version)
}

/// Installs the fixture at [`CURRENT`] through the REAL installer and returns its id.
pub async fn install_fixture(rt: &mut Runtime) -> String {
    install_fixture_at(rt, CURRENT).await
}

/// Installs the fixture at `version` through the REAL installer (`install_from_dir`) — never by
/// poking the registry, which is how a conformance test stops proving anything.
pub async fn install_fixture_at(rt: &mut Runtime, version: &str) -> String {
    rt.install_from_dir(&dir_at(version))
        .await
        .unwrap_or_else(|e| panic!("install the kernel fixture {version}: {e}"))
}

/// A context that carries every permission — the shape of the runtime calling itself.
pub fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// A context with exactly the permissions listed and nothing else.
pub fn ctx_with(permissions: &[&str]) -> RequestContext {
    RequestContext::new(
        "h1",
        "u1",
        permissions
            .iter()
            .map(|p| p.to_string())
            .collect::<Vec<_>>(),
    )
}

/// A **full copy** of the fixture at [`CURRENT`] in a scratch directory, with `mutate` applied to
/// its `module.json`. This is how the suite proves each guard catches the positive: break exactly
/// one clause of a manifest that is otherwise valid, and check the kernel refuses NAMING it.
///
/// It copies the whole package rather than writing a manifest from scratch so a refusal can never
/// come from a missing file — a test that "passes" because the SQL was not there proves nothing.
pub fn broken_copy(tag: &str, mutate: impl FnOnce(&mut serde_json::Value)) -> Scratch {
    let dir = std::env::temp_dir().join(format!("erplora-kcs-{tag}-{}", uuid::Uuid::new_v4()));
    copy_tree(&dir_at(CURRENT), &dir);

    let manifest_path = dir.join("module.json");
    let mut manifest: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&manifest_path).expect("read manifest"))
            .expect("parse manifest");
    mutate(&mut manifest);
    std::fs::write(
        &manifest_path,
        serde_json::to_string_pretty(&manifest).expect("serialise manifest"),
    )
    .expect("write manifest");
    Scratch(dir)
}

/// A scratch directory that removes itself, so a failing assertion does not leak one per run.
pub struct Scratch(std::path::PathBuf);

impl Scratch {
    pub fn path(&self) -> &std::path::Path {
        &self.0
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn copy_tree(from: &std::path::Path, to: &std::path::Path) {
    std::fs::create_dir_all(to).expect("scratch dir");
    for entry in std::fs::read_dir(from).expect("read fixture").flatten() {
        let target = to.join(entry.file_name());
        if entry.path().is_dir() {
            copy_tree(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).expect("copy fixture file");
        }
    }
}
