//! **What the access-email backfill could not decide** (hub#436) — detection, never guessing.
//!
//! The backfill itself is system migration `hub_user_access_email_backfill`: it copies
//! `hub_user_profile.email` onto `hub_user.email` —the key the whole ACCESS plane resolves
//! against— for the rows the alta wrote before hub#356, whose baja therefore revoked nothing.
//!
//! It copies **only where nothing else already answers for that address**. `hub_user.email` has no
//! unique constraint (migration v9 creates a plain index; uniqueness is enforced in code with a
//! SELECT-then-write), so a blind copy cannot fail — it would quietly produce two rows answering
//! for one email. Two situations make that happen and neither can be resolved by a migration:
//!
//!  1. **Another row already answers for it** ([`AccessEmailConflict::AnotherRowAnswersForIt`]).
//!     Either the pair hub#356 produced —the row the administrator created plus the row the first
//!     login provisioned alongside it— or, worse, somebody else's address typed into this person's
//!     profile: `/api/profile` is self-service and unchecked, so copying it would hand a cashier
//!     the administrator's access key and let the next cloud login raise that row to the role floor
//!     (hub#347).
//!  2. **Two profiles claim it** ([`AccessEmailConflict::TwoProfilesClaimIt`]). Nothing in the data
//!     says which of the two is the person and which is the mistake.
//!
//! Merging them is worse than leaving them: `hub_user.id` is what sales, sessions and the audit
//! trail (`created_by`/`updated_by`) point at, and the two rows usually carry **different roles**,
//! so picking one either restores a privilege nobody granted today or drops one that was granted.
//! So the deliverable for these is to be **seen**: [`report_unresolved`] prints them at every boot
//! and [`unresolved`] answers the same question on demand.
//!
//! The report is a **live query**, not a snapshot written by the migration, so it cannot go stale:
//! the moment an administrator resolves the clash, the hub stops mentioning it. It also keeps
//! answering after the migration has run, which is what catches somebody typing another person's
//! address into their profile from then on.
//!
//! A **divergence** (both emails present and different) is not reported: that is the design of
//! hub#356 — `/api/profile` edits the profile and deliberately never touches the key the membership
//! hangs from, and Personal already shows the access one, which is the one a baja revokes.
use erplora_db::{DatabaseAdapter, Params};
use serde::Serialize;
use serde_json::json;

use crate::errors::Result;

/// Why the backfill refused to copy a profile email onto the access column.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AccessEmailConflict {
    /// A **different** `hub_user` already carries this address as its access key (ignoring case).
    /// Copying it would leave two rows answering for one membership.
    AnotherRowAnswersForIt,
    /// Two or more rows with an empty access key hold this address in their profile. Nothing says
    /// which one is the person.
    TwoProfilesClaimIt,
}

impl AccessEmailConflict {
    /// One line for the boot log — what an operator has to understand to act on it.
    fn explain(self) -> &'static str {
        match self {
            AccessEmailConflict::AnotherRowAnswersForIt => {
                "another user already answers for that address"
            }
            AccessEmailConflict::TwoProfilesClaimIt => {
                "two users claim that address in their profile"
            }
        }
    }
}

/// A person whose email lives only in their profile and could not be moved to where access looks
/// for it. **Their baja revokes nothing** until a human decides which row is them.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct UnresolvedAccessEmail {
    pub user_id: String,
    pub name: String,
    /// The address in `hub_user_profile.email` that could not be copied.
    pub profile_email: String,
    pub reason: AccessEmailConflict,
}

