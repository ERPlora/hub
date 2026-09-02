//! Retention: the hub forgets its own HISTORY after 90 days — and only the history (hub#699).
//!
//! …with **one table on a clock of its own**: the receipt of a human approval, which is kept for
//! **four years** (hub#903, ADR-0351). See "The receipt keeps its own window" below.
//!
//! `_event_outbox`, `_flow_runs` and `_flow_run_steps` were append-only: nothing in the whole of
//! `crates/` ever deleted a row from them. Every event a hub has ever emitted, and every step of
//! every automation run — with its resolved `input` and its `output`, both TEXT — accumulated for
//! the life of the hub, in a database that is charged per gigabyte.
//!
//! # The line this draws
//!
//! **It prunes the history, never the durability.** An event goes to the database precisely so a
//! restart cannot lose it, and that property has no expiry date:
//!
//! - `pending` is *not yet delivered*. It survives at any age. Pruning it would be the data loss
//!   the outbox exists to prevent.
//! - `dead` is *waiting for a human to decide* (retry or discard, hub#660). It survives at any
//!   age: an operator who opens the dead-letter after a holiday must find what died there.
//! - `delivered` / `discarded` are **terminal** — the work is done or has been closed by hand.
//!   Past the window they are audit trail, and that is what gets cut.
//!
//! Same shape for runs: `done`/`failed`/`cancelled` are prunable; `running`, `sleeping` and
//! `waiting_approval` are live work and are never touched at any age (`waiting_approval` can sit
//! there for days by design — ADR-0283 §7).
//!
//! **That exemption used to be unbounded** (hub#972). The 72 h TTL of an approval was checked only
//! when somebody tried to decide it, so a proposal nobody answered left its run in
//! `waiting_approval` for ever — and the run kept the proposal, whose `payload` is stored verbatim
//! and can hold a customer's name and phone. The hourly tick now sweeps overdue proposals first
//! (`flows::approvals::sweep_expired`), which puts their runs in a terminal status, and this prune
//! deletes `_flow_approvals` together with the runs it removes. "Live work is exempt" is only
//! honest if work stops being live.
//!
//! What is actually lost after 90 days is **traceability**: `/api/hub/events/{id}/trace`, the run
//! history behind a sale. No invoice is affected — `_event_outbox` stores the *event*, while the
//! document lives in the `invoice`/`verifactu` module tables under its own fiscal retention. The
//! VeriFactu chain does not pass through here.
//!
//! # Decisions taken here (hub#699, Ioan 2026-08-10)
//!
//! - **90 days, fixed, no per-type distinction and no per-hub setting.** A knob is a thing to get
//!   wrong: it would need a UI, a migration and a story for the hub that sets it to one day. The
//!   window is a constant because the honest answer to "who will tune this?" is nobody.
//! - **Hard `DELETE`, not soft-delete.** For `_flow_run_steps` this is not a preference: its
//!   unique index is `(run_id, step_index) WHERE deleted_at IS NULL`, so stamping `deleted_at`
//!   *frees the slot* and a later retry could re-insert the same `step_index` — the exact
//!   duplicate that index exists to catch (v35: "instead of quietly doubling an invoice").
//!   Soft-deleting rows we are removing to save space would also save no space.
//! - **Children before parents, in one statement.** `_event_delivery` has no foreign key to
//!   `_event_outbox` and `_flow_run_steps` has none to `_flow_runs` — the link is by convention,
//!   so nothing in the database would stop a prune from leaving orphans. Deleting the child in the
//!   same statement as the parent (a data-modifying CTE, so it is one atomic snapshot) is what
//!   makes an orphan impossible, including across a crash mid-prune. An orphaned idempotency
//!   marker is the worst of both worlds: the table keeps growing and the row means nothing.
//! - **Bounded and incremental.** [`BATCH`] rows per table per pass, in the background tick — not
//!   one mass `DELETE` that takes a lock over the whole table at the tills' busiest hour.
//! - **It is counted.** [`prune_once`] returns what it deleted so the caller can log it. A silent
//!   prune is indistinguishable from data loss the day somebody looks for an old event and does
//!   not find it.
//!
//! The one thing that ages a row is its TERMINAL moment, not its birth: an event that sat pending
//! for months and was delivered yesterday is a day old for this purpose, not months.
//!
//! # The receipt keeps its own window (hub#903, ADR-0351)
//!
//! `_elevation_audit` — «manager Sofía authorised cashier Nacho to void this ticket» — was the one
//! table nothing here touched, and it is precisely the one that carries employees' names. The hub
//! ended up forgetting almost everything **except** the register with people in it: the opposite
//! of what a retention policy is for.
//!
//! It does not join the 90 days. It gets **[`APPROVAL_AUDIT_DAYS`] — four years**, because the two
//! rows are not the same kind of thing, and the split is the whole policy:
//!
//! > **The receipt of who authorised what is kept four years. The content that was authorised is
//! > kept ninety days.**
//!
//! - A **receipt** is `command` + `permission` + two user ids + a **fingerprint** of the payload.
//!   The payload is hashed, never stored, so the row carries no third party's personal data by
//!   construction. Four years costs nothing in privacy and buys all of the evidence.
//! - The **content** is `_flow_approvals.payload`, stored verbatim — a customer's name and phone.
//!   Minimisation (art. 5.1.c) pushes that the other way, so it stays 90 days and dies with its
//!   run, which is what hub#972 already made honest by sweeping expired proposals first.
//!
//! Why four years, when the market keeps this for ever (four ERPs never purge it; the only
//! published number in eleven references is Shopify POS's one year): art. 5.1.e needs a limit and
//! WP260 says "as long as necessary" is not one. Four is the number the Spanish legislator chose
//! for the closest analogue (art. 34.9 ET, the working-time register), the tax prescription period
//! (art. 66 LGT) and the AEPD's own blocking table; it clears the three years of art. 4.1 LISOS
//! with room. Five and six years belong to the *document* — and the document is not here: the
//! invoice lives in the `invoice`/`verifactu` module tables under its own fiscal retention, the
//! same line ADR-0309 already drew.
//!
//! **Deleting an employee is not a thing the hub does.** `DELETE /api/hub/users/:id` deactivates
//! (`is_active = 0`); the only `DELETE FROM hub_user` in `crates/` is the factory reset. So the
//! attribution is never cascaded and never nulled — the receipt keeps the id and the reader
//! resolves the name by `LEFT JOIN`. Anonymising early (Lightspeed's answer) is deliberately not
//! done: art. 17.3.b/e shields the receipt from an erasure request while the period runs, and the
//! *bloqueo* the law grants afterwards collapses, in a hub, into this prune. **The prune is the
//! erasure.**

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;

