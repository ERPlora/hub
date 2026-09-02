//! **Account user alta** — email + invitation, and the row the login will find (plan step 2b,
//! hub#356). The twin of `local_user.rs`: there the identity lives only in this hub, here it lives
//! in the SaaS and the hub only holds the local half of it.
//!
//! The plan states two identities and one row. hub#355 built the local half behind an explicit
//! «Local user» checkbox and deliberately left the alta unchanged when the box is off. This is the
//! other half, and it makes the alta **exhaustive**: without the box the alta is an **account
//! user**, so the email is required and the SaaS is called. A row with neither PIN nor account —
//! the "person who does not sign in" the generic alta used to allow — is no longer something the
//! alta can create, because it is exactly the mistake the plan calls silent: a person the SaaS
//! never invited and who therefore can never get in.
//!
//! This is the frontier with the SaaS, so the guards are resolved on the conservative side:
//!
//!  - **an email is mandatory** — an account user without one is a ficha nobody invited;
//!  - **the role has to be one the SaaS can grant** (`employee`/`manager`/`admin`, the SaaS's own
//!    `HUB_ROLES`): anything else is refused by `POST /device/members/` with a 400, so letting the
//!    alta through would leave a local row with an email and no membership behind;
//!  - **an email this hub already knows is never invited twice**, active **or** deactivated — the
//!    email twin of `name_taken` (hub#355) and the door through which a membership the hub revoked
//!    (hub#348) would come back to life without anybody deciding it;
//!  - **the PIN stays optional** for an account user, but if one is typed it goes through exactly
//!    the same funnel as the local one (4–8 digits, not guessable, not another active user's);
//!  - and the email is written **where access looks for it** (`hub_user.email`), which is what
//!    makes the invited person's first login land on *this* row instead of provisioning a second
//!    one with the least-privilege role.
use erplora_db::testutil::fresh_db;
use erplora_runtime::hub_users::{NewHubUser, UpdateHubUser};
use erplora_runtime::Runtime;

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// The alta of an account user: name + email + role (+ an optional PIN), box unchecked.
fn account(name: &str, email: &str, role: &str) -> NewHubUser {
    NewHubUser {
        name: name.into(),
        email: email.into(),
        role: role.into(),
        local: false,
        ..NewHubUser::default()
    }
}

/// The stable rejection code of a failed alta (`RuntimeError::Domain`), or the raw message when the
/// runtime answered with something else — the assertion then shows what it really said.
fn code_of(error: &erplora_runtime::RuntimeError) -> String {
    match error {
        erplora_runtime::RuntimeError::Domain { code, .. } => code.clone(),
        other => other.to_string(),
    }
}

#[tokio::test]
async fn an_account_user_is_created_with_an_email_and_no_pin_is_required() {
    let rt = runtime("hub-account").await;

    let id = rt
        .create_hub_user(&account("Ana Soto", "ana@example.com", "manager"))
        .await
        .expect("name + email + role is all an account user needs");

    let created = rt
        .list_hub_users()
        .await
        .unwrap()
        .into_iter()
        .find(|u| u.id == id)
        .expect("the account user is listed in Personal");
    assert_eq!(created.email, "ana@example.com");
    assert_eq!(created.role, "manager");
    assert!(created.is_active);
    assert!(
        !created.has_pin,
        "the PIN is optional: an account user signs in with their ERPlora account"
    );
    assert!(
        created.cloud_user_id.is_none(),
        "nobody has signed in yet: the link happens on their first login"
    );
}

#[tokio::test]
async fn an_account_user_without_an_email_is_rejected_with_a_reason() {
    // The mistake this closes is silent: an alta meant to be an account user that forgets the email
    // produces somebody the SaaS never invited — a ficha with no way in — and nothing on screen
    // says so. With the box off, the email IS the identity.
    let rt = runtime("hub-account").await;

    let err = rt
        .create_hub_user(&account("Ana Soto", "", "employee"))
        .await
        .unwrap_err();

    assert_eq!(code_of(&err), "hub.users.account_needs_email");
    assert!(
        rt.list_hub_users().await.unwrap().is_empty(),
        "a rejected alta creates nobody"
    );
}

