//! `_update_history` — what we changed on this hub, and from which version (hub#564).
//!
//! We update on our own, always, without asking ([ADR-0269](../../../architecture/00-overview/update-model.md)).
//! The other half of that bargain is **transparency**: the owner does not get to choose *when*, so
//! they are owed the answer to *what changed*. This table is that answer, and it is the only place
//! it can come from — the hub knows its **current** version and each module's **current** version,
//! and a current state cannot be subtracted from itself to produce a history.
//!
//! ## One table for both, on purpose
//!
//! A row is about a **component**: the core (`hub`) or a module (`module`). The screen shows
//! `ERPlora 1.1.3 → 1.1.4` on the same list as `Inventory 1.1.1 → 1.1.2`, so a `hub_module_update`
//! table would have been the wrong shape with its correction migration already behind it.
//!
//! ## What never goes in
//!
//! - **Anything that did not change.** A row exists because a version moved. A list of 24 modules
//!   where 23 say "no change" is noise, and noise stops being read.
//! - **Invented prose.** The row carries versions, an outcome and — when we have it — the error
//!   that made us go back. It never carries a changelog we made up. There is no owner-facing
//!   changelog source today (see the module doc), and writing one here would be fiction with a
//!   timestamp on it.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;
use crate::registry::{new_id, now_rfc3339};

/// What the owner calls the core. Not "the hub", not "the image", not a digest (ADR-0254): the
/// product has one name and this is it.
pub const CORE_NAME: &str = "ERPlora";

/// How many entries the history shows by default.
///
/// This is "what have you changed on me lately?", not an audit trail. A perpetual log is a log
/// nobody opens twice.
pub const DEFAULT_LIMIT: i64 = 20;

/// How far back the history reaches, in days.
pub const DEFAULT_MAX_AGE_DAYS: i64 = 90;

/// Which piece of the product a row is about.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Component {
    /// The core: the runtime binary, whose version comes from the tag (ADR-0280).
    Hub,
    /// A marketplace module.
    Module,
}

impl Component {
    pub fn as_str(self) -> &'static str {
        match self {
            Component::Hub => "hub",
            Component::Module => "module",
        }
    }
}

/// How a version transition ended.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    /// It moved forward and stayed there.
    Updated,
    /// It went back to where it was. **This is an entry too** — "went back to 1.1.3" is precisely
    /// the thing the owner is owed, and the thing we ask first on any incident.
    RolledBack,
    /// Not a change: the first version we ever saw for this component.
    ///
    /// Written so the **next** jump has a `from`, and never shown — on a hub that has not been
    /// updated yet, nothing changed, so the screen must be empty.
    Baseline,
    /// The new version failed **and** the old one did not come back: the hub is running without
    /// that app. `to` is empty because there is no version running, and saying one would be a lie.
    Lost,
}

impl Outcome {
    pub fn as_str(self) -> &'static str {
        match self {
            Outcome::Updated => "updated",
            Outcome::RolledBack => "rolled_back",
            Outcome::Baseline => "baseline",
            Outcome::Lost => "lost",
        }
    }
}

/// A transition to write down.
#[derive(Debug, Clone)]
pub struct Change<'a> {
    pub component: Component,
    /// `module_id` for a module; empty for the core (there is only one).
    pub id: &'a str,
    /// The name the owner reads — "Inventory", not `inventory` (ADR-0254). Stored with the row so
    /// it survives the module being uninstalled: a history that degrades into ids the moment an app
    /// is removed is a history about us, not about them.
    pub name: &'a str,
    pub from: &'a str,
    pub to: &'a str,
    pub outcome: Outcome,
    /// Why it went back, verbatim, when we have it. Empty is normal and means "we do not know" —
    /// never a sentence we made up.
    pub reason: &'a str,
}

/// A transition as it comes back out.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub component: String,
    pub id: String,
    pub name: String,
    pub from_version: String,
    pub to_version: String,
    pub outcome: String,
    pub reason: String,
    pub at: String,
}

