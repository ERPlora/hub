//! **The hub's fiscal profile** — the CORE decides THAT there is an obligation (ADR-0259 D1/D6,
//! hub#549).
//!
//! The rule this module exists to enforce:
//!
//! > A fiscal obligation can never depend on a module being installed, enabled, licensed or
//! > available. The module implements **HOW** to comply; the CORE determines **THAT** compliance is
//! > owed.
//!
//! Today the whole of fiscalisation hangs off a module. Uninstall it, deactivate it, restore the
//! hub somewhere the module fails to mount, or hit a bug that leaves it inactive, and the till
//! keeps selling **without anybody generating the record**. The retention gate R2
//! ([`crate::native::NativeHandler::pending_obligations`], hub#314) only looks at the pending
//! queue: with an empty queue the module leaves without a word. Every one of those paths ends in
//! the same place — money taken, no invoicing record — which is worse than the orphan the AEAT FAQ
//! forbids, because there is not even a record to be orphaned.
//!
//! So the fact *"this hub owes VeriFactu"* moves out of the module and into two system tables that
//! no module can uninstall:
//!
//! - `_hub_fiscal_profile` — singleton per hub, **the authority**. What regime applies, what
//!   identifier the chain is anchored to, which environment it emits to, whether it has gone live.
//! - `_hub_fiscal_regime_registry` — **data, not code**: `(country_code, regime_key, since, note)`.
//!   Seeded with a single row, `ES → verifactu`. A country with no row resolves to
//!   [`FiscalStatus::NotRequired`] and the hub is asked for nothing.
//!
//! ## Two things the profile deliberately does NOT store
//!
//! **It does not store WHICH module complies.** It stores the *regime*, and the core asks *"is any
//! installed and active module fulfilling it?"* — the same shape the ADR-0203 gate already uses for
//! the `certificate` capability, which likewise never names `verifactu`. Sealing a `module_id`
//! would drag the runtime into a decision that is not its own: the marketplace may carry N modules
//! that do the same job, replacing one with another is the user's call, and the core only has to
//! count. It is also less code — no column, no provider-swap transition.
//!
//! **The active state is not called `VERIFACTU_ACTIVE`.** The discriminator is `fiscal_system`.
//! Putting "VERIFACTU" in the name of a core state is putting Spain in the core, which is exactly
//! what the rule forbids. The Spanish user's screen says "VeriFactu activo"; the core says
//! [`FiscalStatus::Active`].
//!
//! ## A deliberate exception to "a host with no business inside"
//!
//! [`crate::commands`] §1 says the runtime holds no business logic, and the regime registry bends
//! that. It is declared here rather than smuggled in: the runtime does not implement VeriFactu and
//! does not know what a `RegistroAlta` is — it knows *that in ES an obligation exists and what it
//! is called*. That fact **cannot** live in a module, because that is literally what the rule
//! forbids: if it lives there, uninstalling the module deletes the obligation.
//!
//! Adding France the day it matters is **one row plus a module** that declares
//! `fiscal_regime: {country: "FR", regime: "facturx"}`. Zero core changes.
//!
//! ## What this module does NOT do yet
//!
//! Nothing here rejects anything. [`ensure`] resolves and persists the profile at boot and that is
//! all: deriving the effective mode (including `BLOCKED`, which is **derived and never stored**) is
//! hub#550, and the gate that actually refuses a sale is hub#556.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;

/// The state machine of the fiscal profile (ADR-0259 D2).
///
/// `BLOCKED` is **not** in this enum on purpose: it is derived on every boot and on every gate from
/// `Active` ∧ (no mounted provider ∨ mismatched `system_id`), never persisted. A derived state that
/// gets stored outlives the bug that wrote it and then has to be "repaired" by hand — precisely
/// what one does not want in the safety half of a fiscal system.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FiscalStatus {
    /// The hub's country has no regime in the registry: nothing is owed.
    NotRequired,
    /// There is an obligation and something is still missing.
    Unconfigured,
    /// Identity ∧ certificate ∧ a provider installed and active. Emits to `testing`.
    Ready,
    /// The SIF operates in production.
    Active,
    /// Cessation of activity: read and export, never emit.
    Closed,
}

