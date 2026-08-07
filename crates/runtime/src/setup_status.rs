//! `hub.setup.status` — the ONE query behind the onboarding checklist (hub#369).
//!
//! **The configuration state is a single query. The checklist widget and the assistant are two
//! reads of the same query.** Before this, they were not: the widget ran a loop in the browser
//! (`apps/web/src/lib/setup-status.ts`, N queries from the client) and the assistant received a
//! paragraph of prose built from that loop's in-memory array. Two sources, one of them fiction.
//!
//! This **extends ADR-0063, it does not replace it.** The `setup` block of `module.json` is the one
//! ADR-0063 defined; what changes is *where* it is evaluated (the runtime, not the browser) and
//! *what* the answer covers.
//!
//! # Two classes of item
//!
//! ADR-0063 only knew about modules. But your apps, your business identity and your team are not
//! anybody's module — they are hub settings and `hub_user` rows, and no `module.json` can claim
//! them without arrogating something that is not its own.
//!
//! * **CORE items** — declared right here, in Rust. Fixed: the same three in an empty hub as in a
//!   hub with 24 modules. That matters because the empty hub is exactly when a checklist is worth
//!   the most, and it is exactly where a module-only design says nothing at all.
//! * **MODULE items** — the `setup` block ([`crate::manifest::SetupDef`]), one per installed module
//!   that declares it.
//!
//! The query returns the **union of the two**, in an order the core fixes.
//!
//! # Three properties this owes its callers
//!
//! 1. **Already ordered and already filtered.** Neither the widget nor the assistant decides the
//!    order or what applies; if both decided, they would diverge. A module that is not installed
//!    contributes nothing, and an item that does not apply to this country never shows up.
//! 2. **`actions` belongs to the item, not to the session.** The ways of getting it done travel in
//!    the data, so the assistant knows what it can offer without guessing.
//! 3. **Best-effort, never half-done.** If a module's check fails (no permission, early boot, a
//!    half-applied migration) its item is **omitted** rather than reported as pending. A false "you
//!    are missing X" sends the user to fix something that may already be fine — worse than a gap.
//!
//! # Three levels, and the ⛔ one is a fact about the runtime (hub#370)
//!
//! `required` is a boolean and the checklist needs three answers: ⛔ legal · 🔴 functional · 🟡
//! recommended. The one that cannot be a boolean is ⛔, because it is **not a stronger 🔴**: it is
//! the claim that the dispatcher will refuse the operation. Saying it the other way round —
//! painting ⛔ on something merely important — promises a protection that does not exist, and the
//! blocking strip (hub#374) cuts the screen on the strength of that claim.
//!
//! So the level is derived, never declared:
//!
//! * **⛔ [`LEVEL_LEGAL`] = the gate of ADR-0203**, read from the other side. That gate has two
//!   arms and so does this list: [`BLOCKING_KEYS`] (the business identity, a fixed core key) and
//!   [`certificate_arm`] (the business certificate, which hangs on whichever installed module
//!   declares the `certificate` capability). Nothing else is on it — an entry without a gate behind
//!   it is a colour pretending to be a rule.
//! * **🔴 [`LEVEL_FUNCTIONAL`] / 🟡 [`LEVEL_RECOMMENDED`] = the module's `required`.** A
//!   third-party manifest gets to say how much its own configuration matters, and nothing more: it
//!   can never make itself a condition for selling.
//!
//! The level is **orthogonal to the state**. A done item keeps its level; what the strip reads is
//! `blocking_pending`, the count of items that are ⛔ *and* still pending.
//!
//! # What deliberately is NOT here
//!
//! The third state of the apps item ("unavailable", hub#371): [`STATE_DONE`]/[`STATE_PENDING`] are
//! strings precisely so that adding a third value is an addition, not a break. And the surfaces —
//! the dashboard card (hub#372), the assistant (hub#373), the blocking strip (hub#374). This query
//! paints nothing.
use std::future::Future;
use std::pin::Pin;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::Result;
use crate::manifest::{SetupCheck, SetupDef};
use crate::registry::{Registry, RequestContext};

/// Stable key of the core item "your apps". A core item's key IS its i18n key: the shell translates
/// by it and falls back to the English `title` that travels in the payload.
pub const ITEM_APPS: &str = "apps";
/// Stable key of the core item "your business details" (legal name + tax id).
pub const ITEM_BUSINESS_IDENTITY: &str = "business_identity";
/// Stable key of the core item "your team".
pub const ITEM_TEAM: &str = "team";