/// Writes one transition down, and hands back the row as it will be read.
pub async fn record(db: &dyn DatabaseAdapter, hub_id: &str, change: Change<'_>) -> Result<Entry> {
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(new_id()));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("component".into(), json!(change.component.as_str()));
    p.insert("component_id".into(), json!(change.id));
    p.insert("name".into(), json!(change.name));
    p.insert("from_version".into(), json!(change.from));
    p.insert("to_version".into(), json!(change.to));
    p.insert("outcome".into(), json!(change.outcome.as_str()));
    p.insert("reason".into(), json!(change.reason));
    p.insert("now".into(), json!(now));
    db.execute(
        "INSERT INTO _update_history \
         (id, hub_id, component, component_id, name, from_version, to_version, outcome, reason, \
          created_at, created_by, updated_at, updated_by) \
         VALUES (:id, :hub_id, :component, :component_id, :name, :from_version, :to_version, \
                 :outcome, :reason, :now, '', :now, '')",
        &p,
    )
    .await?;

    Ok(Entry {
        component: change.component.as_str().to_string(),
        id: change.id.to_string(),
        name: change.name.to_string(),
        from_version: change.from.to_string(),
        to_version: change.to.to_string(),
        outcome: change.outcome.as_str().to_string(),
        reason: change.reason.to_string(),
        at: now,
    })
}

/// The last `limit` entries newer than `max_age_days`, newest first.
///
/// Baselines never come out: they are bookkeeping so the next jump has a `from`, not something that
/// happened to the owner.
pub async fn recent(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    limit: i64,
    max_age_days: i64,
) -> Result<Vec<Entry>> {
    let cutoff = (chrono::Utc::now() - chrono::Duration::days(max_age_days.max(0))).to_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("cutoff".into(), json!(cutoff));
    p.insert("limit".into(), json!(limit.max(0)));
    let res = db
        .query(
            "SELECT component, component_id, name, from_version, to_version, outcome, reason, \
                    created_at \
             FROM _update_history \
             WHERE hub_id = :hub_id AND deleted_at IS NULL AND outcome <> 'baseline' \
               AND created_at >= :cutoff \
             ORDER BY created_at DESC, id DESC \
             LIMIT :limit",
            &p,
        )
        .await?;

    Ok(res.rows.iter().map(row_to_entry).collect())
}

/// Column-name text, or empty. Every column of this table is `NOT NULL`, so a missing value means
/// a driver that did not map the column — reading it as `""` keeps a display query from failing.
fn text(row: &serde_json::Value, column: &str) -> String {
    row[column].as_str().unwrap_or_default().to_string()
}

fn row_to_entry(row: &serde_json::Value) -> Entry {
    Entry {
        component: text(row, "component"),
        id: text(row, "component_id"),
        name: text(row, "name"),
        from_version: text(row, "from_version"),
        to_version: text(row, "to_version"),
        outcome: text(row, "outcome"),
        reason: text(row, "reason"),
        at: text(row, "created_at"),
    }
}

/// What a module update attempt leaves in the history — or `None` when nothing changed.
///
/// **One mapping, shared by every writer** (the boot's unattended update and the per-module button
/// today). Two copies would be two answers to "did anything change?", and the screen is exactly
/// where that disagreement would surface: a hub claiming it updated something it did not.
///
/// `attempted` is the version we were going for. It is needed because
/// [`crate::module_update::Outcome`] only carries where we ENDED, and a rollback that cannot name
/// what it rolled back from is half a sentence.
pub fn from_module_outcome<'a>(
    module_id: &'a str,
    name: &'a str,
    attempted: &'a str,
    outcome: &'a crate::module_update::Outcome,
) -> Option<Change<'a>> {
    use crate::module_update::Outcome as Attempt;

    let base = Change {
        component: Component::Module,
        id: module_id,
        name,
        from: "",
        to: "",
        outcome: Outcome::Updated,
        reason: "",
    };

    match outcome {
        // Nothing moved, so nothing is written. This is what keeps a nightly restart from filling
        // the screen with non-events.
        Attempt::AlreadyThere(_) => None,
        Attempt::Updated { from, to } => Some(Change { from, to, ..base }),
        // Told the way rule 5 asks for: "went back to 1.1.1 because 1.1.2 did not start". `from` is
        // the version we tried, `to` is where it actually ended — the same shape as every other row.
        Attempt::RolledBack { stayed_on, error } => Some(Change {
            from: attempted,
            to: stayed_on,
            outcome: Outcome::RolledBack,
            reason: error,
            ..base
        }),
        Attempt::Lost { error, .. } => Some(Change {
            from: attempted,
            to: "",
            outcome: Outcome::Lost,
            reason: error,
            ..base
        }),
    }
}

