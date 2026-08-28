//! ERPlora/hub#1179 — «your apps» may only tick for an app **this hub really runs**.
//!
//! The issue was filed on the premise that a freshly provisioned FREE hub *arrives with `customers`
//! preinstalled*, so `hub.setup.status`'s `apps` item ticked `done` on a business that had chosen
//! nothing — closing the one-click onboarding door before the owner ever saw it.
//!
//! **That premise does not hold.** No door installs a module into a newborn hub:
//!
//! * the boot import of the deploy-declared blueprint was removed (a hub is born EMPTY), and
//!   `crates/server/tests/newborn_hub_is_empty.rs` boots the real server with
//!   `HUB_BOOTSTRAP_BLUEPRINT` set and asserts `hub_module` comes out empty;
//! * `HUB_MODULES_DIR` is scanned at boot **only** in developer mode (`install_guard::boot_scan_dir`),
//!   and developer mode has to be asked for explicitly — no deployment writes `HUB_DEV_MODE`;
//! * `POST /api/modules/install {dir}` is gated behind that same developer mode;
//! * the SaaS has no credential pointing at a hub, so it cannot make one install anything: it
//!   declares and the hub acts;
//! * the two boot steps that DO install (re-hydration from the module cache and the stateless
//!   re-download) act only on rows `hub_module` already has — on a newborn hub, none.
//!
//! So the item is answering correctly today, and what this file is for is keeping it that way: the
//! belief that the runtime ticks `apps` off something nobody chose was written into the shell as
//! fact, and a belief nobody can re-check is how a defect gets re-invented. These cases pin the
//! rule the item actually follows — **`apps` ticks off the modules this hub is RUNNING, and off
//! nothing else** — so any future door that leaves a module (or just a row) behind on a virgin hub
//! trips here instead of quietly closing the onboarding door again.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

const HUB: &str = "hub-1179";

/// The `hub.` namespace gate every LOCAL session carries, plus the administrative rank the core
/// items are gated on: the core items are dropped for a session that cannot configure them.
const ADMIN_SESSION: &[&str] = &[
    "hub.users.view",
    erplora_runtime::hub_users::ADMINISTER_PERMISSION,
];

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

fn ctx() -> RequestContext {
    RequestContext::new(HUB, "u1", ADMIN_SESSION.iter().map(|p| p.to_string()))
}

/// The state of the `apps` item in the one document `hub.setup.status` answers with.
async fn apps_state(rt: &Runtime) -> String {
    let rows = rt
        .execute_query("hub.setup.status", &Params::new(), &ctx())
        .await
        .expect("the core answers the setup status");
    let doc = rows.into_iter().next().expect("the status is ONE document");
    let items = doc["items"]
        .as_array()
        .expect("`items` is an array")
        .clone();
    let apps = items
        .iter()
        .find(|i| i["key"] == "apps")
        .unwrap_or_else(|| panic!("the `apps` item is missing from {doc}"));
    apps["state"]
        .as_str()
        .expect("`state` is a string")
        .to_string()
}

/// Records that the marketplace had something to offer, so an empty hub reads `pending` (its own
/// task) instead of `unavailable` (our breakdown). Both are "not done"; this keeps the cases about
/// the one distinction they are testing.
async fn catalogue_has_apps_to_offer(rt: &Runtime) {
    let modules: Vec<Json> = (0..26)
        .map(|i| json!({ "id": format!("module_{i}"), "name": format!("Module {i}") }))
        .collect();
    erplora_runtime::setup_status::record_catalog_response(
        rt.db(),
        200,
        json!({ "results": modules }).to_string().as_bytes(),
    )
    .await
    .expect("the catalogue answer is recorded");
}

/// A throwaway module package: the smallest thing the installer accepts.
fn module_fixture(id: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-1179-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        json!({ "id": id, "name": id, "version": "1.0.0" }).to_string(),
    )
    .unwrap();
    dir
}

/// **A hub nobody installed anything into does not claim it has apps.**
///
/// The two boot steps that install (`rehydrate_installed` and, above it, the stateless
/// re-download) work off `hub_module`; on a newborn hub that table is empty and they must invent
/// nothing. If either ever seeded a module by itself, the onboarding door would be shut before the
/// owner reached it — which is the failure hub#1179 was filed about.
#[tokio::test]
async fn a_newborn_hub_does_not_claim_it_has_apps_hub1179() {
    let mut rt = runtime().await;
    catalogue_has_apps_to_offer(&rt).await;

    let empty_cache =
        std::env::temp_dir().join(format!("erplora-1179-cache-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&empty_cache).unwrap();
    let rehydrated = rt
        .rehydrate_installed(&empty_cache)
        .await
        .expect("re-hydration over an empty cache is not an error");
    std::fs::remove_dir_all(&empty_cache).ok();

    assert!(
        rehydrated.is_empty(),
        "booting a newborn hub must not register a single module: {rehydrated:?}"
    );
    assert!(
        rt.registry().installed.is_empty(),
        "a newborn hub runs no module at all"
    );
    assert_eq!(
        apps_state(&rt).await,
        "pending",
        "`apps` is the owner's next move on an empty business — never `done`"
    );
}

/// **A `hub_module` row on its own does not tick the checklist.**
///
/// This is the door-independent half. Whatever might one day leave a module behind — a deployment
/// that preinstalls, a stale row from a hub that lost its cache — the checklist follows the modules
/// the runtime is actually RUNNING (the registry), not what the table remembers. A row the registry
/// cannot back is exactly the "app" nobody chose and nobody can use.
#[tokio::test]
async fn a_hub_module_row_the_registry_cannot_back_does_not_tick_the_apps_item_hub1179() {
    let rt = runtime().await;
    catalogue_has_apps_to_offer(&rt).await;

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    rt.db()
        .execute(
            "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
             VALUES (:hub_id, 'customers', '2.3.16', 'active', '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z')",
            &p,
        )
        .await
        .expect("the row of a module this hub is not running");

    assert!(
        rt.registry().installed.is_empty(),
        "the registry is what the hub RUNS, and it runs nothing here"
    );
    assert_eq!(
        apps_state(&rt).await,
        "pending",
        "a row nobody can use is not «this business has its apps»"
    );
}

/// **Only a module this hub is RUNNING ticks it — and it stops ticking when the module stops.**
///
/// The other end of the same rule: `done` is not a one-way latch on «something was installed once»,
/// it is a statement about the hub as it is now. Switching the only app off puts the business back
/// where the checklist can help it.
#[tokio::test]
async fn only_a_module_this_hub_is_running_ticks_the_apps_item_hub1179() {
    let mut rt = runtime().await;
    catalogue_has_apps_to_offer(&rt).await;

    let dir = module_fixture("inventory");
    rt.install_from_dir(&dir)
        .await
        .expect("the module installs");
    std::fs::remove_dir_all(&dir).ok();
    assert_eq!(
        apps_state(&rt).await,
        "done",
        "an app the hub is running IS «this business has its apps»"
    );

    rt.deactivate("inventory")
        .await
        .expect("the module switches off");
    assert_eq!(
        apps_state(&rt).await,
        "pending",
        "an app that is switched off is not one the business can work with"
    );
}
