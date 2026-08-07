//! **The tax rule contract of ERPlora. Once, here.** (hub#295)
//!
//! Which rule applies to `(country, region, category, date)` — ADR-0085 — and how the operation
//! is qualified for the fiscal record — ADR-0186. This module does NOT compute money: the
//! arithmetic is [`crate::money`] (ADR-0123) and it stays there.
//!
//! # Why it exists
//!
//! The very same resolution used to live written THREE times, literally copied:
//!
//! | Where | What it decided |
//! |---|---|
//! | `taxes::resolve_root` | the `taxes.calculate` contract |
//! | `sales::resolve_root` | the rate the customer is CHARGED |
//! | `invoice::resolve_root` | the qualification DECLARED to the tax authority (ADR-0186) |
//!
//! WASM guests cannot call each other, so each handler carried its own copy. The precedence
//! itself had not drifted yet, but everything around it had — and each of those edges decides
//! either what is charged or what is declared:
//!
//! * **the catalog shape.** `taxes` unwrapped only a plain array; `sales` and `invoice` also
//!   accepted the paginated `{"rows": […]}` the list engine composes. Same read, and one entry
//!   point saw an empty catalog while the other two saw the rules.
//! * **`operation_class`.** `taxes` clamped anything outside the closed list to `subject`;
//!   `invoice` only defaulted the EMPTY value and copied any other string verbatim into the
//!   breakdown. A typo in a rule meant charging a plain domestic sale and declaring a
//!   qualification that does not exist.
//! * **the tax family.** `taxes` emitted `tax_type` as stored (`IGIC`), `invoice` lowercased it
//!   (`igic`). Two spellings of the key that decides WHICH tax is declared.
//! * **string coercion.** `taxes`/`sales` rendered a boolean cell as `"true"`, `invoice` as `""`
//!   — enough for `parent_id` or `region_code` to read as empty in one entry point only, which
//!   turns a component into a root, or a regional rule into a national one.
//!
//! Nothing guaranteed they would keep agreeing: the next change to the precedence touched three
//! files in three repositories. Now it touches this one.
//!
//! # The rule that is resolved
//!
//! 1. Candidates: **root** rows (no `parent_id`), active, in force on the date, of the requested
//!    country and category.
//! 2. An exact **region** match beats a country rule (empty/NULL region).
//! 3. Inside a level, the most recent `valid_from` wins; ties break by `id` ascending, so the
//!    answer is deterministic and does not depend on the order the rows arrived in.
//!
//! A rule says how much is charged (`rate_pct`) and which family it belongs to (`tax_type`); its
//! **components** (rows with `parent_id == root.id`, e.g. the Spanish equivalence surcharge) add
//! quota over the same base without turning half a line into another operation.

use serde_json::Value;

/// Reads that may carry the rule catalog, in precedence order. `taxes.rules.list` is the one the
/// runtime pre-loads (ADR-0069); the other two are historical aliases kept so a caller that
/// declared them does not silently lose its catalog.
pub const CATALOG_READS: &[&str] = &["taxes.rules.list", "taxes.rules.by_country", "rules"];

/// Admitted operation classes. The list is **closed** on purpose: a free-form value would reach
/// the fiscal record as a qualification that does not exist, and the rejection arrives with the
/// invoice number already spent in the chain.
pub const OPERATION_CLASSES: &[&str] = &[
    // Subject and not exempt, no reverse charge — the normal POS case.
    "subject",
    // Subject and not exempt WITH reverse charge (the customer self-assesses the quota).
    "subject_reverse",
    // Exempt: the operation is subject but the law exempts it. Requires `exempt_reason`.
    "exempt",
    // Not subject by the nature of the operation.
    "not_subject",
    // Not subject by place-of-supply rules (it is taxed in another jurisdiction).
    "not_subject_location",
];

/// Default regime: the general one.
pub const DEFAULT_REGIME: &str = "01";

/// Default tax family when the rule does not name one.
pub const DEFAULT_TAX_KIND: &str = "vat";

/// One component to apply over the line base: the root rule or one of its children.
#[derive(Debug, Clone, PartialEq)]
pub struct TaxComponent {
    /// The rate, in percent. A rate is not money (it carries decimals); multiplying it by money
    /// PRODUCES money, and that product is [`crate::money`]'s job, not this module's.
    pub rate_pct: f64,
    /// Id of the row this component came from (the root, or one of its children).
    pub rule_id: String,
    /// Display label: `component_label` when the row carries one, the `tax_type` otherwise.
    pub label: String,
    /// The `tax_type` **as stored** — a label, not the fiscal key. The key that decides which
    /// tax is declared is [`Qualification::tax_kind`], which is normalised.
    pub tax_type: String,
}

