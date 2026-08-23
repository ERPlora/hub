//! **hub#1091** — `expect_rows`/`min_affected_rows` counted the BATCH, so an unconditional
//! statement next to the guarded one neutralized the gate: the caller got `200 ok`, nothing was
//! written, and an event was emitted for something that never happened. Measured on
//! `online_booking.bookings.create` (online_booking#25, P0): the booking INSERT misses (outside
//! the booking window), the reference-counter UPSERT always affects 1, the `min: 1` is satisfied
//! by the row that was not the one being watched. `schemas/module.schema.json:526` promised
//! «never a 200 ok with 0 rows nor a false event» — and the promise did not survive the second
//! statement.
//!
//! # The fix, and why it is opt-in
//!
//! `expect_rows.statement` anchors the gate to ONE statement (by its `sql` path). Only the
//! anchored statement counts; the rest of the batch cannot satisfy its contract on its behalf.
//!
//! The DEFAULT stays the documented batch-sum on purpose (sweep of the 25 modules, 22/08/2026):
//! `customers.consent.grant` sums 3 rows from 3 statements that affect 1 each — its `min: 3` IS
//! the batch; `customers.anonymize` has steps that may legitimately affect 0 ("no notes to
//! blank" is not a failure). Only the module knows which statement carries the guard, so the
//! anchor is how it says so. The install refuses an anchor naming no statement of the command:
//! a guard that silently degrades to the neutralized default is the very hole this closes.
//!
//! Real Postgres, ephemeral schema per test.
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{EventSink, EventSource, RequestContext, RuntimeError, Runtime};
use serde_json::{json, Value as Json};

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_gate1091")
        .join(name)
}

#[derive(Default, Debug)]
struct Sink {
    events: Mutex<Vec<String>>,
}

impl EventSink for Sink {
    fn emit(&self, _source: EventSource<'_>, name: &str, _payload: &Json) {
        self.events.lock().unwrap().push(name.to_string());
    }
}

async fn hub() -> (Runtime, Arc<Sink>) {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("gate")).await.expect("install gate");
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    (rt, sink)
}

fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

fn booking(window_ok: i64) -> Params {
    let mut p = Params::new();
    p.insert("ref".into(), json!("BK-1"));
    p.insert("window_ok".into(), json!(window_ok));
    p
}

async fn bookings(rt: &Runtime) -> i64 {
    let rows = rt.execute_query("gate.bookings.count", &Params::new(), &ctx()).await.unwrap();
    rows.first().and_then(|r| r["n"].as_i64()).unwrap_or(0)
}

async fn counter(rt: &Runtime) -> i64 {
    let rows = rt.execute_query("gate.counter", &Params::new(), &ctx()).await.unwrap();
    rows.first().and_then(|r| r["seq"].as_i64()).unwrap_or(0)
}

/// The acceptance case of the issue: guarded statement misses, unconditional sibling affects 1.
/// Before the fix (anchor ignored by the old core) the batch sum was 1 → `200 ok` + event with
/// no booking. With the anchor, the ONE statement that carries the contract is counted alone:
/// 409-shaped `Domain` rejection, nothing written (not even the counter), nothing emitted.
#[tokio::test]
async fn anchored_gate_rolls_back_when_the_guarded_statement_misses() {
    let (rt, sink) = hub().await;

    let err = rt
        .execute_command("gate.bookings.create", &booking(0), &ctx())
        .await
        .expect_err("the anchored statement affected 0 rows: the command must refuse");
    match err {
        RuntimeError::Domain { code, message } => {
            assert_eq!(code, "gate.outside_booking_window", "the declared stable code");
            assert!(message.contains("booking window"), "the declared message: {message}");
        }
        other => panic!("expected the module-declared domain rejection, got {other:?}"),
    }

    assert_eq!(bookings(&rt).await, 0, "no booking row may survive");
    assert_eq!(
        counter(&rt).await,
        0,
        "the whole tx rolled back — the unconditional counter may not land either"
    );
    assert!(
        sink.events.lock().unwrap().is_empty(),
        "no event for a booking that does not exist"
    );
}

/// The compat contract, spelled out: WITHOUT the anchor the documented batch-sum semantics
/// remain, exactly as `customers.consent.grant` (min: 3 over 3 statements) and every published
/// multi-statement gate relies on. This is today's neutralizable shape on purpose — it is why
/// the anchor exists and why the default does not change under published modules.
#[tokio::test]
async fn unanchored_gate_keeps_the_documented_batch_sum() {
    let (rt, sink) = hub().await;

    let out = rt
        .execute_command("gate.bookings.create_unanchored", &booking(0), &ctx())
        .await
        .expect("without the anchor, the batch sum (0 + 1 >= 1) is the contract, as today");
    assert_eq!(out["ok"], json!(true), "compat: the sum gate passes: {out:?}");
    assert_eq!(bookings(&rt).await, 0, "still nothing written by the guarded statement");
    assert_eq!(
        sink.events.lock().unwrap().len(),
        1,
        "compat: the unanchored gate still emits over the missed insert (the documented hole)"
    );
}

/// No false positives: when the anchored statement DOES hit, the command commits everything —
/// booking, counter, event — exactly like a single-statement gate always did.
#[tokio::test]
async fn anchored_gate_passes_when_the_guarded_statement_hits() {
    let (rt, sink) = hub().await;

    let out = rt
        .execute_command("gate.bookings.create", &booking(1), &ctx())
        .await
        .expect("the guarded statement affected 1 row: the command must commit");
    assert_eq!(out["ok"], json!(true), "{out:?}");
    assert_eq!(bookings(&rt).await, 1);
    assert_eq!(counter(&rt).await, 1, "the sibling statement committed with it");
    assert_eq!(sink.events.lock().unwrap().as_slice(), ["gate.booking.created"]);
}

/// An anchor that names no statement of its command is refused AT INSTALL: it would read as
/// "protected" while running with the neutralized default — the exact failure hub#1091 closes.
#[tokio::test]
async fn install_refuses_an_anchor_that_names_no_statement() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let err = rt
        .install_from_dir(&fixture("gate_broken"))
        .await
        .expect_err("a dangling anchor must not install");
    let msg = err.to_string();
    assert!(
        msg.contains("no_such_statement.sql") && msg.contains("gate_broken.bump"),
        "the refusal names the anchor and the command: {msg}"
    );
}
