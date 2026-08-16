//! hub#361 (paso 2b, 2/4) — the PIN is verified in the RUNTIME, and what it buys is **one action**.
//!
//! Rule 2 of the design says the PIN never gets checked by the client; rule 4 says the approval is
//! *por acción*, "ventana de segundos, y se acabó" — never a manager MODE that stays open when the
//! manager walks off to the kitchen. Those two sentences decide everything this file pins down:
//!
//! - **One execution, not a session.** The approval is spent by the action it authorised. Ten
//!   actions need ten approvals; there is no interval during which the till is simply open.
//! - **Bound to THE action.** Approving «void this €4 ticket» cannot void a €400 one: the grant
//!   names the command AND fingerprints the payload the manager was shown.
//! - **It lives in the runtime's memory and dies with it.** An approval is a person standing at the
//!   till right now; one that survived a restart would be a credential outliving the very event
//!   that should have cleared it.
//! - **It cannot be replayed.** Spent once, expired by a ceiling, bound to the cashier who asked,
//!   and the token itself is an opaque secret the client can neither guess nor mint.
//!
//! Plus the two holes hub#360 left open on purpose and this issue closes: a **machine principal**
//! (API key) is never invited to elevate and can never be approved, and the approval never widens
//! anything beyond the single gate it was spent on.
use std::path::PathBuf;

use erplora_db::{testutil::TestDb, Params};
use erplora_runtime::elevation::ElevationRequest;
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn module_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_elevation")
}

/// The manager's PIN. Four digits typed in front of customers — the whole point of the design.
const MANAGER_PIN: &str = "8317";
const CASHIER_PIN: &str = "4692";

/// A hub with the `till` fixture, a manager who can approve and a cashier who cannot.
/// Returns the `TestDb` too, so a test can build a SECOND runtime over the same data (restart).
async fn fresh_hub() -> (TestDb, Runtime) {
    let db = TestDb::new().await;
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&module_dir())
        .await
        .expect("till installs");
    rt.create_user("Sofía", MANAGER_PIN, "manager", None)
        .await
        .expect("the manager exists");
    rt.create_user("Nacho", CASHIER_PIN, "employee", None)
        .await
        .expect("the cashier exists");
    (db, rt)
}

/// The cashier at the till: everything `employee` is granted, and not a permission more.
fn cashier() -> RequestContext {
    RequestContext::new(
        "h1",
        "u-cashier",
        ["till.view_sale".to_string(), "till.add_sale".to_string()],
    )
}

fn admin() -> RequestContext {
    RequestContext::new("h1", "u-owner", ["*".to_string()])
}

/// An integration: the same permissions as the cashier, but nobody is standing at it.
fn integration() -> RequestContext {
    RequestContext::new(
        "h1",
        "apikey:k1",
        ["till.view_sale".to_string(), "till.add_sale".to_string()],
    )
    .as_machine()
}

fn ticket() -> Params {
    params(json!({ "label": "table 4" }))
}

fn other_ticket() -> Params {
    params(json!({ "label": "table 11" }))
}

async fn sales(rt: &Runtime) -> Vec<serde_json::Value> {
    rt.execute_query("till.sales.list", &Params::new(), &admin())
        .await
        .expect("the admin may always read")
}

async fn sales_count(rt: &Runtime) -> usize {
    sales(rt).await.len()
}

/// The manager approves `command(payload)` for `requester`, and hands back the opaque token.
async fn approve(
    rt: &Runtime,
    requester: &RequestContext,
    command: &str,
    payload: &Params,
) -> String {
    rt.approve_elevation(
        requester,
        ElevationRequest::with_pin("Sofía", MANAGER_PIN, command, payload),
    )
    .await
    .expect("the manager approves")
    .token
}

// ─────────────────────────────────────────────────────────────────────────────
// Rule 2 — the PIN is verified in the RUNTIME, and it is what opens the action
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_managers_pin_lets_the_refused_action_through() {
    let (_db, rt) = fresh_hub().await;

    // Without approval: the refusal hub#360 introduced.
    let err = rt
        .execute_command("till.sale.take_payment", &ticket(), &cashier())
        .await
        .expect_err("a cashier does not take payment on their own");
    assert!(
        matches!(&err, RuntimeError::RequiresElevation { permission } if permission == "till.take_payment")
    );
    assert_eq!(sales_count(&rt).await, 0);

    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved action goes through");

    assert_eq!(sales_count(&rt).await, 1, "the sale the manager approved");
}

