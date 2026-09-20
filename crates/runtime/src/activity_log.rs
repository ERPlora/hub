//! **What the people of the business DO here**, hub → Cloud (saas#2129).
//!
//! The Cloud could already tell that a hub was *alive* (`last_heartbeat`), that *somebody entered*
//! ([`crate::super`]'s sibling in `server::activity`, ADR-0175) and that it *sold* today
//! (`daily_usage::collect_daily_usage`). What it could not tell is the shape of the work: a
//! business in its first week — entering, building the catalogue, opening the till, not charging
//! yet — looked exactly like a dead one, because the only business signal was the sale count.
//!
//! This module records the six kinds of work with **who** did them, and hands them to the
//! heartbeat. ERPlora is validated when a customer uses the hub daily and pays; this is the first
//! half of that sentence, and it cannot be reconstructed afterwards — what is not recorded in
//! October is lost.
//!
//! ## Why a table and not an atomic
//!
//! `server::activity` keeps ONE timestamp, so an atomic backed by a row is enough. These are
//! EVENTS: each is a distinct fact and none may be collapsed into the next. And with
//! `order: start-first` (ADR-0269) **every update kills a task**, so anything held only in memory
//! between a sale and the next beat dies on a routine deploy. The buffer is therefore the table
//! itself, `_hub_activity_log`, written at the moment the work happens.
//!
//! ## The delivery contract, which is the whole design
//!
//! - [`record`] inserts. It is **best-effort and never fails the work**: a sale that could not be
//!   logged is still a sale, and taking a till down to record telemetry would be a far worse bug
//!   than the one this closes.
//! - [`pending`] READS a beat's worth. It does not delete — a beat that never arrives must not
//!   take the events with it.
//! - [`confirm`] deletes, and only after a 2xx. The exact shape of
//!   `ActivityState::mark_reported`: delivery is at-least-once, and the Cloud deduplicates on the
//!   `id` this module mints, so a re-send after a lost response costs nothing.
//! - [`trim`] caps the buffer. A hub that cannot reach the Cloud for months must not fill its own
//!   disk with telemetry; the oldest go first, because the recent days are the ones being asked
//!   about.
//!
//! ## What never travels
//!
//! The actor is `RequestContext::user_id` — the hub's own id for that person. No name, no email,
//! and **nothing whatsoever about the end customer**: not who bought, not what, not how much. The
//! row has no column for it, so it cannot leak by somebody adding a field later.

use crate::errors::Result;
use crate::registry::RequestContext;
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

/// One beat's worth. A hub catching up drains over several beats instead of in one request big
/// enough to time out on the Cloud's side.
pub const MAX_EVENTS_PER_BEAT: usize = 500;

/// The ceiling of the buffer. ~5000 events is a busy week for one till; past that the hub has been
/// unable to report for long enough that the oldest events are no longer the interesting ones.
pub const MAX_BUFFERED_EVENTS: usize = 5_000;

/// The six kinds of work the Cloud stores. Closed on purpose and mirrored exactly by
/// `HubUserActivity.ACTIVITY_TYPES` on the Cloud, which drops anything it does not know: a kind
/// added on one side only is silently discarded rather than stored under a name nothing queries.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Login,
    Logout,
    Sale,
    Refund,
    CashOpen,
    CashClose,
}

impl Kind {
    pub fn as_str(self) -> &'static str {
        match self {
            Kind::Login => "login",
            Kind::Logout => "logout",
            Kind::Sale => "sale",
            Kind::Refund => "refund",
            Kind::CashOpen => "cash_open",
            Kind::CashClose => "cash_close",
        }
    }
}

/// Which module COMMAND counts as which kind of work.
///
/// Exact names, and only the **public doors**. The internal relays those commands fan out to
/// (`sales._insert_sale`, `cash_register._open_session_insert`, …) run inside the very same
/// operation, so matching by prefix would count one sale three or four times — and the count is
/// the answer this feature exists to give.
pub fn kind_for_command(name: &str) -> Option<Kind> {
    match name {
        "sales.complete_sale" => Some(Kind::Sale),
        "sales.refund" => Some(Kind::Refund),
        "cash_register.session.open" => Some(Kind::CashOpen),
        "cash_register.session.close" => Some(Kind::CashClose),
        _ => None,
    }
}

/// An event waiting to be reported, in the shape the heartbeat puts on the wire.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PendingEvent {
    pub id: String,
    pub kind: String,
    pub occurred_at: String,
    pub actor: String,
}

