//! **Print hosts** — which device drains which printer role (ADR-0196 §6, hub#342).
//!
//! [`crate::print_queue`] (hub#341) made the queue live in the hub, so a job is never lost for want
//! of somebody holding a device. This module is the other half of that sentence: **who is going to
//! take it out**. A print host is a real device — the one with the installable app, sitting on the
//! printer's network — that says *"I print what goes to `kitchen`"*.
//!
//! Not to be confused with `erplora_set_device_role`: that one assigns a role to a **printer**
//! (which box on the network is the kitchen's). This one registers the **device that talks to it**.
//!
//! ## Four questions this registry has to answer
//!
//! **What if two devices register for the same role?** Both are hosts, and that is a feature, not a
//! conflict: a busy restaurant has two tills within reach of the kitchen printer and either one
//! should be able to print. Nothing here is exclusive — the key is `(hub_id, device_id, role)`, so a
//! role holds a *set* of hosts and a device can hold several roles (the counter till prints
//! `receipt` **and** `kitchen`). It is safe because the queue already made it safe: `claim_next`
//! hands out under `FOR UPDATE SKIP LOCKED`, so two hosts of one role take **different** jobs and
//! never the same ticket twice. Making registration exclusive would buy nothing and would cost the
//! business its spare till.
//!
//! **What if nobody is registered and somebody charges?** The sale goes through and the ticket
//! **waits** — `print_queue::enqueue` has no idea whether a host exists and must not: refusing to
//! charge because a printer is unattended would be the queue-in-the-device failure all over again.
//! What was missing is that waiting was *silent*. [`coverage`] is the fix: it reports, per role, how
//! much work is waiting and how many hosts are live, so the hub can tell the owner *"nothing is
//! printing kitchen tickets and three are waiting"* instead of leaving them to discover it at the
//! pass. It is a **warning, never a gate**.
//!
//! **How does a registration expire when the device is switched off?** A device that lost power
//! runs nothing, so it cannot possibly un-register itself. Liveness therefore cannot be a flag
//! somebody writes; it is **derived** from [`HEARTBEAT_SECONDS`] news: a host is live while its
//! `last_seen_at` is within [`HOST_TTL_SECONDS`]. No news means not live — the same fail-closed
//! reading as [`crate::device_mode`]. Deriving it beats sweeping it with a background job for a
//! blunt reason: a sweeper is one more thing that can be down, and a stale flag would claim a dead
//! till is printing. A derived answer is right even when nothing has run.
//!
//! **Does a registration survive a restart of the runtime?** Yes, and it must. *"This till is the
//! kitchen's print host"* is **configuration**, not a session: the hub redeploys on every merge, and
//! a business that had to re-pair its printers a few times a week would stop using the feature. So
//! the row persists. What does **not** survive is the *liveness* — after a restart no host is
//! connected — and it does not need to: the stale "live" answer lasts at most [`HOST_TTL_SECONDS`]
//! and the host earns it back with its next heartbeat. A bounded, self-correcting lie is far cheaper
//! than losing the setup.
//!
//! Going offline and being retired are **different things**: the first is an accident and leaves the
//! row (not live), the second is a decision and is [`unregister`].
//!
//! **What a role IS, since hub#457.** It is not a word any more: [`register`] resolves what the
//! client sent onto a row of `_print_station` ([`crate::print_stations`]) and stores that station's
//! own `key` and `id`. So a device cannot register for `kitchn` — it is told, with the hub's real
//! stations in the message — and it cannot end up hosting `Kitchen` while the queue fills
//! `kitchen`, because both sides now point at the same row instead of at two strings.
//!
//! Persistence: table `_print_host`, **system migration v19** (`station_id`: **v47**).
//! `registered_by` audits who set the
//! device up, like `mode_set_by` in [`crate::device_mode`]: a host that claims tickets and never
//! prints them starves a queue, so that decision leaves a name.
//!
//! Out of scope here on purpose: draining the queue over the WS and authorising a claim against
//! this registry (hub#343), and the screen that renders [`coverage`] for the owner (hub#343/#344).
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;

/// How often a print host is expected to report in. Published to the host when it registers so the
/// client does not hard-code a guess that could drift away from [`HOST_TTL_SECONDS`].
pub const HEARTBEAT_SECONDS: i64 = 30;

/// How long a registration stays **live** with no news from the device.
///
/// Three missed beats, deliberately: one dropped heartbeat is a phone that changed Wi-Fi cell, not a
/// till that was switched off, and flapping "the kitchen is offline" every time the network hiccups
/// would train the owner to ignore the warning that matters.
pub const HOST_TTL_SECONDS: i64 = 90;

/// Longest human name a device may carry. This is a label on a screen ("Counter till"), not a field
/// anybody should be able to push a document into.
pub const MAX_LABEL_CHARS: usize = 120;

