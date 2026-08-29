//! 🔴 **`MONEY_COLUMNS` calls itself the authoritative inventory of money columns. This is what
//! makes that claim checkable instead of a promise in a doc-comment.**
//!
//! The inventory drives the euros→cents backfill (ADR-0007/ADR-0123). A wrong entry never crashes:
//! `declared_type()` asks `information_schema` and returns `None` for a table the database does not
//! have, so a phantom entry is skipped **in silence**. That silence is the whole problem — it let
//! six entries survive their own tables (hub#1144, hub#1146):
//!
//!   * `orders_order`, `kitchen_orders_*` — modules that do not exist (`kitchen_orders` was merged
//!     into `kitchen` by ADR-0014 and archived);
//!   * `kitchen_order_modifier`, `services_variant`, `services_addon` — tables retired by a
//!     published `contract` migration.
//!
//! Twice already (services#67, services#69) a name in this list had to be proven dead **by reading
//! the runtime** before the module could retire its table. An inventory that names tables nobody
//! creates turns every orphan audit into manual work — exactly the work it exists to save.
//!
//! ## Two ratchets, because the truth lives in two places
//!
//! 1. [`no_money_column_names_a_table_a_published_contract_retired`] — **offline, always runs.**
//!    Reads the `contract` migrations already frozen under `tests/fixtures/published_contracts/`
//!    (the same fixtures `published_contracts_still_install.rs` uses) and refuses any table they
//!    retire. No sibling repo, no network: it has teeth in CI.
//! 2. [`every_money_table_is_created_by_a_published_module_migration`] — **guarded by
//!    [`erplora_runtime::require_modules_workspace`]**, the hub's established pattern for reading
//!    the real catalogue (ERPlora/hub#253): it runs where the modules are, skips *visibly* in CI,
//!    and panics loudly rather than going green empty.
//!
//! Both carry a **positive control**: a sweep that silently parsed nothing would otherwise report
//! "no phantom entries" and be green while checking nothing (ERPlora/pm — verify your check detects
//! the positive).
//!
//! The other two tests guard the shape of the list itself: a duplicate entry would convert the same
//! column twice (`ROUND(col*100)` applied twice = ×10 000 — money corruption, not a typo), and the
//! head of the list is still a live money column even though, since hub#1209, its POSITION decides
//! nothing: the verdict is now a consensus over every money column present, checked against a
//! seeded database in `money_backfill_mixed_hub.rs`.

use std::collections::{BTreeMap, BTreeSet};

use erplora_runtime::money_backfill::MONEY_COLUMNS;

/// The published `contract` migrations, frozen verbatim in this repo. Same files, same rationale as
/// `published_contracts_still_install.rs`: the runtime cannot read `modules-workspace` in CI, so the
/// SQL that retires a table lives here as a fixture.
const PUBLISHED_CONTRACTS: &[(&str, &str)] = &[
    ("kitchen/007_retire_order_modifier.sql", include_str!("fixtures/published_contracts/kitchen__007_retire_order_modifier.sql")),
    ("services/009_retire_addon_tables.sql", include_str!("fixtures/published_contracts/services__009_retire_addon_tables.sql")),
    ("services/010_retire_variant_table.sql", include_str!("fixtures/published_contracts/services__010_retire_variant_table.sql")),
    ("verifactu/012_named_gate_constraints.sql", include_str!("fixtures/published_contracts/verifactu__012_named_gate_constraints.sql")),
];

/// Tables the frozen `contract` migrations retire, as `table -> migration that retired it`.
///
/// A `contract` retires a table with `DROP TABLE [IF EXISTS] <name>;` at the START of the statement
/// — the runtime translates that into `ALTER TABLE … RENAME TO _deprecated_…` instead of executing
/// it (`migration_guard::set_aside_instead_of_dropping`, hub#1137). Retired either way: the module
/// no longer creates it and `declared_type()` will never find it again.
fn tables_retired_by_published_contracts() -> BTreeMap<String, String> {
    let mut retired = BTreeMap::new();
    for (source, sql) in PUBLISHED_CONTRACTS {
        for statement in sql.split(';') {
            // Skip comment-only lines: the prose in these files deliberately sits BELOW the DROP.
            let code: String = statement
                .lines()
                .filter(|l| !l.trim_start().starts_with("--"))
                .collect::<Vec<_>>()
                .join(" ");
            let code = code.split_whitespace().collect::<Vec<_>>().join(" ");
            let upper = code.to_uppercase();
            let Some(rest) = upper.strip_prefix("DROP TABLE ") else { continue };
            let rest = rest.strip_prefix("IF EXISTS ").unwrap_or(rest);
            if let Some(name) = rest.split_whitespace().next() {
                retired.insert(name.to_ascii_lowercase(), (*source).to_string());
            }
        }
    }
    retired
}