#[tokio::test]
async fn a_wrong_pin_approves_nothing() {
    let (_db, rt) = fresh_hub().await;

    let err = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_pin("Sofía", "0000", "till.sale.take_payment", &ticket()),
        )
        .await
        .expect_err("four wrong digits authorise nothing");

    // One code for «those digits do not approve this», whether the name is unknown, the PIN is
    // wrong or the person is deactivated: a dialog at the counter must not become an oracle that
    // tells a stranger which names exist in this hub.
    assert!(
        matches!(&err, RuntimeError::Domain { code, .. } if code == "hub.elevation.rejected"),
        "got {err:?}"
    );
    let unknown = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_pin("Nobody", MANAGER_PIN, "till.sale.take_payment", &ticket()),
        )
        .await
        .expect_err("an unknown name approves nothing either");
    assert_eq!(
        format!("{err:?}"),
        format!("{unknown:?}"),
        "a wrong PIN and an unknown name must be indistinguishable"
    );
}

#[tokio::test]
async fn only_somebody_who_could_do_it_themselves_can_approve_it() {
    let (_db, rt) = fresh_hub().await;

    // The cashier's own PIN is a valid PIN — and approves nothing, because `employee` does not
    // hold `till.take_payment`. You cannot approve what you could not do.
    let err = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_pin("Nacho", CASHIER_PIN, "till.sale.take_payment", &ticket()),
        )
        .await
        .expect_err("a cashier cannot approve their own way past the gate");

    assert!(
        matches!(&err, RuntimeError::Domain { code, .. } if code == "hub.elevation.approver_cannot"),
        "got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0);
}

#[tokio::test]
async fn an_admin_only_permission_is_never_approved_by_pin() {
    let (_db, rt) = fresh_hub().await;

    // Rule 5: `till.manage_settings` reaches `admin` only through its `"*"`. There is no manager
    // level to step up to, so the door does not exist — not even for somebody who holds it.
    let err = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_pin("Sofía", MANAGER_PIN, "till.settings.save", &ticket()),
        )
        .await
        .expect_err("administering the till is not approved at the counter");

    assert!(
        matches!(&err, RuntimeError::Domain { code, .. } if code == "hub.elevation.not_elevable"),
        "got {err:?}"
    );
}

#[tokio::test]
async fn an_internal_command_is_not_approvable_either() {
    let (_db, rt) = fresh_hub().await;

    // `till._settle` is internal: the dispatcher refuses it from outside BEFORE looking at the
    // permission (ADR-0166), so minting an approval for it would hand out a token that can never
    // be spent — and advertise a door the dialog cannot open.
    let err = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_pin("Sofía", MANAGER_PIN, "till._settle", &ticket()),
        )
        .await
        .expect_err("an internal command is invisible from outside");

    assert!(
        matches!(&err, RuntimeError::InternalCommand(c) if c == "till._settle"),
        "got {err:?}"
    );
}

#[tokio::test]
async fn nothing_is_approved_for_somebody_who_already_holds_the_permission() {
    let (_db, rt) = fresh_hub().await;

    // The manager running their own till needs no approval. Minting one anyway would leave a
    // spendable credential lying around for an action that never needed it.
    let err = rt
        .approve_elevation(
            &admin(),
            ElevationRequest::with_pin("Sofía", MANAGER_PIN, "till.sale.take_payment", &ticket()),
        )
        .await
        .expect_err("there is nothing to approve");

    assert!(
        matches!(&err, RuntimeError::Domain { code, .. } if code == "hub.elevation.not_required"),
        "got {err:?}"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Rule 3's seam — the runtime knows WHO approved, and the SQL can see it
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_approved_action_carries_who_approved_it_alongside_who_ran_it() {
    let (_db, rt) = fresh_hub().await;
    let approval = rt
        .approve_elevation(
            &cashier(),
            ElevationRequest::with_pin("Sofía", MANAGER_PIN, "till.sale.take_payment", &ticket()),
        )
        .await
        .expect("the manager approves");
    assert_eq!(approval.permission, "till.take_payment");
    assert_eq!(approval.approver_name, "Sofía");
    assert!(
        !approval.approved_by.is_empty(),
        "the manager's hub_user.id"
    );

    // The cashier's own action first: nobody approved it, so the field stays empty. That empty is
    // the whole reason the two are separate — «who was at the till» and «who authorised» are
    // different questions, and collapsing them loses one of the two.
    rt.execute_command("till.sale.create", &ticket(), &cashier())
        .await
        .expect("the cashier opens the ticket");
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&approval.token),
    )
    .await
    .expect("the approved payment");

    let rows = sales(&rt).await;
    assert_eq!(rows.len(), 2);
    for row in &rows {
        assert_eq!(
            row["created_by"], "u-cashier",
            "both are attributed to whoever was at the till"
        );
    }
    assert_eq!(rows[0]["approved_by"], "", "nobody approved the plain one");
    assert_eq!(
        rows[1]["approved_by"], approval.approved_by,
        "the elevated one names the manager who authorised it"
    );
    // …and the SQL saw it because the dispatcher put it there, not because the caller sent it:
    // hub#362 turns `:approved_by` into the row contract every module table carries.
}

