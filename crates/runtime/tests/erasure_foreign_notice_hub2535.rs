//! **hub#2535** — an erasure notice from an app that does not own the person reaches no one.
//!
//! Since hub#2485 the hub refuses to empty its own history when `<subject>.anonymized` comes from
//! an app that does not own the subject. But the relay delivered the event to the listeners BEFORE
//! asking: WhatsApp emptied and closed her conversations, and an automation triggered by the event
//! started, all on the word of an app that had no say over her. Now the relay asks first: a refused
//! erasure is delivered to no listener and starts no automation; the row stays undelivered with
//! the refusal's code, as before, and ends in the dead letters where a human sees it.
//!
//! The real `customers` and `whatsapp_inbox` modules plus the test app
//! `fixture_erasure2485/intruder`, which emits `customer.anonymized` naming a customer that is not
//! its own. Real Postgres, ephemeral schema per test; the job without the catalogue skips it
//! visibly (`require_modules_workspace`). The unit tests in `erasure.rs` cover the gate itself.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::NewFlow;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

fn params(v: Json) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn admin() -> RequestContext {
    RequestContext::new(erplora_runtime::DEV_HUB_ID, "u1", ["*".to_string()])
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.ensure_system_tables().await.expect("system tables");
    for module in ["customers", "whatsapp_inbox"] {
        rt.install_from_dir(&erplora_runtime::e2e_support::modules_root().join(module))
            .await
            .unwrap_or_else(|e| panic!("install {module}: {e}"));
    }
    let intruder = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_erasure2485")
        .join("intruder");
    rt.install_from_dir(&intruder)
        .await
        .expect("install intruder");
    rt
}

async fn rows(rt: &Runtime, sql: &str, bind: &[(&str, &str)]) -> Vec<String> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(erplora_runtime::DEV_HUB_ID));
    for (k, v) in bind {
        p.insert((*k).into(), json!(v));
    }
    rt.db()
        .query(sql, &p)
        .await
        .expect("query")
        .rows
        .iter()
        .map(|r| match &r["v"] {
            Json::String(s) => s.clone(),
            other => other.to_string(),
        })
        .collect()
}

async fn one(rt: &Runtime, sql: &str, bind: &[(&str, &str)]) -> String {
    let all = rows(rt, sql, bind).await;
    assert_eq!(all.len(), 1, "exactly one row for {sql}: {all:?}");
    all[0].clone()
}

/// Ana: a sheet of the real customers app, and a WhatsApp thread the inbox linked to it.
async fn ana_with_a_thread(rt: &Runtime) -> String {
    rt.execute_command(
        "customers.create",
        &params(json!({ "name": "Ana Pérez", "phone": "+34600111222" })),
        &admin(),
    )
    .await
    .expect("customers.create");
    rt.drain_outbox().await.expect("drain");
    let ana = one(
        rt,
        "SELECT id AS v FROM customers_customer WHERE hub_id = :hub_id",
        &[],
    )
    .await;
    let number = "34600111222";
    let payload = params(json!({
        "wa_message_id": "wamid.ANA1",
        "from": number,
        "direction": "inbound",
        "contact": number,
        "source": "live",
        "text": "Hola, soy Ana",
        "received_at": "2026-10-09T08:00:00+00:00",
        "message": { "id": "wamid.ANA1", "from": number, "type": "text",
                     "text": { "body": "Hola, soy Ana" } },
    }));
    erplora_runtime::outbox::insert_core_event_once(
        rt.db(),
        "wa-wamid.ANA1",
        erplora_runtime::DEV_HUB_ID,
        "hub.whatsapp.message_received",
        &payload,
    )
    .await
    .expect("core event");
    for _ in 0..3 {
        rt.drain_outbox().await.expect("drain");
    }
    assert_eq!(
        thread(rt).await,
        vec![format!("{ana}|+34600111222|0")],
        "the premise: the inbox linked her live thread to her sheet"
    );
    ana
}

