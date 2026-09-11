//! **Local user alta** — name + PIN, nothing in the SaaS (plan step 2b, hub#355).
//!
//! The plan states two identities and one row: a **local user** (PIN only, no email, no ERPlora
//! account) and an **account user** (email + invitation, hub#356). Both are the SAME `hub_user`
//! row, so a local user can be promoted later without losing their history
//! (`get_or_link_cloud_user` links by email keeping the role).
//!
//! What these tests pin down is the **security** half of that alta, because a local user is
//! somebody who can work the till:
//!
//!  - a local user is **useless without a PIN**, so the PIN is required — not optional as in the
//!    generic alta, where a row with neither PIN nor account is a legitimate "person who does not
//!    sign in";
//!  - a local user carries **no email**: nothing is created in the SaaS, so an email here would be
//!    an account that nobody ever invited;
//!  - a local user **never administers the hub**: administration comes from the account plane
//!    (`HUB_OWNER_EMAIL` and the cloud role floor, ADR-0157 / hub#347), never from four digits;
//!  - a PIN is an **attribution** mechanism, so it cannot be guessable nor shared with another
//!    active user — two people behind the same four digits means the sale is attributed to
//!    whoever was tapped on the pinpad, not to whoever typed;
//!  - and the alta **never reopens a door the hub closed** (hub#348): a deactivated row is not
//!    worked around by creating a namesake next to it.
use erplora_db::testutil::fresh_db;
use erplora_runtime::hub_users::{NewHubUser, UpdateHubUser};
use erplora_runtime::Runtime;

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// The alta of a local user: name + PIN + role, and nothing else.
fn local(name: &str, pin: &str, role: &str) -> NewHubUser {
    NewHubUser {
        name: name.into(),
        role: role.into(),
        pin: pin.into(),
        local: true,
        ..NewHubUser::default()
    }
}

/// The stable rejection code of a failed alta (`RuntimeError::Domain`), or the raw message when
/// the runtime answered with something else — the assertion then shows what it really said.
fn code_of(error: &erplora_runtime::RuntimeError) -> String {
    match error {
        erplora_runtime::RuntimeError::Domain { code, .. } => code.clone(),
        other => other.to_string(),
    }
}

#[tokio::test]
async fn a_local_user_is_created_with_a_name_and_a_pin_and_signs_in_with_it() {
    let rt = runtime("hub-local").await;

    let id = rt
        .create_hub_user(&local("Marta Ruiz", "4821", "employee"), 0)
        .await
        .expect("name + PIN is all a local user needs");

    let created = rt
        .list_hub_users()
        .await
        .unwrap()
        .into_iter()
        .find(|u| u.id == id)
        .expect("the local user is listed in Personal");
    assert_eq!(created.name, "Marta Ruiz");
    assert_eq!(created.role, "employee");
    assert!(created.is_active);
    assert!(created.has_pin, "a local user signs in with their PIN");
    assert_eq!(created.email, "", "a local user has no email");
    assert!(
        created.cloud_user_id.is_none(),
        "a local user exists only in this hub: nothing is created in the SaaS"
    );

    // The point of the alta: this person can actually get in, and only with their own PIN.
    let signed_in = rt
        .verify_pin("Marta Ruiz", "4821")
        .await
        .unwrap()
        .expect("the PIN of the alta opens the session");
    assert_eq!(signed_in.id, id);
    assert_eq!(signed_in.role, "employee");
    assert!(rt.verify_pin("Marta Ruiz", "4820").await.unwrap().is_none());
}

#[tokio::test]
async fn a_local_user_without_a_pin_is_rejected_with_a_reason() {
    let rt = runtime("hub-local").await;

    let err = rt
        .create_hub_user(&local("Marta Ruiz", "", "employee"), 0)
        .await
        .unwrap_err();

    assert_eq!(code_of(&err), "hub.users.local_needs_pin");
    assert!(
        rt.list_hub_users().await.unwrap().is_empty(),
        "a rejected alta creates nobody"
    );
}

