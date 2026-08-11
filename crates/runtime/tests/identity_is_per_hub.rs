//! **A session belongs to a HUB, not to a database** (hub#497).
//!
//! `hub_user` and `hub_session` were the last two system tables without a `hub_id` — everything
//! else (`hub_settings`, `hub_api_key`, `hub_module`, `hub_user_profile`, and since hub#489
//! `hub_trusted_device`) is keyed on `(hub_id, …)`. The **profile** of a person was per hub; the
//! person was not.
//!
//! In a database shared by several hubs that was not "seeing too much", it was **getting in**:
//!
//!  - `resolve_session` matched a token and nothing else, so a token minted by hub B authenticated
//!    against hub A — with B's role, and therefore B's permissions;
//!  - `verify_pin` searched the whole table by name, so a four-digit PIN of an employee next door
//!    was a login here;
//!  - a revocation closed `hub_session` rows by `device_id` alone: cutting off a tablet in A
//!    signed the same tablet out of B;
//!  - the single-active-device rule of ADR-0154 deleted every *other* session of the database, so
//!    signing in here signed the neighbour's staff out.
//!
//! # Why this is defence in depth today, and still worth doing
//!
//! Since **ADR-0201** each hub owns its own database (`Hub.database_name`) and its own role, and
//! production has no hub that shares one — verified before this change: 5 hubs, 5 distinct
//! databases, 5 distinct roles, the oldest created *after* ADR-0201 completed. There is not even a
//! legacy hub left to migrate. So this is not a live leak; it is the runtime's SQL finally
//! enforcing what the infrastructure happens to guarantee. The row contract of this schema says
//! `(hub_id, …)` and the isolation of an **authentication** boundary should not depend on
//! provisioning never sharing a database again.
//!
//! # How these tests are written
//!
//! Every one of them keeps **the neighbour alive and populated while the action runs**, and asserts
//! the neighbour came out of it unchanged. A test that emptied the neighbour first — or that only
//! checked "nothing showed up" — passes just as well against the unscoped SQL, which is how this
//! survived as long as it did. Each negative is paired with the same call succeeding where it
//! should.
use erplora_db::testutil::TestDb;
use erplora_runtime::Runtime;

/// A hub running on `test_db`, booted the way the server boots it.
async fn hub_on(test_db: &TestDb, hub_id: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// Two hubs **sharing one database** — the pre-ADR-0201 shape. Since ADR-0201 each hub owns its
/// own, so this is the legacy shape *and* the defence in depth: the row contract of this schema is
/// `(hub_id, …)` whatever the deployment does with databases.
async fn two_hubs_sharing_a_database() -> (TestDb, Runtime, Runtime) {
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let neighbour = hub_on(&test_db, "hub-neighbour").await;
    (test_db, mine, neighbour)
}

/// A business with staff signed in on the shop tablet. Returns `(user_id, session_token)`.
async fn a_business_with_someone_signed_in(
    rt: &Runtime,
    name: &str,
    pin: &str,
    device: &str,
) -> (String, String) {
    let user = rt.create_user(name, pin, "admin", None).await.unwrap();
    rt.trust_device(device, name).await.unwrap();
    let token = rt.create_session(&user, 3600, Some(device)).await.unwrap();
    (user, token)
}

// ── Getting in ────────────────────────────────────────────────────────────────────────────────

/// **The one that matters.** A token is a bearer credential: whoever holds it is signed in. Matched
/// by `token` alone, the neighbour's token signed its holder into this hub — as whatever role they
/// hold *there*.
#[tokio::test]
async fn a_session_token_of_the_business_next_door_opens_nothing_here() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    let (_them, their_token) =
        a_business_with_someone_signed_in(&neighbour, "Ana", "1111", "their-till").await;
    a_business_with_someone_signed_in(&mine, "Bruno", "2222", "my-till").await;

    assert!(
        mine.resolve_session(&their_token).await.unwrap().is_none(),
        "a token minted next door is not a session here"
    );

    // …and the token is not simply broken: it still signs Ana into her own hub, at the same instant,
    // in the same database. Without this the test would pass against a resolver that resolves nothing.
    let still_theirs = neighbour
        .resolve_session(&their_token)
        .await
        .unwrap()
        .expect("Ana is still signed in to her own business");
    assert_eq!(still_theirs.name, "Ana");
}

/// A PIN is four digits. The gate that makes that acceptable is that it only works against the
/// people of *this* hub on a device this hub already trusts — and the census was the whole table.
#[tokio::test]
async fn a_pin_of_an_employee_next_door_is_not_a_login_here() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    neighbour.create_user("Marta", "4321", "cashier", None).await.unwrap();
    mine.create_user("Bruno", "2222", "admin", None).await.unwrap();

    assert!(
        mine.verify_pin("Marta", "4321").await.unwrap().is_none(),
        "the neighbour's staff are not staff here"
    );
    assert!(
        neighbour
            .verify_pin("Marta", "4321")
            .await
            .unwrap()
            .is_some(),
        "…and Marta can still clock in where she works"
    );
    assert!(
        mine.verify_pin("Bruno", "2222").await.unwrap().is_some(),
        "my own staff are unaffected"
    );
}

/// The pinpad shows a list of names to tap. It was showing the people of every business in the
/// database — the staff of the shop next door, by name, on a screen in this one.
#[tokio::test]
async fn the_pin_screen_only_offers_the_people_of_this_business() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    neighbour.create_user("Marta", "4321", "cashier", None).await.unwrap();
    mine.create_user("Bruno", "2222", "admin", None).await.unwrap();

    let mut here: Vec<String> = mine
        .list_pin_users()
        .await
        .unwrap()
        .into_iter()
        .map(|(_, name, _)| name)
        .collect();
    here.sort();
    assert_eq!(here, vec!["Bruno".to_string()]);

    let mut there: Vec<String> = neighbour
        .list_pin_users()
        .await
        .unwrap()
        .into_iter()
        .map(|(_, name, _)| name)
        .collect();
    there.sort();
    assert_eq!(there, vec!["Marta".to_string()], "and theirs is intact");
}

