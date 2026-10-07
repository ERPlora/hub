//! **Old device rows** (hub#2215) — the runtime half.
//!
//! Every time a browser loses its storage it comes back as a NEW device, and the row of the old one
//! stays in Settings → Devices forever. Two things were missing:
//!
//!  1. **when a device was really last used.** `devices::list` only looked at sessions that are
//!     still open, so a row whose session had expired said "added on X, never used since" — false,
//!     and useless for telling a dead browser from the counter till;
//!  2. **a way to clear the dead ones at once**, the way Google, Apple or Microsoft list the devices
//!     of an account. What it must never take is a device that is still in use: one somebody signed
//!     in on within the window, one that held a live session within the window (a `personal` tablet
//!     signs in once and works for thirty days), and the device the administrator is holding.
use erplora_db::testutil::{fresh_db, TestDb};
use erplora_db::Params;
use erplora_runtime::Runtime;
use serde_json::json;

fn days_ago(days: i64) -> String {
    (chrono::Utc::now() - chrono::Duration::days(days)).to_rfc3339()
}

async fn hub(hub_id: &str) -> (Runtime, String) {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let admin = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    (rt, admin)
}

/// Rewrite the clock of a device as if it had been trusted and last used `days` ago.
async fn age_device(rt: &Runtime, hub_id: &str, device_id: &str, trusted: i64, seen: i64) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    p.insert("trusted".into(), json!(days_ago(trusted)));
    p.insert("seen".into(), json!(days_ago(seen)));
    rt.db()
        .execute(
            "UPDATE hub_trusted_device SET trusted_at = :trusted, last_seen_at = :seen \
              WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await
        .unwrap();
}

/// Rewrite every session of a device as opened `created` days ago and running out `expires` days
/// ago (negative = still in the future).
async fn age_sessions(rt: &Runtime, hub_id: &str, device_id: &str, created: i64, expires: i64) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    p.insert("created".into(), json!(days_ago(created)));
    p.insert("expires".into(), json!(days_ago(expires)));
    rt.db()
        .execute(
            "UPDATE hub_session SET created_at = :created, expires_at = :expires \
              WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await
        .unwrap();
}

async fn listed(rt: &Runtime, device_id: &str) -> Option<erplora_runtime::devices::TrustedDevice> {
    rt.list_devices()
        .await
        .unwrap()
        .into_iter()
        .find(|d| d.device_id == device_id)
}

async fn session_rows(rt: &Runtime, hub_id: &str, device_id: &str) -> usize {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("device_id".into(), json!(device_id));
    rt.db()
        .query(
            "SELECT token FROM hub_session WHERE hub_id = :hub_id AND device_id = :device_id",
            &p,
        )
        .await
        .unwrap()
        .rows
        .len()
}

#[tokio::test]
async fn a_device_says_when_it_was_last_used_after_its_session_has_expired() {
    let (rt, admin) = hub("hub-2215-a").await;
    rt.trust_device("till-1", "Ana").await.unwrap();
    rt.create_session(&admin, 3600, Some("till-1"))
        .await
        .unwrap();
    // The shift ended: the session opened 3 days ago and ran out the same evening.
    age_sessions(&rt, "hub-2215-a", "till-1", 3, 2).await;

    let till = listed(&rt, "till-1").await.expect("the till is listed");
    assert_eq!(till.open_sessions, 0, "precondition: nobody is signed in");
    assert!(
        !till.last_used_at.is_empty(),
        "an expired session is still a USE: the row must not say «never used»"
    );
    assert!(
        till.last_used_at >= till.trusted_at,
        "last use {} is not before its first trust {}",
        till.last_used_at,
        till.trusted_at
    );
}

#[tokio::test]
async fn signing_in_with_a_pin_counts_as_using_the_device() {
    // A till signs in by PIN every morning and never repeats the online login that trusted it, so
    // "last used" cannot be written only by `trust_device`: it is written where every login ends.
    let (rt, admin) = hub("hub-2215-b").await;
    rt.trust_device("till-1", "Ana").await.unwrap();
    age_device(&rt, "hub-2215-b", "till-1", 90, 90).await;

    rt.create_session(&admin, 3600, Some("till-1"))
        .await
        .unwrap();
    age_sessions(&rt, "hub-2215-b", "till-1", 0, 0).await;

    let till = listed(&rt, "till-1").await.expect("the till is listed");
    assert!(
        till.last_used_at > days_ago(1),
        "the PIN sign-in of today is the last use, got {}",
        till.last_used_at
    );
    assert!(!till.stale, "a till used today is not a candidate for cleaning");
}