/// Every table any published module migration CREATEs, as `table -> migration that creates it`.
/// Reads the real catalogue under [`erplora_runtime::modules_root`].
fn tables_created_by_the_catalogue() -> BTreeMap<String, String> {
    let root = erplora_runtime::modules_root();
    let mut created = BTreeMap::new();
    let entries = std::fs::read_dir(&root)
        .unwrap_or_else(|e| panic!("cannot read the module catalogue at {}: {e}", root.display()));
    for entry in entries.flatten() {
        let module_dir = entry.path();
        let migrations = module_dir.join("migrations").join("postgres");
        if !migrations.is_dir() {
            continue;
        }
        let module = module_dir.file_name().unwrap_or_default().to_string_lossy().to_string();
        let mut files: Vec<_> = std::fs::read_dir(&migrations)
            .unwrap_or_else(|e| panic!("cannot read {}: {e}", migrations.display()))
            .flatten()
            .map(|f| f.path())
            .filter(|p| p.extension().is_some_and(|e| e == "sql"))
            .collect();
        files.sort();
        for file in files {
            let Ok(sql) = std::fs::read_to_string(&file) else { continue };
            let name = file.file_name().unwrap_or_default().to_string_lossy().to_string();
            for table in tables_created_in(&sql) {
                created.entry(table).or_insert_with(|| format!("{module}/{name}"));
            }
        }
    }
    created
}

/// Table names created by a chunk of SQL (`CREATE TABLE [IF NOT EXISTS] <name>`), lowercased.
fn tables_created_in(sql: &str) -> Vec<String> {
    let mut out = Vec::new();
    for statement in sql.split(';') {
        let code: String = statement
            .lines()
            .filter(|l| !l.trim_start().starts_with("--"))
            .collect::<Vec<_>>()
            .join(" ");
        let code = code.split_whitespace().collect::<Vec<_>>().join(" ");
        let upper = code.to_uppercase();
        let Some(idx) = upper.find("CREATE TABLE ") else { continue };
        let rest = &upper[idx + "CREATE TABLE ".len()..];
        let rest = rest.strip_prefix("IF NOT EXISTS ").unwrap_or(rest);
        if let Some(name) = rest.split(|c: char| c.is_whitespace() || c == '(').next() {
            let name = name.trim_matches(['"', '\'']).to_ascii_lowercase();
            if !name.is_empty() {
                out.push(name);
            }
        }
    }
    out
}

/// 🔴 Ratchet 1 — offline, CI-safe. A table a published `contract` retired cannot stay in the
/// inventory.
#[test]
fn no_money_column_names_a_table_a_published_contract_retired() {
    let retired = tables_retired_by_published_contracts();

    // POSITIVE CONTROL: the parser must actually find the retirements we know are in the fixtures.
    // Without this, a parser that returned an empty map would make the assertion below vacuously
    // green — the exact failure mode this ratchet exists to prevent.
    for known in ["services_addon", "services_variant", "kitchen_order_modifier"] {
        assert!(
            retired.contains_key(known),
            "positive control FAILED: `{known}` is retired by a frozen `contract` fixture and the \
             parser did not see it. The check below would be green without checking anything.\n\
             Retirements parsed: {:?}",
            retired.keys().collect::<Vec<_>>()
        );
    }

    let offenders: Vec<String> = MONEY_COLUMNS
        .iter()
        .filter_map(|(table, _)| {
            retired.get(*table).map(|source| format!("  · `{table}` — retired by `{source}`"))
        })
        .collect();

    assert!(
        offenders.is_empty(),
        "🔴 `MONEY_COLUMNS` names {} table(s) that a PUBLISHED `contract` migration already \
         retired:\n{}\n\n\
         The backfill skips them in silence, so nothing breaks today — and that is why they \
         survive. Remove the entry: the module no longer creates the table, so there is no money \
         there to convert (hub#1144, hub#1146).",
        offenders.len(),
        offenders.join("\n")
    );
}