impl FiscalStatus {
    /// The stored form. Stable ABI: it travels to the UI, which translates against the code.
    pub fn as_str(self) -> &'static str {
        match self {
            FiscalStatus::NotRequired => "NOT_REQUIRED",
            FiscalStatus::Unconfigured => "UNCONFIGURED",
            FiscalStatus::Ready => "READY",
            FiscalStatus::Active => "ACTIVE",
            FiscalStatus::Closed => "CLOSED",
        }
    }

    /// Parses the stored form. An unknown value degrades to [`FiscalStatus::Unconfigured`] rather
    /// than to `NotRequired`: a row nobody can read must not be read as "owes nothing".
    pub fn parse(raw: &str) -> Self {
        match raw {
            "NOT_REQUIRED" => FiscalStatus::NotRequired,
            "READY" => FiscalStatus::Ready,
            "ACTIVE" => FiscalStatus::Active,
            "CLOSED" => FiscalStatus::Closed,
            _ => FiscalStatus::Unconfigured,
        }
    }

    /// Whether the regime and the country are frozen — i.e. the hub already went live, so the
    /// chain is anchored and re-resolving from settings would move the anchor under it.
    pub fn is_frozen(self) -> bool {
        matches!(self, FiscalStatus::Active | FiscalStatus::Closed)
    }
}

/// The `_hub_fiscal_profile` row: one per hub, the authority on what this hub owes.
///
/// Instants are RFC3339 `TEXT` and `""` means "never", like the rest of the system tables; flags
/// are `INTEGER` 0/1 (the `erplora_db` row contract), read here as `bool`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FiscalProfile {
    /// ISO-3166-1 alpha-2. Mirror of `hub_settings.country_code`, frozen once `ACTIVE`.
    pub country_code: String,
    /// The identifier the chain is **anchored to**, frozen at go-live. Not a duplicate of
    /// `hub_settings.business_tax_id`: that one is the editable business identity (ADR-0061), this
    /// one is the frozen copy the emitted chain hangs from. When they diverge the hub has a
    /// problem and somebody has to be told — not silently pick one (hub#554).
    pub taxpayer_id: String,
    /// The regime key (`verifactu`; `""` when none applies).
    pub fiscal_system: String,
    pub status: FiscalStatus,
    /// `testing` | `production`. Rises from the module to the core in hub#551.
    pub environment: String,
    /// Go-live stamp; `""` until then. Write-once.
    pub activated_at: String,
    /// First record that left towards the real tax authority; `""` until then. Write-once, and the
    /// thing that makes go-live irreversible — the damage is done by the record, not by the toggle.
    pub first_record_at: String,
    /// The `NumeroInstalacion` = `hub_id` invariant of ADR-0202, written down so it can be checked
    /// while the hub is running instead of only in a test (hub#558).
    pub system_id: String,
    /// Events that start a fiscal chain, learnt from a healthy provider and **remembered** when it
    /// disappears (hub#556).
    pub fiscal_trigger_events: Vec<String>,
    /// `false` on demo hubs (R5, hub#315/#552): a throwaway hub must never emit for real.
    pub can_go_live: bool,
    /// Something the core could not decide and refuses to guess (ADR-0249).
    pub needs_review: bool,
}

/// Resolves the regime owed by `country_code`, or `""` if that country has no row.
///
/// The registry is keyed `(country_code, regime_key)` and carries `since` so a country that changes
/// regime is one more row rather than a schema change; the answer is the most recent row whose
/// `since` has already arrived. `since = ''` (the seeded shape) always has.
pub async fn regime_for_country(db: &dyn DatabaseAdapter, country_code: &str) -> Result<String> {
    let mut p = Params::new();
    p.insert("country_code".into(), json!(country_code.to_uppercase()));
    p.insert("now".into(), json!(now_rfc3339()));
    let res = db
        .query(
            "SELECT regime_key FROM _hub_fiscal_regime_registry \
             WHERE country_code = :country_code AND since <= :now \
             ORDER BY since DESC LIMIT 1",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["regime_key"].as_str())
        .unwrap_or_default()
        .to_string())
}

