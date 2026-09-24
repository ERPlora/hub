//! hub#1980 — the REAL checkout (`sales.complete_sale`, a WASM handler) tells the live channel which
//! shell tab charged the sale.
//!
//! The server test (`crates/server/tests/event_client_instance.rs`) pins the door and the frame with
//! a declarative command. A sale is not declarative: its `sale.completed` comes out of the handler's
//! output, through a different emission site of the dispatcher. That site forgetting the instance
//! would leave every till printing every sale again, with the door's test still green — so the
//! positive here is the real module, charged the way a till charges it.
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

async fn till() -> (Runtime, Arc<Sink>) {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), "h1");
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    for m in ["taxes", "inventory", "customers", "sales"] {
        rt.install_from_dir(&mdir(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    (rt, sink)
}

async fn charge(rt: &Runtime, ctx: &RequestContext, key: &str) {
    let methods = rt
        .execute_query("sales.payment_methods", &Params::new(), ctx)
        .await
        .expect("sales.payment_methods");
    let cash = methods
        .iter()
        .find(|r| r["type"] == json!("cash"))
        .expect("the seeded cash method")["id"]
        .clone();
    let payload = json!({
        "idempotency_key": key,
        "payment_method_id": cash,
        // An open-price line with no tax category: the one line whose `tax_rate` the handler honours.
        "items": [{ "product_name": "Corte", "price": 1500, "quantity": 1_000_000, "tax_rate": 21.0 }],
        "tax_included": true,
        "amount_tendered": 1500,
    });
    rt.execute_command("sales.complete_sale", payload.as_object().unwrap(), ctx)
        .await
        .expect("the sale must be charged");
}

fn sale_completed(sink: &Sink) -> Vec<Option<String>> {
    sink.seen
        .lock()
        .unwrap()
        .iter()
        .filter(|(name, _)| name == "sale.completed")
        .map(|(_, instance)| instance.clone())
        .collect()
}

#[tokio::test]
async fn the_real_checkout_carries_the_till_that_charged_hub1980() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let (rt, sink) = till().await;
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]).with_client_instance("till-a");

    charge(&rt, &ctx, "hub1980-till-a").await;

    assert_eq!(sale_completed(&sink), vec![Some("till-a".to_string())]);
}

#[tokio::test]
async fn a_checkout_no_shell_sent_is_nobodys_till_hub1980() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let (rt, sink) = till().await;
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);

    charge(&rt, &ctx, "hub1980-no-shell").await;

    // Positive control of the filter above: the sale DID reach the channel, just without a till.
    assert_eq!(sale_completed(&sink), vec![None]);
}
