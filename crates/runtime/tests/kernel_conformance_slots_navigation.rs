//! KCS · navigation, slots and the module's `locales/`.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! What the kernel owes the shell: a navigation entry per active module (and NONE from an inactive
//! one), a label resolved through the module's own `locales/<lang>.json` with English as the
//! canonical fallback (ADR-0055), and the cross-module slot contract — coupling by slot NAME, never
//! by an import, which is what makes `provides_slots` a contract rather than a dependency.
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

/// `provides_slots` and `navigation[].chrome` are carried verbatim in the manifest the shell reads:
/// the kernel transports the contract, it does not reinterpret it.
#[tokio::test]
async fn the_slot_and_chrome_contract_travel_verbatim_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let raw: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(kernel_fixture::dir().join("module.json")).expect("manifest"),
    )
    .expect("parse");

    let slot = &raw["provides_slots"][0];
    assert_eq!(slot["slot"], serde_json::json!("kfx.items.aside"));
    assert_eq!(
        slot["component"],
        serde_json::json!("kfx-aside"),
        "the filler is the module's OWN component: coupling by slot name, never by import"
    );
    assert_eq!(
        raw["navigation"][0]["chrome"],
        serde_json::json!(["fullscreen"]),
        "chrome is an opt-in to a control the SHELL owns; the module never ships the button"
    );

    // And the runtime installed the module with that manifest without complaining about either
    // block — a warning here would mean the kernel silently dropped part of the shell's contract.
    let info = rt
        .modules()
        .into_iter()
        .find(|m| m.id == MODULE_ID)
        .expect("installed");
    assert!(
        info.manifest_warnings.is_empty(),
        "{:?}",
        info.manifest_warnings
    );
}
