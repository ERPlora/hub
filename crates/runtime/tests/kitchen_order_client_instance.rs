//! hub#2029 — the kitchen ticket a till fires tells the live channel WHICH till fired it.
//!
//! Every open shell hears every `kitchen.order.created`, and each one printed it: with two tills
//! that reach the kitchen printer, one order came out twice at the pass. hub#1980 stamped the frame
//! with the shell tab that sent the request, but the kitchen ticket is not born in that request: the
//! till fires the ORDER (`sales.order.fire` → `order.fired`), and `kitchen` makes its ticket in a
//! LISTENER the outbox relay runs afterwards, with a context rebuilt from the outbox row. Without the
//! tab on that row, the ticket reaches the channel as nobody's — and no till can tell it is its own.
//! So the positive here is the real chain: the real modules, fired the way a till fires, drained the
//! way the relay drains.
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{EventSink, EventSource, RequestContext, Runtime};
use serde_json::json;

#[derive(Default, Debug)]
struct Sink {
    /// `(event, client_instance)` as the dispatcher handed them to the live channel.
    seen: Mutex<Vec<(String, Option<String>)>>,
}
impl EventSink for Sink {
    fn emit(&self, _source: EventSource<'_>, name: &str, _payload: &serde_json::Value) {
        self.seen.lock().unwrap().push((name.to_string(), None));
    }
    fn emit_from(
        &self,
        _source: EventSource<'_>,
        client_instance: Option<&str>,
        name: &str,
        _payload: &serde_json::Value,
    ) {
        self.seen
            .lock()
            .unwrap()
            .push((name.to_string(), client_instance.map(str::to_string)));
    }
}

fn mdir(name: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(name)
}

async fn restaurant() -> (Runtime, Arc<Sink>) {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), "h1");
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    for m in ["taxes", "inventory", "customers", "sales", "kitchen"] {
        rt.install_from_dir(&mdir(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    (rt, sink)
}

/// Opens an order and fires it to the kitchen, as the floor does, then lets the relay run.
async fn fire(rt: &Runtime, ctx: &RequestContext) {
    let items = json!({
        "items": [{ "product_name": "Entrecot", "price": 1800, "quantity": 1_000_000 }],
        "label": "Mesa 4",
    });
    let opened = rt
        .execute_command("sales.order.open", items.as_object().unwrap(), ctx)
        .await
        .expect("the order must open");
    let order_id = opened["new_ids"][0].clone();
    assert!(order_id.is_string(), "the order id in new_ids[0]: {opened}");
    let mut fire = Params::new();
    fire.insert("order_id".into(), json!(order_id));
    fire.insert("label".into(), json!("Mesa 4"));
    rt.execute_command("sales.order.fire", &fire, ctx)
        .await
        .expect("the order must fire");
    rt.drain_outbox().await.expect("the relay must drain");
}

fn kitchen_order_created(sink: &Sink) -> Vec<Option<String>> {
    sink.seen
        .lock()
        .unwrap()
        .iter()
        .filter(|(name, _)| name == "kitchen.order.created")
        .map(|(_, instance)| instance.clone())
        .collect()
}

#[tokio::test]
async fn the_kitchen_ticket_carries_the_till_that_fired_it_hub2029() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let (rt, sink) = restaurant().await;
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]).with_client_instance("till-a");

    fire(&rt, &ctx).await;

    assert_eq!(kitchen_order_created(&sink), vec![Some("till-a".to_string())]);
}

#[tokio::test]
async fn an_order_no_shell_fired_is_nobodys_till_hub2029() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let (rt, sink) = restaurant().await;
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);

    fire(&rt, &ctx).await;

    // Positive control of the filter above: the ticket DID reach the channel, just without a till.
    assert_eq!(kitchen_order_created(&sink), vec![None]);
}