#[tokio::test]
async fn the_invited_email_is_the_one_the_login_looks_for() {
    // 🔴 The alta used to write the email ONLY into `hub_user_profile`, while the whole ACCESS
    // plane reads `hub_user.email`: `get_or_link_cloud_user` (step 2, link by email),
    // `revoke_cloud_access` and the `/api/members` baja. So the invited person's first login found
    // nothing, fell through to step 3 and got a SECOND row provisioned with the least-privilege
    // default role — two identities for one person, and the role the admin granted silently lost.
    let rt = runtime("hub-account").await;
    let id = rt
        .create_hub_user(&account("Ana Soto", "ana@example.com", "manager"))
        .await
        .unwrap();

    let signed_in = rt
        .get_or_link_cloud_user(
            "cloud-9",
            "Ana Soto",
            "employee", // what the SaaS would provision a stranger with
            Some("ana@example.com"),
            None,
        )
        .await
        .expect("the invited account signs in for the first time");

    assert_eq!(signed_in.id, id, "the invitation and the login are ONE row");
    assert_eq!(
        signed_in.role, "manager",
        "the role the admin granted survives the first login"
    );
    assert_eq!(
        rt.list_hub_users().await.unwrap().len(),
        1,
        "no second identity is provisioned next to the invited one"
    );
}

#[tokio::test]
async fn an_email_this_hub_already_knows_is_never_invited_twice() {
    // The SaaS would happily take it: `POST /device/members/` upserts and answers 200. What it
    // cannot see is that the hub would end up with TWO local rows for one membership — the second
    // alta only has to use a different name to get past `ensure_name_is_free`.
    let rt = runtime("hub-account").await;
    // Stored exactly as the administrator typed it, mixed case and all — nothing normalises it on
    // the way in, so the guard has to be case-insensitive on BOTH sides or half of it is decorative.
    rt.create_hub_user(&account("Ana Soto", "Ana@Example.com", "employee"))
        .await
        .unwrap();

    for typed_again in ["ana@example.com", "ANA@EXAMPLE.COM", "Ana@Example.com"] {
        let err = rt
            .create_hub_user(&account("Ana S.", typed_again, "admin"))
            .await
            .unwrap_err();
        assert_eq!(
            code_of(&err),
            "hub.users.email_taken",
            "`{typed_again}` is the same person: an email address is not case-sensitive"
        );
    }

    let users = rt.list_hub_users().await.unwrap();
    assert_eq!(users.len(), 1, "no second identity for one email");
    assert_eq!(
        users[0].role, "employee",
        "and the refused alta grants nothing: re-inviting is not a promotion"
    );
}

#[tokio::test]
async fn a_membership_that_was_revoked_is_not_resurrected_by_the_alta() {
    // Regla D (hub#348): a deactivated row is a door somebody closed — the hub in Personal, or the
    // SaaS by revoking the membership. Typing the email again must not be the way it reopens: the
    // way back is reinstating the row, which is an explicit and audited decision. Otherwise the
    // alta is a silent un-revocation that also re-grants whatever role is typed.
    let rt = runtime("hub-account").await;
    let id = rt
        .create_hub_user(&account("Ana Soto", "ana@example.com", "employee"))
        .await
        .unwrap();
    let closed = rt
        .revoke_cloud_access("cloud-9", Some("ana@example.com"))
        .await
        .unwrap();
    assert_eq!(closed, 1, "the SaaS revoked her membership");

    let err = rt
        .create_hub_user(&account("Ana Soto Gil", "ana@example.com", "admin"))
        .await
        .unwrap_err();

    assert_eq!(code_of(&err), "hub.users.email_taken");
    let users = rt.list_hub_users().await.unwrap();
    assert_eq!(users.len(), 1, "no second identity next to the closed one");
    assert!(!users[0].is_active, "and the closed door stays closed");
    assert_eq!(users[0].role, "employee", "nothing was re-granted");

    // The way back exists and is explicit: reinstating the row the hub already has.
    let back = rt
        .update_hub_user(
            &id,
            &UpdateHubUser {
                is_active: Some(true),
                ..UpdateHubUser::default()
            },
        )
        .await
        .expect("reinstating is the door, and it is the administrator who opens it");
    assert!(back.is_active);
}