/// The people who sign in with a Cloud account are the same census by another door. An owner
/// reading their own users screen was reading the neighbour's payroll: names, emails and roles.
#[tokio::test]
async fn the_users_screen_does_not_list_the_business_next_door() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    neighbour
        .create_login_user("ana@next-door.example", "admin")
        .await
        .unwrap();
    mine.create_login_user("bruno@mine.example", "admin")
        .await
        .unwrap();

    let here: Vec<String> = mine
        .list_login_users()
        .await
        .unwrap()
        .into_iter()
        .map(|u| u.email)
        .collect();
    assert_eq!(here, vec!["bruno@mine.example".to_string()]);

    let there: Vec<String> = neighbour
        .list_login_users()
        .await
        .unwrap()
        .into_iter()
        .map(|u| u.email)
        .collect();
    assert_eq!(there, vec!["ana@next-door.example".to_string()]);
}

// ── Collateral ────────────────────────────────────────────────────────────────────────────────

/// **Cutting off a lost tablet must not sign out the business next door.** hub#489 scoped the trust
/// row; the session delete could not be scoped and so still reached across. The same tablet in two
/// businesses is a real case — the same person's shop and their partner's — which is exactly why
/// `hub_trusted_device` is keyed `(hub_id, device_id)`.
#[tokio::test]
async fn revoking_a_tablet_here_does_not_sign_it_out_next_door() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    let (_them, their_token) =
        a_business_with_someone_signed_in(&neighbour, "Ana", "1111", "tablet-1").await;
    let (_me, my_token) =
        a_business_with_someone_signed_in(&mine, "Bruno", "2222", "tablet-1").await;

    let cut = mine.revoke_device("tablet-1").await.unwrap();

    assert!(
        mine.resolve_session(&my_token).await.unwrap().is_none(),
        "my own session on that tablet is closed — that is the point of a revocation"
    );
    assert!(
        neighbour
            .resolve_session(&their_token)
            .await
            .unwrap()
            .is_some(),
        "the neighbour's staff stay signed in on their own tablet of the same id"
    );
    assert_eq!(
        cut.sessions_closed, 1,
        "exactly one session was closed — mine"
    );
}

/// The single active session of ADR-0154 is per **hub**: signing in at the till closes this
/// business's other sessions, not the sessions of every business in the database.
#[tokio::test]
async fn signing_in_here_does_not_sign_the_neighbours_staff_out() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    let (_them, their_token) =
        a_business_with_someone_signed_in(&neighbour, "Ana", "1111", "their-till").await;
    let (me, my_old_token) =
        a_business_with_someone_signed_in(&mine, "Bruno", "2222", "old-till").await;

    // Bruno signs in on a different device: his previous session goes, and only his.
    mine.trust_device("new-till", "Bruno").await.unwrap();
    let my_new_token = mine.create_session(&me, 3600, Some("new-till")).await.unwrap();
    mine.enforce_device_limit(1, Some("new-till")).await.unwrap();

    assert!(
        mine.resolve_session(&my_new_token).await.unwrap().is_some(),
        "the session just opened survives"
    );
    assert!(
        mine.resolve_session(&my_old_token).await.unwrap().is_none(),
        "…and the one it replaced is gone"
    );
    assert!(
        neighbour
            .resolve_session(&their_token)
            .await
            .unwrap()
            .is_some(),
        "the shop next door did not have its staff signed out by mine"
    );
}

/// The devices screen reports how many sessions a device has open and until when. Counted across
/// the whole database, one business's activity was shown as another's.
#[tokio::test]
async fn the_devices_screen_does_not_count_the_neighbours_open_sessions() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    a_business_with_someone_signed_in(&neighbour, "Ana", "1111", "tablet-1").await;
    a_business_with_someone_signed_in(&mine, "Bruno", "2222", "tablet-1").await;

    let listed = mine.list_devices().await.unwrap();
    let tablet = listed
        .iter()
        .find(|d| d.device_id == "tablet-1")
        .expect("my own tablet is listed");
    assert_eq!(
        tablet.open_sessions, 1,
        "one person is signed in on my tablet — the neighbour's is not my activity"
    );

    // And the neighbour reads its own, equally, at the same instant.
    let theirs = neighbour.list_devices().await.unwrap();
    let their_tablet = theirs
        .iter()
        .find(|d| d.device_id == "tablet-1")
        .expect("their tablet is listed for them");
    assert_eq!(their_tablet.open_sessions, 1);
}

// ── The column itself ─────────────────────────────────────────────────────────────────────────

/// The same person's name and the same PIN in two businesses is the ordinary case (a common first
/// name, a default PIN), and both must work. It also pins that nothing was made unique across the
/// database in the process — the fix is a `WHERE`, not a constraint that would make one hub's
/// hiring fail because of another's.
#[tokio::test]
async fn two_businesses_can_employ_the_same_name_with_the_same_pin() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    neighbour.create_user("Marta", "1234", "cashier", None).await.unwrap();
    mine.create_user("Marta", "1234", "cashier", None).await.unwrap();

    let here = mine.verify_pin("Marta", "1234").await.unwrap().unwrap();
    let there = neighbour.verify_pin("Marta", "1234").await.unwrap().unwrap();
    assert_ne!(
        here.id, there.id,
        "two people, two rows — not one row two businesses share"
    );
}