/// The rows the backfill left alone, for this hub. Empty is the normal answer.
///
/// Scoped by `hub_id` on `hub_user` itself since hub#497 gave it the column — subqueries included:
/// «another row already answers for this email» has to mean another row **of this hub**, or the
/// backfill would call an address resolved because the business next door happens to use it.
pub async fn unresolved(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<UnresolvedAccessEmail>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT u.id AS id, u.name AS name, TRIM(pr.email) AS profile_email, \
                    EXISTS (SELECT 1 FROM hub_user o \
                             WHERE o.hub_id = :hub_id AND o.id <> u.id \
                               AND LOWER(TRIM(COALESCE(o.email, ''))) = LOWER(TRIM(pr.email))) \
                      AS answered_elsewhere, \
                    EXISTS (SELECT 1 FROM hub_user_profile r \
                              JOIN hub_user ru ON ru.id = r.user_id AND ru.hub_id = r.hub_id \
                             WHERE r.hub_id = pr.hub_id AND r.user_id <> pr.user_id \
                               AND LOWER(TRIM(r.email)) = LOWER(TRIM(pr.email)) \
                               AND COALESCE(TRIM(ru.email), '') = '') AS claimed_twice \
               FROM hub_user u \
               JOIN hub_user_profile pr ON pr.user_id = u.id AND pr.hub_id = :hub_id \
              WHERE u.hub_id = :hub_id \
                AND COALESCE(TRIM(u.email), '') = '' AND TRIM(pr.email) <> '' \
              ORDER BY u.name, u.id",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .filter_map(|r| {
            let reason = if flag(&r["answered_elsewhere"]) {
                AccessEmailConflict::AnotherRowAnswersForIt
            } else if flag(&r["claimed_twice"]) {
                AccessEmailConflict::TwoProfilesClaimIt
            } else {
                // Nothing clashes: an email that lives only in a profile and belongs to nobody else
                // is a **local** person who typed one into `/api/profile`. They have no membership
                // to revoke, so there is nothing for a human to look at.
                return None;
            };
            Some(UnresolvedAccessEmail {
                user_id: r["id"].as_str().unwrap_or_default().to_string(),
                name: r["name"].as_str().unwrap_or_default().to_string(),
                profile_email: r["profile_email"].as_str().unwrap_or_default().to_string(),
                reason,
            })
        })
        .collect())
}

/// Postgres answers `EXISTS` with a boolean; accept an integer too, like the rest of the runtime.
fn flag(value: &serde_json::Value) -> bool {
    value
        .as_bool()
        .unwrap_or_else(|| value.as_i64().unwrap_or(0) != 0)
}

