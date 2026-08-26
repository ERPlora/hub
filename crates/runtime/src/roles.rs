//! The hub's role **catalogue** and its **per-hub activation** (paso 2b, hub#352).
//!
//! hub#351 gave a module the right to DECLARE the business roles its vertical needs (`roles[]`:
//! `key` + `label` + `extends`). This is what the hub does with them: it aggregates the base
//! catalogue of the core ([`BASE_ROLES`]) with what the installed modules declare, and the
//! administrator switches on the ones this business actually needs. Install the kitchen module →
//! Kitchen shows up; uninstall it → it goes away.
//!
//! Three properties hold the design together:
//!
//! 1. **A declared role is OPT-IN.** It lands in the catalogue `active: false`; installing a
//!    module never hands a hub a role it did not ask for. That is also what leaves room for the
//!    blueprint to pre-activate the right set per vertical (hub#354) instead of every hub getting
//!    every role of every module it installs.
//! 2. **Activation never MINTS a role.** [`set_active`] only accepts a key an installed module
//!    declares: the write door is not a place to invent role keys. Without that guard the
//!    activation endpoint would be a way to create roles out of thin air, which is exactly what
//!    the install-time validation of hub#351 refuses to allow a manifest to do.
//! 3. **A declared role never administers the hub.** `extends` is validated at install time
//!    against the NON-administrative base roles, and [`crate::hub_users::is_admin_role`] keeps
//!    answering `false` for every declared key. Switching a role on is not a way around either:
//!    activation decides whether a role is *live*, never *how far it reaches*.
//!
//! **Where the base roles sit.** `admin`/`manager`/`employee` are always in the catalogue and
//! always active; they cannot be switched off. They are the frozen contract the 24 published
//! modules write their `role_permissions` against, and a hub whose base roles could be switched
//! off would be a hub nobody can work in.
//!
//! **What activation does NOT do (deliberately).** It does not change how permissions are
//! resolved: those are still the union of what the **active modules** grant to the key
//! ([`crate::identity::permissions_for_role`]), which is the property the PLAN states. Activation
//! decides whether a role can be **handed to a person** ([`ensure_assignable`]) and whether the
//! administrator sees it as live. Uninstalling the module that granted the permissions already
//! removes them, so an orphan role narrows down to nothing on its own — never the other way round.
//!
//! Persistence: table `hub_role_activation(hub_id, role_key, …)`, **system migration v13**. A row
//! means "switched on in this hub"; no row means off. Scoped by `hub_id` like the rest of the
//! system schema: one hub switching a role on says nothing about the hub next door.
use std::collections::{BTreeMap, BTreeSet};

use erplora_db::{DatabaseAdapter, Params};
use serde::Serialize;
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::hub_users::{is_admin_role, is_base_role, BASE_ROLES};
use crate::registry::{now_rfc3339, Registry};

/// Where a role of the catalogue comes from.
///
/// Adjacently tagged so the UI can branch on `kind` and still read the module that declared it:
/// `{"kind":"core"}` · `{"kind":"module","module_id":"kitchen"}` · `{"kind":"in_use"}`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", content = "module_id", rename_all = "snake_case")]
pub enum RoleSource {
    /// The frozen base catalogue of the core ([`BASE_ROLES`]).
    Core,
    /// Declared by the `roles[]` of an installed **active** module.
    Module(String),
    /// **Not** in the catalogue: no installed module declares it, but some active user still
    /// carries it — the leftover of an uninstalled module or a role typed by hand before there
    /// was a catalogue. Listed so it stays visible to the administrator; never active.
    InUse,
}

/// A role of the hub's catalogue.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CatalogRole {
    /// The key `role_permissions` grants against and `hub_user.role` stores.
    pub key: String,
    /// Human name, **English canonical** (ADR-0055): the base roles carry the label of the PLAN,
    /// a declared role the `label` of its manifest, and the translation travels in the UI's i18n
    /// or in the module's `locales/<lang>.json`.
    pub label: String,
    /// Base role it resolves to. A base role hangs from itself; an orphan (`InUse`) from nothing.
    pub extends: String,
    pub source: RoleSource,
    /// Live in THIS hub. Base roles: always. Declared roles: only once the administrator says so.
    pub active: bool,
}

/// A role as an installed module declares it.
struct Declared {
    label: String,
    extends: String,
    module_id: String,
}

/// A refused role key, by reason (hub#1070): `required`, `immutable` (a base role of the hub is
/// always live), `unknown` (no installed module declares it) or `inactive` (declared, switched
/// off in this hub). The prose is the fallback.
fn invalid_key(reason: &str, detail: impl Into<String>) -> RuntimeError {
    RuntimeError::InvalidField {
        name: "hub.roles".into(),
        field: "role_key".into(),
        reason: reason.into(),
        detail: detail.into(),
    }
}

