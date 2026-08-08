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
use crate::registry::Registry;
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

/// Why a hub that went live is not operating (ADR-0259 D2, hub#550). Derived, never stored.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockedReason {
    /// Nobody is left to comply: no installed **and active** module fulfils the hub's regime.
    ProviderMissing,
    /// `system_id` is not this hub: these rows were written by a different installation, so the
    /// chain they hang from is not ours to continue (ADR-0202 `NumeroInstalacion = hub_id`).
    InstallationMismatch,
}

impl BlockedReason {
    /// The stable rejection code the UI programs against (hub#556 turns these into refusals).
    pub fn code(self) -> &'static str {
        match self {
            BlockedReason::ProviderMissing => "fiscal.provider_missing",
            BlockedReason::InstallationMismatch => "fiscal.installation_mismatch",
        }
    }
}

/// **What this hub owes right now**: the stored [`FiscalStatus`] plus what has to be derived.
///
/// The only difference from the stored status is [`FiscalMode::Blocked`], and it exists precisely
/// because it is *not* stored: a state that gets written down outlives the bug that wrote it and
/// then has to be repaired by hand. Derived, it is fixed by fixing the fact — reinstall the
/// provider and the hub is `ACTIVE` again on the next read, with nobody editing a row.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FiscalMode {
    NotRequired,
    Unconfigured,
    Ready,
    Active,
    /// `ACTIVE` on paper, not operating in fact.
    Blocked(BlockedReason),
    Closed,
}

/// The installed **and active** modules that fulfil `regime` for `country` (ADR-0259 D5/D6).
///
/// The core **counts**; it never picks. Two providers of one regime are a spare, not a conflict,
/// and which one a hub uses is the user's business — hence a slice and not an `Option`.
///
/// Inactive counts as absent, and that is the point: a deactivated module runs no listener, which
/// is indistinguishable — for the purpose of complying — from not being installed at all.
pub fn providers_of<'a>(
    registry: &'a Registry,
    country: &str,
    regime: &str,
) -> Vec<&'a crate::manifest::Manifest> {
    if regime.trim().is_empty() {
        return Vec::new();
    }
    registry
        .installed
        .iter()
        .filter(|m| registry.is_active(&m.id) && m.fulfils_regime(country, regime))
        .collect()
}

/// The events a healthy provider says it listens to — what the core LEARNS while it can ask
/// (ADR-0259 D4). Sorted and deduplicated so the stored set is stable and comparing it is cheap.
///
/// The runtime does not know what `invoice.created` means, and does not need to: it knows *the
/// provider of this hub's regime said it was listening to it while it was healthy*. That is the
/// whole trick — it never names business, and it never names a module.
pub fn learned_trigger_events(registry: &Registry, country: &str, regime: &str) -> Vec<String> {
    let mut events: Vec<String> = providers_of(registry, country, regime)
        .iter()
        .flat_map(|m| m.events.listen.keys().cloned())
        .collect();
    events.sort();
    events.dedup();
    events
}

/// Resolves the **effective** mode of `profile` against what is actually mounted (ADR-0259 D2/D4).
///
/// Only a hub that went live can be [`FiscalMode::Blocked`]: before the go-live nothing is
/// anchored, so a missing provider is a task, not an emergency. Turning a hub that never emitted
/// into a blocked one would stop a till over a checklist item.
pub fn determine_fiscal_mode(
    profile: &FiscalProfile,
    registry: &Registry,
    hub_id: &str,
) -> FiscalMode {
    match profile.status {
        FiscalStatus::NotRequired => FiscalMode::NotRequired,
        FiscalStatus::Unconfigured => FiscalMode::Unconfigured,
        FiscalStatus::Ready => FiscalMode::Ready,
        FiscalStatus::Closed => FiscalMode::Closed,
        FiscalStatus::Active => {
            // The installation check comes first: if these rows belong to somebody else, whether a
            // provider happens to be mounted is beside the point — continuing another hub's chain
            // is worse than not emitting.
            if !profile.system_id.is_empty() && profile.system_id != hub_id {
                return FiscalMode::Blocked(BlockedReason::InstallationMismatch);
            }
            if providers_of(registry, &profile.country_code, &profile.fiscal_system).is_empty() {
                return FiscalMode::Blocked(BlockedReason::ProviderMissing);
            }
            FiscalMode::Active
        }
    }
}