#[tokio::test]
async fn a_caller_cannot_stamp_an_approver_by_sending_one() {
    let (_db, rt) = fresh_hub().await;

    // `approved_by` is a system param: whatever the payload says about it is overwritten by what
    // the dispatcher actually did — which, here, is nothing.
    rt.execute_command(
        "till.sale.create",
        &params(json!({ "label": "table 4", "approved_by": "u-manager" })),
        &cashier(),
    )
    .await
    .expect("the cashier opens the ticket");

    assert_eq!(
        sales(&rt).await[0]["approved_by"],
        "",
        "an unapproved action stays unapproved however the payload is dressed up"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Rule 4 — the window: ONE action, never a manager mode
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_approval_is_spent_by_the_action_it_authorised() {
    let (_db, rt) = fresh_hub().await;
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the first, approved payment");

    // THE decision of this issue. A time window would leave the till open all afternoon: the
    // manager approves one €4 refund at 13:05 and the cashier keeps refunding until 13:07. The
    // approval authorises the action it was asked for, and then it is gone — even for the very
    // same action, with the very same token, one instant later.
    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &ticket(),
            &cashier().with_elevation_token(&token),
        )
        .await
        .expect_err("a second payment needs a second approval");

    assert!(
        matches!(&err, RuntimeError::RequiresElevation { permission } if permission == "till.take_payment")
    );
    assert_eq!(
        sales_count(&rt).await,
        1,
        "exactly the one that was approved"
    );
}

#[tokio::test]
async fn an_approval_does_not_authorise_a_different_ticket() {
    let (_db, rt) = fresh_hub().await;
    // Approved: «take payment for table 4».
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &other_ticket(),
            &cashier().with_elevation_token(&token),
        )
        .await
        .expect_err("that is not the ticket the manager was shown");

    assert!(
        matches!(&err, RuntimeError::RequiresElevation { .. }),
        "got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0, "nothing ran");

    // And the grant survives the mismatch: the cashier retrying with the RIGHT ticket still works.
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved ticket still goes through");
    assert_eq!(sales_count(&rt).await, 1);
}

#[tokio::test]
async fn an_approval_does_not_authorise_a_different_command() {
    let (_db, rt) = fresh_hub().await;
    // Approved: take the payment. Both commands are manager-level and both need approval, so
    // nothing but the binding to the command name keeps one from paying for the other.
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    let err = rt
        .execute_command(
            "till.sale.void",
            &ticket(),
            &cashier().with_elevation_token(&token),
        )
        .await
        .expect_err("voiding was never approved");

    assert!(
        matches!(&err, RuntimeError::RequiresElevation { permission } if permission == "till.void_sale")
    );
    assert_eq!(sales_count(&rt).await, 0);
}

#[tokio::test]
async fn an_approval_belongs_to_the_cashier_who_asked_for_it() {
    let (_db, rt) = fresh_hub().await;
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    // Another till, another person, same action. A token that travelled (a shared browser, a log,
    // a screenshot) must not authorise anybody else — the approval names WHO it was granted to,
    // which is also what makes the double attribution of hub#362 mean anything.
    let somebody_else = RequestContext::new(
        "h1",
        "u-other-cashier",
        ["till.view_sale".to_string(), "till.add_sale".to_string()],
    );
    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &ticket(),
            &somebody_else.with_elevation_token(&token),
        )
        .await
        .expect_err("the approval was not for them");

    assert!(
        matches!(&err, RuntimeError::RequiresElevation { .. }),
        "got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0);
}

#[tokio::test]
async fn an_approval_does_not_survive_a_restart_of_the_runtime() {
    let db = TestDb::new().await;
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&module_dir()).await.unwrap();
    rt.create_user("Sofía", MANAGER_PIN, "manager", None)
        .await
        .unwrap();
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;
    drop(rt);

    // Same database, new process. The approval is deliberately NOT persisted: it authorises what
    // is happening at the counter right now, and a grant that outlived a redeploy would be a
    // credential surviving the one event that should have cleared it (and would travel in
    // backups and exports, which is nonsense for a step-up).
    let mut restarted = Runtime::with_hub_id(Box::new(db.adapter().await), "h1");
    restarted.ensure_system_tables().await.unwrap();
    restarted.install_from_dir(&module_dir()).await.unwrap();

    let err = restarted
        .execute_command(
            "till.sale.take_payment",
            &ticket(),
            &cashier().with_elevation_token(&token),
        )
        .await
        .expect_err("the approval died with the process that granted it");

    assert!(
        matches!(&err, RuntimeError::RequiresElevation { .. }),
        "got {err:?}"
    );
    assert_eq!(sales_count(&restarted).await, 0);
}