/// The item is done.
pub const STATE_DONE: &str = "done";
/// The item is still the user's to do.
pub const STATE_PENDING: &str = "pending";

/// ⛔ legal — the runtime rejects the operation. *"You need this in order to invoice."*
pub const LEVEL_LEGAL: &str = "legal";
/// 🔴 functional — no gate, but the till cannot do its job. *"Without this you cannot sell."*
pub const LEVEL_FUNCTIONAL: &str = "functional";
/// 🟡 recommended — the business runs; you notice it is missing. Never alerts.
pub const LEVEL_RECOMMENDED: &str = "recommended";

/// **The ⛔ list, and it belongs to the core.** A blocking item is one the runtime actually rejects
/// — the fiscal precondition of ADR-0203 read from the other side — so it can never be something a
/// third-party manifest declares about itself.
///
/// This is the *fixed* half: the business identity, whose two settings are literally the ones
/// `enforce_fiscal_precondition` reads. The other arm of the same gate depends on what is installed
/// and is resolved per call by [`certificate_arm`].
///
/// Only keys of [`CORE_ITEMS`] may appear here. A module item is keyed `<module_id>.setup`, so
/// putting one on this list would hand a third-party manifest the power to stop a sale.
pub const BLOCKING_KEYS: &[&str] = &[ITEM_BUSINESS_IDENTITY];

/// Where an item that declares no `order` lands: after everything the core placed, never in front
/// of it. The core owns the scale; a module takes the slot the core assigned it.
pub const DEFAULT_ORDER: i64 = 500;

/// Slots the core reserves for its own items. The gaps in between are the module slots (see
/// `architecture/hub/setup-status.md`): sell first, invoice after.
const ORDER_APPS: i64 = 10;
const ORDER_BUSINESS_IDENTITY: i64 = 40;
const ORDER_TEAM: i64 = 80;

/// A core item before it becomes JSON. Split out so the English strings and the reserved slots read
/// as one table instead of being scattered through the query.
struct CoreItem {
    key: &'static str,
    order: i64,
    title: &'static str,
    description: &'static str,
    icon: &'static str,
    route: &'static str,
    /// `true` = 🔴 functional, `false` = 🟡 recommended (hub#370 turns this into the real level).
    required: bool,
    actions: &'static [&'static str],
}

/// The core items, in the order the business needs them.
///
/// Ordering is deliberate and it is not the order of urgency: apps come **before** the fiscal
/// identity even though the legal one sounds louder. A new customer can have a till that works in
/// ten minutes and walk the whole thing before going to dig the digital certificate out of a
/// drawer; the fiscal precondition lands where the law puts it — at the first fiscal document, not
/// at signup. A checklist that opens by asking for a tax id makes the first step of the product a
/// piece of paperwork.
const CORE_ITEMS: &[CoreItem] = &[
    CoreItem {
        key: ITEM_APPS,
        order: ORDER_APPS,
        title: "Your apps",
        description: "Install at least one business app so the hub has something to do.",
        icon: "grid-outline",
        route: "/apps",
        required: true,
        // You do not fill an empty hub by hand: you start from a sector blueprint or from the
        // catalogue. Offering "do it manually" here would be offering the slowest of the paths.
        actions: &["template", "catalog"],
    },
    CoreItem {
        key: ITEM_BUSINESS_IDENTITY,
        order: ORDER_BUSINESS_IDENTITY,
        title: "Your business details",
        description: "Legal name and tax id: without them the hub cannot issue an invoice.",
        icon: "business-outline",
        route: "/settings",
        required: true,
        actions: &["manual", "assistant"],
    },
    CoreItem {
        key: ITEM_TEAM,
        order: ORDER_TEAM,
        title: "Your team",
        description: "Add the people who will use the till, each with their own way in.",
        icon: "people-outline",
        route: "/employees",
        required: false,
        // A blueprint activates ROLES, it never creates users: credentials do not travel in a
        // template (ADR-0195 §5). So there is no `template` action here on purpose.
        actions: &["manual"],
    },
];