/// How long a hub keeps its terminal history. Fixed on purpose — see the module header.
pub const RETENTION_DAYS: i64 = 90;

/// How long a hub keeps the RECEIPT of a human approval (`_elevation_audit`) — **four years**,
/// and deliberately not [`RETENTION_DAYS`] (hub#903, ADR-0351).
///
/// 1461 and not 1460: four calendar years contain one leap day, so the window rounds **up** and
/// can never come out short of four years.
pub const APPROVAL_AUDIT_DAYS: i64 = 1461;

/// The two clocks a prune runs on.
///
/// Passed in rather than computed inside, for the same reason the single `cutoff` used to be: the
/// caller owns the clock, which is what lets a test age a row four years without waiting four
/// years. Two fields and not two arguments so a caller cannot swap them by accident — putting the
/// history's 90 days on the receipts is a silent four-year data loss.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Cutoffs {
    /// Terminal history — events, runs, steps, proposals. [`RETENTION_DAYS`].
    pub history: String,
    /// Approval receipts. [`APPROVAL_AUDIT_DAYS`].
    pub receipts: String,
}

impl Cutoffs {
    /// Both windows measured back from one instant.
    pub fn at(now: chrono::DateTime<chrono::Utc>) -> Self {
        Self {
            history: (now - chrono::Duration::days(RETENTION_DAYS)).to_rfc3339(),
            receipts: (now - chrono::Duration::days(APPROVAL_AUDIT_DAYS)).to_rfc3339(),
        }
    }

    /// Both windows, now.
    pub fn now() -> Self {
        Self::at(chrono::Utc::now())
    }
}

/// Rows per table per pass. Small enough that the `DELETE` never holds a long lock on a table the
/// tills are writing to; the pass simply repeats until there is nothing left.
pub const BATCH: i64 = 500;

/// Passes per tick. `BATCH * MAX_PASSES` is the ceiling on one tick's work, so a hub that has been
/// accumulating for a year drains over several ticks instead of stalling one for minutes.
pub const MAX_PASSES: usize = 20;