/// Records one event. Errors are the caller's to swallow — see [`record_best_effort`].
///
/// The `id` is minted HERE, by the hub, and it is what makes at-least-once delivery safe: the
/// Cloud stores it as the dedup key, so a batch re-sent after a lost response inserts nothing.
pub async fn record(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: Kind,
    actor: &str,
    occurred_at: &str,
) -> Result<()> {
    let mut params = Params::new();
    params.insert("id".into(), json!(uuid::Uuid::new_v4().to_string()));
    params.insert("hub_id".into(), json!(hub_id));
    params.insert("activity_type".into(), json!(kind.as_str()));
    params.insert("actor".into(), json!(actor));
    params.insert("occurred_at".into(), json!(occurred_at));
    db.execute(
        "INSERT INTO _hub_activity_log (id, hub_id, activity_type, actor, occurred_at) \
         VALUES (:id, :hub_id, :activity_type, :actor, :occurred_at)",
        &params,
    )
    .await?;
    Ok(())
}

/// Records one event and never lets the failure reach the work that produced it.
///
/// A sale whose telemetry could not be written is still a sale. Nothing above this line may learn
/// that the log exists — taking a till down to record how busy it is would be a far worse bug
/// than the one this closes.
pub async fn record_best_effort(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: Kind,
    ctx: &RequestContext,
) {
    record_best_effort_for(db, hub_id, kind, &ctx.user_id).await;
}

/// [`record_best_effort`] where the actor is already in hand rather than inside a context.
///
/// The auth doors have no `RequestContext` — a login is what creates the identity a context is
/// built from — so they pass the user id straight in.
pub async fn record_best_effort_for(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: Kind,
    actor: &str,
) {
    // Nobody behind it means nothing to attribute, and an empty actor would be counted as a
    // distinct person by the Cloud's rollup. The scheduler and the outbox run commands with no
    // person attached; their work is not somebody using the hub.
    if actor.is_empty() {
        return;
    }
    if let Err(error) = record(db, hub_id, kind, actor, &now_iso8601()).await {
        // `eprintln!` and not `tracing`: this crate has no logging facility of its own, same
        // reasoning as `capabilities::enforce`. Visible, and it never reaches the caller.
        eprintln!(
            "[activity-log] hub={hub_id} kind={} not recorded (the work itself is unaffected): {error}",
            kind.as_str()
        );
    }
}

/// The next beat's worth, oldest first. Reads only — a beat that fails must keep them.
pub async fn pending(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    limit: usize,
) -> Result<Vec<PendingEvent>> {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    // Acotado en los dos extremos: un `0` devolvería un latido que nunca entrega nada, y pedir
    // más del tope haría una petición lo bastante grande como para expirar en el Cloud.
    params.insert(
        "limit".into(),
        json!(limit.clamp(1, MAX_EVENTS_PER_BEAT) as i64),
    );
    // `id` breaks the tie so the order is TOTAL: two events in the same second must not swap
    // places between the read that reports them and the delete that confirms them.
    let result = db
        .query(
            "SELECT id, activity_type, actor, occurred_at FROM _hub_activity_log \
             WHERE hub_id = :hub_id ORDER BY occurred_at ASC, id ASC LIMIT :limit",
            &params,
        )
        .await?;
    Ok(result
        .rows
        .into_iter()
        .map(|row| PendingEvent {
            id: row["id"].as_str().unwrap_or_default().to_string(),
            kind: row["activity_type"]
                .as_str()
                .unwrap_or_default()
                .to_string(),
            occurred_at: row["occurred_at"].as_str().unwrap_or_default().to_string(),
            actor: row["actor"].as_str().unwrap_or_default().to_string(),
        })
        .collect())
}

/// Deletes the events the Cloud has acknowledged. Only ever called after a 2xx.
///
/// Scoped by `hub_id` as well as by id: on a legacy shared database an id is not proof of
/// ownership, and confirming somebody else's events would delete work that was never reported.
pub async fn confirm(db: &dyn DatabaseAdapter, hub_id: &str, ids: &[String]) -> Result<u64> {
    if ids.is_empty() {
        return Ok(0);
    }
    let ops: Vec<(String, Params)> = ids
        .iter()
        .map(|id| {
            let mut params = Params::new();
            params.insert("id".into(), json!(id));
            params.insert("hub_id".into(), json!(hub_id));
            (
                "DELETE FROM _hub_activity_log WHERE hub_id = :hub_id AND id = :id".to_string(),
                params,
            )
        })
        .collect();
    // All or nothing: a half-confirmed batch would re-report the tail on the next beat, which the
    // Cloud would dedup anyway — but it would also leave this table growing behind a bug nobody
    // sees. One transaction keeps "what the Cloud has" and "what we still hold" exact opposites.
    Ok(db.execute_tx(&ops).await?.affected)
}