/// Her thread as `customer_id|contact_phone|is_deleted`.
async fn thread(rt: &Runtime) -> Vec<String> {
    rows(
        rt,
        "SELECT customer_id || '|' || contact_phone || '|' || CAST(is_deleted AS TEXT) AS v \
           FROM whatsapp_inbox_conversation WHERE hub_id = :hub_id",
        &[],
    )
    .await
}

/// An automation of the owner: «when a customer's data is erased, …». Returns its id.
async fn automation_on_erasure(rt: &Runtime) -> String {
    rt.create_flow(
        &NewFlow {
            name: "On erasure".into(),
            enabled: true,
            definition: json!({
                "schema_version": 1,
                "triggers": [{ "kind": "event", "event": "customer.anonymized" }],
                "steps": [{ "id": "wait", "kind": "delay", "seconds": 60 }]
            }),
        },
        "hub_user:owner",
    )
    .await
    .expect("create flow")
    .id
}

async fn runs_of(rt: &Runtime, flow_id: &str) -> String {
    one(
        rt,
        "SELECT CAST(COUNT(*) AS TEXT) AS v FROM _flow_runs \
          WHERE hub_id = :hub_id AND flow_id = :flow",
        &[("flow", flow_id)],
    )
    .await
}

async fn heard(rt: &Runtime) -> String {
    one(
        rt,
        "SELECT CAST(COUNT(*) AS TEXT) AS v FROM intruder_heard WHERE hub_id = :hub_id",
        &[],
    )
    .await
}

async fn erasure_row(rt: &Runtime, module: &str, field: &str) -> String {
    one(
        rt,
        &format!(
            "SELECT {field} AS v FROM _event_outbox \
              WHERE hub_id = :hub_id AND event_name = 'customer.anonymized' AND module_id = :module"
        ),
        &[("module", module)],
    )
    .await
}

/// The bug: `intruder` emits `customer.anonymized` naming Ana. WhatsApp keeps her thread, no
/// listener hears it, no automation starts, and the row waits with its code. The same erasure from
/// `customers`, her owner, reaches all of them.
#[tokio::test]
async fn a_foreign_erasure_notice_reaches_no_app_and_starts_no_automation_hub2535() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = hub().await;
    let ana = ana_with_a_thread(&rt).await;
    let flow = automation_on_erasure(&rt).await;

    rt.execute_command(
        "intruder.customers.forget",
        &params(json!({ "customer_id": ana })),
        &admin(),
    )
    .await
    .expect("intruder.customers.forget");
    rt.drain_outbox().await.expect("drain");
    rt.drain_outbox().await.expect("second drain");

    assert_eq!(
        thread(&rt).await,
        vec![format!("{ana}|+34600111222|0")],
        "WhatsApp erased her thread on the word of an app that does not own her"
    );
    assert_eq!(heard(&rt).await, "0", "a listener heard the foreign erasure");
    assert_eq!(
        runs_of(&rt, &flow).await,
        "0",
        "the foreign erasure started an automation"
    );
    assert_eq!(erasure_row(&rt, "intruder", "status").await, "pending");
    let refusal = erasure_row(&rt, "intruder", "last_error").await;
    assert!(
        refusal.contains("erasure.subject_not_owned"),
        "the refusal names its code: {refusal}"
    );

    rt.execute_command(
        "customers.anonymize",
        &params(json!({ "customer_id": ana, "reason": "gdpr request" })),
        &admin(),
    )
    .await
    .expect("customers.anonymize");
    rt.drain_outbox().await.expect("drain");

    assert_eq!(erasure_row(&rt, "customers", "status").await, "delivered");
    assert_eq!(
        thread(&rt).await,
        vec![format!("{ana}||1")],
        "her owner's erasure empties and closes her thread"
    );
    assert_eq!(heard(&rt).await, "1", "every listener hears the owner's erasure");
    assert_eq!(runs_of(&rt, &flow).await, "1");
}

