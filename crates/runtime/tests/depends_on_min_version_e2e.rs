//! hub#681 — `depends_on` can carry a MINIMUM version, and the installer enforces it.
//!
//! Until now `depends_on` was a list of ids: there was no way to say "I need `inventory` >=
//! 1.2.20". The first versioned cross-module contract (sales#68: `sales` reads
//! `inventory.products.for_sale`, which exists since inventory 1.2.20) made the hole concrete —
//! a hub with new `sales` and old `inventory` cannot charge for catalogue items, each module
//! correct in isolation. The window opens with auto-update (hub#400), so the floor must land
//! before it.
//!
//! Contract under test:
//!  - a plain string entry keeps meaning "any installed version" (every published manifest stays
//!    valid, untouched);
//!  - `{ "id": "...", "min_version": "..." }` is the versioned form; both may be mixed;
//!  - the installer refuses a module whose dependency is installed BELOW the floor, naming the
//!    module, the dependency, the floor and what is installed;
//!  - at or above the floor it installs as always;
//!  - a floor the runtime cannot read is refused, not read as "fine" (same direction as
//!    `compatibility.min_erplora_version`, hub#521).
use std::path::PathBuf;

use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_depmin")
        .join(name)
}

async fn runtime_with_base() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("base")).await.expect("install base 1.2.0");
    rt
}

/// The happy path: the installed dependency meets the floor and the module installs.
#[tokio::test]
async fn a_dependency_at_or_above_the_floor_installs() {
    let mut rt = runtime_with_base().await;
    rt.install_from_dir(&fixture("wants_ok"))
        .await
        .expect("base 1.2.0 satisfies `base >= 1.2.0`");
}

/// The hole of hub#681: the dependency is installed but OLDER than the contract needs. The
/// refusal must name all four facts so the operator can act without reading the runtime's source.
#[tokio::test]
async fn a_dependency_below_the_floor_is_refused_naming_the_versions() {
    let mut rt = runtime_with_base().await;
    let err = rt
        .install_from_dir(&fixture("wants_newer"))
        .await
        .expect_err("base 1.2.0 does not satisfy `base >= 1.3.0`")
        .to_string();
    for fact in ["wants_newer", "base", "1.3.0", "1.2.0"] {
        assert!(
            err.contains(fact),
            "the refusal must name `{fact}`, got: {err}"
        );
    }
}

/// A floor nobody can read is a claim the runtime cannot check, and it is refused — not read as
/// "any version works". Same direction as an unreadable `compatibility.min_erplora_version`.
#[tokio::test]
async fn an_unreadable_floor_is_refused() {
    let mut rt = runtime_with_base().await;
    let err = rt
        .install_from_dir(&fixture("wants_bad"))
        .await
        .expect_err("`not-a-version` is not a floor the runtime can enforce")
        .to_string();
    assert!(
        err.contains("not-a-version"),
        "the refusal must quote the unreadable floor, got: {err}"
    );
}

/// The two authoring shapes parse side by side, and the ids read the same either way — which is
/// what keeps every consumer of `depends_on` (topo-sort, cascades, `/api/modules`) working
/// unchanged on published manifests.
#[test]
fn plain_and_versioned_entries_parse_side_by_side() {
    let manifest: erplora_runtime::manifest::Manifest = serde_json::from_value(serde_json::json!({
        "id": "consumer", "name": "Consumer", "version": "1.0.0",
        "depends_on": ["taxes", { "id": "inventory", "min_version": "1.2.20" }]
    }))
    .expect("both shapes parse");
    let ids: Vec<&str> = manifest.depends_on.iter().map(|d| d.id.as_str()).collect();
    assert_eq!(ids, ["taxes", "inventory"]);
    assert_eq!(manifest.depends_on[0].min_version, None, "a plain id floors nothing");
    assert_eq!(manifest.depends_on[1].min_version.as_deref(), Some("1.2.20"));
}

/// An object entry with a field this core does not know is refused at parse: a dependency entry
/// changes what the installer enforces, which is the refuse tier of ADR-0286.
#[test]
fn an_unknown_field_in_a_versioned_entry_is_refused() {
    let err = serde_json::from_value::<erplora_runtime::manifest::Manifest>(serde_json::json!({
        "id": "consumer", "name": "Consumer", "version": "1.0.0",
        "depends_on": [{ "id": "inventory", "max_version": "2.0.0" }]
    }))
    .expect_err("`max_version` is not part of the dependency contract")
    .to_string();
    assert!(err.contains("max_version"), "the refusal names the field, got: {err}");
}
