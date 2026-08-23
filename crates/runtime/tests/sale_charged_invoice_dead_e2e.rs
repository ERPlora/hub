//! **hub#784 — a sale that CHARGES and cannot be invoiced is never lost in silence.**
//!
//! Measured in production (`demo-76321267`, 2026-08-10) on a hub whose fiscal identity was
//! incomplete: `sales.complete_sale` answered `200`, `invoice.list` came back with `0` rows, and
//! the hub's log carried
//!
//! ```text
//! ERROR sale.completed — invoice.create_from_sale: fiscal precondition failed:
//!       configure business_legal_name, business_tax_id
//! ```
//!
//! The money went one way and the document another. hub#684 removed the CAUSE for the demo (ADR-0305
//! seeds the identity), and deliberately did not touch the BEHAVIOUR: `enforce_fiscal_precondition`
//! (ADR-0203) does not know what a demo is, so any hub whose identity ends up incomplete — a wiped
//! setting, a half-finished blueprint (hub#751/#752) — walks the same path.
//!
//! **The question hub#784 asks is not "does the listener refuse".** That is already pinned, as a
//! unit, in `outbox.rs::the_fiscal_precondition_still_stops_a_listener_that_stamps_the_issuer`, and
//! the refusal is the right answer: an invoice with a BLANK issuer is what VeriFactu would then
//! chain from (ADR-0189). The question is what happens to that refusal AFTERWARDS — whether the
//! failure surfaces where a human sees it, or dies quietly. The issue says so itself: if the row
//! reaches the dead-letter and lights the badge (hub#660 + hub#747) the hole is small and somebody
//! can act on it; **if it does not land, nobody ever learns the invoice is missing.**
//!
//! So that is what this test walks, end to end and through the real doors — a real `sales` module,
//! a real `invoice` module, the real relay, the real dead-letter API the screen reads:
//!
//! 1. the sale is charged and NO invoice exists (the production observation, reproduced);
//! 2. the row burns its [`MAX_ATTEMPTS`] and lands in the dead-letter, carrying the fiscal reason,
//!    so `count_dead_events` — the badge — is non-zero;
//! 3. and the remedy WORKS: stamp the identity, retry the dead-letter, and the invoice of that very
//!    sale appears, with the money it was charged.
//!
//! Point 3 is what makes the first two bearable, and it is the half nobody had verified: an
//! operable dead-letter that could not actually recover THIS failure would be a badge that only
//! reports a loss. It also pins that the sale is not billed twice on the way back.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}
/// The ctx shares the Runtime's `hub_id` so the settings written here and the dispatcher's enricher
/// read the SAME `hub_settings` row — the fiscal precondition keys on it (hub#328, ADR-0203).
fn admin() -> RequestContext {
    RequestContext::new(erplora_runtime::DEV_HUB_ID, "u1", ["*".to_string()])
}
fn wasm() -> bool {
    mdir("invoice").join("dist/handler.wasm").exists()
}

