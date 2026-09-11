//! **The badge is a SIBLING of the PIN, never its replacement** (hub#658).
//!
//! The market decision published on the issue (15/08, 15 references) settles three things this
//! file is the executable form of:
//!
//!  1. **Badge and PIN are two presentations of the SAME identity.** What authorises is the
//!     ROLE, not the kind of credential — so a badge signs somebody in *and* satisfies the
//!     elevation dialog, exactly as Toast, Aloha and Square do.
//!  2. **The badge NEVER replaces the PIN.** Square does not allow it, and the Lightspeed
//!     L-Series is the cautionary tale: an irrevocable card, no documented recovery, product
//!     discontinued. Revoking a badge must leave the PIN untouched, and going back to PIN-only
//!     has to be possible at any moment.
//!  3. **The trace is the differentiator.** `credential_kind` + the badge id, on every login and
//!     on every `_elevation_audit` row. No competitor records it, and it is the only possible
//!     answer to «somebody used my card».
//!
//! And one property that is about this codebase rather than the market: the lookup is by
//! **deterministic index** (HMAC with the hub's own key) and *then* a verification, NOT the
//! row-by-row argon2 scan of [`identity::pin_is_taken`]. With four digits a linear scan is
//! affordable; with a high-entropy badge it is one argon2 per tap at the login door — a denial of
//! service against the till itself.
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::identity;
use erplora_runtime::Runtime;
use serde_json::json;

/// A hub running on `test_db`, booted the way the server boots it.
async fn hub_on(test_db: &TestDb, hub_id: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn a_hub() -> (TestDb, Runtime) {
    let test_db = TestDb::new().await;
    let rt = hub_on(&test_db, "hub-badge").await;
    (test_db, rt)
}

/// A real badge: what an EM4100/MIFARE reader types as a keyboard burst. High entropy on purpose —
/// that is precisely what makes the row-by-row argon2 scan unaffordable.
const ANA_BADGE: &str = "0009171456";
const SOFIA_BADGE: &str = "4A00B7C219E3";

// ── 1 · The badge resolves the whole identity ────────────────────────────────────────────────

/// The pinpad resolves NAME + PIN; a badge resolves the person on its own. That is the point: it
/// replaces the *pair*, never the PIN alone.
#[tokio::test]
async fn a_badge_signs_in_its_owner_without_anybody_tapping_a_name() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();

    let matched = rt
        .verify_badge(ANA_BADGE)
        .await
        .unwrap()
        .expect("the badge opens Ana's identity");

    assert_eq!(matched.user.id, ana);
    assert_eq!(matched.user.name, "Ana");
    assert_eq!(matched.user.role, "employee");
    // The badge id that travels to the trace is the INDEX, never the number on the card: it
    // identifies WHICH card was tapped without the audit trail becoming a list of live credentials.
    assert!(!matched.badge_index.is_empty());
    assert!(!matched.badge_index.contains(ANA_BADGE));
}

#[tokio::test]
async fn an_unknown_badge_opens_nothing() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();

    assert!(rt.verify_badge("999999999").await.unwrap().is_none());
    // …and neither does the empty string, which is what every row without a badge stores.
    assert!(rt.verify_badge("").await.unwrap().is_none());
}

/// A deactivated row is a door the hub closed. The card in the drawer must not reopen it — same
/// rule the PIN already had, and the reason revocation is «deactivate», not «delete».
#[tokio::test]
async fn the_badge_of_a_deactivated_person_opens_nothing() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();
    rt.update_hub_user(
        &ana,
        &erplora_runtime::hub_users::UpdateHubUser {
            is_active: Some(false),
            ..Default::default()
        }, 0,)
    .await
    .unwrap();

    assert!(rt.verify_badge(ANA_BADGE).await.unwrap().is_none());
}

// ── 2 · The lookup is by INDEX, not a row-by-row argon2 scan ─────────────────────────────────

/// The DoS the issue names explicitly. `pin_is_taken` reads **every** row with a PIN and runs
/// argon2 on each; copied to a badge that is what every tap at the login door would cost.
///
/// What is asserted is the shape that makes it impossible: the stored `badge_index` is a
/// deterministic function of the badge, so a lookup narrows to **one row** in SQL before any hash
/// is verified. The neighbours are alive and hold badges of their own while it runs — a test with
/// a single badge holder passes just as well against a linear scan.
#[tokio::test]
async fn a_badge_lookup_narrows_to_one_row_before_a_single_hash_is_verified() {
    let (db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();
    for n in 0..12 {
        let other = rt
            .create_user(
                &format!("Colleague {n}"),
                &format!("47{n:02}"),
                "employee",
                None,
            )
            .await
            .unwrap();
        rt.set_user_badge(&other, &format!("0009171{n:03}"))
            .await
            .unwrap();
    }

    let key = rt.badge_index_key().await.unwrap();
    let index = identity::badge_index(&key, ANA_BADGE);
    let adapter = db.adapter().await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("hub-badge"));
    p.insert("badge_index".into(), json!(index));
    let res = adapter
        .query(
            "SELECT id FROM hub_user WHERE hub_id = :hub_id AND badge_index = :badge_index",
            &p,
        )
        .await
        .unwrap();

    assert_eq!(
        res.rows.len(),
        1,
        "the index must select exactly the badge's owner"
    );
    assert_eq!(res.rows[0]["id"].as_str().unwrap(), ana);
}

