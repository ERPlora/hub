//! KCS · navigation, slots and the module's `locales/`.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! What the kernel owes the shell: a navigation entry per active module (and NONE from an inactive
//! one), a label resolved through the module's own `locales/<lang>.json` with English as the
//! canonical fallback (ADR-0055), and the cross-module slot contract — coupling by slot NAME, never
//! by an import, which is what makes `provides_slots` a contract rather than a dependency.
//!
//! `provides_slots` and `navigation[].chrome` are NOT typed by this crate (see `manifest.rs`'s
//! `ROOT_FIELDS`/`NAV_FIELDS`): the runtime only has to recognise the two blocks at install time
//! and carry them to the shell verbatim. Whether they actually TRAVEL correctly is proven through
//! the real door the shell calls (`GET /modules/:id/module.json`) in
//! `crates/server/tests/kernel_fixture_slots_chrome_real_door_hub1266.rs` — not in this crate, which
//! has no HTTP layer to serve them from. ERPlora/hub#1266.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use kernel_fixture::{install_fixture, MODULE_ID};

#[tokio::test]
async fn the_navigation_entry_carries_what_the_shell_needs_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let nav = rt.registry().active_navigation();
    let entry = nav
        .iter()
        .find(|e| e.module_id == MODULE_ID)
        .expect("the active module contributes its navigation entry");
    assert_eq!(entry.nav.id, "items");
    assert_eq!(entry.nav.component, "kfx-items");
    assert_eq!(
        entry.nav.permission.as_deref(),
        Some("kfx.read"),
        "the manifest says who the tab is for; the runtime still revalidates the query behind it"
    );
    assert_eq!(entry.nav.icon.as_deref(), Some("ion:list-outline"));
}

/// 🔴 Proof it catches the positive: deactivating the module removes its tab. A shell painting a
/// tab whose module is off is a door that leads nowhere.
#[tokio::test]
async fn a_deactivated_module_contributes_no_navigation_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;
    assert!(rt
        .registry()
        .active_navigation()
        .iter()
        .any(|e| e.module_id == MODULE_ID));

    rt.deactivate(MODULE_ID).await.expect("deactivate");
    assert!(
        !rt.registry()
            .active_navigation()
            .iter()
            .any(|e| e.module_id == MODULE_ID),
        "an inactive module has no tab"
    );

    rt.activate(MODULE_ID).await.expect("activate");
    assert!(
        rt.registry()
            .active_navigation()
            .iter()
            .any(|e| e.module_id == MODULE_ID),
        "and it comes back when the module does"
    );
}

/// The label is resolved through the module's `locales/`, with the manifest (English canonical) as
/// the fallback for a language the module does not ship.
#[tokio::test]
async fn labels_resolve_through_the_modules_locales_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let reg = rt.registry();
    assert_eq!(
        reg.nav_label_localized(MODULE_ID, "items", "Items", "es"),
        "Artículos"
    );
    assert_eq!(
        reg.nav_label_localized(MODULE_ID, "items", "Items", "en"),
        "Items"
    );
    assert_eq!(
        reg.nav_label_localized(MODULE_ID, "items", "Items", "de"),
        "Items",
        "a language the module does not ship falls back to the manifest, never to an empty string"
    );
    assert_eq!(
        reg.module_name_localized(MODULE_ID, "Kernel Conformance Fixture", "es"),
        "Fixture de conformidad del kernel"
    );
}

/// `provides_slots` and `navigation[].chrome` install without a `manifest_warnings` entry: the
/// kernel recognises both blocks (`ROOT_FIELDS`/`NAV_FIELDS` in `manifest.rs`) even though it does
/// not type their contents, because both belong to the shell (ADR-0043/0048). A warning here would
/// mean the kernel silently flagged part of a contract it has already promised to carry.
///
/// This is as far as THIS crate can prove: `erplora-runtime` has no HTTP layer, and the shell never
/// reads either block from anything this crate exposes — it fetches the raw `module.json` from
/// `GET /modules/:id/module.json` (`crates/server`). This test used to also assert on that raw JSON
/// by reading the fixture's OWN file off disk, which proved the fixture, never the kernel
/// (ERPlora/hub#1266) — that assertion now lives in
/// `crates/server/tests/kernel_fixture_slots_chrome_real_door_hub1266.rs`, through the real door.
#[tokio::test]
async fn provides_slots_and_chrome_install_without_warnings_hub1266() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let info = rt
        .modules()
        .into_iter()
        .find(|m| m.id == MODULE_ID)
        .expect("installed");
    assert!(
        info.manifest_warnings.is_empty(),
        "installing a manifest with provides_slots/chrome must not warn: {:?}",
        info.manifest_warnings
    );
}