/// A hub with the real chain installed and **no business identity**: the shape of the incomplete
/// hub the issue is about. Everything else is exactly the production wiring.
async fn hub_without_fiscal_identity() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    // `invoice` declares `depends_on: ["sales"]`, and `sales` needs `inventory`+`taxes`, so the
    // order is the install order, not a preference.
    for m in ["taxes", "inventory", "customers", "sales", "invoice"] {
        rt.install_from_dir(&mdir(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    rt
}

/// The cash payment method of this hub's catalogue. Resolved through the public query instead of
/// composing the seed's id by hand, so the test is not tied to how `sales` builds its ids.
async fn cash_method_id(rt: &Runtime, ctx: &RequestContext) -> String {
    let rows = rt
        .execute_query("sales.payment_methods", &Params::new(), ctx)
        .await
        .expect("sales.payment_methods");
    rows.iter()
        .find(|r| r["type"] == json!("cash"))
        .unwrap_or_else(|| panic!("the hub catalogue must ship the `cash` method: {rows:?}"))["id"]
        .as_str()
        .expect("payment method id")
        .to_string()
}

/// Moves every deferred row's due time into the past — the ONLY thing this test fakes, and it fakes
/// the clock, never the gate. The relay's backoff is exponential (`2^attempts`, capped at an hour),
/// so without this the ladder to the dead-letter takes the best part of ten minutes of wall time.
/// Each cycle still goes through the real `claim → execute listener → defer_or_dead`.
async fn wind_the_backoff_forward(rt: &Runtime) {
    let mut p = Params::new();
    p.insert(
        "past".into(),
        json!((chrono::Utc::now() - chrono::Duration::hours(2)).to_rfc3339()),
    );
    rt.db()
        .execute(
            "UPDATE _event_outbox SET next_attempt_at = :past, claim_expires_at = NULL \
             WHERE status = 'pending'",
            &p,
        )
        .await
        .expect("age the queue");
}

/// Runs the relay until nothing is `pending` any more: either everything was delivered, or what is
/// left burnt its attempts and is `dead`. Bounded so a regression that never resolves a row fails
/// the test instead of hanging it.
async fn run_the_relay_to_exhaustion(rt: &Runtime) {
    for _ in 0..(erplora_runtime::outbox::MAX_ATTEMPTS + 4) {
        rt.drain_outbox().await.expect("drain");
        wind_the_backoff_forward(rt).await;
    }
    rt.drain_outbox().await.expect("drain");
}

async fn pending_rows(rt: &Runtime) -> i64 {
    rt.db()
        .query(
            "SELECT COUNT(*) AS c FROM _event_outbox WHERE status = 'pending'",
            &Params::new(),
        )
        .await
        .expect("count pending")
        .rows[0]["c"]
        .as_i64()
        .unwrap_or(-1)
}

/// **The whole of hub#784, in one walk.** Charged, not invoiced, and then FOUND and recovered.
#[tokio::test]
async fn a_sale_that_cannot_be_invoiced_lands_in_the_dead_letter_and_is_recoverable() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !wasm() {
        eprintln!("SKIP: invoice handler.wasm missing");
        return;
    }
    let rt = hub_without_fiscal_identity().await;
    let ctx = admin();

    // ── 1 · The production observation, reproduced ────────────────────────────────────────────
    // The cashier charges. `sales.complete_sale` does NOT stamp the issuer, so the fiscal
    // precondition has nothing to refuse here and the sale goes through — which is the point: the
    // money is taken before anything fiscal is asked.
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "idempotency_key": "hub784-charged-but-not-invoiced",
            "payment_method_id": cash_method_id(&rt, &ctx).await,
            "customer_name": "Bar Manolo",
            "tax_included": false,
            "items": [{ "product_name": "Café", "price": 200, "quantity": 2_000_000, "tax_rate": 21.0 }]
        })),
        &ctx,
    )
    .await
    .expect("the sale is charged: the cashier is never blocked by a documentary problem (ADR-0288)");

    let sales = rt
        .execute_query("sales.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(sales.len(), 1, "the sale exists: {sales:?}");
    let sale_id = sales[0]["id"].as_str().unwrap().to_string();

    run_the_relay_to_exhaustion(&rt).await;

    let invoices = rt
        .execute_query("invoice.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert!(
        invoices.is_empty(),
        "the refusal is the correct answer — an invoice with a BLANK issuer is what VeriFactu \
         would chain from (ADR-0189). What must not happen is that NOBODY finds out: {invoices:?}"
    );

    // ── 2 · …and the failure surfaces. This is the question hub#784 asks ──────────────────────
    // If this assert ever goes red, the answer to the issue is «it does not land» and hub#784 is a
    // P0: the cashier charges, the customer leaves, and no human is ever told the invoice is
    // missing. The row must not be left circling as `pending` for ever either.
    assert_eq!(
        pending_rows(&rt).await,
        0,
        "a row that can never succeed must reach a terminal state, not retry silently for ever"
    );
    let badge = rt.count_dead_events().await.expect("dead count");
    assert_eq!(
        badge, 1,
        "the badge (hub#747) reads this count: at zero, the loss is invisible to every human"
    );

    let dead = rt.list_dead_events(50).await.expect("dead-letter listing");
    let row = dead
        .iter()
        .find(|d| d.event_name == "sale.completed")
        .unwrap_or_else(|| panic!("the dead-letter must hold the sale's event: {dead:?}"));
    assert!(
        row.last_error.contains("invoice.create_from_sale"),
        "the operator has to be able to tell WHICH listener refused: {}",
        row.last_error
    );
    assert!(
        row.last_error.contains("business_tax_id")
            || row.last_error.contains("business_legal_name"),
        "…and WHY, by name, or the remedy is a guess: {}",
        row.last_error
    );
    // It burnt the whole ladder before being given up on — it did not die on the first stumble.
    // The counter reads `MAX_ATTEMPTS - 1` and not `MAX_ATTEMPTS`, which is the counter's semantics
    // rather than a lost attempt: `defer_or_dead` gives up when the NEXT attempt would reach the
    // cap (`next >= MAX_ATTEMPTS`), and `mark_dead` records the reason without bumping the count it
    // is no longer deferring. So the row really was delivered to `MAX_ATTEMPTS` times.
    assert_eq!(
        row.attempts,
        erplora_runtime::outbox::MAX_ATTEMPTS - 1,
        "it burnt its whole budget of retries before being given up on: {row:?}"
    );
    // …and it is an ORDINARY dead-letter, which is the half hub#827 makes worth stating: that
    // change made a row terminal on the first pass when retrying it can never work (a flow whose
    // authorisation was withdrawn). A missing invoice is the opposite case — the cause is the hub's
    // fiscal identity, and completing it is exactly what a human can do — so this row must keep its
    // ladder and its button. If it ever came back `retryable: false`, the screen would stop
    // offering the one gesture that recovers the money already taken.
    assert!(
        row.failure_kind.is_empty() && row.retryable,
        "a missing invoice is recoverable, not a dead end: {row:?}"
    );

    // ── 3 · The remedy really works ───────────────────────────────────────────────────────────
    // The admin does what the dead-letter told them to: completes the fiscal identity and replays.
    // A dead-letter that could not recover THIS failure would be a badge that only reports a loss.
    let mut identity = serde_json::Map::new();
    identity.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    identity.insert("business_tax_id".into(), json!("B12345674"));
    rt.set_settings(&identity, "u1")
        .await
        .expect("stamp the hub's fiscal identity");

    assert_eq!(
        rt.retry_dead_event(&row.id).await.expect("retry"),
        erplora_runtime::outbox::RetryOutcome::Requeued,
        "the dead-letter of this hub goes back in front of the relay"
    );
    run_the_relay_to_exhaustion(&rt).await;

    let invoices = rt
        .execute_query("invoice.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(
        invoices.len(),
        1,
        "the invoice of the sale that was already charged now exists: {invoices:?}"
    );
    let invoice = &invoices[0];
    assert_eq!(invoice["source_type"], json!("sale"), "origin = the sale");
    // …and THAT sale. `invoice.list` does not project `source_id`, so the link is read from the
    // column that carries it — the same one whose partial UNIQUE index enforces «one invoice per
    // sale» (D2). Checking `source_type` alone would pass for an invoice of any other sale.
    let linked = rt
        .db()
        .query(
            "SELECT source_id FROM invoice_invoice WHERE id = :id",
            &params(json!({ "id": invoice["id"].as_str().unwrap() })),
        )
        .await
        .expect("read the invoice's origin");
    assert_eq!(
        linked.rows[0]["source_id"].as_str(),
        Some(sale_id.as_str()),
        "the recovered invoice belongs to the sale that was charged, not to a new one"
    );
    assert_eq!(
        invoice["total_amount"].as_i64(),
        Some(484),
        "for the money that was charged (2 × 2,00 € + 21 %): {invoice:?}"
    );
    assert_eq!(
        rt.count_dead_events().await.expect("dead count"),
        0,
        "and the badge goes out, so a recovered failure does not look like a live one"
    );
}
