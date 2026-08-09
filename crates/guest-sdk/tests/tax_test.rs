//! The tax rule contract (hub#295) — the ONE place the precedence is written.
//!
//! Until now `taxes`, `sales` and `invoice` each carried their own literal copy of
//! `resolve_root` + the qualification defaults. The precedence itself had not drifted yet, but
//! the edges around it had, and every one of those edges decides either what the customer is
//! CHARGED (`sales`) or what is DECLARED to the tax authority (`invoice`):
//!
//! * the catalog shape (`taxes` refused the paginated `{"rows": […]}` the other two accepted),
//! * `operation_class` validation (`taxes` clamped unknown values to `subject`, `invoice` copied
//!   them verbatim into the breakdown),
//! * the casing of the tax family (`IGIC` vs `igic`),
//! * how a boolean cell stringifies (`"true"` vs `""`).
//!
//! These tests are the contract those three entry points now share.

use erplora_guest_sdk::tax;
use serde_json::{json, Value};

/// A root rule: no `parent_id`.
fn root(id: &str, country: &str, region: &str, category: &str, rate: f64) -> Value {
    json!({
        "id": id,
        "country_code": country,
        "region_code": region,
        "tax_category_key": category,
        "rate_pct": rate,
        "tax_type": "vat",
    })
}

fn refs(rows: &[Value]) -> Vec<&Value> {
    rows.iter().collect()
}

// ── Precedence: region beats country ─────────────────────────────────────────

#[test]
fn an_exact_region_rule_beats_the_country_rule() {
    let rows = vec![
        root("es-vat", "ES", "", "standard", 21.0),
        root("es-cn-igic", "ES", "CN", "standard", 7.0),
    ];
    let hit = tax::resolve_root(&refs(&rows), "ES", "CN", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "es-cn-igic");
}

#[test]
fn the_country_rule_applies_when_the_region_has_none() {
    let rows = vec![
        root("es-vat", "ES", "", "standard", 21.0),
        root("es-cn-igic", "ES", "CN", "standard", 7.0),
    ];
    let hit = tax::resolve_root(&refs(&rows), "ES", "MD", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "es-vat");
}

#[test]
fn the_country_and_the_region_are_matched_case_insensitively() {
    let rows = vec![root("es-cn-igic", "es", "cn", "standard", 7.0)];
    let hit = tax::resolve_root(&refs(&rows), "ES", "CN", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "es-cn-igic");
}

#[test]
fn a_rule_of_another_country_never_matches() {
    let rows = vec![root("pt-vat", "PT", "", "standard", 23.0)];
    assert!(tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").is_none());
}

// The twin of the test above, on the axis the precedence actually splits (ERPlora/taxes#10).
//
// Spain is not one tax territory: the peninsula charges VAT, the Canaries charge IGIC, Ceuta and
// Melilla charge IPSI. They are different taxes of different jurisdictions, and a catalog that is
// complete in one of them and empty in another is the normal case, not the exotic one.
//
// So when neither the exact region nor a country-wide rule applies, the answer is «no rule» — and
// the caller has to deal with that. Resolving to a rule that belongs to ANOTHER region means the
// customer is charged one territory's tax and that territory's qualification is what gets declared.
#[test]
fn a_rule_of_another_region_never_matches() {
    let rows = vec![root("es-ce-ipsi", "ES", "CE", "standard", 10.0)];
    assert!(
        tax::resolve_root(&refs(&rows), "ES", "CN", "standard", "2026-08-07").is_none(),
        "a sale in the Canaries resolved with the rule of Ceuta",
    );
}

#[test]
fn each_spanish_territory_resolves_to_its_own_rule_or_to_none() {
    // A catalog with one rule per special territory and NO country-wide rule for the category.
    let rows = vec![
        root("es-cn-igic", "ES", "CN", "standard", 7.0),
        root("es-ce-ipsi", "ES", "CE", "standard", 10.0),
        root("es-ml-ipsi", "ES", "ML", "standard", 4.0),
    ];
    let resolved = |region: &str| {
        tax::resolve_root(&refs(&rows), "ES", region, "standard", "2026-08-07")
            .map(|hit| tax::rule_field(hit, "id"))
    };

    assert_eq!(resolved("CN").as_deref(), Some("es-cn-igic"));
    assert_eq!(resolved("CE").as_deref(), Some("es-ce-ipsi"));
    assert_eq!(resolved("ML").as_deref(), Some("es-ml-ipsi"));
    // The peninsula has no rule here and there is no country-wide one either. It must NOT borrow
    // one from an island or from a Spanish city in Africa.
    assert_eq!(resolved("MD"), None, "the peninsula borrowed another territory's rule");
    // Neither must a hub that never declared its region.
    assert_eq!(resolved(""), None, "a hub without region borrowed a regional rule");
}

#[test]
fn a_country_wide_rule_still_covers_a_region_that_has_none() {
    // The guard above must not break the normal case: the national rule is the fallback, the only
    // one there has ever been.
    let rows = vec![
        root("es-vat", "ES", "", "standard", 21.0),
        root("es-ce-ipsi", "ES", "CE", "standard", 10.0),
    ];
    let hit = tax::resolve_root(&refs(&rows), "ES", "CN", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "es-vat");
}

// ── Precedence inside a level: newest `valid_from`, then `id` ────────────────

#[test]
fn the_most_recent_valid_from_wins_inside_a_level() {
    let mut old = root("a-old", "ES", "", "standard", 18.0);
    old["valid_from"] = json!("2012-09-01");
    let mut new = root("b-new", "ES", "", "standard", 21.0);
    new["valid_from"] = json!("2021-01-01");
    let rows = vec![old, new];
    let hit = tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "b-new");
}

