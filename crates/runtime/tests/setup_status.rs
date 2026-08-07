//! hub#369 — `hub.setup.status`: the ONE query behind the onboarding checklist.
//!
//! ADR-0063 is **extended, not replaced**. What changes is WHERE the computation lives and WHAT it
//! covers. Today it is a loop in the browser (`apps/web/src/lib/setup-status.ts`) firing N queries
//! from the client, and it only knows about modules — so the three things that belong to nobody's
//! module (your apps, your business identity, your team) are invisible to it, and the widget and
//! the assistant each build their own idea of the state.
//!
//! These tests pin the contract that replaces it:
//!
//!  * The core declares its own items **in Rust**, so a brand-new hub with zero modules still has a
//!    checklist. That is the only moment the checklist matters most, and it is exactly the moment
//!    the module-only design says nothing.
//!  * Module items are the ADR-0063 `setup` block, **unioned** in — not a second system.
//!  * The list comes back **already ordered and already filtered**. If the widget and the assistant
//!    each decided the order, they would diverge; and a module that is not installed, or that does
//!    not apply to this country, must not show up at all.
//!  * **Best-effort, never half-done.** A module query that fails (no permission, early boot) omits
//!    its item instead of reporting it as pending. A false "you are missing X" is worse than a gap.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

/// The `hub.` namespace gate: every principal with a LOCAL session carries it
/// (`identity::session_permissions`), an API key never does.
const SESSION: &str = "hub.users.view";

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

fn ctx(hub_id: &str, permissions: &[&str]) -> RequestContext {
    RequestContext::new(hub_id, "u1", permissions.iter().map(|p| p.to_string()))
}

/// Runs the query and returns the single status document.
async fn status(rt: &Runtime, ctx: &RequestContext) -> Json {
    let rows = rt
        .execute_query("hub.setup.status", &Params::new(), ctx)
        .await
        .expect("the core answers the setup status");
    assert_eq!(
        rows.len(),
        1,
        "the status is ONE document (items + counters), not one row per item"
    );
    rows.into_iter().next().unwrap()
}

fn items(doc: &Json) -> &Vec<Json> {
    doc["items"].as_array().expect("`items` is an array")
}

fn keys(doc: &Json) -> Vec<String> {
    items(doc)
        .iter()
        .map(|i| i["key"].as_str().unwrap_or_default().to_string())
        .collect()
}

fn item<'a>(doc: &'a Json, key: &str) -> Option<&'a Json> {
    items(doc).iter().find(|i| i["key"] == key)
}

fn must<'a>(doc: &'a Json, key: &str) -> &'a Json {
    item(doc, key).unwrap_or_else(|| panic!("item `{key}` missing from {:?}", keys(doc)))
}

/// Writes a throwaway module package: `module.json` plus its query files.
fn module_fixture(manifest: Json, sql_files: &[(&str, &str)]) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-setup-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::write(dir.join("module.json"), manifest.to_string()).unwrap();
    for (rel, sql) in sql_files {
        std::fs::write(dir.join(rel), sql).unwrap();
    }
    dir
}

