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

/// What the CORE items are gated on (hub#435): the one administrative rank the core owns. Granted
/// by `identity::session_permissions` to exactly the roles `hub_users::is_admin_role` accepts —
/// which is the very predicate `server::auth::require_admin_session` asks before letting anybody
/// write a setting, install an app or add a user.
const ADMINISTER: &str = erplora_runtime::hub_users::ADMINISTER_PERMISSION;

/// A session that administers the hub. Most tests here are about WHAT the checklist says, so they
/// run as the person the core items are actually for; the ones about WHO sees what use `[SESSION]`
/// on its own, which is the waiter's session.
const ADMIN_SESSION: &[&str] = &[SESSION, ADMINISTER];

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

/// Writes a throwaway module package: `module.json` plus its query/command files.
fn module_fixture(manifest: Json, sql_files: &[(&str, &str)]) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-setup-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::write(dir.join("module.json"), manifest.to_string()).unwrap();
    for (rel, sql) in sql_files {
        let path = dir.join(rel);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, sql).unwrap();
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

/// A module that asks the host for the business certificate — the shape ADR-0203 keys on when it
/// decides whether the certificate is part of the fiscal precondition. Its check NEVER passes, so
/// the item stays pending across the whole test and only its LEVEL can move.
fn certificate_module(id: &str) -> PathBuf {
    module_fixture(
        json!({
            "id": id,
            "name": id,
            "version": "1.0.0",
            "capabilities": { "certificate": { "purpose": "fiscal-sign" } },
            "permissions": [format!("{id}.configure")],
            "queries": {
                format!("{id}.config.get"): {
                    "permission": format!("{id}.configure"),
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": {
                "query": format!("{id}.config.get"),
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": format!("Configure {id}"),
                "route": format!("/m/{id}/settings"),
                "permission": format!("{id}.configure"),
                "order": 60
            }
        }),
        &[("queries/config_get.sql", "SELECT 0 AS ready")],
    )
}

/// A module that asks for a host capability **and whose own check passes**: everything it can say
/// about itself says "configured". The only thing left between it and doing its job is the switch in
/// Ajustes → Permisos, which is exactly the state hub#1119 found in production.
fn sealing_module(id: &str) -> PathBuf {
    module_fixture(
        json!({
            "id": id,
            "name": id,
            "version": "1.0.0",
            "capabilities": { "certificate": { "purpose": "fiscal-sign" } },
            "permissions": [format!("{id}.configure")],
            "queries": {
                format!("{id}.config.get"): {
                    "permission": format!("{id}.configure"),
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": {
                "query": format!("{id}.config.get"),
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": format!("Configure {id}"),
                "route": format!("/m/{id}/settings"),
                "permission": format!("{id}.configure"),
                "order": 60
            }
        }),
        &[("queries/config_get.sql", "SELECT 1 AS ready")],
    )
}

/// Puts the business certificate in the hub, straight into the system table the gate reads
/// (`_hub_certificate`, ADR-0081). Going through `set_business_certificate` would need the
/// process-global `HUB_SECRETS_KEY`, and what both the gate and the checklist look at is the
/// PRESENCE of the row, never its contents.
async fn load_certificate(rt: &Runtime, hub_id: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    rt.db()
        .execute(
            "INSERT INTO _hub_certificate (hub_id, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES (:hub_id, 'v1:ciphertext', 'v1:ciphertext', '2026-08-07T09:00:00Z', 'hub_user:1')",
            &p,
        )
        .await
        .expect("the business certificate is stored in the hub");
}

/// Feeds the hub a real marketplace answer, exactly as the catalogue proxy does
/// (`crates/server/src/lib.rs`): the HTTP status and the raw body, never a pre-chewed number.
async fn catalogue_answered(rt: &Runtime, status: u16, body: &Json) {
    erplora_runtime::setup_status::record_catalog_response(
        rt.db(),
        status,
        body.to_string().as_bytes(),
    )
    .await
    .expect("recording a catalogue answer never fails the caller");
}

/// A 200 from the marketplace listing `installable` modules this hub can install.
async fn catalogue_offered(rt: &Runtime, installable: usize) {
    let modules: Vec<Json> = (0..installable)
        .map(|i| json!({ "id": format!("module_{i}"), "name": format!("Module {i}") }))
        .collect();
    catalogue_answered(rt, 200, &json!({ "results": modules })).await;
}

/// Writes the same marker by hand with an old timestamp — the shape the hub would carry after the
/// marketplace was asked once, hours ago, and nobody has asked since.
async fn catalogue_offered_hours_ago(rt: &Runtime, installable: u64, hours: i64) {
    let at = chrono::Utc::now() - chrono::Duration::hours(hours);
    erplora_runtime::hub_meta::set(
        rt.db(),
        erplora_runtime::setup_status::CATALOG_OFFER_KEY,
        &json!({ "installable": installable, "at": at.to_rfc3339() }).to_string(),
    )
    .await
    .expect("the stale marker is written");
}

/// Sets the two settings the fiscal precondition of ADR-0203 demands.
async fn set_business_identity(rt: &Runtime) {
    let mut updates = serde_json::Map::new();
    updates.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    updates.insert("business_tax_id".into(), json!("B12345674"));
    rt.set_settings(&updates, "u1").await.unwrap();
}

/// Puts the hub's fiscal profile in an explicit environment (ADR-0360, hub#1087): the
/// certificate arm of ADR-0203 lives in PRODUCTION only — in `testing` there is nothing to
/// authorize — so the tests that assert that ⛔ must say which side of the border they are on.
async fn pin_fiscal_environment(rt: &Runtime, hub_id: &str, environment: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("environment".into(), json!(environment));
    rt.db()
        .execute(
            "INSERT INTO _hub_fiscal_profile (hub_id, system_id, environment) \
             VALUES (:hub_id, :hub_id, :environment) \
             ON CONFLICT (hub_id) DO UPDATE SET environment = :environment",
            &p,
        )
        .await
        .unwrap();
}

/// A module with a Tier-0 command that STAMPS the business identity — the shape
/// `enforce_fiscal_precondition` keys on (`invoice.create_from_sale` in production). Running it is
/// the only way to ask the GATE the same question the checklist answers.
fn identity_stamping_module(id: &str) -> PathBuf {
    module_fixture(
        json!({
            "id": id,
            "name": id,
            "version": "1.0.0",
            "permissions": [format!("{id}.issue")],
            "migrations": { "postgres": ["migrations/pg/001.sql"] },
            "commands": {
                format!("{id}.issue"): {
                    "permission": format!("{id}.issue"),
                    "sql": ["commands/issue.sql"]
                }
            }
        }),
        &[
            (
                "migrations/pg/001.sql",
                "CREATE TABLE billing_doc (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, issuer TEXT NOT NULL)",
            ),
            (
                "commands/issue.sql",
                "INSERT INTO billing_doc (id, hub_id, issuer) VALUES (:id, :hub_id, :business_tax_id)",
            ),
        ],
    )
}

// ── The DEMO: no wall, because it BOOTS with its fiscal identity (hub#684) ────────────────────
//
// The demo used to show the visitor a ⛔ «you need this in order to invoice» whose button led to a
// `409` — back then the demo could not write its identity (that closure was lifted by hub#1848). And
// the expensive half: the sale went through and `invoice.create_from_sale` did not, because it
// stamps `:business_tax_id` and the gate rejected it. Money taken, no document.
//
// The fix is data, not a special case in the checklist: with the two settings written, the item is
// done because it IS done and the gate passes because it has what it asks for. These two tests pin
// the halves TOGETHER — a checklist and a gate that disagree in a demo is the failure this whole
// design keeps failing away from.

#[tokio::test]
async fn a_demo_boots_without_a_wall_because_its_fiscal_identity_is_already_there() {
    let mut rt = runtime("hub-demo").await;
    rt.set_demo_hub(true);
    assert!(
        rt.ensure_demo_fiscal_identity().await.unwrap(),
        "the boot fills in the demo's identity"
    );

    let doc = status(&rt, &ctx("hub-demo", ADMIN_SESSION)).await;
    assert_eq!(
        must(&doc, "business_identity")["state"],
        "done",
        "the ⛔ item is DONE — not hidden and not faked: {doc}"
    );
    assert_eq!(
        doc["blocking_pending"], 0,
        "no wall left, so the blocking strip stays down: {doc}"
    );
}

#[tokio::test]
async fn the_checklist_and_the_gate_agree_in_a_demo() {
    // The invariant of `setup_status`'s module docs, written as a test: if the checklist says the
    // fiscal identity is done, the dispatcher has to accept the transaction that stamps it. Before
    // hub#684 the two disagreed in a demo in the worst possible direction — ⛔ pending forever, and
    // a gate nobody could satisfy.
    let mut rt = runtime("hub-demo").await;
    rt.set_demo_hub(true);
    rt.ensure_demo_fiscal_identity().await.unwrap();

    let dir = identity_stamping_module("billing");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-demo", ADMIN_SESSION)).await;
    assert_eq!(must(&doc, "business_identity")["state"], "done");

    let mut payload = Params::new();
    payload.insert("id".into(), json!("doc-1"));
    rt.execute_command(
        "billing.issue",
        &payload,
        &ctx("hub-demo", &[SESSION, ADMINISTER, "billing.issue"]),
    )
    .await
    .expect("the gate lets the demo issue: the checklist promised nothing was missing");
}

/// 🔴 And the direction that must NOT change: a REAL hub with an empty identity still gets the
/// wall, and its gate still refuses. A demo fix that leaked here would leave a paying business
/// invoicing with a blank issuer, and ADR-0189 does not re-send an accepted record.
#[tokio::test]
async fn a_real_hub_still_gets_the_wall_and_the_refusal() {
    let mut rt = runtime("hub-real").await;
    assert!(!rt.ensure_demo_fiscal_identity().await.unwrap());

    let dir = identity_stamping_module("billing");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-real", ADMIN_SESSION)).await;
    assert_eq!(must(&doc, "business_identity")["state"], "pending");
    assert_eq!(must(&doc, "business_identity")["level"], "legal");
    assert_eq!(doc["blocking_pending"], 1, "the wall is up: {doc}");

    let mut payload = Params::new();
    payload.insert("id".into(), json!("doc-1"));
    let err = rt
        .execute_command(
            "billing.issue",
            &payload,
            &ctx("hub-real", &[SESSION, ADMINISTER, "billing.issue"]),
        )
        .await
        .expect_err("no identity, no fiscal document");
    assert!(
        format!("{err:?}").contains("business_tax_id"),
        "the refusal names what is missing: {err:?}"
    );
}

// ── The core half: a hub with nothing installed still has a checklist ─────────────────────────

#[tokio::test]
async fn a_hub_with_no_modules_at_all_still_gets_its_core_checklist() {
    // The module-only design of ADR-0063 says NOTHING here, and this is the first screen a new
    // customer sees. The three core items are declared in Rust precisely so they do not depend on
    // anybody having installed anything.
    let rt = runtime("hub-setup").await;
    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;

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
        doc["blocking_pending"], 1,
        "of the three, only the business identity has a gate behind it (ADR-0203)"
    );
}

#[tokio::test]
async fn the_core_items_flip_to_done_when_the_hub_is_actually_set_up() {
    let rt = runtime("hub-setup").await;
    let ctx = ctx("hub-setup", ADMIN_SESSION);

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
    updates.insert("business_tax_id".into(), json!("B12345674"));
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
    let ctx = ctx("hub-setup", ADMIN_SESSION);

    let mut only_name = serde_json::Map::new();
    only_name.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    rt.set_settings(&only_name, "u1").await.unwrap();
    assert_eq!(
        must(&status(&rt, &ctx).await, "business_identity")["state"],
        "pending",
        "a legal name without a tax id does not let you invoice"
    );

    let mut with_id = serde_json::Map::new();
    with_id.insert("business_tax_id".into(), json!("B12345674"));
    rt.set_settings(&with_id, "u1").await.unwrap();
    assert_eq!(
        must(&status(&rt, &ctx).await, "business_identity")["state"],
        "done"
    );
}

#[tokio::test]
async fn a_legacy_invalid_tax_id_does_not_tick_the_business_identity_item() {
    // hub#1088: before the door validated the format, `ZZZ999` could be stored — and the setup
    // notice ticked «your business details» on it. The door refuses it now, so the notice
    // cannot keep vouching for a value the runtime itself would not accept any more: the item
    // goes back to pending, which is what sends whoever reads it to the screen that fixes it.
    // The value is written straight into `hub_settings` on purpose: that is exactly the shape
    // of a hub configured before the validation existed (the door would refuse the write).
    let rt = runtime("hub-setup").await;
    let ctx = ctx("hub-setup", ADMIN_SESSION);
    let mut up = serde_json::Map::new();
    up.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    rt.set_settings(&up, "u1").await.unwrap();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("hub-setup"));
    p.insert("value".into(), json!("ZZZ999"));
    rt.db()
        .execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by) \
             VALUES (:hub_id, 'business_tax_id', :value, '2026-01-01T00:00:00Z', 'legacy')",
            &p,
        )
        .await
        .unwrap();

    let doc = status(&rt, &ctx).await;
    assert_eq!(
        must(&doc, "business_identity")["state"],
        "pending",
        "a legacy `ZZZ999` is not a business identity: the notice must not tick it done"
    );
    assert_eq!(doc["blocking_pending"], 1, "the ⛔ is the point: it blocks");
}

