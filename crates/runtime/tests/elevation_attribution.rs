//! hub#362 (paso 2b, 3/4) — **double attribution**: who was at the till AND who authorised.
//!
//! Rule 3 of the PLAN is the one that gives the whole mechanism its value. `created_by` is the
//! cashier who was standing at the till; `approved_by` is the manager who stepped up. Keep only
//! the manager and you lose who was working; keep only the cashier and the approval leaves no
//! trace at all — which is the same as not having asked for a PIN.
//!
//! hub#361 exposed the manager as the system parameter `:approved_by`, so a module's SQL *can*
//! bind it. That is where this issue starts, and the question it answers is **who guarantees the
//! record**:
//!
//! - If the trace lived only in the module's own column, then a module that never declares it
//!   loses the attribution **in silence**. Not hypothetically: of the 24 modules in the catalogue,
//!   **none** declares an `approved_by` for elevation today. Worse, the party that decides is the
//!   module author — the one with the least reason to record that their own sensitive command was
//!   waved through, and the ability to omit it without anything failing.
//! - So the **runtime** writes the record, in a core table, the moment it spends the grant. It is
//!   the only component that knows an approval happened at all. Same shape as
//!   [ADR-0238](hub#360): *a manifest coins no privilege* — and, symmetrically, a manifest cannot
//!   drop the audit trail either.
//!
//! The module column stays as optional enrichment (a ticket that wants to print «approved by
//! Sofía» still binds `:approved_by`), but nothing about the audit depends on it any more.
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
const CASHIER_PIN: &str = "4692";

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

fn ticket() -> Params {
    params(json!({ "label": "table 4" }))
}

/// The manager approves `command(payload)` for the cashier, and hands back the opaque token.
async fn approve(rt: &Runtime, command: &str, payload: &Params) -> String {
    rt.approve_elevation(
        &cashier(),
        ElevationRequest::with_pin("Sofía", MANAGER_PIN, command, payload),
    )
    .await
    .expect("the manager approves")
    .token
}

/// `hub_user.id` of the manager, as the runtime knows it — the value the record must carry.
async fn manager_id(rt: &Runtime) -> String {
    rt.approve_elevation(
        &cashier(),
        ElevationRequest::with_pin("Sofía", MANAGER_PIN, "till.sale.take_payment", &ticket()),
    )
    .await
    .expect("the manager approves")
    .approved_by
}

/// Everything the runtime recorded, oldest first. Read straight from the table on purpose: this
/// is the durable record, and a test that read it back through the same code that wrote it would
/// prove only that the code agrees with itself.
async fn recorded(db: &TestDb) -> Vec<Json> {
    let conn = db.adapter().await;
    conn.query(
        "SELECT hub_id, command, permission, created_by, approved_by, payload_fingerprint, \
         created_at FROM _elevation_audit ORDER BY created_at, id",
        &Params::new(),
    )
    .await
    .expect("the elevation audit is a core table, always there")
    .rows
}

async fn sales(rt: &Runtime) -> Vec<Json> {
    rt.execute_query("till.sales.list", &Params::new(), &admin())
        .await
        .expect("the admin may always read")
}

async fn drawer_events(db: &TestDb) -> Vec<Json> {
    let conn = db.adapter().await;
    conn.query(
        "SELECT reason, created_by FROM till_drawer_event ORDER BY created_at",
        &Params::new(),
    )
    .await
    .expect("the fixture table is there")
    .rows
}

// ─────────────────────────────────────────────────────────────────────────────
// Rule 3 — the two names, in one row, written by the runtime
// ─────────────────────────────────────────────────────────────────────────────

/// The record names **both** people, and it names them because the dispatcher knew them — not
/// because a module remembered to ask.
#[tokio::test]
async fn an_approved_action_records_the_cashier_who_ran_it_and_the_manager_who_allowed_it() {
    let (db, rt) = fresh_hub().await;
    let manager = manager_id(&rt).await;
    let token = approve(&rt, "till.sale.take_payment", &ticket()).await;

    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved payment");

    let rows = recorded(&db).await;
    assert_eq!(rows.len(), 1, "one approval used, one record");
    assert_eq!(
        rows[0]["created_by"],
        json!("u-cashier"),
        "who was at the till"
    );
    assert_eq!(rows[0]["approved_by"], json!(manager), "who authorised it");
    assert_eq!(rows[0]["command"], json!("till.sale.take_payment"));
    assert_eq!(
        rows[0]["permission"],
        json!("till.take_payment"),
        "the permission that was stepped up to, so the record says WHAT was allowed"
    );
    assert_eq!(rows[0]["hub_id"], json!("h1"));
    assert!(
        !rows[0]["payload_fingerprint"]
            .as_str()
            .unwrap_or_default()
            .is_empty(),
        "the record fingerprints the exact action approved, not just its name"
    );
}

