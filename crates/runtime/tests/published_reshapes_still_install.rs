//! 🔴 **The blast radius of the N/N-1 rule of hub#1163, measured against the real SQL.**
//!
//! Regression test for ERPlora/hub#1163. Adding `RENAME COLUMN`, `RENAME TO` and
//! `ALTER COLUMN … TYPE` to what a migration may not do as `expand` puts **twelve already
//! published files, across eight modules**, on the wrong side of a rule that did not exist when
//! they were written. They are installed across the fleet — and, what matters here, they are
//! re-run in full on every FRESH install. Refusing them now would undo nothing; it would just
//! stop eight modules from installing, which is the failure that cost the 19/08 (four modules
//! published green and did not install).
//!
//! So they are grandfathered, and this file is what keeps the pass honest in **both** directions:
//!
//!  - too short and eight modules go red without anyone touching them,
//!  - too long and the list carries permissions nothing needs — the quiet way a grandfather list
//!    turns into the door it was supposed to close.
//!
//! The files are frozen here as fixtures, copied from the `origin/main` of each module repo on
//! 2026-08-28, because the runtime cannot read `modules-workspace` in CI — the same reason, and
//! the same shape, as `published_contracts_still_install.rs`.
use erplora_runtime::migration_guard::{check, Kind, Plan, RESHAPE_GRANDFATHERED};

/// Each file, with the `module_id` and the name the hub really applies it under.
const PUBLISHED: &[(&str, &str, &str)] = &[
    (
        "cart_checkout",
        "migrations/postgres/003_quantity_fixed_point.sql",
        include_str!("fixtures/published_reshapes/cart_checkout__003_quantity_fixed_point.sql"),
    ),
    (
        "inventory",
        "migrations/postgres/002_tax_rate_id.sql",
        include_str!("fixtures/published_reshapes/inventory__002_tax_rate_id.sql"),
    ),
    (
        "inventory",
        "migrations/postgres/004_tax_category_key.sql",
        include_str!("fixtures/published_reshapes/inventory__004_tax_category_key.sql"),
    ),
    (
        "inventory",
        "migrations/postgres/005_stock_ledger.sql",
        include_str!("fixtures/published_reshapes/inventory__005_stock_ledger.sql"),
    ),
    (
        "inventory",
        "migrations/postgres/006_quantity_fixed_point.sql",
        include_str!("fixtures/published_reshapes/inventory__006_quantity_fixed_point.sql"),
    ),
    (
        "invoice",
        "migrations/postgres/004_quantity_fixed_point.sql",
        include_str!("fixtures/published_reshapes/invoice__004_quantity_fixed_point.sql"),
    ),
    (
        "kitchen",
        "migrations/postgres/004_dispatch_snapshot.sql",
        include_str!("fixtures/published_reshapes/kitchen__004_dispatch_snapshot.sql"),
    ),
    (
        "kitchen",
        "migrations/postgres/005_quantity_fixed_point.sql",
        include_str!("fixtures/published_reshapes/kitchen__005_quantity_fixed_point.sql"),
    ),
    (
        "pricing",
        "migrations/postgres/005_quantity_fixed_point.sql",
        include_str!("fixtures/published_reshapes/pricing__005_quantity_fixed_point.sql"),
    ),
    (
        "sales",
        "migrations/postgres/014_quantity_fixed_point.sql",
        include_str!("fixtures/published_reshapes/sales__014_quantity_fixed_point.sql"),
    ),
    (
        "services",
        "migrations/postgres/005_tax_category_key.sql",
        include_str!("fixtures/published_reshapes/services__005_tax_category_key.sql"),
    ),
    (
        "services",
        "migrations/postgres/006_quantity_fixed_point.sql",
        include_str!("fixtures/published_reshapes/services__006_quantity_fixed_point.sql"),
    ),
];

/// Nothing that is already installed in the fleet may stop installing.
#[test]
fn every_published_reshape_still_installs_hub1163() {
    for (module_id, filename, sql) in PUBLISHED {
        let plan = check(module_id, filename, sql, Kind::Expand).unwrap_or_else(|e| {
            panic!(
                "🔴 `{module_id}/{filename}` está PUBLICADO y el guard lo rechaza: {e}\n\
                 Una regla nueva no puede poner en rojo lo que ya está instalado en la flota."
            )
        });
        assert_eq!(
            plan,
            Plan::AsWritten,
            "un `expand` se aplica tal cual: {module_id}/{filename}"
        );
    }
}

/// 🔴 **The positive control: every entry has to be NEEDED.**
///
/// The same SQL, under a file name that is not on the list, has to be REFUSED. Without this the
/// list could quietly hold files that pass on their own merits — and a grandfather list nobody
/// can tell is dead is exactly how «grandfather it» becomes the way to keep publishing what the
/// contract forbids.
#[test]
fn every_grandfathered_reshape_would_be_refused_without_its_pass_hub1163() {
    for (module_id, filename, sql) in PUBLISHED {
        let refused = check(
            module_id,
            "migrations/postgres/999_not_on_the_list.sql",
            sql,
            Kind::Expand,
        );

        assert!(
            refused.is_err(),
            "🔴 `{module_id}/{filename}` pasa sin el abuelado: sobra de RESHAPE_GRANDFATHERED"
        );
    }
}

/// The list and the frozen corpus name exactly the same files, or one of the two checks above is
/// measuring something that is no longer the rule.
#[test]
fn the_frozen_corpus_is_exactly_the_grandfathered_list_hub1163() {
    let listed: Vec<(&str, &str)> = RESHAPE_GRANDFATHERED.to_vec();
    let frozen: Vec<(&str, &str)> = PUBLISHED.iter().map(|(m, f, _)| (*m, *f)).collect();

    assert_eq!(
        listed, frozen,
        "`RESHAPE_GRANDFATHERED` y los fixtures de `tests/fixtures/published_reshapes/` divergen"
    );
}