/// What a prune deleted. Returned rather than logged so `crates/runtime` stays free of a logging
/// facility (same contract as the flows `TickReport`): the caller in `crates/server` has `tracing`.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct PruneReport {
    /// Terminal `_event_outbox` rows removed.
    pub events: u64,
    /// `_event_delivery` idempotency markers removed with them.
    pub delivery_markers: u64,
    /// Terminal `_flow_runs` rows removed.
    pub runs: u64,
    /// `_flow_run_steps` rows removed with those runs.
    pub run_steps: u64,
    /// `_flow_approvals` rows removed with those runs (hub#972).
    pub approvals: u64,
    /// `_flow_run_waits` rows removed with those runs (hub#951). A wait is a child of its run in
    /// the same sense a step is: it only ever meant «while this run sleeps».
    pub waits: u64,
    /// `_elevation_audit` receipts removed on their OWN four-year clock (hub#903).
    pub receipts: u64,
}

impl PruneReport {
    /// Every row this prune deleted, across the five tables.
    pub fn total(&self) -> u64 {
        self.events
            + self.delivery_markers
            + self.runs
            + self.run_steps
            + self.approvals
            + self.waits
            + self.receipts
    }

    /// Nothing to do — the common case, and the one the caller must not log.
    pub fn is_empty(&self) -> bool {
        self.total() == 0
    }

    /// Fold one pass into the running total. Public because the server drives the passes itself:
    /// it re-takes the runtime lock per pass so the 1s relay tick is never shut out for a whole
    /// sweep, and therefore cannot use [`prune`]'s internal loop.
    pub fn merge(&mut self, other: PruneReport) {
        self.events += other.events;
        self.delivery_markers += other.delivery_markers;
        self.runs += other.runs;
        self.run_steps += other.run_steps;
        self.approvals += other.approvals;
        self.waits += other.waits;
        self.receipts += other.receipts;
    }
}

/// The terminal outbox statuses and their children, in one atomic statement.
///
/// `COALESCE(delivered_at, discarded_at, created_at)` is the row's terminal moment: `delivered_at`
/// for a delivered row, `discarded_at` for one an admin closed, and `created_at` only as a floor
/// for rows written before those columns existed (they arrived with hub#660).
const PRUNE_EVENTS: &str = "\
WITH doomed AS (\
  SELECT id FROM _event_outbox \
   WHERE hub_id = :hub_id \
     AND status IN ('delivered', 'discarded') \
     AND COALESCE(delivered_at, discarded_at, created_at) < :cutoff \
   ORDER BY COALESCE(delivered_at, discarded_at, created_at) \
   LIMIT :lim\
), markers AS (\
  DELETE FROM _event_delivery WHERE event_id IN (SELECT id FROM doomed) RETURNING event_id\
), events AS (\
  DELETE FROM _event_outbox WHERE id IN (SELECT id FROM doomed) RETURNING id\
) SELECT (SELECT COUNT(*) FROM markers) AS markers, (SELECT COUNT(*) FROM events) AS events";

/// The terminal runs and their children — steps AND approvals — in one atomic statement.
///
/// The children are deleted by `run_id` alone, deliberately: the doomed set is already scoped to
/// the hub, and re-filtering them by `hub_id` would let a row written with a wrong `hub_id` survive
/// its run as an orphan — hiding the bug instead of removing the row.
///
/// `_flow_approvals` joined this in hub#972, and it is not bookkeeping: the row keeps the proposed
/// `payload` VERBATIM, which is exactly where a customer's name, phone or address ends up. Nothing
/// in the hub ever deleted from that table, so a proposal used to outlive by years the run that
/// explains it. It is a child of its run in the same sense a step is — and while its run is live
/// (`waiting_approval` at any age), neither of them is touched.
const PRUNE_RUNS: &str = "\
WITH doomed AS (\
  SELECT id FROM _flow_runs \
   WHERE hub_id = :hub_id \
     AND status IN ('done', 'failed', 'cancelled') \
     AND COALESCE(finished_at, created_at) < :cutoff \
   ORDER BY COALESCE(finished_at, created_at) \
   LIMIT :lim\
), steps AS (\
  DELETE FROM _flow_run_steps WHERE run_id IN (SELECT id FROM doomed) RETURNING id\
), approvals AS (\
  DELETE FROM _flow_approvals WHERE run_id IN (SELECT id FROM doomed) RETURNING id\
), waits AS (\
  DELETE FROM _flow_run_waits WHERE run_id IN (SELECT id FROM doomed) RETURNING id\
), runs AS (\
  DELETE FROM _flow_runs WHERE id IN (SELECT id FROM doomed) RETURNING id\
) SELECT (SELECT COUNT(*) FROM steps) AS steps, (SELECT COUNT(*) FROM runs) AS runs, \
         (SELECT COUNT(*) FROM approvals) AS approvals, \
         (SELECT COUNT(*) FROM waits) AS waits";