/// Reads the profile of `hub_id`, or `None` if it has not been bootstrapped yet.
pub async fn load(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<FiscalProfile>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT country_code, taxpayer_id, fiscal_system, status, environment, activated_at, \
                    first_record_at, system_id, fiscal_trigger_events, can_go_live, needs_review \
             FROM _hub_fiscal_profile WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
    let Some(row) = res.rows.first() else {
        return Ok(None);
    };
    let text = |key: &str| row[key].as_str().unwrap_or_default().to_string();
    // Flags travel as INTEGER 0/1 (row contract): anything that is not 1 is false.
    let flag = |key: &str| row[key].as_i64().unwrap_or(0) == 1;
    Ok(Some(FiscalProfile {
        country_code: text("country_code"),
        taxpayer_id: text("taxpayer_id"),
        fiscal_system: text("fiscal_system"),
        status: FiscalStatus::parse(&text("status")),
        environment: text("environment"),
        activated_at: text("activated_at"),
        first_record_at: text("first_record_at"),
        system_id: text("system_id"),
        // A JSON array in a TEXT column. Unreadable content degrades to "no triggers known" rather
        // than to an error: this is read on every boot and a hub that will not start is worse than
        // one whose trigger set is refreshed by the next healthy provider (hub#556 relearns it).
        fiscal_trigger_events: serde_json::from_str(&text("fiscal_trigger_events"))
            .unwrap_or_default(),
        can_go_live: flag("can_go_live"),
        needs_review: flag("needs_review"),
    }))
}

