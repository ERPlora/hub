//! **The rows written before hub#356 still cannot be revoked** (hub#436).
//!
//! hub#356 (PR #432) fixed the code: the Personal alta now writes the email in the **two** places
//! that need it — `hub_user.email`, the key the whole ACCESS plane resolves against, and
//! `hub_user_profile.email`, what the person sees in their profile. It did **not** touch the rows
//! that were already there, and those are still in the deployed hubs.
//!
//! What such a row is: a person the administrator invited from Personal, whose email landed only in
//! their profile. Everything that administers access looks them up by `hub_user.email` and finds
//! nothing:
//!
//!  - [`Runtime::revoke_cloud_access`] — the SaaS revoked their membership and the hub is supposed
//!    to close the door (step 2b rule D, hub#348). It closes nothing: **their session keeps
//!    resolving**. That is the security failure, and `the_saas_revoking…` below is its reproduction.
//!  - [`Runtime::deactivate_login_user`] — the `DELETE /api/members/{email}` baja. Reports "nothing
//!    to do" while the person stays active.
//!  - [`Runtime::get_or_link_cloud_user`] — their first login does not find them, falls through to
//!    step 3 and provisions a **second** row with the least-privilege role: two identities for one
//!    person, and the role the administrator granted lost in silence.
//!
//! So the fix is a **backfill**: copy the profile email onto the access column where the access
//! column is empty. The whole difficulty is that `hub_user.email` has no unique constraint (v9: the
//! index is not unique, uniqueness is enforced in code), so a blind copy cannot fail — it silently
//! produces two rows answering for one email. The tests below pin **what the backfill refuses to
//! do**, which is where the security lives: `/api/profile` lets anybody type any email into their
//! own profile, so copying a profile email that another identity already answers for would let a
//! cashier be found — and raised to the floor of — the administrator's account.
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params, PgAdapter};
use erplora_runtime::hub_users::{NewHubUser, UpdateHubUser};
use erplora_runtime::user_profile::{UpdateUserProfile, UserPreferences};
use erplora_runtime::Runtime;
use serde_json::json;

const HUB: &str = "hub-436";

fn p(pairs: &[(&str, serde_json::Value)]) -> Params {
    let mut m = Params::new();
    for (k, v) in pairs {
        m.insert((*k).into(), v.clone());
    }
    m
}

