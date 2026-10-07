//! **Revoking a lost device** (hub#455) — the runtime half.
//!
//! `untrust_device` has existed since hub#15 and nothing in the product could call it. With
//! hub#358 in production that gap has a price tag: a tablet marked `personal` carries a session
//! that lasts **thirty days** and asks for no PIN, so "somebody walked off with the tablet" ended
//! at the database prompt.
//!
//! The gesture this file specifies is therefore not "delete a row". It is: **cut this device off
//! now**, which is two writes that must happen together —
//!
//!  1. the trust row goes (with it the `personal` mode it carried, hub#357, and the right to sign
//!     in with a PIN, §2.9), and
//!  2. **its open sessions die**, which is the half that matters today. Without it the thief keeps
//!     working for up to a month with a token that was minted before the revocation.
//!
//! Everything else here is about the blast radius, because the SQL that does this is a `DELETE`
//! keyed on a string the client chose:
//!
//!  - the OTHER till of the same business keeps its row, its mode and its open session;
//!  - a session that names **no** device (opened before hub#200 added the column, or by a client
//!    that identifies none) is not swept along — `WHERE device_id = :id` must not become "and
//!    everything I am unsure about";
//!  - another **hub** that happens to know a device by the same id is not touched at all. Its rows
//!    are alive and populated **while** the revocation runs, and the test asserts they came out
//!    unchanged: a neighbour removed before the action passes with unscoped SQL too.
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

/// A hub with a till and a laptop, both trusted as an online login would have left them, both with
/// somebody signed in. `till-1` is `shared`, `laptop-1` is `personal` — the lax mode, the one whose
/// revocation is the point of the issue.
async fn hub(hub_id: &str) -> (Runtime, String, String) {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let admin = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    rt.trust_device("till-1", "Counter till").await.unwrap();
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    rt.set_device_mode(
        "laptop-1",
        erplora_runtime::device_mode::DeviceMode::Personal,
        &admin,
    )
    .await
    .unwrap();
    let at_till = rt
        .create_session(&admin, 3600, Some("till-1"))
        .await
        .unwrap();
    let at_laptop = rt
        .create_session(&admin, 3600, Some("laptop-1"))
        .await
        .unwrap();
    (rt, at_till, at_laptop)
}

/// Does this token still open the hub?
async fn session_is_alive(rt: &Runtime, token: &str) -> bool {
    rt.resolve_session(token).await.unwrap().is_some()
}

#[tokio::test]
async fn revoking_a_device_kills_the_session_it_had_open() {
    let (rt, _at_till, at_laptop) = hub("hub-455").await;
    assert!(
        session_is_alive(&rt, &at_laptop).await,
        "precondition: the stolen laptop is signed in — that is what makes this worth doing"
    );

    let revocation = rt.revoke_device("laptop-1").await.unwrap();

    // NOW, not at the next refresh: `resolve_session` reads the row on every request, so deleting
    // it is the whole of the cut-off. This is the assertion the screen's wording answers to.
    assert!(
        !session_is_alive(&rt, &at_laptop).await,
        "the token minted before the revocation must stop opening the hub"
    );
    assert!(revocation.was_known, "the hub did know this device");
    assert_eq!(revocation.sessions_closed, 1);
}

/// hub#1801 — **what the owner is told they cut off has to be true.**
///
/// The single-device plan stopped evicting by DELETE: the row survives, expired and marked, so the
/// person left outside can be told why. `sessions_closed` counts what this gesture actually closed,
/// so that tombstone must not be counted — a screen that says "1 session closed" about a device
/// that had been signed out an hour ago is telling the owner somebody was working on the stolen
/// laptop when nobody was.
#[tokio::test]
async fn revoking_a_device_does_not_count_an_already_evicted_session() {
    let (rt, _at_till, at_laptop) = hub("hub-1801").await;
    // The till signs in and the plan of ONE device evicts the laptop.
    rt.enforce_device_limit(1, Some("till-1")).await.unwrap();
    assert!(
        !session_is_alive(&rt, &at_laptop).await,
        "precondition: the laptop was evicted by the takeover"
    );

    let revocation = rt.revoke_device("laptop-1").await.unwrap();

    assert!(revocation.was_known, "the hub did know this device");
    assert_eq!(
        revocation.sessions_closed, 0,
        "nothing was open to close: the takeover had already signed that laptop out"
    );
}