/// Resolves and persists the profile of `hub_id`. Idempotent, runs on **every** boot.
///
/// A brand-new hub is born with its profile already resolved from `hub_settings.country_code`:
/// `ES` → `UNCONFIGURED` with `fiscal_system = verifactu`, any other country → `NOT_REQUIRED`.
///
/// It **re-resolves while the profile is not frozen**, and that is not decoration: on the very
/// first boot the country may not be known yet (`HUB_SEED_SQL` is applied *after*
/// `ensure_system_tables`, and provisioning seeds `country_code` from `Hub.country`), so a French
/// hub would otherwise be born Spanish and stay Spanish for ever. Once the hub is `ACTIVE` the
/// country and the regime are frozen — the chain is anchored and moving it under a live chain is
/// the bug, not the fix.
///
/// One direction is barred outright: a hub that has already emitted (`first_record_at`) never falls
/// back to `NOT_REQUIRED`, whatever its settings say afterwards.
pub async fn ensure(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<FiscalProfile> {
    let country = crate::settings::country_code_of(db, hub_id).await?;
    let regime = regime_for_country(db, &country).await?;

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("country_code".into(), json!(country));
    p.insert("fiscal_system".into(), json!(regime));

    let Some(current) = load(db, hub_id).await? else {
        // Birth. `system_id` is the ADR-0202 invariant `NumeroInstalacion = hub_id`, written down
        // now so a hub restored under a different id can notice (hub#558).
        let status = if regime.is_empty() {
            FiscalStatus::NotRequired
        } else {
            FiscalStatus::Unconfigured
        };
        p.insert("status".into(), json!(status.as_str()));
        db.execute(
            "INSERT INTO _hub_fiscal_profile \
               (hub_id, country_code, fiscal_system, status, system_id) \
             VALUES (:hub_id, :country_code, :fiscal_system, :status, :hub_id) \
             ON CONFLICT (hub_id) DO NOTHING",
            &p,
        )
        .await?;
        return reload(db, hub_id).await;
    };

    if current.status.is_frozen()
        || (current.country_code == country && current.fiscal_system == regime)
    {
        return Ok(current);
    }

    // The chain is anchored once something has been emitted. If the settings now ask for a
    // different regime than the one the emitted chain hangs from, the core CANNOT decide which is
    // right — dropping the obligation would make an emitted chain evaporate, and switching regime
    // under it would move the anchor. So it keeps what it has and says so (ADR-0249, hub#436):
    // what cannot be decided is signalled, never guessed.
    if !current.first_record_at.is_empty() && current.fiscal_system != regime {
        db.execute(
            "UPDATE _hub_fiscal_profile SET needs_review = 1 WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
        return reload(db, hub_id).await;
    }

    // Not live yet: the profile follows the hub's country. An obligation that ARRIVES lifts a
    // `NOT_REQUIRED` hub into `UNCONFIGURED`; one that goes away drops it back. Anything already
    // further along (`READY`) keeps its progress, because what changed is the country, not the
    // certificate or the identity it had gathered.
    let status = if regime.is_empty() {
        FiscalStatus::NotRequired
    } else if current.status == FiscalStatus::NotRequired {
        FiscalStatus::Unconfigured
    } else {
        current.status
    };
    p.insert("status".into(), json!(status.as_str()));
    db.execute(
        "UPDATE _hub_fiscal_profile \
         SET country_code = :country_code, fiscal_system = :fiscal_system, status = :status \
         WHERE hub_id = :hub_id",
        &p,
    )
    .await?;
    reload(db, hub_id).await
}

/// Reads back a profile that must exist because we just wrote it. A `None` here is a broken
/// invariant, not a state a caller should have to handle.
async fn reload(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<FiscalProfile> {
    load(db, hub_id).await?.ok_or_else(|| {
        RuntimeError::Other(format!(
            "the fiscal profile of `{hub_id}` could not be read back after being written"
        ))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::fresh_db;

    /// Boots a hub the way `Runtime::ensure_system_tables` does, optionally with a country set.
    async fn booted_hub(db: &dyn DatabaseAdapter, hub_id: &str, country: Option<&str>) {
        // Baseline v0 first: the versioned catalogue ALTERs `hub_module` and `hub_session`, so
        // those have to exist before `apply` (same order as `Runtime::ensure_system_tables`).
        crate::installer::ensure_hub_module_table(db).await.unwrap();
        crate::identity::ensure_tables(db).await.unwrap();
        crate::system_migrations::apply(db, hub_id).await.unwrap();
        if let Some(c) = country {
            set_country(db, hub_id, c).await;
        }
    }

    /// Writes `hub_settings.country_code`, the way provisioning's seed does.
    async fn set_country(db: &dyn DatabaseAdapter, hub_id: &str, country: &str) {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("value".into(), json!(country));
        p.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at) \
             VALUES (:hub_id, 'country_code', :value, :now) \
             ON CONFLICT (hub_id, key) DO UPDATE SET value = EXCLUDED.value",
            &p,
        )
        .await
        .unwrap();
    }

    /// **A Spanish hub is born owing VeriFactu, and it owes it before any module is installed.**
    /// This is the whole point of the ADR: the obligation is a fact about the hub, not a
    /// consequence of somebody having installed something.
    #[tokio::test]
    async fn a_spanish_hub_is_born_owing_verifactu_with_no_module_installed() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;

        let profile = ensure(&db, "hub-es").await.unwrap();

        assert_eq!(profile.fiscal_system, "verifactu");
        assert_eq!(profile.status, FiscalStatus::Unconfigured);
        assert_eq!(profile.country_code, "ES");
        // The installation number invariant of ADR-0202, written down instead of only asserted in a
        // test: this is what lets a restored hub notice it is not the one that emitted (hub#558).
        assert_eq!(profile.system_id, "hub-es");
        assert_eq!(profile.environment, "testing");
        assert_eq!(profile.first_record_at, "", "nothing has been emitted yet");
        assert!(profile.can_go_live, "a normal hub may go live");
        assert!(!profile.needs_review);
    }

    /// A country with no row in the registry owes nothing — and that is the *default*, so shipping
    /// Spain to the whole fleet is not a thing that can happen by accident.
    #[tokio::test]
    async fn a_hub_in_a_country_with_no_regime_owes_nothing() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-pt", Some("PT")).await;

        let profile = ensure(&db, "hub-pt").await.unwrap();

        assert_eq!(profile.status, FiscalStatus::NotRequired);
        assert_eq!(profile.fiscal_system, "");
    }

    /// **The profile survives a restart and is not rewritten.** `ensure` runs on every boot, so it
    /// has to be idempotent: a second pass returns the same row, not a second one.
    #[tokio::test]
    async fn a_second_boot_returns_the_same_profile() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;

        let first = ensure(&db, "hub-es").await.unwrap();
        let second = ensure(&db, "hub-es").await.unwrap();
        assert_eq!(first, second);

        let rows = db
            .query("SELECT hub_id FROM _hub_fiscal_profile", &Params::new())
            .await
            .unwrap();
        assert_eq!(rows.rows.len(), 1, "the profile is a singleton per hub");
    }

    /// **The country can still arrive late.** On the first boot of a provisioned hub the seed that
    /// writes `country_code` has not run yet (`HUB_SEED_SQL` is applied *after* the system tables),
    /// so the profile is born on the default. If it never re-resolved, a French hub would be
    /// Spanish for ever — and a Spanish one would never pick up its obligation.
    #[tokio::test]
    async fn a_country_that_arrives_after_the_first_boot_is_picked_up() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-late", None).await;
        let born = ensure(&db, "hub-late").await.unwrap();
        assert_eq!(born.country_code, "ES", "the setting's default (ADR-0085)");

        // The provisioning seed lands afterwards and says this hub is Portuguese.
        set_country(&db, "hub-late", "PT").await;

        let after = ensure(&db, "hub-late").await.unwrap();
        assert_eq!(after.country_code, "PT");
        assert_eq!(after.status, FiscalStatus::NotRequired);
        assert_eq!(after.fiscal_system, "");
    }

    /// **Once the hub has gone live the country and the regime are frozen.** The chain is anchored
    /// to them; re-resolving from a setting somebody edited afterwards would move the anchor under
    /// a live chain, which is the failure this table exists to prevent.
    #[tokio::test]
    async fn an_active_profile_is_not_re_resolved_from_settings() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;
        ensure(&db, "hub-es").await.unwrap();

        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-es"));
        db.execute(
            "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = 'production', \
               activated_at = '2026-08-08T10:00:00Z', taxpayer_id = 'B12345678' \
             WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
        set_country(&db, "hub-es", "PT").await;

        let after = ensure(&db, "hub-es").await.unwrap();
        assert_eq!(after.country_code, "ES", "frozen at go-live");
        assert_eq!(after.fiscal_system, "verifactu");
        assert_eq!(after.status, FiscalStatus::Active);
        assert_eq!(after.taxpayer_id, "B12345678");
    }

    /// **A hub that already emitted never falls back to "owes nothing".** Changing the country
    /// setting after the fact is not a way to make an emitted chain disappear; the profile keeps
    /// the obligation and flags itself for a human (ADR-0249: what cannot be decided is signalled,
    /// not guessed).
    #[tokio::test]
    async fn a_hub_that_already_emitted_never_falls_back_to_not_required() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;
        ensure(&db, "hub-es").await.unwrap();

        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-es"));
        // READY, so it is not frozen by status — but it has emitted.
        db.execute(
            "UPDATE _hub_fiscal_profile SET status = 'READY', \
               first_record_at = '2026-08-08T10:00:00Z' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
        set_country(&db, "hub-es", "PT").await;

        let after = ensure(&db, "hub-es").await.unwrap();
        assert_ne!(
            after.status,
            FiscalStatus::NotRequired,
            "an emitted chain does not evaporate because a setting changed"
        );
        assert_eq!(after.fiscal_system, "verifactu");
        assert!(
            after.needs_review,
            "the core cannot decide this one, so it says so instead of choosing"
        );
    }

    /// The registry is data: one row today, `ES → verifactu`. Adding a country is a row, not a
    /// release.
    #[tokio::test]
    async fn the_regime_registry_is_seeded_with_spain_only() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;

        assert_eq!(regime_for_country(&db, "ES").await.unwrap(), "verifactu");
        assert_eq!(regime_for_country(&db, "es").await.unwrap(), "verifactu");
        assert_eq!(regime_for_country(&db, "FR").await.unwrap(), "");
    }

    /// [`load`] is a read: it does not create the row. A caller that wants the profile to exist
    /// asks for [`ensure`], and everything else can tell "not bootstrapped" from "owes nothing".
    #[tokio::test]
    async fn load_does_not_create_the_profile() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;

        assert!(load(&db, "hub-es").await.unwrap().is_none());
        ensure(&db, "hub-es").await.unwrap();
        assert!(load(&db, "hub-es").await.unwrap().is_some());
    }
}
