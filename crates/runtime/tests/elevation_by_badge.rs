//! **The manager's card approves what the manager's PIN approves** (hub#658).
//!
//! The market decision of the issue: Toast, Aloha/NCR and Square use the same credential to sign
//! in, to clock in **and to approve**. Swiping the card IS the approval. Making a manager type
//! four digits in front of the customer when they are already holding the card is friction the
//! sector removed twenty years ago.
//!
//! What does NOT change, and is the whole reason this is cheap: **the badge authorises nothing by
//! itself**. `approve_elevation` keeps asking the same two questions it asked hub#361 — is this
//! permission elevable at the counter ([`is_elevable`], rule 5) and could this person have done it
//! themselves — and the answer to both comes from the ROLE. A card is a presentation of an
//! identity, never a privilege.
//!
//! [`is_elevable`]: erplora_runtime::permissions::is_elevable
use std::path::PathBuf;

use erplora_db::{testutil::TestDb, DatabaseAdapter, Params};
use erplora_runtime::elevation::ElevationRequest;
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::{json, Value as Json};

fn params(v: Json) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn module_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_elevation")
}

const MANAGER_PIN: &str = "8317";
const MANAGER_BADGE: &str = "0009171456";
const CASHIER_BADGE: &str = "0009172208";

/// A till with a manager who carries a card and a cashier who carries one too.
async fn a_till_where_everybody_carries_a_card() -> (TestDb, Runtime) {
    let db = TestDb::new().await;
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&module_dir())
        .await
        .expect("till installs");
    let manager = rt
        .create_user("Sofía", MANAGER_PIN, "manager", None)
        .await
        .expect("the manager exists");
    rt.set_user_badge(&manager, MANAGER_BADGE).await.unwrap();
    let cashier = rt
        .create_user("Nacho", "4692", "employee", None)
        .await
        .expect("the cashier exists");
    rt.set_user_badge(&cashier, CASHIER_BADGE).await.unwrap();
    (db, rt)
}

fn cashier() -> RequestContext {
    RequestContext::new(
        "h1",
        "u-cashier",
        ["till.view_sale".to_string(), "till.add_sale".to_string()],
    )
}

fn ticket() -> Params {
    params(json!({ "label": "table 4" }))
}

fn refusal_code(e: &RuntimeError) -> String {
    match e {
        RuntimeError::Domain { code, .. } => code.clone(),
        other => panic!("expected a domain refusal, got {other:?}"),
    }
}

/// **The case the market decided.** The card is swiped in the approval dialog and the action goes
/// through, attributed to the manager exactly as their PIN would have attributed it.
#[tokio::test]
async fn swiping_the_managers_card_approves_the_action() {
    let (_db, rt) = a_till_where_everybody_carries_a_card().await;

    let by_badge = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_badge(MANAGER_BADGE, "till.sale.void", &ticket()),
        )
        .await
        .expect("the card approves");
    let by_pin = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_pin("Sofía", MANAGER_PIN, "till.sale.void", &ticket()),
        )
        .await
        .expect("and so does the PIN");

    assert_eq!(by_badge.approver_name, "Sofía");
    assert_eq!(
        by_badge.approved_by, by_pin.approved_by,
        "one identity, two presentations of it"
    );
    assert_eq!(by_badge.permission, "till.void_sale");
    assert!(!by_badge.token.is_empty());
    assert_ne!(
        by_badge.token, by_pin.token,
        "each approval is its own single-use grant"
    );
}

/// Rule 5 survives untouched: what authorises is the ROLE. The cashier's own card cannot approve
/// what the cashier's own PIN cannot approve — and the refusal is the SAME code, so nothing on the
/// screen has to learn a second vocabulary.
#[tokio::test]
async fn a_card_grants_nothing_its_holder_did_not_already_have() {
    let (_db, rt) = a_till_where_everybody_carries_a_card().await;

    let refused = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_badge(CASHIER_BADGE, "till.sale.void", &ticket()),
        )
        .await
        .expect_err("the cashier cannot approve their own void");

    assert_eq!(refusal_code(&refused), "hub.elevation.approver_cannot");
}

/// An unknown card answers exactly like an unknown name and a wrong PIN. A dialog at the counter
/// must not become a way to find out which cards this shop has issued.
#[tokio::test]
async fn an_unknown_card_is_refused_with_the_same_sentence_as_a_wrong_pin() {
    let (_db, rt) = a_till_where_everybody_carries_a_card().await;

    let refused = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_badge("4A00B7C219E3", "till.sale.void", &ticket()),
        )
        .await
        .expect_err("nobody carries that card");

    assert_eq!(refusal_code(&refused), "hub.elevation.rejected");
}

/// `admin` territory is not approved at the counter — with a card either. Otherwise the card would
/// be the way around ADR-0238 rule 5, which is exactly the shape of privilege a badge must not
/// manufacture.
#[tokio::test]
async fn a_card_does_not_open_what_belongs_to_whoever_administers_the_hub() {
    let (_db, rt) = a_till_where_everybody_carries_a_card().await;
    // `till.manage_settings` is granted to `admin` only, so it is not elevable.
    let refused = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_badge(MANAGER_BADGE, "till.settings.save", &ticket()),
        )
        .await
        .expect_err("settings are not approved at the till");

    assert_eq!(refusal_code(&refused), "hub.elevation.not_elevable");
}

/// **The trace, on the row that matters.** `_elevation_audit` already carried both attributions;
/// now it carries HOW the approver proved they were there, and WHICH card it was. That single
/// column is the only possible answer to «somebody used my card» — and no competitor records it.
#[tokio::test]
async fn the_receipt_says_the_approval_came_from_a_card_and_which_one() {
    let (db, rt) = a_till_where_everybody_carries_a_card().await;
    let token = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_badge(MANAGER_BADGE, "till.sale.void", &ticket()),
        )
        .await
        .expect("the card approves")
        .token;

    rt.execute_command(
        "till.sale.void",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the void goes through");

    let conn = db.adapter().await;
    let rows = conn
        .query(
            "SELECT created_by, approved_by, credential_kind, credential_ref \
               FROM _elevation_audit ORDER BY created_at, id",
            &Params::new(),
        )
        .await
        .expect("the elevation audit is a core table")
        .rows;

    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["created_by"].as_str().unwrap(), "u-cashier");
    assert_eq!(rows[0]["credential_kind"].as_str().unwrap(), "badge");
    let badge_ref = rows[0]["credential_ref"].as_str().unwrap();
    assert!(
        !badge_ref.is_empty(),
        "the receipt names WHICH card was swiped"
    );
    assert!(
        !badge_ref.contains(MANAGER_BADGE),
        "…by its index, never by the number printed on it"
    );
}

/// And the PIN half keeps saying so too: a receipt with an empty `credential_kind` would be a row
/// nobody can interpret afterwards.
#[tokio::test]
async fn the_receipt_of_a_pin_approval_says_pin() {
    let (db, rt) = a_till_where_everybody_carries_a_card().await;
    let token = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_pin("Sofía", MANAGER_PIN, "till.sale.void", &ticket()),
        )
        .await
        .expect("the PIN approves")
        .token;

    rt.execute_command(
        "till.sale.void",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the void goes through");

    let conn = db.adapter().await;
    let rows = conn
        .query(
            "SELECT credential_kind, credential_ref FROM _elevation_audit",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows;
    assert_eq!(rows[0]["credential_kind"].as_str().unwrap(), "pin");
    assert_eq!(rows[0]["credential_ref"].as_str().unwrap_or_default(), "");
}