/// A module whose whole purpose is to declare a `setup` block. `configured` decides whether its
/// check passes; `extra` is merged into the `setup` block so each test can vary one field.
fn setup_module(id: &str, configured: bool, extra: Json) -> PathBuf {
    let mut setup = json!({
        "query": format!("{id}.config.get"),
        "configured_when": [{ "field": "ready", "truthy": true }],
        "title": format!("Configure {id}"),
        "description": format!("Finish setting up {id}."),
        "icon": "settings-outline",
        "route": format!("/m/{id}/settings"),
        "permission": format!("{id}.configure")
    });
    for (k, v) in extra.as_object().cloned().unwrap_or_default() {
        setup.as_object_mut().unwrap().insert(k, v);
    }
    module_fixture(
        json!({
            "id": id,
            "name": id,
            "version": "1.0.0",
            "permissions": [format!("{id}.configure")],
            "queries": {
                format!("{id}.config.get"): {
                    "permission": format!("{id}.configure"),
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": setup
        }),
        &[(
            "queries/config_get.sql",
            // A row is always produced; only the value of `ready` changes.
            &format!("SELECT {} AS ready", i32::from(configured)),
        )],
    )
}

// ── The core half: a hub with nothing installed still has a checklist ─────────────────────────

#[tokio::test]
async fn a_hub_with_no_modules_at_all_still_gets_its_core_checklist() {
    // The module-only design of ADR-0063 says NOTHING here, and this is the first screen a new
    // customer sees. The three core items are declared in Rust precisely so they do not depend on
    // anybody having installed anything.
    let rt = runtime("hub-setup").await;
    let doc = status(&rt, &ctx("hub-setup", &[SESSION])).await;

    assert_eq!(
        keys(&doc),
        vec!["apps", "business_identity", "team"],
        "the core items are fixed and come back in the order the business needs them"
    );
    for key in ["apps", "business_identity", "team"] {
        assert_eq!(must(&doc, key)["state"], "pending", "{key} is not done yet");
        assert_eq!(must(&doc, key)["source"], "core");
        assert!(
            must(&doc, key)["module_id"].is_null(),
            "a core item belongs to no module"
        );
    }
    assert_eq!(doc["total"], 3);
    assert_eq!(doc["pending"], 3);
    assert_eq!(
        doc["blocking_pending"], 0,
        "the ⛔ list is core-owned and still empty (hub#370 fills it)"
    );
}

#[tokio::test]
async fn the_core_items_flip_to_done_when_the_hub_is_actually_set_up() {
    let rt = runtime("hub-setup").await;
    let ctx = ctx("hub-setup", &[SESSION]);

    // 1 · Your apps — at least one installed module.
    let dir = setup_module("inventory", true, json!({}));
    let mut rt = rt;
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    assert_eq!(must(&status(&rt, &ctx).await, "apps")["state"], "done");

    // 4 · Your business data — the SAME two settings the fiscal precondition reads (ADR-0203), so
    // the checklist can never promise a gate that the runtime does not enforce.
    let mut updates = serde_json::Map::new();
    updates.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    updates.insert("business_tax_id".into(), json!("B12345678"));
    rt.set_settings(&updates, "u1").await.unwrap();
    assert_eq!(
        must(&status(&rt, &ctx).await, "business_identity")["state"],
        "done"
    );

    // 8 · Your team — at least one hub user besides the administrator.
    rt.get_or_link_cloud_user("cloud-1", "Ioan", "admin", None, None)
        .await
        .unwrap();
    assert_eq!(
        must(&status(&rt, &ctx).await, "team")["state"],
        "pending",
        "the administrator alone is not a team"
    );
    rt.create_user("Marta", "1234", "employee", None)
        .await
        .unwrap();

    let doc = status(&rt, &ctx).await;
    assert_eq!(must(&doc, "team")["state"], "done");
    assert_eq!(doc["pending"], 0, "everything the core asks for is done");
}

#[tokio::test]
async fn the_business_identity_item_needs_both_halves_like_the_fiscal_gate_does() {
    // Half an identity is not an identity: the precondition of ADR-0203 demands legal name AND tax
    // id, so a checklist that ticked on either one would lie about what the runtime will accept.
    let rt = runtime("hub-setup").await;
    let ctx = ctx("hub-setup", &[SESSION]);

    let mut only_name = serde_json::Map::new();
    only_name.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    rt.set_settings(&only_name, "u1").await.unwrap();
    assert_eq!(
        must(&status(&rt, &ctx).await, "business_identity")["state"],
        "pending",
        "a legal name without a tax id does not let you invoice"
    );

    let mut with_id = serde_json::Map::new();
    with_id.insert("business_tax_id".into(), json!("B12345678"));
    rt.set_settings(&with_id, "u1").await.unwrap();
    assert_eq!(
        must(&status(&rt, &ctx).await, "business_identity")["state"],
        "done"
    );
}

// ── The union: module items are the ADR-0063 `setup` block, not a second system ───────────────

#[tokio::test]
async fn an_installed_module_setup_block_joins_the_core_items() {
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", false, json!({ "order": 20 }));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "pricing.configure"])).await;
    let pricing = must(&doc, "pricing.setup");

    assert_eq!(
        pricing["source"], "module",
        "the item says who declared it, so a consumer never has to guess"
    );
    assert_eq!(pricing["module_id"], "pricing");
    assert_eq!(pricing["state"], "pending", "`ready` is 0 → not configured");
    assert_eq!(pricing["required"], true, "`required` defaults to true");
    assert_eq!(pricing["title"], "Configure pricing");
    assert_eq!(pricing["route"], "/m/pricing/settings");
    assert_eq!(pricing["icon"], "settings-outline");
    assert_eq!(doc["total"], 4, "three core items + the module one");
}

#[tokio::test]
async fn the_module_item_is_done_when_its_own_query_says_so() {
    // The check is the module's OWN declarative query, run through the dispatcher with the caller's
    // permissions — the same evaluation the browser did, moved server-side. Zero mocks.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "pricing.configure"])).await;
    assert_eq!(must(&doc, "pricing.setup")["state"], "done");
}

#[tokio::test]
async fn an_optional_module_item_is_listed_too_and_says_it_is_optional() {
    // Deliberate change from the browser loop, which SKIPPED `required: false` entirely because its
    // only surface was an alert. The checklist is not an alert: 🟡 recommended items belong on it
    // (folded behind "see all" by the widget, hub#372). Dropping them here would make the list
    // unable to describe the hub.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("printing", false, json!({ "required": false }));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "printing.configure"])).await;
    assert_eq!(must(&doc, "printing.setup")["required"], false);
}

#[tokio::test]
async fn a_module_without_a_setup_block_contributes_nothing_but_still_counts_as_an_app() {
    // 22 of the 24 published modules have no `setup` block. They must keep working untouched: no
    // item, no error — and they still make "your apps" done.
    let mut rt = runtime("hub-setup").await;
    let dir = module_fixture(
        json!({ "id": "customers", "name": "Customers", "version": "1.0.0" }),
        &[],
    );
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION])).await;
    assert_eq!(keys(&doc), vec!["apps", "business_identity", "team"]);
    assert_eq!(must(&doc, "apps")["state"], "done");
}