#[tokio::test]
async fn revoking_a_device_takes_its_lax_mode_and_its_pin_login_with_it() {
    let (rt, _at_till, _at_laptop) = hub("hub-455").await;
    assert!(rt.is_device_trusted("laptop-1").await.unwrap());

    rt.revoke_device("laptop-1").await.unwrap();

    assert!(
        !rt.is_device_trusted("laptop-1").await.unwrap(),
        "a revoked device cannot be used to sign in with a PIN again (§2.9)"
    );
    assert_eq!(
        rt.device_mode("laptop-1").await.unwrap(),
        erplora_runtime::device_mode::DeviceMode::Shared,
        "the `personal` mode lived in the row that just went: no cascade to remember (hub#357)"
    );
}

#[tokio::test]
async fn the_other_till_of_the_same_business_keeps_everything() {
    let (rt, at_till, at_laptop) = hub("hub-455").await;

    rt.revoke_device("laptop-1").await.unwrap();

    // The neighbour is ALIVE and populated during the action, and this is what says the `DELETE`
    // was keyed on one device: a test that removed it first would pass with `DELETE FROM
    // hub_session` with no `WHERE` at all.
    assert!(
        session_is_alive(&rt, &at_till).await,
        "the person at the counter must not be signed out because a laptop was lost"
    );
    assert!(rt.is_device_trusted("till-1").await.unwrap());
    assert!(!session_is_alive(&rt, &at_laptop).await);

    let devices = rt.list_devices().await.unwrap();
    let ids: Vec<&str> = devices.iter().map(|d| d.device_id.as_str()).collect();
    assert_eq!(ids, vec!["till-1"], "only the revoked one is gone");
    assert_eq!(devices[0].label, "Counter till");
    assert_eq!(devices[0].open_sessions, 1);
}

#[tokio::test]
async fn a_session_that_names_no_device_is_not_swept_along() {
    let (rt, _at_till, _at_laptop) = hub("hub-455").await;
    let admin = rt
        .create_user("Owner", "2222", "admin", None)
        .await
        .unwrap();
    // No `device_id`: a client that identifies none, or a session opened before hub#200 added the
    // column. In SQL `NULL != 'laptop-1'` is NULL, so a "delete everything that is not this one"
    // would miss it — and a "delete everything" would take it. Neither is what revoking one device
    // means.
    let anonymous = rt.create_session(&admin, 3600, None).await.unwrap();

    rt.revoke_device("laptop-1").await.unwrap();

    assert!(
        session_is_alive(&rt, &anonymous).await,
        "revoking one device closes THAT device's sessions, not the ones it cannot place"
    );
}

#[tokio::test]
async fn another_hub_that_knows_a_device_by_the_same_id_is_untouched() {
    let (mine, _at_till, _at_laptop) = hub("hub-455").await;
    // The id is a string the client chose, so two businesses colliding on one is not exotic — and
    // per ADR-0201 each hub owns its database, which is the isolation this asserts is real.
    let (neighbour, neighbour_till, neighbour_laptop) = hub("hub-other").await;

    mine.revoke_device("laptop-1").await.unwrap();

    // Alive and with data DURING the action, and asserted unchanged afterwards.
    assert!(session_is_alive(&neighbour, &neighbour_laptop).await);
    assert!(session_is_alive(&neighbour, &neighbour_till).await);
    assert!(neighbour.is_device_trusted("laptop-1").await.unwrap());
    assert_eq!(
        neighbour.device_mode("laptop-1").await.unwrap(),
        erplora_runtime::device_mode::DeviceMode::Personal,
        "the neighbour's mode is exactly as it was"
    );
    let there = neighbour.list_devices().await.unwrap();
    assert_eq!(
        there.len(),
        2,
        "the neighbour still knows both of its devices"
    );
}