/// English canonical label of a base role (the PLAN's table). Falls back to the key so adding a
/// base role can never leave the catalogue with an empty label.
fn base_label(key: &str) -> String {
    match key {
        "admin" => "Administrator".to_string(),
        "manager" => "Manager".to_string(),
        "employee" => "Employee".to_string(),
        other => other.to_string(),
    }
}

/// How far a base role reaches, to resolve a collision by the LEAST privileged side. `admin` is
/// unreachable here on purpose (a manifest cannot extend it, hub#351) but is ranked anyway so the
/// order stays total if the base catalogue ever grows.
fn rank(base_role: &str) -> u8 {
    match base_role {
        "employee" => 0,
        "manager" => 1,
        _ if is_admin_role(base_role) => 2,
        // Anything unknown is treated as the least privileged: guessing high would be guessing in
        // the direction that grants.
        _ => 0,
    }
}

/// Roles declared by the modules that are installed **and active**, keyed by role key.
///
/// Active and not merely installed, for the same reason [`crate::identity::permissions_for_role`]
/// only unions active modules: a deactivated module exposes no query, no command and no menu, so
/// the role it invented is not part of this hub's vocabulary while it is off. Its activation row
/// is kept (deactivating is temporary, ADR-0128) — only uninstalling clears it.
///
/// **Two modules may declare the same key** (a restaurant pack and a KDS both inventing `waiter`).
/// That is not an error — the install-time validation only refuses a duplicate *within one
/// manifest* — so it is resolved here, and by the conservative side: the entry keeps the LEAST
/// privileged `extends` of the two, and the label/module of the first declarer in module-id order
/// so the answer is deterministic.
fn declared(registry: &Registry) -> BTreeMap<String, Declared> {
    let mut modules: Vec<&crate::Manifest> = registry
        .installed
        .iter()
        .filter(|m| registry.is_active(&m.id))
        .collect();
    modules.sort_by(|a, b| a.id.cmp(&b.id));

    let mut out: BTreeMap<String, Declared> = BTreeMap::new();
    for module in modules {
        for role in &module.roles {
            match out.get_mut(&role.key) {
                Some(existing) => {
                    if rank(&role.extends) < rank(&existing.extends) {
                        existing.extends = role.extends.clone();
                    }
                }
                None => {
                    out.insert(
                        role.key.clone(),
                        Declared {
                            label: role.label.clone(),
                            extends: role.extends.clone(),
                            module_id: module.id.clone(),
                        },
                    );
                }
            }
        }
    }
    out
}

/// The role keys switched on in this hub (the rows of `hub_role_activation`).
pub async fn active_keys(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<BTreeSet<String>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT role_key FROM hub_role_activation WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .filter_map(|r| r["role_key"].as_str())
        .map(str::to_string)
        .filter(|k| !k.is_empty())
        .collect())
}

/// Roles carried by the **active** users of this hub, whatever their origin.
async fn roles_in_use(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<BTreeSet<String>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT DISTINCT role FROM hub_user WHERE hub_id = :hub_id AND is_active = 1",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .filter_map(|r| r["role"].as_str())
        .map(|r| r.trim().to_string())
        .filter(|r| !r.is_empty())
        .collect())
}

/// The aggregated catalogue of this hub: the base roles of the core, then what the installed
/// active modules declare, then whatever roles are still carried by somebody and nobody declares.
///
/// Order is stable and meaningful: base first in [`BASE_ROLES`] order (it is the frozen contract),
/// declared roles alphabetically, orphans last.
pub async fn catalog(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
) -> Result<Vec<CatalogRole>> {
    let declared = declared(registry);
    let active = active_keys(db, hub_id).await?;
    let in_use = roles_in_use(db, hub_id).await?;

    let mut out: Vec<CatalogRole> = BASE_ROLES
        .iter()
        .map(|key| CatalogRole {
            key: (*key).to_string(),
            label: base_label(key),
            // A base role hangs from itself: it IS the base. Saying so beats an empty string,
            // which the UI would have to special-case.
            extends: (*key).to_string(),
            source: RoleSource::Core,
            active: true,
        })
        .collect();

    for (key, role) in &declared {
        if is_base_role(key) {
            continue; // refused at install time; belt and braces if a row ever slips through.
        }
        out.push(CatalogRole {
            key: key.clone(),
            label: role.label.clone(),
            extends: role.extends.clone(),
            source: RoleSource::Module(role.module_id.clone()),
            active: active.contains(key),
        });
    }

    // Compared against what was ALREADY listed, not against `is_base_role`: the legacy spelling
    // `owner` is "base" for the gate (hub#349) but is not in `BASE_ROLES`, so discarding it there
    // would drop from the catalogue whoever still carries it — precisely the row that has to be
    // visible to be reassigned. Exact match, as before hub#352: an `Admin` row still shows up on
    // its own instead of merging into `admin` and taking its members somewhere nobody looks.
    let listed: BTreeSet<String> = out.iter().map(|r| r.key.clone()).collect();
    for key in &in_use {
        if listed.contains(key) || declared.contains_key(key) {
            continue;
        }
        out.push(CatalogRole {
            key: key.clone(),
            label: key.clone(),
            extends: String::new(),
            source: RoleSource::InUse,
            // Nothing declares it, so nothing can be switched on: a leftover role is visible,
            // never live.
            active: false,
        });
    }
    Ok(out)
}

