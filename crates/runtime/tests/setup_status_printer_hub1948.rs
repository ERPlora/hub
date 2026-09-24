//! hub#1948 — the onboarding checklist has to say that no printer has been set up.
//!
//! A new business walks the whole checklist, sees it green, and finds out it has no printer when
//! the first sale produces no ticket. The module item that used to cover it (`printing`, slot 70)
//! measured a text that no paper prints any more and was retired (printing#44); what the step has
//! to ask lives in the core: is some device registered to print the `receipt` station
//! (`_print_host`, ADR-0196 §6)? No app can answer that, so it is a CORE item.
//!
//! Registered, not live: setting the printer up is a one-off task, a till that is switched off
//! tonight is an operational alarm (`hub.print.coverage` / `undrained`), not a first step undone.

use erplora_db::testutil::TestDb;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

const ADMIN_SESSION: &[&str] = &[
    "hub.users.view",
    erplora_runtime::hub_users::ADMINISTER_PERMISSION,
];

async fn hub_on(test_db: &TestDb, hub_id: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn status(rt: &Runtime, hub_id: &str) -> Json {
    let ctx = RequestContext::new(
        hub_id,
        "u1",
        ADMIN_SESSION.iter().map(|p| p.to_string()),
    );
    rt.execute_query("hub.setup.status", &Params::new(), &ctx)
        .await
        .expect("the core answers the setup status")
        .into_iter()
        .next()
        .expect("one status document")
}

fn keys(doc: &Json) -> Vec<String> {
    doc["items"]
        .as_array()
        .unwrap()
        .iter()
        .map(|i| i["key"].as_str().unwrap_or_default().to_string())
        .collect()
}

fn printer(doc: &Json) -> Json {
    doc["items"]
        .as_array()
        .unwrap()
        .iter()
        .find(|i| i["key"] == "printer")
        .cloned()
        .unwrap_or_else(|| panic!("no `printer` item in {:?}", keys(doc)))
}

#[tokio::test]
async fn a_new_hub_is_told_to_set_up_its_printer() {
    let test_db = TestDb::new().await;
    let rt = hub_on(&test_db, "hub-1948").await;
    let doc = status(&rt, "hub-1948").await;

    assert_eq!(
        keys(&doc),
        vec!["apps", "business_identity", "printer", "team"],
        "the printer takes slot 70, the one printing#44 left free: after the business details, \
         before the team"
    );
    let item = printer(&doc);
    assert_eq!(item["state"], "pending");
    assert_eq!(item["source"], "core");
    assert!(item["module_id"].is_null(), "a core item belongs to no module");
    assert_eq!(
        item["level"], "recommended",
        "a hub without a printer still sells: this is a notice, never a wall"
    );
    assert_eq!(
        item["route"], "/settings#tickets",
        "the core's own screen for receipts, which exists whatever apps are installed"
    );
    assert_eq!(item["order"], 70);
}

#[tokio::test]
async fn the_printer_item_is_done_only_while_a_device_prints_receipts() {
    let test_db = TestDb::new().await;
    let rt = hub_on(&test_db, "hub-1948").await;

    // A kitchen printer is not the one that prints the customer's ticket.
    rt.register_print_host("till-1", "kitchen", "Kitchen till", "u1")
        .await
        .unwrap();
    assert_eq!(
        printer(&status(&rt, "hub-1948").await)["state"],
        "pending",
        "only the receipt station answers «is there a printer for the ticket?»"
    );

    rt.register_print_host("till-1", "receipt", "Counter till", "u1")
        .await
        .unwrap();
    let doc = status(&rt, "hub-1948").await;
    assert_eq!(printer(&doc)["state"], "done");

    // Retiring the device puts the step back: a false «done» hides the task for good.
    rt.unregister_print_host("till-1", Some("receipt"))
        .await
        .unwrap();
    assert_eq!(printer(&status(&rt, "hub-1948").await)["state"], "pending");
}

#[tokio::test]
async fn a_printer_that_is_switched_off_is_still_set_up() {
    let test_db = TestDb::new().await;
    let rt = hub_on(&test_db, "hub-1948").await;
    rt.register_print_host("till-1", "receipt", "Counter till", "u1")
        .await
        .unwrap();
    // Last news a year ago: not live, but still registered. Being offline is the coverage alarm's
    // business; re-opening a first step every night the till is switched off would teach the owner
    // to ignore the checklist.
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("hub-1948"));
    rt.db()
        .execute(
            "UPDATE _print_host SET last_seen_at = '2025-01-01T00:00:00+00:00' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
    assert_eq!(rt.print_coverage().await.unwrap()[0].live_hosts, 0);

    assert_eq!(printer(&status(&rt, "hub-1948").await)["state"], "done");
}

#[tokio::test]
async fn a_neighbours_printer_does_not_tick_my_step() {
    // Two hubs sharing one database (the pre-ADR-0201 shape): the row contract is `(hub_id, …)`.
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let neighbour = hub_on(&test_db, "hub-neighbour").await;
    neighbour
        .register_print_host("till-9", "receipt", "Their till", "u2")
        .await
        .unwrap();

    assert_eq!(printer(&status(&mine, "hub-mine").await)["state"], "pending");
    assert_eq!(
        printer(&status(&neighbour, "hub-neighbour").await)["state"],
        "done"
    );
}