/// A device registered to drain a printer role.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrintHost {
    /// The device (`X-Device-Id`, ADR-0154). An identifier, never a credential.
    pub device_id: String,
    /// Which queue it drains, by the **station's** key: `receipt`, `kitchen`, `bar`, `label`, or
    /// whatever this hub added. Always the canonical spelling — [`register`] resolves what the
    /// client sent onto a station and stores the station's own key (hub#457).
    pub role: String,
    /// The station this registration points at. **This** is what `claim_next` filters on, so a
    /// host and a job meet through a row instead of through two strings that happen to match.
    pub station_id: String,
    /// What the owner should see instead of an opaque id ("Counter till").
    pub label: String,
    /// **Derived at read time** from `last_seen_at`, never stored: a switched-off device cannot
    /// write anything, so the absence of news is the only honest signal.
    pub live: bool,
    /// When this device was first set up for this role. A reconnect does **not** move it.
    pub registered_at: String,
    /// `hub_user.id` that set it up — who decided this device prints the kitchen's tickets.
    pub registered_by: String,
    /// Last news from the device. A heartbeat or a re-registration both count as news.
    pub last_seen_at: String,
}

/// Per role: is anything going to come out of a printer, and how much is waiting if not.
///
/// This is the answer to *"I charged and no ticket came out"* — in facts the UI can phrase for the
/// owner, not in a sentence baked into the runtime.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RoleCoverage {
    /// The printer role.
    pub role: String,
    /// Jobs still `pending` for it — waiting for **any** host to take them.
    pub waiting: i64,
    /// Registered hosts that reported within [`HOST_TTL_SECONDS`]. `0` with `waiting > 0` is the
    /// state worth warning about.
    pub live_hosts: i64,
}

/// Stored columns every read of the registry returns, in the order [`row_to_host`] expects.
const HOST_FIELDS: &str =
    "device_id, role, station_id, label, registered_at, registered_by, last_seen_at";

/// SQL that resolves `live` for a row of `_print_host` against the `:cutoff` parameter.
///
/// **One definition, deliberately.** The registry view and the coverage report answer the same
/// question ("is anybody there?") and a hub whose list says a till is live while its coverage says
/// the role is uncovered would be worse than either answer alone. Flags travel as INTEGER 0/1 and
/// never BOOLEAN — the row contract of `erplora_db`.
const LIVE_EXPR: &str = "CASE WHEN last_seen_at >= :cutoff THEN 1 ELSE 0 END";

/// Rejection of a malformed registration, before it reaches the database.
fn invalid(detail: impl Into<String>) -> RuntimeError {
    RuntimeError::InvalidPayload {
        name: "print.host".to_string(),
        detail: detail.into(),
    }
}

/// The instant a host must have reported after to still count as live.
fn live_cutoff() -> String {
    (chrono::Utc::now() - chrono::Duration::seconds(HOST_TTL_SECONDS)).to_rfc3339()
}

/// Registers `device_id` as a host of `role`, or refreshes a registration it already had.
///
/// Idempotent on purpose: an app that reconnects re-registers, and that must be news ("still here"),
/// never a duplicate or an error. What a re-registration does **not** touch is `registered_at` /
/// `registered_by` — the audit of when and by whom this till became the kitchen's printer would be
/// worthless if every reconnect rewrote it. An empty `label` keeps the name the device already had,
/// so a lean client that omits it does not blank the name off the owner's screen.
pub async fn register(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
    role: &str,
    label: &str,
    actor: &str,
) -> Result<PrintHost> {
    let device_id = device_id.trim();
    let label = label.trim();
    if device_id.is_empty() {
        return Err(invalid(
            "device_id is required (which device is going to print this role)",
        ));
    }
    if role.trim().is_empty() {
        return Err(invalid(
            "role is required (which queue this device is going to drain)",
        ));
    }
    // Same door as the queue's (hub#457): the role is **resolved** onto a station of this hub, and
    // what gets stored is the station's key and id. A device that registers for `kitchn` is told
    // so here — with the real stations in the message — instead of sitting forever as the live
    // host of a queue no producer will ever fill.
    let station = crate::print_stations::resolve(db, hub_id, role).await?;
    let role = station.key.as_str();
    let label_chars = label.chars().count();
    if label_chars > MAX_LABEL_CHARS {
        return Err(invalid(format!(
            "the device name is {label_chars} characters, over the {MAX_LABEL_CHARS} character \
             cap for a device label"
        )));
    }

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    p.insert("role".into(), json!(role));
    p.insert("station_id".into(), json!(station.id));
    p.insert("label".into(), json!(label));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("actor".into(), json!(actor));
    p.insert("cutoff".into(), json!(live_cutoff()));
    // `DO UPDATE` and not `DO NOTHING`: a reconnect has to count as news, otherwise a host that
    // re-registers instead of beating would look dead. But it updates ONLY the news and the name —
    // `registered_at`/`registered_by` are the audit of when and by whom this device became this
    // role's host, and a network blip is not a new decision. An empty label keeps the stored one,
    // so a lean client does not wipe the name off the owner's screen.
    let sql = format!(
        "INSERT INTO _print_host \
         (hub_id, device_id, role, station_id, label, registered_at, registered_by, last_seen_at) \
         VALUES (:hub_id, :device_id, :role, :station_id, :label, :now, :actor, :now) \
         ON CONFLICT (hub_id, device_id, role) DO UPDATE \
           SET last_seen_at = EXCLUDED.last_seen_at, \
               station_id = EXCLUDED.station_id, \
               label = CASE WHEN EXCLUDED.label = '' THEN _print_host.label \
                            ELSE EXCLUDED.label END \
         RETURNING {HOST_FIELDS}, {LIVE_EXPR} AS live"
    );
    let res = db.query(&sql, &p).await?;
    res.rows
        .first()
        .map(row_to_host)
        .ok_or_else(|| invalid("the registration was not stored"))
}