#[tokio::test]
async fn a_local_user_carries_no_email() {
    // An email here would be an ERPlora account that nobody ever invited: the SaaS is the source of
    // truth of access (ADR-0157 §7) and the local alta deliberately never calls it. Asking for the
    // account user is a different alta (hub#356), not a field somebody fills in by accident.
    let rt = runtime("hub-local").await;

    let err = rt
        .create_hub_user(&NewHubUser {
            email: "marta@example.com".into(),
            ..local("Marta Ruiz", "4821", "employee")
        }, 0)
        .await
        .unwrap_err();

    assert_eq!(code_of(&err), "hub.users.local_has_email");
    assert!(rt.list_hub_users().await.unwrap().is_empty());
}

#[tokio::test]
async fn a_local_user_never_administers_the_hub() {
    // The hardest guard of this alta. Administering the hub — fiscal identity, plan, installing
    // modules, wiping the data — belongs to the ACCOUNT plane: it is seeded from `HUB_OWNER_EMAIL`
    // (ADR-0157) and raised by the cloud role floor (hub#347), and hub#351 already refuses to let a
    // manifest mint administrators. Four digits typed in front of customers cannot be the third
    // way in, so the administrative roles are simply not on offer here.
    let rt = runtime("hub-local").await;

    for role in ["admin", "owner", "ADMIN", "Owner"] {
        let err = rt
            .create_hub_user(&local("Marta Ruiz", "4821", role), 0)
            .await
            .unwrap_err();
        assert_eq!(
            code_of(&err),
            "hub.users.local_cannot_administer",
            "a local user must not be created as `{role}`"
        );
    }
    assert!(rt.list_hub_users().await.unwrap().is_empty());

    // Everything the business plane offers below administration stays available.
    for (name, pin, role) in [
        ("Ana Soto", "4821", "manager"),
        ("Luis Prat", "5390", "employee"),
    ] {
        rt.create_hub_user(&local(name, pin, role), 0)
            .await
            .unwrap_or_else(|e| panic!("`{role}` is a legitimate local role: {e}"));
    }
}

#[tokio::test]
async fn two_active_users_never_share_a_pin() {
    // A PIN is attribution, not authentication: the pinpad resolves NAME + PIN, so two people
    // behind the same four digits means the sale is attributed to whoever was tapped, and the one
    // who actually typed is invisible. Uniqueness is checked against ACTIVE users only — a
    // deactivated row cannot sign in, so it holds no digits hostage.
    let rt = runtime("hub-local").await;
    rt.create_hub_user(&local("Marta Ruiz", "4821", "employee"), 0)
        .await
        .unwrap();

    let err = rt
        .create_hub_user(&local("Luis Prat", "4821", "employee"), 0)
        .await
        .unwrap_err();

    assert_eq!(code_of(&err), "hub.users.pin_in_use");
    let users = rt.list_hub_users().await.unwrap();
    assert_eq!(users.len(), 1, "the second user is not created");
    assert_eq!(users[0].name, "Marta Ruiz");
}

#[tokio::test]
async fn the_pin_of_an_existing_user_cannot_be_changed_into_somebody_elses() {
    // The same rule on the edit door. Without it the alta guard is theatre: create with a free PIN,
    // then edit it into the manager's.
    let rt = runtime("hub-local").await;
    rt.create_hub_user(&local("Marta Ruiz", "4821", "manager"), 0)
        .await
        .unwrap();
    let luis = rt
        .create_hub_user(&local("Luis Prat", "5390", "employee"), 0)
        .await
        .unwrap();

    let err = rt
        .update_hub_user(
            &luis,
            &UpdateHubUser {
                pin: Some("4821".into()),
                ..UpdateHubUser::default()
            }, 0,)
        .await
        .unwrap_err();

    assert_eq!(code_of(&err), "hub.users.pin_in_use");
    assert!(
        rt.verify_pin("Luis Prat", "5390").await.unwrap().is_some(),
        "the rejected edit leaves the old PIN working"
    );
    // Keeping your OWN PIN is not a collision with yourself.
    rt.update_hub_user(
        &luis,
        &UpdateHubUser {
            pin: Some("5390".into()),
            ..UpdateHubUser::default()
        }, 0,)
    .await
    .expect("re-typing your own PIN is not a duplicate");
}