#[test]
fn a_tie_on_valid_from_is_broken_by_the_lowest_id() {
    let mut first = root("aaa", "ES", "", "standard", 21.0);
    first["valid_from"] = json!("2021-01-01");
    let mut second = root("bbb", "ES", "", "standard", 10.0);
    second["valid_from"] = json!("2021-01-01");
    let rows = vec![second, first];
    let hit = tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "aaa");
}

// ── Validity window and activity ─────────────────────────────────────────────

#[test]
fn a_rule_that_is_not_in_force_yet_is_ignored() {
    let mut future = root("future", "ES", "", "standard", 25.0);
    future["valid_from"] = json!("2027-01-01");
    let rows = vec![root("now", "ES", "", "standard", 21.0), future];
    let hit = tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "now");
}

#[test]
fn an_expired_rule_is_ignored() {
    let mut expired = root("expired", "ES", "", "standard", 18.0);
    expired["valid_to"] = json!("2012-08-31");
    let rows = vec![expired, root("now", "ES", "", "standard", 21.0)];
    let hit = tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "now");
}

#[test]
fn an_empty_date_disables_the_validity_filter() {
    let mut expired = root("expired", "ES", "", "standard", 18.0);
    expired["valid_to"] = json!("2012-08-31");
    let rows = vec![expired];
    assert!(tax::resolve_root(&refs(&rows), "ES", "", "standard", "").is_some());
}