#[tokio::test]
async fn revoking_twice_is_the_same_as_revoking_once() {
    let (rt, _at_till, _at_laptop) = hub("hub-455").await;

    let first = rt.revoke_device("laptop-1").await.unwrap();
    let second = rt.revoke_device("laptop-1").await.unwrap();

    assert!(first.was_known);
    assert_eq!(first.sessions_closed, 1);
    // Idempotent on purpose, and it does not become an error: "cut this device off" has to succeed
    // when it is already off — two administrators reacting to the same lost tablet is the normal
    // case, and the second one must not be told something went wrong.
    assert!(!second.was_known);
    assert_eq!(second.sessions_closed, 0);
}

#[tokio::test]
async fn a_device_this_hub_never_trusted_still_gets_its_sessions_closed() {
    let (rt, _at_till, _at_laptop) = hub("hub-455").await;
    let admin = rt
        .create_user("Owner", "2222", "admin", None)
        .await
        .unwrap();
    // A session whose device carries no trust row (the trust expired, a boot sweep removed it,
    // hub#454). Cutting the device off must still reach the session: the row is the reason the
    // device is *listed*, never the reason it is *connected*.
    let orphan = rt
        .create_session(&admin, 3600, Some("ghost-1"))
        .await
        .unwrap();

    let revocation = rt.revoke_device("ghost-1").await.unwrap();

    assert!(!revocation.was_known);
    assert_eq!(revocation.sessions_closed, 1);
    assert!(!session_is_alive(&rt, &orphan).await);
}

#[tokio::test]
async fn a_blank_device_id_is_refused_instead_of_deleting_something() {
    let (rt, at_till, at_laptop) = hub("hub-455").await;

    for blank in ["", "   "] {
        let refused = rt.revoke_device(blank).await;
        assert!(
            refused.is_err(),
            "a request that names no device is malformed, not an instruction"
        );
    }
    assert!(session_is_alive(&rt, &at_till).await);
    assert!(session_is_alive(&rt, &at_laptop).await);
    assert_eq!(rt.list_devices().await.unwrap().len(), 2);
}

#[tokio::test]
async fn the_list_carries_what_lets_a_person_recognise_the_device_they_lost() {
    let (rt, _at_till, _at_laptop) = hub("hub-455").await;

    let devices = rt.list_devices().await.unwrap();

    let laptop = devices
        .iter()
        .find(|d| d.device_id == "laptop-1")
        .expect("the laptop is listed");
    // An opaque id decides nothing. What lets an owner point at the lost one: the name it signed in
    // under, when the hub first met it, what kind of device an administrator said it was, and
    // whether somebody is signed in on it **right now**.
    assert_eq!(laptop.label, "Office laptop");
    assert!(!laptop.trusted_at.is_empty());
    assert_eq!(laptop.mode, "personal");
    assert_eq!(laptop.open_sessions, 1);
    assert!(
        !laptop.last_sign_in.is_empty(),
        "when somebody last signed in on it"
    );
    assert!(
        !laptop.signed_in_until.is_empty(),
        "how long that session still has"
    );
}