// ── The union: module items are the ADR-0063 `setup` block, not a second system ───────────────

#[tokio::test]
async fn an_installed_module_setup_block_joins_the_core_items() {
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", false, json!({ "order": 20 }));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "pricing.configure"]),
    )
    .await;
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

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "pricing.configure"]),
    )
    .await;
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

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "printing.configure"]),
    )
    .await;
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

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
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

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "pricing.configure"]),
    )
    .await;
    assert!(
        item(&doc, "pricing.setup").is_none(),
        "an inactive module has no pending configuration: {:?}",
        keys(&doc)
    );
}

/// hub#1175: `invoice_series` stayed **installed and active** in a hub after its own retirement
/// from the marketplace (ERPlora/invoice#31) — the runtime's own idea of "active" never moved, so
/// its `setup` item kept sending the owner to `/m/invoice_series/list`, a route the dispatcher's
/// entitlement gate (`crates/server::entitlement`, HTTP 402 `module_entitlement_blocked`) refuses
/// at the door. The checklist promised a task the product could not deliver, right next to a
/// SECOND item — `invoice`'s own — with the same title, which is what made it read as a bug and
/// not two unrelated screens.
///
/// The runtime cannot know this on its own (no view of the SaaS's signed claims); the server
/// stamps the blocked ids onto the context, the exact same shape as [`registry::RequestContext`]
/// already uses for `is_active`.
#[tokio::test]
async fn a_module_blocked_by_entitlement_leaves_no_checklist_item_hub1175() {
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("invoice_series", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let mut blocked = ctx(
        "hub-setup",
        &[SESSION, ADMINISTER, "invoice_series.configure"],
    );
    blocked.blocked_modules = std::collections::HashSet::from(["invoice_series".to_string()]);

    let doc = status(&rt, &blocked).await;
    assert!(
        item(&doc, "invoice_series.setup").is_none(),
        "an entitlement-blocked module must not offer a route the dispatcher will refuse: {:?}",
        keys(&doc)
    );
}

/// The other half of hub#1175: entitlement blocking must name the module it blocks, not turn into
/// a blanket filter. A hub whose entitlement blocks nobody (the default, and the common case —
/// dev/local, or a hub with a fresh successful refresh) must keep every module's item exactly as
/// it did before this field existed.
#[tokio::test]
async fn a_module_the_entitlement_does_not_name_keeps_its_checklist_item_hub1175() {
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("invoice", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    // `blocked_modules` defaults empty — nobody stamped it, same as every context before hub#1175.
    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "invoice.configure"]),
    )
    .await;
    assert!(
        item(&doc, "invoice.setup").is_some(),
        "a module the entitlement did not name must keep its item: {:?}",
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
    let ctx = ctx("hub-setup", &[SESSION, ADMINISTER, "verifactu.configure"]);

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

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "inventory.configure"]),
    )
    .await;
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

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
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

    let viewer = ctx("hub-setup", &[SESSION, ADMINISTER, "pricing.view"]);
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
    let admin = ctx(
        "hub-setup",
        &[SESSION, ADMINISTER, "pricing.view", "pricing.configure"],
    );
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

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "broken.configure"]),
    )
    .await;
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

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
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
        &[("queries/config_get.sql", "SELECT 1 AS ready WHERE 1 = 0")],
    );
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "empty.configure"]),
    )
    .await;
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
                ADMINISTER,
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
            "apps",                 // 10 · core
            "pricing.setup",        // 20 · module
            "business_identity",    // 40 · core
            "team",                 // 80 · core
            "cash_register.setup",  // 90 · module
            "unknown_module.setup", // undeclared → last
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

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "pricing.configure"]),
    )
    .await;

    let mut doc_keys: Vec<&str> = doc
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    doc_keys.sort_unstable();
    assert_eq!(
        doc_keys,
        [
            "blocking_pending",
            "items",
            "pending",
            "total",
            "unavailable"
        ],
        "three states need three counters: with only `pending`, `total - pending` reads as done"
    );

    for it in items(&doc) {
        let mut item_keys: Vec<&str> = it.as_object().unwrap().keys().map(String::as_str).collect();
        item_keys.sort_unstable();
        assert_eq!(
            item_keys,
            [
                // Whether THIS session may take those `actions` (hub#435) — the one field of the
                // payload that is about the session and not about the item.
                "actionable",
                "actions",
                "description",
                "icon",
                "key",
                "level",
                "module_id",
                "order",
                // Quién puso los datos que hacen pasar el chequeo (hub#536): el dueño, o una
                // plantilla que alguien importó. Ortogonal al `state` —como `actionable`—, nunca un
                // cuarto estado: `done + pending + unavailable = total` lo leen cuatro superficies.
                "origin",
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

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "pricing.configure"]),
    )
    .await;

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

