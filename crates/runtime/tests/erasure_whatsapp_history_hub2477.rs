//! **hub#2477** — erasing a customer's sheet empties what she wrote on WhatsApp from the hub's own
//! history, through the real dispatcher, relay and modules.
//!
//! An inbound WhatsApp message lands in `_event_outbox` as a chain that never names her sheet: the
//! kernel's `hub.whatsapp.message_received` (number and text), the inbox's
//! `whatsapp_inbox.message.received` (the same plus the id of the message row) and what reacted to
//! it. Since hub#2467 the erasure emptied only the rows that name `customer_id`, so her messages
//! stayed there for the 90 days of `retention`. Now the hub follows the erasure into the tables of
//! the apps that listen to it — her thread, then its messages — and empties the whole chain.
//!
//! **hub#2474** — the same for a number with no sheet: the inbox's «Erase this number's data» emits
//! `whatsapp_inbox.conversation.anonymized` and the hub follows that thread to its messages.
//!
//! The real `customers` and `whatsapp_inbox` modules; real Postgres, ephemeral schema per test.
//! The job without the catalogue skips it visibly (`require_modules_workspace`); the unit tests in
//! `erasure.rs` cover the same chain there.
use erplora_db::{testutil::fresh_db, Params};
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
        .map(|r| r["v"].as_str().unwrap_or_default().to_string())
        .collect()
}

/// A sheet created by the real customers app; returns its id.
async fn customer(rt: &Runtime, name: &str, phone: &str) -> String {
    rt.execute_command(
        "customers.create",
        &params(json!({ "name": name, "phone": phone })),
        &admin(),
    )
    .await
    .expect("customers.create");
    rt.drain_outbox().await.expect("drain");
    rows(
        rt,
        "SELECT id AS v FROM customers_customer WHERE hub_id = :hub_id AND name = :name",
        &[("name", name)],
    )
    .await
    .pop()
    .expect("the sheet exists")
}

/// What the inbound poll writes for one message from `number` (digits, as Meta reports it), and
/// what the relay does with it: the inbox stores it and links the thread to the sheet of that
/// number.
async fn writes(rt: &Runtime, wamid: &str, number: &str, text: &str) {
    let payload = params(json!({
        "wa_message_id": wamid,
        "from": number,
        "direction": "inbound",
        "contact": number,
        "source": "live",
        "text": text,
        "received_at": "2026-10-09T08:00:00+00:00",
        "message": { "id": wamid, "from": number, "type": "text", "text": { "body": text } },
    }));
    erplora_runtime::outbox::insert_core_event_once(
        rt.db(),
        &format!("wa-{wamid}"),
        erplora_runtime::DEV_HUB_ID,
        "hub.whatsapp.message_received",
        &payload,
    )
    .await
    .expect("core event");
    for _ in 0..3 {
        rt.drain_outbox().await.expect("drain");
    }
}

/// Every history row whose payload still holds `needle`, as `event_name`.
async fn history_holding(rt: &Runtime, needle: &str) -> Vec<String> {
    rows(
        rt,
        "SELECT event_name AS v FROM _event_outbox \
          WHERE hub_id = :hub_id AND strpos(payload, :needle) > 0 ORDER BY created_at",
        &[("needle", needle)],
    )
    .await
}

#[tokio::test]
async fn erasing_a_sheet_empties_what_she_wrote_on_whatsapp_hub2477() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = hub().await;
    let ana = customer(&rt, "Ana Pérez", "+34600111222").await;
    customer(&rt, "Bea Ruiz", "+34600333444").await;
    writes(&rt, "wamid.ANA1", "34600111222", "Hola, soy Ana").await;
    writes(&rt, "wamid.BEA1", "34600333444", "Hola, soy Bea").await;

    // The premise: her thread is linked to her sheet, and history holds what she wrote.
    assert_eq!(
        rows(
            &rt,
            "SELECT customer_id AS v FROM whatsapp_inbox_conversation \
              WHERE hub_id = :hub_id AND wa_contact_id = '34600111222'",
            &[],
        )
        .await,
        vec![ana.clone()],
        "the inbox linked her thread to her sheet"
    );
    let before = history_holding(&rt, "soy Ana").await;
    assert!(
        before.contains(&"hub.whatsapp.message_received".to_string())
            && before.contains(&"whatsapp_inbox.message.received".to_string()),
        "history holds the kernel's and the inbox's copies: {before:?}"
    );

    rt.execute_command(
        "customers.anonymize",
        &params(json!({ "customer_id": ana, "reason": "gdpr request" })),
        &admin(),
    )
    .await
    .expect("customers.anonymize");
    rt.drain_outbox().await.expect("drain");

    assert_eq!(
        rows(
            &rt,
            "SELECT status AS v FROM _event_outbox \
              WHERE hub_id = :hub_id AND event_name = 'customer.anonymized'",
            &[],
        )
        .await,
        vec!["delivered".to_string()]
    );
    for said in ["soy Ana", "600111222", "wamid.ANA1"] {
        assert_eq!(
            history_holding(&rt, said).await,
            Vec::<String>::new(),
            "history still holds {said:?}"
        );
    }
    assert!(
        history_holding(&rt, "soy Bea").await.len() >= 2,
        "Bea's messages are not hers to erase"
    );
}

/// **hub#2474** — the same, for a number with no sheet: «Erase this number's data» in the inbox
/// emits `whatsapp_inbox.conversation.anonymized`, and the hub follows that thread to its messages.
#[tokio::test]
async fn erasing_a_number_empties_what_it_wrote_on_whatsapp_hub2474() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = hub().await;
    writes(&rt, "wamid.NUM1", "254712345678", "Hola, soy de Nairobi").await;
    writes(&rt, "wamid.BEA1", "34600333444", "Hola, soy Bea").await;
    let thread = rows(
        &rt,
        "SELECT id AS v FROM whatsapp_inbox_conversation \
          WHERE hub_id = :hub_id AND wa_contact_id = '254712345678'",
        &[],
    )
    .await
    .pop()
    .expect("the inbox opened a thread for the number");
    assert!(
        !history_holding(&rt, "de Nairobi").await.is_empty(),
        "history holds what the number wrote"
    );

    rt.execute_command(
        "whatsapp_inbox.conversations.erase",
        &params(json!({ "conversation_id": thread })),
        &admin(),
    )
    .await
    .expect("whatsapp_inbox.conversations.erase");
    rt.drain_outbox().await.expect("drain");

    assert_eq!(
        rows(
            &rt,
            "SELECT status AS v FROM _event_outbox \
              WHERE hub_id = :hub_id AND event_name = 'whatsapp_inbox.conversation.anonymized'",
            &[],
        )
        .await,
        vec!["delivered".to_string()]
    );
    for said in ["de Nairobi", "254712345678", "wamid.NUM1"] {
        assert_eq!(
            history_holding(&rt, said).await,
            Vec::<String>::new(),
            "history still holds {said:?}"
        );
    }
    assert!(
        history_holding(&rt, "soy Bea").await.len() >= 2,
        "another number's messages are not its to erase"
    );
}