#[tokio::test]
async fn an_account_user_only_carries_a_role_the_saas_can_actually_grant() {
    // The SaaS validates the role of the invitation against its own `HUB_ROLES`
    // (`employee`/`manager`/`admin`) and answers 400 to anything else — including the legacy
    // spelling `owner`, which is never grantable because hub ownership is the account plane's
    // (ADR-0157). A module-declared role (`kitchen`, `waiter`…) is a role of THIS hub only, so an
    // alta carrying one would create a local row with an email and no membership: a person with a
    // ficha, an invitation that never went out and no way in. Refused before anything is written.
    let rt = runtime("hub-account").await;

    for refused in ["kitchen", "owner", "cashier"] {
        let err = rt
            .create_hub_user(&account("Ana Soto", "ana@example.com", refused))
            .await
            .unwrap_err();
        assert_eq!(
            code_of(&err),
            "hub.users.account_role_not_grantable",
            "`{refused}` is not a role the SaaS can put on a membership"
        );
    }
    assert!(rt.list_hub_users().await.unwrap().is_empty());

    // The three the SaaS knows go through, `admin` included: inviting an administrator is the
    // legitimate door of ADR-0157 §7, and it is the only one the hub has.
    for (name, granted) in [
        ("Ana Soto", "employee"),
        ("Luis Prat", "manager"),
        ("Marta Ruiz", "admin"),
    ] {
        rt.create_hub_user(&account(name, &format!("{granted}@example.com"), granted))
            .await
            .unwrap_or_else(|e| panic!("`{granted}` is grantable: {e}"));
    }
    assert_eq!(rt.list_hub_users().await.unwrap().len(), 3);
}

#[tokio::test]
async fn an_account_user_pin_is_optional_but_falls_under_the_same_rules_as_a_local_one() {
    // «Un usuario de cuenta que atiende la barra necesita PIN en el dispositivo compartido»
    // (hub#356). The PIN is the same credential in both altas — it is what attributes a sale to a
    // person — so it cannot be one of the ones everybody tries first, nor already be somebody
    // else's. Without this, the account alta would be the way around the guards of hub#355.
    let rt = runtime("hub-account").await;
    rt.create_hub_user(&NewHubUser {
        pin: "4821".into(),
        ..account("Ana Soto", "ana@example.com", "employee")
    })
    .await
    .expect("an account user may also work the till");

    let guessable = rt
        .create_hub_user(&NewHubUser {
            pin: "1234".into(),
            ..account("Luis Prat", "luis@example.com", "employee")
        })
        .await
        .unwrap_err();
    assert_eq!(code_of(&guessable), "hub.users.pin_too_simple");

    let shared = rt
        .create_hub_user(&NewHubUser {
            pin: "4821".into(),
            ..account("Marta Ruiz", "marta@example.com", "employee")
        })
        .await
        .unwrap_err();
    assert_eq!(code_of(&shared), "hub.users.pin_in_use");

    assert_eq!(
        rt.list_hub_users().await.unwrap().len(),
        1,
        "neither rejected alta created anybody"
    );
    // And the PIN of the one that went through actually opens the session.
    assert!(rt.verify_pin("Ana Soto", "4821").await.unwrap().is_some());
}

#[tokio::test]
async fn moving_an_email_onto_one_the_hub_already_knows_is_rejected_too() {
    // The other half of the guard, for the same reason the PIN is checked on edit (hub#355):
    // without it, the alta guard is theatre — two altas with distinct emails, then one edited onto
    // the other's, and the hub has two rows fighting over one membership.
    let rt = runtime("hub-account").await;
    rt.create_hub_user(&account("Ana Soto", "ana@example.com", "employee"))
        .await
        .unwrap();
    let luis = rt
        .create_hub_user(&account("Luis Prat", "luis@example.com", "employee"))
        .await
        .unwrap();

    let err = rt
        .update_hub_user(
            &luis,
            &UpdateHubUser {
                email: Some("ana@example.com".into()),
                ..UpdateHubUser::default()
            },
        )
        .await
        .unwrap_err();
    assert_eq!(code_of(&err), "hub.users.email_taken");

    // Re-typing your OWN email is not a clash, and the edit still goes through.
    rt.update_hub_user(
        &luis,
        &UpdateHubUser {
            email: Some("luis@example.com".into()),
            role: Some("manager".into()),
            ..UpdateHubUser::default()
        },
    )
    .await
    .expect("editing yourself does not collide with yourself");
}

