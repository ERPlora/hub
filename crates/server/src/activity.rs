//! **User-activity** signal, hub → Cloud (free-hub lifecycle, ADR-0175).
//!
//! The Cloud powers off a free hub **nobody enters** for 60 days, flags it inactive at 90 and
//! deletes it at 120 (`free_hub_lifecycle_task`). Only the hub knows who has entered.
//!
//! **Why the existing heartbeat is not enough** (`daily_usage`, hub#199): that one measures
//! *liveness and business* — the container is up, and N sales happened today. A hub that is switched
//! on beats forever whether anybody uses it or not, so no hub would ever expire on that signal; and
//! with `created_at` (what the Cloud did before ADR-0175) they all expire alike. Neither says
//! "nobody comes here". This one does: `last_user_activity_at` travels **only if somebody entered**,
//! inside the same heartbeat — without opening another network path or another job.
//!
//! **Cost**: zero I/O per request. Every request carrying a valid credential does a `fetch_max` on
//! an `AtomicI64` ([`ActivityState::touch`]) from a single router middleware.
//!
//! ## And the mark also SURVIVES the process (hub#670)
//!
//! That atomic used to be the whole story, and it died with the process. While a restart was rare
//! that was a remote risk; with `order: start-first` (ADR-0269) **every update kills a task**, so a
//! visit that happened between the mark and the next heartbeat was lost on a routine deploy — and
//! the Cloud, seeing silence, keeps counting days towards deleting a hub somebody is really using.
//! Deleting is not undoable.
//!
//! So the atomic is now a **cache in front of a row** (`_hub_activity`, system migration v39):
//!
//! - [`restore_from_db`] seeds it at boot with whatever the previous process left.
//! - [`flush`] writes it back, **write-behind**: a background task ([`spawn_persistence`]) every
//!   [`persist_interval_secs`] (60 s by default), plus one last flush when the hub drains on
//!   SIGTERM. The request path still does no I/O at all.
//! - The upsert never moves a stored mark backwards (`GREATEST`), which matters precisely during a
//!   blue/green rollout: for a few seconds **two processes of the same hub** write to the same row,
//!   and the older one must not overwrite what the newer one already knew.
//!
//! The residual window is the flush interval — at most a minute of "somebody entered" lost to a
//! `SIGKILL`, against a clock measured in days. A clean shutdown loses nothing.

use std::sync::atomic::{AtomicI64, Ordering};

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

/// The two instants that make up the signal. Epoch seconds; `0` = "never".
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ActivityMarks {
    /// When somebody was last seen using this hub.
    pub last_activity: i64,
    /// The last mark the Cloud acknowledged. Kept as well, so a hub that restarts does not report
    /// again a timestamp the control plane already stored.
    pub last_reported: i64,
}

/// User-activity mark shared by the server (lives in the `AppState`).
#[derive(Debug, Default)]
pub struct ActivityState {
    last_activity: AtomicI64,
    last_reported: AtomicI64,
    /// What is already in the database. It is the difference against the two above — not a timer —
    /// that decides whether a flush has anything to write.
    persisted_activity: AtomicI64,
    persisted_reported: AtomicI64,
}

impl ActivityState {
    pub fn new() -> Self {
        Self::default()
    }

    /// Records user activity at instant `now`. Monotonic: a request arriving out of order (or a
    /// clock stepping backwards) never moves the mark back.
    pub fn touch(&self, now: i64) {
        self.last_activity.fetch_max(now, Ordering::Relaxed);
    }

    /// Last known instant with activity (`None` if nobody has entered).
    pub fn last_activity(&self) -> Option<i64> {
        match self.last_activity.load(Ordering::Relaxed) {
            0 => None,
            v => Some(v),
        }
    }

    /// Instant to report, or `None` if there is nothing new since the last send.
    ///
    /// This is the whole decision: with no new activity nothing is sent, so a sleeping hub does not
    /// reset the Cloud's clock.
    pub fn pending(&self) -> Option<i64> {
        let last = self.last_activity.load(Ordering::Relaxed);
        if last > 0 && last > self.last_reported.load(Ordering::Relaxed) {
            Some(last)
        } else {
            None
        }
    }