/// Builds the status document: `{ items, blocking_pending, pending, total }`.
///
/// One row, not one row per item. The counters are a property of the whole answer — the blocking
/// strip of hub#374 reads `blocking_pending` and nothing else — and splitting them across rows
/// would make every consumer re-aggregate what the core already knows.
pub async fn status(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    ctx: &RequestContext,
) -> Result<Json> {
    // Read once: the core path of the dispatcher returns before the business-identity enrichment
    // (`queries::execute_page`), so `ctx` carries none of this. Degrading to the empty document
    // keeps the rule: a check we cannot make is a gap, never a false pending.
    let settings = crate::settings::get_all(db, hub_id)
        .await
        .unwrap_or(Json::Null);
    let setting = |key: &str| {
        settings
            .get(key)
            .and_then(Json::as_str)
            .unwrap_or_default()
            .trim()
            .to_string()
    };
    let country = setting("country_code").to_uppercase();
    // The second arm of ADR-0203, resolved against THIS hub. Read here for the same reason the
    // settings are: the reserved `hub.` path answers before the dispatcher enriches the context,
    // so `ctx.has_certificate` is not populated yet. Degrading to "absent" matches the gate, which
    // degrades the same way and would therefore reject — so ⛔ stays honest either way.
    //
    // ⚠️ This is deliberately the SAME read `queries::execute_page` uses to fill
    // `ctx.has_certificate`, which is what the gate then checks. The two must answer identically:
    // if the checklist and the gate disagree about the certificate, ⛔ starts lying in one
    // direction or the other. Move one, move the other.
    let certificate_present = crate::certificate::status(db, hub_id)
        .await
        .ok()
        .and_then(|s| s.get("present").and_then(Json::as_bool))
        .unwrap_or(false);
    let certificate_arm = certificate_arm(registry, certificate_present);

    let mut items: Vec<Json> = Vec::new();
    for core in CORE_ITEMS {
        if let Some(done) = core_item_done(db, registry, hub_id, core, &setting).await {
            items.push(item_json(
                core.key,
                "core",
                None,
                done,
                core.required,
                level_of(core.key, core.required, &certificate_arm),
                core.title,
                core.description,
                core.icon,
                core.route,
                core.order,
                core.actions,
            ));
        }
    }

    for manifest in &registry.installed {
        let Some(def) = &manifest.setup else { continue };
        // An inactive module is an absence, not a pending task: its screens are gone, so sending
        // the user to configure it would send them to a dead route.
        if !registry.is_active(&manifest.id) {
            continue;
        }
        if !applies_to_country(&def.countries, &country) {
            continue;
        }
        // Only tell whoever can act. The module's query would reject anyone else anyway, so this is
        // the cheap half of a gate the dispatcher enforces for real.
        if !def.permission.is_empty() && !crate::permissions::has(ctx, &def.permission) {
            continue;
        }
        let Some(done) = module_item_done(db, registry, def, ctx).await else {
            continue;
        };
        let key = item_key(&manifest.id);
        items.push(item_json(
            &key,
            "module",
            Some(&manifest.id),
            done,
            def.required,
            // The manifest declares `required`, never the level: the core decides, and the only way
            // a module item reaches ⛔ is the core hanging a gate arm on it.
            level_of(&key, def.required, &certificate_arm),
            &def.title,
            &def.description,
            if def.icon.is_empty() {
                "settings-outline"
            } else {
                &def.icon
            },
            &def.route,
            def.order.unwrap_or(DEFAULT_ORDER),
            // A module item is always reachable by its own screen, and the assistant can drive any
            // module's settings. `template`/`file` are not offered per module yet: no manifest can
            // say today which blueprint section fills it.
            &["manual", "assistant"],
        ));
    }

    // Sorting by the key as a tie-break keeps the answer deterministic when two modules land on the
    // same slot — a checklist that shuffles between reloads looks broken.
    items.sort_by(|a, b| {
        let order = |v: &Json| v["order"].as_i64().unwrap_or(DEFAULT_ORDER);
        let key = |v: &Json| v["key"].as_str().unwrap_or_default().to_string();
        order(a).cmp(&order(b)).then_with(|| key(a).cmp(&key(b)))
    });

    let pending = items.iter().filter(|i| i["state"] == STATE_PENDING).count();
    // What hub#374 reads, and the only number it reads: pending AND ⛔. Counting everything pending
    // would leave the strip up forever; counting every ⛔ item would leave it up on a hub that is
    // already configured.
    let blocking_pending = items
        .iter()
        .filter(|i| i["state"] == STATE_PENDING && i["level"] == LEVEL_LEGAL)
        .count();

    Ok(json!({
        "total": items.len(),
        "pending": pending,
        "blocking_pending": blocking_pending,
        "items": items,
    }))
}