#[tokio::test]
async fn a_module_that_is_installed_but_inactive_does_not_contribute_its_item() {
    // An inactive module is an absence, not a pending task: its screens are gone, so asking the
    // user to go and configure it would send them to a dead route.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", false, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    rt.deactivate("pricing").await.unwrap();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "pricing.configure"])).await;
    assert!(
        item(&doc, "pricing.setup").is_none(),
        "an inactive module has no pending configuration: {:?}",
        keys(&doc)
    );
}

// ── Already filtered ──────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn an_item_outside_the_country_of_the_hub_never_shows_up() {
    // "VeriFactu outside Spain does not show." The Hub is international and knows no concrete
    // module, so the applicability is DECLARED (`countries`), not hardcoded in the core.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("verifactu", false, json!({ "countries": ["ES"] }));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    let ctx = ctx("hub-setup", &[SESSION, "verifactu.configure"]);

    // The hub default is ES, so it applies…
    assert!(
        item(&status(&rt, &ctx).await, "verifactu.setup").is_some(),
        "a Spanish hub does get the Spanish item"
    );

    // …and a French hub must never be told to configure a Spanish obligation.
    let mut updates = serde_json::Map::new();
    updates.insert("country_code".into(), json!("FR"));
    rt.set_settings(&updates, "u1").await.unwrap();
    let doc = status(&rt, &ctx).await;
    assert!(
        item(&doc, "verifactu.setup").is_none(),
        "a French hub must not be asked for a Spanish obligation: {:?}",
        keys(&doc)
    );
}

#[tokio::test]
async fn an_item_without_a_declared_country_applies_everywhere() {
    // Absent `countries` = every country. The 22 modules that will declare a `setup` block without
    // one must not silently disappear outside Spain.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("inventory", false, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let mut updates = serde_json::Map::new();
    updates.insert("country_code".into(), json!("FR"));
    rt.set_settings(&updates, "u1").await.unwrap();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "inventory.configure"])).await;
    assert!(item(&doc, "inventory.setup").is_some(), "{:?}", keys(&doc));
}

#[tokio::test]
async fn an_item_the_session_cannot_configure_is_not_offered() {
    // Only alert whoever can act. Telling a cashier that the price rules are missing is noise they
    // cannot clear.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", false, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION])).await;
    assert!(
        item(&doc, "pricing.setup").is_none(),
        "no `pricing.configure` permission → the item is not offered: {:?}",
        keys(&doc)
    );
}