/// Caps the buffer at `keep`, dropping the OLDEST first. Returns how many were dropped.
///
/// The old end, not the new one: a hub that has been unable to report for months is asked about
/// its recent days, and the events nobody can deliver are worth less than the disk they sit on.
/// Dropping is logged — a silent data loss here is indistinguishable from a hub nobody uses.
pub async fn trim(db: &dyn DatabaseAdapter, hub_id: &str, keep: usize) -> Result<u64> {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    params.insert("keep".into(), json!(keep as i64));
    let dropped = db
        .execute(
            "DELETE FROM _hub_activity_log WHERE hub_id = :hub_id AND id IN (\
               SELECT id FROM _hub_activity_log WHERE hub_id = :hub_id \
               ORDER BY occurred_at DESC, id DESC OFFSET :keep)",
            &params,
        )
        .await?
        .affected;
    if dropped > 0 {
        eprintln!(
            "[activity-log] hub={hub_id} buffer full: {dropped} oldest events discarded without \
             reaching the Cloud (cap {keep})"
        );
    }
    Ok(dropped)
}

/// RFC3339 UTC with MILLISECOND precision — fixed width and always `Z`, like the rest of the
/// system schema, so a string comparison orders the rows chronologically without a cast.
///
/// **Milliseconds and not seconds, which is what the sibling signals store.** Those keep one
/// timestamp; these are a SEQUENCE, and at second precision a login and the logout that follows
/// it land on the same value — leaving the tie to be broken by a random uuid, which reported
/// people leaving before they arrived. A tie is still possible in principle; it is no longer the
/// normal case for two events of the same gesture.
pub fn now_iso8601() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_six_kinds_are_spelled_exactly_as_the_cloud_stores_them() {
        // The Cloud DROPS a type it does not know (saas#2129), so a typo here does not fail
        // anywhere: it silently stops recording that kind of work. Hence the literal list.
        assert_eq!(
            [
                Kind::Login.as_str(),
                Kind::Logout.as_str(),
                Kind::Sale.as_str(),
                Kind::Refund.as_str(),
                Kind::CashOpen.as_str(),
                Kind::CashClose.as_str(),
            ],
            [
                "login",
                "logout",
                "sale",
                "refund",
                "cash_open",
                "cash_close"
            ]
        );
    }

    #[test]
    fn the_public_doors_of_selling_and_the_till_are_the_ones_that_count() {
        assert_eq!(kind_for_command("sales.complete_sale"), Some(Kind::Sale));
        assert_eq!(kind_for_command("sales.refund"), Some(Kind::Refund));
        assert_eq!(
            kind_for_command("cash_register.session.open"),
            Some(Kind::CashOpen)
        );
        assert_eq!(
            kind_for_command("cash_register.session.close"),
            Some(Kind::CashClose)
        );
    }

    /// The trap this mapping exists to avoid. One `sales.complete_sale` fans out into several
    /// internal relays inside the SAME operation; counting those too would report a busy day that
    /// never happened, and the count is the whole answer.
    #[test]
    fn the_internal_relays_of_one_sale_are_not_four_sales() {
        for internal in [
            "sales._insert_sale",
            "sales._insert_line",
            "sales._insert_payment",
            "sales._bump_counter",
            "cash_register._open_session_insert",
            "cash_register._close_session_apply",
            "cash_register.record_sale",
            "cash_register._record_refund",
        ] {
            assert_eq!(kind_for_command(internal), None, "{internal} is not a sale");
        }
    }

    #[test]
    fn everything_else_a_hub_does_all_day_is_not_business_activity() {
        for other in [
            "inventory.product.create",
            "customers.customer.create",
            "sales.order.add_line",
            "sales.void",
            "",
        ] {
            assert_eq!(kind_for_command(other), None, "{other}");
        }
    }

    #[test]
    fn the_instant_is_fixed_width_utc_so_the_rows_sort_as_text() {
        let now = now_iso8601();
        assert_eq!(now.len(), 24, "millisecond precision, fixed width: {now}");
        assert!(now.ends_with('Z'), "{now}");
        assert!(chrono::DateTime::parse_from_rfc3339(&now).is_ok(), "{now}");
    }

    /// The reason the precision is milliseconds and not seconds. Two events of the same gesture —
    /// signing in and straight back out — used to share a timestamp, and the total order fell
    /// back to a random uuid: the Cloud was told somebody left before they arrived.
    #[test]
    fn two_instants_in_the_same_second_still_sort_in_the_order_they_happened() {
        let first = now_iso8601();
        std::thread::sleep(std::time::Duration::from_millis(2));
        let second = now_iso8601();
        assert!(first < second, "{first} should sort before {second}");
        assert_eq!(first[..17], second[..17], "and inside the same second");
    }
}