/// Resolves the profile against the world and returns the effective mode (ADR-0259 D2/D4, hub#550).
///
/// Runs on every boot, after the registry has been rehydrated — that is the first moment the two
/// halves of the answer (what the hub owes, and who is mounted to comply) are both available.
/// Idempotent by construction: everything it writes is recomputed from the same inputs.
///
/// Three things happen, in this order:
///
/// 1. [`ensure`] resolves the country and the regime (and bootstraps the row on a new hub).
/// 2. **`READY` is computed, not remembered**: identity ∧ certificate ∧ at least one provider
///    mounted and active. It is the same condition the go-live will ask for (hub#551), evaluated
///    once — a checklist and a gate that disagree about "is this configured?" turn one of them into
///    a lie. It moves `UNCONFIGURED ⇄ READY` and **never touches** `ACTIVE`/`CLOSED`: after the
///    go-live the answer is not derived from settings any more.
/// 3. **The trigger events are refreshed while there is somebody to ask.** A provider that is
///    updated — or replaced by another of the same regime — moves the set. When there is nobody,
///    the stored set is left exactly as it was: that is the memory hub#556 refuses with.
pub async fn refresh(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
) -> Result<FiscalMode> {
    let profile = ensure(db, hub_id).await?;
    let providers = providers_of(registry, &profile.country_code, &profile.fiscal_system);

    // Learnt while healthy, remembered when gone: only overwrite when somebody taught us something.
    if !providers.is_empty() {
        let learned =
            learned_trigger_events(registry, &profile.country_code, &profile.fiscal_system);
        if learned != profile.fiscal_trigger_events {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("events".into(), json!(json!(learned).to_string()));
            db.execute(
                "UPDATE _hub_fiscal_profile SET fiscal_trigger_events = :events \
                 WHERE hub_id = :hub_id",
                &p,
            )
            .await?;
        }
    }

    // The go-live froze the answer; settings do not move it any more.
    if !profile.status.is_frozen() && profile.status != FiscalStatus::NotRequired {
        let settings = crate::settings::get_all(db, hub_id).await.unwrap_or(json!({}));
        let filled = |key: &str| {
            settings
                .get(key)
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .trim()
                .is_empty()
                .eq(&false)
        };
        // Degrading to `false` on error keeps this failing CLOSED: a hub whose certificate cannot
        // be read is not ready to emit.
        let has_certificate = crate::certificate::can_sign(db, hub_id).await.unwrap_or(false);
        let ready = filled("business_tax_id")
            && filled("business_legal_name")
            && has_certificate
            && !providers.is_empty();
        let wanted = if ready {
            FiscalStatus::Ready
        } else {
            FiscalStatus::Unconfigured
        };
        if wanted != profile.status {
            let mut p = Params::new();
            p.insert("hub_id".into(), json!(hub_id));
            p.insert("status".into(), json!(wanted.as_str()));
            db.execute(
                "UPDATE _hub_fiscal_profile SET status = :status WHERE hub_id = :hub_id",
                &p,
            )
            .await?;
        }
    }

    let profile = reload(db, hub_id).await?;
    Ok(determine_fiscal_mode(&profile, registry, hub_id))
}

/// The stable rejection code of the provider lock (ADR-0259 D5). ABI público: la UI programa
/// contra el código, no contra el mensaje.
pub const NO_PROVIDER_LEFT: &str = "fiscal.no_provider_left";