#[tokio::test]
async fn reading_the_check_is_not_the_same_as_being_able_to_fix_it() {
    // The `permission` of the `setup` block is the one to CONFIGURE, which is deliberately narrower
    // than the one to READ the check. A manager who can see the tax screen but not edit it would
    // otherwise get an item they cannot clear — and the module's own query, which only guards
    // reading, would happily answer them. So the filter has to be its own thing, not a side effect
    // of the query's gate.
    let mut rt = runtime("hub-setup").await;
    let dir = module_fixture(
        json!({
            "id": "pricing",
            "name": "pricing",
            "version": "1.0.0",
            "permissions": ["pricing.view", "pricing.configure"],
            "queries": {
                "pricing.config.get": {
                    // Reading the state only needs `view`…
                    "permission": "pricing.view",
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": {
                "query": "pricing.config.get",
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": "Configure pricing",
                "route": "/m/pricing/settings",
                // …but only `configure` can act on it.
                "permission": "pricing.configure"
            }
        }),
        &[("queries/config_get.sql", "SELECT 0 AS ready")],
    );
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let viewer = ctx("hub-setup", &[SESSION, "pricing.view"]);
    assert!(
        rt.execute_query("pricing.config.get", &Params::new(), &viewer)
            .await
            .is_ok(),
        "the viewer really can run the check — the filter is not just the query's gate in disguise"
    );
    let doc = status(&rt, &viewer).await;
    assert!(
        item(&doc, "pricing.setup").is_none(),
        "whoever cannot configure it is not asked to: {:?}",
        keys(&doc)
    );

    // And whoever can configure it does get it.
    let admin = ctx("hub-setup", &[SESSION, "pricing.view", "pricing.configure"]);
    assert!(item(&status(&rt, &admin).await, "pricing.setup").is_some());
}

// ── Best-effort: a gap beats a false "you are missing X" ──────────────────────────────────────

#[tokio::test]
async fn a_module_whose_setup_query_fails_is_omitted_instead_of_reported_as_pending() {
    // The behaviour of today's browser loop, preserved. The module declares a `setup` pointing at a
    // query that BLOWS UP (broken SQL — the shape of an early boot or a half-applied migration).
    // Reporting it as pending would send the user to fix something that may already be fine.
    let mut rt = runtime("hub-setup").await;
    let dir = module_fixture(
        json!({
            "id": "broken",
            "name": "broken",
            "version": "1.0.0",
            "permissions": ["broken.configure"],
            "queries": {
                "broken.config.get": {
                    "permission": "broken.configure",
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": {
                "query": "broken.config.get",
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": "Configure broken",
                "route": "/m/broken/settings",
                "permission": "broken.configure"
            }
        }),
        &[(
            "queries/config_get.sql",
            "SELECT ready FROM a_table_that_does_not_exist",
        )],
    );
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "broken.configure"])).await;
    assert!(
        item(&doc, "broken.setup").is_none(),
        "a failing check omits its item, it never invents a pending one: {:?}",
        keys(&doc)
    );
    assert_eq!(
        doc["total"], 3,
        "and it does not leave a hole in the counters either"
    );
}

#[tokio::test]
async fn a_setup_block_pointing_at_a_query_that_does_not_exist_is_omitted_too() {
    // Same rule, different failure: the module declares a `setup` whose query it never wrote. That
    // is the module's bug, and it must not become the user's task.
    let mut rt = runtime("hub-setup").await;
    let dir = module_fixture(
        json!({
            "id": "typo",
            "name": "typo",
            "version": "1.0.0",
            "setup": {
                "query": "typo.does.not.exist",
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": "Configure typo",
                "route": "/m/typo/settings"
            }
        }),
        &[],
    );
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION])).await;
    assert!(item(&doc, "typo.setup").is_none(), "{:?}", keys(&doc));
}

#[tokio::test]
async fn a_check_with_no_row_at_all_is_pending_not_omitted() {
    // The one failure that IS an answer: the query ran fine and returned nothing. ADR-0063 says no
    // row = not configured, and that is a real "you still have to do this", not a gap.
    let mut rt = runtime("hub-setup").await;
    let dir = module_fixture(
        json!({
            "id": "empty",
            "name": "empty",
            "version": "1.0.0",
            "permissions": ["empty.configure"],
            "queries": {
                "empty.config.get": {
                    "permission": "empty.configure",
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": {
                "query": "empty.config.get",
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": "Configure empty",
                "route": "/m/empty/settings",
                "permission": "empty.configure"
            }
        }),
        &[(
            "queries/config_get.sql",
            "SELECT 1 AS ready WHERE 1 = 0",
        )],
    );
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "empty.configure"])).await;
    assert_eq!(must(&doc, "empty.setup")["state"], "pending");
}