/// The approval receipts past their OWN window (hub#903).
///
/// Three things about this statement are deliberate:
///
/// - **No status filter.** Every other table here has live rows that are exempt at any age; this
///   one has none. A receipt is written once, when the grant is spent, and is terminal from birth
///   — so the only question is its age.
/// - **`hub_id` in the DELETE as well as in the SELECT.** The key of `_elevation_audit` is
///   `(hub_id, id)`, not `id`: two hubs sharing a database can hold the same receipt id, and a
///   DELETE that named only the id would reach across into a neighbour's audit. This is the exact
///   opposite of the rule for `_flow_run_steps`, which is keyed by `run_id` alone on purpose —
///   the difference is that there the parent set is already hub-scoped, and here there is no
///   parent.
/// - **`created_at` is the age.** A receipt has no terminal stamp because it never changes state,
///   so unlike an event its birth IS its terminal moment.
///
/// The index it needs already exists (`idx_elevation_audit_when (hub_id, created_at)`, system
/// migration v26), so this needs no numbered migration.
const PRUNE_RECEIPTS: &str = "\
WITH doomed AS (\
  SELECT id FROM _elevation_audit \
   WHERE hub_id = :hub_id AND created_at < :receipt_cutoff \
   ORDER BY created_at \
   LIMIT :lim\
), gone AS (\
  DELETE FROM _elevation_audit \
   WHERE hub_id = :hub_id AND id IN (SELECT id FROM doomed) RETURNING id\
) SELECT (SELECT COUNT(*) FROM gone) AS receipts";

/// One bounded pass: up to [`BATCH`] terminal events and [`BATCH`] terminal runs older than
/// `cutoff`, each with its children.
///
/// `cutoff` is passed in rather than computed so the caller owns the clock — which is what lets a
/// test age a row ninety days without waiting ninety days.
pub async fn prune_once(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    cutoffs: &Cutoffs,
) -> Result<PruneReport> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("cutoff".into(), json!(cutoffs.history));
    p.insert("receipt_cutoff".into(), json!(cutoffs.receipts));
    p.insert("lim".into(), json!(BATCH));

    let events = db.query(PRUNE_EVENTS, &p).await?;
    let runs = db.query(PRUNE_RUNS, &p).await?;
    let receipts = db.query(PRUNE_RECEIPTS, &p).await?;

    Ok(PruneReport {
        events: cell(&events, "events"),
        delivery_markers: cell(&events, "markers"),
        runs: cell(&runs, "runs"),
        run_steps: cell(&runs, "steps"),
        approvals: cell(&runs, "approvals"),
        waits: cell(&runs, "waits"),
        receipts: cell(&receipts, "receipts"),
    })
}