#[tokio::test]
async fn editing_the_email_keeps_the_access_plane_and_the_profile_in_step() {
    // `hub_user.email` is what the login and the revocation read; the profile is what the screen
    // shows. If an edit moved only one of them the two would disagree, and the disagreement is
    // silent: the person still shows the new email in Personal while the SaaS-facing half —
    // including their baja — keeps pointing at the old one.
    let rt = runtime("hub-account").await;
    let id = rt
        .create_hub_user(&account("Ana Soto", "ana@example.com", "employee"))
        .await
        .unwrap();

    rt.update_hub_user(
        &id,
        &UpdateHubUser {
            email: Some("a.soto@example.com".into()),
            ..UpdateHubUser::default()
        },
    )
    .await
    .unwrap();

    let linked = rt
        .get_or_link_cloud_user(
            "cloud-9",
            "Ana",
            "employee",
            Some("a.soto@example.com"),
            None,
        )
        .await
        .unwrap();
    assert_eq!(linked.id, id, "the new email reaches the same row");
    assert_eq!(rt.list_hub_users().await.unwrap().len(), 1);
    assert_eq!(
        rt.user_profile(&id).await.unwrap().email,
        "a.soto@example.com",
        "and what the person sees in their own profile says the same thing"
    );
}

#[tokio::test]
async fn personal_shows_the_email_access_is_administered_by_when_the_two_disagree() {
    // They CAN disagree: `/api/profile` lets a person edit their own profile email, and that
    // endpoint touches only `hub_user_profile` — it does not (and must not) move the key their
    // membership hangs from. Personal is the administrator's screen, so it shows the one their
    // baja will actually revoke; showing the other one would let somebody quietly change the email
    // an administrator reads before deciding.
    let rt = runtime("hub-account").await;
    let id = rt
        .create_hub_user(&account("Ana Soto", "ana@example.com", "employee"))
        .await
        .unwrap();

    rt.update_user_profile(
        &id,
        &erplora_runtime::user_profile::UpdateUserProfile {
            first_name: "Ana".into(),
            last_name: "Soto".into(),
            email: "personal@gmail.com".into(),
            preferences: Default::default(),
        },
    )
    .await
    .unwrap();

    let listed = rt.list_hub_users().await.unwrap();
    assert_eq!(listed[0].email, "ana@example.com");
}

#[tokio::test]
async fn personal_shows_the_email_of_a_user_the_cloud_provisioned() {
    // 🔴 Personal read the email from `hub_user_profile` only, so the owner seeded from
    // `HUB_OWNER_EMAIL` (ADR-0157) and anybody added through `/api/members` showed **no email** on
    // screen. That is not cosmetic: the server skips the SaaS call for a row with an empty email,
    // so their baja never revoked their membership — they kept seeing this hub in their payload.
    let rt = runtime("hub-account").await;
    rt.create_login_user("owner@example.com", "admin")
        .await
        .unwrap();

    let listed = rt.list_hub_users().await.unwrap();
    assert_eq!(listed.len(), 1);
    assert_eq!(
        listed[0].email, "owner@example.com",
        "the row carries the email access is administered by"
    );
}

#[tokio::test]
async fn no_door_of_the_hub_invites_with_a_role_the_saas_would_refuse() {
    // `/api/members` is the other alta of an account user (ADR-0157 §7) and it goes through
    // `create_login_user`. Guarding only the Personal alta would leave the same broken invitation
    // one endpoint away — the same reason the PIN is checked on edit and not only on create.
    let rt = runtime("hub-account").await;

    let err = rt
        .create_login_user("chef@example.com", "kitchen")
        .await
        .unwrap_err();
    assert_eq!(code_of(&err), "hub.users.account_role_not_grantable");
    assert!(rt.list_login_users().await.unwrap().is_empty());

    rt.create_login_user("ana@example.com", "manager")
        .await
        .expect("a role the SaaS knows goes through");
}