/// Switch a declared role on or off **in this hub**. `actor` is the `hub_user.id` that decided.
///
/// Refuses, and the refusal always names the role:
///  - a **base role**: it is always live and switching it off would leave the hub unusable;
///  - a key **no installed module declares**: activation aggregates a catalogue, it does not
///    create one. This is the guard that keeps the write door from minting roles.
pub async fn set_active(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    role_key: &str,
    active: bool,
    actor: &str,
) -> Result<()> {
    let key = role_key.trim();
    if key.is_empty() {
        return Err(invalid_key("required", "the role key is required"));
    }
    if is_base_role(key) {
        return Err(invalid_key(
            "immutable",
            format!(
                "role `{key}` is a base role of the hub: base roles are always active and cannot \
                 be switched off"
            ),
        ));
    }
    if !declared(registry).contains_key(key) {
        return Err(invalid_key(
            "unknown",
            format!(
                "role `{key}` is not declared by any installed module: a hub activates the roles \
                 of its catalogue, it does not create new ones"
            ),
        ));
    }

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("role_key".into(), json!(key));
    if active {
        p.insert("now".into(), json!(now_rfc3339()));
        p.insert("actor".into(), json!(actor));
        db.execute(
            "INSERT INTO hub_role_activation (hub_id, role_key, activated_at, activated_by) \
               VALUES (:hub_id, :role_key, :now, :actor) \
             ON CONFLICT (hub_id, role_key) \
             DO UPDATE SET activated_at = :now, activated_by = :actor",
            &p,
        )
        .await?;
    } else {
        db.execute(
            "DELETE FROM hub_role_activation WHERE hub_id = :hub_id AND role_key = :role_key",
            &p,
        )
        .await?;
    }
    Ok(())
}

/// Who switched a role on when the switch came from a **blueprint**, not from a person
/// (`hub_role_activation.activated_by`). The column is an audit trail, and «the template did it»
/// is the honest answer: no `hub_user` decided this.
pub const BLUEPRINT_ACTOR: &str = "blueprint";

/// What the hub did with the role set a blueprint asked for (paso 2b, hub#354).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PreActivation {
    /// Keys that are live now.
    pub activated: Vec<String>,
    /// Keys the hub **refused**: no installed module declares them, or they are base keys a
    /// package may not touch. Kept BY NAME and not merely counted — the report only shows how
    /// many, but a caller that wants to say *which* ones has them here.
    pub refused: Vec<String>,
}

/// Pre-activate the role set of a vertical: what makes a new restaurant open with `Waiter` and
/// `Kitchen` live instead of with three generic roles somebody has to guess at (paso 2b, hub#354).
///
/// Three things this is NOT, and each one is deliberate:
///
/// - **It is not a second door.** Every key goes through [`set_active`], the same one the
///   administrator's click uses, so a downloaded file gets exactly the guards a click gets: it
///   cannot mint a role no installed module declares, and it cannot touch a base or administrative
///   one (hub#347/#351/#352). Pre-activating is granting capability with nobody pressing anything,
///   so it had better not be the lenient path.
/// - **It never switches anything OFF.** The set is additive: a role this hub already had live and
///   the blueprint does not name stays live. Mirroring the template exactly would mean a downloaded
///   file could strip a working hub of a role its people are already carrying — and
///   [`ensure_assignable`] would then refuse to hand it out.
/// - **It is not all-or-nothing.** A key the hub refuses is skipped and reported; the rest still
///   land. A blueprint whose kitchen module failed to install must still open the dining room.
///
/// A refusal ([`RuntimeError::InvalidPayload`], what [`set_active`] raises) is policy and lands in
/// [`PreActivation::refused`]; anything else is the database failing and propagates, because
/// «the row could not be written» must never read as «the hub said no».
///
/// Duplicated keys count once: a template naming `waiter` twice brings one role, not two.
pub async fn pre_activate(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    keys: &[String],
) -> Result<PreActivation> {
    let mut out = PreActivation::default();
    let mut seen: BTreeSet<String> = BTreeSet::new();
    for key in keys {
        let key = key.trim().to_string();
        if !seen.insert(key.clone()) {
            continue;
        }
        match set_active(db, registry, hub_id, &key, true, BLUEPRINT_ACTOR).await {
            Ok(()) => out.activated.push(key),
            // hub#1070: a refused key is an `InvalidField` now; the legacy shape stays matched so
            // nothing that still produces it turns into a hard failure of the whole import.
            Err(RuntimeError::InvalidField { .. } | RuntimeError::InvalidPayload { .. }) => {
                out.refused.push(key)
            }
            Err(e) => return Err(e),
        }
    }
    Ok(out)
}