// ─────────────────────────────────────────────────────────────────────────────
// The client decides nothing — it never did, and an approval does not change that
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_token_the_runtime_never_minted_authorises_nothing() {
    let (_db, rt) = fresh_hub().await;

    for forged in ["", "approved", "0".repeat(64).as_str()] {
        let err = rt
            .execute_command(
                "till.sale.take_payment",
                &ticket(),
                &cashier().with_elevation_token(forged),
            )
            .await
            .expect_err("a token is a reference to a grant the runtime holds, not a claim");
        assert!(
            matches!(&err, RuntimeError::RequiresElevation { .. }),
            "got {err:?}"
        );
    }
    assert_eq!(sales_count(&rt).await, 0);
}

#[tokio::test]
async fn a_real_token_smuggled_in_the_payload_grants_nothing() {
    let (_db, rt) = fresh_hub().await;
    // A GENUINE approval — minted by the manager, for this cashier, this command and (almost)
    // this payload — presented where it must never be read from. The body of a command is
    // caller-controlled data that gets validated, defaulted and bound into SQL; if authority
    // could ride in it, every command in the hub would be an authorisation surface.
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &params(json!({ "label": "table 4", "elevation_token": token })),
            &cashier(),
        )
        .await
        .expect_err("the payload is data, never a credential");

    assert!(
        matches!(&err, RuntimeError::RequiresElevation { .. }),
        "got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0, "nothing ran");

    // …and the approval was not spent by the attempt: it is still the cashier's, through the
    // door it was meant for.
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the header is the only door");
    assert_eq!(sales_count(&rt).await, 1);
}

#[tokio::test]
async fn the_payload_still_grants_nothing_now_that_elevation_can_grant() {
    let (_db, rt) = fresh_hub().await;

    // Everything a hostile client would try once it learns the word «elevation» — including a
    // token field inside the payload, which is exactly where it must NOT be read from.
    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &params(json!({
                "label": "table 4",
                "requires_elevation": false,
                "elevated": true,
                "elevation_token": "whatever",
                "elevation": { "approved": true, "pin": MANAGER_PIN },
                "approved_by": "u-manager",
                "permissions": ["*"],
                "role": "admin"
            })),
            &cashier(),
        )
        .await
        .expect_err("a payload never grants a permission");

    assert!(
        matches!(&err, RuntimeError::RequiresElevation { .. }),
        "got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0, "nothing ran");
}