/// How the operation is DECLARED (ADR-0186). `regime_key` and `exempt_reason` travel **opaque**:
/// they are jurisdiction codes (in Spain, the `ClaveRegimen` of lists L8A/L8B and the
/// `OperacionExenta` of L10). Whoever translates them into XML is the country's compliance
/// module; this contract only carries them.
#[derive(Debug, Clone, PartialEq)]
pub struct Qualification {
    /// One of [`OPERATION_CLASSES`]. Anything else is clamped to `subject`.
    pub operation_class: String,
    pub regime_key: String,
    /// Uppercased, and only kept when the operation is `exempt`.
    pub exempt_reason: String,
    /// The tax family of the ROOT rule (`vat` | `igic` | `ipsi` | …), lowercased.
    pub tax_kind: String,
}

// ── Row reading: one coercion for the three entry points ─────────────────────

/// A cell as a string. Numbers and booleans stringify instead of vanishing: a driver that hands
/// back `id` as a number, or a boolean where a code was expected, must read the same for whoever
/// charges and for whoever declares.
fn as_str(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        _ => String::new(),
    }
}

/// A column of a rule row as a string (empty when absent or NULL).
pub fn rule_field(rule: &Value, key: &str) -> String {
    as_str(rule.get(key).unwrap_or(&Value::Null))
}

/// A rate as `f64`, tolerating the string shape some drivers return for `NUMERIC`.
pub fn rule_rate_pct(rule: &Value, default: f64) -> f64 {
    match rule.get("rate_pct") {
        Some(Value::Number(n)) => n.as_f64().unwrap_or(default),
        Some(Value::String(s)) => s.trim().parse::<f64>().unwrap_or(default),
        _ => default,
    }
}

/// Is the row a ROOT rule (not a component)? `parent_id` empty/NULL.
pub fn is_root(rule: &Value) -> bool {
    rule_field(rule, "parent_id").is_empty()
}

/// Is the row active? A missing column means active — the query already filters.
pub fn is_active(rule: &Value) -> bool {
    match rule.get("is_active") {
        None | Some(Value::Null) => true,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_i64().unwrap_or(0) != 0,
        Some(Value::String(s)) => matches!(s.as_str(), "1" | "true" | "True" | "yes"),
        _ => false,
    }
}

/// Is the row in force on `date` (`YYYY-MM-DD`)? ISO dates compare as strings. An empty date
/// disables the filter (an ad-hoc calculation with no date resolves against every rule).
pub fn is_valid_on(rule: &Value, date: &str) -> bool {
    if date.is_empty() {
        return true;
    }
    let from = rule_field(rule, "valid_from");
    let until = rule_field(rule, "valid_to");
    (from.is_empty() || from.as_str() <= date) && (until.is_empty() || until.as_str() >= date)
}

/// Unwraps the rows of a read the runtime pre-loaded in `context.reads["<query>"]` (ADR-0069).
///
/// `None` means the runtime did NOT deliver that read — the query failed, the manifest does not
/// declare it, or the hub runs a runtime without `reads`. That is a very different thing from
/// `Some(vec![])`, "the query ran and the hub has nothing to say": the first degrades to the
/// caller's hint, the second is authority.
///
/// Both shapes are tolerated on purpose: a plain array, and the paginated `{"rows": […]}` the
/// list engine composes.
pub fn read_rows<'a>(context: &'a Value, query: &str) -> Option<Vec<&'a Value>> {
    let node = context.get("reads").and_then(|reads| reads.get(query))?;
    match node {
        Value::Array(rows) => Some(rows.iter().collect()),
        Value::Object(_) => {
            node.get("rows").and_then(|v| v.as_array()).map(|rows| rows.iter().collect())
        }
        _ => None,
    }
}

/// The candidate rules: the first of [`CATALOG_READS`] the runtime actually delivered, with a
/// fallback to `payload.rules` for callers that run without pre-loaded reads.
///
/// Pass `&Value::Null` as the payload when there is no such fallback.
pub fn rule_catalog<'a>(context: &'a Value, payload: &'a Value) -> Vec<&'a Value> {
    for query in CATALOG_READS {
        if let Some(rows) = read_rows(context, query) {
            return rows;
        }
    }
    payload
        .get("rules")
        .and_then(|v| v.as_array())
        .map(|rows| rows.iter().collect())
        .unwrap_or_default()
}

// ── The resolution ───────────────────────────────────────────────────────────