/// Forget the activation of `keys` in this hub. Called by `installer::uninstall` for the roles the
/// module declared that **no other installed module** declares any more.
///
/// The activation dies with the module on purpose. Keys are global, so a dormant row would mean
/// that installing a *different* package that happens to reuse the key would find its role already
/// switched on — an approval the administrator gave to another module. Coming back from an
/// uninstall asks again; that is one click against inheriting an approval nobody granted.
pub async fn clear_activation(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    keys: &[String],
) -> Result<()> {
    for key in keys {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("role_key".into(), json!(key));
        db.execute(
            "DELETE FROM hub_role_activation WHERE hub_id = :hub_id AND role_key = :role_key",
            &p,
        )
        .await?;
    }
    Ok(())
}

/// Can `role` be handed to a person in this hub? The door where activation earns its keep.
///
/// - **Base role** → always yes (the frozen three-key contract).
/// - **Role declared by an installed module** → only if the administrator switched it on. A role
///   the hub never activated is not part of this business's vocabulary, so assigning it would be
///   assigning something nobody reviewed.
/// - **Anything else** → yes, unchanged. Hubs already carry hand-typed roles (`cashier`,
///   `waiter`…) from before there was a catalogue and modules may grant against keys they did not
///   invent; refusing those would break working hubs to enforce a rule that is not this issue's.
///   They grant only what the installed modules give the key, exactly as before.
pub async fn ensure_assignable(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    role: &str,
) -> Result<()> {
    let key = role.trim();
    if is_base_role(key) || !declared(registry).contains_key(key) {
        return Ok(());
    }
    if active_keys(db, hub_id).await?.contains(key) {
        return Ok(());
    }
    Err(invalid_key(
        "inactive",
        format!(
            "role `{key}` is not active in this hub: activate it in the role catalogue before \
             assigning it"
        ),
    ))
}

/// The role keys a module declares in its manifest.
pub fn declared_by(manifest: &crate::Manifest) -> Vec<String> {
    manifest.roles.iter().map(|r| r.key.clone()).collect()
}

/// Of `keys`, the ones **no installed module** declares any more. Used right after removing a
/// module from the registry to decide whose activation must be forgotten.
///
/// Installed, not active: a merely deactivated module is coming back (ADR-0128), and dropping the
/// administrator's choice on a temporary state would be losing configuration, not securing it.
pub fn no_longer_declared(registry: &Registry, keys: &[String]) -> Vec<String> {
    keys.iter()
        .filter(|key| {
            !registry
                .installed
                .iter()
                .any(|m| m.roles.iter().any(|r| &&r.key == key))
        })
        .cloned()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_source_of_a_role_serialises_as_a_tagged_object() {
        assert_eq!(
            serde_json::to_value(RoleSource::Core).unwrap(),
            serde_json::json!({ "kind": "core" })
        );
        assert_eq!(
            serde_json::to_value(RoleSource::Module("kitchen".into())).unwrap(),
            serde_json::json!({ "kind": "module", "module_id": "kitchen" })
        );
        assert_eq!(
            serde_json::to_value(RoleSource::InUse).unwrap(),
            serde_json::json!({ "kind": "in_use" })
        );
    }

    #[test]
    fn a_collision_between_two_declarers_resolves_to_the_least_privileged_base() {
        // `manager` reaches further than `employee`, so a key declared as both resolves to
        // `employee`: when two manifests disagree, the hub believes the narrower one.
        assert!(rank("employee") < rank("manager"));
        assert!(rank("manager") < rank("admin"));
        // An `extends` nobody recognises is ranked as the narrowest, never as the widest.
        assert_eq!(rank("something_else"), rank("employee"));
    }

    #[test]
    fn every_base_role_has_an_english_canonical_label() {
        for base in BASE_ROLES {
            let label = base_label(base);
            assert!(!label.is_empty());
            assert!(
                label.chars().next().unwrap().is_uppercase(),
                "`{base}` → `{label}` is a human label, not the key"
            );
        }
    }
}