/// The index is a **keyed** digest, not a plain hash: two hubs sharing a badge number produce two
/// different indexes, and the number itself is not recoverable from the column.
#[tokio::test]
async fn the_index_is_keyed_per_hub_and_never_the_badge_in_clear() {
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let theirs = hub_on(&test_db, "hub-theirs").await;

    let my_key = mine.badge_index_key().await.unwrap();
    let their_key = theirs.badge_index_key().await.unwrap();
    assert_ne!(my_key, their_key, "each hub keys its own index");

    let my_index = identity::badge_index(&my_key, ANA_BADGE);
    assert_ne!(my_index, identity::badge_index(&their_key, ANA_BADGE));
    assert!(!my_index.contains(ANA_BADGE));
    // Deterministic, or the index would not be an index.
    assert_eq!(my_index, identity::badge_index(&my_key, ANA_BADGE));
}

/// The key is minted once and **kept**: a key that changed would orphan every badge in the hub in
/// silence — every card stops working and nothing says why.
#[tokio::test]
async fn the_index_key_is_minted_once_and_survives() {
    let (_db, rt) = a_hub().await;
    let first = rt.badge_index_key().await.unwrap();
    let second = rt.badge_index_key().await.unwrap();
    assert_eq!(first, second);
}

/// A badge of the business next door opens nothing here — the same scoping `hub_user` got in v42,
/// now for the column an attacker would aim at.
#[tokio::test]
async fn a_badge_of_the_business_next_door_opens_nothing_here() {
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let neighbour = hub_on(&test_db, "hub-neighbour").await;
    let theirs = neighbour
        .create_user("Ana", "4729", "admin", None)
        .await
        .unwrap();
    neighbour.set_user_badge(&theirs, ANA_BADGE).await.unwrap();
    let mine_user = mine
        .create_user("Bruno", "5183", "employee", None)
        .await
        .unwrap();
    mine.set_user_badge(&mine_user, SOFIA_BADGE).await.unwrap();

    assert!(mine.verify_badge(ANA_BADGE).await.unwrap().is_none());
    // …and the neighbour is untouched: their badge still opens their hub.
    assert_eq!(
        neighbour
            .verify_badge(ANA_BADGE)
            .await
            .unwrap()
            .unwrap()
            .user
            .id,
        theirs
    );
}

// ── 3 · The badge NEVER replaces the PIN ─────────────────────────────────────────────────────

/// Enrolling a badge leaves the PIN exactly where it was. Square does not let a badge stand alone,
/// and the PIN is the way back when the card is lost.
#[tokio::test]
async fn enrolling_a_badge_leaves_the_pin_working() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();

    assert_eq!(rt.verify_pin("Ana", "4729").await.unwrap().unwrap().id, ana);
}

/// **Independent revocation** — the answer to «what if it is lost». Removing the badge does not
/// touch the PIN, and going back to PIN-only is always possible.
#[tokio::test]
async fn revoking_the_badge_does_not_touch_the_pin() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();

    rt.set_user_badge(&ana, "").await.unwrap();

    assert!(
        rt.verify_badge(ANA_BADGE).await.unwrap().is_none(),
        "the lost card is dead"
    );
    assert_eq!(
        rt.verify_pin("Ana", "4729").await.unwrap().unwrap().id,
        ana,
        "and its owner still gets in with the PIN they always had"
    );
    // A new card can be issued straight away; the old one stays dead.
    rt.set_user_badge(&ana, SOFIA_BADGE).await.unwrap();
    assert_eq!(
        rt.verify_badge(SOFIA_BADGE).await.unwrap().unwrap().user.id,
        ana
    );
    assert!(rt.verify_badge(ANA_BADGE).await.unwrap().is_none());
}

/// Removing the PIN does not remove the badge either: they are siblings, and neither owns the
/// other. (Being able to leave somebody badge-only is a decision for the alta screen, not
/// something the storage layer should silently undo.)
#[tokio::test]
async fn changing_the_pin_does_not_touch_the_badge() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();

    rt.set_pin(&ana, Some("4729"), "5183").await.unwrap();

    assert_eq!(
        rt.verify_badge(ANA_BADGE).await.unwrap().unwrap().user.id,
        ana
    );
}

/// Two people behind one card is the badge twin of the PIN clash, and worse: a card is lent. The
/// guard is a single indexed read, not a scan.
#[tokio::test]
async fn a_badge_that_already_belongs_to_somebody_is_refused() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    let bruno = rt
        .create_user("Bruno", "5183", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();

    assert!(rt.badge_is_taken(ANA_BADGE, Some(&bruno)).await.unwrap());
    // Re-writing your own badge is not a clash.
    assert!(!rt.badge_is_taken(ANA_BADGE, Some(&ana)).await.unwrap());
    assert!(!rt.badge_is_taken(SOFIA_BADGE, None).await.unwrap());
}