/// 🔴 Ratchet 2 — against the real catalogue. Every table in the inventory must be created by some
/// published module migration; an entry for a module that does not exist is a phantom.
#[test]
fn every_money_table_is_created_by_a_published_module_migration() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let created = tables_created_by_the_catalogue();

    // POSITIVE CONTROL, two ways. (1) The sweep found a plausible catalogue — an empty or broken
    // read would otherwise "prove" that nothing is missing. (2) Money tables that ARE alive stay
    // alive: a check that dropped `sales_sale` or `services_service` would also be green and would
    // take the real backfill down with it (hub#1144).
    assert!(
        created.len() >= 100,
        "positive control FAILED: only {} tables read from the catalogue at {} — the sweep is \
         broken, and the assertion below would pass without checking anything.",
        created.len(),
        erplora_runtime::modules_root().display()
    );
    for alive in ["sales_sale", "services_service", "services_package", "inventory_product"] {
        assert!(
            created.contains_key(alive),
            "positive control FAILED: `{alive}` is a LIVE money table and the sweep did not find \
             its `CREATE TABLE`. Fix the sweep before trusting its verdict."
        );
    }

    let phantoms: Vec<String> = MONEY_COLUMNS
        .iter()
        .filter(|(table, _)| !created.contains_key(*table))
        .map(|(table, _)| format!("  · `{table}`"))
        .collect();

    assert!(
        phantoms.is_empty(),
        "🔴 `MONEY_COLUMNS` names {} table(s) that NO published module migration creates:\n{}\n\n\
         Either the module was archived (`kitchen_orders` merged into `kitchen`, ADR-0014) or it \
         never existed (`orders`). The backfill skips them in silence; the cost is that every \
         orphan audit has to prove by hand that the entry is not a live consumer (hub#1144).",
        phantoms.len(),
        phantoms.join("\n")
    );
}

/// 🔴 A duplicate `(table, column)` is not a cosmetic problem: `run()` converts a column once per
/// occurrence, so `ROUND(col*100)` would be applied twice and the amount multiplied by 10 000.
#[test]
fn no_money_column_is_listed_twice() {
    let mut seen: BTreeSet<(String, String)> = BTreeSet::new();
    let mut duplicates: Vec<String> = Vec::new();
    for (table, columns) in MONEY_COLUMNS {
        for column in *columns {
            if !seen.insert(((*table).to_string(), (*column).to_string())) {
                duplicates.push(format!("  · `{table}.{column}`"));
            }
        }
    }
    assert!(
        duplicates.is_empty(),
        "🔴 `MONEY_COLUMNS` lists {} column(s) twice:\n{}\n\n\
         The backfill would convert each of them once per occurrence: `ROUND(col*100)` applied \
         twice turns 12.34 € into 1 234 000 cents, not 1 234.",
        duplicates.len(),
        duplicates.join("\n")
    );
}

/// 🔴 The ORDER of `MONEY_COLUMNS` is NO LONGER load-bearing, and this pins THAT (ERPlora/hub#1209).
///
/// The ratchet that used to live here (`the_first_money_column_decides_and_is_pinned`) froze the
/// head of the list, because `seed_marker_if_cents()` and `run()` settled the verdict for the WHOLE
/// hub with the first money column that existed and returned right there. It guarded a symptom: it
/// made a reorder declare itself, but it could not stop a half-migrated hub from getting a verdict
/// by coin flip. hub#1209 removed the cause — `detect_money_unit()` classifies EVERY money column
/// present and demands unanimity — so the head of the list decides nothing any more, and freezing
/// it would only be a chore that fails on a legitimate edit.
///
/// What replaces it is the property itself, checked against a real database in
/// `money_backfill_mixed_hub.rs`: the same anomaly seeded with the units at the head and the tail
/// SWAPPED gets the same verdict (refused), where before it got the two opposite catastrophes.
/// This test keeps the list honest from the offline side: the entry that used to be pinned is still
/// a live money table, so retiring the pin did not quietly retire the column with it.
#[test]
fn the_order_no_longer_decides_but_the_old_head_is_still_inventoried_hub1209() {
    let inventoried: BTreeSet<(&str, &str)> = MONEY_COLUMNS
        .iter()
        .flat_map(|(table, columns)| columns.iter().map(move |c| (*table, *c)))
        .collect();

    assert!(
        inventoried.contains(&("appointments_appointment", "service_price")),
        "🔴 `appointments_appointment.service_price` left `MONEY_COLUMNS`. It used to be pinned as \
         the head that decided the verdict; hub#1209 removed that role, but the column is still \
         real money and must still be converted. If the module genuinely retired it, remove this \
         assertion in the same PR that removes the entry and say so."
    );

    // The verdict must not be reachable from list position any more: nothing in the runtime may
    // read `MONEY_COLUMNS[0]` as a decision. Guarded for real (seeded database, both orders) by
    // `money_backfill_mixed_hub.rs`; this is the cheap offline half of the same rule.
    let source = include_str!("../src/money_backfill.rs");
    assert!(
        !source.contains("MONEY_COLUMNS[0]"),
        "🔴 `money_backfill.rs` reads `MONEY_COLUMNS[0]`. The whole point of hub#1209 is that no \
         single position in this list decides whether a customer's money is multiplied by 100."
    );
}
