//! hub#2500 — the rules of Employees hold on EVERY path that can leave the data in that state, not
//! only on the one the screen uses first.
//!
//! - A person who signs in with a PIN only never administers the hub: refused at the sign-up
//!   (hub#355) and now also when the record is edited (HUB-F145, HUB-F148).
//! - An address is the same address whatever its capitals: signing in with the account the person
//!   was invited with finds the invited record instead of creating a second one (HUB-F130), and the
//!   `/api/members` door finds it too.
//! - The hub never ends up without an active administrator: the write itself re-checks it, so two
//!   administrators taking the role away from each other at the same time leave one (HUB-F149).
use erplora_db::testutil::fresh_db;
use erplora_runtime::hub_users::{HubUserRow, NewHubUser, UpdateHubUser};
use erplora_runtime::{Runtime, RuntimeError};

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn row(rt: &Runtime, id: &str) -> HubUserRow {
    rt.list_hub_users()
        .await
        .unwrap()
        .into_iter()
        .find(|u| u.id == id)
        .expect("the person is in the list")
}

fn domain_code(err: &RuntimeError) -> String {
    match err {
        RuntimeError::Domain { code, .. } => code.clone(),
        other => panic!("expected a domain refusal with a stable code, got {other:?}"),
    }
}

async fn local_person(rt: &Runtime, name: &str, pin: &str) -> String {
    rt.create_hub_user(
        &NewHubUser {
            name: name.into(),
            role: "employee".into(),
            pin: pin.into(),
            local: true,
            ..NewHubUser::default()
        },
        0,
    )
    .await
    .unwrap()
}

async fn account_person(rt: &Runtime, name: &str, email: &str, role: &str) -> String {
    rt.create_hub_user(
        &NewHubUser {
            name: name.into(),
            email: email.into(),
            role: role.into(),
            local: false,
            ..NewHubUser::default()
        },
        0,
    )
    .await
    .unwrap()
}

fn set_role(role: &str) -> UpdateHubUser {
    UpdateHubUser {
        role: Some(role.into()),
        ..UpdateHubUser::default()
    }
}

fn deactivate() -> UpdateHubUser {
    UpdateHubUser {
        is_active: Some(false),
        ..UpdateHubUser::default()
    }
}

async fn active_admins(rt: &Runtime) -> usize {
    rt.list_hub_users()
        .await
        .unwrap()
        .into_iter()
        .filter(|u| u.is_active && erplora_runtime::hub_users::is_admin_role(&u.role))
        .count()
}

// ── A PIN never administers the hub ──────────────────────────────────────────────────────────

#[tokio::test]
async fn hub2500_editing_a_pin_only_person_into_an_administrator_is_refused() {
    let rt = runtime("hub-2500-a").await;
    let marta = local_person(&rt, "Marta Ruiz", "4821").await;

    let err = rt
        .update_hub_user(&marta, &set_role("admin"), 0)
        .await
        .expect_err("a PIN-only person cannot be made an administrator by editing their record");
    assert_eq!(domain_code(&err), "hub.users.local_cannot_administer");
    assert_eq!(row(&rt, &marta).await.role, "employee", "nothing was written");

    // `owner` is the legacy spelling of the same power: the same answer.
    let err = rt
        .update_hub_user(&marta, &set_role("Owner"), 0)
        .await
        .expect_err("the legacy owner role is administration too");
    assert_eq!(domain_code(&err), "hub.users.local_cannot_administer");
}

#[tokio::test]
async fn hub2500_giving_a_pin_only_person_an_account_and_the_admin_role_together_is_allowed() {
    let rt = runtime("hub-2500-b").await;
    let marta = local_person(&rt, "Marta Ruiz", "4821").await;

    // An email turns the record into an account person (HUB-F148): administration then comes from
    // that account, which erplora.com is asked to grant (the HTTP layer does that first).
    let updated = rt
        .update_hub_user(
            &marta,
            &UpdateHubUser {
                email: Some("marta@example.com".into()),
                role: Some("admin".into()),
                ..UpdateHubUser::default()
            },
            0,
        )
        .await
        .expect("with an account, the person may administer");
    assert_eq!(updated.role, "admin");
}