/// Resolves the ROOT rule that applies to `(country_code, region_code, category_key, date)`.
///
/// Precedence: exact region → country rule (empty/NULL region). Inside a level, the most recent
/// `valid_from` first, then `id` ascending.
pub fn resolve_root<'a>(
    rules: &[&'a Value],
    country_code: &str,
    region_code: &str,
    category_key: &str,
    date: &str,
) -> Option<&'a Value> {
    let eligible: Vec<&'a Value> = rules
        .iter()
        .copied()
        .filter(|rule| {
            is_root(rule)
                && is_active(rule)
                && is_valid_on(rule, date)
                && rule_field(rule, "country_code").eq_ignore_ascii_case(country_code)
                && rule_field(rule, "tax_category_key") == category_key
        })
        .collect();

    if !region_code.is_empty() {
        let regional = eligible
            .iter()
            .copied()
            .filter(|rule| rule_field(rule, "region_code").eq_ignore_ascii_case(region_code))
            .collect();
        if let Some(hit) = pick_best(regional) {
            return Some(hit);
        }
    }
    let national =
        eligible.iter().copied().filter(|rule| rule_field(rule, "region_code").is_empty()).collect();
    pick_best(national).or_else(|| pick_best(eligible))
}

/// Best of a set: newest `valid_from` first, then `id` ascending. Deterministic — the answer
/// must not depend on the order the rows arrived in.
fn pick_best<'a>(mut rows: Vec<&'a Value>) -> Option<&'a Value> {
    rows.sort_by(|a, b| {
        rule_field(b, "valid_from")
            .cmp(&rule_field(a, "valid_from"))
            .then_with(|| rule_field(a, "id").cmp(&rule_field(b, "id")))
    });
    rows.first().copied()
}

/// Expands the root rule into the components to apply (ADR-0085): the root itself plus its
/// children (rows with `parent_id == root.id`, active and in force), ordered by `id`.
///
/// A root with no id has no children: matching `parent_id == ""` against it would swallow every
/// other root in the catalog.
pub fn rule_components<'a>(root: &'a Value, rules: &[&'a Value], date: &str) -> Vec<TaxComponent> {
    let root_id = rule_field(root, "id");
    let mut components = vec![component_from_rule(root)];
    if root_id.is_empty() {
        return components;
    }
    let mut children: Vec<&'a Value> = rules
        .iter()
        .copied()
        .filter(|rule| {
            !rule_field(rule, "id").is_empty()
                && rule_field(rule, "parent_id") == root_id
                && is_active(rule)
                && is_valid_on(rule, date)
        })
        .collect();
    children.sort_by_key(|rule| rule_field(rule, "id"));
    components.extend(children.into_iter().map(component_from_rule));
    components
}

fn component_from_rule(rule: &Value) -> TaxComponent {
    let tax_type = rule_field(rule, "tax_type");
    let label = {
        let explicit = rule_field(rule, "component_label");
        if explicit.is_empty() { tax_type.clone() } else { explicit }
    };
    TaxComponent {
        rate_pct: rule_rate_pct(rule, 0.0),
        rule_id: rule_field(rule, "id"),
        label,
        tax_type,
    }
}

/// The combined rate of a set of components (the root plus its children over the same base).
pub fn combined_rate_pct(components: &[TaxComponent]) -> f64 {
    components.iter().map(|component| component.rate_pct).sum()
}

// ── The qualification (ADR-0186) ─────────────────────────────────────────────

/// How the ROOT rule qualifies the operation, with the defaults that keep every rule created
/// before ADR-0186 — none of which carries these columns — meaning exactly what it meant: a
/// domestic sale, general regime, not exempt.
///
/// The qualification is the root's, never a component's: the equivalence surcharge adds quota
/// over the same base, it does not turn half a line into a different operation.
pub fn rule_qualification(rule: &Value) -> Qualification {
    let operation_class = {
        let raw = rule_field(rule, "operation_class").trim().to_ascii_lowercase();
        if OPERATION_CLASSES.contains(&raw.as_str()) { raw } else { "subject".to_string() }
    };
    let regime_key = {
        let raw = rule_field(rule, "regime_key").trim().to_string();
        if raw.is_empty() { DEFAULT_REGIME.to_string() } else { raw }
    };
    let exempt_reason = if operation_class == "exempt" {
        rule_field(rule, "exempt_reason").trim().to_ascii_uppercase()
    } else {
        String::new()
    };
    let tax_kind = {
        let raw = rule_field(rule, "tax_type").trim().to_ascii_lowercase();
        if raw.is_empty() { DEFAULT_TAX_KIND.to_string() } else { raw }
    };
    Qualification { operation_class, regime_key, exempt_reason, tax_kind }
}