// ── The three levels: ⛔ legal · 🔴 functional · 🟡 recommended (hub#370) ───────────────────────

#[tokio::test]
async fn the_core_puts_each_of_its_items_on_one_of_the_three_levels() {
    // `required` was never enough: it has two values and the checklist needs three. The one that
    // cannot be a boolean is ⛔ — "the runtime rejects this", which is a fact about the runtime and
    // not an opinion about importance.
    let rt = runtime("hub-setup").await;
    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;

    assert_eq!(
        must(&doc, "business_identity")["level"],
        "legal",
        "no legal name ∧ tax id ⇒ ADR-0203 refuses to emit the document"
    );
    assert_eq!(
        must(&doc, "apps")["level"],
        "functional",
        "an empty hub sells nothing, but nothing REJECTS it either"
    );
    assert_eq!(must(&doc, "team")["level"], "recommended");
}

#[tokio::test]
async fn the_level_of_an_item_does_not_move_when_it_gets_done() {
    // The level says what KIND of item it is, the state says whether it is left to do. Folding the
    // two would make `blocking_pending` unreadable: hub#374 asks "is anything blocking pending?",
    // which only means something if being done is a different axis from being blocking.
    let rt = runtime("hub-setup").await;
    let c = ctx("hub-setup", ADMIN_SESSION);
    set_business_identity(&rt).await;

    let doc = status(&rt, &c).await;
    assert_eq!(must(&doc, "business_identity")["state"], "done");
    assert_eq!(must(&doc, "business_identity")["level"], "legal");
    assert_eq!(
        doc["blocking_pending"], 0,
        "nothing left that the runtime would reject"
    );
}