#[tokio::test]
async fn hub2500_taking_the_email_away_from_an_invited_administrator_is_refused() {
    let rt = runtime("hub-2500-c").await;
    let _owner = rt
        .get_or_link_cloud_user("cloud-owner", "Ioan", "admin", None, None)
        .await
        .unwrap();
    let ana = account_person(&rt, "Ana López", "ana@example.com", "admin").await;
    rt.update_hub_user(
        &ana,
        &UpdateHubUser {
            pin: Some("5937".into()),
            ..UpdateHubUser::default()
        },
        0,
    )
    .await
    .unwrap();

    // Without the email (and never signed in) she would be an administrator who signs in with a PIN
    // only: the state the sign-up refuses.
    let err = rt
        .update_hub_user(
            &ana,
            &UpdateHubUser {
                email: Some(String::new()),
                ..UpdateHubUser::default()
            },
            0,
        )
        .await
        .expect_err("removing the account of an administrator leaves a PIN administering the hub");
    assert_eq!(domain_code(&err), "hub.users.local_cannot_administer");
    assert_eq!(row(&rt, &ana).await.email, "ana@example.com");
}

#[tokio::test]
async fn hub2500_a_pin_only_person_keeps_being_editable_in_everything_else() {
    let rt = runtime("hub-2500-d").await;
    let marta = local_person(&rt, "Marta Ruiz", "4821").await;

    let updated = rt
        .update_hub_user(
            &marta,
            &UpdateHubUser {
                name: Some("Marta Ruiz Gil".into()),
                role: Some("manager".into()),
                ..UpdateHubUser::default()
            },
            0,
        )
        .await
        .expect("a non-administrator role and a new name are fine");
    assert_eq!(updated.role, "manager");
    assert_eq!(updated.name, "Marta Ruiz Gil");
}

// ── An address is the same whatever its capitals ─────────────────────────────────────────────

#[tokio::test]
async fn hub2500_signing_in_with_the_invited_address_in_other_capitals_finds_the_invited_person() {
    let rt = runtime("hub-2500-e").await;
    let ana = account_person(&rt, "Ana López", "Ana.Lopez@Example.com", "manager").await;
    let before = rt.list_hub_users().await.unwrap().len();

    let signed_in = rt
        .get_or_link_cloud_user(
            "cloud-ana",
            "ana.lopez",
            "employee",
            Some("ana.lopez@example.com"),
            None,
        )
        .await
        .unwrap();

    assert_eq!(signed_in.id, ana, "the invited record is the one that signs in");
    assert_eq!(signed_in.role, "manager", "with the role the administrator gave her");
    assert_eq!(
        rt.list_hub_users().await.unwrap().len(),
        before,
        "no second record for the same person"
    );
}

#[tokio::test]
async fn hub2500_the_members_door_finds_the_person_whatever_the_capitals() {
    let rt = runtime("hub-2500-f").await;
    let _owner = rt
        .get_or_link_cloud_user("cloud-owner", "Ioan", "admin", None, None)
        .await
        .unwrap();
    let ana = account_person(&rt, "Ana López", "ana.lopez@example.com", "employee").await;
    let before = rt.list_hub_users().await.unwrap().len();

    let reinvited = rt
        .create_login_user("Ana.Lopez@Example.COM", "manager", 0)
        .await
        .unwrap();
    assert_eq!(reinvited.id, ana, "a re-invitation, not a second record");
    assert_eq!(rt.list_hub_users().await.unwrap().len(), before);

    assert!(
        rt.deactivate_login_user("ANA.LOPEZ@EXAMPLE.COM").await.unwrap(),
        "the baja by address reaches her"
    );
    assert!(!row(&rt, &ana).await.is_active);
}

// ── Never without an administrator ───────────────────────────────────────────────────────────

#[tokio::test]
async fn hub2500_the_write_itself_refuses_to_leave_the_hub_without_an_administrator() {
    let rt = runtime("hub-2500-g").await;
    let owner = rt
        .get_or_link_cloud_user("cloud-owner", "Ioan", "admin", None, None)
        .await
        .unwrap();

    // The HTTP layer checks this before calling; the runtime is the last word, so a check that
    // ran on an older picture of the team cannot slip through.
    let err = rt
        .update_hub_user(&owner.id, &set_role("employee"), 0)
        .await
        .expect_err("demoting the only administrator is refused by the write");
    assert_eq!(domain_code(&err), "hub.users.last_admin");

    let err = rt
        .update_hub_user(&owner.id, &deactivate(), 0)
        .await
        .expect_err("taking the only administrator off the team is refused by the write");
    assert_eq!(domain_code(&err), "hub.users.last_admin");

    let after = row(&rt, &owner.id).await;
    assert!(after.is_active);
    assert_eq!(after.role, "admin");
}