/// A hub **deployed before this fix**: the schema is at HEAD, but the control table is rewound so
/// that the next boot re-runs the backfill — exactly what a real upgrade does when the binary
/// carries a migration the database has never seen.
///
/// The rewind is by **name**, not by number: renumbering the migration (which happens, because
/// `apply` compares against the maximum applied version and a number at or below it is skipped in
/// silence) must not silently turn this test into a no-op. While the migration does not exist the
/// subquery is `NULL`, nothing is rewound and the backfill never runs — which is the red.
async fn hub_deployed_before_the_fix(tdb: &TestDb) -> (Runtime, PgAdapter) {
    let rt = Runtime::with_hub_id(Box::new(tdb.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    let raw = tdb.adapter().await;
    raw.execute(
        "DELETE FROM _hub_system_migrations WHERE version >= \
           (SELECT MIN(version) FROM _hub_system_migrations WHERE name = :name)",
        &p(&[("name", json!(BACKFILL_MIGRATION))]),
    )
    .await
    .unwrap();
    (rt, raw)
}

/// The name of the migration under test. The test rewinds by it, so a renumbering is free and a
/// **rename** is what breaks the test — which is the right way round: the number is an accident of
/// merge order, the name is the contract.
const BACKFILL_MIGRATION: &str = "hub_user_access_email_backfill";

/// Reboots the hub: a second `ensure_system_tables` over the same data, which is what the server
/// does on every start.
async fn reboot(tdb: &TestDb) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(tdb.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// Writes a row in the **pre-fix shape**: the email only in the profile, the access column empty.
/// Written with raw SQL on purpose — no code path can produce this shape any more, which is
/// precisely why a backfill is needed for the ones that already exist.
async fn row_written_before_the_fix(
    raw: &PgAdapter,
    id: &str,
    name: &str,
    role: &str,
    profile_email: &str,
) {
    let params = p(&[
        ("id", json!(id)),
        ("name", json!(name)),
        ("role", json!(role)),
        ("email", json!(profile_email)),
        ("hub_id", json!(HUB)),
        ("now", json!("2026-08-01T10:00:00Z")),
    ]);
    raw.execute(
        "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
           VALUES (:id, :name, '', :role, NULL, 1, :now, '')",
        &params,
    )
    .await
    .unwrap();
    raw.execute(
        "INSERT INTO hub_user_profile (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
           VALUES (:hub_id, :id, :name, '', :email, '', :now)",
        &params,
    )
    .await
    .unwrap();
}

/// The access email of a row, straight from the column the access plane reads.
async fn access_email(raw: &PgAdapter, id: &str) -> String {
    raw.query(
        "SELECT email FROM hub_user WHERE id = :id",
        &p(&[("id", json!(id))]),
    )
    .await
    .unwrap()
    .rows
    .first()
    .and_then(|r| r["email"].as_str())
    .unwrap_or_default()
    .to_string()
}

async fn is_active(raw: &PgAdapter, id: &str) -> bool {
    raw.query(
        "SELECT is_active FROM hub_user WHERE id = :id",
        &p(&[("id", json!(id))]),
    )
    .await
    .unwrap()
    .rows
    .first()
    .map(|r| r["is_active"].as_bool().unwrap_or_else(|| r["is_active"].as_i64() == Some(1)))
    .unwrap_or(false)
}

async fn role_of(raw: &PgAdapter, id: &str) -> String {
    raw.query(
        "SELECT role FROM hub_user WHERE id = :id",
        &p(&[("id", json!(id))]),
    )
    .await
    .unwrap()
    .rows
    .first()
    .and_then(|r| r["role"].as_str())
    .unwrap_or_default()
    .to_string()
}

// ── The reproduction: a revoked membership that never closed the door ─────────────────────────

/// 🔴 **The security failure of hub#436.** The SaaS revoked Ana's membership; the hub is supposed
/// to deactivate her row and drop her sessions (rule D, hub#348). Because her email only ever
/// reached her profile, `revoke_cloud_access` matches nothing: she stays active and **her open
/// session keeps resolving**. Revoking access did not revoke access.
#[tokio::test]
async fn the_saas_revoking_a_membership_closes_the_door_of_a_row_written_before_the_fix() {
    let tdb = TestDb::new().await;
    let (rt, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "admin", "ana@example.com").await;
    let session = rt.create_session("u-ana", 3600, None).await.unwrap();
    assert!(
        rt.resolve_session(&session).await.unwrap().is_some(),
        "she is in: this is the access the revocation has to take away"
    );

    let rt = reboot(&tdb).await;
    let closed = rt
        .revoke_cloud_access("cloud-ana", Some("ana@example.com"))
        .await
        .unwrap();

    assert_eq!(closed, 1, "the revocation has to reach her row");
    assert!(!is_active(&raw, "u-ana").await, "her row is deactivated");
    assert!(
        rt.resolve_session(&session).await.unwrap().is_none(),
        "and her open session stops resolving — otherwise the revocation changed nothing"
    );
}

/// The other half of the same door: `DELETE /api/members/{email}`, the baja an administrator does
/// from the hub. It answered `deactivated: false` while the person kept working.
#[tokio::test]
async fn the_members_baja_by_email_finds_a_row_written_before_the_fix() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "manager", "ana@example.com").await;

    let rt = reboot(&tdb).await;

    assert!(
        rt.deactivate_login_user("ana@example.com").await.unwrap(),
        "the baja by email has to find her"
    );
    assert!(!is_active(&raw, "u-ana").await);
}

/// Her first login lands on **her** row with the role the administrator granted, instead of
/// provisioning a second identity with the least-privilege default — the symptom users reported as
/// «they invited me as an admin and I get in as an employee».
#[tokio::test]
async fn the_first_login_of_a_row_written_before_the_fix_keeps_the_granted_role() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "manager", "ana@example.com").await;

    let rt = reboot(&tdb).await;
    let signed_in = rt
        .get_or_link_cloud_user("cloud-ana", "Ana Soto", "employee", Some("ana@example.com"), None)
        .await
        .unwrap();

    assert_eq!(signed_in.id, "u-ana", "the login lands on the row that was already there");
    assert_eq!(signed_in.role, "manager", "and keeps the role the administrator granted");
    assert_eq!(
        rt.list_hub_users().await.unwrap().len(),
        1,
        "one person, one row: no second identity provisioned alongside"
    );
}