// ── 4 · The trace ────────────────────────────────────────────────────────────────────────────

/// **The criterion the issue says is worth the most.** Every session records HOW the identity was
/// proven and, when it was a card, WHICH one. Without this column «somebody used my card» is
/// structurally unanswerable, which is where every competitor is.
#[tokio::test]
async fn every_session_records_the_credential_that_opened_it() {
    let (db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();
    let matched = rt.verify_badge(ANA_BADGE).await.unwrap().unwrap();

    let by_badge = rt
        .create_session_with_credential(
            &ana,
            3600,
            Some("till-1"),
            &identity::Credential::badge(&matched.badge_index),
        )
        .await
        .unwrap();
    let by_pin = rt
        .create_session_with_credential(&ana, 3600, Some("till-1"), &identity::Credential::pin())
        .await
        .unwrap();

    let adapter = db.adapter().await;
    let read = |token: String| {
        let adapter = &adapter;
        async move {
            let mut p = Params::new();
            p.insert("token".into(), json!(token));
            let res = adapter
                .query(
                    "SELECT credential_kind, credential_ref FROM hub_session WHERE token = :token",
                    &p,
                )
                .await
                .unwrap();
            (
                res.rows[0]["credential_kind"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string(),
                res.rows[0]["credential_ref"]
                    .as_str()
                    .unwrap_or_default()
                    .to_string(),
            )
        }
    };

    assert_eq!(
        read(by_badge).await,
        ("badge".to_string(), matched.badge_index.clone())
    );
    assert_eq!(read(by_pin).await, ("pin".to_string(), String::new()));
}

// ── 5 · The badge can never become the ONLY way in ───────────────────────────────────────────

/// **Square does not allow it, and Lightspeed L-Series is why.** Leaving somebody with a badge and
/// nothing else is exactly the state that made that product's card irrecoverable: lose the card and
/// the person is locked out of their own till, with no gesture on any screen that lets them back.
///
/// So the refusal is on the EDIT, at the moment the last fallback would go, and it names the
/// alternative (remove the badge first). It is not a rule about badges being dangerous; it is the
/// rule that keeps «going back to PIN-only is always possible» true.
#[tokio::test]
async fn the_pin_cannot_be_removed_from_somebody_whose_only_other_way_in_is_a_badge() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();

    let refused = rt
        .update_hub_user(
            &ana,
            &erplora_runtime::hub_users::UpdateHubUser {
                pin: Some(String::new()),
                ..Default::default()
            }, 0,)
        .await
        .expect_err("that would leave the card as her only credential");

    match refused {
        erplora_runtime::RuntimeError::Domain { code, .. } => {
            assert_eq!(code, "hub.users.badge_without_fallback");
        }
        other => panic!("expected a domain refusal, got {other:?}"),
    }
    // Nothing was written: she still gets in with the PIN she always had.
    assert!(rt.verify_pin("Ana", "4729").await.unwrap().is_some());
}

/// …and the way out is the one the refusal names: **remove the badge, then the PIN**. Both in one
/// edit is fine too — what is refused is the resulting state, not the order of the fields.
#[tokio::test]
async fn removing_the_badge_and_the_pin_together_is_allowed() {
    let (_db, rt) = a_hub().await;
    let ana = rt
        .create_user("Ana", "4729", "employee", None)
        .await
        .unwrap();
    rt.set_user_badge(&ana, ANA_BADGE).await.unwrap();

    rt.update_hub_user(
        &ana,
        &erplora_runtime::hub_users::UpdateHubUser {
            pin: Some(String::new()),
            badge: Some(String::new()),
            ..Default::default()
        }, 0,)
    .await
    .expect("a person who signs in nowhere is a legitimate record");

    assert!(rt.verify_badge(ANA_BADGE).await.unwrap().is_none());
    assert!(rt.verify_pin("Ana", "4729").await.unwrap().is_none());
}

/// The guard is about the FALLBACK, not about the PIN: somebody who signs in with their ERPlora
/// account keeps a way in whatever happens to the card, so their PIN can go.
#[tokio::test]
async fn an_account_user_may_drop_their_pin_while_keeping_a_badge() {
    let (_db, rt) = a_hub().await;
    let sofia = rt
        .create_hub_user(&erplora_runtime::hub_users::NewHubUser {
            name: "Sofía".into(),
            email: "sofia@example.com".into(),
            role: "manager".into(),
            pin: "8317".into(),
            badge: SOFIA_BADGE.into(),
            local: false,
        }, 0)
        .await
        .unwrap();

    rt.update_hub_user(
        &sofia,
        &erplora_runtime::hub_users::UpdateHubUser {
            pin: Some(String::new()),
            ..Default::default()
        }, 0,)
    .await
    .expect("her account is the fallback the badge needs");

    assert!(rt.verify_badge(SOFIA_BADGE).await.unwrap().is_some());
}