#[tokio::test]
async fn cleaning_removes_only_the_devices_nobody_used_in_thirty_days() {
    let hub_id = "hub-2215-c";
    let (rt, admin) = hub(hub_id).await;
    for device in ["dead-browser", "used-last-week", "personal-tablet", "in-my-hands"] {
        rt.trust_device(device, "Ana").await.unwrap();
        rt.create_session(&admin, 3600, Some(device)).await.unwrap();
    }
    // A browser that lost its storage 40 days ago: its last session ran out 39 days ago.
    age_device(&rt, hub_id, "dead-browser", 60, 40).await;
    age_sessions(&rt, hub_id, "dead-browser", 40, 39).await;
    // Signed in 10 days ago.
    age_device(&rt, hub_id, "used-last-week", 60, 10).await;
    age_sessions(&rt, hub_id, "used-last-week", 10, 9).await;
    // `personal`: ONE sign-in 35 days ago, and its thirty-day session only ran out 5 days ago. It
    // was in use inside the window even though nobody typed anything on it.
    age_device(&rt, hub_id, "personal-tablet", 60, 35).await;
    age_sessions(&rt, hub_id, "personal-tablet", 35, 5).await;
    // As old as the dead browser, but it is the device the administrator is cleaning from.
    age_device(&rt, hub_id, "in-my-hands", 60, 40).await;
    age_sessions(&rt, hub_id, "in-my-hands", 40, 39).await;

    // The list says which rows the button would take, with the same rule the button applies.
    let stale: Vec<String> = rt
        .list_devices()
        .await
        .unwrap()
        .into_iter()
        .filter(|d| d.stale)
        .map(|d| d.device_id)
        .collect();
    assert_eq!(
        {
            let mut s = stale.clone();
            s.sort();
            s
        },
        vec!["dead-browser".to_string(), "in-my-hands".to_string()]
    );

    let pruned = rt.prune_stale_devices("in-my-hands").await.unwrap();

    assert_eq!(pruned.removed, 1, "only the dead browser goes");
    assert!(listed(&rt, "dead-browser").await.is_none());
    assert_eq!(
        session_rows(&rt, hub_id, "dead-browser").await,
        0,
        "its old sessions go with it, like a revocation"
    );
    for kept in ["used-last-week", "personal-tablet", "in-my-hands"] {
        assert!(listed(&rt, kept).await.is_some(), "{kept} must stay");
        assert_eq!(session_rows(&rt, hub_id, kept).await, 1, "{kept} keeps its session");
    }
}

#[tokio::test]
async fn cleaning_one_business_never_touches_the_business_next_door() {
    // Same database, same device id, both dead: cleaning mine leaves the neighbour's row and its
    // sessions exactly where they were (`hub_trusted_device` is keyed `(hub_id, device_id)`).
    let test_db = TestDb::new().await;
    let mine = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-2215-mine");
    let theirs = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-2215-theirs");
    mine.ensure_system_tables().await.unwrap();
    theirs.ensure_system_tables().await.unwrap();
    for (rt, hub_id) in [(&mine, "hub-2215-mine"), (&theirs, "hub-2215-theirs")] {
        let admin = rt
            .create_user("Admin", "1111", "admin", None)
            .await
            .unwrap();
        rt.trust_device("dead-browser", "Ana").await.unwrap();
        rt.create_session(&admin, 3600, Some("dead-browser"))
            .await
            .unwrap();
        age_device(rt, hub_id, "dead-browser", 60, 40).await;
        age_sessions(rt, hub_id, "dead-browser", 40, 39).await;
    }

    let pruned = mine.prune_stale_devices("").await.unwrap();

    assert_eq!(pruned.removed, 1);
    assert!(listed(&mine, "dead-browser").await.is_none());
    assert!(
        listed(&theirs, "dead-browser").await.is_some(),
        "the neighbour's row is its own business"
    );
    assert_eq!(session_rows(&theirs, "hub-2215-theirs", "dead-browser").await, 1);
}