#[tokio::test]
async fn blocking_means_the_runtime_really_rejects_it_never_just_a_colour() {
    // **The whole rule of hub#370, across two subsystems.** ⛔ is not a strong 🔴: it is the claim
    // that the dispatcher will refuse. The blocking strip (hub#374) cuts the screen on the strength
    // of this count, so if the claim were decorative the product would stop a sale for a label.
    // Here the two are checked against each other: the same hub state that makes the item ⛔ makes
    // `execute_command` fail, and clearing it clears both.
    let mut rt = runtime("hub-setup").await;
    let dir = module_fixture(
        json!({
            "id": "billing",
            "name": "billing",
            "version": "1.0.0",
            "permissions": ["billing.issue"],
            "commands": {
                "billing.issue": {
                    "permission": "billing.issue",
                    "sql": ["commands/issue.sql"]
                }
            }
        }),
        &[(
            "commands/issue.sql",
            // Stamping the hub's business identity into a document IS emitting a fiscal document:
            // the structural trigger of ADR-0203, no manifest flag involved.
            "INSERT INTO billing_doc (issuer_nif, issuer_name) \
             VALUES (:business_tax_id, :business_legal_name)",
        )],
    );
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    rt.db()
        .execute_batch("CREATE TABLE billing_doc (issuer_nif TEXT, issuer_name TEXT);")
        .await
        .unwrap();
    let c = ctx("hub-setup", &[SESSION, ADMINISTER, "billing.issue"]);

    let doc = status(&rt, &c).await;
    assert_eq!(must(&doc, "business_identity")["level"], "legal");
    assert_eq!(doc["blocking_pending"], 1);
    let err = rt
        .execute_command("billing.issue", &Params::new(), &c)
        .await
        .expect_err("the checklist says ⛔, so the dispatcher MUST reject")
        .to_string();
    assert!(
        err.contains("business_tax_id") && err.contains("business_legal_name"),
        "the gate must name what the ⛔ item is asking for: {err}"
    );

    // And the other direction: the moment the item is no longer blocking, the command goes through.
    set_business_identity(&rt).await;
    assert_eq!(status(&rt, &c).await["blocking_pending"], 0);
    rt.execute_command("billing.issue", &Params::new(), &c)
        .await
        .expect("nothing blocking left ⇒ the document is emitted");
}

#[tokio::test]
async fn a_module_never_reaches_the_blocking_level_whatever_its_manifest_says() {
    // The point of keeping the ⛔ list in the core: a third-party module cannot make itself a
    // condition for selling. `required` has exactly two destinations, and neither is ⛔ — including
    // for a module sitting in `order` 50, a slot the plan first sketched as legal.
    let mut rt = runtime("hub-setup").await;
    for (id, extra) in [
        ("invoice_series", json!({ "order": 50, "required": true })),
        ("printing", json!({ "order": 70, "required": false })),
        // A manifest that tries to award itself the level outright. The runtime does not read a
        // `level` from a module at all, so the attempt is not even rejected: it is invisible.
        ("greedy", json!({ "level": "legal", "required": true })),
    ] {
        let dir = setup_module(id, false, extra);
        rt.install_from_dir(&dir).await.unwrap();
        std::fs::remove_dir_all(&dir).ok();
    }

    let doc = status(
        &rt,
        &ctx(
            "hub-setup",
            &[
                SESSION,
                "invoice_series.configure",
                "printing.configure",
                "greedy.configure",
            ],
        ),
    )
    .await;

    assert_eq!(must(&doc, "invoice_series.setup")["level"], "functional");
    assert_eq!(must(&doc, "printing.setup")["level"], "recommended");
    assert_eq!(must(&doc, "greedy.setup")["level"], "functional");
    assert_eq!(
        doc["blocking_pending"], 1,
        "only the core item counts; three modules asked for nothing"
    );
}

#[tokio::test]
async fn the_certificate_arm_of_the_gate_blocks_through_whoever_carries_the_capability() {
    // ADR-0203 has TWO arms, and the second one is not the core's to hold: while a module declaring
    // the `certificate` capability is installed, the gate also demands the loaded certificate. The
    // core decides the level (the module never does) but hangs it on the item that can clear it —
    // otherwise the strip would be silent about a rejection that is going to happen. Since
    // ADR-0360 (hub#1087) this arm is the PRODUCTION one: the test pins the environment, because
    // in `testing` there is nothing to authorize.
    let mut rt = runtime("hub-setup").await;
    pin_fiscal_environment(&rt, "hub-setup", "production").await;
    let dir = certificate_module("verifactu");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    set_business_identity(&rt).await;

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "verifactu.configure"]),
    )
    .await;
    assert_eq!(must(&doc, "verifactu.setup")["level"], "legal");
    assert_eq!(
        doc["blocking_pending"], 1,
        "the identity is done; what is left blocking is the certificate"
    );
}

#[tokio::test]
async fn the_certificate_item_drops_to_functional_the_moment_the_certificate_is_there() {
    // The other half, and the reason the arm is EVALUATED instead of listed: with the certificate
    // loaded the runtime accepts the document, so the item is still pending (it is not switched on
    // yet) but it no longer blocks anything. A ⛔ that does not block is exactly the colour this
    // issue exists to avoid.
    let mut rt = runtime("hub-setup").await;
    let dir = certificate_module("verifactu");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    set_business_identity(&rt).await;
    load_certificate(&rt, "hub-setup").await;

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "verifactu.configure"]),
    )
    .await;
    assert_eq!(
        must(&doc, "verifactu.setup")["state"],
        "pending",
        "still not configured — the level moved, the state did not"
    );
    assert_eq!(must(&doc, "verifactu.setup")["level"], "functional");
    assert_eq!(doc["blocking_pending"], 0);
}

#[tokio::test]
async fn in_the_testing_environment_there_is_no_certificate_wall_and_the_document_goes_out() {
    // **hub#1087, end to end.** A brand-new hub — identity set, certificate-capable module
    // installed, NO certificate — could not issue even one TEST invoice: the gate demanded the
    // certificate without looking at the environment. ADR-0360 drew the border on the
    // environment: in `testing` there is nothing to authorize. Both halves move together — the
    // checklist stops painting the ⛔ that no longer blocks, and the dispatcher lets the
    // identity-stamping command through. Nothing is simulated: the filing to AEAT-testing keeps
    // its own flow, certificate or not.
    let mut rt = runtime("hub-setup").await;
    // The profile a brand-new hub carries: born `testing` (the DDL default the go-live raises
    // to production, ADR-0273 D3).
    pin_fiscal_environment(&rt, "hub-setup", "testing").await;
    let dir = certificate_module("verifactu");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    set_business_identity(&rt).await;
    let issuer_dir = module_fixture(
        json!({
            "id": "billing",
            "name": "billing",
            "version": "1.0.0",
            "permissions": ["billing.issue"],
            "commands": {
                "billing.issue": { "permission": "billing.issue", "sql": ["commands/issue.sql"] }
            }
        }),
        &[(
            "commands/issue.sql",
            "INSERT INTO billing_doc (issuer_nif, issuer_name) \
             VALUES (:business_tax_id, :business_legal_name)",
        )],
    );
    rt.install_from_dir(&issuer_dir).await.unwrap();
    std::fs::remove_dir_all(&issuer_dir).ok();
    rt.db()
        .execute_batch("CREATE TABLE billing_doc (issuer_nif TEXT, issuer_name TEXT);")
        .await
        .unwrap();

    // The checklist: no ⛔ on the certificate module — the gate behind it does not reject.
    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "verifactu.configure"]),
    )
    .await;
    assert_eq!(
        must(&doc, "verifactu.setup")["level"],
        "functional",
        "in testing there is nothing to authorize (ADR-0360): the arm is gone, the item is \
         still worth configuring"
    );
    assert_eq!(doc["blocking_pending"], 0);

    // And the gate itself: the test document is issued with no certificate in the hub.
    rt.execute_command(
        "billing.issue",
        &Params::new(),
        &ctx("hub-setup", &[SESSION, "billing.issue"]),
    )
    .await
    .expect("the TEST invoice goes out: in testing there is nothing to authorize");
}