#[test]
fn an_inactive_rule_is_ignored() {
    let mut off = root("off", "ES", "", "standard", 21.0);
    off["is_active"] = json!(false);
    let rows = vec![off];
    assert!(tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").is_none());
}

#[test]
fn a_missing_is_active_column_means_active() {
    let rows = vec![root("es-vat", "ES", "", "standard", 21.0)];
    assert!(tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").is_some());
}

#[test]
fn is_active_reads_the_integer_and_string_shapes_of_a_boolean() {
    for truthy in [json!(1), json!("1"), json!("true"), json!("True"), json!("yes"), json!(true)] {
        let mut row = root("r", "ES", "", "standard", 21.0);
        row["is_active"] = truthy.clone();
        assert!(tax::is_active(&row), "{truthy} should read as active");
    }
    for falsy in [json!(0), json!("0"), json!("false"), json!(false)] {
        let mut row = root("r", "ES", "", "standard", 21.0);
        row["is_active"] = falsy.clone();
        assert!(!tax::is_active(&row), "{falsy} should read as inactive");
    }
}

// ── A component is never a root ──────────────────────────────────────────────

#[test]
fn a_component_row_is_never_resolved_as_a_root() {
    let mut surcharge = root("surcharge", "ES", "", "standard", 5.2);
    surcharge["parent_id"] = json!("es-vat");
    let rows = vec![surcharge];
    assert!(tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").is_none());
}

// ── Reduced rates and exempt categories resolve by their own category ────────

#[test]
fn every_category_resolves_to_its_own_rule() {
    let rows = vec![
        root("es-standard", "ES", "", "standard", 21.0),
        root("es-reduced", "ES", "", "restaurant.food", 10.0),
        root("es-super-reduced", "ES", "", "bread", 4.0),
        root("es-exempt", "ES", "", "health.treatment", 0.0),
    ];
    let catalog = refs(&rows);
    for (category, id) in [
        ("standard", "es-standard"),
        ("restaurant.food", "es-reduced"),
        ("bread", "es-super-reduced"),
        ("health.treatment", "es-exempt"),
    ] {
        let hit = tax::resolve_root(&catalog, "ES", "", category, "2026-08-07").unwrap();
        assert_eq!(tax::rule_field(hit, "id"), id, "category {category}");
    }
}

// ── Components: root first, children by id ───────────────────────────────────

#[test]
fn components_are_the_root_first_then_its_children_by_id() {
    let mut child_b = root("z-child", "ES", "", "standard", 1.0);
    child_b["parent_id"] = json!("es-vat");
    child_b["tax_type"] = json!("other");
    let mut child_a = root("a-child", "ES", "", "standard", 5.2);
    child_a["parent_id"] = json!("es-vat");
    child_a["tax_type"] = json!("surcharge");
    let rows = vec![root("es-vat", "ES", "", "standard", 21.0), child_b, child_a];
    let catalog = refs(&rows);
    let root_rule = tax::resolve_root(&catalog, "ES", "", "standard", "2026-08-07").unwrap();
    let components = tax::rule_components(root_rule, &catalog, "2026-08-07");
    let ids: Vec<&str> = components.iter().map(|c| c.rule_id.as_str()).collect();
    assert_eq!(ids, vec!["es-vat", "a-child", "z-child"]);
    assert_eq!(tax::combined_rate_pct(&components), 27.2);
}

#[test]
fn a_child_outside_its_validity_window_is_dropped_from_the_components() {
    let mut child = root("surcharge", "ES", "", "standard", 5.2);
    child["parent_id"] = json!("es-vat");
    child["valid_to"] = json!("2020-12-31");
    let rows = vec![root("es-vat", "ES", "", "standard", 21.0), child];
    let catalog = refs(&rows);
    let root_rule = tax::resolve_root(&catalog, "ES", "", "standard", "2026-08-07").unwrap();
    let components = tax::rule_components(root_rule, &catalog, "2026-08-07");
    assert_eq!(components.len(), 1);
    assert_eq!(tax::combined_rate_pct(&components), 21.0);
}

#[test]
fn a_child_with_no_id_never_joins_the_components() {
    // A row with no id would match `parent_id == ""` against a root with no id either.
    let rows = vec![
        json!({"country_code": "ES", "tax_category_key": "standard", "rate_pct": 21.0}),
        json!({"parent_id": "", "country_code": "ES", "tax_category_key": "standard", "rate_pct": 9.9}),
    ];
    let catalog = refs(&rows);
    let root_rule = tax::resolve_root(&catalog, "ES", "", "standard", "2026-08-07").unwrap();
    let components = tax::rule_components(root_rule, &catalog, "2026-08-07");
    assert_eq!(components.len(), 1, "a row without id is not a child of a root without id");
}

#[test]
fn a_component_label_falls_back_to_the_tax_type() {
    let mut child = root("surcharge", "ES", "", "standard", 5.2);
    child["parent_id"] = json!("es-vat");
    child["tax_type"] = json!("surcharge");
    child["component_label"] = json!("Recargo de equivalencia");
    let rows = vec![root("es-vat", "ES", "", "standard", 21.0), child];
    let catalog = refs(&rows);
    let root_rule = tax::resolve_root(&catalog, "ES", "", "standard", "2026-08-07").unwrap();
    let components = tax::rule_components(root_rule, &catalog, "2026-08-07");
    assert_eq!(components[0].label, "vat", "no component_label → the tax_type is the label");
    assert_eq!(components[1].label, "Recargo de equivalencia");
}

// ── The catalog read: BOTH shapes, everywhere ────────────────────────────────
//
// This is where `taxes` diverged from `sales`/`invoice`: it only unwrapped a plain array, so the
// paginated shape the list engine composes left it with an empty catalog — 0 % charged by one
// entry point and 21 % by the next.

#[test]
fn the_catalog_accepts_a_plain_array() {
    let context = json!({"reads": {"taxes.rules.list": [root("es-vat", "ES", "", "standard", 21.0)]}});
    let catalog = tax::rule_catalog(&context, &Value::Null);
    assert_eq!(catalog.len(), 1);
}

#[test]
fn the_catalog_accepts_the_paginated_rows_shape() {
    let context = json!({
        "reads": {"taxes.rules.list": {"rows": [root("es-vat", "ES", "", "standard", 21.0)], "total": 1}}
    });
    let catalog = tax::rule_catalog(&context, &Value::Null);
    assert_eq!(catalog.len(), 1, "`{{rows: […]}}` is a catalog, not an empty catalog");
    let hit = tax::resolve_root(&catalog, "ES", "", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "es-vat");
}

#[test]
fn the_catalog_falls_back_to_the_payload_when_the_runtime_delivered_no_read() {
    let payload = json!({"rules": [root("es-vat", "ES", "", "standard", 21.0)]});
    let catalog = tax::rule_catalog(&Value::Null, &payload);
    assert_eq!(catalog.len(), 1);
}

#[test]
fn a_delivered_but_empty_read_is_authority_and_does_not_fall_back() {
    let context = json!({"reads": {"taxes.rules.list": []}});
    let payload = json!({"rules": [root("es-vat", "ES", "", "standard", 21.0)]});
    assert!(
        tax::rule_catalog(&context, &payload).is_empty(),
        "`the hub has no rules` is an answer, not a missing read"
    );
}

#[test]
fn the_alternative_catalog_read_keys_are_honoured() {
    for key in ["taxes.rules.list", "taxes.rules.by_country", "rules"] {
        let context = json!({"reads": {key: [root("es-vat", "ES", "", "standard", 21.0)]}});
        assert_eq!(tax::rule_catalog(&context, &Value::Null).len(), 1, "read key {key}");
    }
}

// ── Qualification (ADR-0186): what is DECLARED ───────────────────────────────

#[test]
fn a_rule_with_no_qualification_columns_is_a_plain_domestic_sale() {
    let q = tax::rule_qualification(&root("es-vat", "ES", "", "standard", 21.0));
    assert_eq!(q.operation_class, "subject");
    assert_eq!(q.regime_key, "01");
    assert_eq!(q.exempt_reason, "");
    assert_eq!(q.tax_kind, "vat");
}

#[test]
fn an_unknown_operation_class_falls_back_to_subject() {
    // The list is closed on purpose: a free-form value would reach the fiscal record as a
    // qualification that does not exist, and the rejection arrives with the invoice number
    // already spent. `invoice` used to copy it verbatim while `taxes` clamped it — charging one
    // thing and declaring another.
    let mut rule = root("es-vat", "ES", "", "standard", 21.0);
    rule["operation_class"] = json!("exent");
    assert_eq!(tax::rule_qualification(&rule).operation_class, "subject");
}

#[test]
fn every_admitted_operation_class_survives_untouched() {
    for class in tax::OPERATION_CLASSES {
        let mut rule = root("es-vat", "ES", "", "standard", 21.0);
        rule["operation_class"] = json!(class.to_uppercase());
        assert_eq!(&tax::rule_qualification(&rule).operation_class, class);
    }
}

#[test]
fn the_exempt_reason_is_kept_uppercased_only_for_exempt_operations() {
    let mut exempt = root("es-health", "ES", "", "health.treatment", 0.0);
    exempt["operation_class"] = json!("exempt");
    exempt["exempt_reason"] = json!("e1");
    assert_eq!(tax::rule_qualification(&exempt).exempt_reason, "E1");

    let mut subject = root("es-vat", "ES", "", "standard", 21.0);
    subject["exempt_reason"] = json!("E1");
    assert_eq!(
        tax::rule_qualification(&subject).exempt_reason,
        "",
        "a reason on a non-exempt rule is noise, not a declaration"
    );
}

#[test]
fn the_regime_key_travels_opaque_with_the_general_regime_as_default() {
    let mut rule = root("es-vat", "ES", "", "standard", 21.0);
    rule["regime_key"] = json!(" 08 ");
    assert_eq!(tax::rule_qualification(&rule).regime_key, "08");
}

#[test]
fn the_tax_kind_is_lowercased_with_vat_as_the_default() {
    let mut igic = root("es-cn-igic", "ES", "CN", "standard", 7.0);
    igic["tax_type"] = json!("IGIC");
    assert_eq!(
        tax::rule_qualification(&igic).tax_kind,
        "igic",
        "the family that decides which tax is declared has ONE spelling"
    );
    let mut empty = root("es-vat", "ES", "", "standard", 21.0);
    empty["tax_type"] = json!("");
    assert_eq!(tax::rule_qualification(&empty).tax_kind, "vat");
}

// ── Field coercion: the same cell reads the same everywhere ──────────────────

#[test]
fn a_field_stringifies_numbers_and_booleans_the_same_way_for_every_caller() {
    let row = json!({"id": 42, "flag": true, "nothing": Value::Null});
    assert_eq!(tax::rule_field(&row, "id"), "42");
    assert_eq!(tax::rule_field(&row, "flag"), "true");
    assert_eq!(tax::rule_field(&row, "nothing"), "");
    assert_eq!(tax::rule_field(&row, "absent"), "");
}

#[test]
fn a_numeric_id_orders_like_the_string_it_stringifies_to() {
    let mut a = root("", "ES", "", "standard", 21.0);
    a["id"] = json!(2);
    let mut b = root("", "ES", "", "standard", 10.0);
    b["id"] = json!(1);
    let rows = vec![a, b];
    let hit = tax::resolve_root(&refs(&rows), "ES", "", "standard", "2026-08-07").unwrap();
    assert_eq!(tax::rule_field(hit, "id"), "1");
}

#[test]
fn a_rate_reads_from_both_the_number_and_the_string_shape() {
    let mut as_string = root("es-vat", "ES", "", "standard", 0.0);
    as_string["rate_pct"] = json!("21.0");
    assert_eq!(tax::rule_rate_pct(&as_string, -1.0), 21.0);
    assert_eq!(tax::rule_rate_pct(&json!({}), -1.0), -1.0);
}

// ── The three entry points agree on the shared fixture ───────────────────────
//
// The fixture below is the one `taxes`, `sales` and `invoice` each replay in their own test
// suite. Resolving it here and there is what proves the three entry points read the SAME
// catalog the SAME way.

#[test]
fn the_shared_fixture_resolves_to_one_answer_per_scenario() {
    let rows: Vec<Value> = serde_json::from_value(shared_fixture_rules()).unwrap();
    let catalog = refs(&rows);
    let date = "2026-08-07";

    // Peninsula: standard VAT, plus the equivalence surcharge as a component.
    let peninsula = tax::resolve_root(&catalog, "ES", "MD", "standard", date).unwrap();
    assert_eq!(tax::rule_field(peninsula, "id"), "es-vat-21");
    let components = tax::rule_components(peninsula, &catalog, date);
    assert_eq!(tax::combined_rate_pct(&components), 26.2);
    assert_eq!(tax::rule_qualification(peninsula).tax_kind, "vat");

    // Canary Islands: the region rule wins and the tax family changes.
    let canaries = tax::resolve_root(&catalog, "ES", "CN", "standard", date).unwrap();
    assert_eq!(tax::rule_field(canaries, "id"), "es-cn-igic-7");
    assert_eq!(tax::rule_qualification(canaries).tax_kind, "igic");

    // Reduced rate.
    let reduced = tax::resolve_root(&catalog, "ES", "MD", "restaurant.food", date).unwrap();
    assert_eq!(tax::rule_rate_pct(reduced, -1.0), 10.0);

    // Exempt category: 0 %, and the reason travels.
    let exempt = tax::resolve_root(&catalog, "ES", "MD", "health.treatment", date).unwrap();
    let q = tax::rule_qualification(exempt);
    assert_eq!(q.operation_class, "exempt");
    assert_eq!(q.exempt_reason, "E1");

    // Garbage in `operation_class` is clamped, never declared.
    let broken = tax::resolve_root(&catalog, "ES", "MD", "broken.class", date).unwrap();
    assert_eq!(tax::rule_qualification(broken).operation_class, "subject");
}

/// The catalog the three entry points share in their own tests (hub#295).
pub fn shared_fixture_rules() -> Value {
    json!([
        {"id": "es-vat-21", "country_code": "ES", "region_code": "", "tax_category_key": "standard",
         "rate_pct": 21.0, "tax_type": "vat", "valid_from": "2012-09-01"},
        {"id": "es-vat-21-surcharge", "parent_id": "es-vat-21", "country_code": "ES", "region_code": "",
         "tax_category_key": "standard", "rate_pct": 5.2, "tax_type": "surcharge"},
        {"id": "es-cn-igic-7", "country_code": "ES", "region_code": "CN", "tax_category_key": "standard",
         "rate_pct": 7.0, "tax_type": "IGIC"},
        {"id": "es-vat-10", "country_code": "ES", "region_code": "", "tax_category_key": "restaurant.food",
         "rate_pct": 10.0, "tax_type": "vat"},
        {"id": "es-exempt-health", "country_code": "ES", "region_code": "",
         "tax_category_key": "health.treatment", "rate_pct": 0.0, "tax_type": "vat",
         "operation_class": "exempt", "exempt_reason": "e1"},
        {"id": "es-broken-class", "country_code": "ES", "region_code": "",
         "tax_category_key": "broken.class", "rate_pct": 21.0, "tax_type": "vat",
         "operation_class": "exent"}
    ])
}