/// Prune until there is nothing left in the window or [`MAX_PASSES`] is spent.
///
/// The loop is what lets a hub that has never been pruned catch up over a few ticks instead of in
/// one lock-holding statement; the ceiling is what stops that catch-up from owning the tick.
pub async fn prune(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<PruneReport> {
    let cutoffs = Cutoffs::now();
    let mut total = PruneReport::default();
    for _ in 0..MAX_PASSES {
        let pass = prune_once(db, hub_id, &cutoffs).await?;
        if pass.is_empty() {
            break;
        }
        total.merge(pass);
    }
    Ok(total)
}

/// `COUNT(*)` comes back as an integer, but the JSON bridge can widen it to a float.
fn cell(res: &erplora_db::QueryResult, key: &str) -> u64 {
    res.rows
        .first()
        .and_then(|r| {
            r[key]
                .as_i64()
                .or_else(|| r[key].as_f64().map(|f| f as i64))
        })
        .unwrap_or(0)
        .max(0) as u64
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::fresh_db;
    use erplora_db::PgAdapter;

    const HUB: &str = "h1";

    /// The system schema a real boot leaves behind, same helper shape as `outbox`'s tests.
    async fn system_schema(db: &PgAdapter) {
        crate::installer::ensure_hub_module_table(db).await.unwrap();
        crate::identity::ensure_tables(db).await.unwrap();
        crate::outbox::ensure_tables(db).await.unwrap();
        crate::system_migrations::apply(db, HUB).await.unwrap();
        crate::flows::store::ensure_indexes(db).await.unwrap();
    }

    /// `days` ago, RFC3339 — the same format every timestamp column in these tables holds.
    fn days_ago(days: i64) -> String {
        (chrono::Utc::now() - chrono::Duration::days(days)).to_rfc3339()
    }

    /// The cutoff a real prune would use right now.
    fn cutoff() -> Cutoffs {
        Cutoffs::now()
    }

    /// One outbox row in a chosen status, aged by its terminal timestamp.
    async fn event(db: &PgAdapter, hub: &str, id: &str, status: &str, age_days: i64) {
        let at = days_ago(age_days);
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("status".into(), json!(status));
        p.insert("at".into(), json!(at));
        // `delivered_at`/`discarded_at` are the terminal stamps; a pending or dead row has neither,
        // so for those the age lives in `created_at` — exactly as the relay leaves them.
        let (delivered, discarded) = match status {
            "delivered" => (":at", "NULL"),
            "discarded" => ("NULL", ":at"),
            _ => ("NULL", "NULL"),
        };
        db.execute(
            &format!(
                "INSERT INTO _event_outbox \
                 (id, hub_id, user_id, permissions, event_name, payload, status, \
                  next_attempt_at, created_at, delivered_at, discarded_at) \
                 VALUES (:id, :hub_id, 'u1', '[]', 'e', '{{}}', :status, :at, :at, {delivered}, {discarded})"
            ),
            &p,
        )
        .await
        .unwrap();
    }

    /// The idempotency marker the relay writes inside the listener's transaction.
    async fn marker(db: &PgAdapter, hub: &str, event_id: &str) {
        let mut p = Params::new();
        p.insert("event_id".into(), json!(event_id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("at".into(), json!(days_ago(0)));
        db.execute(
            "INSERT INTO _event_delivery (event_id, listener_command, delivered_at, hub_id) \
             VALUES (:event_id, 'm.listener', :at, :hub_id)",
            &p,
        )
        .await
        .unwrap();
    }

    /// One run plus one step, aged by the run's terminal timestamp.
    async fn run_with_step(db: &PgAdapter, hub: &str, id: &str, status: &str, age_days: i64) {
        let at = days_ago(age_days);
        let terminal = matches!(status, "done" | "failed" | "cancelled");
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("status".into(), json!(status));
        p.insert("at".into(), json!(at));
        db.execute(
            &format!(
                "INSERT INTO _flow_runs (id, hub_id, flow_id, status, created_at, updated_at, finished_at) \
                 VALUES (:id, :hub_id, 'f1', :status, :at, :at, {})",
                if terminal { ":at" } else { "NULL" }
            ),
            &p,
        )
        .await
        .unwrap();
        let mut s = Params::new();
        s.insert("id".into(), json!(format!("{id}-s0")));
        s.insert("hub_id".into(), json!(hub));
        s.insert("run_id".into(), json!(id));
        s.insert("at".into(), json!(at));
        db.execute(
            "INSERT INTO _flow_run_steps \
             (id, hub_id, run_id, step_index, step_id, kind, status, created_at) \
             VALUES (:id, :hub_id, :run_id, 0, 's0', 'command', 'done', :at)",
            &s,
        )
        .await
        .unwrap();
    }

    async fn count(db: &PgAdapter, sql: &str) -> i64 {
        let r = db.query(sql, &Params::new()).await.unwrap();
        r.rows[0]["c"]
            .as_i64()
            .or_else(|| r.rows[0]["c"].as_f64().map(|f| f as i64))
            .unwrap_or(-1)
    }

    /// The whole point: a terminal event past the window goes, and its idempotency marker goes
    /// WITH it. Leaving the marker would keep `_event_delivery` growing at the same rate while
    /// pointing at an event that no longer exists.
    #[tokio::test]
    async fn a_terminal_event_past_the_window_goes_and_takes_its_delivery_marker() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, HUB, "old-delivered", "delivered", 120).await;
        marker(&db, HUB, "old-delivered").await;
        event(&db, HUB, "old-discarded", "discarded", 120).await;
        marker(&db, HUB, "old-discarded").await;

        let rep = prune_once(&db, HUB, &cutoff()).await.unwrap();

        assert_eq!(rep.events, 2, "both terminal rows pruned");
        assert_eq!(rep.delivery_markers, 2, "their markers pruned with them");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox").await,
            0
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_delivery").await,
            0,
            "no orphan idempotency marker survives its event"
        );
    }

    /// Durability is not history. A `pending` row is an event that has NOT been delivered — the
    /// only reason it is in the database at all is so a restart cannot lose it. It has no maximum
    /// age, and pruning it would be precisely the data loss the outbox exists to prevent.
    #[tokio::test]
    async fn a_pending_event_survives_at_any_age() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, HUB, "ancient-pending", "pending", 3650).await;

        let rep = prune_once(&db, HUB, &cutoff()).await.unwrap();

        assert_eq!(
            rep.events, 0,
            "a ten-year-old undelivered event is still owed"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='pending'"
            )
            .await,
            1
        );
    }

    /// `dead` is waiting for a HUMAN (retry or discard, hub#660). An operator opening the
    /// dead-letter after three months must still find what died there; expiring it would close
    /// the decision on their behalf and destroy the only evidence of the failure.
    #[tokio::test]
    async fn a_dead_event_survives_at_any_age() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, HUB, "ancient-dead", "dead", 3650).await;

        let rep = prune_once(&db, HUB, &cutoff()).await.unwrap();

        assert_eq!(rep.events, 0, "the dead-letter is not a log");
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE status='dead'"
            )
            .await,
            1
        );
    }

    /// The window is a window, not a switch: inside 90 days nothing is touched.
    #[tokio::test]
    async fn a_terminal_event_inside_the_window_stays() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, HUB, "recent", "delivered", 89).await;
        marker(&db, HUB, "recent").await;

        let rep = prune_once(&db, HUB, &cutoff()).await.unwrap();

        assert!(rep.is_empty(), "89 days old is inside the window: {rep:?}");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox").await,
            1
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_delivery").await,
            1
        );
    }

    /// A finished run goes with its steps; a run still running does not, at any age. The steps are
    /// the wide rows (`input` and `output`, both TEXT) and the ones that can hold templated values,
    /// so a step orphaned from its run is both the bulk of the cost and the worst thing to leave.
    #[tokio::test]
    async fn a_finished_run_goes_with_its_steps_and_live_ones_do_not() {
        let db = fresh_db().await;
        system_schema(&db).await;
        run_with_step(&db, HUB, "done-old", "done", 120).await;
        run_with_step(&db, HUB, "failed-old", "failed", 120).await;
        run_with_step(&db, HUB, "cancelled-old", "cancelled", 120).await;
        // Live work, however old it looks: `waiting_approval` can legitimately sit for a long time.
        run_with_step(&db, HUB, "running-old", "running", 120).await;
        run_with_step(&db, HUB, "sleeping-old", "sleeping", 120).await;
        run_with_step(&db, HUB, "approval-old", "waiting_approval", 120).await;

        let rep = prune_once(&db, HUB, &cutoff()).await.unwrap();

        assert_eq!(rep.runs, 3, "only done/failed/cancelled");
        assert_eq!(rep.run_steps, 3, "each took its step with it");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _flow_runs").await,
            3,
            "running, sleeping and waiting_approval are live work"
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _flow_run_steps").await,
            3,
            "no step outlives its run, and no live run loses its memory"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _flow_run_steps s \
                 WHERE NOT EXISTS (SELECT 1 FROM _flow_runs r WHERE r.id = s.run_id)"
            )
            .await,
            0,
            "not one orphan step"
        );
    }

    /// One approval row, pointing at a run, holding a payload verbatim.
    async fn approval(db: &PgAdapter, hub: &str, id: &str, run_id: &str, status: &str) {
        let at = days_ago(0);
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("run_id".into(), json!(run_id));
        p.insert("status".into(), json!(status));
        p.insert("at".into(), json!(at));
        db.execute(
            "INSERT INTO _flow_approvals \
             (id, hub_id, run_id, flow_id, step_id, command, payload, reason, status, \
              created_at, updated_at) \
             VALUES (:id, :hub_id, :run_id, 'f1', 'agent', 'agenda.booking.create', \
                     '{\"customer\":\"Marta\",\"phone\":\"600000000\"}', '', :status, :at, :at)",
            &p,
        )
        .await
        .unwrap();
    }

    /// hub#972 — the payload of a proposal is stored VERBATIM, and it can carry a customer's name,
    /// phone or address. It is a child of its run exactly as a step is, so it goes when the run
    /// goes: a proposal that outlived the history explaining it would keep personal data for ever
    /// in the one table nothing ever deleted from.
    #[tokio::test]
    async fn a_pruned_run_takes_its_approvals_with_it() {
        let db = fresh_db().await;
        system_schema(&db).await;
        run_with_step(&db, HUB, "old-run", "cancelled", 120).await;
        approval(&db, HUB, "old-approval", "old-run", "expired").await;
        // Live work, and therefore untouchable — with its proposal still waiting for a person.
        run_with_step(&db, HUB, "waiting-run", "waiting_approval", 120).await;
        approval(&db, HUB, "live-approval", "waiting-run", "pending").await;

        let rep = prune_once(&db, HUB, &cutoff()).await.unwrap();

        assert_eq!(rep.runs, 1);
        assert_eq!(rep.approvals, 1, "the terminal run took its proposal");
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _flow_approvals WHERE id='live-approval'"
            )
            .await,
            1,
            "the pending proposal of a live run is still a question somebody has to answer"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _flow_approvals a \
                 WHERE NOT EXISTS (SELECT 1 FROM _flow_runs r WHERE r.id = a.run_id)"
            )
            .await,
            0,
            "not one orphan proposal"
        );
    }

    /// One approval receipt: who asked, who authorised, and the FINGERPRINT of what.
    async fn receipt(db: &PgAdapter, hub: &str, id: &str, age_days: i64) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("hub_id".into(), json!(hub));
        p.insert("at".into(), json!(days_ago(age_days)));
        db.execute(
            "INSERT INTO _elevation_audit \
             (id, hub_id, command, permission, created_by, approved_by, payload_fingerprint, \
              created_at) \
             VALUES (:id, :hub_id, 'till.sale.void', 'till.void_sale', 'u-cashier', \
                     'u-manager', 'deadbeef', :at)",
            &p,
        )
        .await
        .unwrap();
    }

    /// hub#903 — the receipt is not kept for ever. Nothing in the hub had ever deleted a row from
    /// `_elevation_audit`, so a hub open for a decade held every PIN approval a manager had ever
    /// given, by name. Art. 5.1.e demands a limit and WP260 says "as long as necessary" is not one.
    #[tokio::test]
    async fn an_approval_receipt_past_four_years_goes() {
        let db = fresh_db().await;
        system_schema(&db).await;
        receipt(&db, HUB, "ancient", APPROVAL_AUDIT_DAYS + 1).await;

        let rep = prune(&db, HUB).await.unwrap();

        assert_eq!(rep.receipts, 1, "counted, like every other prune: {rep:?}");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _elevation_audit").await,
            0,
            "four years and a day is past the window"
        );
    }

    /// **The two windows are DIFFERENT windows**, and this is the test that says so. A receipt of
    /// 120 days is long past the generic 90 of [`RETENTION_DAYS`] — and it stays, while the event
    /// sitting next to it at exactly the same age goes. Pruning the receipt on the history's clock
    /// would destroy the evidence of a till discrepancy before the tax year it happened in closes.
    #[tokio::test]
    async fn the_receipt_outlives_the_generic_history_window() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, HUB, "old-event", "delivered", 120).await;
        receipt(&db, HUB, "same-age", 120).await;
        // And the last day it is still owed: four years minus one is inside the window.
        receipt(&db, HUB, "nearly-due", APPROVAL_AUDIT_DAYS - 1).await;

        let rep = prune(&db, HUB).await.unwrap();

        assert_eq!(rep.events, 1, "the history goes on the history's clock");
        assert_eq!(rep.receipts, 0, "and the receipt does not: {rep:?}");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _elevation_audit").await,
            2,
            "both receipts are inside four years"
        );
    }

    /// Tenancy, with a neighbour that is REAL and equally ancient — a scoping test with no live
    /// neighbour proves nothing. Note the receipt's key is `(hub_id, id)`, not `id`: two hubs can
    /// hold the same receipt id, so the DELETE has to name the hub or it reaches across.
    #[tokio::test]
    async fn the_prune_only_takes_the_receipts_of_the_hub_it_was_asked_for() {
        let db = fresh_db().await;
        system_schema(&db).await;
        receipt(&db, HUB, "shared-id", APPROVAL_AUDIT_DAYS + 30).await;
        receipt(&db, "neighbour", "shared-id", APPROVAL_AUDIT_DAYS + 30).await;

        let rep = prune(&db, HUB).await.unwrap();

        assert_eq!(rep.receipts, 1);
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _elevation_audit WHERE hub_id='neighbour'"
            )
            .await,
            1,
            "the neighbour's receipt is theirs, same id and all"
        );
    }

    /// Bounded like every other table: a hub that has never pruned must not take the table with it
    /// on the first tick.
    #[tokio::test]
    async fn a_pass_of_receipts_is_bounded_and_the_driver_finishes_it() {
        let db = fresh_db().await;
        system_schema(&db).await;
        let over = BATCH + 3;
        for i in 0..over {
            receipt(&db, HUB, &format!("r{i}"), APPROVAL_AUDIT_DAYS + 10).await;
        }

        let first = prune_once(&db, HUB, &Cutoffs::now()).await.unwrap();
        assert_eq!(first.receipts, BATCH as u64, "one pass, one batch");

        let rest = prune(&db, HUB).await.unwrap();
        assert_eq!(rest.receipts, 3, "the driver finishes and reports it");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _elevation_audit").await,
            0
        );
    }

    /// One database can hold rows for more than one `hub_id` (the row contract, not the deploy),
    /// so a prune that ignored it would delete a neighbour's history. The neighbour here is REAL
    /// and equally old — a test with no live neighbour proves nothing about scoping.
    #[tokio::test]
    async fn the_prune_only_touches_the_hub_it_was_asked_for() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, HUB, "mine", "delivered", 120).await;
        marker(&db, HUB, "mine").await;
        run_with_step(&db, HUB, "mine-run", "done", 120).await;
        event(&db, "neighbour", "theirs", "delivered", 120).await;
        marker(&db, "neighbour", "theirs").await;
        run_with_step(&db, "neighbour", "their-run", "done", 120).await;

        let rep = prune_once(&db, HUB, &cutoff()).await.unwrap();

        assert_eq!(rep.events, 1);
        assert_eq!(rep.runs, 1);
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_outbox WHERE hub_id='neighbour'"
            )
            .await,
            1,
            "the neighbour's event is untouched"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _event_delivery WHERE event_id='theirs'"
            )
            .await,
            1,
            "and so is its marker: the doomed set is the hub's own events, and nothing else"
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _flow_runs WHERE hub_id='neighbour'"
            )
            .await,
            1
        );
        assert_eq!(
            count(
                &db,
                "SELECT COUNT(*) AS c FROM _flow_run_steps WHERE hub_id='neighbour'"
            )
            .await,
            1
        );
    }

    /// A pass is BOUNDED — the reason this can run on a live till without taking the table with
    /// it — and the driver repeats it until the window is clear.
    #[tokio::test]
    async fn a_pass_is_bounded_and_the_driver_repeats_until_clear() {
        let db = fresh_db().await;
        system_schema(&db).await;
        let over = BATCH + 7;
        for i in 0..over {
            event(&db, HUB, &format!("e{i}"), "delivered", 120).await;
        }

        let first = prune_once(&db, HUB, &cutoff()).await.unwrap();
        assert_eq!(
            first.events, BATCH as u64,
            "one pass never exceeds the batch"
        );
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox").await,
            7
        );

        let rest = prune(&db, HUB).await.unwrap();
        assert_eq!(rest.events, 7, "the driver finishes the job and reports it");
        assert_eq!(
            count(&db, "SELECT COUNT(*) AS c FROM _event_outbox").await,
            0
        );
    }

    /// A quiet hub must report nothing, so the caller can stay silent instead of logging
    /// "deleted 0 rows" once an hour forever.
    #[tokio::test]
    async fn a_hub_with_nothing_to_prune_reports_nothing() {
        let db = fresh_db().await;
        system_schema(&db).await;
        event(&db, HUB, "fresh", "delivered", 1).await;

        let rep = prune(&db, HUB).await.unwrap();

        assert!(rep.is_empty(), "nothing due: {rep:?}");
        assert_eq!(rep.total(), 0);
    }
}
