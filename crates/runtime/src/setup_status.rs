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
//! # What deliberately is NOT here
//!
//! The three levels (⛔ legal · 🔴 functional · 🟡 recommended) are hub#370. This module carries the
//! seam they plug into — [`BLOCKING_KEYS`], the core-owned ⛔ list, empty for now — and nothing
//! else. Emitting a `level` today would promise a gate that only ADR-0203 makes true, and "blocks"
//! that does not block is how a checklist becomes decorative. Likewise the third state of the apps
//! item ("unavailable", hub#371): [`STATE_DONE`]/[`STATE_PENDING`] are strings precisely so that
//! adding a third value is an addition, not a break.
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

/// **The ⛔ list, and it belongs to the core.** A blocking item is one the runtime actually rejects
/// — the fiscal precondition of ADR-0203 read from the other side — so it can never be something a
/// third-party manifest declares about itself.
///
/// Empty until hub#370 fills it, and empty is the honest value: `blocking_pending` counts these, so
/// today it is 0 and the blocking strip (hub#374) stays silent instead of blocking a sale over a
/// label with no gate behind it.
pub const BLOCKING_KEYS: &[&str] = &[];

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

    let mut items: Vec<Json> = Vec::new();
    for core in CORE_ITEMS {
        if let Some(done) = core_item_done(db, registry, hub_id, core, &setting).await {
            items.push(item_json(
                core.key,
                "core",
                None,
                done,
                core.required,
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
        items.push(item_json(
            &item_key(&manifest.id),
            "module",
            Some(&manifest.id),
            done,
            def.required,
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
    let blocking_pending = items
        .iter()
        .filter(|i| {
            i["state"] == STATE_PENDING
                && i["key"]
                    .as_str()
                    .is_some_and(|k| BLOCKING_KEYS.contains(&k))
        })
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

/// Every item carries every key (with `module_id` null for a core item), so a consumer never has to
/// branch on whether a field is present.
#[allow(clippy::too_many_arguments)]
fn item_json(
    key: &str,
    source: &str,
    module_id: Option<&str>,
    done: bool,
    required: bool,
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
        "required": required,
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
    fn the_blocking_list_is_core_owned_and_still_empty() {
        // hub#370 fills it, and not before ADR-0203 makes ⛔ true. An entry here without a gate
        // behind it would be a colour pretending to be a rule.
        assert!(BLOCKING_KEYS.is_empty());
    }

    #[test]
    fn a_module_item_key_is_derived_never_declared() {
        // Keyed by the core so a manifest cannot rename itself out of the ⛔ list.
        assert_eq!(item_key("verifactu"), "verifactu.setup");
    }
}