#[tokio::test]
async fn a_guessable_pin_is_rejected() {
    // Four digits in front of customers: the two classes anybody tries first — all the same digit
    // and a straight run — are not a PIN, they are a formality. Rejected at the only moment the
    // hub ever sees the digits in clear (they are stored as a salted argon2id hash).
    let rt = runtime("hub-local").await;

    // Los ejemplos van en la longitud que pide el hub (hub#974: es fija, y este pide cuatro): un
    // `345678` se rechazaría por LARGO antes de llegar a la lista de adivinables, y el test estaría
    // midiendo otra puerta.
    for weak in ["0000", "1111", "9999", "1234", "4321", "6789"] {
        let err = rt
            .create_hub_user(&local("Marta Ruiz", weak, "employee"), 0)
            .await
            .unwrap_err();
        assert_eq!(
            code_of(&err),
            "hub.users.pin_too_simple",
            "`{weak}` must not be accepted as a PIN"
        );
    }
    assert!(rt.list_hub_users().await.unwrap().is_empty());

    for good in ["4821", "5390", "1357", "9021"] {
        rt.create_hub_user(&local(&format!("User {good}"), good, "employee"), 0)
            .await
            .unwrap_or_else(|e| panic!("`{good}` is a legitimate PIN: {e}"));
    }
}

#[tokio::test]
async fn the_alta_never_reopens_a_door_the_hub_closed() {
    // hub#348 stopped a deactivated row from being re-provisioned as a brand new one by the cloud
    // login. This alta must not become the back door to the same thing: creating a namesake next
    // to somebody who was just deactivated hands out a working PIN to a person the hub (or the
    // SaaS) locked out, and leaves two identities for one person — exactly what "one person, one
    // `hub_user` row" exists to prevent. The way back in is to REINSTATE the row, which is an
    // explicit, audited decision of the administrator.
    let rt = runtime("hub-local").await;
    let marta = rt
        .create_hub_user(&local("Marta Ruiz", "4821", "employee"), 0)
        .await
        .unwrap();
    rt.update_hub_user(
        &marta,
        &UpdateHubUser {
            is_active: Some(false),
            ..UpdateHubUser::default()
        }, 0,)
    .await
    .unwrap();

    let err = rt
        .create_hub_user(&local("Marta Ruiz", "5390", "employee"), 0)
        .await
        .unwrap_err();

    assert_eq!(code_of(&err), "hub.users.name_taken");
    let users = rt.list_hub_users().await.unwrap();
    assert_eq!(users.len(), 1, "no second identity for the same person");
    assert!(!users[0].is_active, "and the closed door stays closed");
    assert!(
        rt.verify_pin("Marta Ruiz", "5390").await.unwrap().is_none(),
        "the PIN of the rejected alta opens nothing"
    );

    // Nor by changing the case: two names the pinpad shows as the same person are the same person.
    for spelling in ["marta ruiz", "MARTA RUIZ", "  Marta Ruiz  "] {
        assert_eq!(
            code_of(
                &rt.create_hub_user(&local(spelling, "5390", "employee"), 0)
                    .await
                    .unwrap_err()
            ),
            "hub.users.name_taken",
            "`{spelling}` is the same person on the pinpad"
        );
    }
}

#[tokio::test]
async fn a_membership_revoked_by_the_saas_is_not_worked_around_with_a_local_alta() {
    // The same door, closed by the OTHER authority (hub#348 rule D): the SaaS revoked the
    // membership, so the row is inactive with `cloud_revoked_at` set. Handing that person a local
    // PIN would give them back the hub the SaaS just took away — and this time without any
    // membership at all to re-check on the next login.
    let rt = runtime("hub-local").await;
    let cloud = rt
        .get_or_link_cloud_user(
            "cloud-9",
            "Ana Soto",
            "manager",
            Some("ana@example.com"),
            None,
        )
        .await
        .unwrap();
    assert_eq!(
        rt.revoke_cloud_access("cloud-9", Some("ana@example.com"))
            .await
            .unwrap(),
        1
    );

    let err = rt
        .create_hub_user(&local("Ana Soto", "4821", "employee"), 0)
        .await
        .unwrap_err();

    assert_eq!(code_of(&err), "hub.users.name_taken");
    let users = rt.list_hub_users().await.unwrap();
    assert_eq!(users.len(), 1);
    assert_eq!(users[0].id, cloud.id);
    assert!(!users[0].is_active);
    assert!(rt.verify_pin("Ana Soto", "4821").await.unwrap().is_none());
}