#[tokio::test]
async fn a_row_with_no_last_use_on_record_is_judged_by_the_day_it_was_trusted() {
    // `last_seen_at` is `''` when the hub has no record of a use (the contract of the column): an
    // empty mark sorts before any date, so on its own it would read "unused for ages" and take a
    // device trusted this morning. The date the hub DOES know decides instead.
    let hub_id = "hub-2215-e";
    let (rt, _admin) = hub(hub_id).await;
    rt.trust_device("trusted-today", "Ana").await.unwrap();
    rt.trust_device("trusted-long-ago", "Ana").await.unwrap();
    age_device(&rt, hub_id, "trusted-today", 0, 0).await;
    age_device(&rt, hub_id, "trusted-long-ago", 60, 60).await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    rt.db()
        .execute(
            "UPDATE hub_trusted_device SET last_seen_at = '' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();

    assert!(!listed(&rt, "trusted-today").await.unwrap().stale);
    assert!(listed(&rt, "trusted-long-ago").await.unwrap().stale);

    let pruned = rt.prune_stale_devices("").await.unwrap();

    assert_eq!(pruned.removed, 1, "only the one trusted sixty days ago goes");
    assert!(listed(&rt, "trusted-today").await.is_some());
    assert!(listed(&rt, "trusted-long-ago").await.is_none());
}

#[tokio::test]
async fn a_device_somebody_signed_out_of_last_week_stays() {
    // Signing out DELETES the session row (`delete_session`), and so do a user's deactivation and
    // the device-limit sweep: a till used ten days ago and closed with «Sign out» has no session left
    // to vouch for it. Its `last_seen_at` is the only trace of that use, and it has to be enough.
    let hub_id = "hub-2215-f";
    let (rt, admin) = hub(hub_id).await;
    rt.trust_device("signed-out-till", "Ana").await.unwrap();
    let token = rt
        .create_session(&admin, 3600, Some("signed-out-till"))
        .await
        .unwrap();
    rt.delete_session(&token).await.unwrap();
    age_device(&rt, hub_id, "signed-out-till", 60, 10).await;
    assert_eq!(
        session_rows(&rt, hub_id, "signed-out-till").await,
        0,
        "precondition: signing out left no session behind"
    );

    assert!(!listed(&rt, "signed-out-till").await.unwrap().stale);

    let pruned = rt.prune_stale_devices("").await.unwrap();

    assert_eq!(pruned.removed, 0, "a till used ten days ago is not unused");
    assert!(listed(&rt, "signed-out-till").await.is_some());
}

#[tokio::test]
async fn the_business_next_door_using_the_same_tablet_does_not_keep_mine() {
    // One tablet can be trusted by two businesses (hub#489). Its live session in the business next
    // door says nothing about its use HERE: the rule reads this hub's sessions only.
    let test_db = TestDb::new().await;
    let mine = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-2215-g-mine");
    let theirs = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-2215-g-theirs");
    mine.ensure_system_tables().await.unwrap();
    theirs.ensure_system_tables().await.unwrap();
    for rt in [&mine, &theirs] {
        let admin = rt
            .create_user("Admin", "1111", "admin", None)
            .await
            .unwrap();
        rt.trust_device("shared-tablet", "Ana").await.unwrap();
        rt.create_session(&admin, 3600, Some("shared-tablet"))
            .await
            .unwrap();
    }
    age_device(&mine, "hub-2215-g-mine", "shared-tablet", 60, 40).await;
    age_sessions(&mine, "hub-2215-g-mine", "shared-tablet", 40, 39).await;

    assert!(listed(&mine, "shared-tablet").await.unwrap().stale);
    assert_eq!(mine.prune_stale_devices("").await.unwrap().removed, 1);
    assert!(listed(&theirs, "shared-tablet").await.is_some());
}

/// hub#2599: the server ends the live channels (`/ws`, `/api/events`) of the sessions the clean-up
/// deletes, so the runtime says exactly which ones — the dead device's of THIS business, never the
/// session of a device that stays nor the one of the business next door with the same tablet id.
#[tokio::test]
async fn cleaning_names_exactly_the_sessions_it_ended_hub2599() {
    let test_db = TestDb::new().await;
    let mine = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-2599-mine");
    let theirs = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-2599-theirs");
    let mut dead = Vec::new();
    for (rt, hub_id) in [(&mine, "hub-2599-mine"), (&theirs, "hub-2599-theirs")] {
        rt.ensure_system_tables().await.unwrap();
        let admin = rt
            .create_user("Admin", "1111", "admin", None)
            .await
            .unwrap();
        rt.trust_device("dead-browser", "Ana").await.unwrap();
        dead.push(
            rt.create_session(&admin, 3600, Some("dead-browser"))
                .await
                .unwrap(),
        );
        age_device(rt, hub_id, "dead-browser", 60, 40).await;
        age_sessions(rt, hub_id, "dead-browser", 40, 39).await;
    }
    let admin = mine
        .create_user("Owner", "2222", "admin", None)
        .await
        .unwrap();
    mine.trust_device("till-1", "Owner").await.unwrap();
    let at_till = mine
        .create_session(&admin, 3600, Some("till-1"))
        .await
        .unwrap();

    let pruned = mine.prune_stale_devices("").await.unwrap();

    assert_eq!(pruned.removed, 1);
    assert_eq!(pruned.ended_sessions, vec![dead[0].clone()]);
    assert!(!pruned.ended_sessions.contains(&at_till));
    assert_eq!(
        session_rows(&theirs, "hub-2599-theirs", "dead-browser").await,
        1
    );
}