/// And Personal shows the same email it did before — the backfill moves where the email is stored,
/// it does not change what the administrator sees.
#[tokio::test]
async fn the_email_personal_shows_does_not_change() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "manager", "ana@example.com").await;

    let rt = reboot(&tdb).await;

    let listed = rt.list_hub_users().await.unwrap();
    assert_eq!(listed.len(), 1);
    assert_eq!(listed[0].email, "ana@example.com");
    assert_eq!(access_email(&raw, "u-ana").await, "ana@example.com");
}

// ── What the backfill refuses to do ───────────────────────────────────────────────────────────

/// 🔴 **An email another row already answers for is never copied.** `/api/profile` is self-service
/// and unchecked: anybody can type any email into their own profile. If the backfill copied it,
/// a cashier who typed the administrator's address would end up holding the administrator's access
/// key — and the next cloud login could link that account to the cashier's row and raise it to the
/// role floor (hub#347). The row is left exactly as it was.
#[tokio::test]
async fn an_email_another_row_already_answers_for_is_never_copied() {
    let tdb = TestDb::new().await;
    let (rt, raw) = hub_deployed_before_the_fix(&tdb).await;
    // Ana is a real account user: her email is where access looks for it.
    rt.create_login_user("ana@example.com", "admin").await.unwrap();
    // Bob works the till and typed Ana's address into his own profile.
    row_written_before_the_fix(&raw, "u-bob", "Bob Ruiz", "employee", "ana@example.com").await;

    let rt = reboot(&tdb).await;

    assert_eq!(
        access_email(&raw, "u-bob").await,
        "",
        "Bob never receives an access key that answers for somebody else"
    );
    assert_eq!(role_of(&raw, "u-bob").await, "employee", "and is not raised by Ana's login");
    let ana = rt
        .get_or_link_cloud_user("cloud-ana", "Ana", "employee", Some("ana@example.com"), Some("admin"))
        .await
        .unwrap();
    assert_ne!(ana.id, "u-bob", "Ana's login links to Ana's row, never to Bob's");
    assert_eq!(role_of(&raw, "u-bob").await, "employee");
}

/// The same refusal ignoring case, because the alta guard that would have caught the duplicate
/// (`email_is_known`) compares case-insensitively: letting `Ana@Example.com` through would create
/// a pair the hub itself considers the same email.
#[tokio::test]
async fn the_refusal_ignores_case() {
    let tdb = TestDb::new().await;
    let (rt, raw) = hub_deployed_before_the_fix(&tdb).await;
    rt.create_login_user("ana@example.com", "admin").await.unwrap();
    row_written_before_the_fix(&raw, "u-bob", "Bob Ruiz", "employee", "Ana@Example.com").await;

    reboot(&tdb).await;

    assert_eq!(access_email(&raw, "u-bob").await, "");
}