/// Key of a module item. Derived by the core from the module id, never declared: the ⛔ list of
/// hub#370 is keyed by these, so letting a manifest choose its own key would let it rename itself
/// out of the list.
fn item_key(module_id: &str) -> String {
    format!("{module_id}.setup")
}

/// The ⛔ arm of ADR-0203 that is not the core's to hold: the business certificate.
///
/// The gate demands it **while any INSTALLED module declares the `certificate` capability** — today
/// verifactu, tomorrow whatever a second country needs — so the ⛔ hangs on the item of that same
/// module, which is the one that can clear it. Two properties this owes the rule:
///
/// * **Keyed on the capability, never on a module id.** Hardcoding `verifactu` would put the
///   business back inside a runtime that has none, block the wrong hub outside Spain, and miss the
///   module that actually carries the certificate. It is also not a self-declaration: a manifest
///   asking for this capability is asking the gate to demand a certificate of the whole hub, and
///   the checklist merely says so out loud.
/// * **Evaluated, not listed.** With the certificate loaded the runtime accepts, so the arm
///   disappears even though the module may still be half-configured — its item stays 🔴 pending. A
///   ⛔ that does not block is the colour this whole design exists to avoid.
fn certificate_arm(registry: &Registry, certificate_present: bool) -> Vec<String> {
    if certificate_present {
        return Vec::new();
    }
    registry
        .installed
        .iter()
        .filter(|m| m.capabilities.certificate.is_some())
        .map(|m| item_key(&m.id))
        .collect()
}

/// The level of an item: ⛔ if the runtime rejects without it, else what the module asked for.
///
/// ⛔ wins over `required` because they answer different questions — `required` is an opinion about
/// importance, ⛔ is a fact about the dispatcher — and a fact does not lose to an opinion.
fn level_of(key: &str, required: bool, certificate_arm: &[String]) -> &'static str {
    if BLOCKING_KEYS.contains(&key) || certificate_arm.iter().any(|k| k == key) {
        LEVEL_LEGAL
    } else if required {
        LEVEL_FUNCTIONAL
    } else {
        LEVEL_RECOMMENDED
    }
}

/// Every item carries every key (with `module_id` null for a core item), so a consumer never has to
/// branch on whether a field is present.
#[allow(clippy::too_many_arguments)]
fn item_json(
    key: &str,
    source: &str,
    module_id: Option<&str>,
    done: bool,
    required: bool,
    level: &str,
    title: &str,
    description: &str,
    icon: &str,
    route: &str,
    order: i64,
    actions: &[&str],
) -> Json {
    json!({
        "key": key,
        "source": source,
        "module_id": module_id,
        "state": if done { STATE_DONE } else { STATE_PENDING },
        // What the module declared…
        "required": required,
        // …and the core's verdict, which is what every surface must read: `required` cannot express
        // ⛔ and no consumer should be re-deriving the level for itself.
        "level": level,
        "title": title,
        "description": description,
        "icon": icon,
        "route": route,
        "order": order,
        "actions": actions,
    })
}

/// Evaluates a core item. `None` = the check could not be made ⇒ the item is omitted (best-effort).
async fn core_item_done(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    core: &CoreItem,
    setting: &impl Fn(&str) -> String,
) -> Option<bool> {
    match core.key {
        // At least one business app. Nothing else can be asked of the registry: the Hub is
        // international and knows no concrete module, so "an app" is "something installed and
        // active" — and the reserved `hub` id can never be a module (the installer refuses it).
        ITEM_APPS => Some(registry.installed.iter().any(|m| registry.is_active(&m.id))),
        // The SAME two settings the fiscal precondition reads (ADR-0203). Reading them from the
        // other side is what keeps "it blocks ⇔ the runtime rejects it" true instead of a colour.
        // Half an identity is not an identity: both halves or nothing.
        ITEM_BUSINESS_IDENTITY => Some(
            !setting("business_legal_name").is_empty() && !setting("business_tax_id").is_empty(),
        ),
        // At least one hub user besides the administrator. A solo business legitimately has one,
        // which is why this item is 🟡 recommended and never nags.
        ITEM_TEAM => {
            let users = crate::hub_users::list(db, hub_id).await.ok()?;
            Some(users.iter().filter(|u| u.is_active).count() > 1)
        }
        _ => None,
    }
}