#[tokio::test]
async fn the_blocking_level_follows_the_capability_and_never_a_module_name() {
    // Same principle ADR-0203 applied to the gate: the condition names the CAPABILITY, not
    // `verifactu`. A runtime that hardcoded the id would block the wrong hub in every country that
    // is not Spain, and would miss the module that actually holds the certificate.
    let mut rt = runtime("hub-setup").await;
    pin_fiscal_environment(&rt, "hub-setup", "production").await;
    for dir in [
        // Carries the capability under a different name → it carries the ⛔ too.
        certificate_module("fattura"),
        // Called `verifactu` but asks the host for nothing → nothing to block on.
        setup_module("verifactu", false, json!({ "order": 60 })),
    ] {
        rt.install_from_dir(&dir).await.unwrap();
        std::fs::remove_dir_all(&dir).ok();
    }
    set_business_identity(&rt).await;

    let doc = status(
        &rt,
        &ctx(
            "hub-setup",
            &[
                SESSION,
                ADMINISTER,
                "fattura.configure",
                "verifactu.configure",
            ],
        ),
    )
    .await;
    assert_eq!(must(&doc, "fattura.setup")["level"], "legal");
    assert_eq!(must(&doc, "verifactu.setup")["level"], "functional");
    assert_eq!(doc["blocking_pending"], 1);
}

#[tokio::test]
async fn blocking_pending_counts_the_pending_legal_items_and_only_those() {
    // The single number hub#374 reads. It has to be the count of what the runtime would reject —
    // not of everything pending (the strip would never go away) and not of everything legal
    // (it would never appear once the hub is set up).
    let mut rt = runtime("hub-setup").await;
    pin_fiscal_environment(&rt, "hub-setup", "production").await;
    let dir = certificate_module("verifactu");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    let c = ctx("hub-setup", &[SESSION, ADMINISTER, "verifactu.configure"]);

    let doc = status(&rt, &c).await;
    assert_eq!(doc["blocking_pending"], 2, "identity AND certificate");
    assert!(
        doc["pending"].as_u64().unwrap() > doc["blocking_pending"].as_u64().unwrap(),
        "the pending count is the whole checklist, the blocking one is the gate: {doc}"
    );

    set_business_identity(&rt).await;
    assert_eq!(status(&rt, &c).await["blocking_pending"], 1);

    load_certificate(&rt, "hub-setup").await;
    let doc = status(&rt, &c).await;
    assert_eq!(doc["blocking_pending"], 0);
    assert!(
        doc["pending"].as_u64().unwrap() > 0,
        "there is still work left — it just no longer blocks the till"
    );
}

// ── The third state of the apps item: "unavailable" (hub#371) ─────────────────────────────────

#[tokio::test]
async fn the_apps_item_is_unavailable_when_the_catalogue_had_nothing_to_offer() {
    // The failure this state exists for: nobody ran `publish_core_modules.py` in production, or the
    // entitlement says no to everything. The hub is empty and the user CANNOT fill it. Calling that
    // "pending" would hand them a task whose only screen is a blank catalogue — a chore we invented
    // and they cannot finish. It is our breakdown, and it says so.
    let rt = runtime("hub-setup").await;
    catalogue_offered(&rt, 0).await;

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
    assert_eq!(must(&doc, "apps")["state"], "unavailable");
}

#[tokio::test]
async fn the_apps_item_stays_pending_while_the_catalogue_has_something_to_install() {
    // The ordinary empty hub: there ARE apps to install, so filling it is genuinely the user's next
    // move. The third state must not swallow the second one.
    let rt = runtime("hub-setup").await;
    catalogue_offered(&rt, 26).await;

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
    assert_eq!(must(&doc, "apps")["state"], "pending");
}

#[tokio::test]
async fn a_catalogue_that_lists_modules_you_may_not_install_is_just_as_unavailable() {
    // The second half of hub#371: the marketplace answers with the full list and the entitlement
    // says no to all of it (the 403). The person in front of the hub hits the same wall as with an
    // empty catalogue — every Install button greyed out — so it has to reach the same state.
    let rt = runtime("hub-setup").await;
    catalogue_answered(
        &rt,
        200,
        &json!({ "results": [
            { "id": "inventory", "can_install": false },
            { "id": "sales", "can_install": false },
        ] }),
    )
    .await;

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
    assert_eq!(must(&doc, "apps")["state"], "unavailable");
}

#[tokio::test]
async fn a_marketplace_that_refuses_to_answer_is_not_news_and_overwrites_nothing() {
    // A refused or unreachable catalogue is NOT the claim that there is nothing to install. If it
    // were recorded as such, a five-minute SaaS outage would tell a paying customer the product is
    // broken — and then keep telling them, because the state talks them out of going to look.
    let rt = runtime("hub-setup").await;
    catalogue_offered(&rt, 26).await;
    assert_eq!(
        must(&status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await, "apps")["state"],
        "pending"
    );

    for (code, body) in [
        (403u16, json!({ "detail": "Not allowed." })),
        (502, json!({ "ok": false, "error": "connection refused" })),
        (200, json!({ "detail": "this is not a catalogue" })),
        // The dangerous one: a body that is shaped exactly like an empty catalogue, under a status
        // that says it is not one. An edge or a gateway will hand back a well-formed envelope with
        // a 503, and believing the shape alone is how an outage gets to tell a paying customer the
        // marketplace has nothing in it. The status decides whether the body IS the catalogue.
        (503, json!({ "results": [] })),
    ] {
        catalogue_answered(&rt, code, &body).await;
        assert_eq!(
            must(&status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await, "apps")["state"],
            "pending",
            "a {code} answering {body} must leave the last real answer standing"
        );
    }
}

#[tokio::test]
async fn a_hub_that_never_asked_the_catalogue_is_not_told_the_catalogue_is_broken() {
    // No marker = we have never asked, which is NOT evidence of a breakdown. Defaulting to
    // "unavailable" would tell every brand-new hub that the product is broken before anyone looked,
    // and it would talk the user out of the one screen that refreshes the answer.
    let rt = runtime("hub-setup").await;

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
    assert_eq!(must(&doc, "apps")["state"], "pending");
}