    /// Confirms that `ts` reached the Cloud. Only called after a successful heartbeat: if the send
    /// fails, `pending` keeps returning it and the next tick retries (losing the report would bring
    /// the shutdown forward).
    pub fn mark_reported(&self, ts: i64) {
        self.last_reported.fetch_max(ts, Ordering::Relaxed);
    }

    /// Both marks as they stand right now.
    pub fn marks(&self) -> ActivityMarks {
        ActivityMarks {
            last_activity: self.last_activity.load(Ordering::Relaxed),
            last_reported: self.last_reported.load(Ordering::Relaxed),
        }
    }

    /// Adopts what the database holds (boot). `fetch_max`, not a store: this process may already
    /// have served a request while the row was being read, and that visit is newer than the row.
    pub fn restore(&self, marks: ActivityMarks) {
        self.last_activity
            .fetch_max(marks.last_activity, Ordering::Relaxed);
        self.last_reported
            .fetch_max(marks.last_reported, Ordering::Relaxed);
        self.persisted_activity
            .fetch_max(marks.last_activity, Ordering::Relaxed);
        self.persisted_reported
            .fetch_max(marks.last_reported, Ordering::Relaxed);
    }

    /// What the next flush would have to write, or `None` if the row is already up to date.
    ///
    /// Both marks count: after a heartbeat only `last_reported` moved, and persisting it is what
    /// stops a restart from re-reporting an instant the Cloud already has.
    pub fn pending_persist(&self) -> Option<ActivityMarks> {
        let marks = self.marks();
        let dirty = marks.last_activity > self.persisted_activity.load(Ordering::Relaxed)
            || marks.last_reported > self.persisted_reported.load(Ordering::Relaxed);
        if dirty && marks.last_activity > 0 {
            Some(marks)
        } else {
            None
        }
    }

    /// Confirms that `marks` reached the database. Only called after a successful write: a failed
    /// flush must stay dirty so the next tick retries it.
    pub fn mark_persisted(&self, marks: ActivityMarks) {
        self.persisted_activity
            .fetch_max(marks.last_activity, Ordering::Relaxed);
        self.persisted_reported
            .fetch_max(marks.last_reported, Ordering::Relaxed);
    }
}

/// Does this request count as "somebody is using the hub"?
///
/// Two conditions, both necessary:
/// - **It carries a credential** (`X-Hub-Session` of a logged-in human, or an API key of a live
///   integration). Without one it is an anonymous caller: the login screen, a load-balancer health
///   check or a bot — none of which should keep alive a hub nobody uses.
/// - **It was not rejected** (401/403). An expired session or an invalid token are exactly what you
///   see when NOBODY comes back; counting them would keep the hub on forever.
pub fn is_user_activity(has_credential: bool, status: u16) -> bool {
    has_credential && status != 401 && status != 403
}

// ── Persistence (hub#670) ──────────────────────────────────────────────────────────────────────

/// Default gap between write-behind flushes. Seconds against a clock measured in days: generous
/// enough that the request path never waits on the database, tight enough that a `SIGKILL` cannot
/// take a meaningful visit with it.
pub const DEFAULT_PERSIST_SECS: u64 = 60;

/// How often the activity mark is written back. `HUB_ACTIVITY_PERSIST_SECS` overrides it; `0` or a
/// nonsense value falls back to the default, because "never flush" is the bug this closes.
pub fn persist_interval_secs(env_value: Option<&str>) -> u64 {
    env_value
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(DEFAULT_PERSIST_SECS)
}