/// An erasure that does not say whose (no usable `<subject>_id`) cannot be shown to come from the
/// owner either, so it reaches no one: a listener would read a missing or empty id as «nobody» or,
/// worse, as «everyone with no sheet».
#[tokio::test]
async fn an_erasure_notice_that_names_nobody_reaches_no_app_hub2535() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = hub().await;
    ana_with_a_thread(&rt).await;

    rt.execute_command(
        "intruder.customers.forget",
        &params(json!({ "customer_id": "" })),
        &admin(),
    )
    .await
    .expect("intruder.customers.forget");
    rt.drain_outbox().await.expect("drain");

    assert_eq!(heard(&rt).await, "0", "a listener heard an erasure of nobody");
    assert_eq!(erasure_row(&rt, "intruder", "status").await, "pending");
    let refusal = erasure_row(&rt, "intruder", "last_error").await;
    assert!(
        refusal.contains("erasure.invalid_subject_id"),
        "the refusal names its code: {refusal}"
    );
}

/// Every real app that listens to `customer.anonymized` today, by the relay's own delivery
/// marker. Returns `listener_command` of every delivery of `module`'s erasure, sorted.
async fn delivered_to(rt: &Runtime, module: &str) -> Vec<String> {
    let event = erasure_row(rt, module, "id").await;
    rows(
        rt,
        "SELECT listener_command AS v FROM _event_delivery \
          WHERE hub_id = :hub_id AND event_id = :event ORDER BY listener_command",
        &[("event", &event)],
    )
    .await
}

/// HUB-F250 with the apps that listen today (Appointments, Reservations, Services, Tables and
/// WhatsApp, all from the catalogue): a foreign erasure leaves no delivery marker in ANY of them —
/// not one listener ran — while the owner's erasure reaches every one of them, once each. The
/// marker is the relay's own ledger, so this holds for an app that has nothing of hers yet.
#[tokio::test]
async fn a_foreign_erasure_reaches_none_of_the_apps_that_listen_and_the_owners_reaches_all_hub2535()
{
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut rt = hub().await;
    // Dependencies first: the four listeners sit on taxes, schedules, staff and tables.
    for module in [
        "taxes",
        "services",
        "schedules",
        "staff",
        "appointments",
        "tables",
        "reservations",
    ] {
        rt.install_from_dir(&erplora_runtime::e2e_support::modules_root().join(module))
            .await
            .unwrap_or_else(|e| panic!("install {module}: {e}"));
    }
    let ana = ana_with_a_thread(&rt).await;

    rt.execute_command(
        "intruder.customers.forget",
        &params(json!({ "customer_id": ana })),
        &admin(),
    )
    .await
    .expect("intruder.customers.forget");
    rt.drain_outbox().await.expect("drain");
    rt.drain_outbox().await.expect("second drain");
    assert_eq!(
        delivered_to(&rt, "intruder").await,
        Vec::<String>::new(),
        "an app that listens got the foreign erasure"
    );
    assert_eq!(erasure_row(&rt, "intruder", "status").await, "pending");

    rt.execute_command(
        "customers.anonymize",
        &params(json!({ "customer_id": ana, "reason": "gdpr request" })),
        &admin(),
    )
    .await
    .expect("customers.anonymize");
    rt.drain_outbox().await.expect("drain");
    assert_eq!(erasure_row(&rt, "customers", "status").await, "delivered");
    assert_eq!(
        delivered_to(&rt, "customers").await,
        [
            "appointments._on_customer_anonymized",
            "intruder._heard_anonymized",
            "reservations._on_customer_anonymized",
            "services._on_customer_deleted",
            "tables._on_customer_anonymized",
            "whatsapp_inbox._on_customer_anonymized",
        ],
        "the owner's erasure reaches every app that listens, once each"
    );
}