#[tokio::test]
async fn a_catalogue_answer_too_old_to_be_an_answer_stops_making_the_item_unavailable() {
    // The trap this closes: a marketplace that was empty (or a SaaS that was down) an hour ago must
    // not freeze the checklist into "nothing to install" forever — because the item then argues the
    // user out of visiting /apps, which is the only thing that would refresh the answer. A stale
    // fact is not a fact: it degrades to "we do not know" ⇒ pending, the state that sends them to
    // look.
    let rt = runtime("hub-setup").await;
    catalogue_offered_hours_ago(&rt, 0, 5).await;

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
    assert_eq!(must(&doc, "apps")["state"], "pending");
}

#[tokio::test]
async fn an_unavailable_item_stays_on_the_list_instead_of_being_omitted() {
    // Where it parts company with the best-effort rule. An OMITTED item is one we could not
    // evaluate, so we say nothing. Here we evaluated it perfectly: we know the hub is empty and we
    // know why it cannot be filled. Hiding that would leave a new customer staring at an empty hub
    // with a checklist that mentions nothing about it — the false "done" that hides a task forever.
    let rt = runtime("hub-setup").await;
    catalogue_offered(&rt, 0).await;

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
    assert_eq!(
        keys(&doc),
        vec!["apps", "business_identity", "team"],
        "the item is still there, and still first"
    );
    assert_eq!(doc["total"], 3);
}

#[tokio::test]
async fn an_unavailable_item_is_not_work_the_user_still_has_to_do() {
    // `pending` is what is left on the user's pile, so an item they cannot touch is not on it. And
    // the counters have to stay a complete partition of the list: with three states, `total -
    // pending` would otherwise read as "done" and quietly count the breakdown as a success.
    let rt = runtime("hub-setup").await;
    catalogue_offered(&rt, 0).await;

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;
    assert_eq!(doc["pending"], 2, "the identity and the team, not the apps");
    assert_eq!(doc["unavailable"], 1);
    let done = items(&doc).iter().filter(|i| i["state"] == "done").count();
    assert_eq!(
        done as u64 + doc["pending"].as_u64().unwrap() + doc["unavailable"].as_u64().unwrap(),
        doc["total"].as_u64().unwrap(),
        "done + pending + unavailable = total, or a consumer can derive a wrong 'done': {doc}"
    );
}

#[tokio::test]
async fn the_third_state_leaves_blocking_pending_exactly_where_it_was() {
    // `blocking_pending` answers one question — what will the fiscal gate refuse — and the empty
    // catalogue does not change that answer in either direction. The count is the same hub state
    // with and without the marker.
    let rt = runtime("hub-setup").await;
    let c = ctx("hub-setup", ADMIN_SESSION);
    let before = status(&rt, &c).await["blocking_pending"].clone();

    catalogue_offered(&rt, 0).await;
    let doc = status(&rt, &c).await;
    assert_eq!(doc["blocking_pending"], before);
    assert_eq!(
        doc["blocking_pending"], 1,
        "the business identity, as always"
    );

    // And it still clears when the gate clears: the third state is on another axis entirely.
    set_business_identity(&rt).await;
    let doc = status(&rt, &c).await;
    assert_eq!(must(&doc, "apps")["state"], "unavailable");
    assert_eq!(doc["blocking_pending"], 0);
}

#[tokio::test]
async fn an_installed_app_beats_whatever_the_catalogue_last_said() {
    // The catalogue is only ever consulted to explain an EMPTY hub. A hub that already has an app
    // running is done, and no answer from the marketplace can un-do it — which is also why the
    // common case never pays for this at all.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("inventory", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    catalogue_offered(&rt, 0).await;

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "inventory.configure"]),
    )
    .await;
    assert_eq!(must(&doc, "apps")["state"], "done");
    assert_eq!(doc["unavailable"], 0);
}

#[tokio::test]
async fn only_the_apps_item_can_be_unavailable_a_module_item_never_is() {
    // The third state is about something OUTSIDE this hub — the marketplace. Every other item is
    // completed on a screen the hub already has, so there is nothing that could make it
    // unreachable; a module item that cannot be evaluated is omitted, and one that is not
    // configured is pending. Neither is this.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", false, json!({ "order": 20 }));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    catalogue_offered(&rt, 0).await;

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "pricing.configure"]),
    )
    .await;
    assert_eq!(must(&doc, "pricing.setup")["state"], "pending");
    for it in items(&doc) {
        assert!(
            it["state"] != "unavailable" || it["key"] == "apps",
            "only the apps item reaches the third state: {it}"
        );
    }
}

// ── Whose task is it: the core items declare their permission too (hub#435) ───────────────────
//
// The three core items reached EVERY session, because the only gate was the namespace one
// (`hub.users.view`), which `identity::session_permissions` grants to every local session. A waiter
// was shown «Your business details» with a button to `/settings`, where the server refuses them.
//
// The rule that replaces it has two halves, and the second is the one that is easy to get wrong:
//
//  1. A task this session cannot do is **not on its list** — nor in its counters. It is not theirs.
//  2. A **wall** is not a task: ⛔ and still pending means `enforce_fiscal_precondition` is going to
//     refuse THIS session's sale, whoever ends up clearing it. Dropping it would take the blocking
//     strip down for exactly the person it was built for, and turn «nothing pending» into a lie.

/// A module shaped like `verifactu` in production: it asks the host for the business certificate,
/// its check is READABLE by an employee (`view`) but only `configure` may act on it, and it is never
/// configured. That combination is what puts the ⛔ certificate arm on a session that cannot clear it.
fn certificate_module_readable_by_all(id: &str) -> PathBuf {
    module_fixture(
        json!({
            "id": id,
            "name": id,
            "version": "1.0.0",
            "capabilities": { "certificate": { "purpose": "fiscal-sign" } },
            "permissions": [format!("{id}.view"), format!("{id}.configure")],
            "queries": {
                format!("{id}.config.get"): {
                    "permission": format!("{id}.view"),
                    "sql": "queries/config_get.sql"
                }
            },
            "setup": {
                "query": format!("{id}.config.get"),
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": format!("Configure {id}"),
                "route": format!("/m/{id}/settings"),
                "permission": format!("{id}.configure"),
                "order": 60
            }
        }),
        &[("queries/config_get.sql", "SELECT 0 AS ready")],
    )
}