#[tokio::test]
async fn the_runtimes_own_doors_never_spend_an_approval() {
    let (_db, rt) = fresh_hub().await;
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    // The internal entrypoint — the same door the Outbox relay and the scheduler use — is handed
    // no approvals at all, so a context carrying a genuine token gets nothing extra through it.
    // An approval is a person authorising an action at the counter; the runtime does not approve
    // things to itself, and a listener re-running a command must not inherit somebody's PIN.
    let err = rt
        .execute_command_internal("till.sale.take_payment", &ticket(), &cashier())
        .await
        .expect_err("no permission, and nothing to spend");
    assert!(
        matches!(&err, RuntimeError::RequiresElevation { .. }),
        "got {err:?}"
    );

    let err = rt
        .execute_command_internal(
            "till.sale.take_payment",
            &ticket(),
            &cashier().with_elevation_token(&token),
        )
        .await
        .expect_err("the token buys nothing on the internal door");
    assert!(
        matches!(&err, RuntimeError::RequiresElevation { .. }),
        "got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0);

    // …and the approval was not burnt on the way: it is still the cashier's to spend outside.
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approval survived the internal attempts");
}

// ─────────────────────────────────────────────────────────────────────────────
// The machine principal (hub#360 left this open on purpose)
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn an_integration_is_never_invited_to_ask_the_manager() {
    let (_db, rt) = fresh_hub().await;

    // An API key has no human standing at it. Telling a nightly job to «ask a manager for their
    // PIN» is an instruction nobody can follow — and now that elevation GRANTS, a machine that
    // could be elevated would be a credential with a second, quieter way in.
    let err = rt
        .execute_command("till.sale.take_payment", &ticket(), &integration())
        .await
        .expect_err("the integration lacks the permission");

    assert!(
        matches!(&err, RuntimeError::PermissionDenied(p) if p == "till.take_payment"),
        "a machine principal gets the flat refusal, got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0);
}

#[tokio::test]
async fn a_machine_principal_cannot_be_approved_at_all() {
    let (_db, rt) = fresh_hub().await;

    let err = rt
        .approve_elevation(
            &integration(),
            ElevationRequest::with_pin("Sofía", MANAGER_PIN, "till.sale.take_payment", &ticket()),
        )
        .await
        .expect_err("there is nobody at the till to approve for");

    assert!(
        matches!(&err, RuntimeError::Domain { code, .. } if code == "hub.elevation.machine_principal"),
        "got {err:?}"
    );
}

#[tokio::test]
async fn an_approval_granted_to_a_person_cannot_be_spent_by_an_integration() {
    let (_db, rt) = fresh_hub().await;
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    // Even holding a genuine token: a machine principal never elevates, so it never reaches the
    // place where a grant is spent.
    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &ticket(),
            &integration().with_elevation_token(&token),
        )
        .await
        .expect_err("still a flat refusal");

    assert!(
        matches!(&err, RuntimeError::PermissionDenied(p) if p == "till.take_payment"),
        "got {err:?}"
    );
    assert_eq!(sales_count(&rt).await, 0);

    // …and the grant is untouched: a machine must not be able to burn somebody's approval either.
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the cashier's approval is still theirs to spend");
}

// ─────────────────────────────────────────────────────────────────────────────
// What must NOT change
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_query_is_still_refused_flat_even_holding_an_approval() {
    let (_db, rt) = fresh_hub().await;
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    // `till.reports.revenue` is gated by the very permission that was approved. Reads stay out of
    // elevation (hub#360, rule 3): a PIN that unlocks a REPORT leaves no `approved_by` trace and
    // would quietly turn the manager's PIN into a see-everything key.
    let err = rt
        .execute_query(
            "till.reports.revenue",
            &Params::new(),
            &cashier().with_elevation_token(&token),
        )
        .await
        .expect_err("the cashier may not read the revenue report");

    assert!(
        matches!(&err, RuntimeError::PermissionDenied(p) if p == "till.take_payment"),
        "got {err:?}"
    );
}

#[tokio::test]
async fn a_command_the_cashier_may_run_never_touches_the_grant() {
    let (_db, rt) = fresh_hub().await;
    let token = approve(&rt, &cashier(), "till.sale.take_payment", &ticket()).await;

    // Opening a ticket is theirs to do, so the gate passes and the approval is not consulted —
    // let alone consumed. Otherwise a cashier could burn a manager's approval by accident.
    rt.execute_command(
        "till.sale.create",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the cashier opens the ticket as before");

    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approval is still spendable");
    assert_eq!(sales_count(&rt).await, 2);
}