/// Epoch seconds → ISO-8601 UTC, the format the Cloud parses (`_coerce_datetime`) and the one the
/// row stores. Fixed width and always `Z`, so lexicographic order **is** chronological order —
/// which is what lets the upsert compare with `GREATEST` and no cast.
pub fn to_iso8601(ts: i64) -> String {
    chrono::DateTime::from_timestamp(ts, 0)
        .unwrap_or_else(|| chrono::DateTime::from_timestamp(0, 0).expect("epoch"))
        .to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

/// The inverse. An unreadable value is `0` ("never"), never a panic: a corrupt row must degrade to
/// "I don't know when", not take the hub's boot down with it.
fn from_iso8601(raw: Option<&str>) -> i64 {
    raw.and_then(|v| chrono::DateTime::parse_from_rfc3339(v).ok())
        .map(|d| d.timestamp())
        .unwrap_or(0)
}

/// Reads the marks persisted for `hub_id`. A hub nobody has ever entered has no row, and that is
/// [`ActivityMarks::default`] — the same "never" the process starts with.
pub async fn load(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<ActivityMarks, String> {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    let result = db
        .query(
            "SELECT last_activity_at, last_reported_at FROM _hub_activity WHERE hub_id = :hub_id",
            &params,
        )
        .await
        .map_err(|error| error.to_string())?;
    let Some(row) = result.rows.first() else {
        return Ok(ActivityMarks::default());
    };
    Ok(ActivityMarks {
        last_activity: from_iso8601(row["last_activity_at"].as_str()),
        last_reported: from_iso8601(row["last_reported_at"].as_str()),
    })
}

/// Writes `marks` for `hub_id`, **never moving a stored mark backwards**.
///
/// The `GREATEST` is not defensive decoration: with `order: start-first` (ADR-0269) the old and the
/// new task of the same hub write to this row at the same time for a few seconds, and the one that
/// is on its way out holds an older snapshot. Without it, the last writer wins and the visit that
/// the new process already recorded disappears.
pub async fn save(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    marks: ActivityMarks,
) -> Result<(), String> {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    params.insert(
        "last_activity_at".into(),
        json!(to_iso8601(marks.last_activity)),
    );
    // NULL, not the epoch: "the Cloud has never confirmed a mark" is a different fact from "it
    // confirmed one in 1970", and it is what keeps the mark pending after a restart.
    params.insert(
        "last_reported_at".into(),
        match marks.last_reported {
            0 => json!(null),
            ts => json!(to_iso8601(ts)),
        },
    );
    params.insert("updated_at".into(), json!(to_iso8601(marks.last_activity)));
    db.execute(
        "INSERT INTO _hub_activity (hub_id, last_activity_at, last_reported_at, updated_at) \
         VALUES (:hub_id, :last_activity_at, :last_reported_at, :updated_at) \
         ON CONFLICT (hub_id) DO UPDATE SET \
           last_activity_at = GREATEST(_hub_activity.last_activity_at, EXCLUDED.last_activity_at), \
           last_reported_at = GREATEST(_hub_activity.last_reported_at, EXCLUDED.last_reported_at), \
           updated_at = GREATEST(_hub_activity.updated_at, EXCLUDED.updated_at)",
        &params,
    )
    .await
    .map_err(|error| error.to_string())?;
    Ok(())
}

/// Boot: adopts the mark the previous process left. Best-effort on purpose — a hub whose activity
/// row cannot be read must still start (degraded, its clock restarted), never fail to boot.
pub async fn restore_from_db(state: &crate::AppState) {
    let hub_id = state.hub_id();
    let marks = {
        let runtime = state.runtime.read().await;
        load(runtime.db(), &hub_id).await
    };
    match marks {
        Ok(marks) => state.activity.restore(marks),
        Err(error) => {
            tracing::warn!(%error, "activity: could not restore the mark; the clock starts over")
        }
    }
}

/// One write-behind flush. Writes nothing when there is nothing new, and only marks the state as
/// persisted **after** the database accepted it — a failed write stays dirty and the next tick
/// retries it.
pub async fn flush(state: &crate::AppState) {
    let Some(marks) = state.activity.pending_persist() else {
        return;
    };
    let hub_id = state.hub_id();
    let written = {
        let runtime = state.runtime.read().await;
        save(runtime.db(), &hub_id, marks).await
    };
    match written {
        Ok(()) => state.activity.mark_persisted(marks),
        Err(error) => tracing::warn!(%error, "activity: could not persist the mark; will retry"),
    }
}

/// Starts the write-behind task. Its own loop and not a piggyback on the 24 h entitlement tick:
/// flushing once a day would leave a whole day of "somebody entered" exposed to the next deploy,
/// which is exactly the window hub#670 closes.
pub fn spawn_persistence(state: &crate::AppState) {
    let state = state.clone();
    let secs = persist_interval_secs(std::env::var("HUB_ACTIVITY_PERSIST_SECS").ok().as_deref());
    tokio::spawn(async move {
        let mut tick = tokio::time::interval(std::time::Duration::from_secs(secs));
        loop {
            tick.tick().await;
            flush(&state).await;
        }
    });
}

#[cfg(test)]
mod tests {
    use erplora_db::testutil::TestDb;

    use super::*;

    #[test]
    fn with_no_activity_there_is_nothing_to_report() {
        let st = ActivityState::new();
        assert_eq!(st.pending(), None);
        assert_eq!(st.last_activity(), None);
    }

    #[test]
    fn a_visit_stays_pending_until_it_is_confirmed() {
        let st = ActivityState::new();
        st.touch(1_000);
        assert_eq!(st.pending(), Some(1_000));
        st.mark_reported(1_000);
        assert_eq!(st.pending(), None, "already reported: not sent again");
    }

    #[test]
    fn new_activity_after_reporting_is_pending_again() {
        let st = ActivityState::new();
        st.touch(1_000);
        st.mark_reported(1_000);
        st.touch(2_000);
        assert_eq!(st.pending(), Some(2_000));
    }

    #[test]
    fn the_mark_does_not_go_back_with_out_of_order_requests() {
        let st = ActivityState::new();
        st.touch(2_000);
        st.touch(1_000);
        assert_eq!(st.pending(), Some(2_000));
    }

    #[test]
    fn a_failed_send_is_retried() {
        // `mark_reported` is only called after an OK heartbeat; without it the next tick retries.
        let st = ActivityState::new();
        st.touch(1_000);
        assert_eq!(st.pending(), Some(1_000));
        assert_eq!(st.pending(), Some(1_000));
    }

    #[test]
    fn only_the_authenticated_and_accepted_request_counts() {
        assert!(is_user_activity(true, 200));
        assert!(is_user_activity(true, 404), "a 404 on a route is real use");
        assert!(
            is_user_activity(true, 500),
            "the hub fails, but somebody is there"
        );
    }

    #[test]
    fn neither_the_anonymous_nor_the_rejected_one_counts() {
        assert!(!is_user_activity(false, 200), "no credential: login/bot/LB");
        assert!(
            !is_user_activity(true, 401),
            "expired session = nobody comes back"
        );
        assert!(!is_user_activity(true, 403));
    }

    #[test]
    fn timestamp_in_iso8601_utc() {
        assert_eq!(to_iso8601(1_700_000_000), "2023-11-14T22:13:20Z");
    }

    #[test]
    fn the_iso8601_round_trip_is_exact() {
        assert_eq!(
            from_iso8601(Some(&to_iso8601(1_700_000_000))),
            1_700_000_000
        );
        assert_eq!(from_iso8601(None), 0, "no row = never");
        assert_eq!(
            from_iso8601(Some("not a date")),
            0,
            "a corrupt row is not a panic"
        );
    }

    #[test]
    fn a_clean_state_has_nothing_to_flush() {
        let st = ActivityState::new();
        assert_eq!(st.pending_persist(), None);
        st.touch(1_000);
        assert_eq!(
            st.pending_persist(),
            Some(ActivityMarks {
                last_activity: 1_000,
                last_reported: 0
            })
        );
        st.mark_persisted(st.marks());
        assert_eq!(st.pending_persist(), None, "the row is up to date");
    }

    /// A confirmation moves nothing the middleware touched, but it still has to reach the row: a
    /// restart that forgot it would re-report a timestamp the Cloud already stored.
    #[test]
    fn confirming_a_report_makes_the_row_dirty_again() {
        let st = ActivityState::new();
        st.touch(1_000);
        st.mark_persisted(st.marks());
        st.mark_reported(1_000);
        assert_eq!(
            st.pending_persist(),
            Some(ActivityMarks {
                last_activity: 1_000,
                last_reported: 1_000
            })
        );
    }

    #[test]
    fn the_flush_interval_falls_back_to_the_default() {
        assert_eq!(persist_interval_secs(Some("30")), 30);
        assert_eq!(persist_interval_secs(None), DEFAULT_PERSIST_SECS);
        assert_eq!(persist_interval_secs(Some("0")), DEFAULT_PERSIST_SECS);
        assert_eq!(persist_interval_secs(Some("later")), DEFAULT_PERSIST_SECS);
    }

    /// A hub with its system schema in place, plus a live handle to it. The `TestDb` must outlive
    /// the handle: it owns the ephemeral schema both adapters point at.
    async fn migrated(hub_id: &str) -> (TestDb, erplora_db::PgAdapter) {
        let db = TestDb::new().await;
        erplora_runtime::Runtime::with_hub_id(Box::new(db.adapter().await), hub_id)
            .ensure_system_tables()
            .await
            .unwrap();
        let handle = db.adapter().await;
        (db, handle)
    }

    #[tokio::test]
    async fn a_hub_nobody_entered_has_no_mark() {
        let (_db, handle) = migrated("hub-a").await;
        assert_eq!(
            load(&handle, "hub-a").await.unwrap(),
            ActivityMarks::default()
        );
    }

    #[tokio::test]
    async fn what_is_saved_is_what_is_loaded_back() {
        let (_db, handle) = migrated("hub-a").await;
        let marks = ActivityMarks {
            last_activity: 1_700_000_000,
            last_reported: 1_699_000_000,
        };
        save(&handle, "hub-a", marks).await.unwrap();
        assert_eq!(load(&handle, "hub-a").await.unwrap(), marks);
    }

    /// 🔒 The blue/green window (ADR-0269): the outgoing task flushes an older snapshot **after**
    /// the incoming one already wrote a newer visit. Last-writer-wins would erase it.
    #[tokio::test]
    async fn a_stale_writer_cannot_move_the_mark_backwards() {
        let (_db, handle) = migrated("hub-a").await;
        let fresh = ActivityMarks {
            last_activity: 2_000_000_000,
            last_reported: 2_000_000_000,
        };
        save(&handle, "hub-a", fresh).await.unwrap();
        save(
            &handle,
            "hub-a",
            ActivityMarks {
                last_activity: 1_000_000_000,
                last_reported: 0,
            },
        )
        .await
        .unwrap();
        assert_eq!(
            load(&handle, "hub-a").await.unwrap(),
            fresh,
            "the dying process must not erase what the new one already knew"
        );
    }

    /// 🔒 The neighbour is real — same database, its mark written through the same door under test.
    /// Reading it as our own would keep an unused free hub alive forever (ADR-0201 row scoping).
    #[tokio::test]
    async fn the_mark_of_the_neighbour_is_not_ours() {
        let (_db, handle) = migrated("hub-a").await;
        save(
            &handle,
            "hub-neighbour",
            ActivityMarks {
                last_activity: 1_700_000_000,
                last_reported: 0,
            },
        )
        .await
        .unwrap();

        assert_eq!(
            load(&handle, "hub-a").await.unwrap(),
            ActivityMarks::default(),
            "nobody entered THIS hub"
        );
        assert_eq!(
            load(&handle, "hub-neighbour").await.unwrap().last_activity,
            1_700_000_000,
            "and the neighbour really does have a mark, or this proves nothing"
        );
    }
}