/// 🔴 **Two identities for one person: the backfill picks neither.** This is the pair hub#356
/// produced — the row the administrator created (with the granted role) and the row the first
/// login provisioned (least privilege, linked to the cloud account). Choosing between them means
/// deciding which one keeps the sales, the sessions and the audit trail that point at its id, and
/// which role is the real one. A migration cannot know that; it leaves both alone and reports them.
#[tokio::test]
async fn when_two_rows_claim_one_email_the_backfill_picks_neither() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana-1", "Ana Soto", "admin", "ana@example.com").await;
    row_written_before_the_fix(&raw, "u-ana-2", "Ana S.", "employee", "ana@example.com").await;

    let rt = reboot(&tdb).await;

    assert_eq!(access_email(&raw, "u-ana-1").await, "");
    assert_eq!(access_email(&raw, "u-ana-2").await, "");
    let unresolved = rt.unresolved_access_emails().await.unwrap();
    assert_eq!(unresolved.len(), 2, "both are reported, neither is guessed");
}

/// A **divergent** row is not a rival. If somebody else's profile happens to hold this address
/// while their own access key is a different one, they are not competing for it — the key is free
/// and the row that has nothing gets it. Blocking on that would leave a revocable person
/// unrevocable because a colleague typed their address into their own profile.
#[tokio::test]
async fn a_row_with_its_own_access_key_does_not_block_the_address_its_profile_claims() {
    let tdb = TestDb::new().await;
    let (rt, raw) = hub_deployed_before_the_fix(&tdb).await;
    // Bob has his own access key; his profile says Ana's address (his own doing, `/api/profile`).
    let bob = rt.create_login_user("bob@example.com", "employee").await.unwrap();
    rt.update_user_profile(
        &bob.id,
        &UpdateUserProfile {
            first_name: "Bob".into(),
            last_name: "Ruiz".into(),
            email: "ana@example.com".into(),
            preferences: UserPreferences::default(),
        },
    )
    .await
    .unwrap();
    // Ana is the row written before the fix, and nobody else answers for her address.
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "manager", "ana@example.com").await;

    let rt = reboot(&tdb).await;

    assert_eq!(access_email(&raw, "u-ana").await, "ana@example.com");
    assert_eq!(access_email(&raw, &bob.id).await, "bob@example.com", "Bob keeps his own");
    assert!(rt.unresolved_access_emails().await.unwrap().is_empty());
}

/// The address is copied **verbatim**, case included. Every access lookup compares the string
/// exactly (`revoke_cloud_access`, the `/api/members` baja, the link on the first login), so
/// lower-casing it here would not be tidying: it would be handing the row an address that answers
/// for nobody — the same silence this migration exists to end.
#[tokio::test]
async fn the_case_of_the_address_is_preserved() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "manager", "Ana.Soto@Example.com").await;

    let rt = reboot(&tdb).await;

    assert_eq!(access_email(&raw, "u-ana").await, "Ana.Soto@Example.com");
    assert_eq!(
        rt.revoke_cloud_access("cloud-ana", Some("Ana.Soto@Example.com"))
            .await
            .unwrap(),
        1,
        "the SaaS revokes by the address it holds, and that comparison is exact"
    );
}

/// A profile of **another hub** claiming the address does not block this hub's backfill. `hub_user`
/// is shared by every hub of a database (it has no `hub_id`), but that is not a reason to leave a
/// revocable person unrevocable here: the other hub's own run of this migration will find that this
/// address is already answered for and leave its row alone (guard 1), so the pair can never end up
/// written twice.
#[tokio::test]
async fn a_rival_profile_of_another_hub_does_not_block_this_hub() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "manager", "ana@example.com").await;
    raw.execute(
        "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
           VALUES ('u-other', 'Ana del otro hub', '', 'employee', NULL, 1, :now, '')",
        &p(&[("now", json!("2026-08-01T10:00:00Z"))]),
    )
    .await
    .unwrap();
    raw.execute(
        "INSERT INTO hub_user_profile (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
           VALUES ('hub-OTHER', 'u-other', 'Ana', '', 'ana@example.com', '', :now)",
        &p(&[("now", json!("2026-08-01T10:00:00Z"))]),
    )
    .await
    .unwrap();

    reboot(&tdb).await;

    assert_eq!(access_email(&raw, "u-ana").await, "ana@example.com");
    assert_eq!(access_email(&raw, "u-other").await, "", "the other hub's row is not this run's");
}