#[tokio::test]
async fn the_device_used_most_recently_is_at_the_top() {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-455");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    for id in ["till-1", "till-2", "till-3"] {
        rt.trust_device(id, id).await.unwrap();
    }
    // `till-2` is the one somebody is on; `till-3` signed in earlier today; `till-1` not at all.
    rt.create_session(&admin, 3600, Some("till-3"))
        .await
        .unwrap();
    tokio::time::sleep(std::time::Duration::from_millis(5)).await;
    rt.create_session(&admin, 3600, Some("till-2"))
        .await
        .unwrap();

    let devices = rt.list_devices().await.unwrap();

    // Order is part of the answer: an owner scanning for the device they lost five minutes ago
    // should not have to read the whole list. Never-used devices sink, not disappear.
    let ids: Vec<&str> = devices.iter().map(|d| d.device_id.as_str()).collect();
    assert_eq!(ids, vec!["till-2", "till-3", "till-1"]);
}

#[tokio::test]
async fn an_expired_session_is_not_somebody_signed_in() {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), "hub-455");
    rt.ensure_system_tables().await.unwrap();
    let admin = rt
        .create_user("Admin", "1111", "admin", None)
        .await
        .unwrap();
    rt.trust_device("till-1", "Counter till").await.unwrap();
    // Already over when it was written. Counting it would tell the owner a till is in use in an
    // empty shop — and, the other way round, would make a genuinely idle device look busy.
    rt.create_session(&admin, -60, Some("till-1"))
        .await
        .unwrap();

    let devices = rt.list_devices().await.unwrap();

    assert_eq!(devices[0].open_sessions, 0);
    assert_eq!(devices[0].last_sign_in, "");
    assert_eq!(devices[0].signed_in_until, "");
}

/// hub#2599: the server ends the live channels (`/ws`, `/api/events`) of the sessions a revocation
/// deletes, so the runtime has to say exactly which ones it deleted — every row of THIS device in
/// THIS business, the expired one included (a channel outlives the expiry of the session it opened
/// with, hub#2600) — and none of the other till, none that names no device, and none of the
/// business next door that knows a tablet by the same id, whose rows live in the same database.
#[tokio::test]
async fn revoking_a_device_names_exactly_the_sessions_it_ended_hub2599() {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let mine = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-2599-mine");
    let theirs = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-2599-theirs");
    let mut tokens = Vec::new();
    for rt in [&mine, &theirs] {
        rt.ensure_system_tables().await.unwrap();
        let admin = rt
            .create_user("Admin", "1111", "admin", None)
            .await
            .unwrap();
        rt.trust_device("laptop-1", "Office laptop").await.unwrap();
        tokens.push(
            rt.create_session(&admin, 3600, Some("laptop-1"))
                .await
                .unwrap(),
        );
    }
    let (at_laptop, neighbour_laptop) = (tokens[0].clone(), tokens[1].clone());
    let admin = mine
        .create_user("Owner", "2222", "admin", None)
        .await
        .unwrap();
    let at_till = mine
        .create_session(&admin, 3600, Some("till-1"))
        .await
        .unwrap();
    let anonymous = mine.create_session(&admin, 3600, None).await.unwrap();
    let expired_on_laptop = mine
        .create_session(&admin, 3600, Some("laptop-1"))
        .await
        .unwrap();
    let mut p = erplora_db::Params::new();
    p.insert("token".into(), serde_json::json!(expired_on_laptop));
    p.insert(
        "past".into(),
        serde_json::json!((chrono::Utc::now() - chrono::Duration::days(2)).to_rfc3339()),
    );
    mine.db()
        .execute(
            "UPDATE hub_session SET expires_at = :past WHERE token = :token",
            &p,
        )
        .await
        .unwrap();

    let revocation = mine.revoke_device("laptop-1").await.unwrap();

    let mut ended = revocation.ended_sessions.clone();
    ended.sort();
    let mut expected = vec![at_laptop, expired_on_laptop];
    expected.sort();
    assert_eq!(ended, expected, "exactly the rows of this device, here");
    assert_eq!(
        revocation.sessions_closed, 1,
        "the count the owner reads is still the open ones only"
    );
    for kept in [&at_till, &anonymous] {
        assert!(session_is_alive(&mine, kept).await);
    }
    assert!(session_is_alive(&theirs, &neighbour_laptop).await);
}