/// Runs the module's own declarative check. `None` = the check could not be made ⇒ omit the item.
async fn module_item_done(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    def: &SetupDef,
    ctx: &RequestContext,
) -> Option<bool> {
    let rows = run_module_check(db, registry, &def.query, &def.params, ctx)
        .await
        .ok()?;
    // A query that RAN and returned nothing is an answer, not a gap: ADR-0063 says no row = not
    // configured, and that is a real "you still have to do this".
    Some(is_configured(rows.first(), &def.configured_when))
}

/// Calls the dispatcher for a module's check, boxed and type-erased on purpose.
///
/// The core query is served *by* the dispatcher and calls *back into* it, so without an indirection
/// here the future would contain itself and the compiler would refuse an infinitely sized type. The
/// call goes through `queries::execute` and not straight to SQL so the module's own permission gate,
/// payload schema and system params apply exactly as they do for any other caller.
fn run_module_check<'a>(
    db: &'a dyn DatabaseAdapter,
    registry: &'a Registry,
    name: &'a str,
    params: &'a Params,
    ctx: &'a RequestContext,
) -> Pin<Box<dyn Future<Output = Result<Vec<Json>>> + Send + 'a>> {
    Box::pin(crate::queries::execute(db, registry, name, params, ctx))
}

/// Configured ⇔ there is a row AND every check passes. No row ⇒ not configured (ADR-0063).
fn is_configured(row: Option<&Json>, checks: &[SetupCheck]) -> bool {
    let Some(row) = row else { return false };
    checks.iter().all(|c| passes(row, c))
}

/// Evaluates one check against the row. Mirror of the browser evaluator this replaces, so a module
/// that was already declaring a `setup` block keeps the exact answer it had.
fn passes(row: &Json, check: &SetupCheck) -> bool {
    let value = row.get(&check.field).unwrap_or(&Json::Null);
    if let Some(want) = check.truthy {
        return truthy(value) == want;
    }
    if let Some(expected) = &check.equals {
        return as_text(value) == as_text(expected);
    }
    // Neither `truthy` nor `equals`: a half-written contract must not silently tick the item as
    // done. Saying "not configured" is the conservative side of the same rule as everywhere else.
    false
}

/// Loosely truthy: not null, not empty, not zero, not `false` — and not the STRINGS `"0"`/`"false"`
/// either, because a boolean crossing SQLite or a text column arrives spelled out.
fn truthy(value: &Json) -> bool {
    match value {
        Json::Null => false,
        Json::Bool(b) => *b,
        Json::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Json::String(s) => {
            let s = s.trim();
            !s.is_empty() && s != "0" && !s.eq_ignore_ascii_case("false")
        }
        Json::Array(a) => !a.is_empty(),
        Json::Object(_) => true,
    }
}

/// Lax comparison, as text on both sides: the declarative layer travels through JSON and SQL, where
/// the same `1` arrives as a number, a string or a boolean depending on the dialect.
fn as_text(value: &Json) -> String {
    match value {
        Json::String(s) => s.clone(),
        Json::Null => String::new(),
        other => other.to_string(),
    }
}