// ── Already ordered ───────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_list_comes_back_already_ordered_by_the_core() {
    // Neither the widget nor the assistant decides the order: if both did, they would diverge. The
    // order is the one the business needs — sell first, invoice after — and the core owns the
    // scale, so a module can only take the slot the core reserved for it.
    let mut rt = runtime("hub-setup").await;
    for (id, order) in [("cash_register", 90), ("pricing", 20)] {
        let dir = setup_module(id, false, json!({ "order": order }));
        rt.install_from_dir(&dir).await.unwrap();
        std::fs::remove_dir_all(&dir).ok();
    }
    // No `order` declared → it lands after everything the core placed, never in front of it.
    let dir = setup_module("unknown_module", false, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(
        &rt,
        &ctx(
            "hub-setup",
            &[
                SESSION,
                "pricing.configure",
                "cash_register.configure",
                "unknown_module.configure",
            ],
        ),
    )
    .await;

    assert_eq!(
        keys(&doc),
        vec![
            "apps",                  // 10 · core
            "pricing.setup",           // 20 · module
            "business_identity",     // 40 · core
            "team",                  // 80 · core
            "cash_register.setup",   // 90 · module
            "unknown_module.setup",  // undeclared → last
        ]
    );
}

// ── The contract itself ───────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_document_and_the_item_carry_exactly_the_contracted_keys() {
    // Eight module repos are about to declare a `setup` block against this shape, and four more
    // issues (hub#370-#375) read it. Pinning the key set makes an accidental rename a red test
    // instead of eight silent breakages.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", false, json!({ "order": 20 }));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "pricing.configure"])).await;

    let mut doc_keys: Vec<&str> = doc.as_object().unwrap().keys().map(String::as_str).collect();
    doc_keys.sort_unstable();
    assert_eq!(doc_keys, ["blocking_pending", "items", "pending", "total"]);

    for it in items(&doc) {
        let mut item_keys: Vec<&str> = it.as_object().unwrap().keys().map(String::as_str).collect();
        item_keys.sort_unstable();
        assert_eq!(
            item_keys,
            [
                "actions",
                "description",
                "icon",
                "key",
                "module_id",
                "order",
                "required",
                "route",
                "source",
                "state",
                "title",
            ],
            "every item carries every key, so a consumer never branches on presence"
        );
    }
}

#[tokio::test]
async fn every_item_travels_with_the_ways_of_getting_it_done() {
    // `actions` belongs to the ITEM, not to the session: the assistant has to know what it can
    // offer without guessing, and the widget has to render the same three speeds to the same place.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", false, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION, "pricing.configure"])).await;

    assert_eq!(
        must(&doc, "apps")["actions"],
        json!(["template", "catalog"]),
        "you fill an empty hub from a blueprint or from the catalogue, never by hand"
    );
    assert_eq!(
        must(&doc, "business_identity")["actions"],
        json!(["manual", "assistant"])
    );
    assert_eq!(
        must(&doc, "pricing.setup")["actions"],
        json!(["manual", "assistant"]),
        "a module item is always reachable by its own screen, and the assistant can drive it"
    );
    for it in items(&doc) {
        assert!(
            !it["actions"].as_array().unwrap().is_empty(),
            "an item with no way to complete it is a dead end: {}",
            it["key"]
        );
    }
}

// ── The gate ──────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn only_a_principal_with_a_local_session_reads_the_setup_status() {
    // Same door as the rest of the reserved `hub.` namespace. A third-party API key carries the
    // scope its administrator gave it and nothing else: it does not get to inventory what this
    // business has left to configure.
    let rt = runtime("hub-setup").await;
    let stranger = ctx("hub-setup", &["inventory.view_product"]);

    let err = rt
        .execute_query("hub.setup.status", &Params::new(), &stranger)
        .await
        .unwrap_err()
        .to_string();
    assert!(err.to_lowercase().contains("permis"), "{err}");
}