#[tokio::test]
async fn hub2500_two_administrators_demoting_each_other_at_once_leave_one() {
    let rt = runtime("hub-2500-h").await;
    let a = rt
        .get_or_link_cloud_user("cloud-a", "Ana", "admin", None, None)
        .await
        .unwrap();
    let b = rt
        .get_or_link_cloud_user("cloud-b", "Bea", "admin", None, None)
        .await
        .unwrap();
    assert_eq!(active_admins(&rt).await, 2);

    let demote_a = set_role("employee");
    let deactivate_b = deactivate();
    let (first, second) = tokio::join!(
        rt.update_hub_user(&a.id, &demote_a, 0),
        rt.update_hub_user(&b.id, &deactivate_b, 0),
    );
    let refused: Vec<_> = [&first, &second]
        .into_iter()
        .filter_map(|r| r.as_ref().err())
        .collect();
    assert_eq!(
        refused.len(),
        1,
        "exactly one of the two goes through: {first:?} / {second:?}"
    );
    assert_eq!(domain_code(refused[0]), "hub.users.last_admin");
    assert_eq!(active_admins(&rt).await, 1, "the hub keeps one administrator");
}

#[tokio::test]
async fn hub2500_with_a_second_administrator_the_demotion_goes_through() {
    let rt = runtime("hub-2500-i").await;
    let a = rt
        .get_or_link_cloud_user("cloud-a", "Ana", "admin", None, None)
        .await
        .unwrap();
    let _b = rt
        .get_or_link_cloud_user("cloud-b", "Bea", "admin", None, None)
        .await
        .unwrap();

    let updated = rt
        .update_hub_user(&a.id, &set_role("employee"), 0)
        .await
        .expect("another administrator stays");
    assert_eq!(updated.role, "employee");
    // A non-administrator leaving never asks for the check at all.
    let marta = local_person(&rt, "Marta Ruiz", "4821").await;
    rt.update_hub_user(&marta, &deactivate(), 0).await.unwrap();
}

#[tokio::test]
async fn hub2500_the_members_door_cannot_take_off_the_last_administrator_either() {
    let rt = runtime("hub-2500-j").await;
    let ana = account_person(&rt, "Ana López", "ana@example.com", "admin").await;

    let err = rt
        .deactivate_login_user("ana@example.com")
        .await
        .expect_err("the baja by address of the only administrator is refused");
    assert_eq!(domain_code(&err), "hub.users.last_admin");

    let err = rt
        .create_login_user("ana@example.com", "employee", 0)
        .await
        .expect_err("a re-invitation that demotes the only administrator is refused");
    assert_eq!(domain_code(&err), "hub.users.last_admin");

    let after = row(&rt, &ana).await;
    assert!(after.is_active);
    assert_eq!(after.role, "admin");
}

/// **The demotion WAITS for the administrators' lock** — the guard that dies if the lock is taken
/// away from the write. The race above is real but its window is microseconds, so a test of two
/// tasks rarely sees it (measured: removing the lock leaves it green). The deterministic side, the
/// same one hub#1804 uses for the seats: another connection holds this hub's `<hub>/admins` lock,
/// and taking administration away from somebody cannot finish before it lets go.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn hub2500_taking_administration_away_waits_for_the_administrators_lock() {
    use erplora_db::{DatabaseAdapter, Params};
    use serde_json::json;
    use std::time::{Duration, Instant};

    const HUB: &str = "hub-2500-k";
    const HELD_FOR: Duration = Duration::from_millis(1_500);

    let tdb = erplora_db::testutil::TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(tdb.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    let a = rt
        .get_or_link_cloud_user("cloud-a", "Ana", "admin", None, None)
        .await
        .unwrap();
    let _b = rt
        .get_or_link_cloud_user("cloud-b", "Bea", "admin", None, None)
        .await
        .unwrap();

    let holder = tdb.adapter().await;
    let mut held = Params::new();
    held.insert("admins_key".into(), json!(format!("{HUB}/admins")));
    let holding = tokio::spawn(async move {
        holder
            .execute_tx_gated(
                &[
                    (
                        "SELECT pg_advisory_xact_lock(hashtext(:admins_key))".to_string(),
                        held.clone(),
                    ),
                    (
                        format!("SELECT pg_sleep({})", HELD_FOR.as_secs_f64()),
                        held.clone(),
                    ),
                ],
                &[],
                &[],
            )
            .await
            .expect("the connection holding the lock cannot fail");
    });
    // The lock is taken inside the transaction above: give it time to get it.
    tokio::time::sleep(Duration::from_millis(400)).await;

    let started = Instant::now();
    rt.update_hub_user(&a.id, &set_role("employee"), 0)
        .await
        .expect("another administrator stays: the demotion goes through, only after waiting");
    let waited = started.elapsed();
    holding.await.expect("the holder finishes");

    assert!(
        waited >= Duration::from_millis(700),
        "the demotion has to WAIT for the administrators' lock before counting and writing; it \
         came back in {waited:?}, so it counted without serializing with anybody"
    );
}