/// **With the profile `ACTIVE`, the hub does not end up with NOBODY complying** (ADR-0259 D5).
///
/// `leaving` is the whole set that would go — the target of a deactivation **plus everything the
/// cascade would drag with it** (ADR-0128). It is computed before touching anything, because
/// turning off `invoice` drags `verifactu` with it: gating only the target would leave the back
/// door open.
///
/// This is **not** "this module is nailed down": it is "you do not end up with nobody". With two
/// providers of the regime installed, removing one is not blocked — somebody still complies, and
/// which one a hub uses is not the runtime's opinion to have.
///
/// The difference with R2 (hub#314), which is kept and complements this one:
///
/// | | R2 | this |
/// |---|---|---|
/// | who decides | the engine is asked (`pending_obligations`) | **the core, and it asks nobody** |
/// | why | only the engine knows what it owes the tax authority | a module cannot have a vote on whether it may be removed |
/// | covers | the `READY` stretch, and `ACTIVE` with a queue | `ACTIVE`, always — queue or no queue |
///
/// R2 alone was not enough precisely because it looks at the **pending queue**: with the queue
/// empty the provider leaves without a word, and from then on the hub sells and nobody generates
/// the record. An empty queue protects the past; the damage is done by the NEXT sales.
///
/// A hub that is already without a provider is not held hostage either: if there was nothing to
/// lose, removing an unrelated module is not what broke it (it already reads `BLOCKED`).
pub fn ensure_provider_remains(
    profile: &FiscalProfile,
    registry: &Registry,
    leaving: &[String],
) -> Result<()> {
    if profile.status != FiscalStatus::Active {
        return Ok(()); // Before the go-live nothing is anchored: this is a checklist item.
    }
    let providers = providers_of(registry, &profile.country_code, &profile.fiscal_system);
    if providers.is_empty() {
        return Ok(()); // Already without one — that is `BLOCKED`, not something this can prevent.
    }
    let remaining = providers
        .iter()
        .filter(|m| !leaving.iter().any(|id| id == &m.id))
        .count();
    if remaining > 0 {
        return Ok(());
    }
    Err(RuntimeError::Domain {
        code: NO_PROVIDER_LEFT.to_string(),
        message: format!(
            "this hub files under `{}` and this would leave it with no module fulfilling that \
             regime: install another provider first, or close the fiscal period",
            profile.fiscal_system
        ),
    })
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
///
/// **Tolerant of the table not being there** (same shape as [`crate::settings::country_code_of`]):
/// a hub that has not run its system migrations has no profile, and that is the answer — not an
/// error to propagate. It matters because this is read from the module-lifecycle path (the provider
/// lock below), and a runtime built straight over an empty database must keep reporting *its own*
/// error — "module not installed" — instead of a missing-relation from the fiscal side.
pub async fn load(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<FiscalProfile>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let Ok(res) = db
        .query(
            "SELECT country_code, taxpayer_id, fiscal_system, status, environment, activated_at, \
                    first_record_at, system_id, fiscal_trigger_events, can_go_live, needs_review \
             FROM _hub_fiscal_profile WHERE hub_id = :hub_id",
            &p,
        )
        .await
    else {
        return Ok(None);
    };
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

    /// Writes any `hub_settings` key.
    async fn set_setting(db: &dyn DatabaseAdapter, hub_id: &str, key: &str, value: &str) {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("key".into(), json!(key));
        p.insert("value".into(), json!(value));
        p.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at) \
             VALUES (:hub_id, :key, :value, :now) \
             ON CONFLICT (hub_id, key) DO UPDATE SET value = EXCLUDED.value",
            &p,
        )
        .await
        .unwrap();
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

    // ── The effective mode: what is derived, and why it is derived (ADR-0259 D2/D4, hub#550) ──

    /// A registry holding `modules`, each `(id, fiscal_regime_json, listens_to, active)`.
    fn registry_with(modules: &[(&str, Option<serde_json::Value>, &[&str], bool)]) -> Registry {
        use crate::registry::ModuleStatus;
        let mut reg = Registry::new();
        for (id, fiscal, listens, active) in modules {
            let listen: serde_json::Map<String, serde_json::Value> = listens
                .iter()
                .map(|e| ((*e).to_string(), json!({ "command": "x.noop" })))
                .collect();
            let mut manifest = json!({
                "id": id, "name": id, "version": "1.0.0",
                "events": { "listen": listen }
            });
            if let Some(f) = fiscal {
                manifest["fiscal_regime"] = f.clone();
            }
            reg.installed.push(serde_json::from_value(manifest).expect("manifest parses"));
            reg.status.insert(
                (*id).to_string(),
                if *active { ModuleStatus::Active } else { ModuleStatus::Inactive },
            );
        }
        reg
    }

    /// A profile in `status`, for a Spanish hub owing VeriFactu.
    fn profile_in(status: FiscalStatus, system_id: &str) -> FiscalProfile {
        FiscalProfile {
            country_code: "ES".into(),
            taxpayer_id: String::new(),
            fiscal_system: "verifactu".into(),
            status,
            environment: "testing".into(),
            activated_at: String::new(),
            first_record_at: String::new(),
            system_id: system_id.into(),
            fiscal_trigger_events: Vec::new(),
            can_go_live: true,
            needs_review: false,
        }
    }

    /// 🔴 **The case the whole ADR exists for.** The hub went live and the provider went away —
    /// uninstalled, failed to mount after a restore, or left inactive by a bug. The stored status
    /// still says `ACTIVE` and must not be believed.
    #[test]
    fn active_with_no_provider_mounted_is_blocked() {
        let empty = registry_with(&[]);
        assert_eq!(
            determine_fiscal_mode(&profile_in(FiscalStatus::Active, "hub-es"), &empty, "hub-es"),
            FiscalMode::Blocked(BlockedReason::ProviderMissing)
        );
    }

    /// With a provider mounted and active, `ACTIVE` means what it says.
    #[test]
    fn active_with_a_provider_is_active() {
        let reg = registry_with(&[(
            "verifactu",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created"],
            true,
        )]);
        assert_eq!(
            determine_fiscal_mode(&profile_in(FiscalStatus::Active, "hub-es"), &reg, "hub-es"),
            FiscalMode::Active
        );
    }

    /// **An inactive provider is not a provider.** The module is installed and its rows are there,
    /// and it will not run a single listener — which is, for the purpose of complying, the same as
    /// not being there.
    #[test]
    fn a_deactivated_provider_does_not_count() {
        let reg = registry_with(&[(
            "verifactu",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created"],
            false,
        )]);
        assert_eq!(
            determine_fiscal_mode(&profile_in(FiscalStatus::Active, "hub-es"), &reg, "hub-es"),
            FiscalMode::Blocked(BlockedReason::ProviderMissing)
        );
    }

    /// A provider of ANOTHER regime does not comply with this one. The core counts providers of the
    /// regime the hub owes, not modules that happen to be fiscal.
    #[test]
    fn a_provider_of_another_regime_does_not_count() {
        let reg = registry_with(&[(
            "facturx",
            Some(json!({ "country": "FR", "regime": "facturx" })),
            &["invoice.created"],
            true,
        )]);
        assert_eq!(
            determine_fiscal_mode(&profile_in(FiscalStatus::Active, "hub-es"), &reg, "hub-es"),
            FiscalMode::Blocked(BlockedReason::ProviderMissing)
        );
    }

    /// **Two providers of one regime are a spare, not a conflict.** The core counts; which one the
    /// hub uses is not its decision (that is why the profile stores no `module_id`).
    #[test]
    fn two_providers_of_the_same_regime_both_count() {
        let reg = registry_with(&[
            ("verifactu", Some(json!({ "country": "ES", "regime": "verifactu" })), &["invoice.created"], true),
            ("otro", Some(json!({ "country": "ES", "regime": "verifactu" })), &["invoice.created"], true),
        ]);
        assert_eq!(providers_of(&reg, "ES", "verifactu").len(), 2);
        assert_eq!(
            determine_fiscal_mode(&profile_in(FiscalStatus::Active, "hub-es"), &reg, "hub-es"),
            FiscalMode::Active
        );
    }

    /// The database says it belongs to a different installation. Continuing a chain somebody else
    /// opened is worse than not emitting, so this is checked **before** looking for a provider.
    #[test]
    fn a_profile_from_another_installation_is_blocked() {
        let reg = registry_with(&[(
            "verifactu",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created"],
            true,
        )]);
        assert_eq!(
            determine_fiscal_mode(&profile_in(FiscalStatus::Active, "hub-otro"), &reg, "hub-es"),
            FiscalMode::Blocked(BlockedReason::InstallationMismatch)
        );
    }

    /// **Only a hub that went live can be blocked.** Before the go-live nothing is anchored, so a
    /// missing provider is a task on a checklist — blocking a till over it would be absurd.
    #[test]
    fn a_hub_that_never_went_live_is_never_blocked() {
        let empty = registry_with(&[]);
        for status in [FiscalStatus::NotRequired, FiscalStatus::Unconfigured, FiscalStatus::Ready] {
            let mode = determine_fiscal_mode(&profile_in(status, "hub-es"), &empty, "hub-es");
            assert!(
                !matches!(mode, FiscalMode::Blocked(_)),
                "{status:?} must not derive to blocked, got {mode:?}"
            );
        }
    }

    /// The core LEARNS from a healthy provider what starts a fiscal chain. It never learns from a
    /// module that is not one, however many events that module listens to — silence never counts as
    /// complying (hub#555).
    #[test]
    fn only_a_declared_provider_teaches_the_trigger_events() {
        let reg = registry_with(&[
            ("verifactu", Some(json!({ "country": "ES", "regime": "verifactu" })), &["invoice.created"], true),
            ("inventory", None, &["sale.completed"], true),
        ]);
        assert_eq!(
            learned_trigger_events(&reg, "ES", "verifactu"),
            vec!["invoice.created".to_string()]
        );
    }

    /// Two providers teach the UNION, deduplicated and stable: the set is compared on every boot.
    #[test]
    fn the_learnt_set_is_the_union_and_it_is_stable() {
        let reg = registry_with(&[
            ("verifactu", Some(json!({ "country": "ES", "regime": "verifactu" })), &["invoice.created"], true),
            ("otro", Some(json!({ "country": "ES", "regime": "verifactu" })), &["sale.completed", "invoice.created"], true),
        ]);
        assert_eq!(
            learned_trigger_events(&reg, "ES", "verifactu"),
            vec!["invoice.created".to_string(), "sale.completed".to_string()]
        );
    }

    /// 🔴 **Learnt while healthy, REMEMBERED when gone.** Deriving the set live from the registry
    /// would give the exact opposite behaviour — no module, no listener, no trigger, and the till
    /// sells — and the moment the trigger matters most is the moment there is nobody left to ask.
    #[tokio::test]
    async fn the_trigger_events_survive_the_provider_that_taught_them() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;
        let with_provider = registry_with(&[(
            "verifactu",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created"],
            true,
        )]);
        refresh(&db, &with_provider, "hub-es").await.unwrap();
        assert_eq!(
            load(&db, "hub-es").await.unwrap().unwrap().fiscal_trigger_events,
            vec!["invoice.created".to_string()]
        );

        // The provider is gone. The core still knows what starts a fiscal chain here.
        refresh(&db, &registry_with(&[]), "hub-es").await.unwrap();
        assert_eq!(
            load(&db, "hub-es").await.unwrap().unwrap().fiscal_trigger_events,
            vec!["invoice.created".to_string()],
            "this memory is what lets hub#556 refuse when there is nobody to ask"
        );
    }

    /// A replacement provider of the same regime **refreshes** the set while it is healthy: the
    /// freeze only exists for the case where there is nobody to ask.
    #[tokio::test]
    async fn a_healthy_provider_refreshes_the_set() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;
        let first = registry_with(&[(
            "verifactu",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created"],
            true,
        )]);
        refresh(&db, &first, "hub-es").await.unwrap();

        let replacement = registry_with(&[(
            "otro",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created", "sale.completed"],
            true,
        )]);
        refresh(&db, &replacement, "hub-es").await.unwrap();

        assert_eq!(
            load(&db, "hub-es").await.unwrap().unwrap().fiscal_trigger_events,
            vec!["invoice.created".to_string(), "sale.completed".to_string()]
        );
    }

    /// `READY` is **computed**, not remembered: identity ∧ certificate ∧ a provider mounted. With
    /// no certificate the hub stays `UNCONFIGURED`, which is the same answer the checklist gives —
    /// one condition, one place, so a gate and a checklist cannot disagree.
    #[tokio::test]
    async fn without_a_certificate_a_hub_is_not_ready() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;
        set_setting(&db, "hub-es", "business_tax_id", "B12345678").await;
        set_setting(&db, "hub-es", "business_legal_name", "Bar Pepe SL").await;
        let reg = registry_with(&[(
            "verifactu",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created"],
            true,
        )]);

        assert_eq!(refresh(&db, &reg, "hub-es").await.unwrap(), FiscalMode::Unconfigured);
    }

    /// And `READY` goes back to `UNCONFIGURED` when a condition stops holding — before the go-live
    /// nothing is anchored, so there is simply something to do again.
    #[tokio::test]
    async fn losing_the_provider_before_go_live_returns_to_unconfigured() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;
        ensure(&db, "hub-es").await.unwrap(); // the row has to exist before it can be moved
        // A hub sitting at READY (however it got there) with nothing mounted is not ready.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-es"));
        db.execute(
            "UPDATE _hub_fiscal_profile SET status = 'READY' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();

        assert_eq!(
            refresh(&db, &registry_with(&[]), "hub-es").await.unwrap(),
            FiscalMode::Unconfigured
        );
    }

    /// **`refresh` never moves a hub that went live.** After the go-live the answer stops being
    /// derived from settings: the chain is anchored, and a missing certificate is a problem to
    /// report, not a reason to quietly un-activate a SIF.
    #[tokio::test]
    async fn refresh_does_not_walk_an_active_hub_backwards() {
        let db = fresh_db().await;
        booted_hub(&db, "hub-es", Some("ES")).await;
        ensure(&db, "hub-es").await.unwrap(); // the row has to exist before it can be moved
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-es"));
        db.execute(
            "UPDATE _hub_fiscal_profile SET status = 'ACTIVE' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();

        let mode = refresh(&db, &registry_with(&[]), "hub-es").await.unwrap();

        assert_eq!(mode, FiscalMode::Blocked(BlockedReason::ProviderMissing));
        assert_eq!(
            load(&db, "hub-es").await.unwrap().unwrap().status,
            FiscalStatus::Active,
            "BLOCKED is a reading; the stored status is untouched"
        );
    }

    /// 🔴 **Leer el perfil no puede ser la razón de que falle otra cosa.** Un runtime construido
    /// sobre una BD vacía —sin migraciones de sistema— tiene que seguir contestando SU error
    /// («módulo no instalado»), no un 42P01 del lado fiscal. Lo pilló el gate al añadir el candado:
    /// `module_retention_gate_e2e` construye exactamente ese runtime.
    #[tokio::test]
    async fn reading_the_profile_of_a_hub_without_system_tables_is_not_an_error() {
        let db = fresh_db().await;
        assert!(load(&db, "hub-sin-migrar").await.unwrap().is_none());
    }

    // ── D5: con el perfil ACTIVE, no te quedas sin proveedor (hub#553) ────────────────────────

    fn code_of(err: &RuntimeError) -> String {
        match err {
            RuntimeError::Domain { code, .. } => code.clone(),
            other => other.to_string(),
        }
    }

    /// 🔴 **Lo que R2 no cubre.** El módulo no debe nada (cola vacía), así que la gate de
    /// retención lo deja marchar sin rechistar — y a partir de ahí el hub sigue vendiendo y nadie
    /// genera el registro. La cola vacía protege el pasado; el daño lo hacen las ventas
    /// siguientes.
    #[test]
    fn the_last_provider_of_an_active_hub_cannot_leave() {
        let reg = registry_with(&[(
            "verifactu",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created"],
            true,
        )]);
        let err = ensure_provider_remains(
            &profile_in(FiscalStatus::Active, "hub-es"),
            &reg,
            &["verifactu".to_string()],
        )
        .expect_err("quedarse sin nadie que cumpla se rechaza");
        assert_eq!(code_of(&err), NO_PROVIDER_LEFT);
    }

    /// **No es «este módulo está clavado»: es «no te quedas sin nadie».** Con dos proveedores del
    /// mismo régimen, quitar uno pasa — sigue habiendo quien cumpla, y el core no tiene por qué
    /// opinar sobre cuál. Sustituir un proveedor por otro es cosa del usuario.
    #[test]
    fn with_two_providers_removing_one_is_allowed() {
        let reg = registry_with(&[
            ("verifactu", Some(json!({ "country": "ES", "regime": "verifactu" })), &["invoice.created"], true),
            ("otro", Some(json!({ "country": "ES", "regime": "verifactu" })), &["invoice.created"], true),
        ]);
        assert!(ensure_provider_remains(
            &profile_in(FiscalStatus::Active, "hub-es"),
            &reg,
            &["verifactu".to_string()],
        )
        .is_ok());
    }

    /// 🔴 **La cascada también pasa por aquí** (ADR-0128). Apagar `invoice` arrastraría al
    /// proveedor, así que el conjunto ENTERO que caería se comprueba **antes** de tocar nada: si
    /// uno solo está bloqueado, no cae ninguno. Gatear solo el objetivo dejaría la puerta de atrás
    /// abierta.
    #[test]
    fn the_cascade_that_would_drag_the_last_provider_is_refused_too() {
        let reg = registry_with(&[
            ("verifactu", Some(json!({ "country": "ES", "regime": "verifactu" })), &["invoice.created"], true),
            ("invoice", None, &[], true),
        ]);
        let err = ensure_provider_remains(
            &profile_in(FiscalStatus::Active, "hub-es"),
            &reg,
            &["invoice".to_string(), "verifactu".to_string()],
        )
        .expect_err("la cascada no puede dejar al hub sin proveedor");
        assert_eq!(code_of(&err), NO_PROVIDER_LEFT);
    }

    /// Quitar un módulo que **no** es proveedor no se bloquea nunca: el candado protege la
    /// capacidad de cumplir, no el inventario de módulos.
    #[test]
    fn removing_a_module_that_is_not_a_provider_is_never_blocked() {
        let reg = registry_with(&[
            ("verifactu", Some(json!({ "country": "ES", "regime": "verifactu" })), &["invoice.created"], true),
            ("inventory", None, &["sale.completed"], true),
        ]);
        assert!(ensure_provider_remains(
            &profile_in(FiscalStatus::Active, "hub-es"),
            &reg,
            &["inventory".to_string()],
        )
        .is_ok());
    }

    /// **Antes del go-live no hay candado.** Nada está anclado todavía: quitar el proveedor es
    /// volver a tener una tarea en la checklist, no una emergencia. R2 sigue cubriendo ese tramo
    /// (la cola sí puede tener trabajo).
    #[test]
    fn before_go_live_there_is_no_lock() {
        let reg = registry_with(&[(
            "verifactu",
            Some(json!({ "country": "ES", "regime": "verifactu" })),
            &["invoice.created"],
            true,
        )]);
        for status in [FiscalStatus::Unconfigured, FiscalStatus::Ready] {
            assert!(
                ensure_provider_remains(&profile_in(status, "hub-es"), &reg, &["verifactu".to_string()])
                    .is_ok(),
                "{status:?} no ancla nada todavía"
            );
        }
    }

    /// Un hub que YA está sin proveedor no queda de rehén: eso ya se lee como `BLOCKED`, y quitar
    /// un módulo cualquiera no es lo que lo rompió.
    #[test]
    fn a_hub_already_without_a_provider_is_not_held_hostage() {
        let reg = registry_with(&[("inventory", None, &["sale.completed"], true)]);
        assert!(ensure_provider_remains(
            &profile_in(FiscalStatus::Active, "hub-es"),
            &reg,
            &["inventory".to_string()],
        )
        .is_ok());
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