/// News from `device_id`: it is still there, for **every** role it hosts.
///
/// Per device and not per role because the news is about the device — one app, one connection, one
/// beat. Returns how many registrations were refreshed; **`0` means "you host nothing here"**, which
/// is what tells a reconnecting app it has to register again (its rows were removed while it was
/// away) instead of beating into the void.
pub async fn heartbeat(db: &dyn DatabaseAdapter, hub_id: &str, device_id: &str) -> Result<usize> {
    let device_id = device_id.trim();
    // A client that names no device hosts nothing, which is exactly what `0` says. It cannot be an
    // error here: this is the answer that tells the caller to register, and it must never be able
    // to refresh a row by matching an empty id.
    if device_id.is_empty() {
        return Ok(0);
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    p.insert("now".into(), json!(now_rfc3339()));
    let res = db
        .execute(
            "UPDATE _print_host SET last_seen_at = :now \
             WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await?;
    Ok(res.affected as usize)
}

/// Retires `device_id` from `role`, or from **all** its roles when `role` is `None`.
///
/// This is the deliberate gesture ("this device no longer prints the kitchen", "that till was
/// stolen"), which is why it deletes the row — unlike going offline, which leaves it there, not
/// live, so the owner can see the till that stopped answering instead of watching it vanish.
///
/// Returns how many registrations were removed.
pub async fn unregister(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    device_id: &str,
    role: Option<&str>,
) -> Result<usize> {
    let device_id = device_id.trim();
    // Same reasoning as the heartbeat, with more at stake: an empty id must never match a row, or
    // "retire this device" would delete somebody else's registration.
    if device_id.is_empty() {
        return Ok(0);
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    let mut sql =
        String::from("DELETE FROM _print_host WHERE hub_id = :hub_id AND device_id = :device_id");
    if let Some(role) = role {
        p.insert("role".into(), json!(role.trim()));
        sql.push_str(" AND role = :role");
    }
    Ok(db.execute(&sql, &p).await?.affected as usize)
}

/// The registry as it stands, ordered by role then device, with `live` resolved.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<PrintHost>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("cutoff".into(), json!(live_cutoff()));
    let sql = format!(
        "SELECT {HOST_FIELDS}, {LIVE_EXPR} AS live FROM _print_host \
         WHERE hub_id = :hub_id ORDER BY role, device_id"
    );
    let res = db.query(&sql, &p).await?;
    Ok(res.rows.iter().map(row_to_host).collect())
}

/// Per role: work waiting and live hosts, for every role that has **either**.
///
/// Both halves matter. A role with waiting work and no live host is the alarm; a role with a live
/// host and nothing waiting is the reassurance ("the kitchen is ready"), and without it the screen
/// could only ever show problems. A role with neither is not a role this business uses.
///
/// Only `pending` counts as waiting: a job a host already claimed is not waiting for one. If that
/// host dies, `print_queue::reclaim_expired` returns the job to `pending` and it shows up here.
pub async fn coverage(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<RoleCoverage>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("cutoff".into(), json!(live_cutoff()));
    p.insert("pending".into(), json!(crate::print_queue::STATUS_PENDING));
    // A `UNION ALL` of the two sides and one `GROUP BY` rather than a join: a role can exist on
    // either side alone — work with nobody to take it (the alarm) and a host with nothing to do
    // (the reassurance) — and any join would drop exactly one of those two.
    let sql = format!(
        "SELECT role, SUM(waiting) AS waiting, SUM(live) AS live_hosts FROM ( \
           SELECT role, 0 AS waiting, {LIVE_EXPR} AS live \
             FROM _print_host WHERE hub_id = :hub_id \
           UNION ALL \
           SELECT role, 1 AS waiting, 0 AS live \
             FROM _print_queue WHERE hub_id = :hub_id AND status = :pending \
         ) t GROUP BY role ORDER BY role"
    );
    let res = db.query(&sql, &p).await?;
    Ok(res
        .rows
        .iter()
        .map(|row| RoleCoverage {
            role: row["role"].as_str().unwrap_or_default().to_string(),
            waiting: row["waiting"].as_i64().unwrap_or(0),
            live_hosts: row["live_hosts"].as_i64().unwrap_or(0),
        })
        .collect())
}

/// Row of [`HOST_COLUMNS`] → [`PrintHost`].
fn row_to_host(row: &serde_json::Value) -> PrintHost {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    PrintHost {
        device_id: s("device_id"),
        role: s("role"),
        station_id: s("station_id"),
        label: s("label"),
        // Row contract: flags travel as INTEGER 0/1, never BOOLEAN (`erplora_db`).
        live: row["live"].as_i64() == Some(1),
        registered_at: s("registered_at"),
        registered_by: s("registered_by"),
        last_seen_at: s("last_seen_at"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::TestDb;
    use erplora_db::PgAdapter;

    /// A hub whose system schema is in place (the print host registry is system migration v19).
    async fn hosts_db() -> PgAdapter {
        let db = TestDb::new().await.adapter().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        db
    }

    /// Back-dates the device's last news, which is the only way to simulate "it was switched off":
    /// a device that is gone writes nothing, so the passage of time IS the signal.
    async fn last_seen_seconds_ago(db: &PgAdapter, device_id: &str, seconds: i64) {
        let at = (chrono::Utc::now() - chrono::Duration::seconds(seconds)).to_rfc3339();
        let mut p = Params::new();
        p.insert("at".into(), json!(at));
        p.insert("device_id".into(), json!(device_id));
        db.execute(
            "UPDATE _print_host SET last_seen_at = :at WHERE device_id = :device_id",
            &p,
        )
        .await
        .unwrap();
    }

    async fn queue(db: &PgAdapter, hub_id: &str, job_id: &str, role: &str) {
        crate::print_queue::enqueue(
            db,
            hub_id,
            &crate::print_queue::NewPrintJob {
                job_id: job_id.into(),
                role: role.into(),
                document_type: "receipt".into(),
                document: serde_json::json!({ "receipt_id": "T-1" }),
                format: crate::print_queue::FORMAT_RECEIPT.into(),
            },
        )
        .await
        .unwrap();
    }

    fn of_role<'a>(cov: &'a [RoleCoverage], role: &str) -> Option<&'a RoleCoverage> {
        cov.iter().find(|c| c.role == role)
    }

    /// The basic gesture: a device says "I print the kitchen's tickets" and the hub knows it.
    #[tokio::test]
    async fn a_device_registers_itself_as_the_host_of_a_role() {
        let db = hosts_db().await;

        let host = register(&db, "h1", "till-1", "kitchen", "Counter till", "u1")
            .await
            .unwrap();
        assert_eq!(host.device_id, "till-1");
        assert_eq!(host.role, "kitchen");
        assert_eq!(
            host.label, "Counter till",
            "the owner sees a name, not an id"
        );
        assert!(host.live, "it just reported in");
        assert_eq!(host.registered_by, "u1", "who set this up is on the record");

        assert_eq!(list(&db, "h1").await.unwrap(), vec![host]);
    }

    /// **Two hosts for one role is legitimate.** Two tills within reach of the kitchen printer are
    /// a spare, not a conflict: the queue hands out under `SKIP LOCKED`, so they take different
    /// jobs. Registration must not be a slot that the second device steals from the first.
    #[tokio::test]
    async fn two_devices_can_host_the_same_role() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();
        register(&db, "h1", "till-2", "kitchen", "Pass", "u1")
            .await
            .unwrap();

        let hosts = list(&db, "h1").await.unwrap();
        assert_eq!(
            hosts
                .iter()
                .map(|h| h.device_id.as_str())
                .collect::<Vec<_>>(),
            ["till-1", "till-2"],
            "the second host joins the first, it does not replace it"
        );
        assert_eq!(
            of_role(&coverage(&db, "h1").await.unwrap(), "kitchen")
                .unwrap()
                .live_hosts,
            2
        );
    }

    /// One device, several roles: the counter till prints the receipt AND the kitchen order.
    #[tokio::test]
    async fn one_device_can_host_several_roles() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "receipt", "Counter", "u1")
            .await
            .unwrap();
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();

        let roles: Vec<String> = list(&db, "h1")
            .await
            .unwrap()
            .into_iter()
            .map(|h| h.role)
            .collect();
        assert_eq!(roles, ["kitchen", "receipt"]);
    }

    /// A reconnecting app re-registers. That is **news**, not a duplicate — and it must not rewrite
    /// who set the device up or when, or the audit would be reset by every network blip.
    #[tokio::test]
    async fn re_registering_refreshes_the_news_without_rewriting_the_audit() {
        let db = hosts_db().await;
        let first = register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();
        last_seen_seconds_ago(&db, "till-1", HOST_TTL_SECONDS + 5).await;
        assert!(!list(&db, "h1").await.unwrap()[0].live, "gone for now");

        let again = register(&db, "h1", "till-1", "kitchen", "Counter", "u2")
            .await
            .unwrap();

        assert_eq!(list(&db, "h1").await.unwrap().len(), 1, "one registration");
        assert!(again.live, "re-registering is news: it is back");
        assert_eq!(
            again.registered_at, first.registered_at,
            "when this till was set up does not move on a reconnect"
        );
        assert_eq!(
            again.registered_by, "u1",
            "who set it up does not move on a reconnect either"
        );
    }

    /// A client that re-registers without repeating the label must not blank the name the owner
    /// gave the device; one that sends a new one renames it.
    #[tokio::test]
    async fn re_registering_without_a_label_keeps_the_name_the_device_already_had() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter till", "u1")
            .await
            .unwrap();

        let kept = register(&db, "h1", "till-1", "kitchen", "", "u1")
            .await
            .unwrap();
        assert_eq!(kept.label, "Counter till");

        let renamed = register(&db, "h1", "till-1", "kitchen", "Pass till", "u1")
            .await
            .unwrap();
        assert_eq!(renamed.label, "Pass till", "a new name does replace it");
    }

    /// **A device that was switched off stops being live, but stays registered.** It cannot
    /// un-register itself — it is off — so silence is the signal, and the row remains so the owner
    /// sees the till that stopped answering instead of watching it disappear.
    #[tokio::test]
    async fn a_host_that_stops_reporting_is_no_longer_live_but_stays_registered() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();

        last_seen_seconds_ago(&db, "till-1", HOST_TTL_SECONDS - 5).await;
        assert!(
            list(&db, "h1").await.unwrap()[0].live,
            "still inside the window: a late beat is not a dead till"
        );

        last_seen_seconds_ago(&db, "till-1", HOST_TTL_SECONDS + 5).await;
        let hosts = list(&db, "h1").await.unwrap();
        assert_eq!(hosts.len(), 1, "the registration is not deleted by silence");
        assert!(
            !hosts[0].live,
            "no news for longer than the TTL is not live"
        );
        assert_eq!(
            of_role(&coverage(&db, "h1").await.unwrap(), "kitchen")
                .unwrap()
                .live_hosts,
            0
        );
    }

    /// The window is pinned from both ends, because both ends are product decisions and neither is
    /// implied by the other:
    ///
    ///  - **at least three missed beats**, or a phone that changed Wi-Fi cell flaps "the kitchen is
    ///    offline" and the owner learns to ignore the warning that matters;
    ///  - **at most two minutes**, or a till that was switched off keeps claiming it prints, and
    ///    the whole point of deriving liveness from silence is lost.
    ///
    /// Written as relations rather than as "90" so the numbers cannot drift apart, and as an
    /// absolute ceiling rather than another multiple of the beat so that raising both together
    /// still has to answer for how long the owner is left in the dark.
    #[test]
    fn the_liveness_window_is_at_least_three_beats_and_at_most_two_minutes() {
        assert!(HEARTBEAT_SECONDS > 0, "a beat has to have a period");
        assert!(
            HOST_TTL_SECONDS >= 3 * HEARTBEAT_SECONDS,
            "a single missed heartbeat must not flap the kitchen offline"
        );
        assert!(
            HOST_TTL_SECONDS <= 120,
            "a till that has been silent for over two minutes must not still count as printing"
        );
    }

    /// The cap is a limit, not an off-by-one: a name of exactly the maximum length is a valid name.
    #[tokio::test]
    async fn a_label_of_exactly_the_cap_is_accepted() {
        let db = hosts_db().await;
        let exact = "x".repeat(MAX_LABEL_CHARS);

        let host = register(&db, "h1", "till-1", "kitchen", &exact, "u1")
            .await
            .unwrap();
        assert_eq!(host.label, exact);
    }

    /// The device comes back and says "still here" — without re-registering, because its setup was
    /// never lost.
    #[tokio::test]
    async fn a_heartbeat_brings_a_silent_host_back() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();
        last_seen_seconds_ago(&db, "till-1", HOST_TTL_SECONDS + 5).await;

        assert_eq!(heartbeat(&db, "h1", "till-1").await.unwrap(), 1);
        assert!(list(&db, "h1").await.unwrap()[0].live);
    }

    /// One app, one connection, one beat: it refreshes **every** role the device hosts.
    #[tokio::test]
    async fn one_heartbeat_refreshes_every_role_of_the_device() {
        let db = hosts_db().await;
        for role in ["receipt", "kitchen", "bar"] {
            register(&db, "h1", "till-1", role, "Counter", "u1")
                .await
                .unwrap();
        }
        register(&db, "h1", "till-2", "label", "Backroom", "u1")
            .await
            .unwrap();
        last_seen_seconds_ago(&db, "till-1", HOST_TTL_SECONDS + 5).await;
        last_seen_seconds_ago(&db, "till-2", HOST_TTL_SECONDS + 5).await;

        assert_eq!(heartbeat(&db, "h1", "till-1").await.unwrap(), 3);

        let hosts = list(&db, "h1").await.unwrap();
        let live: Vec<&str> = hosts
            .iter()
            .filter(|h| h.live)
            .map(|h| h.role.as_str())
            .collect();
        assert_eq!(
            live,
            ["bar", "kitchen", "receipt"],
            "the beat is about the DEVICE: every role it hosts came back at once"
        );
        assert!(
            !hosts.iter().any(|h| h.device_id == "till-2" && h.live),
            "another device's silence is not cured by this one's beat"
        );
    }

    /// A beat from a device that hosts nothing refreshes nothing, and says so: that `0` is what
    /// tells a reconnecting app its rows were removed and it has to register again.
    #[tokio::test]
    async fn a_heartbeat_from_a_device_that_hosts_nothing_refreshes_nothing() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();
        last_seen_seconds_ago(&db, "till-1", HOST_TTL_SECONDS + 5).await;

        assert_eq!(heartbeat(&db, "h1", "phone-9").await.unwrap(), 0);
        // A client that names no device is the same case, and must not be able to refresh a row by
        // matching an empty id — that would keep every host in the hub alive forever.
        assert_eq!(heartbeat(&db, "h1", "").await.unwrap(), 0);
        assert_eq!(heartbeat(&db, "h1", "   ").await.unwrap(), 0);
        assert!(
            !list(&db, "h1").await.unwrap()[0].live,
            "somebody else's beat did not revive this host"
        );
    }

    /// The mirror of the above, with more at stake: an anonymous "retire this device" must delete
    /// nothing at all, rather than everything it happens to match.
    #[tokio::test]
    async fn unregistering_without_naming_a_device_removes_nothing() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();

        assert_eq!(unregister(&db, "h1", "", None).await.unwrap(), 0);
        assert_eq!(
            unregister(&db, "h1", "  ", Some("kitchen")).await.unwrap(),
            0
        );
        assert_eq!(list(&db, "h1").await.unwrap().len(), 1);
    }

    /// **The empty-id guards are the reason a nameless caller cannot reach a row — not luck.**
    ///
    /// [`register`] refuses an empty `device_id`, so in a healthy hub no such row exists and the
    /// guards look redundant: `WHERE device_id = ''` would match nothing anyway. That is precisely
    /// why they are worth pinning, because the column has no `CHECK` and `register` is not the only
    /// thing that can ever put a row there — a restored backup, a hand-run `UPDATE` or a future
    /// import can, which is the same "value this build did not write" case that
    /// [`crate::device_mode::DeviceMode`] fails closed on when it reads storage.
    ///
    /// With such a row present, an anonymous beat must not revive it and an anonymous retire must
    /// not delete it: otherwise "I did not say who I am" becomes a way to act on a real row.
    #[tokio::test]
    async fn a_nameless_caller_cannot_touch_a_row_that_somehow_has_no_device_id() {
        let db = hosts_db().await;
        // Deliberately not reachable through `register`: this is the restored-backup shape.
        db.execute_batch(
            "INSERT INTO _print_host (hub_id, device_id, role, registered_at, last_seen_at) \
             VALUES ('h1', '', 'kitchen', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');",
        )
        .await
        .unwrap();

        assert_eq!(
            heartbeat(&db, "h1", "").await.unwrap(),
            0,
            "a beat from nobody revives nobody"
        );
        assert_eq!(
            unregister(&db, "h1", "  ", None).await.unwrap(),
            0,
            "and deletes nobody"
        );
        assert_eq!(
            list(&db, "h1").await.unwrap().len(),
            1,
            "the odd row is still there, untouched, for a human to look at"
        );
    }

    /// Retiring a device from a role it does not host removes nothing and says so.
    #[tokio::test]
    async fn unregistering_a_role_the_device_does_not_host_removes_nothing() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();

        assert_eq!(
            unregister(&db, "h1", "till-1", Some("bar")).await.unwrap(),
            0
        );
        assert_eq!(unregister(&db, "h1", "phone-9", None).await.unwrap(), 0);
        assert_eq!(list(&db, "h1").await.unwrap().len(), 1);
    }

    /// Retiring a device from one role leaves its other roles alone: "this till no longer prints
    /// the kitchen's" is not "this till prints nothing".
    #[tokio::test]
    async fn unregistering_a_role_leaves_the_other_roles_of_the_device() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "receipt", "Counter", "u1")
            .await
            .unwrap();
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();

        assert_eq!(
            unregister(&db, "h1", "till-1", Some("kitchen"))
                .await
                .unwrap(),
            1
        );

        let roles: Vec<String> = list(&db, "h1")
            .await
            .unwrap()
            .into_iter()
            .map(|h| h.role)
            .collect();
        assert_eq!(roles, ["receipt"]);
    }

    /// Retiring the device itself takes all of its roles — the gesture for a till that was replaced
    /// or stolen.
    #[tokio::test]
    async fn unregistering_a_device_removes_all_of_its_roles() {
        let db = hosts_db().await;
        for role in ["receipt", "kitchen"] {
            register(&db, "h1", "till-1", role, "Counter", "u1")
                .await
                .unwrap();
        }
        register(&db, "h1", "till-2", "kitchen", "Pass", "u1")
            .await
            .unwrap();

        assert_eq!(unregister(&db, "h1", "till-1", None).await.unwrap(), 2);

        let left = list(&db, "h1").await.unwrap();
        assert_eq!(left.len(), 1);
        assert_eq!(left[0].device_id, "till-2", "another device is untouched");
    }

    /// **The registration survives a restart of the runtime.** It is configuration, not a session:
    /// the hub redeploys on every merge and the business must not have to re-pair its printers.
    /// Its *liveness* is another matter — that is re-earned with the next beat.
    #[tokio::test]
    async fn a_registration_survives_a_restart_of_the_runtime() {
        let test_db = TestDb::new().await;

        {
            let db = test_db.adapter().await;
            crate::installer::ensure_hub_module_table(&db)
                .await
                .unwrap();
            crate::identity::ensure_tables(&db).await.unwrap();
            crate::system_migrations::apply(&db, "h1").await.unwrap();
            register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
                .await
                .unwrap();
        }

        // New process over the same data.
        let db = test_db.adapter().await;
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        let hosts = list(&db, "h1").await.unwrap();
        assert_eq!(hosts.len(), 1, "the setup outlived the process");
        assert_eq!(hosts[0].role, "kitchen");
        assert_eq!(hosts[0].label, "Counter");
    }

    /// **Somebody charged and nobody is printing.** The sale is not blocked and the ticket is not
    /// lost — it waits — but the state stops being silent: the hub can now say how much is waiting
    /// and that nothing is going to take it.
    #[tokio::test]
    async fn work_waiting_with_no_live_host_is_visible() {
        let db = hosts_db().await;
        queue(&db, "h1", "j1", "kitchen").await;
        queue(&db, "h1", "j2", "kitchen").await;

        let kitchen = of_role(&coverage(&db, "h1").await.unwrap(), "kitchen")
            .cloned()
            .expect("a role with waiting work is reported even with no host at all");
        assert_eq!(kitchen.waiting, 2);
        assert_eq!(kitchen.live_hosts, 0, "nothing is going to take them");
    }

    /// The same alarm when the role *has* a host but it went quiet — which is the realistic version
    /// of it (somebody configured the till, then it was switched off).
    #[tokio::test]
    async fn work_waiting_for_a_host_that_went_quiet_is_visible() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();
        queue(&db, "h1", "j1", "kitchen").await;
        last_seen_seconds_ago(&db, "till-1", HOST_TTL_SECONDS + 5).await;

        let kitchen = of_role(&coverage(&db, "h1").await.unwrap(), "kitchen")
            .cloned()
            .unwrap();
        assert_eq!(kitchen.waiting, 1);
        assert_eq!(kitchen.live_hosts, 0);
    }

    /// A role that is covered reports itself too — the screen has to be able to say "the kitchen is
    /// ready", not only complain. A role nobody uses is not reported at all.
    #[tokio::test]
    async fn a_covered_role_is_reported_and_an_unused_one_is_not() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();

        let cov = coverage(&db, "h1").await.unwrap();
        let kitchen = of_role(&cov, "kitchen").cloned().unwrap();
        assert_eq!(kitchen.live_hosts, 1);
        assert_eq!(kitchen.waiting, 0, "covered and idle");
        assert!(
            of_role(&cov, "bar").is_none(),
            "a role with neither host nor work is not a role this business uses"
        );
    }

    /// Only `pending` is "waiting for a host". A job somebody already took is being printed, and
    /// counting it would make a working kitchen look stuck.
    #[tokio::test]
    async fn a_job_already_claimed_is_not_counted_as_waiting() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();
        queue(&db, "h1", "j1", "kitchen").await;
        queue(&db, "h1", "j2", "kitchen").await;
        crate::print_queue::claim_next_role(
            &db,
            "h1",
            "kitchen",
            "till-1",
            crate::print_queue::DEFAULT_LEASE_SECONDS,
        )
        .await
        .unwrap()
        .unwrap();

        assert_eq!(
            of_role(&coverage(&db, "h1").await.unwrap(), "kitchen")
                .unwrap()
                .waiting,
            1
        );
    }

    /// The registry is hub-scoped like the rest of the system schema: the same device id in two
    /// hubs is two registrations, and neither hub sees the other's.
    #[tokio::test]
    async fn the_registry_is_scoped_by_hub() {
        let db = hosts_db().await;
        crate::system_migrations::apply(&db, "h2").await.unwrap();

        register(&db, "h1", "till-1", "kitchen", "Counter h1", "u1")
            .await
            .unwrap();
        register(&db, "h2", "till-1", "bar", "Counter h2", "u1")
            .await
            .unwrap();

        let h1 = list(&db, "h1").await.unwrap();
        assert_eq!(h1.len(), 1);
        assert_eq!(h1[0].role, "kitchen");
        assert_eq!(h1[0].label, "Counter h1");

        let h2 = list(&db, "h2").await.unwrap();
        assert_eq!(h2.len(), 1);
        assert_eq!(h2[0].role, "bar");

        // And retiring one hub's device leaves the other hub's alone.
        assert_eq!(unregister(&db, "h1", "till-1", None).await.unwrap(), 1);
        assert_eq!(list(&db, "h2").await.unwrap().len(), 1);
        assert_eq!(
            heartbeat(&db, "h2", "till-1").await.unwrap(),
            1,
            "the other hub's registration still beats"
        );
    }

    /// **A beat in one hub must not revive another hub's device.** The same `device_id` string in
    /// two hubs is two registrations (ADR-0201: each hub owns its database, and the row contract
    /// still carries `hub_id`), so a heartbeat that matched on the id alone would keep a till that
    /// has been off for hours looking alive in a hub it never belonged to.
    ///
    /// The previous test could not see this: it retired h1's row before beating for h2, so an
    /// unscoped `UPDATE` still touched exactly one row. Here both rows exist at once.
    #[tokio::test]
    async fn a_heartbeat_in_one_hub_does_not_revive_the_same_device_in_another() {
        let db = hosts_db().await;
        crate::system_migrations::apply(&db, "h2").await.unwrap();
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();
        register(&db, "h2", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();
        last_seen_seconds_ago(&db, "till-1", HOST_TTL_SECONDS + 5).await;

        assert_eq!(
            heartbeat(&db, "h1", "till-1").await.unwrap(),
            1,
            "only this hub's registration is news"
        );
        assert!(list(&db, "h1").await.unwrap()[0].live);
        assert!(
            !list(&db, "h2").await.unwrap()[0].live,
            "the other hub's till is still off: nobody reported for it"
        );
    }

    /// **Coverage is hub-scoped on BOTH sides.** It joins two tables, so it has two chances to
    /// leak: one hub could otherwise count another's waiting tickets, or borrow its live hosts and
    /// report itself covered while nothing of its own is printing.
    #[tokio::test]
    async fn coverage_never_counts_another_hubs_work_or_hosts() {
        let db = hosts_db().await;
        crate::system_migrations::apply(&db, "h2").await.unwrap();

        // h1: work waiting and nobody to take it. h2: a live host and nothing to do.
        queue(&db, "h1", "j1", "kitchen").await;
        register(&db, "h2", "till-2", "kitchen", "Other hub", "u1")
            .await
            .unwrap();

        let h1 = of_role(&coverage(&db, "h1").await.unwrap(), "kitchen")
            .cloned()
            .unwrap();
        assert_eq!(h1.waiting, 1);
        assert_eq!(
            h1.live_hosts, 0,
            "another hub's till does not cover this hub's queue"
        );

        let h2 = of_role(&coverage(&db, "h2").await.unwrap(), "kitchen")
            .cloned()
            .unwrap();
        assert_eq!(
            h2.waiting, 0,
            "another hub's waiting tickets are not this hub's problem"
        );
        assert_eq!(h2.live_hosts, 1);
    }

    /// A registration without a device or without a role never reaches the table: an empty device
    /// id would register "nobody" as the host of a role and make the coverage report lie.
    #[tokio::test]
    async fn a_registration_without_a_device_or_a_role_is_rejected() {
        let db = hosts_db().await;

        assert!(register(&db, "h1", "", "kitchen", "x", "u1").await.is_err());
        assert!(register(&db, "h1", "  ", "kitchen", "x", "u1")
            .await
            .is_err());
        assert!(register(&db, "h1", "till-1", "", "x", "u1").await.is_err());
        assert!(register(&db, "h1", "till-1", "  ", "x", "u1")
            .await
            .is_err());
        assert!(list(&db, "h1").await.unwrap().is_empty());
    }

    /// The name is bounded: it is a label on a screen, not a place to push a document.
    #[tokio::test]
    async fn a_label_over_the_cap_is_rejected() {
        let db = hosts_db().await;
        let huge = "x".repeat(MAX_LABEL_CHARS + 1);
        assert!(register(&db, "h1", "till-1", "kitchen", &huge, "u1")
            .await
            .is_err());
        assert!(list(&db, "h1").await.unwrap().is_empty());
    }

    /// Ids and roles are stored trimmed, so `"till-1"` and `" till-1 "` are the same device rather
    /// than two rows the owner cannot tell apart.
    #[tokio::test]
    async fn the_device_and_role_are_stored_trimmed() {
        let db = hosts_db().await;
        register(&db, "h1", " till-1 ", " kitchen ", " Counter ", "u1")
            .await
            .unwrap();
        register(&db, "h1", "till-1", "kitchen", "Counter", "u1")
            .await
            .unwrap();

        let hosts = list(&db, "h1").await.unwrap();
        assert_eq!(hosts.len(), 1, "the same device, not two");
        assert_eq!(hosts[0].device_id, "till-1");
        assert_eq!(hosts[0].role, "kitchen");
        assert_eq!(hosts[0].label, "Counter");
    }

    /// The queue and the registry agree on the role spelling: a host registered for `kitchen`
    /// covers the jobs the queue holds for `kitchen`. Trivial-looking, and exactly the seam where a
    /// trimming mismatch would leave tickets waiting forever with a host sitting right there.
    #[tokio::test]
    async fn a_registered_host_covers_the_queue_of_the_same_role() {
        let db = hosts_db().await;
        register(&db, "h1", "till-1", " kitchen ", "Counter", "u1")
            .await
            .unwrap();
        queue(&db, "h1", "j1", "kitchen").await;

        let cov = coverage(&db, "h1").await.unwrap();
        assert_eq!(cov.len(), 1, "one role, not two spellings of it");
        assert_eq!(cov[0].role, "kitchen");
        assert_eq!(cov[0].waiting, 1);
        assert_eq!(cov[0].live_hosts, 1);
    }
}