/// **The point of putting it in the runtime.** `till.drawer.open` writes to a table that has no
/// `approved_by` column and whose SQL never binds `:approved_by` — a module that simply did not
/// think about elevation, which today is every module in the catalogue. The approval still leaves
/// a trace.
#[tokio::test]
async fn a_module_that_never_declared_the_column_still_leaves_the_approval_on_record() {
    let (db, rt) = fresh_hub().await;
    let payload = params(json!({ "reason": "change for table 4" }));
    let token = approve(&rt, "till.drawer.open", &payload).await;

    rt.execute_command(
        "till.drawer.open",
        &payload,
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved drawer opening");

    assert_eq!(
        drawer_events(&db).await.len(),
        1,
        "the module's own row was written as always"
    );
    let rows = recorded(&db).await;
    assert_eq!(
        rows.len(),
        1,
        "and the runtime recorded the approval anyway — the module never had to know"
    );
    assert_eq!(rows[0]["command"], json!("till.drawer.open"));
    assert_eq!(rows[0]["created_by"], json!("u-cashier"));
}

/// An action nobody had to approve writes **nothing**. That silence is a statement, not a gap:
/// the runtime looked, and there was no approval. It only reads that way for actions taken after
/// the record started existing, which is why the migration that created it is dated in
/// `_hub_system_migrations` — before that instant, «no row» means «nobody knows».
#[tokio::test]
async fn an_action_nobody_had_to_approve_records_nothing_and_that_silence_is_dated() {
    let (db, rt) = fresh_hub().await;

    rt.execute_command("till.sale.create", &ticket(), &cashier())
        .await
        .expect("the cashier may open a ticket on their own");

    assert_eq!(sales(&rt).await.len(), 1, "the sale happened");
    assert!(
        recorded(&db).await.is_empty(),
        "nobody approved it, so there is nothing to record"
    );

    let conn = db.adapter().await;
    let control = conn
        .query(
            "SELECT applied_at FROM _hub_system_migrations WHERE name = 'elevation_audit'",
            &Params::new(),
        )
        .await
        .expect("the control table is there");
    assert_eq!(control.rows.len(), 1, "the record has a start date…");
    assert!(
        !control.rows[0]["applied_at"]
            .as_str()
            .unwrap_or_default()
            .is_empty(),
        "…and it is a real instant, so «no row» can be read as «no approval» only after it"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// The caller decides nothing — neither what is written, nor whether it is
// ─────────────────────────────────────────────────────────────────────────────

/// The payload is data. Dressing it up with the field names of the record changes neither of the
/// two attributions: both come from the runtime — the cashier from the authenticated context, the
/// manager from the grant that was just spent.
#[tokio::test]
async fn the_payload_cannot_dress_up_either_of_the_two_names() {
    let (db, rt) = fresh_hub().await;
    let manager = manager_id(&rt).await;
    // Note the payload is the one the manager was shown, forgeries included: the fingerprint is
    // taken over exactly what the cashier sent, so the retry has to send the same thing.
    let payload = params(json!({
        "label": "table 4",
        "created_by": "u-somebody-else",
        "approved_by": "u-the-owner",
    }));
    let token = approve(&rt, "till.sale.take_payment", &payload).await;

    rt.execute_command(
        "till.sale.take_payment",
        &payload,
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved payment");

    let rows = recorded(&db).await;
    assert_eq!(rows.len(), 1);
    assert_eq!(
        rows[0]["created_by"],
        json!("u-cashier"),
        "the till is where the cashier is, not where the payload says"
    );
    assert_eq!(
        rows[0]["approved_by"],
        json!(manager),
        "and the approver is the one who typed a PIN"
    );
}

/// **Breaking the audit must not be a way to get the action through.** If the record cannot be
/// written, the elevated command does not run: otherwise «make the insert fail» would be a
/// perfectly good way to have a manager-level action executed leaving no trace, which is the exact
/// outcome rule 3 exists to prevent.
#[tokio::test]
async fn an_approval_that_cannot_be_recorded_authorises_nothing() {
    let (db, rt) = fresh_hub().await;
    let token = approve(&rt, "till.sale.take_payment", &ticket()).await;

    db.adapter()
        .await
        .execute_batch("DROP TABLE _elevation_audit;")
        .await
        .expect("the audit table goes away under the runtime's feet");

    let err = rt
        .execute_command(
            "till.sale.take_payment",
            &ticket(),
            &cashier().with_elevation_token(&token),
        )
        .await
        .expect_err("no record, no elevated action");

    assert!(
        !matches!(err, RuntimeError::RequiresElevation { .. }),
        "and it is not reported as «ask the manager» — they already did; got {err:?}"
    );
    assert!(
        sales(&rt).await.is_empty(),
        "nothing was written: the action did not happen at all"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// What the record is, next to what the approval is
// ─────────────────────────────────────────────────────────────────────────────

/// [ADR-0246] keeps the **grant** out of the database on purpose: it is a spendable credential and
/// has no business surviving a restart or travelling in a backup. The **receipt** is the opposite
/// — a fact about something that already happened — so it must survive exactly what the grant must
/// not. Both halves in one test, because it is the contrast that is the design.
#[tokio::test]
async fn the_receipt_outlives_the_restart_that_kills_the_approval() {
    let (db, rt) = fresh_hub().await;
    let spent = approve(&rt, "till.sale.take_payment", &ticket()).await;
    let unused = approve(&rt, "till.sale.void", &ticket()).await;
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&spent),
    )
    .await
    .expect("the approved payment");
    drop(rt);

    let mut restarted = Runtime::with_hub_id(Box::new(db.adapter().await), "h1");
    restarted.ensure_system_tables().await.unwrap();
    restarted.install_from_dir(&module_dir()).await.unwrap();

    assert_eq!(
        recorded(&db).await.len(),
        1,
        "what happened, happened: the record survives the restart"
    );
    let err = restarted
        .execute_command(
            "till.sale.void",
            &ticket(),
            &cashier().with_elevation_token(&unused),
        )
        .await
        .expect_err("the approval itself did not survive it");
    assert!(
        matches!(&err, RuntimeError::RequiresElevation { .. }),
        "got {err:?}"
    );
    assert_eq!(
        recorded(&db).await.len(),
        1,
        "and a refused retry records nothing — the record is of approvals USED"
    );
}

/// An approval is spent the moment it is presented, and `Grants::spend` removes it whatever
/// happens next. So a command that then blows up must still be on record: the manager did
/// authorise it, and «the manager approved something that failed» is a fact an audit has to be
/// able to show. Losing it would leave a burnt approval and no trace of who burnt it.
#[tokio::test]
async fn an_approval_spent_on_an_action_that_then_failed_is_still_on_record() {
    let (db, rt) = fresh_hub().await;
    // `label` is NOT NULL in the fixture and the command has no schema to default it: the insert
    // fails inside the command's own transaction, after the gate has already been passed.
    let payload = params(json!({ "label": null }));
    let token = approve(&rt, "till.sale.take_payment", &payload).await;

    rt.execute_command(
        "till.sale.take_payment",
        &payload,
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect_err("the command itself fails");

    assert!(sales(&rt).await.is_empty(), "and it wrote no sale");
    let rows = recorded(&db).await;
    assert_eq!(
        rows.len(),
        1,
        "but the approval was spent, so it is on record"
    );
    assert_eq!(rows[0]["command"], json!("till.sale.take_payment"));
}

/// Tenancy: the record is stamped with the **deployment's** `hub_id`, and a neighbour that is
/// alive and holding records of its own during the action keeps every one of them.
#[tokio::test]
async fn the_neighbours_records_are_still_theirs_afterwards() {
    let (db, rt) = fresh_hub().await;
    let conn = db.adapter().await;
    conn.execute_batch(
        "INSERT INTO _elevation_audit \
         (id, hub_id, command, permission, created_by, approved_by, payload_fingerprint, created_at) \
         VALUES ('n1', 'h2', 'till.sale.void', 'till.void_sale', 'u-their-cashier', \
         'u-their-manager', 'deadbeef', '2020-01-01T00:00:00Z');",
    )
    .await
    .expect("the neighbour was already using the till when we started");

    let token = approve(&rt, "till.sale.take_payment", &ticket()).await;
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved payment");

    let rows = recorded(&db).await;
    assert_eq!(rows.len(), 2, "both hubs' records are here, side by side");
    let theirs: Vec<&Json> = rows.iter().filter(|r| r["hub_id"] == json!("h2")).collect();
    assert_eq!(theirs.len(), 1, "the neighbour still has exactly their row");
    assert_eq!(theirs[0]["approved_by"], json!("u-their-manager"));
    assert_eq!(theirs[0]["created_by"], json!("u-their-cashier"));
    assert_eq!(theirs[0]["created_at"], json!("2020-01-01T00:00:00Z"));
    let ours: Vec<&Json> = rows.iter().filter(|r| r["hub_id"] == json!("h1")).collect();
    assert_eq!(ours.len(), 1, "and ours is stamped with OUR hub");
}

// ─────────────────────────────────────────────────────────────────────────────
// hub#512 — the record is READABLE: hub.approvals.list (the door that was missing)
// ─────────────────────────────────────────────────────────────────────────────

/// An admin reads the audit trail through the core query `hub.approvals.list`. Both attributions
/// arrive, and — the point of #512 — their **names** arrive with them: no UUIDs on the screen.
#[tokio::test]
async fn an_admin_reads_the_audit_with_names_resolved() {
    let (_db, rt) = fresh_hub().await;
    let token = approve(&rt, "till.sale.take_payment", &ticket()).await;
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved payment");

    let rows = rt
        .execute_query("hub.approvals.list", &Params::new(), &admin())
        .await
        .expect("an admin may read the audit");

    assert_eq!(rows.len(), 1, "one approval spent, one row");
    assert_eq!(rows[0]["command"], json!("till.sale.take_payment"));
    assert_eq!(rows[0]["permission"], json!("till.take_payment"));
    assert_eq!(
        rows[0]["created_by"],
        json!("u-cashier"),
        "who was at the till"
    );
    // The manager's name is resolved by JOIN against hub_user — the whole point of #512.
    // (The cashier id "u-cashier" is a fixture stand-in that does not exist as a hub_user, so its
    // name resolves to "" — which is also the right behaviour: a deleted employee's audit row must
    // not disappear.)
    assert_eq!(
        rows[0]["approved_by_name"],
        json!("Sofía"),
        "not a UUID: a name"
    );
    assert!(
        !rows[0]["payload_fingerprint"]
            .as_str()
            .unwrap_or_default()
            .is_empty(),
        "the fingerprint travels"
    );
}

/// hub#903 (ADR-0351, rule R2) — **an employee is never deleted, they are deactivated**, and the
/// receipts they signed stay on record WITH their name.
///
/// This is the market's answer, unanimously: of eleven references, six forbid deleting an employee
/// who has history at all (Business Central, NetSuite, Square, Clover, and SAP B1 / Odoo in all
/// but name), and the five that allow it keep the trail anyway — Toast («information about deleted
/// employees remains available in reports»), Shopify, Fresha, Vagaro, and Lightspeed, which is the
/// only one that anonymises. **Nobody cascades, and nobody nulls the attribution on purpose.**
///
/// The hub already behaves this way — `DELETE /api/hub/users/:id` is routed to `deactivate_user`,
/// an `is_active = 0` — but nothing said so and nothing held it in place. This test is the lock:
/// a refactor that turned the deactivation into a real delete would take a manager's four years of
/// approvals with it, and today only this test would notice.
///
/// Anonymising instead is deliberately NOT done. Art. 17.3.b/e GDPR shields the receipt from an
/// erasure request while the period runs, and what the law grants afterwards is *bloqueo* (art. 32
/// LOPDGDD) — which in a hub collapses into the four-year prune, because the row is already
/// invisible outside this admin-only query. **The prune IS the erasure**; anonymising early would
/// destroy the evidence with nobody entitled to ask for it.
#[tokio::test]
async fn a_deactivated_manager_keeps_their_name_on_every_receipt_they_signed() {
    let (db, rt) = fresh_hub().await;
    let token = approve(&rt, "till.sale.take_payment", &ticket()).await;
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved payment");

    // She leaves the company. This is the strongest thing the hub can do to a person: there is no
    // delete, by decision.
    let manager = manager_id(&rt).await;
    let row = rt
        .update_hub_user(
            &manager,
            &erplora_runtime::hub_users::UpdateHubUser {
                is_active: Some(false),
                ..Default::default()
            },
        )
        .await
        .expect("the manager is deactivated");
    assert!(!row.is_active, "she is out: {row:?}");

    // The receipt is untouched — same row, same two ids.
    let rows = recorded(&db).await;
    assert_eq!(rows.len(), 1, "the receipt did not leave with her");
    assert_eq!(rows[0]["approved_by"], json!(manager));

    // And the screen still names her. The JOIN is on the id and asks nothing about `is_active`, so
    // «who authorised this» keeps its answer instead of degrading to a UUID the day she leaves.
    let read = rt
        .execute_query("hub.approvals.list", &Params::new(), &admin())
        .await
        .expect("an admin may read the audit");
    assert_eq!(read.len(), 1);
    assert_eq!(
        read[0]["approved_by_name"],
        json!("Sofía"),
        "a former employee is still the person who said yes"
    );
}

/// The cashier who **used** the approval cannot read the audit: only an admin can. `hub.approvals.list`
/// is about the staff, not about the till.
#[tokio::test]
async fn a_cashier_cannot_read_the_audit() {
    let (_db, rt) = fresh_hub().await;
    let token = approve(&rt, "till.sale.take_payment", &ticket()).await;
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&token),
    )
    .await
    .expect("the approved payment");

    let err = rt
        .execute_query("hub.approvals.list", &Params::new(), &cashier())
        .await
        .expect_err("the cashier lacks hub.administer");
    assert!(
        matches!(err, RuntimeError::PermissionDenied(_)),
        "got {err:?}"
    );
}

/// The filter by `command` narrows the audit to one kind of action.
#[tokio::test]
async fn the_audit_filters_by_command() {
    let (_db, rt) = fresh_hub().await;
    // Two approvals: one payment, one drawer open.
    let pay_token = approve(&rt, "till.sale.take_payment", &ticket()).await;
    rt.execute_command(
        "till.sale.take_payment",
        &ticket(),
        &cashier().with_elevation_token(&pay_token),
    )
    .await
    .unwrap();

    let drawer_payload = params(json!({ "reason": "change" }));
    let drawer_token = approve(&rt, "till.drawer.open", &drawer_payload).await;
    rt.execute_command(
        "till.drawer.open",
        &drawer_payload,
        &cashier().with_elevation_token(&drawer_token),
    )
    .await
    .unwrap();

    // `f_command`: the same filter convention every list query of the runtime speaks (hub#884
    // moved the audit onto the generic list engine; the ad-hoc `command` param went with it).
    let mut filter = Params::new();
    filter.insert("f_command".into(), json!("till.sale.take_payment"));
    let rows = rt
        .execute_query("hub.approvals.list", &filter, &admin())
        .await
        .unwrap();
    assert_eq!(rows.len(), 1, "only the payment, not the drawer");
    assert_eq!(rows[0]["command"], json!("till.sale.take_payment"));

    // The LEVEL filters the same way — the screen offers it since hub#512, so the server has to
    // answer it now that the client no longer holds the whole trail to filter in memory.
    let mut by_level = Params::new();
    by_level.insert("f_permission".into(), json!("till.void_sale"));
    let rows = rt
        .execute_query("hub.approvals.list", &by_level, &admin())
        .await
        .unwrap();
    assert_eq!(rows.len(), 1, "only the drawer, not the payment");
    assert_eq!(rows[0]["command"], json!("till.drawer.open"));
}

// ─────────────────────────────────────────────────────────────────────────────
// hub#884 — the record is read in PAGES: the whole trail never crosses the wire
// ─────────────────────────────────────────────────────────────────────────────
//
// The write path and the gate are covered above, through the real door. What these tests pin down
// is the READ contract: the audit grows forever by design (nothing deletes it), so the query must
// serve pages with a real total — and the date filter must live in the query, because filtering in
// the client only works while the whole trail is in memory, which is exactly the bug.
//
// The rows are seeded straight into `_elevation_audit` ON PURPOSE: pagination and date filtering
// need controlled, distinct instants, and spending real approvals stamps them all with «now».

/// Seed `n` audit rows, one per minute of 2026-07-01T00:xx, oldest = r0. Same shape the runtime
/// writes (`elevation.rs`), timestamps in the same RFC 3339 form `now_rfc3339` produces.
async fn seed_audit(db: &TestDb, n: usize) {
    let conn = db.adapter().await;
    for i in 0..n {
        let mut p = Params::new();
        p.insert("id".into(), json!(format!("r{i}")));
        p.insert("hub_id".into(), json!("h1"));
        p.insert("command".into(), json!("till.sale.take_payment"));
        p.insert("permission".into(), json!("till.take_payment"));
        p.insert("created_by".into(), json!("u-cashier"));
        p.insert("approved_by".into(), json!("u-manager"));
        p.insert("payload_fingerprint".into(), json!(format!("fp-{i}")));
        p.insert(
            "created_at".into(),
            json!(format!("2026-07-01T00:{i:02}:00+00:00")),
        );
        conn.execute(
            "INSERT INTO _elevation_audit \
             (id, hub_id, command, permission, created_by, approved_by, payload_fingerprint, created_at) \
             VALUES (:id, :hub_id, :command, :permission, :created_by, :approved_by, \
             :payload_fingerprint, :created_at)",
            &p,
        )
        .await
        .expect("the audit table is a core table, always there");
    }
}

/// An admin asks for a page and gets a PAGE: the requested slice, newest first, plus the real
/// total so the pager can say «page 1 of 3» without downloading pages 2 and 3.
#[tokio::test]
async fn the_audit_is_read_in_pages_with_a_real_total() {
    let (db, rt) = fresh_hub().await;
    seed_audit(&db, 5).await;

    let page = rt
        .execute_query_page(
            "hub.approvals.list",
            &params(json!({ "limit": 2 })),
            &admin(),
        )
        .await
        .expect("an admin may read the audit");
    assert_eq!(page.rows.len(), 2, "the page is the slice asked for");
    assert_eq!(page.total, 5, "the total is the whole trail, not the slice");
    assert_eq!(page.limit, 2);
    assert_eq!(page.offset, 0);
    // Newest first is the default order — the question this screen answers is about «that Tuesday»,
    // and the reader starts from today.
    assert_eq!(
        page.rows[0]["created_at"],
        json!("2026-07-01T00:04:00+00:00")
    );

    let last = rt
        .execute_query_page(
            "hub.approvals.list",
            &params(json!({ "limit": 2, "offset": 4 })),
            &admin(),
        )
        .await
        .unwrap();
    assert_eq!(last.rows.len(), 1, "the last page holds the remainder");
    assert_eq!(
        last.rows[0]["created_at"],
        json!("2026-07-01T00:00:00+00:00")
    );
    assert_eq!(last.total, 5);
}

/// Without an explicit `limit` the response is still BOUNDED: the engine's default page size
/// applies. This is the ceiling hub#884 is about — before it, «no limit sent» meant «the whole
/// trail crosses the wire», and at five approvals a day that is megabytes per screen-open.
#[tokio::test]
async fn the_audit_never_ships_whole_by_default() {
    let (db, rt) = fresh_hub().await;
    seed_audit(&db, 60).await;

    let page = rt
        .execute_query_page("hub.approvals.list", &Params::new(), &admin())
        .await
        .unwrap();
    assert_eq!(
        page.rows.len(),
        50,
        "the default page size caps the response"
    );
    assert_eq!(page.total, 60, "…and the total still names the full trail");
}

/// The date range is answered BY THE QUERY (`f_created_at_from`/`_to`, the engine's range filter),
/// with the total reflecting the filtered set — so «show me that Tuesday» works without the client
/// ever holding the rest of the years.
#[tokio::test]
async fn the_audit_filters_by_date_range_on_the_server() {
    let (db, rt) = fresh_hub().await;
    seed_audit(&db, 5).await;

    let page = rt
        .execute_query_page(
            "hub.approvals.list",
            &params(json!({
                "f_created_at_from": "2026-07-01T00:01:00+00:00",
                "f_created_at_to": "2026-07-01T00:03:59",
            })),
            &admin(),
        )
        .await
        .unwrap();
    assert_eq!(
        page.rows.len(),
        3,
        "r1..r3: the range is inclusive on both ends"
    );
    assert_eq!(
        page.total, 3,
        "the total is the FILTERED total: it feeds the pager"
    );
    assert_eq!(
        page.rows[0]["created_at"],
        json!("2026-07-01T00:03:00+00:00")
    );
    assert_eq!(
        page.rows[2]["created_at"],
        json!("2026-07-01T00:01:00+00:00")
    );
}

/// The wire knows it is a list: the server keys the `{rows,total,limit,offset}` envelope off
/// `is_list_query`, which must say yes for the audit — and keep saying no for the core queries
/// that still answer with a plain array (`users.list` feeds dropdowns, not pagers).
#[tokio::test]
async fn the_audit_is_a_list_query_on_the_wire() {
    let (_db, rt) = fresh_hub().await;
    assert!(
        rt.is_list_query("hub.approvals.list"),
        "the server must envelope the audit as a page"
    );
    assert!(
        !rt.is_list_query("hub.users.list"),
        "the other core queries keep their plain-array shape"
    );
}
