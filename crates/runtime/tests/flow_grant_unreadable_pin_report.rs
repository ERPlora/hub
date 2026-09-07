//! **The report of an unreadable grant pin actually leaves `authority()`** (ERPlora/hub#1636).
//!
//! hub#1636 made a `command` grant whose stored `payload` cannot be read stop authorising anything
//! (default-deny by absence, ADR-0283 D2). Refusing is only half of it: nothing reachable in the
//! product can WRITE that row, so the owner whose automation stopped has no path back to it — the
//! permissions screen still shows the grant as given, and `grantPin()` of the `flows` module reads
//! an unreadable pin as `{}` exactly like a grant that fixes nothing. The report is the only thread
//! joining «the automation stopped» to «this row has to be revoked and granted again».
//!
//! The unit test next to the code pins the CONTENT of that report by calling its builder, which is
//! the `failed_install_event` pattern (hub#1477). What no unit test can reach is the WIRING, because
//! `authority()` reports to the process-global [`ErrorRegistry`] and a `OnceLock` sink cannot be
//! swapped per test. Measured on this branch, that gap let two mutants live with the whole
//! `--lib flows` suite green (235 passed):
//!
//!   * deleting the `report(event)` call from `authority()` outright;
//!   * naming the wrong column in it (`r["flow_id"]` instead of `r["id"]`), so the report points at
//!     a row nobody can revoke.
//!
//! Both are exactly the silent regression the report exists to prevent, so the guard lives HERE: an
//! integration test owns its process, which is what makes `ErrorRegistry::install` usable — the same
//! reason `money_backfill_mixed_hub.rs` captures the global sink this way.
use std::sync::{Arc, Mutex};

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::flows::grants;
use erplora_runtime::{ErrorEvent, ErrorRegistry, ErrorSink};
use serde_json::json;

const HUB: &str = "hub-grant-report";
const FLOW: &str = "flow-1";
/// The id is the whole point of the report, so the test FIXES it instead of reading it back: an
/// assertion against whatever the row happens to hold would pass just as happily on a report that
/// names the wrong column.
const GRANT_ID: &str = "grant-unreadable-1";

struct CaptureSink(Mutex<Vec<ErrorEvent>>);

impl ErrorSink for CaptureSink {
    fn submit(&self, event: ErrorEvent) {
        self.0.lock().unwrap().push(event);
    }
}

/// The v0 baseline the real boot lays down (`Runtime::ensure_system_tables`) plus the versioned
/// migrations on top — the same bootstrap `flows_schema.rs` uses, and for the reason written there:
/// the migrations at or below v30 ALTER those baseline tables, so applying them over an empty
/// schema fails on `hub_module` long before reaching `_flow_grants`.
async fn apply_system_schema(db: &dyn DatabaseAdapter) {
    erplora_runtime::installer::ensure_hub_module_table(db)
        .await
        .expect("the v0 baseline the real boot lays down");
    erplora_runtime::identity::ensure_tables(db)
        .await
        .expect("the v0 baseline the real boot lays down");
    erplora_runtime::system_migrations::apply(db, HUB)
        .await
        .expect("the system schema is what holds `_flow_grants`");
}

/// Writes the row this guard exists for, by SQL and on purpose: no door of the kernel produces one
/// (the column is `NOT NULL DEFAULT '{}'`, `replace` always serialises an object), and a row that
/// arrived some other way — edited by hand, a botched column change, a mangled restore — is the
/// only way this state exists at all.
async fn insert_unreadable_grant(db: &dyn DatabaseAdapter, command: &str) {
    let mut p = Params::new();
    p.insert("id".into(), json!(GRANT_ID));
    p.insert("hub_id".into(), json!(HUB));
    p.insert("flow_id".into(), json!(FLOW));
    p.insert("value".into(), json!(command));
    db.execute(
        "INSERT INTO _flow_grants (id, hub_id, flow_id, kind, value, created_at, granted_by, payload) \
         VALUES (:id, :hub_id, :flow_id, 'command', :value, '2026-09-07T00:00:00Z', 'hub_user:1', 'garbage')",
        &p,
    )
    .await
    .expect("the fixture writes the row this guard exists for");
}

/// hub#1636 — the refusal is REPORTED, it names the row to re-grant, and it says so through the
/// registry the host really drains (`CloudErrorSink`), not only through a line on stderr that dies
/// inside the container.
#[tokio::test]
async fn an_unreadable_grant_pin_is_reported_naming_the_row_to_re_grant() {
    let db = fresh_db().await;
    apply_system_schema(&db).await;
    insert_unreadable_grant(&db, "sales.sale.void").await;

    let sink = Arc::new(CaptureSink(Mutex::new(Vec::new())));
    ErrorRegistry::install(sink.clone());

    // The real gate read, not a hand-built event: what is being pinned is that THIS call reports.
    let authority = grants::authority(&db, HUB, FLOW)
        .await
        .expect("an unreadable row is a denied grant, never a failed read");

    assert!(
        !authority.allows_command("sales.sale.void"),
        "an unreadable grant authorises nothing — the refusal is the premise of the report"
    );

    let events = sink.0.lock().unwrap();
    let report = events
        .iter()
        .find(|e| e.error_code == grants::ERR_UNREADABLE_GRANT_PAYLOAD_EVENT)
        .unwrap_or_else(|| {
            panic!(
                "`authority()` dropped the grant WITHOUT reporting it: the owner is left with a \
                 stopped automation and a screen that still shows the permission. Got {events:?}"
            )
        });
    assert_eq!(
        report.context["grant_id"],
        json!(GRANT_ID),
        "the report has to name the GRANT row to revoke and grant again; any other id sends whoever \
         reads it to a row they cannot act on"
    );
    assert_eq!(report.context["flow_id"], json!(FLOW));
    assert_eq!(report.context["command"], json!("sales.sale.void"));
}