#[tokio::test]
async fn a_waiter_is_not_handed_the_administrator_s_tasks() {
    // The bug, reproduced: a hub that is set up enough to sell and invoice. Everything left on it
    // is somebody else's job, so the waiter's checklist is EMPTY — which the card paints as
    // silence (no card at all), never as «you are all done».
    let mut rt = runtime("hub-setup").await;
    set_business_identity(&rt).await;
    let dir = setup_module("inventory", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(&rt, &ctx("hub-setup", &[SESSION])).await;

    assert!(
        keys(&doc).is_empty(),
        "nothing here is the waiter's to do: {:?}",
        keys(&doc)
    );
    assert_eq!(doc["total"], 0);
    assert_eq!(doc["pending"], 0);
    assert_eq!(doc["blocking_pending"], 0, "the hub can invoice: no wall");
}

#[tokio::test]
async fn the_wall_stays_on_the_list_of_whoever_cannot_bring_it_down() {
    // The half that must NOT be filtered. The cashier cannot type the tax id, but ADR-0203 refuses
    // THEIR sale until somebody does — so the item is named, counted and raises the strip. What it
    // does not do is offer itself: `actionable` is false and the surfaces drop the call to action.
    let rt = runtime("hub-setup").await;

    let doc = status(&rt, &ctx("hub-setup", &[SESSION])).await;

    assert_eq!(
        keys(&doc),
        vec!["business_identity"],
        "the 🔴 and the 🟡 are not theirs; the ⛔ is going to stop them"
    );
    let wall = must(&doc, "business_identity");
    assert_eq!(wall["state"], "pending");
    assert_eq!(wall["level"], "legal");
    assert_eq!(wall["actionable"], false, "it is not theirs to clear");
    assert_eq!(
        doc["blocking_pending"], 1,
        "the strip has to rise for the very session the sale is refused to"
    );
    assert_eq!(doc["pending"], 1);
    assert_eq!(doc["total"], 1);
}

#[tokio::test]
async fn a_wall_already_down_is_not_kept_on_a_list_it_never_belonged_to() {
    // A ⛔ that is DONE blocks nothing, so the exception that carried it does not apply any more and
    // the ordinary rule takes over: not this session's task, not on this session's list. Keeping it
    // would put an item on the waiter's checklist that is neither theirs nor pending.
    let rt = runtime("hub-setup").await;
    set_business_identity(&rt).await;

    let doc = status(&rt, &ctx("hub-setup", &[SESSION])).await;

    assert!(
        item(&doc, "business_identity").is_none(),
        "a cleared wall is nobody's task: {:?}",
        keys(&doc)
    );
}

#[tokio::test]
async fn whoever_administers_the_hub_gets_the_three_core_items_and_can_act_on_every_one() {
    // The other side of the same filter: nothing is taken away from the person the items are for.
    let rt = runtime("hub-setup").await;

    let doc = status(&rt, &ctx("hub-setup", ADMIN_SESSION)).await;

    assert_eq!(keys(&doc), vec!["apps", "business_identity", "team"]);
    for key in ["apps", "business_identity", "team"] {
        assert_eq!(
            must(&doc, key)["actionable"],
            true,
            "{key} is this session's to do"
        );
    }
    assert_eq!(doc["total"], 3);
    assert_eq!(doc["pending"], 3);
}

#[tokio::test]
async fn every_item_carries_the_field_so_nobody_branches_on_its_absence() {
    // Same contract as the rest of the payload (§4): all the keys on all the items, core and module
    // alike. A consumer that had to test for presence would be deciding the answer itself.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("inventory", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "inventory.configure"]),
    )
    .await;

    assert!(items(&doc).len() >= 4);
    for it in items(&doc) {
        assert_eq!(
            it["actionable"], true,
            "this session can act on everything it was given: {it}"
        );
    }
}

#[tokio::test]
async fn a_module_wall_reaches_the_session_that_cannot_clear_it_either() {
    // The ⛔ the core hangs on a MODULE item — the certificate arm — is the same wall as the fiscal
    // identity: the gate refuses everybody while it is missing. `verifactu` is exactly this shape
    // (its check needs `view`, its `setup` declares `configure`, and the employee role holds only
    // `view`), so before hub#435 the cashier lost that ⛔ to the module filter and got no strip.
    // Production environment on purpose: since ADR-0360 the arm is the production one.
    let mut rt = runtime("hub-setup").await;
    pin_fiscal_environment(&rt, "hub-setup", "production").await;
    set_business_identity(&rt).await;
    let dir = certificate_module_readable_by_all("fiscal");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let viewer = ctx("hub-setup", &[SESSION, "fiscal.view"]);
    let doc = status(&rt, &viewer).await;

    assert_eq!(keys(&doc), vec!["fiscal.setup"], "{:?}", keys(&doc));
    let wall = must(&doc, "fiscal.setup");
    assert_eq!(wall["level"], "legal");
    assert_eq!(wall["state"], "pending");
    assert_eq!(wall["actionable"], false);
    assert_eq!(doc["blocking_pending"], 1);
}

#[tokio::test]
async fn a_module_item_that_stops_being_a_wall_goes_back_to_being_somebody_else_s_business() {
    // Load the certificate and the gate accepts, so the arm disappears (§4: it is EVALUATED, not
    // listed). The item drops to 🔴 — still not configured — and with it the reason it was on this
    // session's list at all. A ⛔ that does not block is the colour this design exists to avoid.
    let mut rt = runtime("hub-setup").await;
    set_business_identity(&rt).await;
    let dir = certificate_module_readable_by_all("fiscal");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    load_certificate(&rt, "hub-setup").await;

    let viewer = ctx("hub-setup", &[SESSION, "fiscal.view"]);
    let doc = status(&rt, &viewer).await;

    assert!(
        item(&doc, "fiscal.setup").is_none(),
        "nothing blocks any more, so it is just a task that is not theirs: {:?}",
        keys(&doc)
    );
    assert_eq!(doc["blocking_pending"], 0);
    // …and whoever CAN configure it still has it, as a 🔴 and actionable.
    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, "fiscal.view", "fiscal.configure"]),
    )
    .await;
    assert_eq!(must(&doc, "fiscal.setup")["level"], "functional");
    assert_eq!(must(&doc, "fiscal.setup")["actionable"], true);
}