/// The profile of **another hub** is not this hub's to read. `hub_user` has no `hub_id` (since
/// ADR-0201 each hub owns its database) but `hub_user_profile` does, and a database shared by
/// several hubs predates that: the runtime only ever speaks for its own deployment.
#[tokio::test]
async fn a_profile_belonging_to_another_hub_is_not_copied() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    raw.execute(
        "INSERT INTO hub_user (id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
           VALUES ('u-ana', 'Ana Soto', '', 'manager', NULL, 1, :now, '')",
        &p(&[("now", json!("2026-08-01T10:00:00Z"))]),
    )
    .await
    .unwrap();
    raw.execute(
        "INSERT INTO hub_user_profile (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
           VALUES ('hub-OTHER', 'u-ana', 'Ana', 'Soto', 'ana@example.com', '', :now)",
        &p(&[("now", json!("2026-08-01T10:00:00Z"))]),
    )
    .await
    .unwrap();

    reboot(&tdb).await;

    assert_eq!(access_email(&raw, "u-ana").await, "");
}

/// Whitespace does not travel: the access lookups compare the string **exactly**, so an address
/// copied with a stray space would answer for nobody — the same silence this whole migration is
/// about, produced by the migration itself.
#[tokio::test]
async fn the_copied_address_is_trimmed() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "manager", "  ana@example.com  ").await;

    let rt = reboot(&tdb).await;

    assert_eq!(access_email(&raw, "u-ana").await, "ana@example.com");
    assert_eq!(
        rt.deactivate_login_user("ana@example.com").await.unwrap(),
        true,
        "and the baja by email finds her, which is what the trim is for"
    );
}

/// A profile email that **diverges** from the access email is left alone: that is not a defect, it
/// is the design (hub#356). `/api/profile` lets each person keep their own address in their profile
/// and deliberately does not touch the key their membership hangs from, so the two disagreeing is
/// normal — and Personal already shows the access one, which is what a baja revokes.
#[tokio::test]
async fn a_profile_email_that_diverges_from_the_access_email_is_left_alone() {
    let tdb = TestDb::new().await;
    let (rt, raw) = hub_deployed_before_the_fix(&tdb).await;
    let ana = rt.create_login_user("ana@work.example", "manager").await.unwrap();
    rt.update_user_profile(
        &ana.id,
        &UpdateUserProfile {
            first_name: "Ana".into(),
            last_name: "Soto".into(),
            email: "ana@home.example".into(),
            preferences: UserPreferences::default(),
        },
    )
    .await
    .unwrap();

    let rt = reboot(&tdb).await;

    assert_eq!(
        access_email(&raw, &ana.id).await,
        "ana@work.example",
        "the key her membership hangs from is not replaced by the one she edits herself"
    );
    assert_eq!(rt.user_profile(&ana.id).await.unwrap().email, "ana@home.example");
    assert!(
        rt.unresolved_access_emails().await.unwrap().is_empty(),
        "a divergence by design is not something a human has to look at"
    );
}

// ── Idempotence and silence ───────────────────────────────────────────────────────────────────

/// A hub with nothing to fix must not notice the backfill: local staff have no email anywhere and
/// account users already have theirs in both places. Running it twice changes nothing either — it
/// corrects data, so re-running it has to be a no-op, not a second correction.
#[tokio::test]
async fn a_healthy_hub_is_untouched_and_running_it_twice_changes_nothing() {
    let tdb = TestDb::new().await;
    let (rt, raw) = hub_deployed_before_the_fix(&tdb).await;
    rt.create_hub_user(&NewHubUser {
        name: "Local Luis".into(),
        role: "employee".into(),
        pin: "4821".into(),
        local: true,
        ..NewHubUser::default()
    })
    .await
    .unwrap();
    rt.create_hub_user(&NewHubUser {
        name: "Ana Soto".into(),
        email: "ana@example.com".into(),
        role: "manager".into(),
        ..NewHubUser::default()
    })
    .await
    .unwrap();
    let before = snapshot(&raw).await;

    let rt = reboot(&tdb).await;
    let after_first = snapshot(&raw).await;
    reboot(&tdb).await;
    let after_second = snapshot(&raw).await;

    assert_eq!(before, after_first, "a hub with nothing wrong is not touched");
    assert_eq!(after_first, after_second, "re-running corrects nothing a second time");
    assert!(rt.unresolved_access_emails().await.unwrap().is_empty());
}