/// Does an item that declares `countries` apply to this hub? Empty = everywhere.
///
/// A hub with no country cannot answer the question, so a country-scoped item is **omitted**: the
/// safe side of "never a false you-are-missing-X" is not asking a French shop for a Spanish
/// obligation.
fn applies_to_country(countries: &[String], hub_country: &str) -> bool {
    if countries.is_empty() {
        return true;
    }
    !hub_country.is_empty()
        && countries
            .iter()
            .any(|c| c.trim().eq_ignore_ascii_case(hub_country))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn check(field: &str, truthy: Option<bool>, equals: Option<Json>) -> SetupCheck {
        SetupCheck { field: field.to_string(), truthy, equals }
    }

    #[test]
    fn no_row_is_never_configured() {
        // ADR-0063, and the reason a fresh module shows up as pending on day one.
        assert!(!is_configured(None, &[]));
        assert!(!is_configured(None, &[check("ready", Some(true), None)]));
    }

    #[test]
    fn a_row_with_no_checks_is_enough() {
        // `configured_when: []` means "having a row is the whole condition".
        assert!(is_configured(Some(&json!({})), &[]));
    }

    #[test]
    fn every_check_has_to_pass_not_just_one() {
        let row = json!({ "enabled": 1, "has_certificate": 0 });
        let checks = [
            check("enabled", Some(true), None),
            check("has_certificate", Some(true), None),
        ];
        assert!(!is_configured(Some(&row), &checks));
        let row = json!({ "enabled": 1, "has_certificate": 1 });
        assert!(is_configured(Some(&row), &checks));
    }

    #[test]
    fn truthy_reads_the_shapes_a_database_actually_returns() {
        // The same `false` arrives as 0 from Postgres, as "0" from a text column and as false from
        // JSON. All three mean the same thing to a person, so they must here too.
        for falsy in [json!(null), json!(0), json!(""), json!("0"), json!(false), json!("false"), json!("  ")] {
            assert!(!truthy(&falsy), "{falsy} must not count as configured");
        }
        for t in [json!(1), json!("1"), json!(true), json!("yes"), json!(-3), json!(0.5)] {
            assert!(truthy(&t), "{t} must count as configured");
        }
    }

    #[test]
    fn truthy_false_inverts_the_check() {
        // `truthy: false` is "configured when this is EMPTY" — a module may well define it that way
        // (no pending migrations, no unassigned tables).
        let row = json!({ "pending_steps": 0 });
        assert!(is_configured(Some(&row), &[check("pending_steps", Some(false), None)]));
        let row = json!({ "pending_steps": 3 });
        assert!(!is_configured(Some(&row), &[check("pending_steps", Some(false), None)]));
    }

    #[test]
    fn equals_compares_as_text_on_both_sides() {
        let row = json!({ "mode": 1 });
        assert!(is_configured(Some(&row), &[check("mode", None, Some(json!("1")))]));
        assert!(is_configured(Some(&row), &[check("mode", None, Some(json!(1)))]));
        assert!(!is_configured(Some(&row), &[check("mode", None, Some(json!(2)))]));
    }

    #[test]
    fn a_check_that_declares_neither_condition_never_ticks_the_item() {
        // A malformed manifest must fail towards "not configured", never towards "all good".
        let row = json!({ "ready": 1 });
        assert!(!is_configured(Some(&row), &[check("ready", None, None)]));
    }

    #[test]
    fn a_missing_column_is_not_configured() {
        // The module renamed the column and forgot the manifest: pending, not done.
        let row = json!({ "other": 1 });
        assert!(!is_configured(Some(&row), &[check("ready", Some(true), None)]));
    }

    #[test]
    fn an_item_without_countries_applies_everywhere() {
        assert!(applies_to_country(&[], "FR"));
        assert!(applies_to_country(&[], ""));
    }

    #[test]
    fn a_country_scoped_item_only_applies_where_it_was_declared() {
        let es = vec!["ES".to_string()];
        assert!(applies_to_country(&es, "ES"));
        assert!(applies_to_country(&es, "es"), "the comparison is case-insensitive");
        assert!(!applies_to_country(&es, "FR"));
        assert!(
            !applies_to_country(&es, ""),
            "a hub with no country cannot be asked for a national obligation"
        );
    }

    #[test]
    fn the_core_reserves_its_slots_and_leaves_the_gaps_to_the_modules() {
        // The gaps are the contract eight module repos are about to fill; closing one would push a
        // module in front of a core item it is supposed to follow.
        let orders: Vec<i64> = CORE_ITEMS.iter().map(|c| c.order).collect();
        assert_eq!(orders, vec![ORDER_APPS, ORDER_BUSINESS_IDENTITY, ORDER_TEAM]);
        assert!(
            orders.windows(2).all(|w| w[1] - w[0] > 1),
            "core slots must leave room between them"
        );
        assert!(
            orders.iter().all(|o| *o < DEFAULT_ORDER),
            "an item that declares no order lands after everything the core placed"
        );
    }

    #[test]
    fn every_core_item_offers_at_least_one_way_to_complete_it() {
        for core in CORE_ITEMS {
            assert!(!core.actions.is_empty(), "{} is a dead end", core.key);
            assert!(!core.route.is_empty(), "{} has nowhere to go", core.key);
            assert!(!core.title.is_empty());
        }
    }

    #[test]
    fn the_blocking_list_only_ever_holds_keys_of_the_core() {
        // A module key is `<id>.setup`, so the dot is the boundary: a core key can never have one.
        // If a module id ever landed here, a third-party manifest would decide what blocks a sale.
        for key in BLOCKING_KEYS {
            assert!(
                !key.contains('.'),
                "`{key}` looks like a module item, and the ⛔ list is the core's"
            );
            assert!(
                CORE_ITEMS.iter().any(|c| c.key == *key),
                "`{key}` is on the ⛔ list but is not an item the core emits"
            );
        }
    }

    #[test]
    fn the_static_blocking_list_is_exactly_the_identity_half_of_the_fiscal_gate() {
        // ADR-0203 rejects on legal name ∧ tax id, and `business_identity` reads those same two
        // settings. Anything else added here would be a colour with no gate behind it.
        assert_eq!(BLOCKING_KEYS, [ITEM_BUSINESS_IDENTITY]);
    }

    #[test]
    fn the_three_levels_and_nothing_else() {
        // ⛔ beats 🔴 beats 🟡, and `required` can only reach the last two.
        assert_eq!(level_of(ITEM_BUSINESS_IDENTITY, false, &[]), LEVEL_LEGAL);
        assert_eq!(
            level_of(ITEM_BUSINESS_IDENTITY, true, &[]),
            LEVEL_LEGAL,
            "the ⛔ list wins over whatever `required` says"
        );
        assert_eq!(level_of(ITEM_APPS, true, &[]), LEVEL_FUNCTIONAL);
        assert_eq!(level_of(ITEM_TEAM, false, &[]), LEVEL_RECOMMENDED);
    }

    #[test]
    fn a_module_key_only_becomes_legal_when_the_core_hands_it_the_arm() {
        // The only way a module item reaches ⛔: the core resolved a gate arm onto it. A manifest
        // has no say — `required` is the only thing it declares, and it maps to 🔴/🟡.
        let arm = vec!["verifactu.setup".to_string()];
        assert_eq!(level_of("verifactu.setup", true, &[]), LEVEL_FUNCTIONAL);
        assert_eq!(level_of("verifactu.setup", true, &arm), LEVEL_LEGAL);
        assert_eq!(level_of("printing.setup", false, &arm), LEVEL_RECOMMENDED);
    }

    #[test]
    fn every_core_item_lands_on_one_of_the_three_levels() {
        for core in CORE_ITEMS {
            let level = level_of(core.key, core.required, &[]);
            assert!(
                [LEVEL_LEGAL, LEVEL_FUNCTIONAL, LEVEL_RECOMMENDED].contains(&level),
                "{} got `{level}`, which no surface knows how to paint",
                core.key
            );
        }
    }

    #[test]
    fn the_certificate_arm_disappears_once_the_certificate_is_loaded() {
        // With the certificate in the hub the gate accepts, so there is nothing left to block on —
        // even though the module that carries it may still be half-configured.
        let mut registry = Registry::new();
        registry
            .installed
            .push(certificate_manifest("verifactu"));
        assert_eq!(certificate_arm(&registry, false), vec!["verifactu.setup"]);
        assert!(certificate_arm(&registry, true).is_empty());
    }

    #[test]
    fn the_certificate_arm_is_keyed_on_the_capability_not_on_a_module_id() {
        // Same reason ADR-0203 never names `verifactu`: the runtime carries no business inside.
        let mut registry = Registry::new();
        registry.installed.push(certificate_manifest("fattura"));
        registry.installed.push(plain_manifest("verifactu"));
        assert_eq!(certificate_arm(&registry, false), vec!["fattura.setup"]);
    }

    #[test]
    fn a_hub_with_no_certificate_module_has_no_certificate_arm() {
        // The gate only demands the certificate WHILE such a module is installed, so a hub outside
        // Spain must not be told it is blocked by something nothing will ever ask it for.
        let mut registry = Registry::new();
        registry.installed.push(plain_manifest("inventory"));
        assert!(certificate_arm(&registry, false).is_empty());
    }

    fn certificate_manifest(id: &str) -> crate::manifest::Manifest {
        serde_json::from_value(json!({
            "id": id, "name": id, "version": "1.0.0",
            "capabilities": { "certificate": { "purpose": "fiscal-sign" } }
        }))
        .unwrap()
    }

    fn plain_manifest(id: &str) -> crate::manifest::Manifest {
        serde_json::from_value(json!({ "id": id, "name": id, "version": "1.0.0" })).unwrap()
    }

    #[test]
    fn a_module_item_key_is_derived_never_declared() {
        // Keyed by the core so a manifest cannot rename itself out of the ⛔ list.
        assert_eq!(item_key("verifactu"), "verifactu.setup");
    }
}
