//! **When a session runs out, read through the same door that resolves it** (hub#2600).
//!
//! The live channel of a session closes when that session expires. To know when, the stream ticket
//! reads the session's `expires_at` — and that read is an authentication read: it answers for a
//! bearer token. So it is scoped like [`Runtime::resolve_session`] (hub#497): this hub's row, a
//! person of this hub who is still active, and a session that has not run out yet. Anything else
//! has no expiry to give, because it is not a session here.
//!
//! The neighbour's hub shares the database and is populated while each read runs: a query that
//! forgot `hub_id` hands this hub the neighbour's deadline, and that is what these tests catch.
use erplora_db::testutil::TestDb;
use erplora_runtime::Runtime;

async fn hub_on(test_db: &TestDb, hub_id: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// Signs `name` in on `rt` for `ttl_secs`. Returns `(user_id, session_token)`.
async fn signed_in(rt: &Runtime, name: &str, pin: &str, ttl_secs: i64) -> (String, String) {
    let user = rt.create_user(name, pin, "employee", None).await.unwrap();
    let token = rt.create_session(&user, ttl_secs, None).await.unwrap();
    (user, token)
}

/// A session of this hub gives the moment it runs out — the one it was opened with, not "about
/// now" and not the ticket's minute.
#[tokio::test]
async fn hub2600_a_live_session_says_when_it_runs_out() {
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let before = chrono::Utc::now();
    let (_, token) = signed_in(&mine, "Bruno", "2222", 7200).await;
    let after = chrono::Utc::now();

    let ends = mine
        .session_expires_at(&token)
        .await
        .unwrap()
        .expect("a live session has an end");

    assert!(
        ends >= before + chrono::Duration::seconds(7200)
            && ends <= after + chrono::Duration::seconds(7200),
        "the end is the one the session was opened with: {ends}"
    );
}

/// **Tenancy.** The neighbour's token, with the neighbour alive and signed in, has no end here.
#[tokio::test]
async fn hub2600_a_session_of_the_business_next_door_has_no_end_here() {
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let neighbour = hub_on(&test_db, "hub-neighbour").await;
    let (_, theirs) = signed_in(&neighbour, "Ana", "1111", 3600).await;
    let (_, ours) = signed_in(&mine, "Bruno", "2222", 3600).await;

    assert!(
        mine.session_expires_at(&theirs).await.unwrap().is_none(),
        "the neighbour's session is not a session of this hub"
    );
    assert!(
        neighbour
            .session_expires_at(&theirs)
            .await
            .unwrap()
            .is_some(),
        "…and it is still alive at home"
    );
    assert!(mine.session_expires_at(&ours).await.unwrap().is_some());
}

/// A session that has already run out has no end left to wait for.
#[tokio::test]
async fn hub2600_an_expired_session_has_no_end_left() {
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let (_, gone) = signed_in(&mine, "Bruno", "2222", -60).await;
    let (_, live) = signed_in(&mine, "Carla", "3333", 3600).await;

    assert!(mine.session_expires_at(&gone).await.unwrap().is_none());
    assert!(mine.session_expires_at(&live).await.unwrap().is_some());
}

/// A person taken off the team holds no session here, even if the row has time left.
#[tokio::test]
async fn hub2600_the_session_of_someone_taken_off_the_team_has_no_end() {
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let (user, token) = signed_in(&mine, "Bruno", "2222", 3600).await;
    let (_, colleague) = signed_in(&mine, "Carla", "3333", 3600).await;

    let mut p = erplora_db::Params::new();
    p.insert("hub_id".into(), serde_json::json!("hub-mine"));
    p.insert("id".into(), serde_json::json!(user));
    mine.db()
        .execute(
            "UPDATE hub_user SET is_active = 0 WHERE hub_id = :hub_id AND id = :id",
            &p,
        )
        .await
        .unwrap();

    assert!(mine.session_expires_at(&token).await.unwrap().is_none());
    assert!(mine.session_expires_at(&colleague).await.unwrap().is_some());
}