/// Running the backfill a second time over a hub it **did** fix leaves the fixed rows alone.
#[tokio::test]
async fn a_hub_it_fixed_is_not_fixed_again() {
    let tdb = TestDb::new().await;
    let (_, raw) = hub_deployed_before_the_fix(&tdb).await;
    row_written_before_the_fix(&raw, "u-ana", "Ana Soto", "manager", "ana@example.com").await;

    reboot(&tdb).await;
    let after_first = snapshot(&raw).await;
    // Rewind again: the same migration re-runs over data it has already corrected.
    raw.execute(
        "DELETE FROM _hub_system_migrations WHERE version >= \
           (SELECT MIN(version) FROM _hub_system_migrations WHERE name = :name)",
        &p(&[("name", json!(BACKFILL_MIGRATION))]),
    )
    .await
    .unwrap();
    reboot(&tdb).await;

    assert_eq!(snapshot(&raw).await, after_first);
    assert_eq!(access_email(&raw, "u-ana").await, "ana@example.com");
}

/// Every `hub_user` as `(id, email, role, is_active)` plus its profile email, ordered — the whole
/// surface the backfill could possibly move.
async fn snapshot(raw: &PgAdapter) -> Vec<String> {
    let mut rows: Vec<String> = raw
        .query(
            "SELECT u.id AS id, u.email AS email, u.role AS role, u.is_active AS is_active, \
                    COALESCE(pr.email, '<none>') AS profile_email \
               FROM hub_user u LEFT JOIN hub_user_profile pr ON pr.user_id = u.id",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows
        .iter()
        .map(|r| {
            format!(
                "{}|{}|{}|{}|{}",
                r["id"].as_str().unwrap_or_default(),
                r["email"].as_str().unwrap_or_default(),
                r["role"].as_str().unwrap_or_default(),
                r["is_active"],
                r["profile_email"].as_str().unwrap_or_default(),
            )
        })
        .collect();
    rows.sort();
    rows
}

/// The check is an **advisory**, not a step of the bootstrap: a hub that will not open is a shop
/// that cannot charge, which is far worse than a warning nobody printed. A database missing the
/// profile table (the shape the old fixtures faked: a version recorded but never run) still boots.
#[tokio::test]
async fn a_hub_whose_profile_table_is_missing_still_boots() {
    let tdb = TestDb::new().await;
    let rt = reboot(&tdb).await;
    let raw = tdb.adapter().await;
    rt.create_login_user("ana@example.com", "manager").await.unwrap();
    raw.execute_batch("DROP TABLE hub_user_profile;").await.unwrap();

    reboot(&tdb).await; // panics if `ensure_system_tables` propagated the failure

    assert!(
        Runtime::with_hub_id(Box::new(tdb.adapter().await), HUB)
            .unresolved_access_emails()
            .await
            .is_err(),
        "asked directly, the failure is still a failure — it is only the boot that tolerates it"
    );
}

// ── The guard: no alta path may write the profile email without the access one ────────────────

/// The regression guard hub#436 asks for. **Every** way a hub gains a person with an email has to
/// write it where access looks for it; writing only the profile is what produced the rows this
/// backfill exists to repair, and it did so in silence.
///
/// The one deliberate exception is `/api/profile` (self-service), covered by its own test below:
/// it must NOT write the access column, because that would let anybody grant themselves an
/// identity by typing an address.
#[tokio::test]
async fn no_alta_path_writes_the_profile_email_without_the_access_email() {
    let tdb = TestDb::new().await;
    let rt = reboot(&tdb).await;
    let raw = tdb.adapter().await;

    // 1) Personal, account user (the alta hub#356 fixed).
    rt.create_hub_user(&NewHubUser {
        name: "Ana Soto".into(),
        email: "ana@example.com".into(),
        role: "manager".into(),
        ..NewHubUser::default()
    })
    .await
    .unwrap();
    assert_access_email_is_written(&raw, "after the Personal alta of an account user").await;

    // 2) Personal, editing somebody's email.
    let ana = rt.list_hub_users().await.unwrap()[0].id.clone();
    rt.update_hub_user(
        &ana,
        &UpdateHubUser {
            email: Some("ana.soto@example.com".into()),
            ..UpdateHubUser::default()
        },
    )
    .await
    .unwrap();
    assert_access_email_is_written(&raw, "after editing an email in Personal").await;

    // 3) `POST /api/members` (ADR-0157 §7).
    rt.create_login_user("carla@example.com", "employee").await.unwrap();
    assert_access_email_is_written(&raw, "after the /api/members alta").await;

    // 4) The owner seeded by provisioning (`HUB_OWNER_EMAIL`, ADR-0157).
    rt.seed_owner("owner@example.com").await.unwrap();
    assert_access_email_is_written(&raw, "after seeding the hub owner").await;

    // 5) The row a first cloud login provisions when nobody matched.
    rt.get_or_link_cloud_user("cloud-new", "Nuevo", "employee", Some("nuevo@example.com"), None)
        .await
        .unwrap();
    assert_access_email_is_written(&raw, "after a cloud login provisioned a row").await;

    // 6) Personal, local user: no email anywhere — the invariant is about agreement, not presence.
    rt.create_hub_user(&NewHubUser {
        name: "Local Luis".into(),
        role: "employee".into(),
        pin: "4821".into(),
        local: true,
        ..NewHubUser::default()
    })
    .await
    .unwrap();
    assert_access_email_is_written(&raw, "after the alta of a local user").await;
}

/// Fails if any row holds a profile email while its access column is empty — the exact shape
/// hub#436 backfills. Checked after every alta path so a new one cannot reintroduce it.
async fn assert_access_email_is_written(raw: &PgAdapter, after: &str) {
    let offenders = raw
        .query(
            "SELECT u.id AS id, pr.email AS profile_email FROM hub_user u \
               JOIN hub_user_profile pr ON pr.user_id = u.id \
              WHERE TRIM(pr.email) <> '' AND COALESCE(TRIM(u.email), '') = ''",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows;
    assert!(
        offenders.is_empty(),
        "{after}: {} row(s) got a profile email and no access email — the access plane cannot see \
         them, so their baja would never revoke anything: {offenders:?}",
        offenders.len()
    );
}

/// The exception, pinned so nobody "fixes" it: **self-service must not write the access column.**
/// `/api/profile` takes whatever address the person types, with no uniqueness check; writing it
/// where access resolves would let anybody make themselves findable as somebody else.
#[tokio::test]
async fn editing_your_own_profile_never_writes_the_access_email() {
    let tdb = TestDb::new().await;
    let rt = reboot(&tdb).await;
    let raw = tdb.adapter().await;
    let ana = rt.create_login_user("ana@example.com", "manager").await.unwrap();

    rt.update_user_profile(
        &ana.id,
        &UpdateUserProfile {
            first_name: "Ana".into(),
            last_name: "Soto".into(),
            email: "boss@example.com".into(),
            preferences: UserPreferences::default(),
        },
    )
    .await
    .unwrap();

    assert_eq!(
        access_email(&raw, &ana.id).await,
        "ana@example.com",
        "the key her membership hangs from is hers, and she cannot retype it into somebody else's"
    );
}