/// Prints [`unresolved`] on stderr at boot and returns how many there were. **Silent when there is
/// nothing** — a healthy hub must never learn this code exists.
pub async fn report_unresolved(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<usize> {
    report_unresolved_to(db, hub_id, &mut std::io::stderr()).await
}

/// [`report_unresolved`] against any sink, so what an operator actually reads is under test and not
/// just the count. A write that fails is ignored: a hub does not stop booting because its log did.
///
/// `+ Send` is load-bearing, not decoration: the sink is alive across the `await` of the query, so
/// without it this future is not `Send`, `ensure_system_tables` stops being `Send` with it, and
/// **every axum handler of the server stops compiling** (they must be `Handler`, which requires it).
pub async fn report_unresolved_to(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    out: &mut (dyn std::io::Write + Send),
) -> Result<usize> {
    let pending = unresolved(db, hub_id).await?;
    if pending.is_empty() {
        return Ok(0);
    }
    let _ = writeln!(
        out,
        "[access-email] {} user(s) have an email only in their profile that cannot be moved to \
         where access looks for it (hub#436): deactivating them does NOT revoke their membership. \
         Somebody has to decide which row is the person:",
        pending.len()
    );
    for row in &pending {
        let _ = writeln!(
            out,
            "[access-email]   · {} «{}» <{}> — {}",
            row.user_id,
            row.name,
            row.profile_email,
            row.reason.explain()
        );
    }
    Ok(pending.len())
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::fresh_db;
    use erplora_db::PgAdapter;

    const HUB: &str = "hub-access-email";

    async fn db() -> PgAdapter {
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, HUB).await.unwrap();
        db
    }

    fn p(pairs: &[(&str, serde_json::Value)]) -> Params {
        let mut m = Params::new();
        for (k, v) in pairs {
            m.insert((*k).into(), v.clone());
        }
        m
    }

    /// A `hub_user` with the access email given (`""` = the shape this whole module is about).
    async fn user(db: &PgAdapter, id: &str, name: &str, access_email: &str) {
        db.execute(
            "INSERT INTO hub_user (id, hub_id, name, pin_hash, role, cloud_user_id, is_active, created_at, email) \
               VALUES (:id, :hub_id, :name, '', 'employee', NULL, 1, :now, :email)",
            &p(&[
                ("id", json!(id)),
                ("hub_id", json!(HUB)),
                ("name", json!(name)),
                ("email", json!(access_email)),
                ("now", json!("2026-08-01T10:00:00Z")),
            ]),
        )
        .await
        .unwrap();
    }

    async fn profile(db: &PgAdapter, user_id: &str, email: &str) {
        db.execute(
            "INSERT INTO hub_user_profile (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
               VALUES (:hub_id, :id, '', '', :email, '', :now)",
            &p(&[
                ("hub_id", json!(HUB)),
                ("id", json!(user_id)),
                ("email", json!(email)),
                ("now", json!("2026-08-01T10:00:00Z")),
            ]),
        )
        .await
        .unwrap();
    }

    #[tokio::test]
    async fn a_hub_with_nothing_to_decide_reports_nothing() {
        let db = db().await;
        user(&db, "u1", "Ana", "ana@example.com").await;
        profile(&db, "u1", "ana@example.com").await;
        // A local person with no email anywhere, and one who typed their own into their profile:
        // neither has a membership to revoke, so neither is anybody's problem.
        user(&db, "u2", "Luis", "").await;
        user(&db, "u3", "Marta", "").await;
        profile(&db, "u3", "marta@example.com").await;
        // And two local people whose profile row exists with an EMPTY email — what `set_avatar`
        // writes, and what clearing the field leaves. Nothing links them, and "the empty address"
        // is not an address two people are fighting over: reporting them would put the whole shop
        // floor in the boot log of every hub and the real warning would stop being read.
        user(&db, "u4", "Nerea", "").await;
        profile(&db, "u4", "").await;
        user(&db, "u5", "Pau", "").await;
        profile(&db, "u5", "  ").await;

        assert!(unresolved(&db, HUB).await.unwrap().is_empty());
        assert_eq!(report_unresolved(&db, HUB).await.unwrap(), 0);
    }

    #[tokio::test]
    async fn a_profile_claiming_an_address_another_row_answers_for_is_reported() {
        let db = db().await;
        user(&db, "u1", "Ana", "ana@example.com").await;
        user(&db, "u2", "Bob", "").await;
        profile(&db, "u2", "ANA@example.com").await; // case must not hide it

        let pending = unresolved(&db, HUB).await.unwrap();

        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].user_id, "u2");
        assert_eq!(pending[0].name, "Bob");
        assert_eq!(pending[0].profile_email, "ANA@example.com");
        assert_eq!(
            pending[0].reason,
            AccessEmailConflict::AnotherRowAnswersForIt
        );
    }

    #[tokio::test]
    async fn two_profiles_claiming_one_address_are_both_reported() {
        let db = db().await;
        user(&db, "u1", "Ana Soto", "").await;
        profile(&db, "u1", "ana@example.com").await;
        user(&db, "u2", "Ana S.", "").await;
        profile(&db, "u2", "ana@example.com").await;

        let pending = unresolved(&db, HUB).await.unwrap();

        assert_eq!(pending.len(), 2);
        for row in &pending {
            assert_eq!(row.reason, AccessEmailConflict::TwoProfilesClaimIt);
        }
        // And the operator is told the RIGHT thing: the two reasons ask for different work — one is
        // «somebody else owns this address», the other «pick which of these two is the person».
        let mut out: Vec<u8> = Vec::new();
        assert_eq!(report_unresolved_to(&db, HUB, &mut out).await.unwrap(), 2);
        let text = String::from_utf8(out).unwrap();
        assert!(text.contains("two users claim that address"), "{text}");
        assert!(!text.contains("another user already answers"), "{text}");
    }

    /// A row that already carries **its own** access key is never reported, however its profile
    /// disagrees. That divergence is the design of hub#356 (`/api/profile` is the person's own
    /// address and must not move the key their membership hangs from), and the backfill has no
    /// business with a row it would never have touched: reporting it would cry wolf on every hub
    /// where somebody put a personal address in their profile.
    #[tokio::test]
    async fn a_row_that_already_has_its_own_access_key_is_never_reported() {
        let db = db().await;
        user(&db, "u1", "Ana", "ana@example.com").await;
        user(&db, "u2", "Bob", "bob@example.com").await;
        profile(&db, "u2", "ana@example.com").await; // Bob's profile claims Ana's address

        assert!(unresolved(&db, HUB).await.unwrap().is_empty());
    }

    /// What the operator reads has to name the person and say what to do something about — a count
    /// alone is not actionable.
    #[tokio::test]
    async fn the_report_names_the_row_the_address_and_the_reason() {
        let db = db().await;
        user(&db, "u1", "Ana", "ana@example.com").await;
        user(&db, "u2", "Bob Ruiz", "").await;
        profile(&db, "u2", "ana@example.com").await;

        let mut out: Vec<u8> = Vec::new();
        assert_eq!(report_unresolved_to(&db, HUB, &mut out).await.unwrap(), 1);

        let text = String::from_utf8(out).unwrap();
        assert!(text.contains("u2"), "{text}");
        assert!(text.contains("Bob Ruiz"), "{text}");
        assert!(text.contains("ana@example.com"), "{text}");
        assert!(text.contains("another user already answers"), "{text}");
        assert!(text.contains("does NOT revoke"), "{text}");
    }

    /// And it says nothing at all when there is nothing to say: a line in every hub's boot log is
    /// how a real warning stops being read.
    #[tokio::test]
    async fn the_report_writes_nothing_when_there_is_nothing() {
        let db = db().await;
        user(&db, "u1", "Ana", "ana@example.com").await;
        profile(&db, "u1", "ana@example.com").await;

        let mut out: Vec<u8> = Vec::new();
        assert_eq!(report_unresolved_to(&db, HUB, &mut out).await.unwrap(), 0);

        assert!(out.is_empty());
    }

    /// A profile from **another hub** is not this hub's business (a database shared by several hubs
    /// predates ADR-0201, but the runtime only ever speaks for its own `hub_id`).
    #[tokio::test]
    async fn a_profile_of_another_hub_is_not_reported() {
        let db = db().await;
        user(&db, "u1", "Ana", "ana@example.com").await;
        user(&db, "u2", "Bob", "").await;
        db.execute(
            "INSERT INTO hub_user_profile (hub_id, user_id, first_name, last_name, email, avatar_path, updated_at) \
               VALUES ('hub-OTHER', 'u2', '', '', 'ana@example.com', '', :now)",
            &p(&[("now", json!("2026-08-01T10:00:00Z"))]),
        )
        .await
        .unwrap();

        assert!(unresolved(&db, HUB).await.unwrap().is_empty());
    }

    /// Both reasons at once — a pair claiming one address while a third row already answers for it
    /// — reports the **more dangerous** one: somebody else's key is at stake, not just ambiguity.
    #[tokio::test]
    async fn an_address_that_is_both_claimed_twice_and_taken_reports_the_taken_reason() {
        let db = db().await;
        user(&db, "u1", "Ana", "ana@example.com").await;
        user(&db, "u2", "Bob", "").await;
        profile(&db, "u2", "ana@example.com").await;
        user(&db, "u3", "Carla", "").await;
        profile(&db, "u3", "ana@example.com").await;

        let pending = unresolved(&db, HUB).await.unwrap();

        assert_eq!(pending.len(), 2);
        for row in &pending {
            assert_eq!(row.reason, AccessEmailConflict::AnotherRowAnswersForIt);
        }
    }

    #[test]
    fn every_reason_explains_itself() {
        for reason in [
            AccessEmailConflict::AnotherRowAnswersForIt,
            AccessEmailConflict::TwoProfilesClaimIt,
        ] {
            assert!(!reason.explain().is_empty());
        }
    }

    #[test]
    fn flag_accepts_booleans_and_integers() {
        assert!(flag(&json!(true)));
        assert!(!flag(&json!(false)));
        assert!(flag(&json!(1)));
        assert!(!flag(&json!(0)));
        assert!(!flag(&json!(null)));
    }
}