#[tokio::test]
async fn the_core_items_are_gated_on_what_an_administrator_session_really_carries() {
    // The filter and the server gate must not be able to disagree about who administers the hub.
    // `require_admin_session` asks `is_admin_role`; this permission is granted by
    // `session_permissions` to exactly those roles and to no other — so «the checklist offered it»
    // and «the server would accept it» are the same sentence.
    let rt = runtime("hub-setup").await;

    for role in ["admin", "ADMIN", "owner"] {
        assert!(
            rt.session_permissions(role).contains(ADMINISTER),
            "{role} administers the hub"
        );
    }
    for role in ["manager", "employee", "bartender", ""] {
        assert!(
            !rt.session_permissions(role).contains(ADMINISTER),
            "{role} does NOT administer the hub"
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

// ── De dónde viene lo que ya está hecho (hub#536, ADR-0267) ───────────────────────────────────

/// Marca una fila de `<table>` como escrita por una importación, igual que hace el motor.
async fn imported_row(rt: &Runtime, hub_id: &str, table: &str, row_id: &str) {
    let db = rt.db();
    db.execute_batch(
        "CREATE TABLE IF NOT EXISTS _hub_import_batch (\
           id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL);\
         CREATE TABLE IF NOT EXISTS _hub_import_row (\
           batch_id TEXT NOT NULL, table_name TEXT NOT NULL, row_id TEXT NOT NULL);",
    )
    .await
    .unwrap();
    let mut p = Params::new();
    p.insert("hub".into(), json!(hub_id));
    p.insert("t".into(), json!(table));
    p.insert("r".into(), json!(row_id));
    db.execute(
        "INSERT INTO _hub_import_batch (id, hub_id, name, created_at) \
         VALUES ('b1', :hub, 'restaurante_es', '2026-08-08T10:00:00Z')",
        &p,
    )
    .await
    .unwrap();
    db.execute(
        "INSERT INTO _hub_import_row (batch_id, table_name, row_id) VALUES ('b1', :t, :r)",
        &p,
    )
    .await
    .unwrap();
}

/// 🔴 [hub#536] Un ítem hecho dice **de dónde viene**: lo puso el dueño o lo trajo una plantilla.
///
/// Es la mitad de hub#426 que no arregla sacar cosas del bundle. Con la numeración fiscal fuera
/// (hub#533) y las casillas por tabla (hub#534), casi todo el falso «hecho» desaparece — pero queda
/// un residuo **legítimo**: las mesas, el catálogo y los servicios **sí** viajan, para eso existe
/// una plantilla, y **sí** marcan su ítem como hecho. Es verdad que están hechos, pero con menos
/// confianza que si los hubiera puesto el dueño: un bar tiene su propia sala y sus propios precios.
///
/// Un falso «pendiente» se ve; un falso «hecho» esconde la tarea para siempre.
#[tokio::test]
async fn un_item_hecho_por_una_plantilla_lo_dice() {
    let mut rt = runtime("hub-origen").await;
    let dir = setup_module("tables", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    imported_row(&rt, "hub-origen", "tables_table", "t1").await;

    let doc = status(
        &rt,
        &ctx("hub-origen", &[SESSION, ADMINISTER, "tables.configure"]),
    )
    .await;

    assert_eq!(must(&doc, "tables.setup")["origin"], "blueprint");
}

/// …y lo que puso el dueño no se marca como heredado. Un falso «esto lo trajo una plantilla»
/// mandaría a revisar algo que ya se decidió, que es la molestia simétrica.
#[tokio::test]
async fn lo_que_configuro_el_dueno_no_se_marca_como_heredado() {
    let mut rt = runtime("hub-propio").await;
    let dir = setup_module("tables", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();

    let doc = status(
        &rt,
        &ctx("hub-propio", &[SESSION, ADMINISTER, "tables.configure"]),
    )
    .await;

    assert_eq!(must(&doc, "tables.setup")["origin"], "user");
}

/// Un import de OTRO módulo no contamina a éste: la pregunta es «¿los datos de ESTA app los trajo
/// una plantilla?», no «¿este hub importó algo alguna vez?».
#[tokio::test]
async fn el_origen_es_por_modulo_no_por_hub() {
    let mut rt = runtime("hub-mixto").await;
    rt.install_from_dir(&setup_module("tables", true, json!({})))
        .await
        .unwrap();
    imported_row(&rt, "hub-mixto", "inventory_product", "p1").await;

    let doc = status(
        &rt,
        &ctx("hub-mixto", &[SESSION, ADMINISTER, "tables.configure"]),
    )
    .await;

    assert_eq!(must(&doc, "tables.setup")["origin"], "user");
}

/// Los ítems del CORE son siempre del dueño: una plantilla no lleva identidades ni personas
/// (ADR-0195 §3/§4/§5), así que `business_identity` y `team` no pueden venir heredados. Decirlo
/// como dato —y no como ausencia de campo— es lo que evita que un consumidor ramifique por
/// presencia de clave (ADR-0222 §4).
#[tokio::test]
async fn los_items_del_core_son_siempre_del_dueno() {
    let mut rt = runtime("hub-core").await;
    imported_row(&rt, "hub-core", "inventory_product", "p1").await;

    let doc = status(&rt, &ctx("hub-core", ADMIN_SESSION)).await;

    for key in ["apps", "business_identity", "team"] {
        assert_eq!(must(&doc, key)["origin"], "user", "ítem del core: {key}");
    }
}

/// Todo ítem lleva el campo, hecho o pendiente (ADR-0222 §4: nadie ramifica por presencia).
#[tokio::test]
async fn todo_item_lleva_origen_aunque_este_pendiente() {
    let mut rt = runtime("hub-pendiente").await;
    rt.install_from_dir(&setup_module("tables", false, json!({})))
        .await
        .unwrap();

    let doc = status(
        &rt,
        &ctx("hub-pendiente", &[SESSION, ADMINISTER, "tables.configure"]),
    )
    .await;

    for it in items(&doc) {
        assert!(it["origin"].is_string(), "sin origen: {it}");
    }
}

// ── hub#1119 · a module the dispatcher will refuse is NOT «configured» ──────────────────────────
//
// The checklist's whole job is to answer «is anything left before this business can work». A module
// whose declared capability (ADR-0079) is not granted cannot run its engine at all: the dispatcher
// turns its native commands away before they start. Ticking its item because its own settings are
// filled in is the false «done» this design keeps failing away from — and it is the one that let a
// hub invoice, charge and print for a whole day believing it was sealing.

#[tokio::test]
async fn a_module_whose_capability_is_not_granted_is_still_pending() {
    let mut rt = runtime("hub-setup").await;
    let dir = sealing_module("verifactu");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "verifactu.configure"]),
    )
    .await;
    assert_eq!(
        must(&doc, "verifactu.setup")["state"],
        "pending",
        "its own query says ready, but nobody granted the capability its engine needs"
    );
}

#[tokio::test]
async fn granting_the_capability_is_what_finishes_the_item() {
    let mut rt = runtime("hub-setup").await;
    let dir = sealing_module("verifactu");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    rt.set_module_capability("verifactu", "certificate", true, "hub_user:1")
        .await
        .expect("the owner grants it in Ajustes → Permisos");

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "verifactu.configure"]),
    )
    .await;
    assert_eq!(
        must(&doc, "verifactu.setup")["state"],
        "done",
        "settings filled in AND the switch on: now there is genuinely nothing left"
    );
}

#[tokio::test]
async fn a_module_that_asks_for_nothing_is_unaffected() {
    // The rule must not invent a task for the 20-odd modules that declare no capability at all.
    let mut rt = runtime("hub-setup").await;
    let dir = setup_module("pricing", true, json!({}));
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let doc = status(
        &rt,
        &ctx("hub-setup", &[SESSION, ADMINISTER, "pricing.configure"]),
    )
    .await;
    assert_eq!(must(&doc, "pricing.setup")["state"], "done");
}