/// The name to put on an entry, in the reader's language.
///
/// Stored name and live translation are not redundant: the stored one is the **durable** answer
/// (it survives the module being uninstalled, which is exactly when an id would leak onto the
/// screen), and the module's own `locales/<lang>.json` is the **current** one, which has to win
/// while the module is there or the history would say "Inventory" on a screen that says
/// "Inventario" everywhere else.
pub fn display_name(registry: &crate::registry::Registry, entry: &Entry, locale: &str) -> String {
    if entry.component == Component::Hub.as_str() {
        return entry.name.clone();
    }
    registry.module_name_localized(&entry.id, &entry.name, locale)
}

/// The last version we wrote down for a component, whatever the outcome (baselines included —
/// that is what they are for).
async fn last_seen(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    component: Component,
    id: &str,
) -> Result<Option<String>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("component".into(), json!(component.as_str()));
    p.insert("component_id".into(), json!(id));
    let res = db
        .query(
            "SELECT to_version FROM _update_history \
             WHERE hub_id = :hub_id AND component = :component AND component_id = :component_id \
               AND deleted_at IS NULL \
             ORDER BY created_at DESC, id DESC LIMIT 1",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["to_version"].as_str().map(str::to_string)))
}

/// Notices what the **core** version did since the last boot, and writes it down if it moved.
///
/// This is the only way the hub can know: nobody tells it that it was updated. The image is
/// re-resolved outside the container, the task is replaced, and the new binary boots reporting a
/// different number. Comparing that number with the last one we wrote is the whole mechanism — and
/// it is also what makes an **automatic rollback visible**, because Swarm reverting a bad release
/// looks, from in here, exactly like a version going backwards.
///
/// Returns the entry when something changed, `None` on the first boot ever and on every restart
/// that changed nothing.
pub async fn note_core_version(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    current: &str,
) -> Result<Option<Entry>> {
    let core = Change {
        component: Component::Hub,
        id: "",
        name: CORE_NAME,
        from: "",
        to: current,
        outcome: Outcome::Baseline,
        // Nobody tells the hub why its own image moved: the decision was taken outside the
        // container. An empty reason is the honest one — see the rollback sentence in the UI.
        reason: "",
    };

    let Some(previous) = last_seen(db, hub_id, Component::Hub, "").await? else {
        // First boot that can remember. Not a change: nothing happened to this hub yet.
        record(db, hub_id, core).await?;
        return Ok(None);
    };

    if previous == current {
        return Ok(None); // a restart is not an update.
    }

    // Backwards means the release was reverted. From in here that is all a rollback ever looks
    // like, and calling it "updated" would be a lie in the one place the owner goes to find out
    // why something broke.
    let outcome = match (
        crate::module_update::parse(&previous),
        crate::module_update::parse(current),
    ) {
        (Some(before), Some(now)) if now < before => Outcome::RolledBack,
        // Unparseable on either side: we know it MOVED, and that is what we say. Guessing a
        // direction from two strings we cannot compare would be worse than the plain fact.
        _ => Outcome::Updated,
    };

    let entry = record(
        db,
        hub_id,
        Change {
            from: &previous,
            outcome,
            ..core
        },
    )
    .await?;
    Ok(Some(entry))
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::TestDb;
    use erplora_db::PgAdapter;

    /// A hub whose system schema is in place (this table is a system migration).
    async fn history_db() -> PgAdapter {
        let db = TestDb::new().await.adapter().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        db
    }

    fn module_change<'a>(id: &'a str, name: &'a str, from: &'a str, to: &'a str) -> Change<'a> {
        Change {
            component: Component::Module,
            id,
            name,
            from,
            to,
            outcome: Outcome::Updated,
            reason: "",
        }
    }

    /// A hub nobody has updated shows NOTHING — not 24 rows saying "no change".
    ///
    /// This is the definition of done of hub#564 and the rule that carries the value: the first
    /// boot has to leave a mark so the *next* jump knows where it came from, and that mark must not
    /// be visible, because nothing happened to the owner yet.
    #[tokio::test]
    async fn a_hub_that_was_never_updated_shows_nothing() {
        let db = history_db().await;

        let first = note_core_version(&db, "h1", "1.0.0").await.unwrap();

        assert!(
            first.is_none(),
            "the first version we ever see is not a change: nothing was updated"
        );
        assert!(
            recent(&db, "h1", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
                .await
                .unwrap()
                .is_empty(),
            "an untouched hub must show an EMPTY history, not a baseline row"
        );
    }

    /// The core moving is one entry, and it says where it came from.
    ///
    /// "ERPlora 1.0.1" tells the owner nothing; "1.0.0 → 1.0.1" tells them what we did.
    #[tokio::test]
    async fn a_core_jump_is_one_entry_that_says_where_it_came_from() {
        let db = history_db().await;
        note_core_version(&db, "h1", "1.0.0").await.unwrap();

        let jump = note_core_version(&db, "h1", "1.0.1")
            .await
            .unwrap()
            .expect("a version that moved is a change");

        assert_eq!(jump.from_version, "1.0.0");
        assert_eq!(jump.to_version, "1.0.1");
        assert_eq!(jump.outcome, Outcome::Updated.as_str());
        assert_eq!(
            jump.name, CORE_NAME,
            "the owner reads a product name, not «the image»"
        );

        let shown = recent(&db, "h1", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
            .await
            .unwrap();
        assert_eq!(shown.len(), 1, "one jump, one row");
        assert_eq!(shown[0].to_version, "1.0.1");
    }

    /// Restarting is not updating.
    ///
    /// A hub reboots nightly. If every boot wrote a row, the history would be a list of restarts
    /// with the same number on both sides — the exact noise rule 1 exists to keep out.
    #[tokio::test]
    async fn restarting_on_the_same_version_is_not_an_entry() {
        let db = history_db().await;
        note_core_version(&db, "h1", "1.0.0").await.unwrap();
        note_core_version(&db, "h1", "1.0.1").await.unwrap();

        for _ in 0..3 {
            assert!(
                note_core_version(&db, "h1", "1.0.1")
                    .await
                    .unwrap()
                    .is_none(),
                "a restart on the same version changed nothing"
            );
        }

        assert_eq!(
            recent(&db, "h1", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
                .await
                .unwrap()
                .len(),
            1,
            "three restarts must not add three rows"
        );
    }

    /// Going backwards is a ROLLBACK, and it is an entry of its own (rule 5).
    ///
    /// From inside the container an automatic revert is indistinguishable from any other boot: the
    /// binary just reports a lower number. Calling that "updated to 1.1.3" would be a lie in the one
    /// place the owner goes to find out why something broke.
    #[tokio::test]
    async fn going_back_is_told_as_a_rollback_not_as_an_update() {
        let db = history_db().await;
        note_core_version(&db, "h1", "1.1.3").await.unwrap();
        note_core_version(&db, "h1", "1.1.4").await.unwrap();

        let back = note_core_version(&db, "h1", "1.1.3")
            .await
            .unwrap()
            .expect("coming back down is a change");

        assert_eq!(back.outcome, Outcome::RolledBack.as_str());
        assert_eq!(back.from_version, "1.1.4");
        assert_eq!(back.to_version, "1.1.3");
    }

    /// The core and a module live in the SAME list, newest first.
    ///
    /// This is why the table is per component and not `hub_module_update`.
    #[tokio::test]
    async fn the_core_and_a_module_share_one_list() {
        let db = history_db().await;
        note_core_version(&db, "h1", "1.1.3").await.unwrap();
        note_core_version(&db, "h1", "1.1.4").await.unwrap();
        record(
            &db,
            "h1",
            module_change("inventory", "Inventory", "1.1.1", "1.1.2"),
        )
        .await
        .unwrap();

        let shown = recent(&db, "h1", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
            .await
            .unwrap();

        assert_eq!(shown.len(), 2);
        assert_eq!(shown[0].id, "inventory", "newest first");
        assert_eq!(shown[0].component, Component::Module.as_str());
        assert_eq!(shown[0].name, "Inventory");
        assert_eq!(shown[1].component, Component::Hub.as_str());
    }

    /// A rollback keeps WHY, verbatim.
    ///
    /// "went back to 1.1.1 because 1.1.2 did not start" is the sentence the owner is owed, and the
    /// error behind it is the first thing we ask for on an incident. It is stored, never invented:
    /// an empty reason means we did not know, and stays empty.
    #[tokio::test]
    async fn a_rollback_keeps_the_error_that_caused_it() {
        let db = history_db().await;
        record(
            &db,
            "h1",
            Change {
                component: Component::Module,
                id: "inventory",
                name: "Inventory",
                from: "1.1.2",
                to: "1.1.1",
                outcome: Outcome::RolledBack,
                reason: "migration 004_add_stock.sql failed: column already exists",
            },
        )
        .await
        .unwrap();

        let shown = recent(&db, "h1", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
            .await
            .unwrap();

        assert_eq!(shown[0].outcome, Outcome::RolledBack.as_str());
        assert_eq!(
            shown[0].reason,
            "migration 004_add_stock.sql failed: column already exists"
        );
    }

    /// The history is SHORT (rule 4): the last N, and nothing older than the window.
    #[tokio::test]
    async fn the_history_is_short_and_does_not_reach_back_forever() {
        let db = history_db().await;
        for n in 0..8 {
            record(
                &db,
                "h1",
                module_change(
                    "sales",
                    "Sales",
                    &format!("2.0.{n}"),
                    &format!("2.0.{}", n + 1),
                ),
            )
            .await
            .unwrap();
        }

        let shown = recent(&db, "h1", 3, DEFAULT_MAX_AGE_DAYS).await.unwrap();
        assert_eq!(shown.len(), 3, "only the last N entries");
        assert_eq!(shown[0].to_version, "2.0.8", "and they are the NEWEST ones");

        // An entry from before the window is out, however few rows there are.
        let old = now_rfc3339();
        let mut p = Params::new();
        p.insert("id".into(), json!(new_id()));
        p.insert("hub_id".into(), json!("h1"));
        p.insert("at".into(), json!(old.replace("2026", "2019")));
        db.execute(
            "INSERT INTO _update_history \
             (id, hub_id, component, component_id, name, from_version, to_version, outcome, \
              reason, created_at, created_by, updated_at, updated_by) \
             VALUES (:id, :hub_id, 'module', 'ancient', 'Ancient', '0.9.0', '1.0.0', 'updated', \
                     '', :at, '', :at, '')",
            &p,
        )
        .await
        .unwrap();

        let windowed = recent(&db, "h1", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
            .await
            .unwrap();
        assert!(
            windowed.iter().all(|e| e.id != "ancient"),
            "an entry older than the window is not «lately»"
        );
        assert_eq!(
            windowed.len(),
            8,
            "…and the ones inside it are all still there"
        );
    }

    /// One hub never reads another hub's history.
    ///
    /// The neighbour is ALIVE here on purpose: asserting an empty result against an empty table
    /// proves nothing at all, because a query that returns nothing to anybody would pass it.
    #[tokio::test]
    async fn a_hub_only_reads_its_own_history() {
        let db = history_db().await;
        record(
            &db,
            "h1",
            module_change("inventory", "Inventory", "1.0.0", "1.1.0"),
        )
        .await
        .unwrap();
        record(&db, "h2", module_change("sales", "Sales", "2.0.0", "2.1.0"))
            .await
            .unwrap();

        let mine = recent(&db, "h1", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
            .await
            .unwrap();
        let theirs = recent(&db, "h2", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
            .await
            .unwrap();

        assert_eq!(
            mine.len(),
            1,
            "the neighbour is alive, and I still see mine"
        );
        assert_eq!(mine[0].id, "inventory");
        assert_eq!(theirs.len(), 1, "…and they see theirs");
        assert_eq!(theirs[0].id, "sales");
    }

    /// The owner reads the app's name in THEIR language, and an uninstalled app still has a name.
    ///
    /// Two halves of rule 3. The live translation has to win while the module is installed —
    /// otherwise the history says "Inventory" on a screen where every other surface says
    /// "Inventario" — and the stored name has to hold the line when the module is gone, because a
    /// row that decays into `inventory` the day somebody uninstalls it is a row about us.
    #[test]
    fn a_module_is_named_the_way_the_owner_reads_it() {
        use crate::manifest::ModuleLocale;
        use std::collections::HashMap;

        let mut registry = crate::registry::Registry::new();
        let mut locales = HashMap::new();
        locales.insert(
            "es".to_string(),
            ModuleLocale {
                name: Some("Inventario".into()),
                navigation: HashMap::new(),
                ..Default::default()
            },
        );
        registry.set_locales("inventory", locales);

        let installed = Entry {
            component: Component::Module.as_str().into(),
            id: "inventory".into(),
            name: "Inventory".into(),
            from_version: "1.1.1".into(),
            to_version: "1.1.2".into(),
            outcome: Outcome::Updated.as_str().into(),
            reason: String::new(),
            at: now_rfc3339(),
        };
        assert_eq!(display_name(&registry, &installed, "es"), "Inventario");
        assert_eq!(display_name(&registry, &installed, "en"), "Inventory");

        let uninstalled = Entry {
            id: "sales".into(),
            name: "Sales & POS".into(),
            ..installed.clone()
        };
        assert_eq!(
            display_name(&registry, &uninstalled, "es"),
            "Sales & POS",
            "a module that is gone keeps the name we wrote down, never its id"
        );

        let core = Entry {
            component: Component::Hub.as_str().into(),
            id: String::new(),
            name: CORE_NAME.into(),
            ..installed
        };
        assert_eq!(display_name(&registry, &core, "es"), CORE_NAME);
    }

    /// Every way a module update can end, turned into a row — or into nothing.
    ///
    /// This mapping is the seam the three writers share (the boot, the button, and any future one).
    /// Two copies of it would be two answers to "did anything change?", and the screen is the place
    /// where that disagreement would surface as a hub that says it updated something it did not.
    #[test]
    fn each_ending_of_an_update_becomes_the_row_it_deserves() {
        use crate::module_update::Outcome as Attempt;

        // Already there: NOTHING changed, so nothing is written. This is rule 1, and it is what
        // keeps a nightly restart from filling the screen with non-events.
        let already = Attempt::AlreadyThere("1.1.2".into());
        assert!(
            from_module_outcome("inventory", "Inventory", "1.1.2", &already).is_none(),
            "a module that was already on that version did not change"
        );

        let updated = Attempt::Updated {
            from: "1.1.1".into(),
            to: "1.1.2".into(),
        };
        let moved = from_module_outcome("inventory", "Inventory", "1.1.2", &updated)
            .expect("an update that happened is an entry");
        assert_eq!((moved.from, moved.to), ("1.1.1", "1.1.2"));
        assert_eq!(moved.outcome, Outcome::Updated);
        assert_eq!(
            moved.name, "Inventory",
            "the name the owner reads, not the id"
        );

        // Rolled back: it is told the way rule 5 asks for it — "went back to 1.1.1 because 1.1.2
        // did not start". So `from` is the version we TRIED and `to` is where it actually ended,
        // the same shape as any other row, and the error that caused it is kept verbatim.
        let reverted = Attempt::RolledBack {
            stayed_on: "1.1.1".into(),
            error: "migration 004 failed".into(),
        };
        let back = from_module_outcome("inventory", "Inventory", "1.1.2", &reverted)
            .expect("a rollback is an entry");
        assert_eq!((back.from, back.to), ("1.1.2", "1.1.1"));
        assert_eq!(back.outcome, Outcome::RolledBack);
        assert_eq!(back.reason, "migration 004 failed");

        // Lost: the new one failed AND the old one did not come back, so the hub is serving without
        // the app. That is the single worst thing that can happen to the owner here, and it is
        // exactly the one that must not be the silent case.
        let gone = Attempt::Lost {
            module: "inventory".into(),
            error: "zip corrupt".into(),
        };
        let lost = from_module_outcome("inventory", "Inventory", "1.1.2", &gone)
            .expect("losing an app is the LAST thing that should go unrecorded");
        assert_eq!(lost.outcome, Outcome::Lost);
        assert_eq!(lost.from, "1.1.2");
        assert_eq!(
            lost.to, "",
            "there is no version running: saying one would be a lie"
        );
        assert_eq!(lost.reason, "zip corrupt");
    }

    /// A deleted row stops being shown (soft-delete, like every other table).
    #[tokio::test]
    async fn a_soft_deleted_entry_is_not_shown() {
        let db = history_db().await;
        record(
            &db,
            "h1",
            module_change("inventory", "Inventory", "1.0.0", "1.1.0"),
        )
        .await
        .unwrap();

        let mut p = Params::new();
        p.insert("at".into(), json!(now_rfc3339()));
        db.execute(
            "UPDATE _update_history SET deleted_at = :at WHERE hub_id = 'h1'",
            &p,
        )
        .await
        .unwrap();

        assert!(recent(&db, "h1", DEFAULT_LIMIT, DEFAULT_MAX_AGE_DAYS)
            .await
            .unwrap()
            .is_empty());
    }
}
